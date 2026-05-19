import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, type SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const baseClass =
  'rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed'

type InputSize = 'sm' | 'md'

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  inputSize?: InputSize
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ inputSize = 'md', className = '', ...props }, ref) => {
    const sizeClass = inputSize === 'sm' ? 'px-2 py-1.5 text-xs' : 'w-full px-3 py-2 text-sm'
    return (
      <input
        ref={ref}
        className={cn(baseClass, sizeClass, className)}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'size'> {
  inputSize?: InputSize
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ inputSize = 'md', className = '', ...props }, ref) => {
    const sizeClass = inputSize === 'sm' ? 'px-2 py-1.5 text-xs' : 'w-full px-3 py-2 text-sm'
    return (
      <textarea
        ref={ref}
        className={cn(baseClass, sizeClass, 'resize-none', className)}
        {...props}
      />
    )
  }
)
Textarea.displayName = 'Textarea'

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  inputSize?: InputSize
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ inputSize = 'md', className = '', children, ...props }, ref) => {
    const sizeClass = inputSize === 'sm' ? 'px-2 py-1.5 text-xs' : 'px-3 py-2 text-sm'
    return (
      <select
        ref={ref}
        className={cn(baseClass, sizeClass, className)}
        {...props}
      >
        {children}
      </select>
    )
  }
)
Select.displayName = 'Select'
