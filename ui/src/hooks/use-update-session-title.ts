import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updateSessionTitle } from '@/lib/api'

export function useUpdateSessionTitle(sessionId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (title: string) => updateSessionTitle(sessionId, title),
    onSuccess: () => {
      // Invalidate sessions list to reflect the updated title
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
