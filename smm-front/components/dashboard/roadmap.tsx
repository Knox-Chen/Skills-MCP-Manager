"use client"

import { CheckCircle2, Circle, Loader2 } from "lucide-react"

export interface RoadmapStep {
  id: string
  title: string
  description: string
  status: "completed" | "in-progress" | "pending"
}

interface RoadmapProps {
  steps: RoadmapStep[]
}

export function Roadmap({ steps }: RoadmapProps) {
  const getStatusIcon = (status: RoadmapStep["status"]) => {
    switch (status) {
      case "completed":
        return <CheckCircle2 className="w-5 h-5 text-accent" />
      case "in-progress":
        return <Loader2 className="w-5 h-5 text-primary animate-spin" />
      case "pending":
        return <Circle className="w-5 h-5 text-muted-foreground" />
    }
  }

  return (
    <aside className="glass-card rounded-xl p-6">
      <h2 className="text-lg font-semibold text-foreground mb-2">
        实施路线图
      </h2>
      <p className="text-sm text-muted-foreground mb-6">
        建议的实施步骤
      </p>

      {steps.length === 0 ? (
        <div className="text-center py-8">
          <Circle className="w-8 h-8 text-muted-foreground mx-auto mb-3 opacity-50" />
          <p className="text-sm text-muted-foreground">
            分析完成后将生成路线图
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {steps.map((step, index) => (
            <div
              key={step.id}
              className="relative animate-in fade-in slide-in-from-left-4"
              style={{ animationDelay: `${index * 150}ms` }}
            >
              <div className="flex gap-4">
                {/* Timeline line */}
                <div className="flex flex-col items-center">
                  {getStatusIcon(step.status)}
                  {index < steps.length - 1 && (
                    <div
                      className={`w-px flex-1 my-2 ${
                        step.status === "completed"
                          ? "bg-accent"
                          : "bg-border"
                      }`}
                    />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 pb-6">
                  <div
                    className={`p-4 rounded-lg transition-colors ${
                      step.status === "in-progress"
                        ? "bg-primary/10 border border-primary/30"
                        : step.status === "completed"
                        ? "bg-accent/10 border border-accent/30"
                        : "bg-secondary/30 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-muted-foreground font-mono">
                        步骤 {index + 1}
                      </span>
                      {step.status === "in-progress" && (
                        <span className="text-xs text-primary font-medium">
                          进行中
                        </span>
                      )}
                    </div>
                    <h3
                      className={`font-medium ${
                        step.status === "pending"
                          ? "text-muted-foreground"
                          : "text-foreground"
                      }`}
                    >
                      {step.title}
                    </h3>
                    <p
                      className={`text-sm text-muted-foreground mt-1 whitespace-pre-wrap ${
                        step.id === "2" && step.description.length > 200
                          ? "max-h-64 overflow-y-auto"
                          : ""
                      }`}
                    >
                      {step.description}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
