import { ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { SessionStatusBadge } from './SessionStatusBadge'
import { Button } from '@/components/ui/Button'
import type { SessionResponse } from '@/lib/api'

interface ChatHeaderProps {
  session: SessionResponse | null
}

export function ChatHeader({ session }: ChatHeaderProps) {
  const navigate = useNavigate()

  return (
    <div className="flex items-center gap-3 px-4 h-14 border-b border-[var(--color-border)] shrink-0">
      <Button
        variant="icon"
        onClick={() => navigate('/chat')}
        aria-label="返回列表"
      >
        <ArrowLeft size={18} />
      </Button>
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
