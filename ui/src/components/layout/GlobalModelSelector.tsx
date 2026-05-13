import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProviderStore } from '@/stores/provider-store'
import { Settings } from 'lucide-react'

export function GlobalModelSelector() {
  const navigate = useNavigate()
  const providers = useProviderStore((s) => s.providers)
  const models = useProviderStore((s) => s.models)
  const activeSelection = useProviderStore((s) => s.activeSelection)
  const fetchModels = useProviderStore((s) => s.fetchModels)
  const setActiveSelection = useProviderStore((s) => s.setActiveSelection)

  const [selectedProviderId, setSelectedProviderId] = useState('')
  const [selectedModelId, setSelectedModelId] = useState('')

  useEffect(() => {
    if (activeSelection) {
      setSelectedProviderId(activeSelection.provider_id)
      setSelectedModelId(activeSelection.model_id)
    }
  }, [activeSelection])

  useEffect(() => {
    if (selectedProviderId && !models[selectedProviderId]) {
      fetchModels(selectedProviderId)
    }
  }, [selectedProviderId, models, fetchModels])

  const currentModels = models[selectedProviderId] || []

  const handleProviderChange = (providerId: string) => {
    setSelectedProviderId(providerId)
    setSelectedModelId('')
    if (!models[providerId]) {
      fetchModels(providerId)
    }
  }

  const handleApply = async () => {
    if (selectedProviderId && selectedModelId) {
      await setActiveSelection(selectedProviderId, selectedModelId)
    }
  }

  if (providers.length === 0) {
    return (
      <div className="px-3 py-2">
        <button
          onClick={() => navigate('/settings/provider')}
          className="flex items-center gap-2 w-full rounded-md px-3 py-2 text-xs text-[var(--color-text-placeholder)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-secondary)] transition-colors duration-150"
        >
          <Settings size={14} />
          前往设置配置提供商
        </button>
      </div>
    )
  }

  return (
    <div className="px-3 py-2 border-b border-[var(--color-border)]">
      <div className="text-xs text-[var(--color-text-placeholder)] mb-2 font-medium">当前模型</div>
      <div className="flex gap-2">
        <select
          value={selectedProviderId}
          onChange={(e) => handleProviderChange(e.target.value)}
          className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-2 py-1.5 text-xs text-[var(--color-text-primary)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150 min-w-0"
        >
          <option value="" disabled>提供商</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select
          value={selectedModelId}
          onChange={(e) => setSelectedModelId(e.target.value)}
          disabled={!selectedProviderId}
          className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-2 py-1.5 text-xs text-[var(--color-text-primary)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150 min-w-0 disabled:opacity-50"
        >
          <option value="" disabled>模型</option>
          {currentModels.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </select>
        <button
          onClick={handleApply}
          disabled={!selectedProviderId || !selectedModelId}
          className="shrink-0 px-2 py-1.5 rounded-md text-xs bg-[var(--color-brand)] text-white font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          应用
        </button>
      </div>
      {activeSelection && (
        <p className="mt-1.5 text-[10px] text-[var(--color-text-placeholder)] truncate">
          当前: {activeSelection.provider_name} / {activeSelection.model_name}
        </p>
      )}
    </div>
  )
}
