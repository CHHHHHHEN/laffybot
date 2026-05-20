import { create } from 'zustand'

export type MessageRole = 'user' | 'assistant' | 'system'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

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

export interface IterationContent {
  iteration: number
  reasoning?: string
  content?: string
  toolCalls?: ToolCall[]
}

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  iterations?: IterationContent[]
  currentIteration?: IterationContent
  isStreaming?: boolean
  isError?: boolean
}

interface ChatState {
  // Active session identifier
  activeSessionId: string | null

  // Session-isolated state
  messagesBySession: Record<string, Message[]>
  streamingSessions: string[]
  connectionStatusBySession: Record<string, ConnectionStatus>
  requestIdBySession: Record<string, string>
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

  // New iteration-based operations
  initCurrentIteration: (sessionId: string, iteration: number) => void
  appendCurrentContent: (sessionId: string, text: string) => void
  appendCurrentReasoning: (sessionId: string, text: string) => void
  addCurrentToolCall: (sessionId: string, toolCall: ToolCall) => void
  updateCurrentToolCall: (sessionId: string, toolCallId: string, updates: Partial<ToolCall>) => void
  archiveCurrentIteration: (sessionId: string) => void

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
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant') return state
      messages[messages.length - 1] = { ...last, ...updates }
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

  // New iteration-based operations
  initCurrentIteration: (sessionId, iteration) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant') return state
      messages[messages.length - 1] = {
        ...last,
        currentIteration: { iteration, reasoning: undefined, content: undefined, toolCalls: undefined },
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  appendCurrentContent: (sessionId, text) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant' || !last.currentIteration) return state
      const current = last.currentIteration
      messages[messages.length - 1] = {
        ...last,
        currentIteration: {
          ...current,
          content: (current.content || '') + text,
        },
        isStreaming: true,
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  appendCurrentReasoning: (sessionId, text) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant' || !last.currentIteration) return state
      const current = last.currentIteration
      messages[messages.length - 1] = {
        ...last,
        currentIteration: {
          ...current,
          reasoning: (current.reasoning || '') + text,
        },
        isStreaming: true,
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  addCurrentToolCall: (sessionId, toolCall) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant' || !last.currentIteration) return state
      const current = last.currentIteration
      messages[messages.length - 1] = {
        ...last,
        currentIteration: {
          ...current,
          toolCalls: [...(current.toolCalls || []), toolCall],
        },
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  updateCurrentToolCall: (sessionId, toolCallId, updates) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant' || !last.currentIteration) return state
      const current = last.currentIteration
      messages[messages.length - 1] = {
        ...last,
        currentIteration: {
          ...current,
          toolCalls: (current.toolCalls || []).map((tc) =>
            tc.tool_call_id === toolCallId ? { ...tc, ...updates } : tc
          ),
        },
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
    }),
  archiveCurrentIteration: (sessionId) =>
    set((state) => {
      const messages = [...(state.messagesBySession[sessionId] ?? [])]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role !== 'assistant' || !last.currentIteration) return state
      const current = last.currentIteration
      // Skip archiving if currentIteration is empty (nothing accumulated)
      if (!current.content && !current.reasoning && (!current.toolCalls || current.toolCalls.length === 0)) {
        messages[messages.length - 1] = { ...last, currentIteration: undefined }
        return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
      }
      messages[messages.length - 1] = {
        ...last,
        iterations: [...(last.iterations || []), current],
        currentIteration: undefined,
      }
      return { messagesBySession: { ...state.messagesBySession, [sessionId]: messages } }
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
      return {
        messagesBySession: restMsgs,
        streamingSessions: state.streamingSessions.filter((id) => id !== sessionId),
        connectionStatusBySession: restConn,
        requestIdBySession: restReq,
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
