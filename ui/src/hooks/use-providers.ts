import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '@/lib/api'

export function useProviders() {
  return useQuery({
    queryKey: ['providers'],
    queryFn: () => api.listProviders(),
    staleTime: 30_000,
  })
}

export function useModels(providerId: string | undefined) {
  return useQuery({
    queryKey: ['models', providerId],
    queryFn: () => api.listModels(providerId!),
    enabled: !!providerId,
    staleTime: 30_000,
  })
}

export function useCreateProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: api.ProviderCreateRequest) => api.createProvider(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useUpdateProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: api.ProviderUpdateRequest }) =>
      api.updateProvider(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useDeleteProvider() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteProvider(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
    },
  })
}

export function useAddModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ providerId, name }: { providerId: string; name: string }) =>
      api.addModel(providerId, { name }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['models', variables.providerId] })
    },
  })
}

export function useDeleteModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ providerId, modelId }: { providerId: string; modelId: string }) =>
      api.deleteModel(providerId, modelId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['models', variables.providerId] })
    },
  })
}

export function useDefaultSessionModel() {
  return useQuery({
    queryKey: ['defaultSessionModel'],
    queryFn: () => api.getDefaultSessionModel(),
    staleTime: 30_000,
  })
}

export function useSetDefaultSessionModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { provider_id: string; model_name: string }) =>
      api.setDefaultSessionModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['defaultSessionModel'] })
    },
  })
}

export function useClearDefaultSessionModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.clearDefaultSessionModel(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['defaultSessionModel'] })
    },
  })
}

export function useSummaryModel() {
  return useQuery({
    queryKey: ['summaryModel'],
    queryFn: () => api.getSummaryModel(),
    staleTime: 30_000,
  })
}

export function useSetSummaryModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { provider_id: string; model_name: string }) =>
      api.setSummaryModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['summaryModel'] })
    },
  })
}

export function useClearSummaryModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.clearSummaryModel(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['summaryModel'] })
    },
  })
}

export function useExtractModel() {
  return useQuery({
    queryKey: ['extractModel'],
    queryFn: () => api.getExtractModel(),
    staleTime: 30_000,
  })
}

export function useSetExtractModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: { provider_id: string; model_name: string }) =>
      api.setExtractModel(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['extractModel'] })
    },
  })
}

export function useClearExtractModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.clearExtractModel(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['extractModel'] })
    },
  })
}

