import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

export function useSkillsPath() {
  return useQuery({
    queryKey: ['skillsPath'],
    queryFn: () => api.getSkillsPath(),
    staleTime: 30_000,
  })
}

export function useSetSkillsPath() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.setSkillsPath(path),
    onSuccess: (data) => {
      queryClient.setQueryData(['skillsPath'], { path: data.skills_path })
      queryClient.setQueryData(['skills'], data)
    },
  })
}

export function useSkills() {
  return useQuery({
    queryKey: ['skills'],
    queryFn: () => api.listSkills(),
    staleTime: 30_000,
  })
}

export function useSetSkillEnabled() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.setSkillEnabled(name, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['skills'] })
    },
  })
}
