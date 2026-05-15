import { useCallback, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { MessageSquarePlus } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { MessageList } from '@/components/chat/MessageList'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionStatusBanner } from '@/components/ui/ConnectionStatusBanner'
import { Button } from '@/components/ui/Button'
import {
  useChatStore,
  selectActiveSessionMessages,
  selectActiveSessionIsStreaming,
  selectActiveSessionConnectionStatus,
} from '@/stores/chat-store'
import { useSessions, useCreateSession, useUpdateSessionStatus } from '@/hooks/use-sessions'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { getHistory, cancelRequest } from '@/lib/api'
import { useToastStore } from '@/stores/toast-store'
import {
  getOrCreateAbortController,
  abortSession,
} from '@/lib/abort-manager'

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Use selectors for active session state
  const messages = useChatStore(selectActiveSessionMessages)
  const isStreaming = useChatStore(selectActiveSessionIsStreaming)
  const connectionStatus = useChatStore(selectActiveSessionConnectionStatus)

  const sessionsQuery = useSessions()
  const allSessions = sessionsQuery.data?.pages.flatMap((p) => p.sessions) ?? []
  const session = sessionId ? allSessions.find((s) => s.session_id === sessionId) ?? null : null

  const createSession = useCreateSession()
  const updateSessionStatus = useUpdateSessionStatus()

  // Set active session and load history on session switch
  useEffect(() => {
    if (!sessionId) return

    const store = useChatStore.getState()

    // Update active session ID
    store.setActiveSessionId(sessionId)

    // Lazy load history if not already loaded
    if (!store.hasLoadedHistory(sessionId)) {
      const loadHistory = async () => {
        try {
          store.setSessionConnectionStatus(sessionId, 'connecting')
          const history = await getHistory(sessionId)
          store.setSessionMessages(
            sessionId,
            history.messages.map((m, i) => ({
              id: `${i}`,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp,
            }))
          )
          store.setSessionConnectionStatus(sessionId, 'disconnected')
          store.markHistoryLoaded(sessionId)
        } catch {
          store.setSessionConnectionStatus(sessionId, 'error')
        }
      }
      loadHistory()
    }
  }, [sessionId])

  const handleSseEvent = useCallback(
    (event: SseEvent, currentSessionId: string) => {
      const store = useChatStore.getState()

      switch (event.type) {
        case 'session_start':
          store.setSessionConnectionStatus(currentSessionId, 'connected')
          store.setSessionRequestId(currentSessionId, event.request_id ?? null)
          updateSessionStatus(currentSessionId, 'busy')
          break
        case 'content':
          store.appendSessionContent(currentSessionId, event.text ?? '')
          break
        case 'reasoning':
          store.appendSessionReasoning(currentSessionId, event.text ?? '')
          break
        case 'tool_call':
          store.addSessionToolCall(currentSessionId, {
            tool_call_id: event.tool_call_id ?? '',
            name: event.name ?? '',
            arguments: (event.arguments as Record<string, unknown>) ?? {},
            status: 'pending',
          })
          break
        case 'tool_result':
          store.updateSessionToolCall(currentSessionId, event.tool_call_id ?? '', {
            status: event.success ? 'completed' : 'failed',
            result: event.result,
            success: event.success,
            duration_ms: event.duration_ms,
          })
          break
        case 'done':
          store.flushSessionStreamBuffer(currentSessionId)
          store.setSessionConnectionStatus(currentSessionId, 'disconnected')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'idle')
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          break
        case 'error':
          store.flushSessionStreamBuffer(currentSessionId)
          store.setSessionConnectionStatus(currentSessionId, 'error')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'error')
          break
        case 'cancelled':
          store.flushSessionStreamBuffer(currentSessionId)
          store.setSessionConnectionStatus(currentSessionId, 'disconnected')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'idle')
          break
        case 'ping':
          break
      }
    },
    [updateSessionStatus, queryClient]
  )

  const handleSubmit = useCallback(
    async (content: string) => {
      if (!sessionId) return

      const store = useChatStore.getState()

      // Append user message
      store.appendSessionMessage(sessionId, {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      })

      // Get or create AbortController for this session
      const abortController = getOrCreateAbortController(sessionId)

      // Start streaming
      store.startStreaming(sessionId)
      store.initSessionStreamBuffer(sessionId)

      // Append assistant message placeholder
      store.appendSessionMessage(sessionId, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      })

      try {
        // Pass sessionId to event handler via closure
        await connectSseStream(
          sessionId,
          content,
          (event) => handleSseEvent(event, sessionId),
          abortController.signal
        )
      } catch {
        if (abortController.signal.aborted) return
        useToastStore.getState().addToast('error', '发送消息失败，请重试')
        store.setSessionConnectionStatus(sessionId, 'error')
        store.stopStreaming(sessionId)
        store.setSessionRequestId(sessionId, null)
        store.updateSessionLastMessage(sessionId, { isError: true, isStreaming: false })
      }
    },
    [sessionId, handleSseEvent]
  )

  const handleCancel = useCallback(async () => {
    if (!sessionId) return

    // Abort the SSE connection for this session
    abortSession(sessionId)

    try {
      await cancelRequest(sessionId)
    } catch {
      // best effort
    }
  }, [sessionId])

  const handleCreateSession = useCallback(async () => {
    try {
      const newSession = await createSession.mutateAsync({})
      if (newSession) {
        navigate(`/chat/${newSession.session_id}`)
      }
    } catch (err) {
      useToastStore.getState().addToast('error', err instanceof Error ? err.message : '创建会话失败')
    }
  }, [createSession, navigate])

  if (!sessionId) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-h1 font-bold text-[var(--color-text-primary)] mb-2">
            Laffybot
          </h1>
          <p className="text-[var(--color-text-secondary)] mb-6">
            选择或创建一个会话开始对话
          </p>
          <Button
            onClick={handleCreateSession}
            aria-label="新建会话"
          >
            <MessageSquarePlus size={18} />
            新建会话
          </Button>
        </div>
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
        sessionId={sessionId}
        providerId={session?.provider_id}
        modelName={session?.model_name}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
      />
    </div>
  )
}
