import { create } from 'zustand'

export type MessageRole = 'user' | 'assistant' | 'system'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface MessageSegment {
  type: 'reasoning' | 'content' | 'tool_calls'
  data: string | ToolCall[]
  iteration: number
}

export interface ToolCall {
  tool_call_id: string
  name: string
  arguments: Record<string, unknown>
  status: 'pending' | 'running' | 'completed' | 'failed'
  result?: string
  duration_ms?: number
  success?: boolean
  error_message?: string
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  reasoning?: string
  tool_calls?: ToolCall[]
  segments?: MessageSegment[]
  isStreaming?: boolean
  isError?: boolean
}

interface StreamBuffer {
  content: string
  reasoning: string
}

interface ChatState {
  // Active session identifier
  activeSessionId: string | null

  // Session-isolated state
  messagesBySession: Record<string, Message[]>
  streamingSessions: string[]
  connectionStatusBySession: Record<string, ConnectionStatus>
  requestIdBySession: Record<string, string>
  streamBuffersBySession: Record<string, StreamBuffer>
  loadedHistorySessions: string[]

  // Actions for active session
  setActiveSessionId: (id: string | null) => void

  // Actions for session-isolated state
  getSessionMessages: (sessionId: string) => Message[]
  setSessionMessages: (sessionId: string, messages: Message[]) => void
  appendSessionMessage: (sessionId: string, message: Message) => void
  updateSessionLastMessage: (sessionId: string, updates: Partial<Message>) => void

  isSessionStreaming: (sessionId: string) => boolean
  startStreaming: (sessionId: string) => void
  stopStreaming: (sessionId: string) => void

  getSessionConnectionStatus: (sessionId: string) => ConnectionStatus
  setSessionConnectionStatus: (sessionId: string, status: ConnectionStatus) => void

  getSessionRequestId: (sessionId: string) => string | undefined
  setSessionRequestId: (sessionId: string, requestId: string | null) => void

  initSessionStreamBuffer: (sessionId: string) => void
  appendSessionContent: (sessionId: string, text: string) => void
  appendSessionReasoning: (sessionId: string, text: string) => void
  addSessionToolCall: (sessionId: string, toolCall: ToolCall) => void
  updateSessionToolCall: (sessionId: string, toolCallId: string, updates: Partial<ToolCall>) => void
  appendSessionSegment: (sessionId: string, segment: MessageSegment) => void
  flushSessionStreamBuffer: (sessionId: string) => void

  hasLoadedHistory: (sessionId: string) => boolean
  markHistoryLoaded: (sessionId: string) => void

  cleanupSession: (sessionId: string) => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  activeSessionId: null,
  messagesBySession: {},
  streamingSessions: [],
  connectionStatusBySession: {},
  requestIdBySession: {},
  streamBuffersBySession: {},
  loadedHistorySessions: [],

  setActiveSessionId: (id) => set({ activeSessionId: id }),

