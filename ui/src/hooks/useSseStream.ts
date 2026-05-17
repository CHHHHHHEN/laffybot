import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore, type ConnectionStatus } from '@/stores/chat-store'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { cancelRequest, ApiError } from '@/lib/api'
import { useToastStore } from '@/stores/toast-store'
import { getOrCreateAbortController, abortSession } from '@/lib/abort-manager'
import { useCreateSession, useUpdateSessionStatus } from '@/hooks/use-sessions'

export interface UseSseStreamOptions {
  onNewSession?: (newSessionId: string) => void
  onError?: (errorMessage: string) => void
}

export interface UseSseStreamReturn {
  submit: (content: string) => Promise<void>
  cancel: () => Promise<void>
  isStreaming: boolean
  connectionStatus: ConnectionStatus
  error: string | null
}

export function useSseStream(
  sessionId: string | undefined,
  options?: UseSseStreamOptions
): UseSseStreamReturn {
  const queryClient = useQueryClient()
  const createSession = useCreateSession()
  const updateSessionStatus = useUpdateSessionStatus()

  const submittingRef = useRef(false)
  const boundaryToolCallCounts = useRef<Record<string, number>>({})
  const sessionIdRef = useRef(sessionId)

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  const [error, setError] = useState<string | null>(null)

  const isStreaming = useChatStore((s) => {
    if (!sessionIdRef.current) return false
    return s.streamingSessions.includes(sessionIdRef.current)
  })

  const connectionStatus = useChatStore((s) => {
    if (!sessionIdRef.current) return 'disconnected'
    return s.connectionStatusBySession[sessionIdRef.current] ?? 'disconnected'
  })

  // Clean up the previous session's connection when sessionId changes
  const prevSessionIdRef = useRef<string | undefined>(sessionId)
  useEffect(() => {
    const prev = prevSessionIdRef.current
    if (prev && prev !== sessionId) {
      abortSession(prev)
      const store = useChatStore.getState()
      store.flushSessionStreamBuffer(prev)
      store.setSessionConnectionStatus(prev, 'disconnected')
      store.stopStreaming(prev)
      store.setSessionRequestId(prev, null)
    }
    prevSessionIdRef.current = sessionId
  }, [sessionId])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (sessionId) {
        abortSession(sessionId)
      }
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
          setError(event.error?.message ?? 'Stream error')
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

  const submit = useCallback(
    async (content: string) => {
      if (submittingRef.current) return

      let currentSessionId = sessionIdRef.current

      if (!currentSessionId) {
        submittingRef.current = true
        try {
          const session = await createSession.mutateAsync({})
          if (!session) {
            submittingRef.current = false
            return
          }
          currentSessionId = session.session_id
          sessionIdRef.current = currentSessionId

          const store = useChatStore.getState()
          store.setActiveSessionId(currentSessionId)
          store.markHistoryLoaded(currentSessionId)

          options?.onNewSession?.(currentSessionId)
        } catch (err) {
          submittingRef.current = false
          const message = err instanceof Error ? err.message : '创建会话失败'
          useToastStore.getState().addToast('error', message)
          options?.onError?.(message)
          return
        }
      }

      submittingRef.current = false
      setError(null)

      const store = useChatStore.getState()

      store.appendSessionMessage(currentSessionId, {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      })

      const abortController = getOrCreateAbortController(currentSessionId)

      store.startStreaming(currentSessionId)
      store.initSessionStreamBuffer(currentSessionId)

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
        const message = '发送消息失败，请重试'
        useToastStore.getState().addToast('error', message)
        store.setSessionConnectionStatus(currentSessionId, 'error')
        store.stopStreaming(currentSessionId)
        store.setSessionRequestId(currentSessionId, null)
        store.updateSessionLastMessage(currentSessionId, { isError: true, isStreaming: false })
      }
    },
    [createSession, handleSseEvent, options]
  )

  const cancel = useCallback(async () => {
    const currentSessionId = sessionIdRef.current
    if (!currentSessionId) return

    abortSession(currentSessionId)

    try {
      await cancelRequest(currentSessionId)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'SESSION_NOT_BUSY') {
        const store = useChatStore.getState()
        store.flushSessionStreamBuffer(currentSessionId)
        store.setSessionConnectionStatus(currentSessionId, 'disconnected')
        store.stopStreaming(currentSessionId)
        store.setSessionRequestId(currentSessionId, null)
        updateSessionStatus(currentSessionId, 'idle')
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        return
      }
    }

    const store = useChatStore.getState()
    store.flushSessionStreamBuffer(currentSessionId)
    store.setSessionConnectionStatus(currentSessionId, 'disconnected')
    store.stopStreaming(currentSessionId)
    store.setSessionRequestId(currentSessionId, null)
    updateSessionStatus(currentSessionId, 'idle')
    queryClient.invalidateQueries({ queryKey: ['sessions'] })
  }, [updateSessionStatus, queryClient])

  return {
    submit,
    cancel,
    isStreaming,
    connectionStatus,
    error,
  }
}
