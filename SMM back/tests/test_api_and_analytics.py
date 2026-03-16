"""
API 与埋点模块测试：FastAPI 客户端 + mock recommend，校验 recommend/feedback 写入 analytics_v1.jsonl。
"""
from __future__ import annotations

import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# 在 import api 前注入路径
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api import app


def _wait_for_log_write(log_path: Path, timeout: float = 2.0, min_lines: int = 1) -> None:
    """等待埋点异步写入完成（后台线程），最多 timeout 秒。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_path.exists() and sum(1 for _ in open(log_path, encoding="utf-8")) >= min_lines:
            return
        time.sleep(0.05)
    # 超时也继续，由后续 assert 报错


@pytest.fixture
def client_and_temp_log(temp_log_path, mock_recommend_result):
    """提供 TestClient，并 patch recommend 与 DEFAULT_LOG_PATH 到临时文件。"""
    with patch("api.recommend") as mock_recommend:
        with patch("api.DEFAULT_LOG_PATH", temp_log_path):
            mock_recommend.return_value = mock_recommend_result
            with TestClient(app) as c:
                yield c, temp_log_path, mock_recommend_result


def test_health(client_and_temp_log):
    """GET /health 返回 ok。"""
    client, _, _ = client_and_temp_log
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_recommend_returns_request_id_and_metrics(client_and_temp_log):
    """POST /api/recommend 返回 request_id、recommend 结果与 metrics。"""
    client, temp_log_path, mock_result = client_and_temp_log
    r = client.post("/api/recommend", json={"query": "test idea", "top_k": 12})
    assert r.status_code == 200
    data = r.json()
    assert "request_id" in data
    assert len(data["request_id"]) > 0
    assert data["user_idea"] == mock_result["user_idea"]
    assert data["reasoning"] == mock_result["reasoning"]
    assert data["metrics"] == mock_result["metrics"]
    assert len(data["retrieved"]) == 2


def test_api_recommend_writes_to_analytics(client_and_temp_log):
    """推荐成功后，后台异步写入一条 recommend 事件到 analytics_v1.jsonl。"""
    client, temp_log_path, mock_result = client_and_temp_log
    client.post("/api/recommend", json={"query": "test query", "top_k": 12})
    _wait_for_log_write(temp_log_path, min_lines=1)
    assert temp_log_path.exists()
    lines = [line.strip() for line in open(temp_log_path, encoding="utf-8") if line.strip()]
    assert len(lines) >= 1
    event = json.loads(lines[0])
    assert event.get("event_type") == "recommend"
    assert "request_id" in event
    assert event.get("query") == "test query"
    assert event.get("metrics") == mock_result["metrics"]
    assert len(event.get("results", [])) == 2


def test_api_feedback_validation(client_and_temp_log):
    """POST /api/feedback 的 action_type 只允许 click/copy。"""
    client, _, _ = client_and_temp_log
    r = client.post(
        "/api/feedback",
        json={
            "request_id": "any-uuid",
            "is_useful": True,
            "clicked_tool_id": "",
            "action_type": "invalid",
        },
    )
    assert r.status_code == 400


def test_api_feedback_ok_and_writes(client_and_temp_log):
    """POST /api/feedback 返回 200 并异步写入一条 feedback 事件。"""
    client, temp_log_path, _ = client_and_temp_log
    # 先写一条 recommend（得到 request_id）
    r_rec = client.post("/api/recommend", json={"query": "q", "top_k": 12})
    assert r_rec.status_code == 200
    request_id = r_rec.json()["request_id"]
    _wait_for_log_write(temp_log_path, min_lines=1)
    # 再发反馈
    r_fb = client.post(
        "/api/feedback",
        json={
            "request_id": request_id,
            "is_useful": True,
            "clicked_tool_id": "id1",
            "action_type": "click",
        },
    )
    assert r_fb.status_code == 200
    assert r_fb.json() == {"ok": True, "request_id": request_id}
    _wait_for_log_write(temp_log_path, min_lines=2)
    lines = [line.strip() for line in open(temp_log_path, encoding="utf-8") if line.strip()]
    assert len(lines) >= 2
    feedback_events = [json.loads(ln) for ln in lines if json.loads(ln).get("event_type") == "feedback"]
    assert len(feedback_events) >= 1
    assert feedback_events[0]["request_id"] == request_id
    assert feedback_events[0]["is_useful"] is True
    assert feedback_events[0]["clicked_tool_id"] == "id1"
    assert feedback_events[0]["action_type"] == "click"


def test_api_recommend_empty_query_rejected(client_and_temp_log):
    """query 为空时返回 422。"""
    client, _, _ = client_and_temp_log
    r = client.post("/api/recommend", json={"query": "", "top_k": 12})
    assert r.status_code == 422