  getSessionMessages: (sessionId) => get().messagesBySession[sessionId] ?? [],
  setSessionMessages: (sessionId, messages) =>
    set((state) => ({
      messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
    })),
  appendSessionMessage: (sessionId, message) =>
    set((state) => {
      const existing = state.messagesBySession[sessionId] ?? []
      return {
        messagesBySession: { ...state.messagesBySession, [sessionId]: [...existing, message] },
      }
    }),
  updateSessionLastMessage: (sessionId, updates) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      messages[messages.length - 1] = { ...messages[messages.length - 1], ...updates }
      return {
        messagesBySession: { ...state.messagesBySession, [sessionId]: messages },
      }
    }),

  isSessionStreaming: (sessionId) => get().streamingSessions.includes(sessionId),
  startStreaming: (sessionId) =>
    set((state) => ({
      streamingSessions: state.streamingSessions.includes(sessionId)
        ? state.streamingSessions
        : [...state.streamingSessions, sessionId],
    })),
  stopStreaming: (sessionId) =>
    set((state) => ({
      streamingSessions: state.streamingSessions.filter((id) => id !== sessionId),
    })),

  getSessionConnectionStatus: (sessionId) => get().connectionStatusBySession[sessionId] ?? 'disconnected',
  setSessionConnectionStatus: (sessionId, status) =>
    set((state) => ({
      connectionStatusBySession: { ...state.connectionStatusBySession, [sessionId]: status },
    })),

  getSessionRequestId: (sessionId) => get().requestIdBySession[sessionId],
  setSessionRequestId: (sessionId, requestId) =>
    set((state) => {
      if (requestId === null) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { [sessionId]: _, ...rest } = state.requestIdBySession
        return { requestIdBySession: rest }
      }
      return { requestIdBySession: { ...state.requestIdBySession, [sessionId]: requestId } }
    }),

  initSessionStreamBuffer: (sessionId) =>
    set((state) => ({
      streamBuffersBySession: { ...state.streamBuffersBySession, [sessionId]: { content: '', reasoning: '' } },
    })),
  appendSessionContent: (sessionId, text) => {
    const buffer = get().streamBuffersBySession[sessionId]
    if (!buffer) return
    const newContent = buffer.content + text
    set((state) => ({
      streamBuffersBySession: { ...state.streamBuffersBySession, [sessionId]: { ...buffer, content: newContent } },
    }))
    get().updateSessionLastMessage(sessionId, { content: newContent })
  },
  appendSessionReasoning: (sessionId, text) => {
    const buffer = get().streamBuffersBySession[sessionId]
    if (!buffer) return
    const newReasoning = buffer.reasoning + text
    set((state) => ({
      streamBuffersBySession: { ...state.streamBuffersBySession, [sessionId]: { ...buffer, reasoning: newReasoning } },
    }))
    get().updateSessionLastMessage(sessionId, { reasoning: newReasoning })
  },
  addSessionToolCall: (sessionId, toolCall) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      messages[messages.length - 1] = {
        ...last,
        tool_calls: [...(last.tool_calls || []), toolCall],
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  updateSessionToolCall: (sessionId, toolCallId, updates) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      messages[messages.length - 1] = {
        ...last,
        tool_calls: (last.tool_calls || []).map((tc) =>
          tc.tool_call_id === toolCallId ? { ...tc, ...updates } : tc
        ),
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  appendSessionSegment: (sessionId, segment) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      messages[messages.length - 1] = {
        ...last,
        segments: [...(last.segments || []), segment],
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  flushSessionStreamBuffer: (sessionId) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role === 'assistant' && last.isStreaming) {
        messages[messages.length - 1] = { ...last, isStreaming: false }
        return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
      }
      return state
    }),

  hasLoadedHistory: (sessionId) => get().loadedHistorySessions.includes(sessionId),
  markHistoryLoaded: (sessionId) =>
    set((state) => ({
      loadedHistorySessions: state.loadedHistorySessions.includes(sessionId)
        ? state.loadedHistorySessions
        : [...state.loadedHistorySessions, sessionId],
    })),

  cleanupSession: (sessionId) =>
    set((state) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [sessionId]: _, ...restMsgs } = state.messagesBySession
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [sessionId]: __, ...restConn } = state.connectionStatusBySession
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [sessionId]: ___, ...restReq } = state.requestIdBySession
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [sessionId]: ____, ...restBuf } = state.streamBuffersBySession
      return {
        messagesBySession: restMsgs,
        streamingSessions: state.streamingSessions.filter((id) => id !== sessionId),
        connectionStatusBySession: restConn,
        requestIdBySession: restReq,
        streamBuffersBySession: restBuf,
        loadedHistorySessions: state.loadedHistorySessions.filter((id) => id !== sessionId),
      }
    }),
}))

// Stable empty array for selectors to avoid infinite re-renders
const EMPTY_MESSAGES: Message[] = []

// Selectors for active session
export const selectActiveSessionMessages = (state: ChatState): Message[] => {
  if (!state.activeSessionId) return EMPTY_MESSAGES
  return state.messagesBySession[state.activeSessionId] ?? EMPTY_MESSAGES
}

export const selectActiveSessionIsStreaming = (state: ChatState): boolean => {
  if (!state.activeSessionId) return false
  return state.streamingSessions.includes(state.activeSessionId)
}

export const selectActiveSessionConnectionStatus = (state: ChatState): ConnectionStatus => {
  if (!state.activeSessionId) return 'disconnected'
  return state.connectionStatusBySession[state.activeSessionId] ?? 'disconnected'
}
