#!/usr/bin/env python3
"""
MCP/Skills Smart Recommender - 检索与推荐
HyDE + 集成检索 + OpenAI 重排，输出最匹配的 MCP 工具及组合建议。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# 与 ingest 保持一致：384 维 all-MiniLM-L6-v2
from ingest import (
    EXPECTED_DIM,
    EMBEDDING_MODEL,
    _load_embedding_backend,
    get_env,
)


def get_optional_env(key: str, default: str | None = None) -> str | None:
    val = os.environ.get(key, default)
    if val is None or (isinstance(val, str) and not val.strip()):
        return None
    return val.strip()


def _clean_api_key(key: str) -> str:
    """去除首尾空格和常见不可见字符，避免 401 API key format is incorrect。"""
    if not key:
        return key
    # 去除 BOM、零宽字符、多余空白
    key = key.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\u2028", "").replace("\u2029", "")
    key = " ".join(key.split()).strip()
    return key


def _doubao_client():
    """统一豆包 API 客户端：所有 LLM 调用均走豆包。"""
    raw_key = get_optional_env("DOUBAO_API_KEY") or get_optional_env("VOLC_API_KEY")
    api_key = _clean_api_key(raw_key) if raw_key else ""
    base_url = (get_optional_env("DOUBAO_BASE_URL") or get_optional_env("VOLC_BASE_URL") or "https://ark.cn-beijing.volces.com/api/v3").strip().rstrip("/")
    raw_ep = get_optional_env("DOUBAO_ENDPOINT_ID") or get_optional_env("VOLC_ENDPOINT_ID")
    endpoint_id = _clean_api_key(raw_ep) if raw_ep else ""
    if not api_key or not endpoint_id:
        raise RuntimeError(
            "未配置豆包 API。请在 .env 中填写：\n"
            "  DOUBAO_API_KEY=你的API_Key\n"
            "  DOUBAO_ENDPOINT_ID=你的推理接入点ID（ep- 开头）\n"
            "获取方式见 .env.template 或项目说明。"
        )
    try:
        from openai import OpenAI
    except ImportError:
        print("请安装: pip install openai", file=sys.stderr)
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, endpoint_id


def generate_hypothetical_doc(user_idea: str) -> tuple[str, float]:
    """
    根据用户 Idea 生成「理想的 MCP 工具技术说明」用于 HyDE。极简 prompt 与 token 以提速。
    返回 (文档内容, 耗时毫秒)。
    """
    t0 = time.perf_counter()
    client, model = _doubao_client()
    prompt = f"""根据用户需求写一句「理想 MCP 工具技术说明」（抽象描述，不写具体项目名），用于向量检索。1-2 句即可。

用户需求：{user_idea}

