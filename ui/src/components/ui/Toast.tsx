import { X, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { useToastStore } from '@/stores/toast-store'

const iconMap = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
}

const colorMap = {
  success: 'text-[var(--color-success)]',
  error: 'text-[var(--color-error)]',
  info: 'text-[var(--color-info)]',
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const removeToast = useToastStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  const topToast = toasts[toasts.length - 1]

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[var(--z-toast)]">
      <div
        key={topToast.id}
        className="flex items-center gap-3 bg-[var(--color-page-bg)] border border-[var(--color-border)] rounded-lg shadow-lg px-4 py-3 animate-in fade-in slide-in-from-top-2 duration-200 ease-out"
      >
        {(() => {
          const Icon = iconMap[topToast.type]
          return <Icon size={18} className={`shrink-0 ${colorMap[topToast.type]}`} />
        })()}
        <p className="text-sm text-[var(--color-text-primary)]">{topToast.message}</p>
        <button
          onClick={() => removeToast(topToast.id)}
          className="p-0.5 rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
          aria-label="关闭通知"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
