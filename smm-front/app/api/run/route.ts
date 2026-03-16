import { NextRequest, NextResponse } from "next/server"

// 后端地址：默认 8000（uvicorn api:app --port 8000）
const BACKEND_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.API_URL ||
  "http://127.0.0.1:8000"
const RECOMMEND_URL = `${BACKEND_BASE.replace(/\/$/, "")}/api/recommend`
const API_KEY = process.env.API_KEY || process.env.COZE_API_KEY || process.env.NEXT_PUBLIC_API_KEY

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const query =
      typeof body?.query === "string"
        ? body.query
        : Array.isArray(body?.messages) && body.messages[0]?.content
          ? String(body.messages[0].content)
          : ""
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (API_KEY) headers["Authorization"] = `Bearer ${API_KEY}`

    const res = await fetch(RECOMMEND_URL, {
      method: "POST",
      headers,
      body: JSON.stringify({ query: query.trim() || "MCP/Skill 推荐", top_k: body?.top_k ?? 12 }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      return NextResponse.json(
        { detail: data.detail || res.statusText || "请求失败" },
        { status: res.status }
      )
    }
    // 适配页面期望：run_id、messages（用于展示分析结果）
    const reasoning = data.reasoning ?? ""
    return NextResponse.json({
      run_id: data.request_id,
      request_id: data.request_id,
      messages: [{ role: "assistant", content: reasoning }],
      retrieved: data.retrieved,
      roadmap_text: data.roadmap_text,
      metrics: data.metrics,
    })
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return NextResponse.json(
      { detail: message || "无法连接分析服务，请确认后端已启动（如：python -m uvicorn api:app --port 8000）" },
      { status: 502 }
    )
  }
}
