import { useState, useRef } from 'react'
import { Settings } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useActiveSelection } from '@/hooks/use-providers'
import { Modal } from './Modal'
import { Button } from './Button'
import { Textarea, Input } from './Input'

interface NewSessionDialogProps {
  isOpen: boolean
  onSubmit: (systemPrompt: string, maxIterations: number) => void
  onCancel: () => void
  error?: string | null
}

export function NewSessionDialog({ isOpen, onSubmit, onCancel, error }: NewSessionDialogProps) {
  const navigate = useNavigate()
  const { data: activeSelection } = useActiveSelection()
  const [systemPrompt, setSystemPrompt] = useState('')
  const [maxIterations, setMaxIterations] = useState(10)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(systemPrompt.trim(), maxIterations)
  }

  const hasActive = activeSelection !== null && activeSelection !== undefined

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title="新建会话" size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            当前模型
          </label>
          {hasActive ? (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-secondary-bg)] px-3 py-2 text-sm text-[var(--color-text-secondary)]">
              {activeSelection!.provider_name} / {activeSelection!.model_name}
            </div>
          ) : (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-secondary-bg)] px-3 py-2">
              <p className="text-sm text-[var(--color-text-placeholder)] mb-2">
                请先选择提供商和模型
              </p>
              <Button
                variant="link"
                size="sm"
                onClick={() => { onCancel(); navigate('/settings/provider') }}
              >
                <Settings size={12} />
                前往设置配置提供商
              </Button>
            </div>
          )}
        </div>

        <div>
          <label htmlFor="system-prompt" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            System Prompt <span className="text-[var(--color-text-placeholder)]">(可选)</span>
          </label>
          <Textarea
            ref={inputRef}
            id="system-prompt"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={3}
            placeholder="设定助手的角色和行为..."
          />
        </div>

        <div>
          <label htmlFor="max-iterations" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            最大迭代次数
          </label>
          <Input
            id="max-iterations"
            type="number"
            value={maxIterations}
            onChange={(e) => setMaxIterations(Number(e.target.value))}
            min={1}
            max={100}
          />
        </div>

        {error && (
          <p className="text-sm text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" onClick={onCancel}>取消</Button>
          <Button type="submit" disabled={!hasActive}>创建</Button>
        </div>
      </form>
    </Modal>
  )
}
