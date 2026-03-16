"""
评估脚本逻辑测试：load_events、evaluate 对 analytics_v1.jsonl 的解析与统计。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluate_analytics import load_events, evaluate


@pytest.fixture
def temp_jsonl():
    """临时 JSONL 文件路径，调用方写入内容。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


def test_load_events_empty(temp_jsonl):
    """空文件返回空列表。"""
    recs, fbs = load_events(temp_jsonl)
    assert recs == []
    assert fbs == []


def test_load_events_only_recommend(temp_jsonl):
    """仅 recommend 事件。"""
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "recommend", "request_id": "r1", "query": "q1", "results": [], "metrics": {}}, ensure_ascii=False) + "\n")
    recs, fbs = load_events(temp_jsonl)
    assert len(recs) == 1
    assert recs[0]["request_id"] == "r1"
    assert len(fbs) == 0


def test_load_events_only_feedback(temp_jsonl):
    """仅 feedback 事件。"""
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "feedback", "request_id": "r1", "is_useful": True, "clicked_tool_id": "", "action_type": "click"}, ensure_ascii=False) + "\n")
    recs, fbs = load_events(temp_jsonl)
    assert len(recs) == 0
    assert len(fbs) == 1
    assert fbs[0]["request_id"] == "r1" and fbs[0]["is_useful"] is True


def test_evaluate_adoption_rate(temp_jsonl):
    """2 条 recommend，其中 1 条有 feedback 且 is_useful=true，采纳率 50%。"""
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "recommend", "request_id": "r1", "query": "q1", "results": [{"id": "a", "type": "MCP"}], "metrics": {"time_hyde_ms": 100, "time_retrieval_ms": 50, "time_reasoning_ms": 200}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"event_type": "recommend", "request_id": "r2", "query": "q2", "results": [], "metrics": {}}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"event_type": "feedback", "request_id": "r1", "is_useful": True, "clicked_tool_id": "a", "action_type": "click"}, ensure_ascii=False) + "\n")
    stats = evaluate(temp_jsonl)
    assert stats["total_recommends"] == 2
    assert stats["total_feedbacks"] == 1
    assert stats["request_ids_with_feedback"] == 1
    assert stats["useful_feedback_request_ids"] == 1
    assert stats["adoption_rate_pct"] == 50.0
    assert stats["feedback_rate_pct"] == 50.0
    assert stats["avg_time_hyde_ms"] == 100
    assert stats["avg_time_retrieval_ms"] == 50
    assert stats["avg_time_reasoning_ms"] == 200


def test_evaluate_no_recommends(temp_jsonl):
    """0 条推荐时采纳率为 0，不除零。"""
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        f.write(json.dumps({"event_type": "feedback", "request_id": "x", "is_useful": True, "clicked_tool_id": "", "action_type": "click"}, ensure_ascii=False) + "\n")
    stats = evaluate(temp_jsonl)
    assert stats["total_recommends"] == 0
    assert stats["adoption_rate_pct"] == 0.0
    assert stats["feedback_rate_pct"] == 0.0


def test_evaluate_skips_invalid_lines(temp_jsonl):
    """含非法 JSON 或非 recommend/feedback 的行被忽略。"""
    with open(temp_jsonl, "w", encoding="utf-8") as f:
        f.write("not json\n")
        f.write(json.dumps({"event_type": "recommend", "request_id": "r1", "query": "q", "results": [], "metrics": {}}, ensure_ascii=False) + "\n")
        f.write('{"event_type":"other"}\n')
    recs, fbs = load_events(temp_jsonl)
    assert len(recs) == 1
    assert len(fbs) == 0
