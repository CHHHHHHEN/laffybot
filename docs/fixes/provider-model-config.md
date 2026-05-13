# 提供商模型配置功能

## 设计目标

消除用户在新建会话时每次手动输入模型名称的摩擦。允许用户在界面中配置多个 LLM 提供商及其可用模型列表，新建会话时直接从预配置的模型中选择。

## 现状与痛点

- 只支持单一提供商，配置硬编码在 `config.json` 中
- 新建会话时模型为自由文本输入框，无提示无验证
- 设置页面的提供商管理界面为静态 mock，无后端对接
- 每次新建会话需手动输入模型名称，易出错且重复
- 无结构化日志，排查问题依赖 print/默认 logging

## 概念模型

引入两个新实体：

**提供商（Provider）**：代表一个 LLM API 服务端，包含连接该服务所需的凭证和地址信息。

**提供商模型（Provider Model）**：属于某个提供商的模型名称，标识该提供商可用的具体模型。

一个提供商可拥有多个模型，一个模型仅属于一个提供商。

使用三张新表存储：`providers` 表存储提供商凭证和地址，`provider_models` 表通过外键关联提供商，`app_settings` 表以 key-value 形式存储全局当前选中的提供商和模型 ID。将当前选中独立为 app_settings 而非 providers 的列，以保持提供商管理与选中状态分离，便于清除选中。

引入两个 Store 分工：**SessionStore**（现有，不变）专注于会话和消息的持久化；**ProviderStore**（新增）负责提供商、模型和全局选中的持久化，独立于 SessionStore 管理自己的抽象接口。两者在实现层可共享同一数据库连接。

## 架构决策

### 决策 1：会话与提供商解耦

会话不存储 `provider_id`。提供商与模型的选择是全局运行时设置，独立于任何会话。

sessions 表仍保留 `model` 列，但语义变为**创建快照**——创建会话时从全局选中解析出模型名称并写入该列。该值仅用于 API 响应返回，不作为运行时模型选择的依据。`_build_messages` 的 `model` 参数直接使用当前全局选中的 model_name，保持运行时一致。消息发送时使用的提供商和模型均由当前全局选中决定，与会话记录的 model 无关。

理由：
- 会话聚焦消息历史，不关心底层由哪个提供商驱动
- API 响应需要告知用户"此会话使用什么模型"，保留 model 快照满足该需求
- 用户可在任意时刻切换提供商或模型，即时生效，无需预先绑定
- 删除或修改提供商不影响任何历史会话

### 决策 2：Provider Factory 的职责拆分

Provider Factory 不再承担配置查找职责，改为只负责根据给定的配置对象创建 Provider 实例。配置查找由 SessionManager 从 ProviderStore 中完成并传入。Factory 签名从 `Callable[[str], BaseProvider]` 改为 `Callable[[ProviderConfig], BaseProvider]`。

理由：
- Factory 职责单一化，易于测试和复用
- 配置来源对 Factory 透明
- SessionManager 已持有 SessionStore 和 ProviderStore 引用，无需额外注入

### 决策 3：移除 config.json 中的提供商配置

`config.json` 不再包含任何提供商或密钥相关配置，仅保留服务器运行时参数（host、port、cors 等）。所有提供商管理统一通过 ProviderStore + API + UI 完成。`config.example.json` 同步精简。

**用户完全通过界面配置提供商和模型**，不涉及编辑文件或重启服务。首次启动时 providers 表为空，用户打开设置页面通过表单添加提供商和模型，所有操作即时持久化到数据库。

理由：
- 单一数据源：提供商配置只存在于数据库中，不存在配置分裂
- 运行时变更：用户通过 UI 修改配置即时生效，无需编辑文件或重启服务
- 简化部署：`config.json` 缩减为纯 Web 服务器配置，不涉及敏感信息

### 决策 4：API Key 加密存储

