import type { InfiniteData } from '@tanstack/react-query'
import { useMutation, useQueryClient, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

const PAGE_LIMIT = 20

interface SessionsPage {
  sessions: api.SessionResponse[]
  total: number
  limit: number
  offset: number
}

export function useSessions(archived?: boolean) {
  return useInfiniteQuery({
    queryKey: ['sessions', { archived }],
    queryFn: async ({ pageParam = 0 }) => {
      const res = await api.listSessions({ limit: PAGE_LIMIT, offset: pageParam, archived })
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions', { archived: false }] })
    },
  })
}

export function useArchiveSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.archiveSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useUnarchiveSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.unarchiveSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions', { archived: true }] })
    },
  })
}

export function useSessionById(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => api.getSession(sessionId!),
    enabled: !!sessionId,
    staleTime: 30_000,
  })
}

export function useUpdateSessionModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: api.UpdateSessionModelRequest }) =>
      api.updateSessionModel(sessionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
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
