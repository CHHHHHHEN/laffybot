# 桌面端实现方案

## 参考文档
- `docs/ui/desktop-design.md` — 桌面端技术选型与架构设计
- `docs/ui/ui-tech-selection.md` — Web UI 技术栈
- `docs/ui/ui-design.md` — 组件设计与数据流

## 前置条件

- Rust 工具链：`rustc` ≥ 1.80，`cargo` 对应版本
- Linux 额外依赖（Arch Linux 已预装多数）：`webkit2gtk-4.1` `libayatana-appindicator` `librsvg`
- Node.js ≥ 20，pnpm ≥ 9

### Windows 构建额外依赖

| 依赖 | 说明 | 安装方式 |
|------|------|----------|
| WebView2 | Win10 1803+ 已内置（无须额外安装） | — |
| Visual Studio Build Tools | C++ 编译工具链 | `winget install Microsoft.VisualStudio.2022.BuildTools --includeRecommended` |
| WiX Toolset v3 | MSI 安装器（如使用 `wix`） | `dotnet tool install --global wix` |
| 或 NSIS | 轻量安装器（如使用 `nsis`） | `winget install NSIS.NSIS` |

> Tauri v2 默认使用 WiX 生成 MSI。如不想安装 WiX，可在 `tauri.conf.json` 中切换为 NSIS（见步骤 6b）。

## 阶段一：初始实现

### 步骤 1：搭建 Tauri v2 项目骨架

在 `ui/` 目录下初始化 `src-tauri/`：

```
ui/src-tauri/
├── Cargo.toml           # Tauri + Rust 依赖
├── tauri.conf.json      # 窗口配置、构建、CSP
├── build.rs             # Tauri 构建脚本
├── src/
│   ├── main.rs          # Rust 入口
│   └── lib.rs           # Tauri 应用定义
├── capabilities/
│   └── default.json     # 权限声明
└── icons/               # 多平台图标（由命令自动生成）
```

**关键配置**：
- `tauri.conf.json`：`build.frontendDist` 指向 `../dist`，`build.devUrl` 指向 Vite 开发服务器地址
- `tauri.conf.json`：`build.beforeDevCommand` / `beforeBuildCommand`，确保 `pnpm tauri dev` 自动启动 Vite
- `tauri.conf.json`：窗口标题 "Laffybot"，默认尺寸 1200×800
- `tauri.conf.json`：CSP（见步骤 4），`security.csp` 在 `tauri.conf.json` 中配置
- `capabilities/default.json`：权限声明（见步骤 4）

`tauri.conf.json` 基础示例：

```json
{
  "productName": "Laffybot",
  "version": "0.1.0",
  "identifier": "com.laffybot.desktop",
  "build": {
    "frontendDist": "../dist",
    "devUrl": "http://localhost:1420",
    "beforeDevCommand": "pnpm dev",
    "beforeBuildCommand": "pnpm build"
  },
  "app": {
    "windows": [
      {
        "title": "Laffybot",
        "width": 1200,
        "height": 800
      }
    ]
  }
}
```

**`.gitignore` 需新增**：`ui/src-tauri/target/`（Rust 编译产物，体积较大，不应提交到仓库）

### 步骤 1b：调整 Vite 配置以兼容 Tauri 开发模式

