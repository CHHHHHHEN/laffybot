---
archived_from: plan.md
archived_at: 2026-05-19
implements: laffybot SKILL system
status: implemented
summary: |
  Add SKILL support to laffybot: SkillsLoader, SkillRegistry, SkillViewTool,
  API endpoints, and frontend settings page.
---

# SKILL 系统实现计划

(Full plan content archived from `plan.md`)

## Implementation Record

### Core files changed

**New files:**
- `laffybot/agent/skills/__init__.py` — Module exports
- `laffybot/agent/skills/loader.py` — SkillsLoader (discovery, parsing, caching, content loading)
- `laffybot/agent/skills/registry.py` — SkillRegistry (enabled state management via AppSettingStore)
- `laffybot/agent/skills/models.py` — SkillMetadata, Skill dataclasses
- `laffybot/agent/skills/errors.py` — SkillError exception
- `laffybot/agent/tools/skill_view.py` — SkillViewTool (kind="skill", protected from pruning)
- `laffybot/api/skill_routes.py` — 4 SKILL API endpoints
- `ui/src/pages/SkillSettingsPage.tsx` — SKILL settings page
- `ui/src/hooks/use-skills.ts` — TanStack Query hooks for skills

**Modified files:**
- `laffybot/agent/tools/base.py` — `Tool.kind` extended to `Literal["builtin", "mcp", "skill"]`
- `laffybot/context/compressor.py` — `prune_tool_outputs()` receives ToolRegistry for kind-based matching
- `laffybot/context/builder.py` — `SimpleContextBuilder` accepts ToolRegistry, passes to prune_tool_outputs
- `laffybot/session/app_setting_store.py` — Added `_get_raw`/`_set_raw` generic methods; `get_skills_path`, `set_skills_path`, `get_enabled_skills`, `set_enabled_skills`
- `laffybot/session/manager.py` — `context_builder` made required; accepts SkillsLoader/SkillRegistry; generates `skills_block` in `_build_messages()`
- `laffybot/api/schemas.py` — Added SkillsPathResponse, SkillsPathUpdateRequest, SkillItem, SkillsListResponse, SkillEnabledUpdateRequest
- `laffybot/api/dependencies.py` — Added `build_skills_loader`, `build_skill_registry`, `build_context_builder`, `get_skills_loader`, `get_skill_registry`
- `laffybot/api/app.py` — Wires SkillsLoader/SkillRegistry/SkillViewTool/SimpleContextBuilder; sets app.state
- `laffybot/api/routes.py` — Registers skill_routes
- `laffybot/config.py` — Default `system_prompt_template` includes `{{ skills_block }}`
- `ui/src/App.tsx` — Added `/settings/skills` route
- `ui/src/pages/SettingsPage.tsx` — Added "SKILL 设置" tab
- `ui/src/lib/api.ts` — Added skill API functions

### Design docs referenced
- `plan.md` (this document)

### Outstanding items / known gaps
- None. All items in the plan scope have been implemented.

### Implementation notes
- `SessionManager.__init__` no longer has fallback `SimpleContextBuilder` creation; `context_builder` is required.
- `prune_tool_outputs` now matches by `Tool.kind` (via ToolRegistry) before falling back to message name matching.
- SkillsLoader uses a simple YAML parser (no pyyaml dependency) for frontmatter parsing.
- Path traversal protection implemented in `SkillsLoader.load_resource()`.