直接输出说明内容，不要标题："""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=180,
        )
    except Exception as e:
        err = str(e).lower()
        if "401" in err or "authentication" in err or "api key format" in err:
            raise RuntimeError(
                "豆包 API 鉴权失败（401）。请检查 .env：\n"
                "  1) DOUBAO_API_KEY 是否从火山方舟完整复制，无多余空格、引号、换行；\n"
                "  2) DOUBAO_ENDPOINT_ID 是否为 ep- 开头的接入点 ID；\n"
                "  3) 若从网页复制，可重新手打一行或删除首尾再保存。\n"
                f"原始错误: {e}"
            ) from e
        raise
    text = (resp.choices[0].message.content or "").strip()
    time_hyde_ms = round((time.perf_counter() - t0) * 1000)
    return (text or user_idea, time_hyde_ms)


def load_components():
    """加载本地向量化组件并连接 Pinecone；结果全局缓存，后续请求复用（显著缩短 E2E）。"""
    global _cached_embed_fn, _cached_index
    if _cached_embed_fn is not None and _cached_index is not None:
        return _cached_embed_fn, _cached_index
    print("加载组件：使用本地 all-MiniLM-L6-v2 模型进行向量化，连接 Pinecone...")
    embed_model, embed_fn = _load_embedding_backend()
    if "fastembed" in type(embed_model).__module__:
        print("  使用 fastembed 后端（384 维）")
    else:
        print("  使用 sentence_transformers 后端（384 维）")

    api_key = get_env("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX_NAME", "mcp-skills").strip()
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=api_key)
        index = pc.Index(index_name)
    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "Unauthorized" in err_str or "Invalid API Key" in err_str:
            print("  Pinecone API Key 无效或未配置，请检查 .env 中的 PINECONE_API_KEY。", file=sys.stderr)
        else:
            print(f"  连接 Pinecone 失败: {e}", file=sys.stderr)
        sys.exit(1)
    print("  Pinecone 已连接。")
    _cached_embed_fn, _cached_index = embed_fn, index
    return embed_fn, index


# 推荐时 MCP 与 Skill 各自至少数量
MIN_MCP_PER_RECOMMEND = 5
MIN_SKILL_PER_RECOMMEND = 5

# 并行检索 top_k（单路），保证候选池足够以筛出至少 5 MCP + 5 Skill
RETRIEVAL_TOP_K = 24
# 预筛：取前 N 进入重排（N 越小 LLM 输入/输出越少，耗时越短；仍通过 need_mcp/need_skill 保证至少 5+5）
PRE_RERANK_TOP_N = 12
# 是否打印各阶段耗时（性能诊断）
PERF_LOG = os.environ.get("RECOMMEND_PERF_LOG", "1").strip().lower() in ("1", "true", "yes")

# 默认线程池用于 run_in_executor
_default_executor: ThreadPoolExecutor | None = None

# 全局缓存：首次请求后复用，避免每次加载模型和 Pinecone（E2E 最大瓶颈）
_cached_embed_fn = None
_cached_index = None


def _get_executor() -> ThreadPoolExecutor:
    global _default_executor
    if _default_executor is None:
        _default_executor = ThreadPoolExecutor(max_workers=4)
    return _default_executor


def _query_pinecone_sync(embed_fn, index, text: str, top_k: int, label: str = "") -> list[dict]:
    """同步：向量化 text 并在 Pinecone 检索，返回 [{"id", "score", "metadata"}, ...]。"""
    tag = f" [{label}]" if label else ""
    t0 = time.perf_counter()
    vec = embed_fn([text], EXPECTED_DIM)[0]
    t_embed = time.perf_counter() - t0
    t1 = time.perf_counter()
    r = index.query(vector=vec, top_k=top_k, include_metadata=True)
    t_search = time.perf_counter() - t1
    if PERF_LOG:
        print(f"  [Perf]{tag} Embedding took {t_embed:.2f}s, Pinecone Search took {t_search:.2f}s", file=sys.stderr)
    out = []
    for m in r.matches or []:
        score = getattr(m, "score", None)
        out.append({
            "id": m.id,
            "score": score if score is not None else 0.0,
            "metadata": (m.metadata or {}),
        })
    return out


def _pre_rerank_math_select(merged_with_scores: list[dict]) -> list[dict]:
    """
    数学预选（LLM rerank 前粗筛）：
    - 同时兼顾「相关性」与「类型多样性」；
    - 保证只要索引里有 MCP，就一定有 MCP 进入重排，而不是被 Skill 全部挤掉；
    - 默认留下最多 PRE_RERANK_TOP_N 条进入 LLM 重排。
    """
    if not merged_with_scores:
        return []

    def _sorted_desc(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda t: float(t.get("score") or 0.0), reverse=True)

    def _high_relevance(items: list[dict]) -> list[dict]:
        """对同一类型内部按相对得分做粗筛，滤掉该类型里明显弱相关的尾部。"""
        if not items:
            return []
        items_sorted = _sorted_desc(items)
        max_s = float(items_sorted[0].get("score") or 0.0)
        if max_s <= 0:
            return items_sorted
        rel = max_s * 0.7
        abs_t = max_s - 0.15
        threshold = min(rel, abs_t)
        return [t for t in items_sorted if float(t.get("score") or 0.0) >= threshold]

    # 按类型拆分
    by_type: dict[str, list[dict]] = {}
    for t in merged_with_scores:
        typ = (t.get("metadata") or {}).get("type") or "N/A"
        by_type.setdefault(typ, []).append(t)

    mcp_all = by_type.get("MCP", [])
    skill_all = by_type.get("Skill", [])

    mcp_high = _high_relevance(mcp_all)
    skill_high = _high_relevance(skill_all)

    selected: list[dict] = []
    seen_ids: set[str] = set()

    # 1) 先从各类型的高相关集合里挑：保证 MCP / Skill 至少有代表进入重排
    for t in mcp_high[:MIN_MCP_PER_RECOMMEND]:
        if t["id"] in seen_ids:
            continue
        selected.append(t)
        seen_ids.add(t["id"])
    for t in skill_high[:MIN_SKILL_PER_RECOMMEND]:
        if t["id"] in seen_ids:
            continue
        selected.append(t)
        seen_ids.add(t["id"])

    # 2) 若还没到 PRE_RERANK_TOP_N，用全局高分结果补齐（不限类型）
    if len(selected) < PRE_RERANK_TOP_N:
        all_sorted = _sorted_desc(merged_with_scores)
        for t in all_sorted:
            if t["id"] in seen_ids:
                continue
            selected.append(t)
            seen_ids.add(t["id"])
            if len(selected) >= PRE_RERANK_TOP_N:
                break

    return selected[:PRE_RERANK_TOP_N]


def _rerank_ids_only(client, model: str, candidates_short: list[dict], user_idea: str) -> list[str]:
    """
    极简 Rerank：只传 id/name/desc_summary，强制 LLM 只输出选中的 ID 列表（无分析）。
    返回解析出的 ID 列表。
    """
    safe = []
    for c in candidates_short:
        safe.append({
            "id": c["id"],
            "name": (c.get("name") or "")[:60],
            "desc_summary": (c.get("desc_summary") or "")[:80],
        })
    json_str = json.dumps(safe, ensure_ascii=False, indent=0)
    prompt = f"""用户需求：{user_idea}