API Key 在存储层使用对称加密（Fernet）加密保存，在 Provider 实例创建时解密使用，加解密对上层透明。加密密钥仅从环境变量获取，首次启动时若环境变量未设置则拒绝启动。

加密/解密在 ProviderStore 层封装，上层业务（SessionManager、API Routes）无感知。运行时加密密钥失效（如进程启动后被移除环境变量）不做预检，由 `encrypt_api_key` / `decrypt_api_key` 在调用路径中自然失败并抛 `ProviderConfigError`。

理由：
- 明文存储凭证存在安全风险
- 加密范围限定在 ProviderStore 层，上层业务逻辑无需感知
- 解密仅在 Provider 实例化的内存路径中发生，不落盘
- 加密密钥仅存在于内存（环境变量），不写盘，减少密钥泄露面
- 运行时不做预检，避免在每次请求中重复检查环境变量

### 决策 5：新增前端 providerStore，减少状态耦合

在 Zustand 中新增独立的 `providerStore`，管理提供商列表、模型列表、全局当前选中。不将提供商状态混入 `uiStore` 或 `sessionStore`，各 Store 职责不重叠：

| Store | 持有状态 | 不与下列耦合 |
|-------|----------|-------------|
| `sessionStore` | 会话列表、当前会话 ID | 不感知提供商 |
| `chatStore` | 消息流、SSE 状态 | 不感知提供商 |
| `providerStore` | 提供商列表、模型列表、全局选中 | 独立存在 |
| `uiStore` | 侧边栏折叠、主题 | 不感知提供商 |

理由：
- 提供商状态变更频繁（增删改、切换选中），独立 Store 避免触发无关组件重渲染
- 会话/聊天 Store 不需要感知提供商的存在，符合决策 1 的解耦原则

### 决策 6：数据库直接重建，无迁移逻辑

不保留向后兼容，不写迁移脚本。数据库变更后手动删除 `laffybot.db` 文件，启动时自动建表。

理由：
- 当前系统无生产数据，迁移成本为零
- 避免维护复杂迁移代码

### 决策 7：不设置回退策略

系统完全依赖数据库提供商配置。数据库不可用、加密密钥未配置等场景均不设降级或回退方案。启动时前置校验，不满足则拒绝启动。

providers 表为空**不视为启动错误**——用户首次使用时应通过 UI 配置提供商，启动时不要求存在任何提供商。

理由：
- 避免维护两套路径带来的复杂度
- 提供商管理是纯运行时行为，不决定服务能否启动

## 交互流程

### 提供商配置流程

```
用户 → ProviderSettingsPage → API → ProviderStore → SQLite
```

1. 用户在设置页面管理提供商（增/删/改）
2. 对每个提供商管理其模型列表
3. 操作通过 API 持久化到数据库（api_key 在 ProviderStore 层加密后落库）
4. 每次操作后前端刷新 `providerStore`，确保 UI 一致

### 新建会话流程

```
用户 → NewSessionDialog → API → SessionManager → SessionStore + ProviderStore
```

1. 用户打开新建会话对话框
2. 对话框显示当前全局选中的提供商和模型（只读展示，不可修改）
3. 若无全局选中，对话框展示"请先选择提供商和模型"提示及跳转设置链接，禁用"创建"按钮
4. 用户填写 system prompt，可选调整 max_iterations，提交
5. `POST /api/v1/sessions` 不再接收 `model` 字段。后端通过 ProviderStore 解析当前选中的 model_name，存入 session 快照。若全局选中为空，返回 `400 NoActiveProviderError`
6. 消息发送时使用当前全局选中的提供商配置

### 消息发送流程

```
SessionManager.send_message()
  → ProviderStore.get_active_selection()    # 返回 { provider_id, model_id, model_name }
  → 若为空则抛 NoActiveProviderError
  → ProviderStore.get_provider_config(provider_id)  # JOIN provider_models 解析 model_name，自动解密 api_key
  → ProviderFactory(config) → Provider
  → _build_messages(model=model_name)                 # model_name 来自 active_selection，保持运行时一致
  → AgentRunner.run(provider, model_name, ...)      # model_name 来自 active_selection
```

