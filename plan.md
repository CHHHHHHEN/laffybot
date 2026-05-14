# 修复：多 Provider 下拉菜单不可选

## 问题描述

用户在 UI 中添加多个 Provider 后，侧边栏 `GlobalModelSelector` 的提供商和模型下拉菜单无法正常选择。选择提供商后菜单卡住，无法继续选择模型。

## 根因分析

`GlobalModelSelector.tsx:19` 在选择提供商时发送空的 `modelId`：

```typescript
setActiveSelection.mutate({ providerId, modelId: '' })
```

→ `PUT /api/v1/providers/active` 请求体：`{"provider_id": "xxx", "model_id": ""}`

后端 `SQLiteProviderStore.set_active_selection()` 中 `provider_store.py:397-403` **强制校验 model 在 `provider_models` 表中存在**：

```python
async with db.execute(
    "SELECT model_id FROM provider_models WHERE model_id = ? AND provider_id = ?",
    (model_id, provider_id),   # model_id = ""
) as cursor:
    model_row = await cursor.fetchone()
if model_row is None:
    raise ModelNotFoundError(model_id)  # ← 无匹配，抛出异常
```

由于没有 model 的 ID 是空字符串，查询返回空，抛出 `ModelNotFoundError`，API 返回 404。前端 mutation 失败，`activeSelection` 始终为 `null`，两个下拉菜单均不可用。

`get_active_selection()` 同样存在问题：即使跳过校验存入了空 `model_id`，该方法使用 `INNER JOIN provider_models` 查询，`model_id=""` 无法匹配任何记录，仍返回 `null`。

## 修改范围

只改 **1 个文件**：`laffybot/session/provider_store.py`

无需修改前端代码。

### 改动 1：`set_active_selection()`

- 当 `model_id` 为空字符串时，**跳过 model 存在性校验**，直接写入 `app_settings`
- 当 `model_id` 非空时，保持原有校验逻辑不变

```python
# 在 model 校验前加：
if not model_id:
    # 仅选择提供商，尚未选择模型 — 跳过 model 校验
    pass  # 直接走到 INSERT 逻辑
else:
    # 原有校验逻辑
    async with db.execute(...):
        ...
    if model_row is None:
        raise ModelNotFoundError(model_id)
```

### 改动 2：`get_active_selection()`

在拿到 `provider_id` 和 `model_id` 后：

- 如果 `model_id` 为空 → 只查询 provider name，返回 `ActiveSelection` 且 `model_name=""`
- 如果 `model_id` 非空 → 走原有 `JOIN provider_models` 逻辑

```python
if not model_id:
    async with db.execute(
        "SELECT name AS provider_name FROM providers WHERE provider_id = ?",
        (provider_id,),
    ) as cursor:
        selection = await cursor.fetchone()
    if selection is None:
        return None
    return ActiveSelection(
        provider_id=provider_id,
        model_id="",
        provider_name=selection["provider_name"],
        model_name="",
    )

# 原有 JOIN 逻辑保持不变
```

## 数据流（修复后）

```
用户选择提供商 "Provider A"
  → handleProviderChange("p1")
  → setActiveSelection.mutate({ providerId: "p1", modelId: "" })
  → PUT /api/v1/providers/active { provider_id: "p1", model_id: "" }
  → set_active_selection("p1", "")：跳过校验，写入 app_settings
  → GET /api/v1/providers/active
  → get_active_selection()：model_id=""，走 provider-only 分支
  → 返回 { provider_id: "p1", model_id: "", provider_name: "Provider A", model_name: "" }
  → 模型下拉菜单启用，加载模型列表

用户选择模型 "gpt-4"
  → handleModelChange("m1")
  → setActiveSelection.mutate({ providerId: "p1", modelId: "m1" })
  → PUT /api/v1/providers/active { provider_id: "p1", model_id: "m1" }
  → set_active_selection("p1", "m1")：校验通过，写入 app_settings
  → 返回完整 ActiveSelection
```

## 验证方式

1. 启动后端 + 前端
2. 进入 `/settings/provider`，添加 2+ 个 Provider，每个添加至少 1 个 Model
3. 回到聊天页，点击侧边栏下拉菜单：
   - [ ] 提供商下拉可展开，能看到所有 Provider
   - [ ] 选择 Provider A → 模型下拉自动加载该 Provider 的模型
   - [ ] 选择某个模型 → 底部显示 "当前: Provider A / model-name"
   - [ ] 切换到 Provider B → 模型下拉切换为 Provider B 的模型列表
   - [ ] 再次切回 Provider A → 模型下拉显示 Provider A 的模型
4. 用新选择的模型发送消息，确认后端正确使用该 Provider
