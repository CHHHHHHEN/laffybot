import { useForm, useFieldArray } from 'react-hook-form'
import { X } from 'lucide-react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Input, Select } from '@/components/ui/Input'

interface McpServerFormValues {
  name: string
  transport_type: string
  command: string
  url: string
  args: string
  tool_timeout: string
  startup_timeout: string
  env: { key: string; value: string }[]
  headers: { key: string; value: string }[]
}

interface McpServerFormProps {
  isOpen: boolean
  initialData?: {
    name?: string
    transport_type?: string
    command?: string
    args?: string[]
    url?: string
    env?: Record<string, string>
    headers?: Record<string, string>
    tool_timeout?: number
    startup_timeout?: number
  }
  onSave: (data: {
    name: string
    transport_type?: string
    command?: string
    args?: string[]
    url?: string
    env?: Record<string, string>
    headers?: Record<string, string>
    tool_timeout?: number
    startup_timeout?: number
  }) => Promise<void>
  onCancel: () => void
  title: string
}

export function McpServerForm({ isOpen, initialData, onSave, onCancel, title }: McpServerFormProps) {
  const initialEnv = initialData?.env
    ? Object.entries(initialData.env).map(([key, value]) => ({ key, value }))
    : []
  const initialHeaders = initialData?.headers
    ? Object.entries(initialData.headers).map(([key, value]) => ({ key, value }))
    : []

  const {
    register,
    control,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<McpServerFormValues>({
    defaultValues: {
      name: initialData?.name ?? '',
      transport_type: initialData?.transport_type ?? 'stdio',
      command: initialData?.command ?? '',
      url: initialData?.url ?? '',
      args: initialData?.args?.join(' ') ?? '',
      tool_timeout: String(initialData?.tool_timeout ?? 30),
      startup_timeout: String(initialData?.startup_timeout ?? 30),
      env: initialEnv,
      headers: initialHeaders,
    },
  })

  const { fields: envFields, append: appendEnv, remove: removeEnv } = useFieldArray({
    control,
    name: 'env',
  })

  const { fields: headerFields, append: appendHeader, remove: removeHeader } = useFieldArray({
    control,
    name: 'headers',
  })

  const transportType = watch('transport_type')

  const onSubmit = async (values: McpServerFormValues) => {
    const env: Record<string, string> = {}
    for (const e of values.env) {
      if (e.key.trim()) {
        env[e.key.trim()] = e.value
      }
    }
    const headers: Record<string, string> = {}
    for (const h of values.headers) {
      if (h.key.trim()) {
        headers[h.key.trim()] = h.value
      }
    }
    const args = values.args
      ? values.args.split(' ').filter(Boolean)
      : undefined
    const toolTimeout = parseInt(values.tool_timeout, 10) || 30
    const startupTimeout = parseInt(values.startup_timeout, 10) || 30

    await onSave({
      name: values.name.trim(),
      transport_type: values.transport_type,
      command: values.command.trim() || undefined,
      args,
      url: values.url.trim() || undefined,
      env: Object.keys(env).length > 0 ? env : undefined,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      tool_timeout: toolTimeout,
      startup_timeout: startupTimeout,
    })
  }

  return (
    <Modal isOpen={isOpen} onClose={onCancel} title={title} size="lg">
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label htmlFor="mcp-name" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            名称 <span className="text-[var(--color-error)]">*</span>
          </label>
          <Input
            id="mcp-name"
            type="text"
            placeholder="例如: filesystem"
            {...register('name')}
          />
          {errors.name && (
            <p className="text-xs text-[var(--color-error)] mt-1">{errors.name.message}</p>
          )}
        </div>

        <div>
          <label htmlFor="mcp-transport" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
            传输类型 <span className="text-[var(--color-error)]">*</span>
          </label>
          <Select id="mcp-transport" {...register('transport_type')}>
            <option value="stdio">Stdio (子进程)</option>
            <option value="sse">SSE (HTTP + Server-Sent Events)</option>
            <option value="streamableHttp">Streamable HTTP</option>
          </Select>
        </div>

        {(transportType === 'stdio') && (
          <>
            <div>
              <label htmlFor="mcp-command" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                命令 <span className="text-[var(--color-error)]">*</span>
              </label>
              <Input
                id="mcp-command"
                type="text"
                placeholder="npx -y @modelcontextprotocol/server-filesystem"
                {...register('command')}
              />
            </div>
            <div>
              <label htmlFor="mcp-args" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
                参数 <span className="text-[var(--color-text-placeholder)]">(可选，空格分隔)</span>
              </label>
              <Input
                id="mcp-args"
                type="text"
                placeholder="/path/to/allowed/dir"
                {...register('args')}
              />
            </div>
          </>
        )}

        {(transportType === 'sse' || transportType === 'streamableHttp') && (
          <div>
            <label htmlFor="mcp-url" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              URL <span className="text-[var(--color-error)]">*</span>
            </label>
            <Input
              id="mcp-url"
              type="text"
              placeholder="http://localhost:3001/sse"
              {...register('url')}
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="mcp-tool-timeout" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              工具超时 (秒)
            </label>
            <Input
              id="mcp-tool-timeout"
              type="number"
              {...register('tool_timeout')}
            />
          </div>
          <div>
            <label htmlFor="mcp-startup-timeout" className="block text-sm font-medium text-[var(--color-text-primary)] mb-1">
              连接超时 (秒)
            </label>
            <Input
              id="mcp-startup-timeout"
              type="number"
              {...register('startup_timeout')}
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-[var(--color-text-primary)]">
              环境变量 <span className="text-[var(--color-text-placeholder)]">(可选)</span>
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => appendEnv({ key: '', value: '' })}
            >
              + 添加
            </Button>
          </div>
          <div className="space-y-2">
            {envFields.map((field, i) => (
              <div key={field.id} className="flex gap-2 items-center">
                <Input
                  type="text"
                  placeholder="KEY"
                  inputSize="sm"
                  className="flex-1"
                  {...register(`env.${i}.key`)}
                />
                <Input
                  type="text"
                  placeholder="VALUE"
                  inputSize="sm"
                  className="flex-1"
                  {...register(`env.${i}.value`)}
                />
                <Button
                  type="button"
                  variant="icon"
                  onClick={() => removeEnv(i)}
                  aria-label="删除环境变量"
                >
                  <X size={14} />
                </Button>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-[var(--color-text-primary)]">
              请求头 <span className="text-[var(--color-text-placeholder)]">(可选)</span>
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              onClick={() => appendHeader({ key: '', value: '' })}
            >
              + 添加
            </Button>
          </div>
          <div className="space-y-2">
            {headerFields.map((field, i) => (
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
                  onClick={() => removeHeader(i)}
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
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '保存中...' : '保存'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
