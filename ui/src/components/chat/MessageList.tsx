import { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'
import type { Message } from '@/stores/chat-store'
import { ScrollToBottomButton } from './ScrollToBottomButton'

interface MessageListProps {
  messages: Message[]
  isStreaming: boolean
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
}

export function MessageList({ messages, isStreaming, isLoading, error, onRetry }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isAtBottom = useRef(true)

  const checkIfAtBottom = () => {
    const el = containerRef.current
    if (!el) return
    const threshold = 100
    isAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }

  const scrollToBottom = (smooth = true) => {
    bottomRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'instant' })
    isAtBottom.current = true
  }

  useEffect(() => {
    if (isAtBottom.current && messages.length > 0) {
      scrollToBottom(!isStreaming)
    }
  }, [messages, isStreaming])

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-[var(--color-border)] border-t-[var(--color-brand)] rounded-full animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-[var(--color-error)] mb-3">{error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="text-sm text-[var(--color-brand)] hover:underline"
            >
              点击重试
            </button>
          )}
        </div>
      </div>
    )
  }

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-[var(--color-text-placeholder)]">
            发送第一条消息开始对话
          </p>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      onScroll={checkIfAtBottom}
      className="flex-1 overflow-y-auto px-4 py-4"
    >
      <div className="max-w-[800px] mx-auto">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      <ScrollToBottomButton
        visible={!isAtBottom.current}
        onClick={() => scrollToBottom()}
      />
    </div>
  )
}
