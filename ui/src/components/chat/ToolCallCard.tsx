import { useState } from 'react'
import { ChevronDown, ChevronRight, Wrench } from 'lucide-react'
import type { ToolCall } from '@/stores/chat-store'

interface ToolCallCardProps {
  toolCall: ToolCall
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-[var(--color-border)] rounded-md overflow-hidden mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
        aria-expanded={open}
      >
        <Wrench size={14} className="shrink-0" />
        <span className="font-medium text-[var(--color-text-primary)]">
          {toolCall.name}
        </span>
        {open ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}
      </button>
      {open && (
        <div className="px-3 py-2 text-xs text-[var(--color-text-secondary)] border-t border-[var(--color-border)]">
          <pre className="whitespace-pre-wrap font-mono text-code">
            {JSON.stringify(toolCall.arguments, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
