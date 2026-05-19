import { useState } from 'react'
import { Plus, Pencil, Trash2, Plug, Loader2, Power, PowerOff, Server } from 'lucide-react'
import * as api from '@/lib/api'
import { useMcpServers, useCreateMcpServer, useUpdateMcpServer, useDeleteMcpServer, useToggleMcpServer, useTestMcpServer } from '@/hooks/use-mcp-servers'
import { McpServerForm } from '@/components/settings/McpServerForm'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  ready: { label: '已就绪', color: 'var(--color-success)' },
  starting: { label: '连接中', color: 'var(--color-warning)' },
  failed: { label: '失败', color: 'var(--color-error)' },
  disconnected: { label: '未连接', color: 'var(--color-text-placeholder)' },
  created: { label: '已创建', color: 'var(--color-text-placeholder)' },
}

export function McpSettingsPage() {
  const { data: servers = [], isLoading } = useMcpServers()
  const createServer = useCreateMcpServer()
  const updateServer = useUpdateMcpServer()
  const deleteServer = useDeleteMcpServer()
  const toggleServer = useToggleMcpServer()
  const testServer = useTestMcpServer()

  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const handleCreate = async (data: api.MCPServerCreateRequest) => {
    await createServer.mutateAsync(data)
    setShowForm(false)
    toast.success('MCP 服务器创建成功')
  }

  const handleUpdate = async (data: api.MCPServerCreateRequest) => {
    if (!editingId) return
    await updateServer.mutateAsync({ id: editingId, data })
    setEditingId(null)
    toast.success('MCP 服务器更新成功')
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteServer.mutateAsync(id)
      toast.success('MCP 服务器已删除')
    } catch {
      toast.error('删除失败')
    }
  }

  const handleToggle = async (id: string) => {
    try {
      const result = await toggleServer.mutateAsync(id)
      toast.success(result.enabled ? '已启用' : '已禁用')
    } catch {
      toast.error('切换失败')
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testServer.mutateAsync(id)
      if (result.success) {
        toast.success(`连接成功: ${result.message}`)
      } else {
        toast.error(`连接失败: ${result.message}`)
      }
    } catch {
      toast.error('测试请求失败')
    } finally {
      setTestingId(null)
    }
  }

  const editingServer = editingId ? servers.find((s) => s.id === editingId) : undefined

  return (
    <div className="p-6 max-w-[720px]">
      <div className="flex items-center justify-between mb-6">
        <p className="text-sm text-[var(--color-text-secondary)]">
          管理 MCP (Model Context Protocol) 服务器连接
        </p>
        <Button onClick={() => setShowForm(true)} aria-label="添加 MCP 服务器">
          <Plus size={16} />
          添加服务器
        </Button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
        </div>
      ) : servers.length === 0 ? (
        <div className="text-center py-12">
          <Server size={48} className="mx-auto mb-4 text-[var(--color-text-placeholder)]" />
          <p className="text-[var(--color-text-secondary)] mb-2">暂无 MCP 服务器配置</p>
          <p className="text-sm text-[var(--color-text-placeholder)]">点击上方按钮添加你的第一个 MCP 服务器</p>
        </div>
      ) : (
        <div className="space-y-4">
          {servers.map((server) => {
            const statusInfo = STATUS_LABELS[server.connection_status] ?? STATUS_LABELS.disconnected
            return (
              <div
                key={server.id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-md bg-[var(--color-secondary-bg)] flex items-center justify-center">
                      <Server size={16} className="text-[var(--color-text-secondary)]" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
                          {server.name}
                        </h3>
                        <span
                          className="inline-flex items-center gap-1 text-xs"
                          style={{ color: statusInfo.color }}
                        >
                          <span className="w-1.5 h-1.5 rounded-full inline-block"
                            style={{ backgroundColor: statusInfo.color }} />
                          {statusInfo.label}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--color-text-placeholder)] font-mono">
                        {server.transport_type === 'stdio'
                          ? `${server.transport_type}: ${server.command ?? ''}`
                          : `${server.transport_type}: ${server.url ?? ''}`
                        }
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="icon"
                      onClick={() => handleToggle(server.id)}
                      aria-label={server.enabled ? '禁用' : '启用'}
                    >
                      {server.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                    </Button>
                    <Button
                      variant="icon"
                      onClick={() => handleTest(server.id)}
                      disabled={testingId === server.id}
                      aria-label="测试连接"
                    >
                      {testingId === server.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Plug size={14} />
                      )}
                    </Button>
                    <Button
                      variant="icon"
                      onClick={() => setEditingId(server.id)}
                      aria-label="编辑"
                    >
                      <Pencil size={14} />
                    </Button>
                    <Button
                      variant="icon"
                      onClick={() => handleDelete(server.id)}
                      aria-label="删除"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs text-[var(--color-text-placeholder)]">
                  <span>工具: {server.tool_count}</span>
                  <span>超时: {server.tool_timeout}s</span>
                  <span>启用的工具: {server.enabled_tools.includes('*') ? '全部' : `${server.enabled_tools.length} 个`}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showForm && (
        <McpServerForm
          isOpen={true}
          onSave={handleCreate}
          onCancel={() => setShowForm(false)}
          title="添加 MCP 服务器"
        />
      )}

      {editingId !== null && (
        <McpServerForm
          isOpen={true}
          initialData={editingServer ? {
            name: editingServer.name,
            transport_type: editingServer.transport_type,
            command: editingServer.command ?? undefined,
            url: editingServer.url ?? undefined,
            tool_timeout: editingServer.tool_timeout,
            startup_timeout: editingServer.startup_timeout,
          } : undefined}
          onSave={handleUpdate}
          onCancel={() => setEditingId(null)}
          title="编辑 MCP 服务器"
        />
      )}
    </div>
  )
}
