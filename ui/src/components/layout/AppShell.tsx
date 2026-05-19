import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Sidebar } from './Sidebar'
import { ErrorBoundary } from '@/components/ui/ErrorBoundary'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useGlobalEvents } from '@/hooks/use-global-events'
import { useUiStore } from '@/stores/ui-store'

function useTheme() {
  const theme = useUiStore((s) => s.theme)

  useEffect(() => {
    const root = document.documentElement

    const apply = (isDark: boolean) => {
      root.classList.toggle('dark', isDark)
    }

    if (theme === 'dark') {
      apply(true)
    } else if (theme === 'light') {
      apply(false)
    } else {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      apply(mq.matches)
      const handler = (e: MediaQueryListEvent) => apply(e.matches)
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
  }, [theme])
}

export function AppShell() {
  useKeyboardShortcuts()
  useTheme()
  useGlobalEvents()

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 bg-[var(--color-page-bg)]">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
      <Toaster position="top-center" />
    </div>
  )
}
