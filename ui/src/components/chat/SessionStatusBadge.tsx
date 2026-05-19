import { cn } from '@/lib/utils'

type SessionStatus = 'idle' | 'busy' | 'error'

const statusConfig: Record<SessionStatus, { label: string; color: string }> = {
  idle: { label: '就绪', color: 'bg-[var(--color-success)]' },
  busy: { label: '处理中', color: 'bg-[var(--color-info)]' },
  error: { label: '错误', color: 'bg-[var(--color-error)]' },
}

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const config = statusConfig[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-caption text-[var(--color-text-secondary)]">
      <span className={cn('w-2 h-2 rounded-full', config.color)} aria-hidden="true" />
      <span>{config.label}</span>
    </span>
  )
}
