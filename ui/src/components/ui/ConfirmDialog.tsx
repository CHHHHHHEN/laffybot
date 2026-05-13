import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  description: string
  confirmLabel?: string
  variant?: 'danger' | 'default'
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  isOpen,
  title,
  description,
  confirmLabel = '确认',
  variant = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (isOpen) {
      confirmRef.current?.focus()
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

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div
        className="relative bg-[var(--color-page-bg)] rounded-lg shadow-xl w-full max-w-sm mx-4 p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
      >
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
          aria-label="关闭"
        >
          <X size={16} />
        </button>
        <h3 id="confirm-title" className="text-h3 font-semibold text-[var(--color-text-primary)] mb-2">
          {title}
        </h3>
        <p className="text-sm text-[var(--color-text-secondary)] mb-6">{description}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-primary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
          >
            取消
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className={`px-4 py-2 text-sm rounded-md text-white font-medium transition-colors duration-150 ${
              variant === 'danger'
                ? 'bg-[var(--color-error)] hover:opacity-90'
                : 'bg-[var(--color-brand)] hover:bg-[var(--color-brand-hover)]'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
