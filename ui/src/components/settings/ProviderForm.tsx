import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'

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
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [headerKeys, setHeaderKeys] = useState<string[]>([])
  const [headerValues, setHeaderValues] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)
  const isEdit = !!initialData?.name

  useEffect(() => {
    if (!isOpen) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onCancel])

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

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onCancel} />
      <div
        className="relative bg-[var(--color-page-bg)] rounded-lg shadow-xl w-full max-w-lg mx-4 p-6"
        role="dialog"
        aria-modal="true"
      >
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 p-1 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
          aria-label="关闭"
        >
          <X size={16} />
        </button>

        <h3 className="text-h3 font-semibold text-[var(--color-text-primary)] mb-4">{title}</h3>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="provider-name" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              名称 <span className="text-[var(--color-error)]">*</span>
            </label>
            <input
              ref={nameRef}
              id="provider-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如: SiliconFlow"
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
              required
            />
          </div>

          <div>
            <label htmlFor="provider-base-url" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              Base URL <span className="text-[var(--color-error)]">*</span>
            </label>
            <input
              id="provider-base-url"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
              required
            />
          </div>

          <div>
            <label htmlFor="provider-api-key" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              API Key {!isEdit && <span className="text-[var(--color-error)]">*</span>}
              {isEdit && <span className="text-[var(--color-text-placeholder)]">(留空则不修改)</span>}
            </label>
            <input
              id="provider-api-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={isEdit ? '留空以保留现有密钥' : 'sk-...'}
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-3 py-2 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
              required={!isEdit}
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-[var(--color-text-primary)]">
                额外请求头 <span className="text-[var(--color-text-placeholder)]">(可选)</span>
              </span>
              <button
                type="button"
                onClick={addHeader}
                className="text-xs text-[var(--color-brand)] hover:text-[var(--color-brand-hover)] transition-colors duration-150"
              >
                + 添加
              </button>
            </div>
            <div className="space-y-2">
              {headerKeys.map((key, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input
                    type="text"
                    value={key}
                    onChange={(e) => updateHeaderKey(i, e.target.value)}
                    placeholder="Header"
                    className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-2 py-1.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
                  />
                  <input
                    type="text"
                    value={headerValues[i]}
                    onChange={(e) => updateHeaderValue(i, e.target.value)}
                    placeholder="Value"
                    className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] px-2 py-1.5 text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-placeholder)] outline-none focus:border-[var(--color-brand)] transition-colors duration-150"
                  />
                  <button
                    type="button"
                    onClick={() => removeHeader(i)}
                    className="p-1 rounded text-[var(--color-text-placeholder)] hover:text-[var(--color-error)] transition-colors duration-150"
                    aria-label="删除请求头"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-sm text-[var(--color-error)]">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm rounded-md border border-[var(--color-border)] text-[var(--color-text-primary)] hover:bg-[var(--color-hover-bg)] transition-colors duration-150"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim() || !baseUrl.trim() || (!isEdit && !apiKey.trim())}
              className="px-4 py-2 text-sm rounded-md bg-[var(--color-brand)] text-white font-medium hover:bg-[var(--color-brand-hover)] transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
