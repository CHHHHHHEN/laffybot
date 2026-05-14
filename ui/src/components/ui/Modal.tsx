import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ModalProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
}

export function Modal({ isOpen, onClose, title, children, size = 'md' }: ModalProps) {
  useEffect(() => {
    if (!isOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div
        className={`relative bg-[var(--color-page-bg)] rounded-lg shadow-xl w-full ${sizeClasses[size]} mx-4 p-6`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
          aria-label="关闭"
        >
          <X size={16} />
        </button>
        {title && (
          <h3 className="text-h3 font-semibold text-[var(--color-text-primary)] mb-4">
            {title}
          </h3>
        )}
        {children}
      </div>
    </div>
  )
}
