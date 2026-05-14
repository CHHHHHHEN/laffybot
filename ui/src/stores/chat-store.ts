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

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: string
  reasoning?: string
  tool_calls?: ToolCall[]
  isStreaming?: boolean
  isError?: boolean
}

let contentBuffer = ''
let reasoningBuffer = ''

interface ChatState {
  messages: Message[]
  connectionStatus: ConnectionStatus
  isStreaming: boolean
  activeRequestId: string | null
  setMessages: (messages: Message[]) => void
  appendMessage: (message: Message) => void
  updateLastMessage: (updates: Partial<Message>) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setIsStreaming: (streaming: boolean) => void
  initStreamBuffer: () => void
  appendContent: (text: string) => void
  appendReasoning: (text: string) => void
  addToolCall: (toolCall: ToolCall) => void
  updateToolCallInMessage: (toolCallId: string, updates: Partial<ToolCall>) => void
  flushStreamBuffer: () => void
  setActiveRequestId: (id: string | null) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  connectionStatus: 'disconnected',
  isStreaming: false,
  activeRequestId: null,

  setMessages: (messages) => set({ messages }),

  appendMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateLastMessage: (updates) =>
    set((state) => {
      const messages = [...state.messages]
      if (messages.length === 0) return state
      messages[messages.length - 1] = { ...messages[messages.length - 1], ...updates }
      return { messages }
    }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setIsStreaming: (streaming) => set({ isStreaming: streaming }),

  initStreamBuffer: () => {
    contentBuffer = ''
    reasoningBuffer = ''
  },

  appendContent: (text) => {
    contentBuffer += text
    get().updateLastMessage({ content: contentBuffer })
  },

  appendReasoning: (text) => {
    reasoningBuffer += text
    get().updateLastMessage({ reasoning: reasoningBuffer })
  },

  addToolCall: (toolCall) =>
    set((state) => {
      const messages = [...state.messages]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      messages[messages.length - 1] = {
        ...last,
        tool_calls: [...(last.tool_calls || []), toolCall],
      }
      return { messages }
    }),

  updateToolCallInMessage: (toolCallId, updates) =>
    set((state) => {
      const messages = [...state.messages]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      messages[messages.length - 1] = {
        ...last,
        tool_calls: (last.tool_calls || []).map((tc) =>
          tc.tool_call_id === toolCallId ? { ...tc, ...updates } : tc
        ),
      }
      return { messages }
    }),

  flushStreamBuffer: () => {
    set((state) => {
      const messages = [...state.messages]
      if (messages.length === 0) return state
      const last = messages[messages.length - 1]
      if (last.role === 'assistant' && last.isStreaming) {
        messages[messages.length - 1] = { ...last, isStreaming: false }
        return { messages }
      }
      return state
    })
  },

  setActiveRequestId: (id) => set({ activeRequestId: id }),
  clearMessages: () => {
    contentBuffer = ''
    reasoningBuffer = ''
    set({ messages: [] })
  },
}))
