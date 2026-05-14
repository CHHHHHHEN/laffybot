import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface ReasoningBlockProps {
  text: string
  isStreaming?: boolean
}

export function ReasoningBlock({ text, isStreaming }: ReasoningBlockProps) {
  const [open, setOpen] = useState(true)
  const wasStreamingRef = useRef(isStreaming)

  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming && text) {
      setOpen(false)
    }
    wasStreamingRef.current = !!isStreaming
  }, [isStreaming, text])

  if (!text) return null

  return (
    <div className="border border-[var(--color-border)] rounded-md overflow-hidden mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[var(--color-reasoning)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>推理过程</span>
        {isStreaming && (
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-reasoning)] animate-pulse" />
        )}
      </button>
      {open && (
        <div className="px-3 py-2 text-xs text-[var(--color-text-secondary)] leading-relaxed whitespace-pre-wrap border-t border-[var(--color-border)]">
          {text}
        </div>
      )}
    </div>
  )
}
