import { useState } from 'react'
import { ChevronDown, ChevronRight, CheckCircle, XCircle } from 'lucide-react'
import type { ToolCall } from '@/stores/chat-store'

interface ToolResultBlockProps {
  toolCall: ToolCall
}

export function ToolResultBlock({ toolCall }: ToolResultBlockProps) {
  const [open, setOpen] = useState(false)

  const isSuccess = toolCall.success
  const duration = toolCall.duration_ms

  return (
    <div className="border border-[var(--color-border)] rounded-md overflow-hidden mb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
        aria-expanded={open}
      >
        {isSuccess ? (
          <CheckCircle size={14} className="shrink-0 text-[var(--color-success)]" />
        ) : (
          <XCircle size={14} className="shrink-0 text-[var(--color-error)]" />
        )}
        <span className={isSuccess ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'}>
          {toolCall.name}
        </span>
        {isSuccess ? (
          <span className="text-[var(--color-text-placeholder)]">执行成功</span>
        ) : (
          <span className="text-[var(--color-error)]">执行失败</span>
        )}
        {duration != null && (
          <span className="text-[var(--color-text-placeholder)]">({duration}ms)</span>
        )}
        {open ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}
      </button>
      {open && (
        <div className="px-3 py-2 text-xs text-[var(--color-text-secondary)] border-t border-[var(--color-border)]">
          <pre className="whitespace-pre-wrap font-mono text-code">
            {toolCall.result ?? toolCall.error_message ?? '无结果'}
          </pre>
        </div>
      )}
    </div>
  )
}
