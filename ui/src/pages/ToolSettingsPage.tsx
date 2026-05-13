import { useState } from 'react'
import { Wrench, Settings2 } from 'lucide-react'

interface Tool {
  id: string
  name: string
  description: string
  enabled: boolean
}

const mockTools: Tool[] = [
  { id: '1', name: 'read_file', description: '读取文件内容', enabled: true },
  { id: '2', name: 'write_file', description: '写入文件内容', enabled: true },
  { id: '3', name: 'bash', description: '执行 shell 命令', enabled: false },
]

export function ToolSettingsPage() {
  const [tools, setTools] = useState<Tool[]>(mockTools)

  const toggleTool = (id: string) => {
    setTools((prev) =>
      prev.map((t) => (t.id === id ? { ...t, enabled: !t.enabled } : t))
    )
  }

  return (
    <div className="p-6 max-w-[720px]">
      <p className="text-sm text-[var(--color-text-secondary)] mb-6">
        管理可用工具及其配置
      </p>

      <div className="space-y-3">
        {tools.map((tool) => (
          <div
            key={tool.id}
            className="flex items-center gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4"
          >
            <div className="w-8 h-8 rounded-md bg-[var(--color-secondary-bg)] flex items-center justify-center shrink-0">
              <Wrench size={16} className="text-[var(--color-text-secondary)]" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
                {tool.name}
              </h3>
              <p className="text-xs text-[var(--color-text-placeholder)] truncate">
                {tool.description}
              </p>
            </div>
            <button
              onClick={() => toggleTool(tool.id)}
              className="p-1.5 rounded-md text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)] transition-colors duration-150"
              aria-label="配置工具"
            >
              <Settings2 size={14} />
            </button>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={tool.enabled}
                onChange={() => toggleTool(tool.id)}
                className="sr-only peer"
                aria-label={`${tool.enabled ? '禁用' : '启用'} ${tool.name}`}
              />
              <div className="w-9 h-5 rounded-full bg-[var(--color-text-disabled)] peer-checked:bg-[var(--color-brand)] after:content-[''] after:absolute after:top-0.5 after:start-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full" />
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}
