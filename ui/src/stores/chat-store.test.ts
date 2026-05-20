import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore, selectActiveSessionMessages } from './chat-store'

describe('ChatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      activeSessionId: null,
      messagesBySession: {},
      streamingSessions: [],
      connectionStatusBySession: {},
      requestIdBySession: {},
      loadedHistorySessions: [],
    })
  })

  it('starts with no active session', () => {
    expect(useChatStore.getState().activeSessionId).toBeNull()
  })

  it('sets active session id', () => {
    useChatStore.getState().setActiveSessionId('sess-1')
    expect(useChatStore.getState().activeSessionId).toBe('sess-1')
  })

  it('manages streaming state per session', () => {
    const store = useChatStore.getState()
    expect(store.isSessionStreaming('sess-1')).toBe(false)
    store.startStreaming('sess-1')
    expect(store.isSessionStreaming('sess-1')).toBe(true)
    store.stopStreaming('sess-1')
    expect(store.isSessionStreaming('sess-1')).toBe(false)
  })

  it('manages connection status per session', () => {
    const store = useChatStore.getState()
    expect(store.getSessionConnectionStatus('sess-1')).toBe('disconnected')
    store.setSessionConnectionStatus('sess-1', 'connected')
    expect(store.getSessionConnectionStatus('sess-1')).toBe('connected')
  })

  it('appends and retrieves messages', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', {
      id: '1',
      role: 'user',
      content: 'hello',
      timestamp: '2024-01-01T00:00:00Z',
    })
    const messages = store.getSessionMessages('sess-1')
    expect(messages).toHaveLength(1)
    expect(messages[0].content).toBe('hello')
  })

  it('tracks loaded history', () => {
    const store = useChatStore.getState()
    expect(store.hasLoadedHistory('sess-1')).toBe(false)
    store.markHistoryLoaded('sess-1')
    expect(store.hasLoadedHistory('sess-1')).toBe(true)
  })

  it('cleans up all session state', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'user', content: 'x', timestamp: '' })
    store.startStreaming('sess-1')
    store.setSessionConnectionStatus('sess-1', 'connected')
    store.setSessionRequestId('sess-1', 'req-1')
    store.markHistoryLoaded('sess-1')
    store.cleanupSession('sess-1')
    expect(store.getSessionMessages('sess-1')).toEqual([])
    expect(store.isSessionStreaming('sess-1')).toBe(false)
  })

  it('manages currentIteration content', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true, currentIteration: { iteration: 0 } })
    store.appendCurrentContent('sess-1', 'Hello')
    store.appendCurrentContent('sess-1', ' World')
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.currentIteration?.content).toBe('Hello World')
  })

  it('manages currentIteration reasoning', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true, currentIteration: { iteration: 0 } })
    store.appendCurrentReasoning('sess-1', 'thinking...')
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.currentIteration?.reasoning).toBe('thinking...')
  })

  it('archives currentIteration to iterations', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true, currentIteration: { iteration: 0 } })
    store.appendCurrentContent('sess-1', 'Hello')
    store.archiveCurrentIteration('sess-1')
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.iterations).toHaveLength(1)
    expect(lastMessage.iterations![0].content).toBe('Hello')
    expect(lastMessage.currentIteration).toBeUndefined()
  })

  it('adds tool calls to currentIteration', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true, currentIteration: { iteration: 0 } })
    store.addCurrentToolCall('sess-1', { tool_call_id: 'tc1', name: 'test', arguments: {}, status: 'pending' })
    store.updateCurrentToolCall('sess-1', 'tc1', { status: 'completed', result: 'done' })
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.currentIteration?.toolCalls).toHaveLength(1)
    expect(lastMessage.currentIteration?.toolCalls![0].status).toBe('completed')
  })

  it('migrates flat assistant messages to iterations format on append', () => {
    const store = useChatStore.getState()
    const flatMsg = {
      id: '1',
      role: 'assistant' as const,
      content: 'Hello',
      timestamp: '',
      reasoning_content: 'thinking',
      tool_calls: [{ tool_call_id: 'tc1', name: 'test', arguments: {}, status: 'completed' }],
    }
    store.appendSessionMessage('sess-1', flatMsg as never)
    const msg = store.getSessionMessages('sess-1')[0]
    expect(msg.iterations).toHaveLength(1)
    expect(msg.iterations![0].content).toBe('Hello')
    expect(msg.iterations![0].reasoning).toBe('thinking')
    expect(msg.iterations![0].toolCalls).toHaveLength(1)
  })

  it('selects messages for active session', () => {
    const state = useChatStore.getState()
    state.setActiveSessionId('sess-1')
    state.appendSessionMessage('sess-1', { id: '1', role: 'user', content: 'hello', timestamp: '' })
    const messages = selectActiveSessionMessages(useChatStore.getState())
    expect(messages).toHaveLength(1)
  })

  it('skips archiving empty currentIteration', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true, currentIteration: { iteration: 0 } })
    store.archiveCurrentIteration('sess-1')
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.iterations).toBeUndefined()
    expect(lastMessage.currentIteration).toBeUndefined()
  })

  it('initCurrentIteration sets up a new iteration on the last assistant message', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true })
    store.initCurrentIteration('sess-1', 1)
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.currentIteration).toBeDefined()
    expect(lastMessage.currentIteration!.iteration).toBe(1)
  })
})
