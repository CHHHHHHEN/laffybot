# 提供商模型管理设计

## 设计目标

消除用户在新建会话时每次手动输入模型名称的摩擦。允许用户在界面中配置多个 LLM 提供商及其可用模型列表，新建会话时直接从预配置的模型中选择。

## 概念模型

引入两个新实体：

**提供商（Provider）**：代表一个 LLM API 服务端，包含连接该服务所需的凭证和地址信息。

**提供商模型（Provider Model）**：属于某个提供商的模型名称，标识该提供商可用的具体模型。

一个提供商可拥有多个模型，一个模型仅属于一个提供商。提供商与模型通过外键关联，删除提供商时级联删除其所有模型。

**全局选中（Active Selection）**：运行时的全局设定，记录当前使用的提供商和模型 ID。该选中独立于任何会话，切换即时生效。

## 架构决策

### 决策 1：会话与提供商解耦

会话不存储 `provider_id`。提供商与模型的选择是全局运行时设置，独立于任何会话。

`sessions` 表仍保留 `model` 列，但语义变为**创建快照**——创建会话时从全局选中解析出模型名称并写入该列。该值仅用于 API 响应返回，不作为运行时模型选择的依据。消息发送时使用的提供商和模型均由当前全局选中决定，与会话记录的 model 无关。

理由：
- 会话聚焦消息历史，不关心底层由哪个提供商驱动
- API 响应需要告知用户"此会话使用什么模型"，保留 model 快照满足该需求
- 用户可在任意时刻切换提供商或模型，即时生效，无需预先绑定
- 删除或修改提供商不影响任何历史会话

### 决策 2：运行时配置取代文件配置

`config.json` 不再包含任何提供商或密钥相关配置，仅保留服务器运行时参数（host、port、cors 等）。所有提供商管理统一通过 ProviderStore + API + UI 完成。

用户完全通过界面配置提供商和模型，不涉及编辑文件或重启服务。首次启动时 providers 表为空，用户打开设置页面通过表单添加提供商和模型，所有操作即时持久化到数据库。

理由：
- 单一数据源：提供商配置只存在于数据库中，不存在配置分裂
- 运行时变更：用户通过 UI 修改配置即时生效，无需编辑文件或重启服务
- 简化部署：config.json 缩减为纯 Web 服务器配置，不涉及敏感信息

### 决策 3：API Key 加密存储

API Key 在存储层使用对称加密保存，在 Provider 实例创建时解密使用，加解密对上层透明。加密密钥仅从环境变量获取，首次启动时若环境变量未设置则拒绝启动。

加密/解密在 ProviderStore 层封装，上层业务（SessionManager、API Routes）无感知。

理由：
- 明文存储凭证存在安全风险
- 加密范围限定在 ProviderStore 层，上层业务逻辑无需感知
- 解密仅在 Provider 实例化的内存路径中发生，不落盘
- 加密密钥仅存在于内存（环境变量），不写盘，减少密钥泄露面

### 决策 4：Store 职责分离

前端新增独立的 `providerStore`，管理提供商列表、模型列表、全局当前选中。各 Store 职责不重叠：

| Store | 持有状态 | 不与下列耦合 |
|-------|----------|-------------|
| `sessionStore` | 会话列表、当前会话 ID | 不感知提供商 |
| `chatStore` | 消息流、SSE 状态 | 不感知提供商 |
| `providerStore` | 提供商列表、模型列表、全局选中 | 独立存在 |
| `uiStore` | 侧边栏折叠、主题 | 不感知提供商 |

### 决策 5：不设置回退策略

系统完全依赖数据库提供商配置。数据库不可用、加密密钥未配置等场景均不设降级或回退方案。启动时前置校验，不满足则拒绝启动。

providers 表为空不视为启动错误——用户首次使用时应通过 UI 配置提供商，启动时不要求存在任何提供商。

### 决策 6：数据库直接重建，无迁移逻辑

不保留向后兼容，不写迁移脚本。数据库变更后手动删除 `laffybot.db` 文件，启动时自动建表。

## 组件职责

### 后端

| 组件 | 职责 |
|------|------|
| **SessionStore** | 不变。仅处理 sessions 和 messages 两张表的持久化，不涉及任何提供商逻辑 |
| **ProviderStore** | 独立抽象接口，持久化 providers/provider_models/app_settings 三张表，提供 CRUD 方法；提供根据 provider_id 组装配置并解密 api_key 的方法；管理全局当前选中的读写 |
| **API Routes** | 提供商管理路由依赖 ProviderStore；提供商 CRUD / 模型管理 / 连通性测试 / 全局选中读写；POST /sessions 不再接收 model 字段 |
| **SessionManager** | create_session() 从 ProviderStore 获取当前选中的 model_name 写入 session 快照；send_message() 运行时从 ProviderStore 获取配置并创建 Provider 实例 |
| **加密模块** | 提供对称加密/解密原语，封装在 ProviderStore 层 |

