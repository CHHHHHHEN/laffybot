import { useCallback, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { MessageList } from '@/components/chat/MessageList'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionStatusBanner } from '@/components/ui/ConnectionStatusBanner'
import {
  useChatStore,
  selectActiveSessionMessages,
  selectActiveSessionIsStreaming,
  selectActiveSessionConnectionStatus,
} from '@/stores/chat-store'
import { useSessions, useCreateSession, useUpdateSessionStatus } from '@/hooks/use-sessions'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { getHistory, cancelRequest, ApiError } from '@/lib/api'
import { useToastStore } from '@/stores/toast-store'
import {
  getOrCreateAbortController,
  abortSession,
} from '@/lib/abort-manager'

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const boundaryToolCallCounts = useRef<Record<string, number>>({})

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

  const flushPendingSegments = useCallback(
    (currentSessionId: string, iteration: number) => {
      const store = useChatStore.getState()
      const buffer = store.streamBuffersBySession[currentSessionId]
      if (!buffer) return
      if (buffer.reasoning) {
        store.appendSessionSegment(currentSessionId, {
          type: 'reasoning',
          data: buffer.reasoning,
          iteration,
        })
      }
      if (buffer.content) {
        store.appendSessionSegment(currentSessionId, {
          type: 'content',
          data: buffer.content,
          iteration,
        })
      }
      const lastMessage = store.getSessionMessages(currentSessionId).slice(-1)[0]
      const toolCallsSinceBoundary = (lastMessage?.tool_calls ?? []).slice(
        boundaryToolCallCounts.current[currentSessionId] ?? 0
      )
      if (toolCallsSinceBoundary.length > 0) {
        store.appendSessionSegment(currentSessionId, {
          type: 'tool_calls',
          data: toolCallsSinceBoundary,
          iteration,
        })
      }
      boundaryToolCallCounts.current[currentSessionId] = lastMessage?.tool_calls?.length ?? 0
    },
    []
  )

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
        case 'iteration_boundary':
          flushPendingSegments(currentSessionId, event.iteration ?? 0)
          store.initSessionStreamBuffer(currentSessionId)
          break
        case 'done':
          flushPendingSegments(currentSessionId, -1)
          store.flushSessionStreamBuffer(currentSessionId)
          store.setSessionConnectionStatus(currentSessionId, 'disconnected')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'idle')
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          break
        case 'error':
          flushPendingSegments(currentSessionId, -1)
          store.flushSessionStreamBuffer(currentSessionId)
          store.setSessionConnectionStatus(currentSessionId, 'error')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'error')
          break
        case 'cancelled':
          flushPendingSegments(currentSessionId, -1)
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
    [updateSessionStatus, queryClient, flushPendingSegments]
  )

  const submittingRef = useRef(false)

  const handleSubmit = useCallback(
    async (content: string) => {
      if (submittingRef.current) return

      let currentSessionId = sessionId

      if (!currentSessionId) {
        submittingRef.current = true
        try {
          const session = await createSession.mutateAsync({})
          if (!session) {
            submittingRef.current = false
            return
          }
          currentSessionId = session.session_id

          const store = useChatStore.getState()
          store.setActiveSessionId(currentSessionId)
          store.markHistoryLoaded(currentSessionId)

          navigate(`/chat/${currentSessionId}`, { replace: true })
        } catch (err) {
          submittingRef.current = false
          useToastStore.getState().addToast('error', err instanceof Error ? err.message : '创建会话失败')
          return
        }
      }

      submittingRef.current = false

      const store = useChatStore.getState()

      // Append user message
      store.appendSessionMessage(currentSessionId, {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      })

      // Get or create AbortController for this session
      const abortController = getOrCreateAbortController(currentSessionId)

      // Start streaming
      store.startStreaming(currentSessionId)
      store.initSessionStreamBuffer(currentSessionId)

      // Append assistant message placeholder
      store.appendSessionMessage(currentSessionId, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      })

      try {
        await connectSseStream(
          currentSessionId,
          content,
          (event) => handleSseEvent(event, currentSessionId),
          abortController.signal
        )
      } catch {
        if (abortController.signal.aborted) return
        useToastStore.getState().addToast('error', '发送消息失败，请重试')
        store.setSessionConnectionStatus(currentSessionId, 'error')
        store.stopStreaming(currentSessionId)
        store.setSessionRequestId(currentSessionId, null)
        store.updateSessionLastMessage(currentSessionId, { isError: true, isStreaming: false })
      }
    },
    [sessionId, handleSseEvent, createSession, navigate]
  )

  const handleCancel = useCallback(async () => {
    if (!sessionId) return

    // Abort the SSE connection for this session
    abortSession(sessionId)

    try {
      await cancelRequest(sessionId)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'SESSION_NOT_BUSY') {
        // Session already reset on backend — sync frontend state
        const store = useChatStore.getState()
        store.flushSessionStreamBuffer(sessionId)
        store.setSessionConnectionStatus(sessionId, 'disconnected')
        store.stopStreaming(sessionId)
        store.setSessionRequestId(sessionId, null)
        updateSessionStatus(sessionId, 'idle')
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        return
      }
      // best effort for other errors
    }

    // SSE connection already aborted before cancel response — force state sync
    const store = useChatStore.getState()
    store.flushSessionStreamBuffer(sessionId)
    store.setSessionConnectionStatus(sessionId, 'disconnected')
    store.stopStreaming(sessionId)
    store.setSessionRequestId(sessionId, null)
    updateSessionStatus(sessionId, 'idle')
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
  }, [sessionId, updateSessionStatus, queryClient])

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
          onSubmit={handleSubmit}
          onCancel={handleCancel}
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
        onSubmit={handleSubmit}
        onCancel={handleCancel}
      />
    </div>
  )
}
