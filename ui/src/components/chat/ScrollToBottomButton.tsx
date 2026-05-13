import { ChevronDown } from 'lucide-react'

interface ScrollToBottomButtonProps {
  visible: boolean
  onClick: () => void
}

export function ScrollToBottomButton({ visible, onClick }: ScrollToBottomButtonProps) {
  if (!visible) return null

  return (
    <button
      onClick={onClick}
      className="fixed bottom-20 left-1/2 -translate-x-1/2 z-[var(--z-floating-button)] flex items-center gap-1.5 rounded-full bg-[var(--color-page-bg)] border border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-text-secondary)] shadow-lg hover:bg-[var(--color-hover-bg)] transition-all duration-200 ease-out"
      aria-label="回到最新"
    >
      <ChevronDown size={16} />
      回到最新
    </button>
  )
}
