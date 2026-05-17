---
archived_from: plan.md
archived_at: 2026-05-17
implements: docs/memory-system-impl-roadmap.md (Phase 2)
status: implemented
summary: |
  为 Laffybot 记忆系统实现整合 Agent 和相似内容去重功能，
  解决多个 Session 产生相似记忆导致的冗余问题，提升记忆质量和注入效率。
---

# Plan: 记忆系统整合 Agent 与相似内容去重

(Full content from plan.md — see original at plan.md for full context)

## Goal

为 Laffybot 记忆系统实现 **整合 Agent** 和 **相似内容去重** 功能，解决多个 Session 产生相似记忆导致的冗余问题，提升记忆质量和注入效率。

## Acceptance Criteria

1. **整合 Agent**：新增整合流程，合并多个原始记忆为精简的整合记忆
2. **相似内容去重**：整合 Agent 的 prompt 包含去重指令，合并相似内容
3. **注入优化**：Session 启动时注入整合后的记忆，而非原始记忆列表
4. **存储分离**：原始记忆与整合记忆分离存储，支持追溯
5. **API 兼容**：现有记忆 API 保持兼容，新增整合记忆查询接口
6. **触发条件**：未整合原始记忆达到阈值（默认 10 条）时自动触发整合
7. **降级策略**：无整合记忆时回退到原始记忆注入
8. **并发安全**：同时多个 Session 触发整合时，只执行一次整合操作

## Implementation Record

### Core Files Changed

**Python Backend** (`laffybot/memory/`):

| File | Change |
|------|--------|
| `laffybot/memory/config.py` | Added `consolidation_trigger_count`, `consolidation_model`, `max_source_memories` fields |
| `laffybot/memory/prompts.py` | Added `CONSOLIDATE_MEMORY_PROMPT` template with dedup instructions |
| `laffybot/memory/consolidated_store.py` | **New file**: `ConsolidatedMemoryStore` with `consolidated_memory` table (single record) |
| `laffybot/memory/consolidator.py` | **New file**: `MemoryConsolidator` class with LLM-based consolidation logic |
| `laffybot/memory/store.py` | Added `get_unconsolidated_memories()` method to `MemoryStore` / `SQLiteMemoryStore` |
| `laffybot/memory/manager.py` | Added consolidator integration, `get_injection_content()`, init `ConsolidatedMemoryStore` |
| `laffybot/memory/__init__.py` | Added `ConsolidatedMemoryStore`, `MemoryConsolidator` to exports |

**API Layer** (`laffybot/api/`):

| File | Change |
|------|--------|
| `laffybot/api/schemas.py` | Added `ConsolidatedMemoryResponse`, `ConsolidationStatusResponse` |
| `laffybot/api/routes.py` | Added `GET /consolidated-memory`, `POST /consolidated-memory/trigger`, `GET /consolidated-memory/status`, consolidation model settings routes |

**Settings** (`laffybot/session/`):

| File | Change |
|------|--------|
| `laffybot/session/app_setting_store.py` | Added `get/set/delete_consolidation_model()` methods |

**Frontend** (`ui/src/`):

| File | Change |
|------|--------|
| `ui/src/lib/api.ts` | Added `getConsolidatedMemory`, `getConsolidationStatus`, `triggerConsolidation` |
| `ui/src/hooks/use-memories.ts` | Added `useConsolidatedMemory`, `useConsolidationStatus`, `useTriggerConsolidation` |
| `ui/src/pages/MemoryManagePage.tsx` | Added `ConsolidationSection` component with status card and trigger |

### Design Doc References

- `docs/memory-system-impl-roadmap.md` — Phase 2 section updated to ✅

### Outstanding Items / Known Gaps

None.
