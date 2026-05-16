---
archived_from: plan.md
archived_at: 2026-05-16
implements: docs/memory-system-impl-roadmap.md (Phase 2 continuation)
status: implemented
summary: Fix memory injection not working due to None defaults, unify system_prompt as UI global setting
---

# Phase 2 续：记忆注入修复 + system_prompt 架构统一

Archived from `plan.md`. See plan.md for full design details.

## Implementation Record

### Core files changed

**Configuration:**
- `laffybot/config.py`: `system_prompt` default `None` → `"You are a helpful assistant."`, `system_prompt_template` default `None` → memory-aware Jinja2 template

**Context builder:**
- `laffybot/context/builder.py`: Changed priority from `session prompt > template > config prompt` to `template > ContextConfig.system_prompt`

**Session manager:**
- `laffybot/session/manager.py`: `create_session()` removed `system_prompt` parameter; `_build_messages()` sources `system_prompt` from `context_config` instead of `session.system_prompt`

**API layer:**
- `laffybot/api/app.py`: Store `context_config` in `app.state.context_config`
- `laffybot/api/schemas.py`: `SessionCreateRequest` removed `system_prompt` field; added `SystemPromptUpdateRequest`
- `laffybot/api/routes.py`: Added `GET/PUT /api/v1/settings/system-prompt` endpoints; updated create session route

**UI layer:**
- `ui/src/lib/api.ts`: `CreateSessionRequest` removed `system_prompt`; added `getSystemPrompt()` / `setSystemPrompt()` API methods
- `ui/src/hooks/use-providers.ts`: Added `useSystemPrompt()` / `useSetSystemPrompt()` hooks
- `ui/src/pages/AdvancedSettingsPage.tsx`: Added system prompt editor section

**Documentation:**
- `docs/api.md`: Removed `system_prompt` from create session request body; added system prompt API documentation
- `docs/memory-system-impl-roadmap.md`: Updated implementation status
- `docs/session-model-decoupling.md`: Updated references to removed `system_prompt` field

### Design docs referenced
- `docs/memory-system-impl-roadmap.md`

### Outstanding items / known gaps
- None
