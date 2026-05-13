import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { MessageSquarePlus } from 'lucide-react'
import { ChatHeader } from '@/components/chat/ChatHeader'
import { MessageList } from '@/components/chat/MessageList'
import { InputBar } from '@/components/chat/InputBar'
import { NewSessionDialog } from '@/components/ui/NewSessionDialog'
import { ConnectionStatusBanner } from '@/components/ui/ConnectionStatusBanner'
import { useChatStore } from '@/stores/chat-store'
import { useSessionStore, type Session } from '@/stores/session-store'
import { connectSseStream } from '@/lib/sse'
import type { SseEvent } from '@/lib/sse'
import { getHistory, cancelRequest } from '@/lib/api'
import { useToastStore } from '@/components/ui/Toast'

export function ChatPage() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const messages = useChatStore((s) => s.messages)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const connectionStatus = useChatStore((s) => s.connectionStatus)
  const session = useSessionStore((s) =>
    sessionId ? s.sessions.find((sess: Session) => sess.session_id === sessionId) ?? null : null
  )

  const fetchSessions = useSessionStore((s) => s.fetchSessions)
  const createSession = useSessionStore((s) => s.createSession)
  const setActiveSession = useSessionStore((s) => s.setActiveSession)
  const updateSessionStatus = useSessionStore((s) => s.updateSessionStatus)

  // Load sessions on mount
  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // Set active session
  useEffect(() => {
    setActiveSession(sessionId ?? null)
  }, [sessionId, setActiveSession])

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
          chat.appendToStreamBuffer('text', event.text ?? '')
          break
        case 'reasoning':
          chat.appendToStreamBuffer('reasoning', event.text ?? '')
          break
        case 'tool_call':
          chat.addToolCallToBuffer({
            tool_call_id: event.tool_call_id ?? '',
            name: event.name ?? '',
            arguments: (event.arguments as Record<string, unknown>) ?? {},
            status: 'pending',
          })
          break
        case 'tool_result':
          chat.updateToolCallInBuffer(event.tool_call_id ?? '', {
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
          // Refresh session to get updated message_count
          useSessionStore.getState().refreshSession(sessionId!)
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
          // no-op
          break
      }
    },
    [sessionId, updateSessionStatus]
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

      // Create an empty assistant message for streaming
      chatStoreActions.appendMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date().toISOString(),
        isStreaming: true,
      })

      try {
        await connectSseStream(sessionId, content, handleSseEvent, abort.signal)
      } catch (err) {
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

  const handleCreateSession = useCallback(
    async (systemPrompt: string, maxIterations: number) => {
      setDialogError(null)
      try {
        const session = await createSession({ system_prompt: systemPrompt || undefined, max_iterations: maxIterations })
        if (session) {
          setShowNewDialog(false)
          navigate(`/chat/${session.session_id}`)
        }
      } catch (err) {
        setDialogError(err instanceof Error ? err.message : '创建会话失败')
      }
    },
    [createSession, navigate]
  )

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
          <button
            onClick={() => setShowNewDialog(true)}
            className="inline-flex items-center gap-2 rounded-md bg-[var(--color-brand)] text-white px-4 py-2 text-sm font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150"
            aria-label="新建会话"
          >
            <MessageSquarePlus size={18} />
            新建会话
          </button>
        </div>

        <NewSessionDialog
          isOpen={showNewDialog}
          onSubmit={handleCreateSession}
          onCancel={() => setShowNewDialog(false)}
          error={dialogError}
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

      <NewSessionDialog
        isOpen={showNewDialog}
        onSubmit={handleCreateSession}
        onCancel={() => setShowNewDialog(false)}
        error={dialogError}
      />
    </div>
  )
}

// Keep a reference to chat store actions to avoid stale closures
const chatStoreActions = {
  appendMessage: (msg: Parameters<ReturnType<typeof useChatStore.getState>['appendMessage']>[0]) =>
    useChatStore.getState().appendMessage(msg),
  setIsStreaming: (v: boolean) => useChatStore.getState().setIsStreaming(v),
  setConnectionStatus: (s: ReturnType<typeof useChatStore.getState>['connectionStatus']) =>
    useChatStore.getState().setConnectionStatus(s),
  setActiveRequestId: (id: string | null) => useChatStore.getState().setActiveRequestId(id),
}
