# Laffybot UI 设计文档

> **文档范围说明**：本文档聚焦于 Laffybot UI 的交互设计、组件职责和数据流。
>
> **配套文档**：视觉规范（色彩、字体、间距、动画等）见 `ui-design-spec.md`。
>
> **适用范围**：本文档讨论的是 Web UI 的交互设计，不涉及具体实现细节和代码示例。

## 实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 页面结构设计 | ✅ 已完成 | 本文档 |
| 组件设计 | ✅ 已完成 | 本文档 |
| 交互与状态设计 | ✅ 已完成 | 本文档 |
| 实现 | ⏳ 未开始 | |

## 页面结构

### 路由规划

```
/chat                    聊天主面板（默认页，/ 重定向到 /chat）
/chat/:sessionId         指定会话的聊天视图
/settings                设置面板根（重定向到 /settings/provider）
/settings/provider       提供商配置
/settings/tools          工具管理
```

### 布局骨架

整体采用 **左侧 Sidebar + 右侧 Main Panel** 的双栏布局：

```
┌──────────────────────────────────────────────────┐
│  Sidebar                     │  Main Panel       │
│  ┌─────────────────┐         │  ┌──────────────┐ │
│  │  Logo / Brand    │         │  │              │ │
│  │  New Chat 按钮   │         │  │   Outlet     │ │
│  │  ─────────────── │         │  │   (子路由)   │ │
│  │  导航链接        │         │  │              │ │
│  │  · 聊天          │         │  │              │ │
│  │  · 设置          │         │  │              │ │
│  │  ─────────────── │         │  │              │ │
│  │  会话列表        │         │  │              │ │
│  │  ┌─────────────┐ │         │  │              │ │
│  │  │ SessionItem │ │         │  │              │ │
│  │  │ SessionItem │ │         │  │              │ │
│  │  │ SessionItem │ │         │  │              │ │
│  │  └─────────────┘ │         │  │              │ │
│  └─────────────────┘         │  └──────────────┘ │
└──────────────────────────────────────────────────┘
```

Sidebar 支持折叠，折叠后只显示图标，为聊天区域提供更多空间。

## 页面设计

### 1. 聊天页（/chat, /chat/:sessionId）

#### 无会话状态（/chat）
- 居中展示欢迎区域
- 显示"新建会话"按钮作为主要 CTA
- 可展示快速使用提示或示例

#### 有会话状态（/chat/:sessionId）
```
┌──────────────────────────────────────────────┐
│  会话标题栏                                    │
│  [← 返回列表]  [模型名]  [状态标签]  [...]    │
├──────────────────────────────────────────────┤
│                                              │
│  消息列表                                     │
│  ┌──────────────────────────────────────────┐│
│  │  ... 历史消息滚动区域                     ││
│  │                                          ││
│  │  ┌──────────────────┐  ← 用户消息       ││
│  │  │ 用户消息内容      │   右对齐           ││
│  │  └──────────────────┘                    ││
│  │                                          ││
│  │  ┌──────────────────┐  ← 助手消息       ││
│  │  │ ╭┄┄┄┄┄┄┄┄┄┄┄┄┄╮│   左对齐           ││
│  │  │ ┊ 推理过程      ┊│  ⇅ 可折叠        ││
│  │  │ ╰┄┄┄┄┄┄┄┄┄┄┄┄┄╯│                    ││
│  │  │ Markdown 渲染    │   流式逐 token    ││
│  │  │                  │   更新             ││
│  │  │ ┌──────────────┐│  ← 工具调用卡片   ││
│  │  │ │ 🔧 工具名    ││   可展开参数      ││
│  │  │ │ arguments...  ││                   ││
│  │  │ └──────────────┘│                    ││
│  │  │ ┌──────────────┐│  ← 工具结果       ││
│  │  │ │ ✅ 执行成功   ││   耗时标记        ││
│  │  │ │ result...     ││                   ││
│  │  │ └──────────────┘│                    ││
│  │  └──────────────────┘                    ││
│  └──────────────────────────────────────────┘│
│                                              │
├──────────────────────────────────────────────┤
│  [输入框]                          [发送/取消]│
└──────────────────────────────────────────────┘
```

