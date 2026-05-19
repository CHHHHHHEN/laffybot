# UI 技术选型设计文档

> **最后更新**：2026-05-19
>
> **文档范围说明**：本文档聚焦于 Laffybot UI 的技术选型依据与架构决策。
>
> **配套文档**：视觉规范与交互模式见 `ui-design-spec.md`，组件设计与数据流见 `ui-design.md`，桌面端设计见 `desktop-design.md`。
>
> **本文档不包含以下内容**：
> - 具体实现细节、代码示例和 API 使用方式
> - 开发环境搭建步骤和构建流程
> - 测试策略和测试用例
>
> **适用范围**：本文档讨论的是 Web UI，桌面端相关内容见 `desktop-design.md`。

## 实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 技术选型 | ✅ 已完成 | 本文档 |
| 项目初始化 | ✅ 已完成 | Vite + React + TypeScript + Tailwind 4 脚手架已搭建 |
| 布局框架 (AppShell/Sidebar) | ✅ 已完成 | 含折叠 Sidebar、导航链接、响应式遮罩层 |
| 聊天面板 (ChatView) | ✅ 已完成 | 含 ChatHeader、MessageList、InputBar、流式渲染 |
| 会话管理 (SessionList) | ✅ 已完成 | 内联在 Sidebar 内，非独立组件；支持骨架屏、空状态、删除、滚动加载 |
| Agent 展示组件 | ✅ 已完成 | StreamMessage、ReasoningBlock、ToolCallCard、ToolResultBlock、ScrollToBottomButton、SessionStatusBadge |
| 设置面板 | ✅ 已完成 | 提供商配置对接真实 API；工具管理对接 `GET /api/v1/tools`（只读列表） |
| SSE 集成 | ✅ 已完成 | 基于 fetch + ReadableStream 的 POST-based SSE 实现 |
| Tauri 桌面端 | ✅ 已完成 | 详见 `desktop-design.md`、`tauri-impl-plan.md` |

## 动机

Laffybot 当前仅提供 REST + SSE API，没有可视化界面。设计 UI 的目标是：

1. **完善产品形态** — 提供可直接使用的交互界面，降低使用门槛
2. **展示全部 API 能力** — 会话管理、流式消息、工具调用、推理过程等
3. **为未来服务提供容器** — MCP、Skill、RAG、Memory 等后续服务需要统一的 UI 承载层

## 技术选型

### 最终方案

| 层面 | 选型 | 版本 |
|------|------|------|
| 框架 | React | 19 |
| 构建工具 | Vite | 最新 |
| 语言 | TypeScript | 6.x |
| 样式 | Tailwind CSS | 4 |
| 图标 | lucide-react | 最新 |
| 路由 | React Router | 7.x |
| 状态管理 | Zustand + TanStack Query | 最新 |
| 消息渲染 | react-markdown | 最新 |
| 类名合并 | clsx + tailwind-merge | 最新 ✅ |
| 表单处理 | react-hook-form + zod | 最新 ✅ |
| 通知 | sonner | 最新 ✅ |
| 日期处理 | date-fns | 最新 ✅ |
| 类型生成 | openapi-typescript | 已否决（见下方说明） |
| PWA | vite-plugin-pwa | 最新 |

### 选型依据

#### React vs 其他框架

React 的选择基于三个核心考量：

**AI 辅助能力**：React/TSX 在所有 AI 模型（GPT、Claude、Cursor 等）的训练数据中占比最大，AI 生成 React 代码的质量和准确性显著优于其他框架。本项目后续开发高度依赖 AI 辅助，这一优势直接影响开发效率和代码质量。

**生态成熟度**：React 拥有最丰富的第三方组件库和工具链，Markdown 渲染（react-markdown）、代码高亮（rehype-highlight）、SSE 处理、桌面端（Tauri）等所有潜在需求都有成熟的 React 封装。

**架构适配性**：React 的组件模型天然适配面板式布局（见下文架构部分），每个未来服务可作为独立组件树开发，互不耦合。

#### SPA vs SSR

选择 SPA（Vite）而非 SSR（Next.js）的原因：

- 聊天界面不需要 SEO
- 初始加载时间对聊天应用不关键
- SSE 流式渲染在 SPA 中更简单直接
- 桌面端 Tauri 加载的是静态文件，SPA 天然兼容

#### shadcn/ui vs 其他组件库

选择 shadcn/ui 而非 Ant Design、Chakra UI 等传统组件库的原因：

- **组件归你所有**：shadcn/ui 的组件是复制到项目中的源代码，而非 npm 依赖。你可以直接修改任何组件的行为和样式，不受上游 breaking change 影响
- **基于 Tailwind**：与项目的样式体系一致，定制成本低
- **设计质量**：组件遵循现代设计规范，视觉效果精致

