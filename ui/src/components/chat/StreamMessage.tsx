import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ReasoningBlock } from './ReasoningBlock'
import { ToolCallCard } from './ToolCallCard'
import { ToolResultBlock } from './ToolResultBlock'
import type { ToolCall, MessageSegment } from '@/stores/chat-store'

interface StreamMessageProps {
  text: string
  reasoning?: string
  toolCalls?: ToolCall[]
  segments?: MessageSegment[]
  isStreaming?: boolean
}

export function StreamMessage({ text, reasoning, toolCalls, segments, isStreaming }: StreamMessageProps) {
  if (segments && segments.length > 0) {
    return (
      <div className="space-y-2">
        {segments.map((seg, i) => {
          if (seg.type === 'reasoning') {
            return <ReasoningBlock key={i} text={seg.data as string} isStreaming={isStreaming && i === segments.length - 1} />
          }
          if (seg.type === 'tool_calls') {
            const calls = seg.data as ToolCall[]
            return calls.map((tc) =>
              tc.status === 'completed' || tc.status === 'failed' ? (
                <ToolResultBlock key={tc.tool_call_id} toolCall={tc} />
              ) : (
                <ToolCallCard key={tc.tool_call_id} toolCall={tc} />
              )
            )
          }
          if (seg.type === 'content') {
            const segText = seg.data as string
            if (!segText) return null
            return (
              <div key={i} className="prose prose-sm max-w-none text-[var(--color-text-primary)]">
                {isStreaming && i === segments.length - 1 ? (
                  <div className="whitespace-pre-wrap">{segText}</div>
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
                    {segText}
                  </ReactMarkdown>
                )}
              </div>
            )
          }
          return null
        })}
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 bg-[var(--color-text-primary)] animate-pulse align-text-bottom" />
        )}
      </div>
    )
  }

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
