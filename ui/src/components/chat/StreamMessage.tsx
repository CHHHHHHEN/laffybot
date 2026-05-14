import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ReasoningBlock } from './ReasoningBlock'
import { ToolCallCard } from './ToolCallCard'
import { ToolResultBlock } from './ToolResultBlock'
import type { ToolCall } from '@/stores/chat-store'

interface StreamMessageProps {
  text: string
  reasoning?: string
  toolCalls?: ToolCall[]
  isStreaming?: boolean
}

export function StreamMessage({ text, reasoning, toolCalls, isStreaming }: StreamMessageProps) {
  return (
    <div className="space-y-2">
      {reasoning && <ReasoningBlock text={reasoning} isStreaming={isStreaming} />}

      {toolCalls?.map((tc) =>
        tc.status === 'completed' || tc.status === 'failed' ? (
          <ToolResultBlock key={tc.tool_call_id} toolCall={tc} />
        ) : (
          <ToolCallCard key={tc.tool_call_id} toolCall={tc} />
        )
      )}

      {text && (
        <div className="prose prose-sm max-w-none text-[var(--color-text-primary)]">
          {isStreaming ? (
            <div className="whitespace-pre-wrap">{text}</div>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => (
                  <pre className="bg-[var(--color-secondary-bg)] border border-[var(--color-border)] rounded-md p-3 overflow-x-auto text-code font-mono">
                    {children}
                  </pre>
                ),
                code: ({ children, ...props }) => {
                  const isInline = !props.className
                  if (isInline) {
                    return (
                      <code className="bg-[var(--color-secondary-bg)] text-[var(--color-text-primary)] rounded-sm px-1 py-0.5 text-code font-mono">
                        {children}
                      </code>
                    )
                  }
                  return (
                    <code className="text-code font-mono" {...props}>
                      {children}
                    </code>
                  )
                },
              }}
            >
              {text}
            </ReactMarkdown>
          )}
        </div>
      )}

      {isStreaming && (
        <span className="inline-block w-1.5 h-4 bg-[var(--color-text-primary)] animate-pulse align-text-bottom" />
      )}
    </div>
  )
}
