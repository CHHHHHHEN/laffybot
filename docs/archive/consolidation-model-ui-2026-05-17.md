---
archived_from: plan.md
archived_at: 2026-05-17
implements: N/A (standalone feature)
status: implemented
summary: |
  为前端增加记忆归并模型（Consolidation Model）配置 UI，
  对接后端已有的 GET/PUT/DELETE /settings/consolidation-model API。
---

# 计划：前端记忆模型（Consolidation Model）配置 UI

## 1. 设计目标

为前端增加**记忆归并模型（Consolidation Model）**的配置界面，使其与现有的记忆提取模型处于同级可见位置，形成完整的"记忆模型"配置区域。

## 2. 背景现状

| 模型类型 | 后端 API | 前端 UI |
|---------|---------|--------|
| 记忆提取模型 (Extract) | ✅ `GET/PUT/DELETE /settings/extract-model` | ✅ AdvancedSettingsPage (记忆提取模型 区块) |
| 记忆归并模型 (Consolidation) | ✅ `GET/PUT/DELETE /settings/consolidation-model` | ❌ 前端尚未对接 |

后端 consolidation-model 的三个 API 端点已实现（routes.py:578-609），前端只需对接。

## 3. 范围

### 3.1 新增组件

- AdvancedSettingsPage 内新增「记忆归并模型」UI 区块（复用同一文件内的 `ProviderModelSelector` 组件）

### 3.2 修改的组件

| 文件 | 改动 |
|------|------|
| `ui/src/lib/api.ts` | 新增 `ConsolidationModelResponse` 类型和三个 API 函数 (`get/put/delete`) |
| `ui/src/hooks/use-providers.ts` | 新增三个 hooks: `useConsolidationModel`, `useSetConsolidationModel`, `useClearConsolidationModel` |
| `ui/src/pages/AdvancedSettingsPage.tsx` | 新增「记忆归并模型」区块（与「记忆提取模型」区块并列） |

### 3.3 不变的内容

- 不新增设置 tab / 路由（直接追加到 AdvancedSettingsPage 内）
- 不修改后端（API 已完整）
- 不修改现有 extract model 代码

### 3.4 已确认的范围决策

归并模型直接追加到 `AdvancedSettingsPage`，与提取模型并列。不新增设置 tab / 路由。

## 4. 组件设计

### 4.1 API 层 (`api.ts`)

新增三个函数，遵循 `getExtractModel` / `setExtractModel` / `clearExtractModel` 完全一致的签名和响应结构：

- `getConsolidationModel()` → `GET /api/v1/settings/consolidation-model` → `ConsolidationModelResponse | null`
- `setConsolidationModel(data)` → `PUT /api/v1/settings/consolidation-model` → `void`
- `clearConsolidationModel()` → `DELETE /api/v1/settings/consolidation-model` → `void`

`ConsolidationModelResponse: { provider_id: string, model_name: string }`

### 4.2 Hook 层 (`use-providers.ts`)

新增三个 hooks，遵循 `useExtractModel` 完全一致的模式：

- `useConsolidationModel()` — `useQuery({ queryKey: ['consolidationModel'], ... })`
- `useSetConsolidationModel()` — `useMutation` + invalidate `['consolidationModel']`
- `useClearConsolidationModel()` — `useMutation` + invalidate `['consolidationModel']`

### 4.3 UI 层 (`AdvancedSettingsPage.tsx`)

在「记忆提取模型」区块**之后**追加「记忆归并模型」区块。

结构与现有「记忆提取模型」区块完全一致：
1. Icon + heading + description（使用合适的图标）
2. Bordered card wrapper + explanation text
3. 当前配置显示（如果已设置）
4. `ProviderModelSelector` 组件（复用）
5. 无提供商时的引导提示文本

说明文案要解释归并模型的用途：将多条原始记忆通过 LLM 合并为一条结构化摘要。

## 5. 错误处理

| 场景 | 行为 |
|------|------|
| 后端返回 404（未配置） | `getConsolidationModel()` 返回 `null`，UI 显示无配置 |
| 后端返回 4xx（provider 不存在等） | mutation 抛异常，catch 后 toast 提示"保存失败，请稍后重试" |
| 后端返回 5xx | 同上，toast 提示 |
| 用户未选择提供商/模型时点保存 | 前端校验后 toast 提示"请选择提供商和模型" |
| 清除时后端失败 | toast 提示"清除失败，请稍后重试" |

## 6. 边界情况

- 无任何提供商时：显示引导文字"请先在「提供商配置」中添加提供商"，ProviderModelSelector 不渲染
- 已配置归并模型时：在区块顶部显示当前配置 `provider_id / model_name`
- 清除后：ProviderModelSelector 内选中项重置为空

## 7. 实现顺序

1. `api.ts` — 新增 consolidation model 的三个 API 函数
2. `use-providers.ts` — 新增三个 hooks
3. `AdvancedSettingsPage.tsx` — 新增 UI 区块（文案 + ProviderModelSelector）

## 8. 验收标准

- [x] 可在「高级设置」页看到「记忆归并模型」区块
- [x] 可从提供商列表中选择归并用的模型并保存
- [x] 保存后页面刷新仍显示已保存的配置
- [x] 可清除已保存的归并模型配置
- [x] 无提供商时显示引导提示
- [x] API 返回错误时提示"保存失败，请稍后重试"
- [x] `pnpm run check` 通过

## Implementation Record

### Core Files Changed

**Frontend** (`ui/src/`):

| File | Change |
|------|--------|
| `ui/src/lib/api.ts` | Added `ConsolidationModelResponse` type, `getConsolidationModel`, `setConsolidationModel`, `clearConsolidationModel` |
| `ui/src/hooks/use-providers.ts` | Added `useConsolidationModel`, `useSetConsolidationModel`, `useClearConsolidationModel` hooks |
| `ui/src/pages/AdvancedSettingsPage.tsx` | Added Consolidation Model UI section with `Combine` icon, handlers, and `ProviderModelSelector` |

### Design Doc References

None (standalone feature).

### Outstanding Items / Known Gaps

None.
