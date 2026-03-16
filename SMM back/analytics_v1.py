#!/usr/bin/env python3
"""
产品评价与埋点监控 v1：异步写入 analytics_v1.jsonl。
包含 recommend 事件（request_id, query, results, metrics）与 feedback 事件（request_id, is_useful, clicked_tool_id, action_type）。
"""

from __future__ import annotations

import atexit
import json
import queue
import threading
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "analytics_v1.jsonl"
_log_path: Path = DEFAULT_LOG_PATH
_write_queue: queue.Queue[dict[str, Any]] = queue.Queue()
_worker: threading.Thread | None = None


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _writer_loop() -> None:
    while True:
        try:
            event = _write_queue.get()
            if event is None:
                break
            path = event.pop("__path__", _log_path)
            _ensure_dir(path)
            line = json.dumps(event, ensure_ascii=False) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


def _start_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _worker = threading.Thread(target=_writer_loop, daemon=True)
    _worker.start()
    atexit.register(_shutdown)


def _shutdown() -> None:
    _write_queue.put(None)


def set_log_path(path: Path) -> None:
    global _log_path
    _log_path = path


def write_recommend_async(
    request_id: str,
    query: str,
    results: list[dict[str, Any]],
    metrics: dict[str, Any],
    log_path: Path | None = None,
) -> None:
    """
    异步追加一条 recommend 事件到 analytics_v1.jsonl。
    results 为推荐的工具列表，每项含 id 与 type（从 metadata 取）。
    """
    _start_worker()
    payload: dict[str, Any] = {
        "event_type": "recommend",
        "request_id": request_id,
        "query": query,
        "results": [
            {"id": r.get("id"), "type": (r.get("metadata") or {}).get("type")}
            for r in results
        ],
        "metrics": dict(metrics),
    }
    if log_path is not None:
        payload["__path__"] = log_path
    _write_queue.put(payload)


def write_feedback_async(
    request_id: str,
    is_useful: bool,
    clicked_tool_id: str,
    action_type: str,
    log_path: Path | None = None,
) -> None:
    """异步追加一条 feedback 事件，用于方案采纳率等分析。"""
    _start_worker()
    payload: dict[str, Any] = {
        "event_type": "feedback",
        "request_id": request_id,
        "is_useful": is_useful,
        "clicked_tool_id": clicked_tool_id,
        "action_type": action_type,
    }
    if log_path is not None:
        payload["__path__"] = log_path
    _write_queue.put(payload)
