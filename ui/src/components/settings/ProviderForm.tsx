import { useForm, useFieldArray } from 'react-hook-form'
import { z } from 'zod/v4'
import { zodResolver } from '@hookform/resolvers/zod'
import { X } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const headerSchema = z.object({
  key: z.string(),
  value: z.string(),
})

const providerFormSchema = z.object({
  name: z.string().min(1, '名称不能为空'),
  base_url: z.string().min(1, 'Base URL 不能为空').url('请输入有效的 URL'),
  api_key: z.string(),
  headers: z.array(headerSchema),
})

type ProviderFormValues = z.infer<typeof providerFormSchema>

interface ProviderFormProps {
  isOpen: boolean
  initialData?: {
    name?: string
    base_url?: string
    extra_headers?: Record<string, string>
  }
  onSave: (data: { name: string; base_url: string; api_key: string; extra_headers: Record<string, string> }) => Promise<void>
  onCancel: () => void
  title: string
}

export function ProviderForm({ isOpen, initialData, onSave, onCancel, title }: ProviderFormProps) {
  const isEdit = !!initialData?.name

  const initialHeaders = initialData?.extra_headers
    ? Object.entries(initialData.extra_headers).map(([key, value]) => ({ key, value }))
    : []

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProviderFormValues>({
    resolver: zodResolver(providerFormSchema),
    defaultValues: {
      name: initialData?.name ?? '',
      base_url: initialData?.base_url ?? '',
      api_key: '',
      headers: initialHeaders,
    },
  })

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'headers',
  })

  const onSubmit = async (values: ProviderFormValues) => {
    const extra_headers: Record<string, string> = {}
    for (const h of values.headers) {
      if (h.key.trim()) {
        extra_headers[h.key.trim()] = h.value
      }
    }
    await onSave({
      name: values.name.trim(),
      base_url: values.base_url.trim(),
      api_key: values.api_key,
      extra_headers,
    })
  }

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title={title} size="lg">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label htmlFor="provider-name" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            名称 <span className="text-[var(--color-error)]">*</span>
          </label>
          <Input
            id="provider-name"
            type="text"
            placeholder="例如: SiliconFlow"
            {...register('name')}
          />
          {errors.name && (
            <p className="text-xs text-[var(--color-error)] mt-1">{errors.name.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="provider-base-url" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            Base URL <span className="text-[var(--color-error)]">*</span>
          </label>
          <Input
            id="provider-base-url"
            type="text"
            placeholder="https://api.openai.com/v1"
            {...register('base_url')}
          />
          {errors.base_url && (
            <p className="text-xs text-[var(--color-error)] mt-1">{errors.base_url.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="provider-api-key" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            API Key {!isEdit && <span className="text-[var(--color-error)]">*</span>}
            {isEdit && <span className="text-[var(--color-text-placeholder)]">(留空则不修改)</span>}
          </label>
          <Input
            id="provider-api-key"
            type="password"
            placeholder={isEdit ? '留空以保留现有密钥' : 'sk-...'}
            {...register('api_key', isEdit ? {} : { required: 'API Key 不能为空' })}
          />
          {errors.api_key && (
            <p className="text-xs text-[var(--color-error)] mt-1">{errors.api_key.message}</p>
          )}
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
              onClick={() => append({ key: '', value: '' })}
            >
              + 添加
            </Button>
          </div>
          <div className="space-y-2">
            {fields.map((field, i) => (
              <div key={field.id} className="flex gap-2 items-center">
                <Input
                  type="text"
                  placeholder="Header"
                  inputSize="sm"
                  className="flex-1"
                  {...register(`headers.${i}.key`)}
                />
                <Input
                  type="text"
                  placeholder="Value"
                  inputSize="sm"
                  className="flex-1"
                  {...register(`headers.${i}.value`)}
                />
                <Button
                  type="button"
                  variant="icon"
                  onClick={() => remove(i)}
                  aria-label="删除请求头"
                >
                  <X size={14} />
                </Button>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="ghost" onClick={onCancel}>取消</Button>
          <Button
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? '保存中...' : '保存'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
