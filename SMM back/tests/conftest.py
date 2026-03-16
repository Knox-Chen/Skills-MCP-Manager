"""Pytest fixtures: temp log path and mock recommend result."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# 保证能 import 项目模块
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def temp_log_path():
    """临时目录下的 analytics_v1.jsonl，测试结束后清理。"""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "analytics_v1.jsonl"


@pytest.fixture
def mock_recommend_result():
    """recommend() 的模拟返回值，含 metrics 与 retrieved。"""
    return {
        "user_idea": "test idea",
        "hypothetical_doc": "hypothetical doc text",
        "retrieved": [
            {"id": "id1", "metadata": {"type": "MCP", "name": "Tool A"}},
            {"id": "id2", "metadata": {"type": "Skill", "name": "Tool B"}},
        ],
        "reasoning": "Recommendation reasoning text",
        "metrics": {
            "time_hyde_ms": 100,
            "time_retrieval_ms": 50,
            "time_reasoning_ms": 200,
            "hyde_length": 20,
            "top1_score": 0.85,
        },
    }
