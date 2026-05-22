import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ChatPage } from '@/pages/ChatPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { ProviderSettingsPage } from '@/pages/ProviderSettingsPage'
import { ToolSettingsPage } from '@/pages/ToolSettingsPage'
import { AdvancedSettingsPage } from '@/pages/AdvancedSettingsPage'
import { McpSettingsPage } from '@/pages/McpSettingsPage'
import { MemoryManagePage } from '@/pages/MemoryManagePage'
import { SkillSettingsPage } from '@/pages/SkillSettingsPage'
import { ErrorLogPage } from '@/pages/ErrorLogPage'

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      {
        path: 'chat',
        children: [
          { index: true, element: <ChatPage /> },
          { path: ':sessionId', element: <ChatPage /> },
        ],
      },
      {
        path: 'settings',
        element: <SettingsPage />,
        children: [
          { index: true, element: <Navigate to="/settings/provider" replace /> },
          { path: 'provider', element: <ProviderSettingsPage /> },
          { path: 'mcp', element: <McpSettingsPage /> },
          { path: 'tools', element: <ToolSettingsPage /> },
          { path: 'advanced', element: <AdvancedSettingsPage /> },
          { path: 'memories', element: <MemoryManagePage /> },
          { path: 'skills', element: <SkillSettingsPage /> },
          { path: 'errors', element: <ErrorLogPage /> },
        ],
      },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
