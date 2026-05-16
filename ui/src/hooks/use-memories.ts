import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

export function useMemories(params?: { limit?: number; offset?: number; search?: string }) {
  return useQuery({
    queryKey: ['memories', params],
    queryFn: () => api.listMemories(params),
    staleTime: 10_000,
  })
}

export function useMemory(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memory', memoryId],
    queryFn: () => api.getMemory(memoryId!),
    enabled: !!memoryId,
    staleTime: 10_000,
  })
}

export function useMemorySource(memoryId: string | undefined) {
  return useQuery({
    queryKey: ['memorySource', memoryId],
    queryFn: () => api.getMemorySource(memoryId!),
    enabled: !!memoryId,
    staleTime: 60_000,
  })
}

export function useDeleteMemory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (memoryId: string) => api.deleteMemory(memoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memories'] })
    },
  })
}
