import { useQuery } from '@tanstack/react-query'
import * as api from '@/lib/api'

export function useErrorLogs(limit = 20) {
  return useQuery({
    queryKey: ['errorLogs', limit],
    queryFn: () => api.listErrorLogs(limit),
    refetchInterval: 10_000, // auto-refresh every 10s
    staleTime: 5_000,
  })
}
