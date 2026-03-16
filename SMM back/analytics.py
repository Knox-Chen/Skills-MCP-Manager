#!/usr/bin/env python3
"""
埋点模块：将每次推荐的耗时、Query、检索结果及用户反馈写入 analytics_logs.jsonl。
用于后续分析「有效方案采纳率」等指标。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# 日志文件路径（与项目根目录同级或可配置）
DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "analytics_logs.jsonl"


def _ensure_log_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: dict[str, Any], log_path: Path | None = None) -> None:
    """
    追加一条 JSONL 记录。
    event 建议包含：ts, event_type, query, duration_sec, retrieved_count, feedback 等。
    """
    path = log_path or DEFAULT_LOG_PATH
    _ensure_log_file(path)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def log_recommend_start(query: str) -> float:
    """记录推荐开始，返回 start time，用于后续计算 duration_sec。"""
    return time.perf_counter()


def log_recommend_end(
    query: str,
    start_time: float,
    result: dict[str, Any],
    log_path: Path | None = None,
) -> None:
    """
    推荐完成后写入一条记录。
    result 为 recommend.recommend() 的返回值，会提取 retrieved 数量等。
    """
    duration_sec = round(time.perf_counter() - start_time, 3)
    retrieved = result.get("retrieved") or []
    n_mcp = sum(1 for t in retrieved if (t.get("metadata") or {}).get("type") == "MCP")
    n_skill = sum(1 for t in retrieved if (t.get("metadata") or {}).get("type") == "Skill")
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_type": "recommend",
        "query": query,
        "duration_sec": duration_sec,
        "retrieved_count": len(retrieved),
        "retrieved_mcp": n_mcp,
        "retrieved_skill": n_skill,
        "hypothetical_doc_preview": (result.get("hypothetical_doc") or "")[:200],
        "feedback": None,
    }
    log_event(event, log_path)


def log_feedback(session_or_query_id: str, feedback: str, log_path: Path | None = None) -> None:
    """用户对某次推荐提交反馈时调用（可与上一条 recommend 关联）。"""
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_type": "feedback",
        "session_or_query_id": session_or_query_id,
        "feedback": feedback,
    }
    log_event(event, log_path)