**实际实现状态**：shadcn/ui 未落地。项目改用手写组件（Button、Modal、Input、Collapsible 等），使用 Tailwind 自定义 CSS 变量保持样式一致。2026-05-19 补齐基础构建库时引入了 `@radix-ui/react-dialog`、`@radix-ui/react-collapsible` 等底层原语，并使用 `clsx` + `tailwind-merge`（`cn()` 工具函数）、`react-hook-form` + `zod`（ProviderForm 表单校验）、`sonner`（Toast 通知替换）、`date-fns`（日期格式化）补齐了前端基础依赖。

#### Zustand + TanStack Query 并存策略

本项目的状态管理采用 **TanStack Query 处理服务端数据 + Zustand 处理客户端状态** 的双轨方案：

**TanStack Query（服务端数据层）**：
- 处理会话列表/详情查询、创建/删除 mutations
- 处理提供商/模型 CRUD 和当前选中状态
- 提供免费缓存、去重、后台刷新、乐观更新
- 消除手动 `isLoading`/`error` 状态管理

**Zustand（客户端状态层）**：
- `chat-store`：消息流缓冲区、SSE 连接状态（流式客户端状态不适合缓存）
- ~~`toast-store`~~：已由 `sonner` 替换（2026-05-19）
- `ui-store`：侧边栏折叠、主题偏好

**否决的方案**：
- **纯 TanStack Query**：SSE 流式推送状态（streamBuffer、isStreaming）不适合查询缓存模型
- **纯 Zustand**：需要手动管理缓存、去重、乐观更新回滚、loading/error 样板代码
- **Redux**：样板代码过多，不适合本项目规模
- **Jotai**：原子化状态管理适合表单密集型应用，但本项目的状态模型更适合按领域拆分

## 架构设计

### 路由架构

使用 React Router 管理所有视图的路由和导航：

```
/chat                  聊天主面板
/settings              设置面板
/settings/provider     提供商配置
/settings/tools        工具管理

[future]
/mcp                   MCP 管理
/skills                Skill 配置
/rag                   RAG 知识库
/memory                Memory 浏览器
```

### 设计依据

**为什么用 React Router**：

- **规范化路由管理** — 所有视图入口统一在路由表中定义，新增面板只需添加一条路由声明，避免视图散落在条件渲染中
- **URL 可寻址** — 支持直接通过 URL 定位到设置页、未来服务面板等深层视图，方便分享和书签
- **嵌套路由** — 支持设置页、服务面板等场景下的子页面/选项卡结构（如 `/settings/provider`、`/settings/tools`）
- **布局复用** — 通过 `layout route` 统一管理 Sidebar + MainPanel 的布局骨架，子路由自动继承
- **代码分割** — React Router 配合 `React.lazy` 实现按路由懒加载，避免首屏加载不必要的代码

**扩展方式**：
```
新增一个服务面板的流程:
1. 创建 components/<service>/<ServiceView>.tsx
2. 在路由表中添加一条 route
3. 在 Sidebar 中添加导航链接

无需修改: 布局组件、状态管理、构建配置
```

### 桌面端策略

UI 使用标准 Web API，构建产物为纯静态文件。Tauri v2 直接加载 `dist/` 目录作为 WebView 内容，无需任何前端代码改动：

```
Vite build  →  dist/  ──→  Tauri v2 (desktop)
                           ├── 开发阶段: pnpm tauri dev
                           └── 构建阶段: pnpm tauri build
```

桌面端的详细架构设计、安全模型、扩展规划见 `desktop-design.md`。

### PWA 支持

通过 `vite-plugin-pwa` 实现：
- Service Worker 缓存应用资源，支持离线启动
- manifest.json 支持添加到主屏幕（移动端）
- 为未来桌面端 Tauri 提供渐进过渡路径

### 类型安全的 API 契约

~~使用 `openapi-typescript` 从 FastAPI 的 OpenAPI 规范自动生成 TypeScript 类型：~~

**实现中并未使用 `openapi-typescript`。** 当前 API 类型（`SessionResponse`, `HistoryMessage`, `SseEvent` 等）直接在 `ui/src/lib/api.ts` 中手写定义，理由是：

- 当前后端在 `/docs` 路径提供了 Swagger UI，但 `openapi.json` 路径不定，维护自动生成脚本的成本超过了手动维护少量类型定义的成本
- API 接口层当前较稳定，类型变更频率低
- 如后续 API 大幅扩张，可重新评估是否引入 `openapi-typescript`

## 组件树结构

