"use client"

import { ExternalLink, Wrench, Plug } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

export interface Tool {
  id: string
  name: string
  type: "MCP" | "Skill"
  description: string
  link: string
  relevance?: number
  reason?: string
}

interface ToolCardsProps {
  tools: Tool[]
}

export function ToolCards({ tools }: ToolCardsProps) {
  return (
    <section className="py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-foreground">推荐工具</h2>
          <p className="text-sm text-muted-foreground mt-1">
            基于您的项目需求精选的工具和技能
          </p>
        </div>
        <Badge variant="secondary" className="text-xs">
          {tools.length} 个匹配
        </Badge>
      </div>

      {tools.length === 0 ? (
        <div className="glass-card rounded-xl p-12 text-center">
          <Wrench className="w-10 h-10 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">
            输入项目想法后将显示推荐工具
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {tools.map((tool, index) => (
            <div
              key={tool.id}
              className="glass-card rounded-xl p-5 hover:border-primary/50 transition-all duration-300 group animate-in fade-in slide-in-from-bottom-4"
              style={{ animationDelay: `${index * 100}ms` }}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg ${
                    tool.type === "MCP" 
                      ? "bg-accent/20 text-accent" 
                      : "bg-primary/20 text-primary"
                  }`}>
                    {tool.type === "MCP" ? (
                      <Plug className="w-4 h-4" />
                    ) : (
                      <Wrench className="w-4 h-4" />
                    )}
                  </div>
                  <div>
                    <h3 className="font-medium text-foreground group-hover:text-primary transition-colors">
                      {tool.name}
                    </h3>
                  </div>
                </div>
                <Badge
                  variant={tool.type === "MCP" ? "default" : "secondary"}
                  className={`text-xs ${
                    tool.type === "MCP"
                      ? "bg-accent/20 text-accent border-accent/30"
                      : "bg-primary/20 text-primary border-primary/30"
                  }`}
                >
                  {tool.type}
                </Badge>
              </div>

              <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                {tool.description}
              </p>

              <p className="text-xs text-primary/90 mb-3 line-clamp-3">
                推荐理由：{tool.reason ? `"${tool.reason}"` : "（暂无）"}
              </p>

              {tool.relevance != null && (
                <div className="mb-4">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-muted-foreground">匹配度</span>
                    <span className="text-foreground">{tool.relevance}%</span>
                  </div>
                  <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        tool.type === "MCP" ? "bg-accent" : "bg-primary"
                      }`}
                      style={{ width: `${Math.min(100, tool.relevance)}%` }}
                    />
                  </div>
                </div>
              )}

              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-between text-muted-foreground hover:text-foreground hover:bg-secondary/50"
                asChild
              >
                <a href={tool.link} target="_blank" rel="noopener noreferrer">
                  源链接
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </Button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