## 组件职责

| 组件 | 职责 |
|------|------|
| **SessionStore** | 现有组件，不变。仅处理 sessions 和 messages 两张表的持久化，不涉及任何提供商逻辑 |
| **ProviderStore** | 新组件。独立抽象接口，持久化 providers/provider_models/app_settings 三张表，提供 CRUD 方法；提供根据 provider_id 组装 ProviderConfig 并解密 api_key 的方法；管理全局当前选中的读写；提供 `get_active_selection()` 返回包含 provider_id、model_id、model_name 的完整对象（通过 JOIN 解析 model_name） |
| **API Routes** | 新增加密模块用于端点层异常捕获。提供商管理路由依赖 ProviderStore；暴露提供商和模型的 RESTful 端点；提供查询/切换全局当前选中的提供商和模型；`POST /api/v1/sessions` 不再接收 `model` 字段，后端从全局选中解析 model_name 后写入 session 快照 |
| **SessionManager** | `create_session()` 从 ProviderStore 获取当前选中的 model_name 写入 session 快照；`send_message()` 从 ProviderStore 获取当前选中的 provider_id 和 model_name，调用 ProviderStore.get_provider_config() 获取解密配置后创建 Provider；`_build_messages()` 的 model 参数从当前全局选中传入，与运行时的 provider 保持一致 |
| **ProviderSettingsPage** | 提供商和模型的完整管理界面（增删改）；调用 API 后刷新 providerStore |
| **GlobalModelSelector** | 全局提供商+模型选择器，显示在界面常驻位置（如侧边栏或顶栏），切换即时生效；从 providerStore 读取数据，切换后调用 API 更新全局选中；若 providers 列表为空，显示"前往设置配置提供商"链接 |
| **NewSessionDialog** | 从 providerStore 读取当前全局选中的提供商和模型，只读展示；若无选中则展示提示+跳转设置链接，并禁用提交；不再包含 model 输入框 |
| **ProviderFactory** | 仅负责从给定 ProviderConfig 对象创建 Provider 实例 |
| **providerStore** | 管理提供商列表、模型列表、当前选中状态，提供 API 调用的封装。在 `AppShell` 挂载时执行首次 fetchProviders 和 getActive |

## API 契约

### 提供商管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/providers` | 列出所有提供商（不返回 api_key） |
| POST | `/api/v1/providers` | 创建提供商（接收 api_key，后端加密存储） |
| GET | `/api/v1/providers/{id}` | 获取提供商详情（不返回 api_key，返回 has_api_key: bool） |
| PUT | `/api/v1/providers/{id}` | 更新提供商（api_key 可选，不传时保留旧值） |
| DELETE | `/api/v1/providers/{id}` | 删除提供商（级联删除其模型、若为当前选中则清除选中） |

### 模型管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/providers/{id}/models` | 列出提供商下的模型 |
| POST | `/api/v1/providers/{id}/models` | 添加模型 |
| DELETE | `/api/v1/providers/{id}/models/{model_id}` | 删除模型 |

### 连通性验证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/providers/{id}/test` | 验证提供商配置的有效性 |

**判定标准（以 OpenAI API 为标准）**：
- 请求端点：`/v1/chat/completions`
- 请求体：`{ "model": "<该提供商下第一个模型的名称>", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1 }`
- 成功：返回 200，响应格式合法
- 失败分类：连接超时/无路由 → `ProviderConnectionError` (502)；4xx 凭证错误 → `ProviderConfigError` (500)；5xx 服务端错误 → `ProviderConnectionError` (502)

