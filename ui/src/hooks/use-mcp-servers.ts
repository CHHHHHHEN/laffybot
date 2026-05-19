import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

export function useMcpServers() {
  return useQuery({
    queryKey: ['mcpServers'],
    queryFn: () => api.listMcpServers(),
    staleTime: 10_000,
    refetchInterval: 15_000,
  })
}

export function useMcpServer(id: string | undefined) {
  return useQuery({
    queryKey: ['mcpServer', id],
    queryFn: () => api.getMcpServer(id!),
    enabled: !!id,
    staleTime: 10_000,
  })
}

export function useCreateMcpServer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: api.MCPServerCreateRequest) => api.createMcpServer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
    },
  })
}

export function useUpdateMcpServer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: api.MCPServerUpdateRequest }) =>
      api.updateMcpServer(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
    },
  })
}

export function useDeleteMcpServer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteMcpServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
    },
  })
}

export function useToggleMcpServer() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.toggleMcpServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['mcpServers'] })
    },
  })
}

export function useTestMcpServer() {
  return useMutation({
    mutationFn: (id: string) => api.testMcpServer(id),
  })
}
