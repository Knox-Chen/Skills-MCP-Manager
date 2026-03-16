"use client"

import { useState, useCallback } from "react"
import { Header } from "@/components/dashboard/header"
import { HeroSearch } from "@/components/dashboard/hero-search"
import { ThoughtProcess, type ThoughtStep } from "@/components/dashboard/thought-process"
import { ToolCards, type Tool } from "@/components/dashboard/tool-cards"
import { Feedback } from "@/components/dashboard/feedback"

const API_BASE = typeof window !== "undefined" ? "" : ""

type RecommendResponse = {
  request_id?: string
  run_id?: string
  retrieved?: Array<{
    id: string
    metadata?: { name?: string; type?: string; description?: string; url?: string }
    score?: number
    reason?: string
  }>
  roadmap_text?: string
  reasoning?: string
  metrics?: Record<string, unknown>
}

/** 路线图文本：步骤2、步骤n 前换行，去掉 - * # 等 */
function sanitizeRoadmapText(text: string): string {
  if (!text || typeof text !== "string") return ""
  let s = text.trim()
  s = s.replace(/\n*步骤\s*(\d+)\s*[：:]/g, "\n步骤$1：")
  s = s.replace(/\n+/g, "\n").trim()
  s = s.replace(/^[\s\-*#]+/gm, "").replace(/\*\*/g, "").replace(/#+\s*/g, "")
  return s.trim()
}

/** 后端 retrieved 转为 Tool[]，按 id+name 去重 */
function retrievedToTools(retrieved: RecommendResponse["retrieved"]): Tool[] {
  if (!Array.isArray(retrieved)) return []
  const seen = new Set<string>()
  const tools: Tool[] = []
  for (const r of retrieved) {
    const meta = r?.metadata || {}
    const name = (meta.name || r?.id || "").trim().slice(0, 200)
    const key = `${r.id}\t${name}`
    if (seen.has(key)) continue
    seen.add(key)
    tools.push({
      id: r.id,
      name: name || r.id,
      type: (meta.type === "Skill" ? "Skill" : "MCP") as "MCP" | "Skill",
      description: (meta.description || "").slice(0, 500),
      link: (meta.url || "").slice(0, 1000) || "#",
      relevance: typeof r.score === "number" ? Math.round(r.score) : undefined,
      reason: (r.reason || "").trim() || undefined,
    })
  }
  return tools
}

const PROGRESS_LABELS = ["解析用户输入", "HyDE", "检索", "推荐与方案", "分析完成"] as const

function buildThoughtSteps(
  query: string,
  loading: boolean,
  done: boolean,
  error: string | null
): ThoughtStep[] {
  const now = () => new Date()
  const base: ThoughtStep[] = [
    { id: "1", type: "thinking", content: `解析需求: "${query.slice(0, 50)}${query.length > 50 ? "…" : ""}"`, timestamp: now() },
    { id: "2", type: "action", content: "HyDE", timestamp: now() },
    { id: "3", type: "analysis", content: "检索", timestamp: now() },
    { id: "4", type: "analysis", content: "推荐与方案", timestamp: now() },
    { id: "5", type: "result", content: error ? `失败: ${error}` : "分析完成", timestamp: now() },
  ]
  if (error) {
    return base.map((s, i) => (i < 4 ? { ...s, content: PROGRESS_LABELS[i] } : { ...s, content: `失败: ${error}` }))
  }
  if (done) {
    return base.map((s, i) => (i < 4 ? { ...s, content: PROGRESS_LABELS[i] } : { ...s, content: "分析完成" }))
  }
  if (loading) {
    return base.map((s, i) => (i < 4 ? { ...s, content: PROGRESS_LABELS[i] } : { ...s, content: "推荐与方案…", type: "analysis" as const }))
  }
  return base
}

export default function Dashboard() {
  const [isProcessing, setIsProcessing] = useState(false)
  const [thoughtSteps, setThoughtSteps] = useState<ThoughtStep[]>([])
  const [tools, setTools] = useState<Tool[]>([])
  const [roadmapText, setRoadmapText] = useState("")
  const [hasSearched, setHasSearched] = useState(false)
  const [requestId, setRequestId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const currentStepLabel = isProcessing
    ? "推荐与方案…"
    : error
      ? "失败"
      : tools.length > 0 || roadmapText
        ? "分析完成"
        : ""

  const handleSearch = useCallback(async (query: string) => {
    setError(null)
    setTools([])
    setRoadmapText("")
    setHasSearched(true)
    setRequestId(null)
    setIsProcessing(true)
    setThoughtSteps(buildThoughtSteps(query, true, false, null))

    try {
      const res = await fetch(`${API_BASE}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), top_k: 12 }),
      })

      const raw = await res.text()
      let data: RecommendResponse = {}
      try {
        data = JSON.parse(raw) as RecommendResponse
      } catch {
        throw new Error(raw || res.statusText || "请求失败")
      }

      if (!res.ok) {
        const detail = typeof data === "object" && data !== null && "detail" in data ? (data as { detail?: string }).detail : raw
        throw new Error(String(detail || res.statusText))
      }

      const reqId = data.request_id ?? data.run_id ?? null
      if (reqId) setRequestId(reqId)
      setTools(retrievedToTools(data.retrieved))
      setRoadmapText(sanitizeRoadmapText(data.roadmap_text ?? ""))
      setThoughtSteps(buildThoughtSteps(query, false, true, null))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      const friendly =
        msg.includes("Failed to fetch") || msg.includes("NetworkError")
          ? "无法连接推荐服务，请确认后端已启动（如：python -m uvicorn api:app --port 8000）"
          : msg
      setError(friendly)
      setThoughtSteps(buildThoughtSteps(query, false, false, friendly))
    } finally {
      setIsProcessing(false)
    }
  }, [])

  const handleFeedback = useCallback(
    (type: "positive" | "negative", _comment?: string) => {
      if (!requestId) return
      fetch(`${API_BASE}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: requestId,
          is_useful: type === "positive",
          clicked_tool_id: "",
          action_type: "click",
        }),
      }).catch(() => {})
    },
    [requestId]
  )

  return (
    <div className="min-h-screen bg-background">
      <div className="fixed inset-0 grid-pattern scanline pointer-events-none opacity-40" />

      <div className="relative">
        <Header />

        <main className="max-w-4xl mx-auto px-4 pb-20">
          {error && (
            <div className="mt-4 p-4 rounded-xl bg-destructive/10 border border-destructive/30 text-destructive text-sm">
              {error}
            </div>
          )}
          <HeroSearch onSearch={handleSearch} isProcessing={isProcessing} />

          <div className="mt-6 space-y-6">
            <ThoughtProcess
              steps={thoughtSteps}
              isProcessing={isProcessing}
              currentStepLabel={currentStepLabel}
              defaultCollapsed={!isProcessing && (tools.length > 0 || !!roadmapText)}
            />

            {hasSearched && (tools.length > 0 || isProcessing) && (
              <ToolCards tools={tools} />
            )}

            {hasSearched && roadmapText && (
              <section className="glass-card rounded-xl overflow-hidden">
                <h2 className="text-lg font-semibold text-foreground px-5 py-4 border-b border-border/50">
                  全栈实现方案
                </h2>
                <div
                  className="p-5 text-base text-foreground text-left leading-relaxed whitespace-pre-wrap"
                  style={{ lineHeight: 1.8 }}
                >
                  {roadmapText}
                </div>
              </section>
            )}

            {hasSearched && (tools.length > 0 || roadmapText) && <Feedback onFeedback={handleFeedback} />}
          </div>
        </main>
      </div>
    </div>
  )
}
