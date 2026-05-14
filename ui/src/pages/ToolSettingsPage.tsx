import { useQuery } from '@tanstack/react-query'
import { Wrench, Settings2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { listTools, type ToolInfo } from '@/lib/api'

export function ToolSettingsPage() {
  const { data: tools = [], isLoading } = useQuery({
    queryKey: ['tools'],
    queryFn: () => listTools(),
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
          {tools.map((tool: ToolInfo) => (
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
                </h3>
                <p className="text-xs text-[var(--color-text-placeholder)] truncate">
                  {tool.description}
                </p>
              </div>
              <Button
                variant="icon"
                aria-label="配置工具"
              >
                <Settings2 size={14} />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
