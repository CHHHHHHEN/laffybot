import { useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface CollapsibleProps {
  title: string
  defaultOpen?: boolean
  children: ReactNode
  className?: string
}

export function Collapsible({ title, defaultOpen = false, children, className = '' }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`border border-[var(--color-border)] rounded-md overflow-hidden ${className}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full px-3 py-2 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
        aria-expanded={open}
      >
        <span className="font-medium text-[var(--color-text-primary)]">{title}</span>
        {open ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}
      </button>
      {open && (
        <div className="px-3 py-2 text-xs text-[var(--color-text-secondary)] border-t border-[var(--color-border)]">
          {children}
        </div>
      )}
    </div>
  )
}
