import { ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { SessionStatusBadge } from './SessionStatusBadge'
import type { Session } from '@/stores/session-store'

interface ChatHeaderProps {
  session: Session | null
}

export function ChatHeader({ session }: ChatHeaderProps) {
  const navigate = useNavigate()

  return (
    <div className="flex items-center gap-3 px-4 h-14 border-b border-[var(--color-border)] shrink-0">
      <button
        onClick={() => navigate('/chat')}
        className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
        aria-label="返回列表"
      >
        <ArrowLeft size={18} />
      </button>
      {session && (
        <>
          <span className="text-sm font-medium text-[var(--color-text-primary)] truncate">
            {session.model}
          </span>
          <SessionStatusBadge status={session.status} />
        </>
      )}
    </div>
  )
}
