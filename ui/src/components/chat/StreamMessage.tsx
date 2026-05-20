import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ReasoningBlock } from './ReasoningBlock'
import { ToolCallCard } from './ToolCallCard'
import { ToolResultBlock } from './ToolResultBlock'
import type { IterationContent } from '@/stores/chat-store'

interface StreamMessageProps {
  iterations?: IterationContent[]
  currentIteration?: IterationContent
  isStreaming?: boolean
}

function IterationView({ iteration, isStreaming: showCursor }: { iteration: IterationContent; isStreaming?: boolean }) {
  const hasReasoning = !!iteration.reasoning
  const hasToolCalls = !!iteration.toolCalls && iteration.toolCalls.length > 0
  const hasContent = !!iteration.content

  if (!hasReasoning && !hasToolCalls && !hasContent) {
    return null
  }

  return (
    <div className="space-y-2">
      {hasReasoning && (
        <ReasoningBlock text={iteration.reasoning!} isStreaming={showCursor} />
      )}
      {hasToolCalls && iteration.toolCalls!.map((tc) =>
        tc.status === 'completed' || tc.status === 'failed' ? (
          <ToolResultBlock key={tc.tool_call_id} toolCall={tc} />
        ) : (
          <ToolCallCard key={tc.tool_call_id} toolCall={tc} />
        )
      )}
      {hasContent && (
        <div className="prose prose-sm max-w-none text-[var(--color-text-primary)]">
          {showCursor ? (
            <div className="whitespace-pre-wrap">{iteration.content}</div>
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
              {iteration.content}
            </ReactMarkdown>
          )}
        </div>
      )}
    </div>
  )
}

export function StreamMessage({ iterations, currentIteration, isStreaming }: StreamMessageProps) {
  const hasHistory = !!iterations && iterations.length > 0
  const hasCurrent = !!currentIteration

  if (!hasHistory && !hasCurrent) {
    return null
  }

  return (
    <div className="space-y-3">
      {hasHistory && iterations!.map((iter, i) => (
        <div key={i}>
          <IterationView iteration={iter} />
        </div>
      ))}
      {hasCurrent && (
        <div>
          <IterationView iteration={currentIteration!} isStreaming={isStreaming} />
          {isStreaming && (
            <span className="inline-block w-1.5 h-4 bg-[var(--color-text-primary)] animate-pulse align-text-bottom" />
          )}
        </div>
      )}
    </div>
  )
}
