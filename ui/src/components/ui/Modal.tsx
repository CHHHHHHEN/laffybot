import { type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

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
  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => { if (!open) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-[var(--z-modal)]" />
        <Dialog.Content
          className={cn(
            'fixed z-[var(--z-modal)] left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2',
            'bg-[var(--color-page-bg)] rounded-lg shadow-xl w-full mx-4 p-6',
            'focus:outline-none',
            sizeClasses[size]
          )}
        >
          <Dialog.Close
            className="absolute top-4 right-4 p-1 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
            aria-label="关闭"
          >
            <X size={16} />
          </Dialog.Close>
          {title && (
            <Dialog.Title className="text-h3 font-semibold text-[var(--color-text-primary)] mb-4">
              {title}
            </Dialog.Title>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
