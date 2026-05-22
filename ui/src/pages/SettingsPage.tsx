import { Outlet, NavLink } from 'react-router-dom'

const tabs = [
  { to: '/settings/provider', label: '提供商配置' },
  { to: '/settings/mcp', label: 'MCP 服务' },
  { to: '/settings/tools', label: '工具管理' },
  { to: '/settings/advanced', label: '高级设置' },
  { to: '/settings/memories', label: '记忆管理' },
  { to: '/settings/skills', label: 'SKILL 设置' },
  { to: '/settings/errors', label: '错误日志' },
]

export function SettingsPage() {
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 h-14 flex items-center border-b border-[var(--color-border)]">
        <h2 className="text-h2 font-semibold text-[var(--color-text-primary)]">设置</h2>
      </div>
      <div className="flex border-b border-[var(--color-border)] px-6">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `px-4 py-3 text-sm border-b-2 transition-colors duration-150 ${
                isActive
                  ? 'border-[var(--color-brand)] text-[var(--color-brand)] font-medium'
                  : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  )
}