### 2. 设置页（/settings, /settings/provider, /settings/tools）

设置页通过侧边栏内的次级导航切换子页面：

```
┌──────────────────────────────────────────────────┐
│  Sidebar                     │  Main Panel       │
│  ┌─────────────────┐         │  ┌──────────────┐ │
│  │  ... 导航链接     │         │  │  设置面板标题  │ │
│  │  ─────────────── │         │  │              │ │
│  │  设置            │         │  │  ┌────────┐  │ │
│  │  ├ 提供商配置 ← 高亮│       │  │  │ 提供商A  │  │ │
│  │  └ 工具管理      │         │  │  │ 名称     │  │ │
│  │  ─────────────── │         │  │  │ Base URL │  │ │
│  │  ... 会话列表     │         │  │  │ 模型列表  │  │ │
│  │                  │         │  │  │ [编辑删除]│  │ │
│  └─────────────────┘         │  │  ├────────┤  │ │
│                              │  │  │ 提供商B  │  │ │
│                              │  │  │ ...     │  │ │
│                              │  │  └────────┘  │ │
│                              │  │  [+ 添加提供商]│ │
│                              │  └──────────────┘ │
└──────────────────────────────────────────────────┘
```

列表/表单布局：设置项以卡片列表形式展示，编辑/添加在对话框或内联展开中完成。

#### 提供商配置（/settings/provider）
- 当前配置的 LLM 提供商列表
- 每个提供商展示：名称、API 基础 URL、模型列表
- 添加/编辑/删除提供商
- 模型名称为自由文本输入（由用户填写提供商支持的模型标识）

#### 工具管理（/settings/tools）
- 可用工具列表
- 每个工具展示：名称、描述、启用/禁用开关
- 工具的详细配置参数（如文件路径白名单、超时时间等）

> **API 依赖说明**：提供商配置和工具管理页面的增删改操作依赖对应的管理 API。当前后端仅提供会话和消息相关端点，提供商和工具的运行时配置通过服务端 config.json 管理。这些页面的实现在 API 就绪前以只读展示为主，写操作（添加/编辑/删除/启用/禁用）待后续补充 API 后接入。

## 组件设计

### 组件职责边界

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `AppShell` | 整体布局骨架，管理 Sidebar + Main Panel | 无 | 无 |
| `Sidebar` | 导航 + 会话列表容器 | sessions, activeSessionId | onSelectSession, onNewSession |
| `SessionList` | 展示所有会话，支持分页加载 | sessions[], isLoading, error | onSelect, onDelete |
| `SessionItem` | 单个会话卡片 | session, isActive | onClick, onDelete |
| `NewSessionDialog` | 创建会话的表单对话框 | isOpen, modelOptions[] | onConfirm, onCancel |
| `ChatHeader` | 当前会话信息标题栏 | session, status | onBack |
| `MessageList` | 消息容器，管理滚动 | messages[], isStreaming | onScroll |
| `MessageBubble` | 单条消息渲染 | message | 无 |
| `StreamMessage` | 流式消息内容区域 | text, reasoning[], toolCalls[] | 无 |
| `ReasoningBlock` | 推理过程折叠展示 | text, isStreaming | 无 |
| `ToolCallCard` | 工具调用卡片 | name, arguments, status | 无 |
| `ToolResultBlock` | 工具执行结果 | name, result, success, duration | 无 |
| `InputBar` | 输入与发送/取消 | isStreaming, disabled | onSubmit, onCancel |
| `ProviderSettings` | 提供商配置管理 | providers[] | onAdd, onEdit, onDelete |
| `ToolSettings` | 工具管理 | tools[] | onToggle, onConfigure |

