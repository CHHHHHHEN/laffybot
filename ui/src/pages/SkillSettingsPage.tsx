import { useState } from 'react'
import { FolderOpen, Loader2, Check, AlertCircle } from 'lucide-react'
import { useSkillsPath, useSetSkillsPath, useSkills, useSetSkillEnabled } from '@/hooks/use-skills'
import { Button } from '@/components/ui/Button'
import { toast } from 'sonner'

export function SkillSettingsPage() {
  const { data: skillsPathData, isLoading: pathLoading } = useSkillsPath()
  const { data: skillsData, isLoading: skillsLoading } = useSkills()
  const setSkillsPathMutation = useSetSkillsPath()
  const setSkillEnabledMutation = useSetSkillEnabled()

  const [pathInput, setPathInput] = useState('')
  const [isSavingPath, setIsSavingPath] = useState(false)

  const handleSavePath = async () => {
    if (!pathInput.trim()) {
      toast.error('请输入 SKILL 目录路径')
      return
    }
    setIsSavingPath(true)
    try {
      await setSkillsPathMutation.mutateAsync(pathInput.trim())
      toast.success('SKILL 目录路径已保存')
    } catch {
      toast.error('保存失败，请检查路径是否正确')
    } finally {
      setIsSavingPath(false)
    }
  }

  const handleToggleSkill = async (name: string, currentEnabled: boolean) => {
    try {
      await setSkillEnabledMutation.mutateAsync({ name, enabled: !currentEnabled })
    } catch {
      toast.error('操作失败，请稍后重试')
    }
  }

  if (pathLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 size={24} className="animate-spin text-[var(--color-text-secondary)]" />
      </div>
    )
  }

  const currentPath = skillsPathData?.path ?? ''
  const skills = skillsData?.skills ?? []

  return (
    <div className="p-6 max-w-[720px]">
      {/* Path Configuration */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <FolderOpen size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">SKILL 目录</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            设置 SKILL 文件所在的目录路径
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4 mb-8">
        <div className="text-sm text-[var(--color-text-secondary)] space-y-2 mb-4">
          <p>SKILL 是预设的指令文件，可以通过 <code className="text-[var(--color-text-primary)] bg-[var(--color-secondary-bg)] px-1 rounded">skill_view</code> 工具让 Agent 按需加载。</p>
          <p>目录下每个子目录应包含一个 <code className="text-[var(--color-text-primary)] bg-[var(--color-secondary-bg)] px-1 rounded">SKILL.md</code> 文件，以及可选的 <code className="text-[var(--color-text-primary)] bg-[var(--color-secondary-bg)] px-1 rounded">references/</code> 资源目录。</p>
        </div>

        {currentPath && (
          <div className="mb-4 p-3 rounded bg-[var(--color-secondary-bg)] text-sm">
            <span className="text-[var(--color-text-secondary)]">当前路径：</span>
            <span className="font-mono text-[var(--color-text-primary)]">{currentPath}</span>
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            value={pathInput}
            onChange={(e) => setPathInput(e.target.value)}
            placeholder={currentPath || '输入 SKILL 目录路径...'}
            className="flex-1 px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-page-bg)] text-sm text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] font-mono"
          />
          <Button onClick={handleSavePath} disabled={isSavingPath}>
            {isSavingPath ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Check size={14} />
            )}
            保存
          </Button>
        </div>
      </div>

      {/* Skills List */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-lg bg-[var(--color-secondary-bg)] flex items-center justify-center">
          <AlertCircle size={20} className="text-[var(--color-text-secondary)]" />
        </div>
        <div>
          <h3 className="text-base font-medium text-[var(--color-text-primary)]">已发现的 SKILL</h3>
          <p className="text-sm text-[var(--color-text-secondary)]">
            启用后，SKILL 元数据会自动注入会话的 system prompt
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-page-bg)] p-4">
        {skillsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="animate-spin text-[var(--color-text-secondary)]" />
          </div>
        ) : skills.length === 0 ? (
          <div className="text-center py-8 text-sm text-[var(--color-text-placeholder)]">
            {currentPath ? '未发现 SKILL 文件，请检查目录路径' : '请先设置 SKILL 目录路径'}
          </div>
        ) : (
          <div className="space-y-3">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className="flex items-center justify-between p-3 rounded-md bg-[var(--color-secondary-bg)]"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">
                      {skill.name}
                    </span>
                    {skill.has_resources && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--color-border)] text-[var(--color-text-secondary)]">
                        references
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 truncate">
                    {skill.description}
                  </p>
                </div>
                <button
                  onClick={() => handleToggleSkill(skill.name, skill.enabled)}
                  className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)] focus:ring-offset-2 ${
                    skill.enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]'
                  }`}
                  role="switch"
                  aria-checked={skill.enabled}
                >
                  <span
                    className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform ring-0 transition duration-200 ease-in-out ${
                      skill.enabled ? 'translate-x-4' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
