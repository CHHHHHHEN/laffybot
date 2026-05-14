import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Wrench } from 'lucide-react'
import { listTools, enableTool, disableTool, type ToolInfoWithStatus } from '@/lib/api'

export function ToolSettingsPage() {
  const queryClient = useQueryClient()
  const { data: tools = [], isLoading } = useQuery({
    queryKey: ['tools'],
    queryFn: () => listTools(),
  })

  const toggleMutation = useMutation({
    mutationFn: async (tool: ToolInfoWithStatus) => {
      if (tool.enabled) {
        await disableTool(tool.name)
      } else {
        await enableTool(tool.name)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tools'] })
    },
  })

  return (
    <div className="p-6 max-w-[720px]">
      <p className="text-sm text-[var(--color-text-secondary)] mb-6">
        管理可用工具及其配置
      </p>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <p className="text-sm text-[var(--color-text-placeholder)]">加载中...</p>
        </div>
      ) : tools.length === 0 ? (
        <p className="text-sm text-[var(--color-text-placeholder)]">暂无可用工具</p>
      ) : (
        <div className="space-y-3">
          {tools.map((tool: ToolInfoWithStatus) => (
            <div
              key={tool.name}
              className="flex items-center gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4"
            >
              <div className="w-8 h-8 rounded-md bg-[var(--color-secondary-bg)] flex items-center justify-center shrink-0">
                <Wrench size={16} className="text-[var(--color-text-secondary)]" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
                  {tool.name}
                  {tool.read_only && (
                    <span className="ml-2 text-xs text-[var(--color-text-placeholder)]">(只读)</span>
                  )}
                  {!tool.enabled && (
                    <span className="ml-2 inline-flex items-center rounded bg-[var(--color-error)] px-1.5 py-0.5 text-xs text-white">
                      已禁用
                    </span>
                  )}
                </h3>
                <p className="text-xs text-[var(--color-text-placeholder)] truncate">
                  {tool.description}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={tool.enabled}
                aria-label={`${tool.enabled ? '禁用' : '启用'} ${tool.name}`}
                disabled={toggleMutation.isPending}
                onClick={() => toggleMutation.mutate(tool)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                  tool.enabled
                    ? 'bg-[var(--color-brand)]'
                    : 'bg-[var(--color-border)]'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm ring-0 transition-transform duration-200 ${
                    tool.enabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
