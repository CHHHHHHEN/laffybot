import { useCallback, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { MessageSquarePlus } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { MessageList } from '@/components/chat/MessageList'
import { InputBar } from '@/components/chat/InputBar'
import { ConnectionStatusBanner } from '@/components/ui/ConnectionStatusBanner'
import { Button } from '@/components/ui/Button'
import { useChatStore } from '@/stores/chat-store'
import { useSessions, useCreateSession, useUpdateSessionStatus } from '@/hooks/use-sessions'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { getHistory, cancelRequest } from '@/lib/api'
import { useToastStore } from '@/stores/toast-store'

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const abortRef = useRef<AbortController | null>(null)

  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const connectionStatus = useChatStore((s) => s.connectionStatus)
  const sessionsQuery = useSessions()
  const allSessions = sessionsQuery.data?.pages.flatMap((p) => p.sessions) ?? []
  const session = sessionId ? allSessions.find((s) => s.session_id === sessionId) ?? null : null

  const createSession = useCreateSession()
  const updateSessionStatus = useUpdateSessionStatus()

  // Load history on session switch
  useEffect(() => {
    if (!sessionId) return
    const loadHistory = async () => {
      try {
        useChatStore.getState().setConnectionStatus('connecting')
        const history = await getHistory(sessionId)
        useChatStore.getState().setMessages(
          history.messages.map((m, i) => ({
            id: `${i}`,
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
          }))
        )
        useChatStore.getState().setConnectionStatus('disconnected')
      } catch {
        useChatStore.getState().setConnectionStatus('error')
      }
    }
    useChatStore.getState().clearMessages()
    loadHistory()
  }, [sessionId])

  const handleSseEvent = useCallback(
    (event: SseEvent) => {
      const chat = useChatStore.getState()
      switch (event.type) {
        case 'session_start':
          chat.setConnectionStatus('connected')
          chat.setActiveRequestId(event.request_id ?? null)
          updateSessionStatus(sessionId!, 'busy')
          break
        case 'content':
          chat.appendContent(event.text ?? '')
          break
        case 'reasoning':
          chat.appendReasoning(event.text ?? '')
          break
        case 'tool_call':
          chat.addToolCall({
            tool_call_id: event.tool_call_id ?? '',
            name: event.name ?? '',
            arguments: (event.arguments as Record<string, unknown>) ?? {},
            status: 'pending',
          })
          break
        case 'tool_result':
          chat.updateToolCallInMessage(event.tool_call_id ?? '', {
            status: event.success ? 'completed' : 'failed',
            result: event.result,
            success: event.success,
            duration_ms: event.duration_ms,
          })
          break
        case 'done':
          chat.flushStreamBuffer()
          chat.setConnectionStatus('disconnected')
          chat.setIsStreaming(false)
          chat.setActiveRequestId(null)
          updateSessionStatus(sessionId!, 'idle')
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          break
        case 'error':
          chat.flushStreamBuffer()
          chat.setConnectionStatus('error')
          chat.setIsStreaming(false)
          chat.setActiveRequestId(null)
          updateSessionStatus(sessionId!, 'error')
          break
        case 'cancelled':
          chat.flushStreamBuffer()
          chat.setConnectionStatus('disconnected')
          chat.setIsStreaming(false)
          chat.setActiveRequestId(null)
          updateSessionStatus(sessionId!, 'idle')
          break
        case 'ping':
          break
      }
    },
    [sessionId, updateSessionStatus, queryClient]
  )

  const handleSubmit = useCallback(
    async (content: string) => {
      if (!sessionId) return

      chatStoreActions.appendMessage({
        id: crypto.randomUUID(),
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      })

      const abort = new AbortController()
      abortRef.current = abort

      chatStoreActions.setIsStreaming(true)
      chatStoreActions.initStreamBuffer()

      chatStoreActions.appendMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      })

      try {
        await connectSseStream(sessionId, content, handleSseEvent, abort.signal)
      } catch {
        if (abort.signal.aborted) return
        useToastStore.getState().addToast('error', '发送消息失败，请重试')
        chatStoreActions.setConnectionStatus('error')
        chatStoreActions.setIsStreaming(false)
        chatStoreActions.setActiveRequestId(null)
        useChatStore.getState().updateLastMessage({ isError: true, isStreaming: false })
      }
    },
    [sessionId, handleSseEvent]
  )

  const handleCancel = useCallback(async () => {
    if (!sessionId || !abortRef.current) return
    abortRef.current.abort()
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

const chatStoreActions = {
  appendMessage: (msg: Parameters<ReturnType<typeof useChatStore.getState>['appendMessage']>[0]) =>
    useChatStore.getState().appendMessage(msg),
  setIsStreaming: (v: boolean) => useChatStore.getState().setIsStreaming(v),
  setConnectionStatus: (s: ReturnType<typeof useChatStore.getState>['connectionStatus']) =>
    useChatStore.getState().setConnectionStatus(s),
  setActiveRequestId: (id: string | null) => useChatStore.getState().setActiveRequestId(id),
  initStreamBuffer: () => useChatStore.getState().initStreamBuffer(),
}
