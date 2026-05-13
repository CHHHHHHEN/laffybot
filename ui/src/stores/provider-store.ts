import { create } from 'zustand'
import * as api from '@/lib/api'

export interface Provider {
  id: string
  name: string
  base_url: string
  has_api_key: boolean
  created_at: string
}

export interface Model {
  id: string
  provider_id: string
  name: string
}

export interface ActiveSelection {
  provider_id: string
  model_id: string
  provider_name: string
  model_name: string
}

interface ProviderState {
  providers: Provider[]
  models: Record<string, Model[]>
  activeSelection: ActiveSelection | null
  isLoading: boolean
  fetchProviders: () => Promise<void>
  fetchModels: (providerId: string) => Promise<void>
  createProvider: (data: api.ProviderCreateRequest) => Promise<void>
  updateProvider: (id: string, data: api.ProviderUpdateRequest) => Promise<void>
  deleteProvider: (id: string) => Promise<boolean>
  addModel: (providerId: string, name: string) => Promise<void>
  deleteModel: (providerId: string, modelId: string) => Promise<void>
  fetchActiveSelection: () => Promise<void>
  setActiveSelection: (providerId: string, modelId: string) => Promise<void>
}

export const useProviderStore = create<ProviderState>((set) => ({
  providers: [],
  models: {},
  activeSelection: null,
  isLoading: false,

  fetchProviders: async () => {
    set({ isLoading: true })
    try {
      const providers = await api.listProviders()
      set({ providers, isLoading: false })
    } catch {
      set({ isLoading: false })
    }
  },

  fetchModels: async (providerId: string) => {
    try {
      const models = await api.listModels(providerId)
      set((state) => ({
        models: { ...state.models, [providerId]: models },
      }))
    } catch {
      // silently fail
    }
  },

  createProvider: async (data) => {
    const provider = await api.createProvider(data)
    set((state) => ({
      providers: [...state.providers, provider],
    }))
  },

  updateProvider: async (id, data) => {
    const updated = await api.updateProvider(id, data)
    set((state) => ({
      providers: state.providers.map((p) => (p.id === id ? { ...p, ...updated } : p)),
    }))
  },

  deleteProvider: async (id) => {
    const result = await api.deleteProvider(id)
    set((state) => ({
      providers: state.providers.filter((p) => p.id !== id),
      activeSelection:
        state.activeSelection?.provider_id === id ? null : state.activeSelection,
    }))
    return result.active_cleared ?? false
  },

  addModel: async (providerId, name) => {
    const model = await api.addModel(providerId, { name })
    set((state) => ({
      models: {
        ...state.models,
        [providerId]: [...(state.models[providerId] || []), model],
      },
    }))
  },

  deleteModel: async (providerId, modelId) => {
    await api.deleteModel(providerId, modelId)
    set((state) => ({
      models: {
        ...state.models,
        [providerId]: (state.models[providerId] || []).filter((m) => m.id !== modelId),
      },
      activeSelection:
        state.activeSelection?.model_id === modelId ? null : state.activeSelection,
    }))
  },

  fetchActiveSelection: async () => {
    try {
      const selection = await api.getActiveSelection()
      set({ activeSelection: selection })
    } catch {
      // silently fail
    }
  },

  setActiveSelection: async (providerId, modelId) => {
    const selection = await api.setActiveSelection({ provider_id: providerId, model_id: modelId })
    set({ activeSelection: selection })
  },
}))
