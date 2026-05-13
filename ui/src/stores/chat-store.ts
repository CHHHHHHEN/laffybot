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

interface StreamBuffer {
  text: string
  reasoning: string
  toolCalls: ToolCall[]
}

interface ChatState {
  messages: Message[]
  connectionStatus: ConnectionStatus
  isStreaming: boolean
  streamBuffer: StreamBuffer
  activeRequestId: string | null
  setMessages: (messages: Message[]) => void
  appendMessage: (message: Message) => void
  updateLastMessage: (updates: Partial<Message>) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setIsStreaming: (streaming: boolean) => void
  appendToStreamBuffer: (type: 'text' | 'reasoning', text: string) => void
  addToolCallToBuffer: (toolCall: ToolCall) => void
  updateToolCallInBuffer: (toolCallId: string, updates: Partial<ToolCall>) => void
  flushStreamBuffer: () => void
  setActiveRequestId: (id: string | null) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  connectionStatus: 'disconnected',
  isStreaming: false,
  streamBuffer: { text: '', reasoning: '', toolCalls: [] },
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

  appendToStreamBuffer: (type, text) =>
    set((state) => ({
      streamBuffer: {
        ...state.streamBuffer,
        [type === 'text' ? 'text' : 'reasoning']:
          state.streamBuffer[type === 'text' ? 'text' : 'reasoning'] + text,
      },
    })),

  addToolCallToBuffer: (toolCall) =>
    set((state) => ({
      streamBuffer: {
        ...state.streamBuffer,
        toolCalls: [...state.streamBuffer.toolCalls, toolCall],
      },
    })),

  updateToolCallInBuffer: (toolCallId, updates) =>
    set((state) => ({
      streamBuffer: {
        ...state.streamBuffer,
        toolCalls: state.streamBuffer.toolCalls.map((tc) =>
          tc.tool_call_id === toolCallId ? { ...tc, ...updates } : tc
        ),
      },
    })),

  flushStreamBuffer: () => {
    const { streamBuffer } = get()
    if (!streamBuffer.text && streamBuffer.toolCalls.length === 0) return

    const message: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: streamBuffer.text,
      timestamp: new Date().toISOString(),
      reasoning: streamBuffer.reasoning || undefined,
      tool_calls: streamBuffer.toolCalls.length > 0 ? streamBuffer.toolCalls : undefined,
    }

    set((state) => ({
      messages: [...state.messages, message],
      streamBuffer: { text: '', reasoning: '', toolCalls: [] },
    }))
  },

  setActiveRequestId: (id) => set({ activeRequestId: id }),
  clearMessages: () => set({ messages: [], streamBuffer: { text: '', reasoning: '', toolCalls: [] } }),
}))
