import { useState } from 'react'
import { Plus, Trash2, Loader2 } from 'lucide-react'
import { useProviderStore } from '@/stores/provider-store'

interface ModelListProps {
  providerId: string
  models: { id: string; name: string }[]
}

export function ModelList({ providerId, models }: ModelListProps) {
  const [newName, setNewName] = useState('')
  const [adding, setAdding] = useState(false)
  const addModel = useProviderStore((s) => s.addModel)
  const deleteModel = useProviderStore((s) => s.deleteModel)

  const handleAdd = async () => {
    if (!newName.trim() || adding) return
    setAdding(true)
    try {
      await addModel(providerId, newName.trim())
      setNewName('')
    } catch {
      // error handled by toast
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (modelId: string) => {
    try {
      await deleteModel(providerId, modelId)
    } catch {
      // error handled by toast
    }
  }

  return (
    <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
      <div className="flex flex-wrap gap-2 mb-3">
        {models.map((model) => (
          <span
            key={model.id}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-mono bg-[var(--color-secondary-bg)] text-[var(--color-text-secondary)] group"
          >
            {model.name}
            <button
              onClick={() => handleDelete(model.id)}
              className="opacity-0 group-hover:opacity-100 text-[var(--color-text-placeholder)] hover:text-[var(--color-error)] transition-all duration-150"
              aria-label={`删除模型 ${model.name}`}
            >
              <Trash2 size={12} />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd() } }}
          placeholder="添加模型名称..."
          className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-2.5 py-1.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newName.trim()}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs bg-[var(--color-brand)] text-white font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          添加
        </button>
      </div>
    </div>
  )
}
