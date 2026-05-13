import { create } from 'zustand'
import * as api from '@/lib/api'

export interface Session {
  session_id: string
  model: string
  status: 'idle' | 'busy' | 'error'
  created_at: string
  message_count?: number
}

interface SessionState {
  sessions: Session[]
  activeSessionId: string | null
  isLoading: boolean
  error: string | null
  total: number
  setSessions: (sessions: Session[]) => void
  setActiveSession: (id: string | null) => void
  removeSession: (id: string) => void
  updateSessionStatus: (id: string, status: Session['status']) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  fetchSessions: (offset?: number) => Promise<void>
  createSession: (data: api.CreateSessionRequest) => Promise<Session | null>
  deleteSession: (id: string) => Promise<void>
  refreshSession: (id: string) => Promise<void>
  loadMore: () => Promise<void>
  hasMore: () => boolean
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  isLoading: false,
  error: null,
  total: 0,

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (id) => set({ activeSessionId: id }),
  removeSession: (id) =>
    set((state) => ({
      sessions: state.sessions.filter((s) => s.session_id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
    })),
  updateSessionStatus: (id, status) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.session_id === id ? { ...s, status } : s
      ),
    })),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),

  fetchSessions: async (offset = 0) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.listSessions({ limit: 20, offset })
      if (offset === 0) {
        set({ sessions: res.sessions, total: res.total, isLoading: false })
      } else {
        set((state) => ({
          sessions: [...state.sessions, ...res.sessions],
          total: res.total,
          isLoading: false,
        }))
      }
    } catch (err) {
      set({
        isLoading: false,
        error: err instanceof api.ApiError ? err.message : '加载会话失败',
      })
    }
  },

  createSession: async (data) => {
    try {
      const session = await api.createSession(data)
      set((state) => ({
        sessions: [
          {
            session_id: session.session_id,
            model: session.model,
            status: session.status,
            created_at: session.created_at,
            message_count: session.message_count,
          },
          ...state.sessions,
        ],
      }))
      return session
    } catch (err) {
      throw err
    }
  },

  deleteSession: async (id) => {
    const prev = get().sessions
    set((state) => ({
      sessions: state.sessions.filter((s) => s.session_id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
    }))
    try {
      await api.deleteSession(id)
    } catch {
      set({ sessions: prev })
      throw new Error('删除会话失败')
    }
  },

  refreshSession: async (id) => {
    try {
      const session = await api.getSession(id)
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.session_id === id
            ? {
                session_id: session.session_id,
                model: session.model,
                status: session.status,
                created_at: session.created_at,
                message_count: session.message_count,
              }
            : s
        ),
      }))
    } catch {
      // silently fail
    }
  },

  loadMore: async () => {
    const { sessions, isLoading, total } = get()
    if (isLoading || sessions.length >= total) return
    await get().fetchSessions(sessions.length)
  },

  hasMore: () => {
    const { sessions, total } = get()
    return sessions.length < total
  },
}))
