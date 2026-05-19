import { useState } from 'react'
import { Settings2, Loader2, Check, X, Brain, MessageSquareText, Combine } from 'lucide-react'
import { useProviders, useModels, useSummaryModel, useSetSummaryModel, useClearSummaryModel, useExtractModel, useSetExtractModel, useClearExtractModel, useConsolidationModel, useSetConsolidationModel, useClearConsolidationModel, useSystemPrompt, useSetSystemPrompt } from '@/hooks/use-providers'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

function ProviderModelSelector({
  currentConfig,
  providers,
  onSave,
  onClear,
  isSaving,
  isClearing,
}: {
  currentConfig: { provider_id: string; model_name: string } | null | undefined
  providers: { id: string; name: string }[]
  onSave: (providerId: string, modelName: string) => Promise<void>
  onClear: () => Promise<void>
  isSaving: boolean
  isClearing: boolean
}) {
  const [selectedProviderId, setSelectedProviderId] = useState(currentConfig?.provider_id ?? '')
  const [selectedModelName, setSelectedModelName] = useState(currentConfig?.model_name ?? '')
  const { data: models = [], isLoading: modelsLoading } = useModels(selectedProviderId)

  const handleProviderChange = (providerId: string) => {
    setSelectedProviderId(providerId)
    setSelectedModelName('')
  }

  const handleSave = async () => {
    if (!selectedProviderId || !selectedModelName) {
      toast.error('请选择提供商和模型')
      return
    }
    await onSave(selectedProviderId, selectedModelName)
  }

  const handleClear = async () => {
    await onClear()
    setSelectedProviderId('')
    setSelectedModelName('')
  }

  return (
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
  )
}

