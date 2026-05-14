import { useNavigate } from 'react-router-dom'
import { Settings } from 'lucide-react'
import { useProviders, useModels, useActiveSelection, useSetActiveSelection } from '@/hooks/use-providers'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Input'

export function GlobalModelSelector() {
  const navigate = useNavigate()
  const { data: providers = [] } = useProviders()
  const { data: activeSelection } = useActiveSelection()
  const setActiveSelection = useSetActiveSelection()

  const selectedProviderId = activeSelection?.provider_id ?? ''
  const selectedModelId = activeSelection?.model_id ?? ''

  const { data: currentModels = [] } = useModels(selectedProviderId || undefined)

  const handleProviderChange = (providerId: string) => {
    setActiveSelection.mutate({ providerId, modelId: '' })
  }

  const handleModelChange = (modelId: string) => {
    if (activeSelection) {
      setActiveSelection.mutate({ providerId: activeSelection.provider_id, modelId })
    }
  }

  if (providers.length === 0) {
    return (
      <div className="px-3 py-2">
        <Button
          variant="link"
          size="sm"
          onClick={() => navigate('/settings/provider')}
          className="w-full justify-start"
        >
          <Settings size={14} />
          前往设置配置提供商
        </Button>
      </div>
    )
  }

  return (
    <div className="px-3 py-2 border-b border-[var(--color-border)]">
      <div className="text-xs text-[var(--color-text-placeholder)] mb-2 font-medium">当前模型</div>
      <div className="flex gap-2">
        <Select
          value={selectedProviderId}
          onChange={(e) => handleProviderChange(e.target.value)}
          inputSize="sm"
          className="flex-1 min-w-0"
        >
          <option value="" disabled>提供商</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
        <Select
          value={selectedModelId}
          onChange={(e) => handleModelChange(e.target.value)}
          disabled={!selectedProviderId}
          inputSize="sm"
          className="flex-1 min-w-0"
        >
          <option value="" disabled>模型</option>
          {currentModels.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </Select>
      </div>
      {activeSelection && (
        <p className="mt-1.5 text-[10px] text-[var(--color-text-placeholder)] truncate">
          当前: {activeSelection.provider_name} / {activeSelection.model_name}
        </p>
      )}
    </div>
  )
}
