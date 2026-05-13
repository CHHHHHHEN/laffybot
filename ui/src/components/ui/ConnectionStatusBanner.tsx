import type { ConnectionStatus } from '@/stores/chat-store'

interface ConnectionStatusBannerProps {
  status: ConnectionStatus
}

const config: Record<ConnectionStatus, { label: string; color: string; show: boolean }> = {
  disconnected: { label: '', color: '', show: false },
  connecting: { label: '正在连接...', color: 'bg-[var(--color-info)]', show: true },
  connected: { label: '', color: '', show: false },
  error: { label: '连接失败，请检查服务状态', color: 'bg-[var(--color-error)]', show: true },
}

export function ConnectionStatusBanner({ status }: ConnectionStatusBannerProps) {
  const c = config[status]
  if (!c.show) return null

  return (
    <div className={`${c.color} text-white text-xs text-center py-1 px-4`}>
      {c.label}
    </div>
  )
}
