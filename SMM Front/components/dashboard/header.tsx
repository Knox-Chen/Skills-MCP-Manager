"use client"

import { BarChart3 } from "lucide-react"

export function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/50 glass">
      <div className="max-w-4xl mx-auto px-4 h-12 flex items-center justify-center">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-foreground/10 flex items-center justify-center">
            <BarChart3 className="w-4 h-4 text-foreground" />
          </div>
          <span className="font-semibold text-foreground text-sm tracking-tight">
            MCP/Skills 架构师
          </span>
        </div>
      </div>
    </header>
  )
}
