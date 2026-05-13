import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useUiStore } from '@/stores/ui-store'
import { NavLinks } from './NavLinks'
import { MessageSquarePlus, PanelLeftClose, PanelLeft, Trash2, Loader2 } from 'lucide-react'
import { useSessionStore } from '@/stores/session-store'
import { NewSessionDialog } from '@/components/ui/NewSessionDialog'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useToastStore } from '@/components/ui/Toast'
import type { Session } from '@/stores/session-store'

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUiStore()
  const navigate = useNavigate()
  const sessions = useSessionStore((s) => s.sessions)
  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const isLoading = useSessionStore((s) => s.isLoading)
  const createSession = useSessionStore((s) => s.createSession)
  const deleteSession = useSessionStore((s) => s.deleteSession)
  const [showNewDialog, setShowNewDialog] = useState(false)
  const [dialogError, setDialogError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const handleCreateSession = async (model: string, systemPrompt: string, maxIterations: number) => {
    setDialogError(null)
    try {
      const session = await createSession({
        model,
        system_prompt: systemPrompt || undefined,
        max_iterations: maxIterations,
      })
      if (session) {
        setShowNewDialog(false)
        navigate(`/chat/${session.session_id}`)
      }
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : '创建会话失败')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteSession(deleteTarget)
      if (activeSessionId === deleteTarget) {
        navigate('/chat')
      }
    } catch {
      useToastStore.getState().addToast('error', '删除会话失败')
    }
    setDeleteTarget(null)
  }

  return (
    <>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-[var(--z-sidebar-overlay)] lg:hidden"
          onClick={() => useUiStore.getState().setSidebarOpen(false)}
        />
      )}

      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-[var(--z-sidebar)]
          flex flex-col bg-[var(--color-page-bg)] border-r border-[var(--color-border)]
          transition-all duration-250 ease-in-out
          ${sidebarOpen ? 'w-60 translate-x-0' : 'w-0 -translate-x-full lg:w-14 lg:translate-x-0'}
        `}
      >
        <div className={`flex flex-col h-full ${sidebarOpen ? 'block' : 'lg:block hidden'}`}>
          {/* Header */}
          <div className="flex items-center justify-between px-4 h-14 border-b border-[var(--color-border)] shrink-0">
            {sidebarOpen && (
              <span className="font-semibold text-base text-[var(--color-text-primary)]">
                Laffybot
              </span>
            )}
            <button
              onClick={toggleSidebar}
              className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
              aria-label={sidebarOpen ? '折叠侧边栏' : '展开侧边栏'}
            >
              {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
            </button>
          </div>

          {/* Nav links */}
          <NavLinks />

          {/* New chat button */}
          <div className="px-3 mb-2">
            <button
              onClick={() => setShowNewDialog(true)}
              className="flex items-center gap-2 w-full rounded-md px-3 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
              aria-label="新建会话"
            >
              <MessageSquarePlus size={18} />
              <span>新建会话</span>
            </button>
          </div>

          {/* Session list */}
          <div className="flex-1 overflow-y-auto px-3">
            {isLoading ? (
              <div className="space-y-2 px-3 py-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-8 rounded-md bg-[var(--color-secondary-bg)] animate-pulse" style={{ width: `${60 + i * 10}%` }} />
                ))}
              </div>
            ) : sessions.length === 0 ? (
              <p className="text-xs text-[var(--color-text-placeholder)] px-3 py-4">
                还没有会话
              </p>
            ) : (
              <div className="flex flex-col gap-0.5">
                {sessions.map((session: Session) => (
                  <div
                    key={session.session_id}
                    onClick={() => navigate(`/chat/${session.session_id}`)}
                    className={`group flex items-center gap-2 rounded-md px-3 py-2 text-sm cursor-pointer transition-colors duration-150 ${
                      activeSessionId === session.session_id
                        ? 'bg-[var(--color-hover-bg)] text-[var(--color-text-primary)]'
                        : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)]'
                    }`}
                  >
                    <div className="flex-1 truncate">{session.model || session.session_id.slice(0, 8)}</div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setDeleteTarget(session.session_id)
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded text-[var(--color-text-placeholder)] hover:text-[var(--color-error)] hover:bg-[var(--color-hover-bg)] transition-all duration-150"
                      aria-label="删除会话"
                    >
                      <Trash2 size={14} />
                    </button>
                    {session.status === 'busy' && (
                      <Loader2 size={14} className="animate-spin text-[var(--color-info)] shrink-0" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </aside>

      <NewSessionDialog
        isOpen={showNewDialog}
        onSubmit={handleCreateSession}
        onCancel={() => { setShowNewDialog(false); setDialogError(null) }}
        error={dialogError}
      />

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title="删除会话"
        description="删除后将无法恢复该会话及其所有消息。"
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  )
}