| `ScrollToBottomButton` | 用户上滚后出现的"回到最新"浮动按钮 | visible, onClick | 无 |
| `ConnectionStatusBanner` | 连接状态提示横幅 | status (connected/disconnected/reconnecting), message | 无 |
| `Toast` | 瞬态通知容器 | toasts[] | onDismiss |
| `ConfirmDialog` | 破坏性操作确认弹窗 | isOpen, title, description, confirmLabel, variant | onConfirm, onCancel |
| `SessionStatusBadge` | 会话状态标签 | status (idle/busy/error), sessionId | 无 |

### 关键组件状态

#### SessionList
- **Loading**: 骨架屏占位，3-4 个灰色条
- **Empty**: 空状态提示 + "创建第一个会话" 按钮
- **Error**: 错误提示 + 重试按钮
- **Normal**: 按创建时间降序排列的会话列表
- **Edge Cases**:
  - 会话名过长 → 单行截断加省略号
  - 会话数量过多 → 滚动加载（基于 limit/offset 分页）
  - 状态为 busy/error 的会话 → 状态标签和颜色标识

#### MessageList
- **Loading**: 区域居中加载指示器（获取历史消息时）
- **Empty**: 首次会话 → 欢迎提示；已有会话但无消息 → 提示发送第一条消息
- **Normal**: 消息列表，自动滚动到底部
- **Streaming**: 实时逐 token 更新最后一条助手消息，自动跟随滚动
- **Error**: 错误消息气泡，含重试/删除操作
- **Edge Cases**:
  - 用户手动上滚 → 暂停自动跟随，显示"回到最新"浮动按钮
  - 大量连续 tool_call + tool_result → 折叠展示，减少视觉噪音
  - 大段代码块 → 代码高亮 + 复制按钮

#### InputBar
- **Idle**: 空文本区域 + 发送按钮（禁用状态）
- **Ready**: 有输入文本 + 发送按钮（可点击）
- **Streaming**: 输入框禁用 + 取消按钮（可点击）
- **Disabled**: 输入框禁用 + 发送按钮禁用（会话 busy 但非当前窗口发起的请求）
- **Edge Cases**:
  - 空内容或纯空白提交 → 阻止发送
  - 非常长输入 → 自动增长高度，最大高度限制后出现滚动
  - Enter 发送 / Shift+Enter 换行

## 数据流

### 消息发送与 SSE 流式渲染

```
InputBar 提交
    │
    ▼
创建用户消息 → 立即追加到 MessageList（乐观更新）
    │
    ▼
POST /sessions/{id}/messages → 建立 SSE 连接
    │
    ▼
    开始接收 SSE 事件流
    │
    ├── session_start → 记录 request_id，标记会话为 busy
    ├── content      → 追加 token 到当前助手消息的文本缓冲区
    │                   并触发 MessageBubble 重新渲染
    ├── reasoning    → 追加到推理过程缓冲区，ReasoningBlock 实时更新
    ├── tool_call    → 创建 ToolCallCard，显示工具名和参数
    ├── tool_result  → 更新对应的 ToolCallCard 为完成状态
    │                   显示执行结果和耗时
    ├── done          → 标记消息完成，更新 usage 和 tools_used 信息
    │                   关闭 SSE 连接，标记会话为 idle
    ├── error         → 显示错误消息，标记会话为 error
    ├── cancelled     → 标记消息为中断状态，标记会话为 idle
    └── ping          → 忽略，无操作
```

### 会话切换

```
用户点击 Sidebar 中的会话
    │
    ▼
React Router 导航到 /chat/:sessionId
    │
    ▼
GET /sessions/{id}/history?limit=50 → 加载历史消息
    │
    ▼
更新 chat-store 中的 messages 列表
    │
    ▼
MessageList 渲染历史消息，滚动到底部
```

### 新建会话

