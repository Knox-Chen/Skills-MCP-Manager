#!/usr/bin/env python3
"""
MCP/Skills 架构师 Agent - FastAPI 接口
- POST /api/recommend: 推荐流程，返回 request_id 与结果，后台异步写入 analytics_v1.jsonl
- POST /api/feedback: 用户反馈，异步写入 analytics_v1.jsonl 用于方案采纳率
"""

from __future__ import annotations

import sys
import threading
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from recommend import load_components, recommend
from analytics_v1 import write_recommend_async, write_feedback_async, DEFAULT_LOG_PATH


def _warmup():
    try:
        load_components()
    except Exception:
        pass


app = FastAPI(
    title="MCP/Skills 架构师 API",
    description="输入 Idea 获取 MCP/Skill 推荐与全栈实现方案，支持埋点与反馈",
    version="1.0.0",
)


@app.on_event("startup")
def startup():
    """后台预加载模型与 Pinecone，避免阻塞启动（Railway 健康检查需快速响应）。"""
    threading.Thread(target=_warmup, daemon=True).start()
# 允许前端（Vite/Next 等）跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 请求/响应模型 ----------
class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户 Idea")
    top_k: int = Field(default=12, ge=5, le=30, description="检索候选数量")


class FeedbackRequest(BaseModel):
    request_id: str = Field(..., description="推荐请求返回的 request_id")
    is_useful: bool = Field(..., description="本次推荐是否有用")
    clicked_tool_id: str = Field(default="", description="用户点击/复制的工具 ID")
    action_type: str = Field(default="click", description="行为类型: click | copy")


# ---------- 接口 ----------
@app.post("/api/recommend")
def api_recommend(body: RecommendRequest, background_tasks: BackgroundTasks):
    """
    执行推荐流程，返回 request_id、推荐结果与 metrics。
    埋点数据在后台异步写入 analytics_v1.jsonl，不阻塞响应。
    """
    request_id = str(uuid.uuid4())
    try:
        result = recommend(body.query.strip(), top_k=body.top_k)
    except Exception as e:
        err_msg = str(e).strip() or type(e).__name__
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        raise HTTPException(status_code=500, detail=err_msg[:500])

    metrics = result.get("metrics") or {}
    results_for_log = [
        {"id": r.get("id"), "type": (r.get("metadata") or {}).get("type")}
        for r in (result.get("retrieved") or [])
    ]

    def log_after_response():
        write_recommend_async(
            request_id=request_id,
            query=body.query.strip(),
            results=result.get("retrieved") or [],
            metrics=metrics,
            log_path=DEFAULT_LOG_PATH,
        )

    background_tasks.add_task(log_after_response)

    return {
        "request_id": request_id,
        "user_idea": result.get("user_idea"),
        "hypothetical_doc": result.get("hypothetical_doc"),
        "retrieved": result.get("retrieved"),
        "reasoning": result.get("reasoning"),
        "roadmap_text": result.get("roadmap_text", ""),
        "metrics": metrics,
    }


@app.post("/api/feedback")
def api_feedback(body: FeedbackRequest, background_tasks: BackgroundTasks):
    """
    提交用户反馈，用于计算方案采纳率。
    支持 is_useful、clicked_tool_id、action_type (click/copy)，异步写入 analytics_v1.jsonl。
    """
    if body.action_type not in ("click", "copy"):
        raise HTTPException(status_code=400, detail="action_type 必须为 click 或 copy")

    def log_feedback():
        write_feedback_async(
            request_id=body.request_id,
            is_useful=body.is_useful,
            clicked_tool_id=body.clicked_tool_id or "",
            action_type=body.action_type,
            log_path=DEFAULT_LOG_PATH,
        )

    background_tasks.add_task(log_feedback)
    return {"ok": True, "request_id": body.request_id}


@app.get("/")
def root():
    """根路径，供 Railway 等平台健康检查 GET / 使用。"""
    return {"status": "ok"}
    @app.get("/health")
def health():
    return {"status": "ok"}




if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