### 前端

| 组件 | 职责 |
|------|------|
| **providerStore** | 管理提供商列表、模型列表、当前选中状态，提供 API 调用的封装。在 AppShell 挂载时执行首次 fetch 操作 |
| **ProviderSettingsPage** | 提供商和模型的完整管理界面（增删改）；调用 API 后刷新 providerStore |
| **GlobalModelSelector** | 全局提供商+模型选择器，显示在侧边栏，切换即时生效；从 providerStore 读取数据 |
| **NewSessionDialog** | 从 providerStore 读取当前全局选中的提供商和模型，只读展示；若无选中则展示提示并禁用提交；不再包含 model 输入框 |
| **ProviderForm** | 提供商添加/编辑表单，包含名称、Base URL、API Key、额外请求头 |
| **ModelList** | 管理指定提供商下的模型列表（添加/删除） |

## 数据流

### 提供商配置流程

```
用户 → ProviderSettingsPage → API → ProviderStore → SQLite
```

用户在设置页面管理提供商（增/删/改），对每个提供商管理其模型列表，操作通过 API 持久化到数据库（api_key 在 ProviderStore 层加密后落库），每次操作后前端刷新 providerStore。

### 新建会话流程

```
用户 → NewSessionDialog → API → SessionManager → SessionStore + ProviderStore
```

用户打开新建会话对话框，对话框显示当前全局选中的提供商和模型（只读展示，不可修改）。若无全局选中，对话框展示提示及跳转设置链接，禁用创建按钮。用户填写 system prompt 后提交，POST /sessions 不再接收 model 字段。后端通过 ProviderStore 解析当前选中的 model_name，存入 session 快照。若全局选中为空，返回 400 错误。

### 消息发送流程

```
SessionManager.send_message()
  → ProviderStore.get_active_selection()
  → ProviderStore.get_provider_config(provider_id)  # 自动解密 api_key
  → OpenAIProvider(config)
  → AgentRunner.run(provider, model=model_name)
```

每次 send_message 运行时获取当前全局选中，保证使用的提供商和模型与当前选中一致。

## API 契约

### 提供商管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/providers | 列出所有提供商（不返回 api_key） |
| POST | /api/v1/providers | 创建提供商（接收 api_key，后端加密存储） |
| GET | /api/v1/providers/{id} | 获取提供商详情（返回 has_api_key: bool） |
| PUT | /api/v1/providers/{id} | 更新提供商（api_key 可选，不传时保留旧值） |
| DELETE | /api/v1/providers/{id} | 删除提供商（级联删除其模型、若为当前选中则清除选中） |

### 模型管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/providers/{id}/models | 列出提供商下的模型 |
| POST | /api/v1/providers/{id}/models | 添加模型 |
| DELETE | /api/v1/providers/{id}/models/{model_id} | 删除模型 |

### 连通性验证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/providers/{id}/test | 验证提供商配置的有效性 |

### 全局选中

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/providers/active | 获取当前全局选中的提供商和模型；若无选中返回 null |
| PUT | /api/v1/providers/active | 设置当前全局选中的提供商和模型 |

### 安全约束

- 所有 GET 响应不返回 api_key 明文，仅返回布尔字段指示是否已配置
- POST/PUT 接收 api_key，后端加密后存储，不再回传
- PUT 时 api_key 为可选字段，不传时保留旧值
- 前端不参与任何加解密逻辑

### 会话 API 变更

GET /api/v1/sessions 和 GET /api/v1/sessions/{id} 的响应中 model 字段仍然返回，值为创建时从全局选中解析的 model_name（session 快照）。该值不随全局选中切换而改变。

POST /api/v1/sessions 移除 model 字段（请求体不再接收），后端通过 ProviderStore 解析当前全局选中的 model_name 并写入 session 快照。若发起请求时全局选中为空，返回 400 错误。

## 错误处理

| 异常 | 触发条件 | HTTP 状态码 | error code |
|------|----------|-------------|------------|
| ProviderNotFoundError | provider_id 不存在 | 404 | PROVIDER_NOT_FOUND |
| ProviderConfigError | API Key 解密失败、配置格式错误 | 500 | PROVIDER_CONFIG_ERROR |
| ProviderConnectionError | 连通性测试连接失败 | 502 | PROVIDER_CONNECTION_ERROR |
| NoActiveProviderError | 发送消息时未选中全局提供商 | 400 | NO_ACTIVE_PROVIDER |
| ModelNotFoundError | model_id 不存在 | 404 | MODEL_NOT_FOUND |
| ModelNameConflictError | 同一提供商下模型名重复 | 409 | MODEL_NAME_CONFLICT |

## 安全边界

- 提供商管理 API 在设计上假定局域网或反向代理保护，不实现前端用户认证
- API Key 不在任何日志、错误消息或响应体中出现
- 前端不存储 api_key，仅在创建/编辑表单中临时持有，提交后丢弃