```
用户点击"新建会话"按钮
    │
    ▼
打开 NewSessionDialog
    │
    ▼
用户选择/输入 model（自由文本输入，
同时展示最近使用过的模型作为建议列表）
用户填写: system_prompt（可选） + max_iterations
    │
    ▼
POST /sessions → 创建会话
    │
    ▼
更新 session-store 追加新会话
    │
    ▼
导航到 /chat/{new_session_id}
    │
    ▼
关闭对话框，聚焦输入框
```

### 删除会话

```
用户点击 SessionItem 的删除按钮
    │
    ▼
打开 ConfirmDialog（标题："删除会话"，
描述：确认删除后将无法恢复）
    │
    ▼
用户确认
    │
    ├── 删除当前活跃会话 → 从列表移除 → 导航到 /chat
    └── 删除非活跃会话 → 从列表移除 → 保持当前视图
    │
    ▼
DELETE /sessions/{id}
    │
    ├── 成功 → 从 session-store 移除该会话（乐观更新）
    └── 失败 → 回滚列表，Toast 通知错误
```

## 状态管理分布

### Store 职责

| Store | 职责 | 关键状态 |
|-------|------|----------|
| `session-store` | 会话列表 CRUD、当前活跃会话 | sessions[], activeSessionId, isLoading, error |
| `chat-store` | 当前会话的消息流、SSE 连接、流式追加 | messages[], connectionStatus (disconnected/connecting/connected/error), streamBuffer, activeRequestId |
| `ui-store` | UI 偏好 | sidebarOpen, theme |

### Session Store 状态转换

```
IDLE
  │  请求列表 → loading=true → 完成 → loading=false
  │  创建会话 → 追加到列表首部
  │  删除会话 → 从列表中移除
  │  切换会话 → activeSessionId = newId
  │
  └── ERROR ← 请求失败 → 设置 error
```

### Chat Store 流式状态

connectionStatus 作为独立层，与消息流状态正交：

```
connectionStatus: disconnected
  │  发送消息 → connecting → 建立 SSE → connected
  │
connectionStatus: connected
  │  SSE 非正常断开 → disconnected（保留已接收消息）
  │  done/cancelled 事件 → 关闭连接 → disconnected
  │
connectionStatus: connecting
  │  连接建立 → connected
  │  连接超时/失败 → error
```

```
IDLE
  │  发送消息 → 追加用户消息 → 建立 SSE → STREAMING
  │  加载历史 → loading=true → 完成 → loading=false
  │
STREAMING
  │  content 事件 → 追加到 streamBuffer
  │  reasoning 事件 → 追加到推理缓冲区
  │  tool_call 事件 → 创建工具调用记录
  │  tool_result 事件 → 更新工具调用状态
  │  done (stop_reason=completed) → 刷新消息列表 → IDLE
  │  done (stop_reason=max_iterations) → 刷新消息列表，消息末尾追加"已达到最大迭代次数"提示 → IDLE
  │  error 事件 → 标记错误 → ERROR
  │  cancelled 事件 → 标记中断 → IDLE
  │  取消按钮 → POST cancel → 等待 cancelled 事件
  │  连接断开 → connectionStatus=disconnected，标记流中断 → IDLE
  │
ERROR
  │  发送新消息 → 切换回 IDLE → 发送
```

## 错误处理策略

### 操作错误

| 错误场景 | 用户感知 | 处理方式 |
|----------|----------|----------|
| 创建会话失败 | 对话框内错误提示 | 保持对话框打开，允许重试 |
| 发送消息失败 (4xx) | 消息旁错误标记 | 保留用户消息，显示重发按钮 |
| SSE 连接断开 | 消息标记为中断 | 提示重新发送 |
| 删除会话失败 | Toast 通知 | 静默失败 |
| 取消失败 | Toast 通知 | 静默失败 |
| 加载历史失败 | 内联错误提示 | 显示重试按钮 |
| 会话 busy (409) | 输入栏禁用提示 | 显示"当前会话正在处理"提示 |

