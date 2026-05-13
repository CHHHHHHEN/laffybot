import { NavLink } from 'react-router-dom'
import { MessageSquare, Settings } from 'lucide-react'

const links = [
  { to: '/chat', label: '聊天', icon: MessageSquare },
  { to: '/settings', label: '设置', icon: Settings },
]

export function NavLinks() {
  return (
    <nav className="flex flex-col gap-1 px-3 py-4">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.to === '/chat'}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 ${
              isActive
                ? 'bg-[var(--color-hover-bg)] text-[var(--color-text-primary)] font-medium'
                : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-hover-bg)] hover:text-[var(--color-text-primary)]'
            }`
          }
        >
          <link.icon size={20} />
          <span>link.label</span>
        </NavLink>
      ))}
    </nav>
  )
}
