import { useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useChatStore, selectActiveSessionMessages } from '@/stores/chat-store'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { MessageList } from '@/components/chat/MessageList'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionStatusBanner } from '@/components/ui/ConnectionStatusBanner'
import { useSessions } from '@/hooks/use-sessions'
import { useSseStream } from '@/hooks/useSseStream'
import { getHistory } from '@/lib/api'

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const messages = useChatStore(selectActiveSessionMessages)
  const { submit, cancel, isStreaming, connectionStatus } = useSseStream(sessionId, {
    onNewSession: (newSessionId) => {
      navigate(`/chat/${newSessionId}`, { replace: true })
    },
  })

  const sessionsQuery = useSessions()
  const allSessions = sessionsQuery.data?.pages.flatMap((p) => p.sessions) ?? []
  const session = sessionId ? allSessions.find((s) => s.session_id === sessionId) ?? null : null

  // Set active session and load history on session switch
  const historyLoadedRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (!sessionId) return

    const abortController = new AbortController()
    const store = useChatStore.getState()
    store.setActiveSessionId(sessionId)

    if (!historyLoadedRef.current.has(sessionId) && !store.hasLoadedHistory(sessionId)) {
      historyLoadedRef.current.add(sessionId)
      const loadHistory = async () => {
        try {
          store.setSessionConnectionStatus(sessionId, 'connecting')
          const history = await getHistory(sessionId, 50, abortController.signal)
          if (abortController.signal.aborted) return
          const messages: Parameters<typeof store.setSessionMessages>[1] = history.messages.map((m, i) => {
            const msg: Parameters<typeof store.setSessionMessages>[1][number] = {
              id: `${i}`,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp,
            }
            // Migrate assistant messages from flat API format to iterations format
            if (m.role === 'assistant' && (m.content || m.reasoning_content || m.tool_calls)) {
              msg.iterations = [
                {
                  iteration: 0,
                  content: m.content || undefined,
                  reasoning: m.reasoning_content || undefined,
                  toolCalls: m.tool_calls as import('@/stores/chat-store').ToolCall[] | undefined,
                },
              ]
            }
            return msg
          })
          store.setSessionMessages(sessionId, messages)
          store.setSessionConnectionStatus(sessionId, 'disconnected')
          store.markHistoryLoaded(sessionId)
        } catch {
          if (abortController.signal.aborted) return
          store.setSessionConnectionStatus(sessionId, 'error')
        }
      }
      loadHistory()
    }

    return () => {
      abortController.abort()
    }
  }, [sessionId])

  if (!sessionId) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-h1 font-bold text-[var(--color-text-primary)] mb-2">
              Laffybot
            </h1>
            <p className="text-[var(--color-text-secondary)]">
              选择或创建一个会话开始对话
            </p>
          </div>
        </div>
        <InputBar
          isStreaming={false}
          disabled={false}
          onSubmit={submit}
          onCancel={cancel}
        />
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <ChatHeader session={session} />
      <ConnectionStatusBanner status={connectionStatus} />
      <MessageList
        messages={messages}
        isStreaming={isStreaming}
      />
      <InputBar
        isStreaming={isStreaming}
        disabled={!session || session.status === 'busy'}
        onSubmit={submit}
        onCancel={cancel}
      />
    </div>
  )
}
