import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface NewSessionDialogProps {
  isOpen: boolean
  onSubmit: (model: string, systemPrompt: string, maxIterations: number) => void
  onCancel: () => void
  error?: string | null
}

export function NewSessionDialog({ isOpen, onSubmit, onCancel, error }: NewSessionDialogProps) {
  const [model, setModel] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [maxIterations, setMaxIterations] = useState(10)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isOpen) {
      setModel('')
      setSystemPrompt('')
      setMaxIterations(10)
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onCancel])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!model.trim()) return
    onSubmit(model.trim(), systemPrompt.trim(), maxIterations)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div
        className="relative bg-[var(--color-page-bg)] rounded-lg shadow-xl w-full max-w-md mx-4 p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-session-title"
      >
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
          aria-label="关闭"
        >
          <X size={16} />
        </button>

        <h3 id="new-session-title" className="text-h3 font-semibold text-[var(--color-text-primary)] mb-4">
          新建会话
        </h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="model-input" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              模型
            </label>
            <input
              ref={inputRef}
              id="model-input"
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="例如: deepseek-ai/DeepSeek-V3"
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
              required
            />
          </div>

          <div>
            <label htmlFor="system-prompt" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              System Prompt <span className="text-[var(--color-text-placeholder)]">(可选)</span>
            </label>
            <textarea
              id="system-prompt"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={3}
              placeholder="设定助手的角色和行为..."
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150 resize-none"
            />
          </div>

          <div>
            <label htmlFor="max-iterations" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              最大迭代次数
            </label>
            <input
              id="max-iterations"
              type="number"
              value={maxIterations}
              onChange={(e) => setMaxIterations(Number(e.target.value))}
              min={1}
              max={100}
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
            />
          </div>

          {error && (
            <p className="text-sm text-[var(--color-error)]">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-primary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={!model.trim()}
              className="px-4 py-2 text-sm rounded-md bg-[var(--color-brand)] text-white font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              创建
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