export function AdvancedSettingsPage() {
  const { data: providers = [], isLoading: providersLoading } = useProviders()
  const { data: currentSummaryConfig } = useSummaryModel()
  const { data: currentExtractConfig } = useExtractModel()
  const { data: currentConsolidationConfig } = useConsolidationModel()
  const { data: systemPromptData } = useSystemPrompt()
  const setSummaryModel = useSetSummaryModel()
  const clearSummaryModel = useClearSummaryModel()
  const setExtractModel = useSetExtractModel()
  const clearExtractModel = useClearExtractModel()
  const setConsolidationModel = useSetConsolidationModel()
  const clearConsolidationModel = useClearConsolidationModel()
  const setSystemPrompt = useSetSystemPrompt()

  const [isSavingSummary, setIsSavingSummary] = useState(false)
  const [isClearingSummary, setIsClearingSummary] = useState(false)
  const [isSavingExtract, setIsSavingExtract] = useState(false)
  const [isClearingExtract, setIsClearingExtract] = useState(false)
  const [isSavingConsolidation, setIsSavingConsolidation] = useState(false)
  const [isClearingConsolidation, setIsClearingConsolidation] = useState(false)
  const [systemPromptValue, setSystemPromptValue] = useState('')
  const [isSavingSystemPrompt, setIsSavingSystemPrompt] = useState(false)
  const [systemPromptInitialized, setSystemPromptInitialized] = useState(false)

  if (!systemPromptInitialized && systemPromptData) {
    setSystemPromptValue(systemPromptData.system_prompt)
    setSystemPromptInitialized(true)
  }

  const handleSaveSummary = async (providerId: string, modelName: string) => {
    setIsSavingSummary(true)
    try {
      await setSummaryModel.mutateAsync({ provider_id: providerId, model_name: modelName })
      toast.success('总结模型配置已保存')
    } catch {
      toast.error('保存失败，请稍后重试')
    } finally {
      setIsSavingSummary(false)
    }
  }

  const handleClearSummary = async () => {
    setIsClearingSummary(true)
    try {
      await clearSummaryModel.mutateAsync()
      toast.success('已清除总结模型配置')
    } catch {
      toast.error('清除失败，请稍后重试')
    } finally {
      setIsClearingSummary(false)
    }
  }

  const handleSaveExtract = async (providerId: string, modelName: string) => {
    setIsSavingExtract(true)
    try {
      await setExtractModel.mutateAsync({ provider_id: providerId, model_name: modelName })
      toast.success('记忆提取模型配置已保存')
    } catch {
      toast.error('保存失败，请稍后重试')
    } finally {
      setIsSavingExtract(false)
    }
  }

  const handleClearExtract = async () => {
    setIsClearingExtract(true)
    try {
      await clearExtractModel.mutateAsync()
      toast.success('已清除记忆提取模型配置')
    } catch {
      toast.error('清除失败，请稍后重试')
    } finally {
      setIsClearingExtract(false)
    }
  }

  const handleSaveConsolidation = async (providerId: string, modelName: string) => {
    setIsSavingConsolidation(true)
    try {
      await setConsolidationModel.mutateAsync({ provider_id: providerId, model_name: modelName })
      toast.success('记忆归并模型配置已保存')
    } catch {
      toast.error('保存失败，请稍后重试')
    } finally {
      setIsSavingConsolidation(false)
    }
  }

  const handleClearConsolidation = async () => {
    setIsClearingConsolidation(true)
    try {
      await clearConsolidationModel.mutateAsync()
      toast.success('已清除记忆归并模型配置')
    } catch {
      toast.error('清除失败，请稍后重试')
    } finally {
      setIsClearingConsolidation(false)
    }
  }

  const handleSaveSystemPrompt = async () => {
    setIsSavingSystemPrompt(true)
    try {
      await setSystemPrompt.mutateAsync(systemPromptValue)
      toast.success('系统提示已保存')
    } catch {
      toast.error('保存失败，请稍后重试')
    } finally {
      setIsSavingSystemPrompt(false)
    }
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
      {/* System Prompt Section */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <MessageSquareText size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">系统提示</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            为所有新会话设置的全局系统提示词
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-8">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>系统提示词会在每个新会话开始前注入 LLM 上下文。此处设置的提示词会在重启后恢复为默认值。</p>
          <p>如果你在 config.json 中配置了 <code className="text-[var(--color-text-primary)] bg-[var(--color-secondary-bg)] px-1 rounded">system_prompt_template</code>，则模板会作为完整提示词，此处设置将不生效。</p>
        </div>

        <textarea
          value={systemPromptValue}
          onChange={(e) => setSystemPromptValue(e.target.value)}
          rows={5}
          className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] resize-y font-mono"
          placeholder="输入系统提示词..."
        />

        <div className="flex justify-end mt-4">
          <Button
            onClick={handleSaveSystemPrompt}
            disabled={isSavingSystemPrompt}
          >
            {isSavingSystemPrompt ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            保存系统提示
          </Button>
        </div>
      </div>

      {/* Summary Model Section */}
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

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-8">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>总结模型用于为新会话自动生成标题。建议选择轻量、低成本的模型（如 gpt-4o-mini、claude-3-haiku 等）。</p>
          <p>未配置时，系统将截取首条用户消息的前 50 个字符作为标题。</p>
        </div>

        {currentSummaryConfig && (
          <div className="mb-4 p-3 rounded bg-[var(--color-secondary-bg)] text-sm">
            <span className="text-[var(--color-text-secondary)]">当前配置：</span>
            <span className="font-mono text-[var(--color-text-primary)]">
              {' '}{currentSummaryConfig.provider_id} / {currentSummaryConfig.model_name}
            </span>
          </div>
        )}

        {providers.length === 0 ? (
          <div className="text-center py-6 text-sm text-[var(--color-text-placeholder)]">
            请先在「提供商配置」中添加提供商
          </div>
        ) : (
          <ProviderModelSelector
            currentConfig={currentSummaryConfig}
            providers={providers}
            onSave={handleSaveSummary}
            onClear={handleClearSummary}
            isSaving={isSavingSummary}
            isClearing={isClearingSummary}
          />
        )}
      </div>

      {/* Extract Model Section */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <Brain size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">记忆提取模型</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            用于从会话中提取结构化记忆的模型
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-4">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>记忆提取模型用于从完成的会话中提取可复用的跨会话知识（如用户偏好、项目约定、工具使用模式等）。</p>
          <p>建议选择指令遵循能力较强的模型（如 gpt-4o、claude-3.5-sonnet 等）。</p>
        </div>

        {currentExtractConfig && (
          <div className="mb-4 p-3 rounded bg-[var(--color-secondary-bg)] text-sm">
            <span className="text-[var(--color-text-secondary)]">当前配置：</span>
            <span className="font-mono text-[var(--color-text-primary)]">
              {' '}{currentExtractConfig.provider_id} / {currentExtractConfig.model_name}
            </span>
          </div>
        )}

        {providers.length === 0 ? (
          <div className="text-center py-6 text-sm text-[var(--color-text-placeholder)]">
            请先在「提供商配置」中添加提供商
          </div>
        ) : (
          <ProviderModelSelector
            currentConfig={currentExtractConfig}
            providers={providers}
            onSave={handleSaveExtract}
            onClear={handleClearExtract}
            isSaving={isSavingExtract}
            isClearing={isClearingExtract}
          />
        )}
      </div>

      {/* Consolidation Model Section */}
      <div className="flex items-center gap-3 mb-6 mt-8">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <Combine size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">记忆归并模型</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            用于将多条原始记忆合并为结构化摘要的模型
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-4">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>记忆归并模型用于将多条原始记忆通过 LLM 合并为一条结构化摘要，减少冗余并提升记忆注入效率。</p>
          <p>建议选择指令遵循能力较强的模型（如 gpt-4o、claude-3.5-sonnet 等）。</p>
        </div>

        {currentConsolidationConfig && (
          <div className="mb-4 p-3 rounded bg-[var(--color-secondary-bg)] text-sm">
            <span className="text-[var(--color-text-secondary)]">当前配置：</span>
            <span className="font-mono text-[var(--color-text-primary)]">
              {' '}{currentConsolidationConfig.provider_id} / {currentConsolidationConfig.model_name}
            </span>
          </div>
        )}

        {providers.length === 0 ? (
          <div className="text-center py-6 text-sm text-[var(--color-text-placeholder)]">
            请先在「提供商配置」中添加提供商
          </div>
        ) : (
          <ProviderModelSelector
            currentConfig={currentConsolidationConfig}
            providers={providers}
            onSave={handleSaveConsolidation}
            onClear={handleClearConsolidation}
            isSaving={isSavingConsolidation}
            isClearing={isClearingConsolidation}
          />
        )}
      </div>
    </div>
  )
}
