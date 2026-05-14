import { useState } from 'react'
import { Settings2, Loader2, Check, X } from 'lucide-react'
import { useProviders, useModels, useSummaryModel, useSetSummaryModel, useClearSummaryModel } from '@/hooks/use-providers'
import { Button } from '@/components/ui/Button'
import { useToastStore } from '@/stores/toast-store'

export function AdvancedSettingsPage() {
  const { data: providers = [], isLoading: providersLoading } = useProviders()
  const { data: currentConfig } = useSummaryModel()
  const setSummaryModel = useSetSummaryModel()
  const clearSummaryModel = useClearSummaryModel()

  // Initialize with current config if available
  const [selectedProviderId, setSelectedProviderId] = useState<string>(currentConfig?.provider_id ?? '')
  const [selectedModelName, setSelectedModelName] = useState<string>(currentConfig?.model_name ?? '')
  const [isSaving, setIsSaving] = useState(false)
  const [isClearing, setIsClearing] = useState(false)

  const { data: models = [], isLoading: modelsLoading } = useModels(selectedProviderId)

  const handleSave = async () => {
    if (!selectedProviderId || !selectedModelName) {
      useToastStore.getState().addToast('error', '请选择提供商和模型')
      return
    }

    setIsSaving(true)
    try {
      await setSummaryModel.mutateAsync({
        provider_id: selectedProviderId,
        model_name: selectedModelName,
      })
      useToastStore.getState().addToast('success', '总结模型配置已保存')
    } catch {
      useToastStore.getState().addToast('error', '保存失败，请稍后重试')
    } finally {
      setIsSaving(false)
    }
  }

  const handleClear = async () => {
    setIsClearing(true)
    try {
      await clearSummaryModel.mutateAsync()
      setSelectedProviderId('')
      setSelectedModelName('')
      useToastStore.getState().addToast('success', '已清除总结模型配置')
    } catch {
      useToastStore.getState().addToast('error', '清除失败，请稍后重试')
    } finally {
      setIsClearing(false)
    }
  }

  const handleProviderChange = (providerId: string) => {
    setSelectedProviderId(providerId)
    setSelectedModelName('') // Reset model when provider changes
  }

  if (providersLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[720px]">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <Settings2 size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">总结模型配置</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            用于自动生成会话标题的轻量模型
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-4">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>总结模型用于为新会话自动生成标题。建议选择轻量、低成本的模型（如 gpt-4o-mini、claude-3-haiku 等）。</p>
          <p>未配置时，系统将截取首条用户消息的前 50 个字符作为标题。</p>
        </div>

        {currentConfig && (
          <div className="mb-4 p-3 rounded bg-[var(--color-secondary-bg)] text-sm">
            <span className="text-[var(--color-text-secondary)]">当前配置：</span>
            <span className="font-mono text-[var(--color-text-primary)]">
              {' '}{currentConfig.provider_id} / {currentConfig.model_name}
            </span>
          </div>
        )}

        {providers.length === 0 ? (
          <div className="text-center py-6 text-sm text-[var(--color-text-placeholder)]">
            请先在「提供商配置」中添加提供商
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-primary)] mb-1.5">
                提供商
              </label>
              <select
                value={selectedProviderId}
                onChange={(e) => handleProviderChange(e.target.value)}
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
              >
                <option value="">选择提供商...</option>
                {providers.map((provider) => (
                  <option key={provider.id} value={provider.id}>
                    {provider.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-[var(--color-text-primary)] mb-1.5">
                模型
              </label>
              <select
                value={selectedModelName}
                onChange={(e) => setSelectedModelName(e.target.value)}
                disabled={!selectedProviderId || modelsLoading}
                className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <option value="">
                  {modelsLoading ? '加载中...' : '选择模型...'}
                </option>
                {models.map((model) => (
                  <option key={model.id} value={model.name}>
                    {model.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-2 pt-2">
              <Button
                onClick={handleSave}
                disabled={isSaving || !selectedProviderId || !selectedModelName}
              >
                {isSaving ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Check size={14} />
                )}
                保存配置
              </Button>
              {currentConfig && (
                <Button
                  variant="ghost"
                  onClick={handleClear}
                  disabled={isClearing}
                >
                  {isClearing ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <X size={14} />
                  )}
                  清除配置
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
