import { useState, useRef, useCallback, type KeyboardEvent } from 'react'
import { Send, Square } from 'lucide-react'
import { useProviders, useModels } from '@/hooks/use-providers'
import { useUpdateSessionModel } from '@/hooks/use-sessions'
import { Button } from '@/components/ui/Button'
import { Textarea, Select } from '@/components/ui/Input'
import { useToastStore } from '@/stores/toast-store'

interface InputBarProps {
  isStreaming: boolean
  disabled?: boolean
  sessionId?: string
  providerId?: string
  modelName?: string
  onSubmit: (content: string) => void
  onCancel: () => void
}

export function InputBar({ isStreaming, disabled, sessionId, providerId, modelName, onSubmit, onCancel }: InputBarProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { data: providers = [] } = useProviders()
  const { data: models = [] } = useModels(providerId)
  const updateSessionModel = useUpdateSessionModel()
  const [switching, setSwitching] = useState(false)

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

  const handleProviderChange = (newProviderId: string) => {
    if (!sessionId) return
    setSwitching(true)
    const firstModel = models.length > 0 ? models[0].name : ''
    updateSessionModel.mutate(
      { sessionId, data: { provider_id: newProviderId, model_name: firstModel } },
      {
        onError: () => {
          useToastStore.getState().addToast('error', '切换模型失败')
        },
        onSettled: () => setSwitching(false),
      }
    )
  }

  const handleModelChange = (newModelName: string) => {
    if (!sessionId || !providerId) return
    setSwitching(true)
    updateSessionModel.mutate(
      { sessionId, data: { provider_id: providerId, model_name: newModelName } },
      {
        onError: () => {
          useToastStore.getState().addToast('error', '切换模型失败')
        },
        onSettled: () => setSwitching(false),
      }
    )
  }

  return (
    <div className="border-t border-[var(--color-border)] p-4 shrink-0">
      <div className="max-w-[800px] mx-auto flex gap-2 items-end">
        {sessionId && (
          <div className="flex flex-col gap-1">
            <Select
              value={providerId ?? ''}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={isStreaming || switching}
              inputSize="sm"
              className="min-w-[100px]"
            >
              <option value="" disabled>提供商</option>
              {providers.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </Select>
            <Select
              value={modelName ?? ''}
              onChange={(e) => handleModelChange(e.target.value)}
              disabled={!providerId || isStreaming || switching}
              inputSize="sm"
              className="min-w-[100px]"
            >
              <option value="" disabled>模型</option>
              {models.map((m) => (
                <option key={m.id} value={m.name}>{m.name}</option>
              ))}
            </Select>
          </div>
        )}
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