候选工具（仅 id/name/desc_summary）：
{json_str}

请只输出你选中的工具 id 列表，用英文逗号分隔，不要任何分析、不要标题。例如：id1,id2,id3"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception:
        return [c["id"] for c in candidates_short[:PRE_RERANK_TOP_N]]
    valid_ids = {c["id"] for c in candidates_short}
    ids = []
    for part in re.split(r"[,，\s\n]+", text):
        part = part.strip().strip('"\'')
        if part and part in valid_ids:
            ids.append(part)
    seen = set()
    out = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out if out else [c["id"] for c in candidates_short[:PRE_RERANK_TOP_N]]


def _summary_with_full_tools(client, model: str, selected_full: list[dict], user_idea: str) -> str:
    """本地回填后，用完整工具信息做一次方案总结（架构师风格）。"""
    tools_text = "\n".join(
        f"- {m.get('name', 'N/A')} [类型: {m.get('type', 'N/A')}] | 描述: {m.get('description', '')[:280]} | 链接: {m.get('url', '')}"
        for t in selected_full
        for m in [t.get("metadata") or {}]
    )
    prompt = f"""你是一位资深 AI 架构师。用户需求：{user_idea}

已选工具（名称/类型/描述/链接）：
{tools_text}

请按以下结构输出：
## 一、推荐清单
对每个工具给出：工具名 [MCP/Skill]（链接）、一句话描述、推荐原因、项目适配度 x/10。
## 二、深度实现方案
2.1 开发流程（Step-by-step）
2.2 技术栈建议
2.3 组合逻辑与数据流

直接输出，不要前缀。"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"方案总结生成失败: {e}"


def _rerank_and_summary_one_call(
    client, model: str, candidates_short: list[dict], full_items: list[dict], user_idea: str
) -> tuple[list[str], str, list[str], list[float], str]:
    """
    一次 LLM 调用：选 ID + 根据用户 query 与每个工具的【介绍】生成推荐理由 + 匹配度 + 实施路线图（步骤1、步骤2…格式）。
    返回 (selected_ids, reasoning_full, reasons_list, match_scores_list, roadmap_text)。
    """
    payload = []
    for c in candidates_short:
        desc = (c.get("desc_summary") or "").strip()[:220]
        if not desc:
            desc = (c.get("name") or c["id"] or "工具") + "，可结合用户需求评估是否适用。"
        payload.append({"id": c["id"], "name": (c.get("name") or "")[:40], "介绍": desc})
    json_str = json.dumps(payload, ensure_ascii=False)
    prompt = f"""用户需求：
{user_idea}

候选工具（id、name、介绍；介绍来自该工具 readme/说明）：
{json_str}

请严格按以下格式输出：
第一段：只写选中的工具 id，用英文逗号分隔。必须从下面候选里选出至少 10 个（或全部），不要只选 3～4 个。例如：id1,id2,id3,id4,...

第二段：空一行后——
一、推荐清单：对【每一个】第一段中列出的工具，按相同顺序各写【三行】：
  第1行：该工具名或 id
  第2行：推荐原因：（必写）根据【用户需求】与上面该工具的【介绍】写一句推荐理由，说明为何适合本需求，不要写「结合用户需求该工具适合纳入方案」这种泛泛的句子。
  第3行：匹配度：x/10（1-10 分）
  下一个工具同样三行，共 N 组（N = 第一段 id 个数）。

二、跳过

