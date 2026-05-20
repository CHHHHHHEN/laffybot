import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useChatStore, type ConnectionStatus } from '@/stores/chat-store'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { cancelRequest, ApiError } from '@/lib/api'
import { toast } from 'sonner'
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
      store.archiveCurrentIteration(prev)
      store.updateSessionLastMessage(prev, { isStreaming: false })
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

  const handleSseEvent = useCallback(
    (event: SseEvent, currentSessionId: string) => {
      const store = useChatStore.getState()

      switch (event.type) {
        case 'session_start':
          store.setSessionRequestId(currentSessionId, event.request_id ?? null)
          store.setSessionConnectionStatus(currentSessionId, 'connected')
          updateSessionStatus(currentSessionId, 'busy')
          break
        case 'content':
          store.appendCurrentContent(currentSessionId, event.text ?? '')
          break
        case 'reasoning':
          store.appendCurrentReasoning(currentSessionId, event.text ?? '')
          break
        case 'tool_call':
          store.addCurrentToolCall(currentSessionId, {
            tool_call_id: event.tool_call_id ?? '',
            name: event.name ?? '',
            arguments: (event.arguments as Record<string, unknown>) ?? {},
            status: 'pending',
          })
          break
        case 'tool_result':
          store.updateCurrentToolCall(currentSessionId, event.tool_call_id ?? '', {
            status: event.success ? 'completed' : 'failed',
            result: event.result,
            success: event.success,
            duration_ms: event.duration_ms,
          })
          break
        case 'iteration_boundary':
          store.archiveCurrentIteration(currentSessionId)
          store.initCurrentIteration(currentSessionId, (event.iteration ?? 0) + 1)
          break
        case 'done':
          store.archiveCurrentIteration(currentSessionId)
          store.updateSessionLastMessage(currentSessionId, { isStreaming: false })
          store.setSessionConnectionStatus(currentSessionId, 'disconnected')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'idle')
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          break
        case 'error':
          store.archiveCurrentIteration(currentSessionId)
          store.updateSessionLastMessage(currentSessionId, { isStreaming: false, isError: true })
          store.setSessionConnectionStatus(currentSessionId, 'error')
          store.stopStreaming(currentSessionId)
          store.setSessionRequestId(currentSessionId, null)
          updateSessionStatus(currentSessionId, 'error')
          setError(event.error?.message ?? 'Stream error')
          break
        case 'cancelled':
          store.archiveCurrentIteration(currentSessionId)
          store.updateSessionLastMessage(currentSessionId, { isStreaming: false })
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
          toast.error(message)
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
      store.appendSessionMessage(currentSessionId, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
        currentIteration: { iteration: 0 },
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
        toast.error(message)
        store.archiveCurrentIteration(currentSessionId)
        store.setSessionConnectionStatus(currentSessionId, 'error')
        store.stopStreaming(currentSessionId)
        store.setSessionRequestId(currentSessionId, null)
        store.updateSessionLastMessage(currentSessionId, { isError: true, isStreaming: false, currentIteration: undefined })
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
        store.archiveCurrentIteration(currentSessionId)
        store.updateSessionLastMessage(currentSessionId, { isStreaming: false })
        store.setSessionConnectionStatus(currentSessionId, 'disconnected')
        store.stopStreaming(currentSessionId)
        store.setSessionRequestId(currentSessionId, null)
        updateSessionStatus(currentSessionId, 'idle')
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        return
      }
    }

    const store = useChatStore.getState()
    store.archiveCurrentIteration(currentSessionId)
    store.updateSessionLastMessage(currentSessionId, { isStreaming: false })
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
