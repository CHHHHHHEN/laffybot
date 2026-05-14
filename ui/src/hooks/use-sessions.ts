import type { InfiniteData } from '@tanstack/react-query'
import { useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

const PAGE_LIMIT = 20

interface SessionsPage {
  sessions: api.SessionResponse[]
  total: number
  limit: number
  offset: number
}

export function useSessions() {
  return useInfiniteQuery({
    queryKey: ['sessions'],
    queryFn: async ({ pageParam = 0 }) => {
      const res = await api.listSessions({ limit: PAGE_LIMIT, offset: pageParam })
      return res as SessionsPage
    },
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.limit
      return nextOffset < lastPage.total ? nextOffset : undefined
    },
    initialPageParam: 0,
    staleTime: 30_000,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: api.CreateSessionRequest) => api.createSession(data),
    onSuccess: (newSession) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      return newSession
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useSessionById(sessionId: string | undefined) {
  const query = useSessions()
  const allSessions = query.data?.pages.flatMap((p) => p.sessions) ?? []
  const session = sessionId ? allSessions.find((s) => s.session_id === sessionId) ?? null : null
  return { session, ...query }
}

export function useUpdateSessionStatus() {
  const queryClient = useQueryClient()
  return (id: string, status: string) => {
    queryClient.setQueryData(['sessions'], (old: InfiniteData<SessionsPage> | undefined) => {
      if (!old?.pages) return old
      return {
        ...old,
        pages: old.pages.map((page) => ({
          ...page,
          sessions: page.sessions.map((s) =>
            s.session_id === id ? { ...s, status } : s
          ),
        })),
      }
    })
  }
}