三、实施路线图：严格按「步骤1：xxx」换行「步骤2：xxx」换行……「步骤n：xxx」的格式输出，每步一行，只写步骤内容，不要用 - 或 1. 2. 等其它格式。"""
    try:
        # 输出包含 N 组（工具名+推荐原因+匹配度）+ 实施路线图，需足够 token 避免截断导致多数理由被默认句补齐
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3200,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception:
        ids = [c["id"] for c in candidates_short[:PRE_RERANK_TOP_N]]
        return ids, "方案生成失败。", [], [], ""
    lines = text.split("\n")
    first_line = (lines[0] if lines else "").strip()
    valid_ids = {c["id"] for c in candidates_short}
    ids = []
    for part in re.split(r"[,，\s]+", first_line):
        part = part.strip().strip('"\'')
        if part and part in valid_ids:
            ids.append(part)
    seen = set()
    selected_ids = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            selected_ids.append(i)
    if not selected_ids:
        selected_ids = [c["id"] for c in candidates_short[:PRE_RERANK_TOP_N]]
    reasoning = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    if not reasoning:
        id_to_item = {t["id"]: t for t in full_items}
        names = [id_to_item.get(i, {}).get("metadata", {}).get("name", i) for i in selected_ids]
        reasoning = "推荐工具：" + "、".join(names) + "。"
    # 只在「一、推荐清单」段落内解析，避免匹配到实施路线图里的内容
    list_section = reasoning
    for sep in ("三、实施路线图", "三、实施路线", "## 实施路线图", "二、"):
        idx = reasoning.find(sep)
        if idx >= 0:
            list_section = reasoning[:idx]
            break
    reasons = re.findall(r"推荐原因[：:]\s*([^\n]+)", list_section)
    if len(reasons) < len(selected_ids):
        reasons = re.findall(r"原因[：:]\s*([^\n]+)", list_section)
    # 保证每条都有理由：不足的用默认句补齐，确保每个 skill/MCP 都配上推荐理由
    default_reason = "结合用户需求，该工具适合纳入方案。"
    while len(reasons) < len(selected_ids):
        reasons.append(default_reason)
    reasons = reasons[: len(selected_ids)]
    # 解析匹配度：x/10 或 匹配度：x
    match_scores_raw = re.findall(r"匹配度[：:]\s*(\d+)(?:/\s*10)?", reasoning)
    match_scores_list = []
    for s in match_scores_raw:
        try:
            x = int(s.strip())
            match_scores_list.append(min(100, max(0, x * 10 if x <= 10 else x)))
        except ValueError:
            match_scores_list.append(0)
    # 解析「三、实施路线图」之后的内容为纯路线图（不含推荐理由与推荐清单）
    roadmap_text = ""
    for sep in ("三、实施路线图", "三、实施路线", "实施路线图", "## 实施路线图"):
        idx = reasoning.find(sep)
        if idx >= 0:
            roadmap_text = reasoning[idx + len(sep) :].strip()
            # 去掉开头的冒号、换行等
            roadmap_text = re.sub(r"^[：:\s\n]+", "", roadmap_text)
            break
    if not roadmap_text and reasoning:
        # 若没有明确标题，取「二、」之后或最后一个「步骤」段落
        parts = re.split(r"一、|二、|三、", reasoning, maxsplit=3)
        if len(parts) >= 4:
            roadmap_text = parts[-1].strip()
        elif len(parts) >= 2:
            roadmap_text = parts[-1].strip()
    # 统一为「步骤1：…换行步骤2：…换行步骤n：…」格式，每步一行
    roadmap_text = _normalize_roadmap_steps(roadmap_text)
    return selected_ids, reasoning, reasons, match_scores_list, roadmap_text


def _normalize_roadmap_steps(text: str) -> str:
    """将实施路线图规范为 步骤1：xxx\\n步骤2：xxx\\n… 每步一行。"""
    if not (text or "").strip():
        return text or ""
    text = text.strip()
    # 按「步骤N」分割，保留序号与内容（每步一行）
    chunks = re.split(r"(?=步骤\s*\d+\s*[：:])", text)
    lines = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        m = re.match(r"^步骤\s*(\d+)\s*[：:]\s*(.*)$", ch, re.DOTALL)
        if m:
            content = m.group(2).strip().replace("\n", " ").strip()
            lines.append(f"步骤{m.group(1)}：{content}")
    if lines:
        return "\n".join(lines)
    # 兼容按行写的 步骤1：... 或 1. ...
    lines = []
    for i, line in enumerate(re.split(r"[\n]+", text)):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^步骤\s*(\d+)\s*[：:]\s*(.*)$", line)
        if m:
            lines.append(f"步骤{m.group(1)}：{m.group(2).strip()}")
        else:
            # 行首为数字. 或 - 步骤 等
            m2 = re.match(r"^[\-\*]?\s*步骤\s*(\d+)\s*[：:]\s*(.*)$", line)
            if m2:
                lines.append(f"步骤{m2.group(1)}：{m2.group(2).strip()}")
            elif re.match(r"^\d+\s*[\.．]\s*", line):
                num = re.match(r"^(\d+)\s*[\.．]\s*(.*)$", line)
                if num:
                    lines.append(f"步骤{num.group(1)}：{num.group(2).strip()}")
            else:
                lines.append(line)
    return "\n".join(lines) if lines else text


def _query_by_type(index, embed_fn, query_text: str, item_type: str, top_k: int) -> list[dict]:
    """按 type 过滤检索，返回 [{"id", "metadata"}, ...]。若索引不支持 filter 则退回无过滤并按 type 筛结果。"""
    vec = embed_fn([query_text], EXPECTED_DIM)[0]
    try:
        r = index.query(
            vector=vec,
            top_k=top_k * 2,
            include_metadata=True,
            filter={"type": {"$eq": item_type}},
        )
        out = [{"id": m.id, "metadata": (m.metadata or {})} for m in (r.matches or [])]
    except Exception:
        r = index.query(vector=vec, top_k=top_k * 3, include_metadata=True)
        out = [
            {"id": m.id, "metadata": (m.metadata or {})}
            for m in (r.matches or [])
            if (m.metadata or {}).get("type") == item_type
        ][:top_k]
    return out[: top_k + 5]


def ensemble_retrieve(embed_fn, index, user_idea: str, hypothetical_doc: str, top_k: int = 12) -> tuple[list[dict], float, float | None]:
    """
    集成检索：路径 A + 路径 B 合并去重；
    并保证候选池中 MCP 与 Skill 各至少 MIN_MCP_PER_RECOMMEND / MIN_SKILL_PER_RECOMMEND 条（不足则按 type 补查）。
    返回 (merged, time_retrieval_ms, top1_score)，top1_score 为路径 A（用户 query）的 Top-1 原始得分。
    """
    t0 = time.perf_counter()
    # 路径 A
    q_vec_a = embed_fn([user_idea], EXPECTED_DIM)[0]
    r_a = index.query(vector=q_vec_a, top_k=top_k, include_metadata=True)
    matches_a = r_a.matches or []
    ids_a = [m.id for m in matches_a]
    meta_a = {m.id: (m.metadata or {}) for m in matches_a}
    top1_score = getattr(matches_a[0], "score", None) if matches_a else None

    # 路径 B
    q_vec_b = embed_fn([hypothetical_doc], EXPECTED_DIM)[0]
    r_b = index.query(vector=q_vec_b, top_k=top_k, include_metadata=True)
    ids_b = [m.id for m in (r_b.matches or [])]
    meta_b = {m.id: (m.metadata or {}) for m in (r_b.matches or [])}

    # 合并去重：两路都出现的排最前
    set_a, set_b = set(ids_a), set(ids_b)
    both = [iid for iid in ids_a if iid in set_b]
    only_a = [iid for iid in ids_a if iid not in set_b]
    only_b = [iid for iid in ids_b if iid not in set_a]
    merged_ids = both + only_a + only_b
    metadata_by_id = {**meta_a, **meta_b}

    merged = []
    seen = set()
    for iid in merged_ids:
        if iid not in seen:
            seen.add(iid)
            merged.append({"id": iid, "metadata": metadata_by_id.get(iid) or {}})

    # 按 type 统计，不足则补查
    by_type = {}
    for t in merged:
        typ = (t.get("metadata") or {}).get("type") or "N/A"
        by_type.setdefault(typ, []).append(t)
    need_mcp = max(0, MIN_MCP_PER_RECOMMEND - len(by_type.get("MCP", [])))
    need_skill = max(0, MIN_SKILL_PER_RECOMMEND - len(by_type.get("Skill", [])))
    existing_ids = {t["id"] for t in merged}

    if need_mcp > 0:
        extra = _query_by_type(index, embed_fn, user_idea, "MCP", need_mcp + 10)
        for t in extra:
            if t["id"] not in existing_ids:
                existing_ids.add(t["id"])
                merged.append(t)
    if need_skill > 0:
        extra = _query_by_type(index, embed_fn, user_idea, "Skill", need_skill + 10)
        for t in extra:
            if t["id"] not in existing_ids:
                existing_ids.add(t["id"])
                merged.append(t)

    time_retrieval_ms = round((time.perf_counter() - t0) * 1000)
    return merged, time_retrieval_ms, top1_score


async def _recommend_async(user_idea: str, top_k: int, embed_fn, index) -> dict[str, Any]:
    """
    极致提速：双路并行检索（user_idea 与 HyDE 并行）→ 预筛 → 极简 Rerank(ID) → 本地回填 → 方案总结。
    """
    loop = asyncio.get_event_loop()
    executor = _get_executor()
    t_start = time.perf_counter()

    def run_sync(fn, *args, **kwargs):
        return loop.run_in_executor(executor, lambda: fn(*args, **kwargs))

    # 并发：Task 1 = Idea 向量检索，Task 2 = 豆包 HyDE，同时执行不等待
    t_before_retrieval = time.perf_counter()
    path_a_fut = run_sync(_query_pinecone_sync, embed_fn, index, user_idea, RETRIEVAL_TOP_K, "Idea")
    hyde_fut = run_sync(generate_hypothetical_doc, user_idea)
    path_a, hyde_result = await asyncio.gather(path_a_fut, hyde_fut)
    hypothetical_doc, time_hyde_ms = hyde_result
    t_after_path_a_hyde = time.perf_counter()
    if PERF_LOG:
        print(f"  [Perf] PathA+Idea + HyDE 并行完成 wall={t_after_path_a_hyde - t_before_retrieval:.2f}s (HyDE={time_hyde_ms/1000:.2f}s)", file=sys.stderr)

    # Task 3: HyDE 生成后，用 HyDE 向量检索
    path_b = await run_sync(_query_pinecone_sync, embed_fn, index, hypothetical_doc, RETRIEVAL_TOP_K, "HyDE")
    t_retrieval_end = time.perf_counter()
    time_retrieval_ms = round((t_retrieval_end - t_start) * 1000)
    if PERF_LOG:
        print(f"  [Perf] PathB+HyDE 检索完成 wall={t_retrieval_end - t_after_path_a_hyde:.2f}s", file=sys.stderr)

    # 合并去重（按 id 保留最大 score）
    t_merge_start = time.perf_counter()
    by_id: dict[str, dict] = {}
    for t in path_a + path_b:
        iid = t["id"]
        if iid not in by_id or t["score"] > by_id[iid]["score"]:
            by_id[iid] = dict(t)
    merged_with_scores = list(by_id.values())
    if PERF_LOG:
        print(f"  [Perf] 检索合并去重后候选数={len(merged_with_scores)}（若很少则多半是索引里数据少）", file=sys.stderr)

    # 数学预选：仅按 score 排序取前 12，不让大模型处理全部召回
    filtered = _pre_rerank_math_select(merged_with_scores)
    if not filtered:
        filtered = merged_with_scores[:PRE_RERANK_TOP_N]
    if PERF_LOG:
        print(f"  [Perf] Math pre-select (merge+top{PRE_RERANK_TOP_N}) took {time.perf_counter() - t_merge_start:.2f}s, 进入重排={len(filtered)}", file=sys.stderr)

    # 保证 MCP/Skill 至少各有 MIN（分 type 精准补齐，避免被 Skill「刷屏」）
    by_type = {}
    for t in filtered:
        typ = (t.get("metadata") or {}).get("type") or "N/A"
        by_type.setdefault(typ, []).append(t)
    need_mcp = max(0, MIN_MCP_PER_RECOMMEND - len(by_type.get("MCP", [])))
    need_skill = max(0, MIN_SKILL_PER_RECOMMEND - len(by_type.get("Skill", [])))
    existing_ids = {t["id"] for t in filtered}
    if need_mcp or need_skill:
        extra_mcp: list[dict] = []
        extra_skill: list[dict] = []
        if need_mcp:
            # 明确按 type=MCP 再查一轮，避免被 Skill 盖过导致没有 MCP 进入候选
            extra_mcp = await run_sync(_query_pinecone_sync, embed_fn, index, user_idea, need_mcp + 10, "MCP补齐")
            extra_mcp = [t for t in extra_mcp if (t.get("metadata") or {}).get("type") == "MCP"]
        if need_skill:
            extra_skill = await run_sync(_query_pinecone_sync, embed_fn, index, user_idea, need_skill + 10, "Skill补齐")
            extra_skill = [t for t in extra_skill if (t.get("metadata") or {}).get("type") == "Skill"]
        for t in extra_mcp + extra_skill:
            if t["id"] in existing_ids:
                continue
            typ = (t.get("metadata") or {}).get("type")
            if need_mcp and typ == "MCP":
                filtered.append(t)
                existing_ids.add(t["id"])
                need_mcp -= 1
            elif need_skill and typ == "Skill":
                filtered.append(t)
                existing_ids.add(t["id"])
                need_skill -= 1
            if need_mcp == 0 and need_skill == 0:
                break

    # 一次 LLM 调用：选 ID + 每条推荐理由 + 匹配度 + 路线图（此处为最耗时步骤）
    candidates_short = [
        {
            "id": t["id"],
            "name": (t.get("metadata") or {}).get("name", "") or t["id"],
            "desc_summary": ((t.get("metadata") or {}).get("description") or "")[:220],
        }
        for t in filtered
    ]
    if PERF_LOG:
        print(f"  [Perf] 进入重排候选数={len(candidates_short)}", file=sys.stderr)
    client, model = _doubao_client()
    t_rerank_start = time.perf_counter()
    selected_ids, reasoning, reasons_list, match_scores_list, roadmap_text = await run_sync(
        _rerank_and_summary_one_call, client, model, candidates_short, filtered, user_idea
    )
    id_to_item = {t["id"]: t for t in filtered}
    selected_full = []
    for iid in selected_ids:
        if iid in id_to_item:
            selected_full.append(id_to_item[iid])
    for t in filtered:
        if t["id"] not in {x["id"] for x in selected_full} and len(selected_full) < PRE_RERANK_TOP_N:
            selected_full.append(t)
    # 保证最终至少 5 MCP + 5 Skill（不足则从 filtered 按类型补足）
    sel_ids = {t["id"] for t in selected_full}
    by_type_sel = {}
    for t in selected_full:
        typ = (t.get("metadata") or {}).get("type") or "N/A"
        by_type_sel.setdefault(typ, []).append(t)
    need_mcp = max(0, MIN_MCP_PER_RECOMMEND - len(by_type_sel.get("MCP", [])))
    need_skill = max(0, MIN_SKILL_PER_RECOMMEND - len(by_type_sel.get("Skill", [])))
    for t in filtered:
        if t["id"] in sel_ids:
            continue
        typ = (t.get("metadata") or {}).get("type")
        if need_mcp and typ == "MCP":
            selected_full.append(t)
            sel_ids.add(t["id"])
            need_mcp -= 1
        elif need_skill and typ == "Skill":
            selected_full.append(t)
            sel_ids.add(t["id"])
            need_skill -= 1
        if need_mcp == 0 and need_skill == 0:
            break
    time_reasoning_ms = round((time.perf_counter() - t_rerank_start) * 1000)
    if PERF_LOG:
        print(f"  [Perf] Rerank+Summary(LLM) took {time_reasoning_ms / 1000:.2f}s", file=sys.stderr)

    top1_score = None
    if path_a:
        top1_score = path_a[0].get("score")
    if PERF_LOG:
        e2e = time.perf_counter() - t_start
        print(f"  [Perf] E2E total={e2e:.2f}s (检索~{time_retrieval_ms/1000:.2f}s + LLM~{time_reasoning_ms/1000:.2f}s)", file=sys.stderr)

    # 理由/匹配度与 selected_ids 一一对应；selected_full 可能多于 selected_ids（为凑够 5+5 从 filtered 补入）
    # 用 id -> reason/score 映射，避免用 enumerate(selected_full) 错位导致补入项拿到空理由被过滤
    default_reason = "结合用户需求，该工具适合纳入方案。"
    while len(match_scores_list) < len(selected_ids):
        match_scores_list.append(0)
    match_scores_list = match_scores_list[: len(selected_ids)]
    id_to_reason = dict(zip(selected_ids, reasons_list))
    id_to_score = dict(zip(selected_ids, match_scores_list))

    def _reason_ok(s: str) -> bool:
        s = (s or "").strip()
        return bool(s) and s not in ("暂无", "（暂无）")

    seen_names = set()
    retrieved: list[dict] = []
    for t in selected_full:
        reason = (id_to_reason.get(t["id"]) or "").strip() or default_reason
        if not _reason_ok(reason):
            reason = default_reason
        meta = t.get("metadata") or {}
        name = (meta.get("name") or t.get("id") or "").strip()
        if name in seen_names:
            continue
        seen_names.add(name)
        rec = {"id": t["id"], "metadata": meta}
        if t["id"] in id_to_score and id_to_score[t["id"]] is not None:
            rec["score"] = float(id_to_score[t["id"]])
        elif "score" in t and t["score"] is not None:
            rec["score"] = min(100, max(0, float(t["score"]) * 100))
        rec["reason"] = reason
        retrieved.append(rec)

    # 按匹配度过滤明显不相关的工具：优先保留高分，再为每种类型补齐至少 MIN_*_PER_RECOMMEND 条
    MIN_SCORE_KEEP = 40.0  # 低于此分数视为弱相关，除非用于凑够数量
    strong = [r for r in retrieved if float(r.get("score") or 0) >= MIN_SCORE_KEEP]
    weak = [r for r in retrieved if float(r.get("score") or 0) < MIN_SCORE_KEEP]

    def _by_type(items: list[dict]) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in items:
            typ = (r.get("metadata") or {}).get("type") or "N/A"
            out.setdefault(typ, []).append(r)
        return out

    by_type_strong = _by_type(strong)
    need_mcp = max(0, MIN_MCP_PER_RECOMMEND - len(by_type_strong.get("MCP", [])))
    need_skill = max(0, MIN_SKILL_PER_RECOMMEND - len(by_type_strong.get("Skill", [])))

    final_retrieved: list[dict] = []
    # 先放入所有高分结果，按得分从高到低排序
    strong_sorted = sorted(strong, key=lambda r: float(r.get("score") or 0), reverse=True)
    final_retrieved.extend(strong_sorted)

    # 再从低分结果里为 MCP / Skill 分别补齐数量
    if need_mcp or need_skill:
        for r in weak:
            typ = (r.get("metadata") or {}).get("type")
            if need_mcp and typ == "MCP":
                final_retrieved.append(r)
                need_mcp -= 1
            elif need_skill and typ == "Skill":
                final_retrieved.append(r)
                need_skill -= 1
            if need_mcp == 0 and need_skill == 0:
                break

    if PERF_LOG:
        print(
            f"  [Perf] 最终返回推荐数={len(final_retrieved)}（MCP+Skill 合计，过滤低匹配度后）",
            file=sys.stderr,
        )

    return {
        "user_idea": user_idea,
        "hypothetical_doc": hypothetical_doc,
        "retrieved": final_retrieved,
        "reasoning": reasoning,
        "roadmap_text": roadmap_text or "",
        "metrics": {
            "time_hyde_ms": time_hyde_ms,
            "time_retrieval_ms": time_retrieval_ms,
            "time_reasoning_ms": time_reasoning_ms,
            "hyde_length": len(hypothetical_doc),
            "top1_score": top1_score,
        },
    }


def rerank_with_doubao(tools: list[dict], user_idea: str) -> tuple[str, float]:
    """
    将工具列表与用户 Idea 发给豆包，以资深 AI 架构师角色输出：
    哪些工具最合适、如何组合使用。返回 (方案文本, 耗时毫秒)。
    """
    t0 = time.perf_counter()
    try:
        client, model = _doubao_client()
    except RuntimeError as e:
        return (str(e), round((time.perf_counter() - t0) * 1000))
    # 检索结果中确保包含 type、url（来自 metadata）
    tools_text = "\n".join(
        f"- {m.get('name', 'N/A')} [类型: {m.get('type', 'N/A')}] | 描述: {m.get('description', '')[:280]} | 链接: {m.get('url', '')}"
        for t in tools
        for m in [t.get("metadata") or {}]
    )
    prompt = f"""你是一位资深 AI 架构师。用户有一个 Agent 项目想法，我们已从 MCP/Skill 库中检索出以下候选工具。请严格按下面结构输出。