### 网络错误

- 请求超时 → 内联错误提示，提供重试
- 服务不可用 → Sidebar 顶部或页面 banner 显示连接状态
- SSE 非正常断开 → 标记当前流为中断，保留已接收内容

### 错误恢复

- 所有列表类操作（会话列表、历史消息）支持手动重试
- 发送消息失败后，用户可重新发送（重新 POST）
- SSE 流中断后，保留已接收的内容，不自动重连（当前 API 不支持断线续传）

## 交互细节

### 滚动行为

1. **默认行为**: 新消息/流式 token 到达时，自动滚动到底部
2. **用户上滚**: 用户手动向上滚动查看历史时，暂停自动跟随
3. **回到最新**: 用户上滚后，底部出现"回到最新"浮动按钮，点击恢复自动跟随
4. **上滚加载更多**: 用户滚动到消息列表顶部时，触发加载更早历史消息（分页参数 `offset` 累加）。加载期间顶部显示加载指示器，无更多消息时显示"已加载全部消息"提示
5. **会话切换**: 切换会话时直接定位到底部（最新消息）

### 流式渲染反馈

1. **文本光标**: 流式渲染中的最后一条助手消息末尾显示闪烁光标
2. **推理过程**: 推理过程中的 ReasoningBlock 显示实时追加的内容
3. **工具调用**: tool_call 事件到达时立即显示卡片，tool_result 到达后更新状态
4. **完成状态**: done 事件到达后，移除光标，渲染完成状态

### 键盘交互

| 操作 | 快捷键 | 生效范围 |
|------|--------|----------|
| 发送消息 | Enter | InputBar 聚焦时 |
| 换行 | Shift+Enter | InputBar 聚焦时 |
| 关闭弹窗/对话框 | Escape | 对话框打开时 |
| 新建会话 | Ctrl+N / Cmd+N | 全局 |
| 切换侧边栏折叠 | Ctrl+B / Cmd+B | 全局 |
| 会话列表导航 | ↑/↓ 方向键 | Sidebar 聚焦时 |
| 进入选中会话 | Enter | Sidebar 聚焦时 |

### 无障碍

- 所有交互元素（按钮、链接、输入框）具备可聚焦和键盘可操作性
- Sidebar 折叠状态下，导航图标带有 `aria-label` 说明
- 流式渲染中的内容区域标记 `aria-live="polite"`，屏幕阅读器可感知增量更新
- 对话框使用焦点陷阱（focus trap），关闭后焦点回到触发元素
- 状态标签（idle/busy/error）使用辅助文字而非仅颜色区分

## 组件颜色分配

| 组件/区域 | 色彩来源 | 说明 |
|-----------|----------|------|
| 用户消息 | 品牌色浅色变体 | 右对齐，区分于助手消息 |
| 助手消息 | 中性色板-次级背景 | 左对齐，主要内容区域 |
| 推理过程 | 推理语义色 | 折叠状态，与普通内容区分 |
| 工具调用 | 中性色板-次级背景 + 边框 | 代码风格卡片 |
| 工具成功 | 成功语义色 | 绿色状态指示 |
| 工具失败 | 错误语义色 | 红色状态指示 |
| 会话状态标签 | 对应语义色 | idle（绿）/ busy（蓝）/ error（红） |

> 色值定义、暗色模式映射及布局约束等视觉规范详见 `ui-design-spec.md`。

## 扩展点

### 新增服务面板流程

1. 创建面板组件（如 `MCPView.tsx`）
2. 在路由表中添加路由声明
3. 在 Sidebar 导航中添加链接

### 新增 SSE 事件类型

chat-store 处理 SSE 事件的部分设计为可扩展的事件分发模式，新增事件类型只需添加对应的事件处理函数，无需修改核心流式处理逻辑。
