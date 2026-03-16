"use client"

import { useState } from "react"
import { Search, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"

interface HeroSearchProps {
  onSearch: (query: string) => void
  isProcessing: boolean
}

export function HeroSearch({ onSearch, isProcessing }: HeroSearchProps) {
  const [query, setQuery] = useState("")

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query)
    }
  }

  return (
    <section className="relative py-6 px-4">
      <div className="absolute inset-0 gradient-bg pointer-events-none opacity-60" />

      <div className="relative max-w-xl mx-auto text-center">
        <h1 className="text-xl md:text-2xl font-bold text-foreground mb-1.5 tracking-tight text-balance">
          输入 Idea，获取 MCP/Skill 推荐与全栈方案
        </h1>
        <p className="text-xs text-muted-foreground mb-4 max-w-md mx-auto leading-relaxed">
          基于 HyDE 与双路检索，为您推荐最匹配的 MCP 与 Skill，并生成实施路线图。
        </p>

        <form onSubmit={handleSubmit} className="relative">
          <div className="glass-card rounded-lg p-1 glow-primary border border-border/60">
            <div className="relative flex items-center">
              <Search className="absolute left-2.5 w-3.5 h-3.5 text-muted-foreground shrink-0" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="输入项目想法或技术需求…"
                className="w-full bg-transparent text-foreground placeholder:text-muted-foreground py-1.5 pl-8 pr-24 focus:outline-none text-sm min-h-[2rem]"
                disabled={isProcessing}
              />
              <Button
                type="submit"
                disabled={!query.trim() || isProcessing}
                className="absolute right-1 bg-foreground hover:bg-foreground/90 text-background px-3 py-1 h-7 text-xs font-medium gap-1 rounded-md"
              >
{isProcessing ? (
                <span className="animate-pulse">推荐中</span>
              ) : (
                <>
                  推荐
                  <ArrowRight className="w-3 h-3" />
                </>
              )}
              </Button>
            </div>
          </div>
        </form>
      </div>
    </section>
  )
}