## 一、推荐清单（必须满足数量与格式）

**数量要求**：MCP 至少推荐 5 个，Skill 至少推荐 5 个（若候选列表中该类型不足 5 个则全部推荐）。每个推荐项必须包含以下 4 项：

1. **工具名** [MCP 或 Skill]（点击跳转：完整链接）
2. **描述**：一句话说明该工具做什么、能解决什么问题。
3. **推荐原因**：为何适合本用户项目（1～2 句，结合用户需求说明）。
4. **项目适配度**：x/10 分（满分 10 分），并一句话说明打分理由。

示例格式（每个工具按此 4 行输出）：
- **xxx** [MCP]（https://...）
- 描述：...
- 推荐原因：...
- 项目适配度：8/10，...

请先列出所有推荐的 MCP（至少 5 个），再列出所有推荐的 Skill（至少 5 个），每个工具都带齐：描述、推荐原因、项目适配度(10分)。

## 二、深度实现方案 (Implementation Roadmap)

### 2.1 开发流程
基于上述推荐工具，给出 Step-by-step 的落地步骤（第一步用 X 抓取/处理，第二步用 Y 写入/调用…），每步简明扼要。

### 2.2 全技术栈建议
除上述 MCP/Skill 外，还需要哪些前端、后端、数据库或其它基础设施？简要列出并说明用途。

