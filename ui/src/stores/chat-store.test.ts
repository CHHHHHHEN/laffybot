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
      streamBuffersBySession: {},
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
    store.initSessionStreamBuffer('sess-1')
    store.markHistoryLoaded('sess-1')
    store.cleanupSession('sess-1')
    expect(store.getSessionMessages('sess-1')).toEqual([])
    expect(store.isSessionStreaming('sess-1')).toBe(false)
  })

  it('appends content to stream buffer', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: '', timestamp: '', isStreaming: true })
    store.initSessionStreamBuffer('sess-1')
    store.appendSessionContent('sess-1', 'Hello')
    store.appendSessionContent('sess-1', ' World')
    const lastMessage = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(lastMessage.content).toBe('Hello World')
  })

  it('flushes stream buffer and stops streaming', () => {
    const store = useChatStore.getState()
    store.appendSessionMessage('sess-1', { id: '1', role: 'assistant', content: 'Hello', timestamp: '', isStreaming: true })
    store.flushSessionStreamBuffer('sess-1')
    const last = store.getSessionMessages('sess-1').slice(-1)[0]
    expect(last.isStreaming).toBe(false)
  })

  it('selects messages for active session', () => {
    const state = useChatStore.getState()
    state.setActiveSessionId('sess-1')
    state.appendSessionMessage('sess-1', { id: '1', role: 'user', content: 'hello', timestamp: '' })
    const messages = selectActiveSessionMessages(useChatStore.getState())
    expect(messages).toHaveLength(1)
  })
})
