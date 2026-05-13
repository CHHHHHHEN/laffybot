import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ToastContainer } from '@/components/ui/Toast'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { useSessionStore } from '@/stores/session-store'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'

export function AppShell() {
  const fetchSessions = useSessionStore((s) => s.fetchSessions)

  useKeyboardShortcuts()

  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 bg-[var(--color-page-bg)]">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
      <ToastContainer />
    </div>
  )
}
