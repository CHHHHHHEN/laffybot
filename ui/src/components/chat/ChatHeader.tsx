import { ArrowLeft, Pencil, Check, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import { SessionStatusBadge } from './SessionStatusBadge'
import { Button } from '@/components/ui/Button'
import type { SessionResponse } from '@/lib/api'
import { useUpdateSessionTitle } from '@/hooks/use-update-session-title'

interface ChatHeaderProps {
  session: SessionResponse | null
}

export function ChatHeader({ session }: ChatHeaderProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const updateTitle = useUpdateSessionTitle(session?.session_id ?? '')

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleStartEdit = () => {
    setEditValue(session?.title ?? '')
    setIsEditing(true)
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditValue('')
  }

  const handleSaveEdit = () => {
    const trimmed = editValue.trim()
    if (trimmed && trimmed !== session?.title) {
      updateTitle.mutate(trimmed)
    }
    setIsEditing(false)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit()
    } else if (e.key === 'Escape') {
      handleCancelEdit()
    }
  }

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
          <div className="flex-1 flex items-center gap-2 min-w-0">
            {isEditing ? (
              <div className="flex items-center gap-1 flex-1 min-w-0">
                <input
                  ref={inputRef}
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onBlur={handleSaveEdit}
                  className="flex-1 min-w-0 px-2 py-1 text-sm font-medium bg-[var(--color-secondary-bg)] border border-[var(--color-border)] rounded outline-none focus:border-[var(--color-primary)]"
                  placeholder="输入标题..."
                  maxLength={100}
                />
                <Button
                  variant="icon"
                  onClick={handleSaveEdit}
                  aria-label="保存标题"
                >
                  <Check size={16} />
                </Button>
                <Button
                  variant="icon"
                  onClick={handleCancelEdit}
                  aria-label="取消编辑"
                >
                  <X size={16} />
                </Button>
              </div>
            ) : (
              <>
                <span className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                  {session.title ?? (
                    <span className="text-[var(--color-text-placeholder)] italic">
                      Generating title...
                    </span>
                  )}
                </span>
                <Button
                  variant="icon"
                  onClick={handleStartEdit}
                  aria-label="编辑标题"
                  className="shrink-0"
                >
                  <Pencil size={14} />
                </Button>
              </>
            )}
          </div>
          <span className="text-xs text-[var(--color-text-placeholder)] truncate shrink-0">
            {session.model_name}
          </span>
          <SessionStatusBadge status={session.status} />
        </>
      )}
    </div>
  )
}
