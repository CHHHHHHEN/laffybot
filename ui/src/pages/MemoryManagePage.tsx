import { useState } from 'react'
import { Loader2, Search, Trash2, MessageSquare, ChevronLeft, Database, Layers, RefreshCw } from 'lucide-react'
import { useMemories, useMemory, useMemorySource, useDeleteMemory, useConsolidationStatus, useConsolidatedMemory, useTriggerConsolidation } from '@/hooks/use-memories'
import { Button } from '@/components/ui/Button'
import { useToastStore } from '@/stores/toast-store'

function ConsolidationSection() {
  const { data: status, isLoading: statusLoading } = useConsolidationStatus()
  const { data: consolidated, isLoading: consolidatedLoading } = useConsolidatedMemory()
  const triggerConsolidation = useTriggerConsolidation()
  const [showContent, setShowContent] = useState(false)
  const [isTriggering, setIsTriggering] = useState(false)

  if (statusLoading) return null

  const handleTrigger = async () => {
    setIsTriggering(true)
    try {
      const result = await triggerConsolidation.mutateAsync()
      useToastStore.getState().addToast(
        result.performed ? 'success' : 'info',
        result.performed ? '整合完成' : result.message
      )
    } catch {
      useToastStore.getState().addToast('error', '触发整合失败')
    } finally {
      setIsTriggering(false)
    }
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-4">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-8 h-8 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <Layers size={16} className="text-[var(--color-text-secondary)]" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-medium text-[var(--color-text-primary)]">记忆整合</h4>
          <p className="text-xs text-[var(--color-text-secondary)]">
            将多条原始记忆合并为一条精简的整合记忆
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleTrigger}
          disabled={isTriggering}
          title="手动触发整合"
        >
          {isTriggering ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          整合
        </Button>
      </div>

      {status && (
        <div className="grid grid-cols-3 gap-3 text-xs mb-3">
          <div className="p-2 rounded bg-[var(--color-secondary-bg)]">
            <span className="text-[var(--color-text-secondary)]">原始记忆</span>
            <p className="text-[var(--color-text-primary)] font-medium">{status.total_raw_memories}</p>
          </div>
          <div className="p-2 rounded bg-[var(--color-secondary-bg)]">
            <span className="text-[var(--color-text-secondary)]">已整合</span>
            <p className="text-[var(--color-text-primary)] font-medium">{status.consolidated_source_count}</p>
          </div>
          <div className="p-2 rounded bg-[var(--color-secondary-bg)]">
            <span className="text-[var(--color-text-secondary)]">未整合</span>
            <p className="text-[var(--color-text-primary)] font-medium">{status.unconsolidated_count}</p>
          </div>
        </div>
      )}

      {status?.has_consolidated_memory && (
        <>
          <button
            onClick={() => setShowContent(!showContent)}
            className="text-xs text-[var(--color-brand)] hover:underline mb-2"
          >
            {showContent ? '隐藏整合内容' : '查看整合内容'}
          </button>
          {showContent && (
            <div className="p-3 rounded bg-[var(--color-secondary-bg)] text-xs text-[var(--color-text-primary)] whitespace-pre-wrap max-h-48 overflow-y-auto">
              {consolidatedLoading
                ? <Loader2 size={12} className="animate-spin inline" />
                : consolidated?.content || '暂无内容'}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function MemoryDetailView({ memoryId, onBack }: { memoryId: string; onBack: () => void }) {
  const { data: memory, isLoading } = useMemory(memoryId)
  const { data: source, isLoading: sourceLoading } = useMemorySource(memoryId)
  const [showSource, setShowSource] = useState(false)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
      </div>
    )
  }

  if (!memory) {
    return <div className="text-center py-12 text-[var(--color-text-secondary)]">记忆未找到</div>
  }

  return (
    <div>
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] mb-4"
      >
        <ChevronLeft size={16} />
        返回列表
      </button>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-4">
        <div className="text-xs text-[var(--color-text-secondary)] mb-2">
          来源会话：<span className="font-mono">{memory.session_title || memory.session_id}</span>
        </div>
        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {memory.tags.map((tag) => (
              <span key={tag} className="px-2 py-0.5 text-xs rounded-full bg-[var(--color-secondary-bg)] text-[var(--color-text-secondary)]">
                #{tag}
              </span>
            ))}
          </div>
        )}
        <div className="text-sm text-[var(--color-text-primary)] whitespace-pre-wrap">
          {memory.content}
        </div>
        <div className="mt-3 text-xs text-[var(--color-text-secondary)]">
          创建于 {new Date(memory.created_at).toLocaleString()}
        </div>
      </div>

      <Button
        variant="ghost"
        onClick={() => setShowSource(!showSource)}
        className="mb-4"
      >
        <MessageSquare size={14} />
        {showSource ? '隐藏来源消息' : '查看来源消息'}
      </Button>

      {showSource && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4">
          <h4 className="text-sm font-medium text-[var(--color-text-primary)] mb-3">
            来源会话消息
          </h4>
          {sourceLoading ? (
            <Loader2 size={16} className="animate-spin text-[var(--color-text-secondary)]" />
          ) : source?.messages ? (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {source.messages.map((msg, i) => (
                <div key={i} className="text-sm">
                  <span className="font-medium text-[var(--color-text-secondary)]">
                    {msg.role === 'user' ? '用户' : msg.role === 'assistant' ? '助手' : msg.role}：
                  </span>
                  <span className="text-[var(--color-text-primary)]">
                    {msg.content?.slice(0, 200)}{msg.content?.length > 200 ? '...' : ''}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

export function MemoryManagePage() {
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null)
  const pageSize = 20

  const { data, isLoading } = useMemories({ limit: pageSize, offset: page * pageSize, search: search || undefined })
  const deleteMemory = useDeleteMemory()

  const handleDelete = async (memoryId: string) => {
    try {
      await deleteMemory.mutateAsync(memoryId)
      useToastStore.getState().addToast('success', '记忆已删除')
    } catch {
      useToastStore.getState().addToast('error', '删除失败')
    }
  }

  if (selectedMemoryId) {
    return (
      <div className="p-6 max-w-[720px]">
        <MemoryDetailView memoryId={selectedMemoryId} onBack={() => setSelectedMemoryId(null)} />
      </div>
    )
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  return (
    <div className="p-6 max-w-[720px]">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <Database size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">记忆管理</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            查看和管理从会话中提取的结构化记忆
          </p>
        </div>
      </div>

      {/* Consolidation Status */}
      <ConsolidationSection />

      {/* Search */}
      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]" />
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0) }}
          placeholder="搜索记忆内容..."
          className="w-full pl-9 pr-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
        />
      </div>

      {/* Memory List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
        </div>
      ) : data?.memories.length === 0 ? (
        <div className="text-center py-12 text-sm text-[var(--color-text-placeholder)]">
          {search ? '没有匹配的记忆' : '暂无记忆，完成会话后将自动生成'}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {data?.memories.map((memory) => (
              <div
                key={memory.memory_id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 cursor-pointer hover:border-[var(--color-brand)] transition-colors"
                onClick={() => setSelectedMemoryId(memory.memory_id)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-[var(--color-text-secondary)] mb-1">
                      {memory.session_title || memory.session_id.slice(0, 8)}
                    </div>
                    <div className="text-sm text-[var(--color-text-primary)] line-clamp-3">
                      {memory.content}
                    </div>
                    {memory.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {memory.tags.map((tag) => (
                          <span key={tag} className="px-1.5 py-0.5 text-xs rounded bg-[var(--color-secondary-bg)] text-[var(--color-text-secondary)]">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(memory.memory_id) }}
                    className="shrink-0 p-1.5 rounded hover:bg-[var(--color-secondary-bg)] text-[var(--color-text-secondary)] hover:text-red-500 transition-colors"
                    title="删除"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                <div className="mt-2 text-xs text-[var(--color-text-secondary)]">
                  {new Date(memory.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-4">
              <Button
                variant="ghost"
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
              >
                上一页
              </Button>
              <span className="text-sm text-[var(--color-text-secondary)]">
                {page + 1} / {totalPages}
              </span>
              <Button
                variant="ghost"
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
              >
                下一页
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
