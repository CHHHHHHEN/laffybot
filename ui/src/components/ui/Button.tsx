import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type ButtonVariant = 'brand' | 'ghost' | 'danger' | 'icon' | 'link'
type ButtonSize = 'sm' | 'md' | 'icon'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

const variantClasses: Record<ButtonVariant, string> = {
  brand:
    'bg-[var(--color-brand)] text-white font-medium hover:bg-[var(--color-brand-hover)] disabled:opacity-50 disabled:cursor-not-allowed',
  ghost:
    'border border-[var(--color-border)] text-[var(--color-text-primary)] hover:bg-[var(--color-hover-bg)]',
  danger:
    'bg-[var(--color-error)] text-white font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed',
  icon: 'text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)]',
  link: 'text-[var(--color-brand)] hover:text-[var(--color-brand-hover)]',
}

const sizeClasses: Record<ButtonSize, string> = {
  md: 'px-4 py-2 text-sm rounded-md',
  sm: 'px-2.5 py-1.5 text-xs rounded-md',
  icon: 'p-1.5 rounded-md',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'brand', size = 'md', className = '', children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn('inline-flex items-center justify-center gap-2 transition-colors duration-150', variantClasses[variant], sizeClasses[size], className)}
        {...props}
      >
        {children}
      </button>
    )
  }
)
Button.displayName = 'Button'
