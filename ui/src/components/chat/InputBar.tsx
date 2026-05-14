import { useState, useRef, useCallback, type KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Input'

interface InputBarProps {
  isStreaming: boolean
  disabled?: boolean
  onSubmit: (content: string) => void
  onCancel: () => void
}

export function InputBar({ isStreaming, disabled, onSubmit, onCancel }: InputBarProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [])

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || isStreaming || disabled) return
    onSubmit(trimmed)
    setValue('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t border-[var(--color-border)] p-4 shrink-0">
      <div className="max-w-[800px] mx-auto flex gap-2 items-end">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            adjustHeight()
          }}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          disabled={disabled}
          className="flex-1"
          aria-label="消息输入框"
        />
        {isStreaming ? (
          <Button
            variant="danger"
            onClick={onCancel}
            aria-label="取消生成"
          >
            <Square size={16} />
            取消
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={!value.trim() || disabled}
            aria-label="发送消息"
          >
            <Send size={16} />
            发送
          </Button>
        )}
      </div>
    </div>
  )
}
