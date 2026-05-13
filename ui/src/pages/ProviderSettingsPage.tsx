import { useState } from 'react'
import { Plus, Pencil, Trash2, Globe } from 'lucide-react'

interface Provider {
  id: string
  name: string
  baseUrl: string
  models: string[]
}

const mockProviders: Provider[] = [
  { id: '1', name: 'DeepSeek', baseUrl: 'https://api.deepseek.com', models: ['deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-R1'] },
  { id: '2', name: 'OpenAI', baseUrl: 'https://api.openai.com', models: ['gpt-4o', 'gpt-4o-mini'] },
]

export function ProviderSettingsPage() {
  const [providers] = useState<Provider[]>(mockProviders)

  return (
    <div className="p-6 max-w-[720px]">
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-[var(--color-text-secondary)]">
          管理 LLM 提供商配置
        </p>
        <button
          className="inline-flex items-center gap-2 rounded-md bg-[var(--color-brand)] text-white px-4 py-2 text-sm font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150"
          aria-label="添加提供商"
        >
          <Plus size={16} />
          添加提供商
        </button>
      </div>

      <div className="space-y-4">
        {providers.map((provider) => (
          <div
            key={provider.id}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-md bg-[var(--color-secondary-bg)] flex items-center justify-center">
                  <Globe size={16} className="text-[var(--color-text-secondary)]" />
                </div>
                <div>
                  <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
                    {provider.name}
                  </h3>
                  <p className="text-xs text-[var(--color-text-placeholder)] font-mono">
                    {provider.baseUrl}
                  </p>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
                  aria-label="编辑提供商"
                >
                  <Pencil size={14} />
                </button>
                <button
                  className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-error)] transition-colors duration-150"
                  aria-label="删除提供商"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {provider.models.map((model) => (
                <span
                  key={model}
                  className="inline-flex items-center px-2 py-1 rounded text-xs font-mono bg-[var(--color-secondary-bg)] text-[var(--color-text-secondary)]"
                >
                  {model}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