在 `vite.config.ts` 中添加 Tauri 开发必需的配置：

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://v2.tauri.app/start/frontend/vite/
const host = process.env.TAURI_DEV_HOST

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({ ... }),
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? { protocol: 'ws', host, port: 1421 }
      : undefined,
    watch: {
      ignored: ['**/src-tauri/**'],
    },
  },
  envPrefix: ['VITE_', 'TAURI_'],
})
```

| 配置 | 作用 |
|------|------|
| `clearScreen: false` | 防止 Vite 清屏覆盖 Tauri 日志输出 |
| `server.port: 1420` | 固定端口，与 `tauri.conf.json` 的 `build.devUrl` 对齐 |
| `server.strictPort: true` | 端口被占时直接报错而非自动切换，避免 Tauri 连不上 |
| `server.host` | 配合 `TAURI_DEV_HOST` 环境变量支持移动端/局域网测试 |
| `server.hmr` | 显式配置 HMR，确保 Tauri WebView 内热更新正常 |
| `server.watch.ignored` | 排除 `src-tauri/` 目录，避免 Rust 文件变动触发 Vite 重载 |
| `envPrefix` | 暴露 `TAURI_*` 环境变量给前端代码，用于构建时判断环境 |

> `clearScreen`、`strictPort`、`hmr`、`envPrefix` 等配置仅影响开发体验，不影响生产构建。

### 步骤 2：添加 Tauri 相关依赖

```bash
pnpm add -D @tauri-apps/cli@^2
pnpm add @tauri-apps/api@^2
```

- `@tauri-apps/cli` (devDependency) — `pnpm tauri dev`/`build`
- `@tauri-apps/api` (dependency) — 前端代码中通过 `window.__TAURI__` 判断运行环境，或调用 `invoke`/`event` 等 Tauri API
- `ui/package.json` 新增 script: `"tauri": "tauri"`

### 步骤 3：配置开发工作流

> **重要**：`pnpm tauri dev` 会自动启动 Vite 开发服务器并打开 Tauri WebView，但**后端需在另一个终端中手动启动**。

- 终端 1：`laffybot serve` — 启动 FastAPI 后端
- 终端 2：`pnpm tauri dev` — 启动 Vite + Tauri WebView
- 构建期：`pnpm tauri build` → `vite build` → 打包安装程序
- 前端代码零改动，所有桌面逻辑在 `src-tauri/` 侧实现

### 步骤 4：权限与安全配置

Tauri v2 有两层安全机制，需同时配置：

**4.1 Capabilities（权限声明）**

`capabilities/default.json`：

```json
{
  "identifier": "default",
  "description": "Default capabilities",
  "windows": ["main"],
  "permissions": [
    "core:default"
  ]
}
```

- `core:default` — 基础窗口管理
- **不需要 `http:default` 或 HTTP 插件权限**。前端使用标准 Web `fetch()` API 请求 `localhost:8000`，WebView 原生支持 HTTP 请求，不受 capabilities 管控，仅受 CSP 限制。Tauri 的 HTTP 插件（`tauri-plugin-http`）用于 Rust 侧发请求，与本项目无关。

**4.2 CSP（内容安全策略）**

`tauri.conf.json` 中配置：

```json
"security": {
  "csp": "connect-src 'self' http://localhost:8000 https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-eval'"
}
```

### 步骤 5：图标资源

```bash
# 将一张 1024×1024 的 PNG 源图放在 src-tauri/ 下
pnpm tauri icon src-tauri/app-icon.png
```

此命令自动生成全平台所需格式（macOS .icns、Windows .ico、Linux .png、.ico），输出到 `src-tauri/icons/`。

### 步骤 6：验证

```bash
# 终端 1：启动后端
laffybot serve