```
App (RouterProvider)
└── Routes
    └── Layout Route (AppShell)   # 布局骨架: Sidebar + Outlet
        ├── ErrorBoundary         # React 错误边界
        ├── Toaster (sonner)      # 全局 Toast 通知
        │
        ├── Sidebar               # 侧边栏导航 + 会话列表（内联）
        │   ├── NavLinks          # 路由导航链接列表
        │   ├── NewSessionDialog  # 新建会话弹窗（基于 Modal + Button + Input）
        │   ├── ConfirmDialog     # 删除确认弹窗（基于 Modal + Button）
        │   └── 会话列表（内联）
        │
        └── Outlet                # 子路由渲染出口
            ├── /chat             →  ChatPage
            │   ├── ChatHeader (基于 Button)
            │   ├── ConnectionStatusBanner
            │   ├── MessageList
            │   │   └── MessageBubble
            │   │       └── StreamMessage
            │   │           ├── ReasoningBlock（基于 Collapsible）
            │   │           ├── ToolCallCard / ToolResultBlock
            │   │           └── react-markdown 渲染
            │   ├── InputBar (基于 Button + Textarea)
            │   └── ScrollToBottomButton
            │
            ├── /settings         →  SettingsPage
            │   ├── /settings/provider  →  ProviderSettingsPage（对接真实 API）
            │   │   ├── ProviderForm（基于 Modal + Button + Input）
            │   │   └── ModelList（基于 Button + Input）
            │   └── /settings/tools     →  ToolSettingsPage（对接真实 API）
            │
            └── [future] /mcp     →  MCPView
                /skills           →  SkillsView
                /rag              →  RagView
                /memory           →  MemoryView
```

## 数据流

### 消息发送与 SSE 流式响应

```
User Input  →  InputBar
                  ↓
              api.ts (POST /sessions/{id}/messages)
                  ↓
              FastAPI 返回 SSE stream
                  ↓
              sse.ts (parse events)
                  ↓
              chat-store.ts (append messages & update stream state)
                  ↓
              StreamMessage → 逐 token 追加渲染
```

### 状态分布

| State Layer | 职责 | 状态示例 | 技术 |
|-------------|------|----------|------|
| `chat-store` | 当前会话的消息流、SSE 连接状态、流式追加缓冲区 | messages, isStreaming, streamBuffer | Zustand |
| `ui-store` | 主题、侧边栏状态 | theme, sidebarOpen | Zustand |
| `sonner` | Toast 通知（替换 `toast-store`） | — | 外部库 |
| `use-sessions` hooks | 会话列表 CRUD + 分页加载 | sessions[], isLoading | TanStack Query |
| `use-providers` hooks | 提供商/模型 CRUD + 全局选中 | providers[], models{}, activeSelection | TanStack Query |

路由状态由 React Router 统一管理，不纳入 Zustand。`useParams`、`useSearchParams` 等路由 API 直接从 React Router 获取。

## 拓展性分析

### 已知拓展场景的支持

| 场景 | 支持方式 | 影响范围 |
|------|----------|----------|
| 新增服务面板 (MCP/Skill/RAG/Memory) | 新增组件 + 路由表注册 + 导航链接 | 仅新增文件 + 1 条路由声明 |
| 桌面端 (Tauri v2) | 直接加载 dist/，详见 `desktop-design.md` | 新增 src-tauri/ 目录 |
| 用户认证 | api.ts 新增请求拦截器 | 仅 lib/api.ts |
| 主题定制 | Tailwind CSS 变量覆盖 + shadcn/ui CSS 变量 | 全局样式表 |
| 国际化 | react-i18next Provider 包裹 | 新增 locales/ + 组件包裹 |
| 后端 API 变更 | 重新生成 openapi-typescript | 全量类型检查 |
| 代码分割 | Vite 动态导入 + React.lazy | 按需新增 |

### 非目标

以下场景不在当前设计范围内，且不推荐用当前架构解决：

- **微前端**：项目规模不需要多团队独立部署
- **SSR/SSG**：聊天界面不需要 SEO
- **多实例状态同步**：非 WebSocket 实时协作场景
- **原生移动端**：PWA 足够覆盖大部分移动端需求；如需原生能力，可基于同一 API 层开发 React Native 应用

## 否决的方案

### ReactPy

基于 Python 的 React 实现。否决原因：
- 仍处于 Beta 阶段，文档不完整
- 无 SSE/流式原生支持，需手动桥接
- AI 模型对该框架的训练数据极少

### Gradio

HuggingFace 出品的 ML Demo 框架。否决原因：
- 难以嵌入现有 FastAPI 应用
- 自定义 UI 能力受限，无法满足工具调用、推理过程等复杂展示需求
- 不适合作为长期产品的 UI 基础

### FastHTML + HTMX

Python 全栈方案。否决原因：
- 工具调用卡片、流式逐 token 渲染、推理过程折叠等复杂交互用 HTMX 实现后，复杂度随交互密度指数上升
- AI 辅助能力不足
- 无桌面端方案

### Svelte

否决原因（相对于 React）：
- AI 训练数据量约为 React 的 1/10，AI 辅助生成质量差距明显
- 组件库生态不如 React 丰富
- shadcn-svelte 成熟度不如原版

---

> Implementation record: see `docs/archive/architecture-remediation-plan-2026-05-19.md`
