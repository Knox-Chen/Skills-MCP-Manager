#!/usr/bin/env python3
"""
MCP/Skills Smart Recommender - 数据管道
多数据源抓取（MCP + Skill），向量化后写入 Pinecone，元数据含 type / url / source。
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from typing import Any, Callable

import requests
from dotenv import load_dotenv

load_dotenv()

# 数据源配置：url, type ("MCP" | "Skill"), source 标识, 可选 base_url 用于解析相对链接
# 解析格式：支持 "- [名称](链接) - 描述"、"- [名称](链接)：描述"、* [名称](链接)、1. [名称](链接) 等。无抓取条数上限，BATCH_SIZE 仅用于 Pinecone 分批上传。
# 新增数据源：找 GitHub 上 README 含上述列表格式的仓库，用 raw 地址：https://raw.githubusercontent.com/owner/repo/main/README.md
DATA_SOURCES = [
    # ---------- MCP 数据源 ----------
    {
        "url": "https://raw.githubusercontent.com/punkpeye/awesome-mcp-servers/main/README.md",
        "type": "MCP",
        "source": "awesome-mcp-servers",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/README.md",
        "type": "MCP",
        "source": "official-mcp-servers",
        "base_url": "https://github.com/modelcontextprotocol/servers/blob/main/",
    },
    # ---------- Skill 数据源（格式：- [名称](链接) - 描述） ----------
    {
        "url": "https://raw.githubusercontent.com/VoltAgent/awesome-agent-skills/main/README.md",
        "type": "Skill",
        "source": "voltagent-awesome-agent-skills",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/heilcheng/awesome-agent-skills/main/README.md",
        "type": "Skill",
        "source": "heilcheng-awesome-agent-skills",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/philipbankier/awesome-agent-skills/main/README.md",
        "type": "Skill",
        "source": "philipbankier-awesome-agent-skills",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/skillmatic-ai/awesome-agent-skills/main/README.md",
        "type": "Skill",
        "source": "skillmatic-ai-awesome-agent-skills",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/libukai/awesome-agent-skills/main/README.md",
        "type": "Skill",
        "source": "libukai-awesome-agent-skills",
        "base_url": None,
    },
    {
        "url": "https://raw.githubusercontent.com/anthropics/skills/main/README.md",
        "type": "Skill",
        "source": "anthropics-skills-readme",
        "base_url": "https://github.com/anthropics/skills/blob/main/",
    },
    {
        "url": "https://raw.githubusercontent.com/openai/skills/main/README.md",
        "type": "Skill",
        "source": "openai-skills-readme",
        "base_url": None,
    },
    # 可继续追加：复制上面一个 Skill 块，改 url（GitHub 仓库的 raw README）和 source（唯一标识）即可
]

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EXPECTED_DIM = 384
# 每批写入 Pinecone 的条数（非抓取上限，抓取无上限）
BATCH_SIZE = 300

# 大批量入库目标：从 API 拉取至少各 1 万条（若 API 不足则能拉多少算多少）
MIN_MCP_FROM_REGISTRY = 10_000
MIN_SKILL_FROM_API = 10_000
MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
SKILLS_API_URL = "https://openagentskill.com/api/agent/skills"


# fastembed 下 384 维模型（与 all-MiniLM-L6-v2 同维，Pinecone 索引兼容）
FASTEMBED_MODEL_384 = "BAAI/bge-small-en-v1.5"


def _load_embedding_backend() -> tuple[Any, Callable[..., list[list[float]]]]:
    # 优先 fastembed（轻量，Railway 等 4GB 镜像可用）
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding(model_name=FASTEMBED_MODEL_384)
        def embed_fe(texts: list[str], expected_dim: int) -> list[list[float]]:
            vecs = list(model.embed(texts))
            result = [v.tolist() for v in vecs]
            for i, v in enumerate(result):
                if len(v) != expected_dim:
                    raise ValueError(f"维度不匹配: 第 {i} 条向量维度为 {len(v)}，期望 {expected_dim}。")
            return result
        return model, embed_fe
    except ImportError:
        pass
    except Exception as e:
        print(f"fastembed 加载失败，尝试 sentence_transformers: {e}", file=sys.stderr)
    # 回退到 sentence_transformers（本地/大内存环境）
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(EMBEDDING_MODEL)
        def embed_st(texts: list[str], expected_dim: int) -> list[list[float]]:
            vecs = model.encode(texts, show_progress_bar=True).tolist()
            for i, v in enumerate(vecs):
                if len(v) != expected_dim:
                    raise ValueError(f"维度不匹配: 第 {i} 条向量维度为 {len(v)}，期望 {expected_dim}。")
            return vecs
        return model, embed_st
    except (ImportError, OSError):
        pass
    print("错误: 请安装 fastembed（pip install fastembed）或 sentence-transformers。", file=sys.stderr)
    sys.exit(1)


def get_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None or (isinstance(val, str) and not val.strip()):
        print(f"错误: 未设置环境变量 {key}。请复制 .env.template 为 .env 并填写。", file=sys.stderr)
        sys.exit(1)
    return val.strip()


def fetch_readme(url: str) -> str:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"网络请求失败: {e}", file=sys.stderr)
        raise
    return resp.text


def _normalize_url(url: str, base_url: str | None) -> str:
    url = url.strip()
    if base_url and url and not url.startswith("http"):
        base = base_url.rstrip("/")
        return f"{base}{url}" if url.startswith("/") else f"{base}/{url}"
    return url


def _normalize_url_for_dedup(url: str) -> str:
    """用于去重键：统一小写、去掉末尾斜杠和常见差异，避免同一资源因 URL 写法不同重复入库。"""
    u = url.strip().lower()
    u = u.rstrip("/")
    # 去掉 ? 后的 query，避免同一页不同参数被当成不同条
    if "?" in u:
        u = u.split("?")[0]
    return u


def _extract_description(tail_clean: str) -> str:
    """从链接后的 tail 中提取描述。"""
    tail_clean = tail_clean.strip()
    if " - " in tail_clean:
        return tail_clean.split(" - ", 1)[1].strip()
    if re.match(r"^[：:]\s*", tail_clean):
        return re.sub(r"^[：:]\s*", "", tail_clean).strip()
    return tail_clean.strip("*").strip() or ""


def parse_markdown_list_items(md_text: str, item_type: str, source: str, base_url: str | None = None) -> list[dict[str, str]]:
    """解析 Markdown 列表项，提取 name, description, url；并注入 type / source。同一源内按 URL 去重。无条数上限。"""
    badge_pattern = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # 多种列表格式，尽量多匹配 Skill/MCP 条目（无抓取上限）
    patterns = [
        (r"^\s*-\s+\[([^\]]+)\]\(([^)]+)\)\s*(.*)$", "dash"),       # - [name](url) ...
        (r"^\s*\*\s+\[([^\]]+)\]\(([^)]+)\)\s*(.*)$", "asterisk"), # * [name](url) ...
        (r"^\s*\d+[\.\)]\s*\[([^\]]+)\]\(([^)]+)\)\s*(.*)$", "num"), # 1. [name](url) 或 1) [name](url)
    ]
    for pattern, _ in patterns:
        link_pattern = re.compile(pattern, re.MULTILINE)
        for m in link_pattern.finditer(md_text):
            name = m.group(1).strip().strip("*")
            url = _normalize_url(m.group(2).strip(), base_url)
            tail = m.group(3).strip()
            dedup_key = _normalize_url_for_dedup(url)
            if dedup_key in seen_urls:
                continue
            seen_urls.add(dedup_key)
            tail_clean = badge_pattern.sub("", tail).strip()
            description = _extract_description(tail_clean)
            items.append({
                "name": name,
                "description": description,
                "url": url,
                "type": item_type,
                "source": source,
            })
    return items


def compute_id(source: str, url: str) -> str:
    """不同来源的同一 URL 会得到不同 ID，避免冲突。"""
    return hashlib.md5(f"{source}\n{url}".encode("utf-8")).hexdigest()


def fetch_mcp_registry(min_count: int = MIN_MCP_FROM_REGISTRY) -> list[dict[str, str]]:
    """从官方 MCP Registry API 分页拉取，按 server name 去重，返回至少 min_count 条 MCP（若不足则全部）。"""
    items: list[dict[str, str]] = []
    seen_names: set[str] = set()
    cursor: str | None = None
    page_size = 200
    while len(items) < min_count:
        url = f"{MCP_REGISTRY_URL}?limit={page_size}"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"      MCP Registry 请求失败: {e}", file=sys.stderr)
            break
        except ValueError as e:
            print(f"      MCP Registry 响应非 JSON: {e}", file=sys.stderr)
            break
        servers = data.get("servers") or []
        meta = data.get("metadata") or {}
        for ent in servers:
            s = (ent.get("server") or ent) if isinstance(ent, dict) else {}
            name = (s.get("name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            title = (s.get("title") or name).strip()
            desc = (s.get("description") or "").strip()[:2000]
            url_val = s.get("websiteUrl") or ""
            if not url_val and s.get("repository"):
                url_val = (s["repository"].get("url") or "") if isinstance(s["repository"], dict) else ""
            if not url_val and (s.get("remotes") or []):
                url_val = (s["remotes"][0].get("url") or "") if isinstance(s["remotes"][0], dict) else ""
            if not url_val:
                url_val = f"https://github.com/search?q=mcp+{name.replace('/', '+')}"
            items.append({
                "name": title or name,
                "description": desc,
                "url": url_val[:1000],
                "type": "MCP",
                "source": "mcp-registry-official",
            })
            if len(items) >= min_count:
                break
        print(f"      [MCP Registry] 本页 {len(servers)} 条，累计 {len(items)} 条（去重后）")
        cursor = meta.get("nextCursor")
        if not cursor or not servers:
            break
    return items


def fetch_skills_from_api(min_count: int = MIN_SKILL_FROM_API) -> list[dict[str, str]]:
    """从 Open Agent Skill API 拉取 Skill；若 API 支持分页则拉满 min_count，否则拉单页（可能数千条）。"""
    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    page_size = 2000
    offset = 0
    while len(items) < min_count:
        try:
            resp = requests.get(
                SKILLS_API_URL,
                params={"format": "json", "limit": page_size, "offset": offset},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"      Skill API 请求失败: {e}", file=sys.stderr)
            break
        except ValueError as e:
            print(f"      Skill API 响应非 JSON: {e}", file=sys.stderr)
            break
        skills = data.get("skills") or []
        for s in skills:
            url_val = (s.get("urls") or {}).get("repository") or s.get("repository") or (s.get("urls") or {}).get("detail") or ""
            if not url_val:
                url_val = f"https://openagentskill.com/skills/{s.get('slug', '')}"
            key = _normalize_url_for_dedup(url_val)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            name = (s.get("name") or s.get("slug") or "").strip()[:500]
            desc = (s.get("description") or "").strip()[:2000]
            items.append({
                "name": name,
                "description": desc,
                "url": url_val[:1000],
                "type": "Skill",
                "source": "openagentskill-api",
            })
            if len(items) >= min_count:
                break
        print(f"      [Skill API] 本页 {len(skills)} 条，累计 {len(items)} 条")
        if len(skills) < page_size:
            break
        offset += page_size
        if offset > 50000:
            break
    return items


def embed_texts(embed_fn: Callable[..., list[list[float]]], texts: list[str], expected_dim: int) -> list[list[float]]:
    return embed_fn(texts, expected_dim)


def run_ingest() -> None:
    api_key = get_env("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "mcp-skills").strip()

    all_items: list[dict[str, str]] = []
    existing_dedup_keys: set[str] = set()

    def merge_items(new_items: list[dict[str, str]], label: str) -> None:
        nonlocal all_items, existing_dedup_keys
        added = 0
        for it in new_items:
            key = _normalize_url_for_dedup(it["url"])
            if key in existing_dedup_keys:
                continue
            existing_dedup_keys.add(key)
            all_items.append(it)
            added += 1
        if new_items:
            print(f"      {label} 新增 {added} 条，跨源去重后累计 {len(all_items)} 条")

    # 1a) 从官方 MCP Registry API 拉取至少 MIN_MCP_FROM_REGISTRY 条
    print(f"[1a] MCP Registry API（目标 ≥{MIN_MCP_FROM_REGISTRY} 条）")
    mcp_registry_items = fetch_mcp_registry(MIN_MCP_FROM_REGISTRY)
    merge_items(mcp_registry_items, "MCP Registry")

    # 1b) 从 Open Agent Skill API 拉取至少 MIN_SKILL_FROM_API 条
    print(f"[1b] Skill API（目标 ≥{MIN_SKILL_FROM_API} 条）")
    skill_api_items = fetch_skills_from_api(MIN_SKILL_FROM_API)
    merge_items(skill_api_items, "Skill API")

    # 1c) 抓取并解析各 Markdown 数据源（补充）
    for cfg in DATA_SOURCES:
        url, item_type, source, base_url = cfg["url"], cfg["type"], cfg["source"], cfg.get("base_url")
        print(f"[1] 抓取: {source} ({url[:60]}...)")
        try:
            raw = fetch_readme(url)
        except Exception:
            print(f"      跳过（抓取失败）")
            continue
        parsed = parse_markdown_list_items(raw, item_type, source, base_url)
        merge_items(parsed, f"{source} Markdown")

    if not all_items:
        print("未解析到任何条目，退出。", file=sys.stderr)
        sys.exit(1)

    # 3) 向量化
    print(f"[3] 加载 Embedding 模型: {EMBEDDING_MODEL} (维度 {EXPECTED_DIM})")
    _model, embed_fn = _load_embedding_backend()
    texts = [f"{it['name']} {it['description']}".strip() or it["name"] for it in all_items]
    vectors = embed_texts(embed_fn, texts, EXPECTED_DIM)

    # 4) 连接 Pinecone 并 upsert（metadata 含 type, url, source）
    print(f"[4] 连接 Pinecone 索引: {index_name}")
    try:
        from pinecone import AwsRegion, CloudProvider, Metric, Pinecone, ServerlessSpec
        pc = Pinecone(api_key=api_key)
        existing = list(pc.list_indexes().names()) if pc.list_indexes() else []
        if index_name not in existing:
            print(f"      索引不存在，正在创建 (dimension={EXPECTED_DIM}, metric=cosine)...")
            pc.create_index(
                name=index_name,
                dimension=EXPECTED_DIM,
                metric=Metric.COSINE,
                spec=ServerlessSpec(cloud=CloudProvider.AWS, region=AwsRegion.US_EAST_1),
            )
            print("      索引创建请求已提交，请稍候再运行本脚本完成写入。")
            sys.exit(0)
        index = pc.Index(index_name)
    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "Unauthorized" in err_str or "Invalid API Key" in err_str:
            print("连接 Pinecone 失败: API Key 无效或已过期。请检查 .env 中的 PINECONE_API_KEY。", file=sys.stderr)
        else:
            print(f"连接 Pinecone 失败: {e}", file=sys.stderr)
        sys.exit(1)

    to_upsert: list[dict[str, Any]] = []
    for item, vec in zip(all_items, vectors):
        vid = compute_id(item["source"], item["url"])
        meta: dict[str, str] = {
            "type": item["type"],
            "url": item["url"][:1000],
            "source": item["source"][:200],
            "name": item["name"][:500],
            "description": (item.get("description") or "")[:2000],
        }
        to_upsert.append({"id": vid, "values": vec, "metadata": meta})

    total = len(to_upsert)
    for start in range(0, total, BATCH_SIZE):
        batch = to_upsert[start : start + BATCH_SIZE]
        try:
            index.upsert(vectors=batch)
        except Exception as e:
            print(f"Upsert 失败 (offset {start}): {e}", file=sys.stderr)
            sys.exit(1)
        print(f"      已入库: {min(start + BATCH_SIZE, total)} / {total}")

    # 入库统计：MCP 与 Skill 数量
    n_mcp = sum(1 for it in all_items if it.get("type") == "MCP")
    n_skill = sum(1 for it in all_items if it.get("type") == "Skill")
    print("完成。数据已写入 Pinecone。")
    print(f"入库统计: MCP {n_mcp} 条, Skill {n_skill} 条，合计 {total} 条。")


if __name__ == "__main__":
    run_ingest()
