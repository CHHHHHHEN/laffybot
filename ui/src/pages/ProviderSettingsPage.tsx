import { useState } from 'react'
import { Plus, Pencil, Trash2, Globe, Loader2, Plug } from 'lucide-react'
import { useQueries } from '@tanstack/react-query'
import * as api from '@/lib/api'
import { useProviders, useCreateProvider, useUpdateProvider, useDeleteProvider } from '@/hooks/use-providers'
import { ProviderForm } from '@/components/settings/ProviderForm'
import { ModelList } from '@/components/settings/ModelList'
import { Button } from '@/components/ui/Button'
import { useToastStore } from '@/stores/toast-store'

export function ProviderSettingsPage() {
  const { data: providers = [], isLoading } = useProviders()
  const createProvider = useCreateProvider()
  const updateProvider = useUpdateProvider()
  const deleteProvider = useDeleteProvider()

  const modelQueries = useQueries({
    queries: providers.map((p) => ({
      queryKey: ['models', p.id],
      queryFn: () => api.listModels(p.id),
      staleTime: 30_000,
    })),
  })

  const modelsMap = Object.fromEntries(
    providers.map((p, i) => [p.id, modelQueries[i].data ?? []])
  )

  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const handleCreate = async (data: { name: string; base_url: string; api_key: string; extra_headers: Record<string, string> }) => {
    await createProvider.mutateAsync(data)
    setShowForm(false)
    useToastStore.getState().addToast('success', '提供商创建成功')
  }

  const handleUpdate = async (data: { name: string; base_url: string; api_key: string; extra_headers: Record<string, string> }) => {
    if (!editingId) return
    await updateProvider.mutateAsync({ id: editingId, data })
    setEditingId(null)
    useToastStore.getState().addToast('success', '提供商更新成功')
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteProvider.mutateAsync(id)
      useToastStore.getState().addToast('success', '提供商已删除')
    } catch {
      useToastStore.getState().addToast('error', '删除提供商失败')
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await api.testProvider(id)
      if (result.success) {
        useToastStore.getState().addToast('success', `连接成功 (${result.latency_ms}ms)`)
      } else {
        useToastStore.getState().addToast('error', `连接失败: ${result.message}`)
      }
    } catch {
      useToastStore.getState().addToast('error', '连接测试失败')
    } finally {
      setTestingId(null)
    }
  }

  const editingProvider = editingId ? providers.find((p) => p.id === editingId) : undefined

  return (
    <div className="p-6 max-w-[720px]">
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-[var(--color-text-secondary)]">
          管理 LLM 提供商配置
        </p>
        <Button
          onClick={() => setShowForm(true)}
          aria-label="添加提供商"
        >
          <Plus size={16} />
          添加提供商
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
        </div>
      ) : providers.length === 0 ? (
        <div className="text-center py-12">
          <Globe size={48} className="mx-auto mb-4 text-[var(--color-text-placeholder)]" />
          <p className="text-[var(--color-text-secondary)] mb-2">暂无提供商配置</p>
          <p className="text-sm text-[var(--color-text-placeholder)]">点击上方按钮添加你的第一个 LLM 提供商</p>
        </div>
      ) : (
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
                      {!provider.has_api_key && (
                        <span className="ml-2 text-xs text-[var(--color-error)]">(未配置 API Key)</span>
                      )}
                    </h3>
                    <p className="text-xs text-[var(--color-text-placeholder)] font-mono">
                      {provider.base_url}
                    </p>
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="icon"
                    onClick={() => handleTest(provider.id)}
                    disabled={testingId === provider.id}
                    aria-label="测试连接"
                  >
                    {testingId === provider.id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Plug size={14} />
                    )}
                  </Button>
                  <Button
                    variant="icon"
                    onClick={() => setEditingId(provider.id)}
                    aria-label="编辑提供商"
                  >
                    <Pencil size={14} />
                  </Button>
                  <Button
                    variant="icon"
                    onClick={() => handleDelete(provider.id)}
                    aria-label="删除提供商"
                  >
                    <Trash2 size={14} />
                  </Button>
                </div>
              </div>

              <ModelList
                providerId={provider.id}
                models={modelsMap[provider.id] || []}
              />
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <ProviderForm
          isOpen={true}
          onSave={handleCreate}
          onCancel={() => setShowForm(false)}
          title="添加提供商"
        />
      )}

      {editingId !== null && (
        <ProviderForm
          isOpen={true}
          initialData={editingProvider ? { name: editingProvider.name, base_url: editingProvider.base_url } : undefined}
          onSave={handleUpdate}
          onCancel={() => setEditingId(null)}
          title="编辑提供商"
        />
      )}
    </div>
  )
}
