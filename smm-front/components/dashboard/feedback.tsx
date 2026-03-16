"use client"

import { useState } from "react"
import { ThumbsUp, ThumbsDown, MessageSquare } from "lucide-react"
import { Button } from "@/components/ui/button"

interface FeedbackProps {
  onFeedback?: (type: "positive" | "negative", comment?: string) => void
}

export function Feedback({ onFeedback }: FeedbackProps) {
  const [feedback, setFeedback] = useState<"positive" | "negative" | null>(null)
  const [showComment, setShowComment] = useState(false)
  const [comment, setComment] = useState("")
  const [submitted, setSubmitted] = useState(false)

  const handleFeedback = (type: "positive" | "negative") => {
    setFeedback(type)
    if (type === "negative") {
      setShowComment(true)
    } else {
      onFeedback?.(type)
      setSubmitted(true)
    }
  }

  const submitComment = () => {
    if (feedback) {
      onFeedback?.(feedback, comment)
      setSubmitted(true)
      setShowComment(false)
    }
  }

  if (submitted) {
    return (
      <div className="glass-card rounded-xl p-6 text-center animate-in fade-in zoom-in-95">
        <div className="w-12 h-12 rounded-full bg-accent/20 flex items-center justify-center mx-auto mb-4">
          <ThumbsUp className="w-6 h-6 text-accent" />
        </div>
        <h3 className="font-medium text-foreground mb-2">感谢您的反馈！</h3>
        <p className="text-sm text-muted-foreground">
          您的意见帮助我们不断改进
        </p>
      </div>
    )
  }

  return (
    <div className="glass-card rounded-xl p-6">
      <div className="flex items-center gap-3 mb-4">
        <MessageSquare className="w-5 h-5 text-primary" />
        <h3 className="font-medium text-foreground">推荐结果有帮助吗？</h3>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <Button
          variant={feedback === "positive" ? "default" : "outline"}
          size="sm"
          onClick={() => handleFeedback("positive")}
          className={`gap-2 ${
            feedback === "positive"
              ? "bg-accent text-accent-foreground hover:bg-accent/90"
              : "hover:border-accent hover:text-accent"
          }`}
        >
          <ThumbsUp className="w-4 h-4" />
          有帮助
        </Button>
        <Button
          variant={feedback === "negative" ? "default" : "outline"}
          size="sm"
          onClick={() => handleFeedback("negative")}
          className={`gap-2 ${
            feedback === "negative"
              ? "bg-destructive text-destructive-foreground hover:bg-destructive/90"
              : "hover:border-destructive hover:text-destructive"
          }`}
        >
          <ThumbsDown className="w-4 h-4" />
          需改进
        </Button>
      </div>

      {showComment && (
        <div className="space-y-3 animate-in fade-in slide-in-from-top-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="请告诉我们如何改进..."
            className="w-full h-24 bg-input border border-border rounded-lg p-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowComment(false)
                setFeedback(null)
              }}
            >
              取消
            </Button>
            <Button size="sm" onClick={submitComment}>
              提交反馈
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
