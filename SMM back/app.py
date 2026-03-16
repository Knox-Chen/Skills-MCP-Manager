#!/usr/bin/env python3
"""
MCP/Skills 架构师 Agent - Streamlit 前端
用户输入 Idea → 推荐 [MCP/Skills] 组合 + 全栈实现流程；埋点写入 analytics_v1.jsonl。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# 确保项目根在 path 中
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

# 后端推荐与埋点 v1
from recommend import recommend
from analytics_v1 import write_recommend_async, DEFAULT_LOG_PATH

st.set_page_config(
    page_title="MCP/Skills 架构师",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----- 侧边栏：说明与配置 -----
with st.sidebar:
    st.title("🔧 MCP/Skills 架构师")
    st.markdown("输入你的 Agent **Idea**，获取推荐的 MCP/Skill 组合与全栈实现流程。")
    st.divider()
    top_k = st.slider("检索候选数量 (top_k)", min_value=5, max_value=30, value=12, step=1)
    st.caption("仅影响检索阶段，最终会保证 MCP/Skill 各至少 5 条。")
    st.divider()
    st.caption(f"埋点: `{DEFAULT_LOG_PATH.name}`")

# ----- 主区：输入与结果 -----
st.header("输入你的 Idea")
idea = st.text_area(
    "描述你想做的 Agent 或项目想法（例如：自动读 PDF 论文并总结到 Notion）",
    height=100,
    placeholder="例如：我想做一个能自动读取 PDF 论文并总结到 Notion 的 Agent",
)

if not idea.strip():
    st.info("👆 在上方输入你的想法后点击「获取推荐」。")
    st.stop()

run = st.button("获取推荐", type="primary")

if run:
    request_id = str(uuid.uuid4())
    with st.spinner("正在生成 HyDE、检索并生成方案，请稍候…"):
        try:
            result = recommend(idea.strip(), top_k=top_k)
        except Exception as e:
            st.error(f"推荐失败: {e}")
            st.stop()
    # 异步写入 analytics_v1.jsonl（不阻塞）
    write_recommend_async(
        request_id=request_id,
        query=idea.strip(),
        results=result.get("retrieved") or [],
        metrics=result.get("metrics") or {},
        log_path=DEFAULT_LOG_PATH,
    )

    st.success("推荐完成")
    metrics = result.get("metrics") or {}
    st.caption(
        f"**request_id**: `{request_id}` · "
        f"HyDE {metrics.get('time_hyde_ms')}ms · 检索 {metrics.get('time_retrieval_ms')}ms · 方案 {metrics.get('time_reasoning_ms')}ms"
    )

    # 展示：HyDE 摘要
    with st.expander("HyDE 理想文档（摘要）", expanded=False):
        st.write(result.get("hypothetical_doc", "")[:500])

    # 展示：检索到的候选
    st.subheader("检索到的候选工具")
    retrieved = result.get("retrieved") or []
    n_mcp = sum(1 for t in retrieved if (t.get("metadata") or {}).get("type") == "MCP")
    n_skill = sum(1 for t in retrieved if (t.get("metadata") or {}).get("type") == "Skill")
    st.caption(f"共 {len(retrieved)} 条（MCP {n_mcp}，Skill {n_skill}）")
    for i, t in enumerate(retrieved[:20], 1):
        meta = t.get("metadata") or {}
        name = meta.get("name", "N/A")
        typ = meta.get("type", "N/A")
        desc = (meta.get("description") or "")[:120]
        url = meta.get("url", "")
        st.markdown(f"**{i}. {name}** [{typ}]")
        st.caption(desc)
        if url:
            st.markdown(f"🔗 [{url}]({url})")
        st.divider()

    # 展示：架构师方案（核心）
    st.subheader("推荐清单与全栈实现方案")
    reasoning = result.get("reasoning") or ""
    st.markdown(reasoning)

    # 用户反馈（可通过 POST /api/feedback 提交，用于方案采纳率）
    st.divider()
    st.subheader("反馈（可选）")
    st.caption("可通过 API 提交反馈以便计算方案采纳率：`POST /api/feedback`，body: request_id, is_useful, clicked_tool_id, action_type(click/copy)。")
    st.code(f'request_id = "{request_id}"', language="text")

if __name__ == "__main__":
    # 本地运行: streamlit run app.py
    pass