### 2.3 组合逻辑
这些工具之间如何通过 API 或协议进行数据传递？数据流与调用关系简要说明。

用户需求：
{user_idea}

候选工具（名称 / 类型 / 描述 / 链接）：
{tools_text}

请按「一、推荐清单」和「二、深度实现方案」两大部分直接输出，推荐清单中 MCP 与 Skill 各至少 5 个，且每项都包含描述、推荐原因、项目适配度(10分)。"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
        )
    except Exception as e:
        err = str(e).lower()
        time_reasoning_ms = round((time.perf_counter() - t0) * 1000)
        if "401" in err or "authentication" in err or "api key format" in err:
            return (
                "豆包 API 鉴权失败（401）。请检查 .env 中 DOUBAO_API_KEY 与 DOUBAO_ENDPOINT_ID："
                " 无多余空格/引号/换行，API Key 从火山方舟完整复制。"
                f"\n原始错误: {e}",
                time_reasoning_ms,
            )
        return (f"豆包调用失败: {e}", time_reasoning_ms)
    reasoning = (resp.choices[0].message.content or "").strip()
    time_reasoning_ms = round((time.perf_counter() - t0) * 1000)
    return (reasoning, time_reasoning_ms)


def recommend(user_idea: str, top_k: int = 5) -> dict[str, Any]:
    """
    极致提速流程：双路并行检索 → 预筛(norm>0.4, top12) → 极简 Rerank(ID) → 本地回填 → 方案总结。
    返回：{ user_idea, hypothetical_doc, retrieved, reasoning, metrics }。
    """
    embed_fn, index = load_components()
    print("\n执行双路并行检索与极简重排（HyDE 与 user_idea 检索并行）...")
    result = asyncio.run(_recommend_async(user_idea, max(top_k, 20), embed_fn, index))
    n = len(result["retrieved"])
    n_mcp = sum(1 for t in result["retrieved"] if (t.get("metadata") or {}).get("type") == "MCP")
    n_skill = sum(1 for t in result["retrieved"] if (t.get("metadata") or {}).get("type") == "Skill")
    print(f"  候选进入重排 12 条，最终推荐 {n} 条（MCP {n_mcp}，Skill {n_skill}）。")
    return result


def main():
    if len(sys.argv) > 1:
        idea = " ".join(sys.argv[1:])
    else:
        idea = "我想做一个能自动读取 PDF 论文并总结到 Notion 的 Agent"

    print("=" * 60)
    print("MCP/Skills Smart Recommender - 测试运行")
    print("=" * 60)
    print("用户 Idea:", idea)
    print()

    result = recommend(idea, top_k=5)

    print("\n" + "=" * 60)
    print("检索到的工具（合并去重后）")
    print("=" * 60)
    for i, t in enumerate(result["retrieved"], 1):
        meta = t.get("metadata") or {}
        print(f"  {i}. {meta.get('name', 'N/A')}  [类型: {meta.get('type', 'N/A')}]")
        print(f"     描述: {meta.get('description', '')[:120]}...")
        print(f"     链接: {meta.get('url', '')}")

    print("\n" + "=" * 60)
    print("智能重排：推荐与组合建议（豆包 · 资深 AI 架构师）")
    print("=" * 60)
    print(result["reasoning"])
    print()

    return result


if __name__ == "__main__":
    main()
