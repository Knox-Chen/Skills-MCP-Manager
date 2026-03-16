"use client"

import { Terminal } from "lucide-react"

export interface ThoughtStep {
  id: string
  type: "thinking" | "analysis" | "result" | "action"
  content: string
  timestamp: Date
}

interface ThoughtProcessProps {
  steps: ThoughtStep[]
  isProcessing: boolean
  /** 当前步骤一句话（只显示正在进行的） */
  currentStepLabel?: string
  /** 完成后是否默认收起（本组件已无展开内容，保留兼容） */
  defaultCollapsed?: boolean
}

export function ThoughtProcess({
  isProcessing,
  currentStepLabel,
}: ThoughtProcessProps) {
  const displayLabel = currentStepLabel ?? (isProcessing ? "团队各部门激烈磋商中..." : "")

  return (
    <div className="glass-card rounded-xl overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Terminal className="w-4 h-4 text-muted-foreground shrink-0" />
          <span className="text-sm text-muted-foreground font-mono shrink-0">
            系统进展
          </span>
          {displayLabel && (
            <span className="text-sm text-foreground truncate font-mono">
              {displayLabel}
            </span>
          )}
          {isProcessing && (
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
