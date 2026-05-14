import { useState } from 'react'
import { Plus, Trash2, Loader2 } from 'lucide-react'
import { useAddModel, useDeleteModel } from '@/hooks/use-providers'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

interface ModelListProps {
  providerId: string
  models: { id: string; name: string }[]
}

export function ModelList({ providerId, models }: ModelListProps) {
  const [newName, setNewName] = useState('')
  const [adding, setAdding] = useState(false)
  const addModel = useAddModel()
  const deleteModel = useDeleteModel()

  const handleAdd = async () => {
    if (!newName.trim() || adding) return
    setAdding(true)
    try {
      await addModel.mutateAsync({ providerId, name: newName.trim() })
      setNewName('')
    } catch {
      // error handled by toast
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (modelId: string) => {
    try {
      await deleteModel.mutateAsync({ providerId, modelId })
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
            <Button
              variant="icon"
              onClick={() => handleDelete(model.id)}
              className="opacity-0 group-hover:opacity-100"
              aria-label={`删除模型 ${model.name}`}
            >
              <Trash2 size={12} />
            </Button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd() } }}
          placeholder="添加模型名称..."
          inputSize="sm"
          className="flex-1"
        />
        <Button
          size="sm"
          onClick={handleAdd}
          disabled={adding || !newName.trim()}
        >
          {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          添加
        </Button>
      </div>
    </div>
  )
}