### 当前提供商选择

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/providers/active` | 获取当前全局选中的提供商和模型；若无选中返回 null |
| PUT | `/api/v1/providers/active` | 设置当前全局选中的提供商和模型 |

### 安全约束

- 所有 GET 响应不返回 `api_key` 明文，仅返回布尔字段指示是否已配置
- `POST/PUT` 接收 `api_key`，后端加密后存储，不再回传
- `PUT` 时 `api_key` 为可选字段，不传时保留旧值
- 前端不参与任何加解密逻辑

### 会话 API 响应

`GET /api/v1/sessions` 和 `GET /api/v1/sessions/{id}` 的响应中 `model` 字段**仍然返回**，值为创建时从全局选中解析的 model_name（session 快照）。该值不随全局选中切换而改变。

### 会话创建

`POST /api/v1/sessions` 移除 `model` 字段（请求体不再接收），后端通过 ProviderStore 解析当前全局选中的 model_name 并写入 session 快照。

若发起请求时全局选中为空（无任何提供商或未选中），返回 `400 NoActiveProviderError`，不创建 session。

## 错误处理策略

### 领域异常

| 异常 | 触发条件 | HTTP 状态码 | error code |
|------|----------|-------------|------------|
| `ProviderNotFoundError` | provider_id 不存在 | 404 | PROVIDER_NOT_FOUND |
| `ProviderConfigError` | API Key 解密失败、配置格式错误 | 500 | PROVIDER_CONFIG_ERROR |
| `ProviderConnectionError` | 连通性测试连接失败 | 502 | PROVIDER_CONNECTION_ERROR |
| `NoActiveProviderError` | 发送消息时未选中全局提供商 | 400 | NO_ACTIVE_PROVIDER |
| `ModelNotFoundError` | model_id 不存在 | 404 | MODEL_NOT_FOUND |
| `ModelNameConflictError` | 同一提供商下模型名重复 | 409 | MODEL_NAME_CONFLICT |

### 场景处理

- 删除提供商时级联删除其所有模型。若该提供商为当前全局选中，清除选中状态并**通过 toast 通知用户**"已被删除，请重新选择"。API 响应体附加 `active_cleared: true` 标记供前端展示
- 添加模型时验证模型名在同一提供商下的唯一性
- API Key 解密失败时返回 `ProviderConfigError`，阻止 Provider 实例化
- 发送消息前检查全局选中是否存在，不存在则返回 `NoActiveProviderError`
- 创建会话时全局选中为空，返回 `400 NoActiveProviderError`，不创建 session
- 加密密钥环境变量缺失时启动阶段拒绝启动（密钥用于加密存储 api_key，不涉及 providers 表是否为空）
- 加密密钥在运行时缺失（启动后环境变量被移除）：`encrypt_api_key` / `decrypt_api_key` 内部捕获异常并抛 `ProviderConfigError`，API 层统一映射为 500。此场景不在启动时预检，由调用路径自然失败

## 日志策略

使用 loguru 进行结构化分级日志。各组件按以下原则记录：

- **ProviderStore**：记录 provider CRUD 操作（不含 api_key 任何形式）和活跃选中变更；解密失败、约束冲突等异常场景提升至 WARNING
- **SessionStore**：不变，沿用现有日志
- **API 层**：记录提供商创建/删除和选中切换等关键操作；请求校验失败记为 WARNING
- **SessionManager**：每次 send_message 记录 session_id、provider_id、model_name；Provider 实例化失败记为 ERROR
- **ProviderFactory**：创建 Provider 实例时 DEBUG 级别记录（不含 api_key）；配置缺失导致创建失败记为 ERROR
- **加密模块**：解密失败、密钥无效记为 ERROR

严格禁止记录 api_key 明文或密文，`logger.exception()` 仅用于非预期异常。

## 安全边界

- 提供商管理 API 在设计上假定局域网或反向代理保护，不实现前端用户认证
- 若未来需要暴露到公网，应在反向代理层实现认证
- API Key 不在任何日志、错误消息或响应体中出现
- 解密前对密文做空值检测
- 前端不存储 api_key，仅在创建/编辑表单中临时持有，提交后丢弃