# 终端 2：启动 Tauri 桌面端
pnpm tauri dev
```

验证清单：
- [ ] WebView 窗口正常打开，标题 "Laffybot"，尺寸 1200×800
- [ ] React SPA 完整加载，路由导航正常
- [ ] WebView 控制台**无 capability 或 CSP 相关报错**
- [ ] 发送消息 → SSE 流式渲染正常
- [ ] 工具调用卡片正常显示

### 步骤 6b：配置 Windows 安装器

Windows 安装包仅在 Windows 平台或 GitHub Actions `windows-latest` runner 上构建。`tauri.conf.json` 中的 `bundle` 配置：

```json
{
  "bundle": {
    "active": true,
    "targets": ["deb", "appimage", "msi", "nsis"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "windows": {
      "wix": {
        "language": "zh-CN",
        "template": null,
        "fragment": null,
        "componentRefs": []
      },
      "nsis": null
    }
  }
}
```

**选项说明**：

| 安装器 | 优点 | 缺点 | 选择建议 |
|--------|------|------|----------|
| `wix`（默认） | 原生 MSI，企业可批量部署 | 需安装 WiX Toolset；构建慢 | 需要 MSI 时用 |
| `nsis` | 无需额外工具链；构建快 | 非 MSI 格式 | 开发阶段试用首选 |

将不需要的安装器置为 `null` 即可禁用。例如只用 NSIS：

```json
"windows": {
  "wix": null,
  "nsis": {}
}
```

> 用户**安装后**首次启动时需自己运行 `laffybot serve` 启动后端（阶段一限制，阶段二 Sidecar 解决）。

## 跨平台构建策略

| 目标平台 | 构建主机 | CI runner |
|----------|---------|-----------|
| Linux (.deb, .AppImage) | Arch Linux | `ubuntu-latest` |
| Windows (.msi, .exe) | Windows | `windows-latest` |
| macOS (.dmg) | macOS | `macos-latest` |

当前开发在 Arch Linux 上，阶段一仅验证 Linux 构建。Windows/macOS 打包在阶段二引入 CI 时统一处理。

## UI 侧需要的改动

- 检测运行环境：通过 `window.__TAURI__` 是否存在判断 Web vs Tauri
- 如需在 Tauri 下调用原生 API，引入 `@tauri-apps/api`（参考步骤 2）
- 其余前端代码无需修改

## 阶段二：后续增强（规划）

按优先级排序：

1. **Python Sidecar** — Tauri 自动管理后端进程生命周期
   - 检测后端端口是否可用，不可用时自动启动
   - 窗口关闭时自动终止后端进程
2. **系统托盘** — 最小化到系统托盘，后台运行
3. **全局快捷键** — `Ctrl+Shift+L` 快速唤醒窗口
4. **原生文件对话框** — 替代 `<input type="file">`
5. **自动更新** — 基于 GitHub Releases + `@tauri-apps/plugin-updater`
6. **原生菜单** — 应用菜单栏（文件/编辑/视图/帮助）
7. **深色模式同步** — 跟随系统主题切换

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Tauri v2 仍在迭代，API 可能变动 | 中 | 中 | 锁定 `@tauri-apps/cli` v2.x 版本，在 Cargo.toml 中用 `tauri = "2"` 锁定大版本 |
| 后端端口被占用 | 低 | 低 | 后端已有端口配置机制，可在 tauri.conf.json 中配置环境变量覆盖 |
| Linux WebView 兼容性（WebKitGTK） | 中 | 中 | Arch Linux 开发环境已验证。如遇问题，升级 `webkit2gtk` 至最新 |
| Tauri v2 HTTP 请求跨域/权限拦截 | 中 | 高 | 开发阶段如遇请求失败，优先检查 CSP 而非 capabilities（标准 fetch 不受 capabilities 管控）；Tauri WebView origin 为 `tauri://localhost`，后端需允许该 origin |

## 架构图

```
┌─────────────────────────────────────────────────────┐
│                  Tauri Desktop App                   │
│  ┌───────────────────────────────────────────────┐  │
│  │           WebView (系统 WebView)               │  │
│  │  ┌─────────────────────────────────────────┐  │  │
│  │  │     React SPA (from ui/dist/)           │  │  │
│  │  │                                          │  │  │
│  │  │  Zustand stores ←→ fetch API ──────┐    │  │  │
│  │  │  TanStack Query                    │    │  │  │
│  │  └────────────────────────────────────│────┘  │  │
│  └───────────────────────────────────────│───────┘  │
└──────────────────────────────────────────│──────────┘
                                           │ HTTP/SSE
                                  ┌────────┴────────┐
                                  │  laffybot server │
                                  │  (uvicorn :8000) │
                                  │                  │
                                  │  FastAPI + SSE   │
                                  └──────────────────┘
```
