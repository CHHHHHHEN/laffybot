import { useState, useRef } from 'react'
import { X } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

interface ProviderFormData {
  name: string
  base_url: string
  api_key: string
  extra_headers: Record<string, string>
}

interface ProviderFormProps {
  isOpen: boolean
  initialData?: Partial<ProviderFormData>
  onSave: (data: ProviderFormData) => Promise<void>
  onCancel: () => void
  title: string
}

export function ProviderForm({ isOpen, initialData, onSave, onCancel, title }: ProviderFormProps) {
  const [name, setName] = useState(initialData?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(initialData?.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [headerKeys, setHeaderKeys] = useState<string[]>([])
  const [headerValues, setHeaderValues] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const isEdit = !!initialData?.name

  const addHeader = () => {
    setHeaderKeys([...headerKeys, ''])
    setHeaderValues([...headerValues, ''])
  }

  const updateHeaderKey = (index: number, value: string) => {
    const next = [...headerKeys]
    next[index] = value
    setHeaderKeys(next)
  }

  const updateHeaderValue = (index: number, value: string) => {
    const next = [...headerValues]
    next[index] = value
    setHeaderValues(next)
  }

  const removeHeader = (index: number) => {
    setHeaderKeys(headerKeys.filter((_, i) => i !== index))
    setHeaderValues(headerValues.filter((_, i) => i !== index))
  }

  const getExtraHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {}
    for (let i = 0; i < headerKeys.length; i++) {
      if (headerKeys[i].trim()) {
        headers[headerKeys[i].trim()] = headerValues[i]
      }
    }
    return headers
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !baseUrl.trim()) return
    if (!isEdit && !apiKey.trim()) return

    setSaving(true)
    setError(null)
    try {
      await onSave({
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey,
        extra_headers: getExtraHeaders(),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title={title} size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="provider-name" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            名称 <span className="text-[var(--color-error)]">*</span>
          </label>
          <Input
            ref={nameRef}
            id="provider-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如: SiliconFlow"
            required
          />
        </div>

        <div>
          <label htmlFor="provider-base-url" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            Base URL <span className="text-[var(--color-error)]">*</span>
          </label>
          <Input
            id="provider-base-url"
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            required
          />
        </div>

        <div>
          <label htmlFor="provider-api-key" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            API Key {!isEdit && <span className="text-[var(--color-error)]">*</span>}
            {isEdit && <span className="text-[var(--color-text-placeholder)]">(留空则不修改)</span>}
          </label>
          <Input
            id="provider-api-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={isEdit ? '留空以保留现有密钥' : 'sk-...'}
            required={!isEdit}
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-[var(--color-text-primary)]">
              额外请求头 <span className="text-[var(--color-text-placeholder)]">(可选)</span>
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={addHeader}
            >
              + 添加
            </Button>
          </div>
          <div className="space-y-2">
            {headerKeys.map((key, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  type="text"
                  value={key}
                  onChange={(e) => updateHeaderKey(i, e.target.value)}
                  placeholder="Header"
                  inputSize="sm"
                  className="flex-1"
                />
                <Input
                  type="text"
                  value={headerValues[i]}
                  onChange={(e) => updateHeaderValue(i, e.target.value)}
                  placeholder="Value"
                  inputSize="sm"
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="icon"
                  onClick={() => removeHeader(i)}
                  aria-label="删除请求头"
                >
                  <X size={14} />
                </Button>
              </div>
            ))}
          </div>
        </div>

        {error && (
          <p className="text-sm text-[var(--color-error)]">{error}</p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" onClick={onCancel}>取消</Button>
          <Button
            type="submit"
            disabled={saving || !name.trim() || !baseUrl.trim() || (!isEdit && !apiKey.trim())}
          >
            {saving ? '保存中...' : '保存'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
