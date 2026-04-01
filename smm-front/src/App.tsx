import { useState } from "react";

const API_BASE = "";

type RetrievedItem = {
  id: string;
  metadata?: { name?: string; type?: string; description?: string; url?: string };
};

type RecommendResponse = {
  request_id: string;
  user_idea: string;
  hypothetical_doc: string;
  retrieved: RetrievedItem[];
  reasoning: string;
  metrics: {
    time_hyde_ms?: number;
    time_retrieval_ms?: number;
    time_reasoning_ms?: number;
    hyde_length?: number;
    top1_score?: number;
  };
};

export default function App() {
  const [idea, setIdea] = useState("");
  const [topK, setTopK] = useState(12);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [feedbackSent, setFeedbackSent] = useState(false);

  async function handleRecommend() {
    if (!idea.trim()) return;
    setError(null);
    setResult(null);
    setFeedbackSent(false);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: idea.trim(), top_k: topK }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || res.statusText || "请求失败");
      }
      const data: RecommendResponse = await res.json();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleFeedback(isUseful: boolean, actionType: "click" | "copy" = "click", clickedToolId = "") {
    if (!result?.request_id) return;
    setFeedbackSent(true);
    try {
      await fetch(`${API_BASE}/api/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: result.request_id,
          is_useful: isUseful,
          clicked_tool_id: clickedToolId,
          action_type: actionType,
        }),
      });
    } catch {
      setFeedbackSent(false);
    }
  }

  return (
    <div className="app">
      <header style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>skill & MCP Manager</h1>
        <div style={{ color: "#a1a1aa", marginTop: "0.5rem", lineHeight: 1.5 }}>
          <div>描述任务，为Agent推荐适配的skill或MCP</div>
          <div>打造专属于您的专业助手</div>
        </div>
      </header>

      <section style={{ marginBottom: "1.5rem" }}>
        <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>任务描述</label>
        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="请描述您的意图或希望处理的任务"
          rows={4}
          style={{
            width: "100%",
            padding: "0.75rem",
            borderRadius: "8px",
            border: "1px solid #3f3f46",
            background: "#18181b",
            color: "#e4e4e7",
            fontSize: "1rem",
            resize: "vertical",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.75rem" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span>检索数量 top_k</span>
            <input
              type="number"
              min={5}
              max={30}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value) || 12)}
              style={{
                width: "4rem",
                padding: "0.35rem 0.5rem",
                borderRadius: "6px",
                border: "1px solid #3f3f46",
                background: "#18181b",
                color: "#e4e4e7",
              }}
            />
          </label>
          <button
            onClick={handleRecommend}
            disabled={loading || !idea.trim()}
            style={{
              padding: "0.6rem 1.25rem",
              borderRadius: "8px",
              border: "none",
              background: loading ? "#52525b" : "#3b82f6",
              color: "#fff",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "推荐中…" : "获取推荐"}
          </button>
        </div>
      </section>

      {error && (
        <div
          style={{
            padding: "1rem",
            borderRadius: "8px",
            background: "rgba(239,68,68,0.15)",
            color: "#f87171",
            marginBottom: "1rem",
          }}
        >
          {error}
        </div>
      )}

      {result && (
        <>
          <section
            style={{
              padding: "1.25rem",
              borderRadius: "12px",
              background: "#18181b",
              border: "1px solid #27272a",
              marginBottom: "1rem",
            }}
          >
            <div style={{ fontSize: "0.85rem", color: "#71717a", marginBottom: "0.75rem" }}>
              request_id: <code style={{ background: "#27272a", padding: "0.2rem 0.4rem", borderRadius: "4px" }}>{result.request_id}</code>
              {result.metrics && (
                <span style={{ marginLeft: "1rem" }}>
                  HyDE {result.metrics.time_hyde_ms}ms · 检索 {result.metrics.time_retrieval_ms}ms · 方案 {result.metrics.time_reasoning_ms}ms
                </span>
              )}
            </div>

            <details style={{ marginBottom: "1rem" }}>
              <summary style={{ cursor: "pointer", color: "#a1a1aa" }}>HyDE 理想文档（摘要）</summary>
              <pre
                style={{
                  marginTop: "0.5rem",
                  padding: "0.75rem",
                  background: "#27272a",
                  borderRadius: "8px",
                  fontSize: "0.9rem",
                  whiteSpace: "pre-wrap",
                  overflow: "auto",
                }}
              >
                {result.hypothetical_doc.slice(0, 500)}
              </pre>
            </details>

            <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>检索到的候选工具</h3>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 1rem 0" }}>
              {(result.retrieved || []).slice(0, 20).map((r, i) => (
                <li
                  key={r.id}
                  style={{
                    padding: "0.6rem 0",
                    borderBottom: "1px solid #27272a",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.25rem",
                  }}
                >
                  <span style={{ fontWeight: 600 }}>
                    {i + 1}. {r.metadata?.name ?? r.id} [{r.metadata?.type ?? "N/A"}]
                  </span>
                  {r.metadata?.description && (
                    <span style={{ fontSize: "0.9rem", color: "#a1a1aa" }}>{r.metadata.description.slice(0, 120)}…</span>
                  )}
                  {r.metadata?.url && (
                    <a
                      href={r.metadata.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#3b82f6", fontSize: "0.9rem" }}
                    >
                      {r.metadata.url}
                    </a>
                  )}
                </li>
              ))}
            </ul>

            <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem" }}>推荐清单与使用建议</h3>
            <div
              style={{
                padding: "1rem",
                background: "#27272a",
                borderRadius: "8px",
                whiteSpace: "pre-wrap",
                fontSize: "0.95rem",
                lineHeight: 1.6,
              }}
            >
              {result.reasoning}
            </div>
          </section>

          <section
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: "#18181b",
              border: "1px solid #27272a",
            }}
          >
            <h3 style={{ fontSize: "0.95rem", marginBottom: "0.5rem" }}>反馈（用于方案采纳率）</h3>
            {feedbackSent ? (
              <p style={{ color: "#22c55e", margin: 0 }}>感谢反馈，已记录。</p>
            ) : (
              <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
                <button
                  onClick={() => handleFeedback(true)}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: "6px",
                    border: "none",
                    background: "#22c55e",
                    color: "#fff",
                    cursor: "pointer",
                  }}
                >
                  有用
                </button>
                <button
                  onClick={() => handleFeedback(false)}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: "6px",
                    border: "1px solid #3f3f46",
                    background: "transparent",
                    color: "#a1a1aa",
                    cursor: "pointer",
                  }}
                >
                  没用
                </button>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
