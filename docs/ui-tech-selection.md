# UI 技术选型设计文档

> **文档范围说明**：本文档聚焦于 Laffybot UI 的技术选型依据与架构决策。
>
> **本文档不包含以下内容**：
> - 具体实现细节、代码示例和 API 使用方式
> - 开发环境搭建步骤和构建流程
> - 测试策略和测试用例
>
> **适用范围**：本文档讨论的是 Web UI，不涉及 CLI 或其他客户端形式。

## 实现状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 技术选型 | ✅ 已完成 | 本文档 |
| 项目初始化 | ⏳ 未开始 | |
| 布局框架 (AppShell/Sidebar) | ⏳ 未开始 | |
| 聊天面板 (ChatView) | ⏳ 未开始 | |
| 会话管理 (SessionList) | ⏳ 未开始 | |
| Agent 展示组件 | ⏳ 未开始 | |
| 设置面板 | ⏳ 未开始 | |
| SSE 集成 | ⏳ 未开始 | |
| Tauri 桌面端 | 📅 规划中 | 将来阶段 |

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
| 语言 | TypeScript | 5.x |
| 样式 | Tailwind CSS | 4 |
| 组件库 | shadcn/ui | 最新 |
| 图标 | lucide-react | 最新 |
| 路由 | React Router | 7.x |
| 状态管理 | Zustand | 最新 |
| 消息渲染 | react-markdown | 最新 |
| 类型生成 | openapi-typescript | 最新 |
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

#### Zustand vs 其他状态管理

选择 Zustand 而非 TanStack Query / Redux / Jotai 的原因：

- **TanStack Query**：适合以查询缓存为中心的场景。本项目的核心交互是 SSE 流式推送，REST 查调用量小，用 Zustand + fetch 更轻量
- **Redux**：样板代码过多，不适合本项目规模
- **Jotai**：原子化状态管理适合表单密集型应用，但本项目的状态模型（会话列表、消息流、UI 状态）更适合按领域拆分的 store 模式

Zustand 的优势在于轻量、TypeScript 友好、支持多 store 拆分，且 future-proof — 应用变大后可无缝迁移到中间件模式。

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

UI 使用标准 Web API，构建产物为纯静态文件。Tauri 直接加载 `dist/` 目录作为 WebView 内容，无需任何前端代码改动：

```
Vite build  →  dist/  ──→  Tauri (desktop)
                          ├── 开发阶段: cargo tauri dev
                          └── 构建阶段: cargo tauri build
```

### PWA 支持

通过 `vite-plugin-pwa` 实现：
- Service Worker 缓存应用资源，支持离线启动
- manifest.json 支持添加到主屏幕（移动端）
- 为未来桌面端 Tauri 提供渐进过渡路径

### 类型安全的 API 契约

使用 `openapi-typescript` 从 FastAPI 的 OpenAPI 规范自动生成 TypeScript 类型：

```
FastAPI  →  GET /openapi.json  →  openapi-typescript  →  types/schema.ts
```

- 后端新增字段 → 重新生成类型 → TypeScript 编译检查所有调用点
- 消除前后端类型不同步的问题
- 无需手写任何 API 类型定义

## 组件树结构

```
App (RouterProvider)
└── Routes
    └── Layout Route            # 布局骨架: Sidebar + Outlet
        ├── Sidebar             # 侧边栏导航
        │   ├── NavLinks        # 路由导航链接列表
        │   └── SessionList     # 会话列表
        │       └── SessionItem *n
        │
        └── Outlet              # 子路由渲染出口
            ├── /chat           →  ChatView
            │   ├── MessageList
            │   │   └── MessageBubble *n
            │   │       ├── StreamMessage
            │   │       ├── ReasoningBlock
            │   │       ├── ToolCallCard
            │   │       └── ToolResultBlock
            │   └── InputBar
            │
            ├── /settings       →  SettingsView
            │   ├── /settings/provider
            │   └── /settings/tools
            │
            └── [future] /mcp   →  MCPView
                /skills         →  SkillsView
                /rag            →  RagView
                /memory         →  MemoryView
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

| Store | 职责 | 状态示例 |
|-------|------|----------|
| `chat-store` | 当前会话的消息流、SSE 连接状态、流式追加缓冲区 | messages, isStreaming, streamBuffer |
| `session-store` | 会话列表的 CRUD、当前活跃会话 | sessions, activeSessionId, isLoading |
| `ui-store` | 主题、侧边栏状态 | theme, sidebarOpen |

路由状态由 React Router 统一管理，不纳入 Zustand。`useParams`、`useSearchParams` 等路由 API 直接从 React Router 获取。

## 拓展性分析

### 已知拓展场景的支持

| 场景 | 支持方式 | 影响范围 |
|------|----------|----------|
| 新增服务面板 (MCP/Skill/RAG/Memory) | 新增组件 + 路由表注册 + 导航链接 | 仅新增文件 + 1 条路由声明 |
| 桌面端 (Tauri) | 直接加载 dist/ | 新增 src-tauri/ 目录 |
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
