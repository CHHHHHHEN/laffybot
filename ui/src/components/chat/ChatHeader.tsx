import { ArrowLeft, Pencil, Check, X, Archive, RotateCcw } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useState, useRef, useEffect } from 'react'
import { SessionStatusBadge } from './SessionStatusBadge'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Input'
import type { SessionResponse } from '@/lib/api'
import { useUpdateSessionTitle } from '@/hooks/use-update-session-title'
import { useArchiveSession, useUnarchiveSession, useUpdateSessionModel } from '@/hooks/use-sessions'
import { useProviders, useModels } from '@/hooks/use-providers'
import { toast } from 'sonner'

interface ChatHeaderProps {
  session: SessionResponse | null
}

export function ChatHeader({ session }: ChatHeaderProps) {
  const navigate = useNavigate()
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const updateTitle = useUpdateSessionTitle(session?.session_id ?? '')
  const archiveSession = useArchiveSession()
  const unarchiveSession = useUnarchiveSession()

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

  const handleArchive = async () => {
    if (!session) return
    try {
      await archiveSession.mutateAsync(session.session_id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '归档失败')
    }
  }

  const handleUnarchive = async () => {
    if (!session) return
    try {
      await unarchiveSession.mutateAsync(session.session_id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '取消归档失败')
    }
  }

  const isArchived = session?.archived_at != null

  const { data: providers = [] } = useProviders()
  const { data: models = [] } = useModels(session?.provider_id)
  const updateSessionModel = useUpdateSessionModel()
  const [modelSwitching, setModelSwitching] = useState(false)

  const handleProviderChange = (newProviderId: string) => {
    if (!session) return
    setModelSwitching(true)
    const firstModel = models.length > 0 ? models[0].name : ''
    updateSessionModel.mutate(
      { sessionId: session.session_id, data: { provider_id: newProviderId, model_name: firstModel } },
      {
        onError: () => {
          toast.error('切换模型失败')
        },
        onSettled: () => setModelSwitching(false),
      }
    )
  }

  const handleModelChange = (newModelName: string) => {
    if (!session) return
    setModelSwitching(true)
    updateSessionModel.mutate(
      { sessionId: session.session_id, data: { provider_id: session.provider_id, model_name: newModelName } },
      {
        onError: () => {
          toast.error('切换模型失败')
        },
        onSettled: () => setModelSwitching(false),
      }
    )
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
          <div className="flex items-center gap-1 shrink-0">
            <Select
              value={session.provider_id}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={session.status === 'busy' || modelSwitching}
              inputSize="sm"
              className="min-w-[90px]"
            >
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
            <Select
              value={session.model_name}
              onChange={(e) => handleModelChange(e.target.value)}
              disabled={session.status === 'busy' || modelSwitching}
              inputSize="sm"
              className="min-w-[90px]"
            >
              {models.map((m) => (
                <option key={m.id} value={m.name}>{m.name}</option>
              ))}
            </Select>
          </div>
          {isArchived ? (
            <>
              <span className="text-xs text-[var(--color-text-placeholder)] flex items-center gap-1">
                <Archive size={14} />
                已归档
              </span>
              <Button
                variant="icon"
                onClick={handleUnarchive}
                aria-label="取消归档"
                title="取消归档"
              >
                <RotateCcw size={16} />
              </Button>
            </>
          ) : (
            <Button
              variant="icon"
              onClick={handleArchive}
              aria-label="归档"
              title="归档"
            >
              <Archive size={16} />
            </Button>
          )}
          <span className="text-xs text-[var(--color-text-placeholder)] truncate shrink-0">
            {session.model_name}
          </span>
          <SessionStatusBadge status={session.status} />
        </>
      )}
    </div>
  )
}
