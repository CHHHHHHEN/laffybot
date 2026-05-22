import { useState } from 'react'
import { AlertTriangle, Bug, ChevronDown, ChevronRight, Clock, RefreshCw, FileWarning, Hash } from 'lucide-react'
import { useErrorLogs } from '@/hooks/use-error-logs'
import { Button } from '@/components/ui/Button'
import { format } from 'date-fns'

function LevelBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    CRITICAL: 'bg-red-600 text-white',
    ERROR: 'bg-red-500/20 text-red-400',
    WARNING: 'bg-yellow-500/20 text-yellow-400',
  }
  const cls = colors[level] ?? 'bg-gray-500/20 text-gray-400'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold ${cls}`}>
      {level}
    </span>
  )
}

function SourceTag({ source }: { source: string }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[var(--color-secondary-bg)] text-xs font-mono text-[var(--color-text-secondary)]">
      <Bug size={10} />
      {source}
    </span>
  )
}

function ErrorDetailCard({
  record,
  defaultOpen,
}: {
  record: {
    timestamp: string
    level: string
    source: string
    message: string
    session_id?: string
    request_id?: string
    error_code?: string
    traceback?: string
  }
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const time = record.timestamp ? format(new Date(record.timestamp), 'HH:mm:ss') : '--'

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-hover-bg)] transition-colors"
      >
        <div className="shrink-0">
          {record.level === 'CRITICAL' ? (
            <FileWarning size={16} className="text-red-500" />
          ) : (
            <AlertTriangle size={16} className="text-yellow-500" />
          )}
        </div>

        <div className="flex items-center gap-2 text-xs font-mono text-[var(--color-text-placeholder)] min-w-[60px]">
          <Clock size={10} />
          {time}
        </div>

        <LevelBadge level={record.level} />

        {record.error_code && (
          <span className="text-xs font-mono text-[var(--color-text-secondary)]">
            {record.error_code}
          </span>
        )}

        <div className="flex-1 min-w-0">
          <p className="text-sm text-[var(--color-text-primary)] truncate">
            {record.message}
          </p>
        </div>

        <div className="shrink-0 text-[var(--color-text-secondary)]">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </button>

      {/* Expanded details */}
      {open && (
        <div className="border-t border-[var(--color-border)] px-4 py-3 space-y-3">
          <SourceTag source={record.source} />

          {record.session_id && (
            <div className="flex items-center gap-2 text-xs font-mono text-[var(--color-text-secondary)]">
              <Hash size={10} />
              session: {record.session_id}
              {record.request_id && <span className="ml-3">request: {record.request_id}</span>}
            </div>
          )}

          {record.error_code && (
            <div className="text-xs font-mono text-[var(--color-text-secondary)]">
              code: {record.error_code}
            </div>
          )}

          {record.traceback && (
            <div className="mt-2">
              <p className="text-xs font-medium text-[var(--color-text-secondary)] mb-1">Traceback:</p>
              <pre className="text-xs font-mono text-red-400 bg-red-950/20 rounded-md p-3 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-all">
                {record.traceback}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ErrorLogPage() {
  const [limit, setLimit] = useState(50)
  const { data, isLoading, isError, refetch } = useErrorLogs(limit)

  return (
    <div className="p-6 max-w-[960px]">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
          <AlertTriangle size={20} className="text-red-400" />
        </div>
        <div className="flex-1">
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">错误日志</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            查看系统运行时记录的错误和异常
          </p>
        </div>
        <Button
          variant="ghost"
          onClick={() => refetch()}
          disabled={isLoading}
        >
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          刷新
        </Button>
      </div>

      {/* Stats bar */}
      {data && (
        <div className="flex items-center gap-4 mb-4 text-xs text-[var(--color-text-secondary)]">
          <span>总计 {data.total} 条记录</span>
          <span>显示最近 {data.errors.length} 条</span>
        </div>
      )}

      {/* Loading state */}
      {isLoading && !data && (
        <div className="text-center py-12">
          <RefreshCw size={20} className="animate-spin mx-auto mb-3 text-[var(--color-text-secondary)]" />
          <p className="text-sm text-[var(--color-text-placeholder)]">加载错误日志...</p>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="text-center py-12">
          <p className="text-sm text-red-400">加载失败，请稍后重试</p>
        </div>
      )}

      {/* Empty state */}
      {data && data.errors.length === 0 && (
        <div className="text-center py-16">
          <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-4">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-green-500">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </div>
          <p className="text-sm font-medium text-[var(--color-text-primary)] mb-1">一切正常</p>
          <p className="text-sm text-[var(--color-text-placeholder)]">暂无错误记录</p>
        </div>
      )}

      {/* Error list */}
      {data && data.errors.length > 0 && (
        <div className="space-y-2 mt-4">
          {data.errors.map((record, i) => (
            <ErrorDetailCard
              key={`${record.timestamp}-${i}`}
              record={record}
              defaultOpen={i === 0 && record.level === 'CRITICAL'}
            />
          ))}
        </div>
      )}

      {/* Load more */}
      {data && data.total > limit && (
        <div className="text-center mt-4">
          <Button variant="ghost" onClick={() => setLimit(limit + 50)}>
            加载更多
          </Button>
        </div>
      )}
    </div>
  )
}
