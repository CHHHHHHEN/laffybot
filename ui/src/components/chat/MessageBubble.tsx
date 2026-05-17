import { StreamMessage } from './StreamMessage'
import type { Message } from '@/stores/chat-store'

interface MessageBubbleProps {
  message: Message
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-md px-4 py-3 ${
          isUser
            ? 'bg-[var(--color-brand-light)] text-[var(--color-text-primary)]'
            : 'bg-[var(--color-secondary-bg)] text-[var(--color-text-primary)]'
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <StreamMessage
            text={message.content}
            reasoning={message.reasoning}
            toolCalls={message.tool_calls}
            segments={message.segments}
            isStreaming={message.isStreaming}
          />
        )}

        {message.isError && (
          <p className="text-xs text-[var(--color-error)] mt-2">
            发送失败
          </p>
        )}
      </div>
    </div>
  )
}
