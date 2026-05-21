# Laffybot 打包发行计划

> **目标**：实现桌面应用安装包，内嵌 Python 后端，支持 Linux/Windows/macOS 三平台，通过 GitHub Actions 自动发布。
>
> **技术选型**：Nuitka 编译 + onedir 模式

---

## 1. 设计目标

### 1.1 核心目标

| 目标 | 说明 |
|------|------|
| 一键安装运行 | 用户安装后无需额外配置，无需手动启动后端 |
| 多平台支持 | Linux (.deb/.AppImage)、Windows (.msi/.exe)、macOS (.dmg) |
| 自动发布 | 推送 tag 触发 GitHub Actions，自动构建并发布到 GitHub Releases |
| 后端嵌入 | Python 后端编译为可执行文件，作为 Tauri sidecar 运行 |
| 快速启动 | 后端启动时间 < 2 秒 |

### 1.2 非目标

| 非目标 | 原因 |
|--------|------|
| PyPI 发布 | 本计划聚焦桌面端打包，Python 包发布另行处理 |
| 代码签名 | 首次发布暂不处理，后续可添加 |
| 自动更新 | 后续阶段实现 |
| 移动端 | 不在范围内 |

### 1.3 技术选型依据

**Nuitka vs PyInstaller**：

| 维度 | Nuitka | PyInstaller |
|------|--------|-------------|
| 编译方式 | Python → C → 机器码 | 打包字节码 + 解释器 |
| 启动速度 | 快（< 1s） | 慢（onefile 模式需 3-10s 解压） |
| 运行性能 | 更快（部分代码编译优化） | 与源码一致 |
| 体积 | 较小 | 较大 |
| Python 3.12+ 支持 | 良好 | 常有问题 |
| 跨平台稳定性 | 高 | 中等 |

**onedir vs onefile**：

| 维度 | onedir | onefile |
|------|--------|---------|
| 启动速度 | 快（无需解压） | 慢（每次启动解压到临时目录） |
| 安装后结构 | 多文件目录 | 单文件 |
| 分发复杂度 | 稍高（需打包整个目录） | 低 |
| 适用场景 | 桌面应用安装包 | 便携工具 |

**结论**：Nuitka + onedir 是桌面应用的最优方案。

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                    Tauri Desktop App                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │              WebView (系统原生)                     │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │         React SPA (from ui/dist/)           │  │  │
│  │  │                                              │  │  │
│  │  │  fetch → localhost:8000 (后端 API)          │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │           Sidecar Manager (Rust)                  │  │
│  │  - 应用启动时自动启动 Python 后端进程              │  │
│  │  - 应用关闭时自动终止后端进程                      │  │
│  │  - 监控后端进程健康状态                           │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │      Embedded Binary (Nuitka 编译的 Python 后端)  │  │
│  │  laffybot-backend-{target-triple}/               │  │
│  │  ├─ laffybot-backend (主可执行文件)              │  │
│  │  ├─ laffybot-backend.dist/ (依赖库)              │  │
│  │  └─ ... (其他运行时文件)                          │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 构建流程

```
GitHub Actions (matrix: linux/windows/macos)
  │
  ├─→ [Step 1] 构建 Python 后端 (Nuitka)
  │     ├─ 安装 Python 3.12+
  │     ├─ 安装 Nuitka
  │     ├─ 安装依赖 (uv sync)
  │     ├─ Nuitka 编译 → laffybot-backend-{target}/
  │     └─ 输出到 ui/src-tauri/binaries/
  │
  ├─→ [Step 2] 构建前端 (Vite)
  │     └─ pnpm build → ui/dist/
  │
  ├─→ [Step 3] 构建 Tauri 应用
  │     ├─ 安装 Rust 工具链
  │     ├─ tauri build (自动嵌入 sidecar 目录)
  │     └─ 输出安装包 (.deb/.AppImage/.msi/.exe/.dmg)
  │
  └─→ [Step 4] 发布到 GitHub Releases
        └─ 上传所有平台安装包
```

---

## 3. 组件设计

### 3.1 Nuitka 编译配置

**职责**：将 Python 后端编译为机器码可执行程序。

**入口点**：`laffybot.__main__:main`

**编译参数**：
- `--mode=standalone` — 独立部署模式（onedir）
- `--follow-imports` — 自动追踪所有导入
- `--include-package=laffybot` — 包含 laffybot 主包
- `--include-package=laffybot_agent_runtime` — 包含运行时引擎（workspace 依赖）
- `--include-package=pydantic` — 显式包含 pydantic
- `--include-package=jinja2` — 显式包含 jinja2
- `--enable-plugin=pylint-warnings` — 启用兼容性检查

**需显式包含的包**（动态导入）：
- `pydantic` 系列
- `jinja2` + `jinja2.ext`
- `openai`
- `httpx` / `httpx_sse`
- `aiosqlite`
- `cryptography`

**需包含的数据文件**：
- 无 — 系统提示模板在 `laffybot_agent_runtime.config.ContextConfig.system_prompt_template` 中以内联字符串定义
- Skills 定义（SKILL.md）在运行时从用户配置路径加载，非源码内数据

**输出目录结构**：
```
laffybot-backend-{target}/
├── laffybot-backend{.exe}    # 主可执行文件
├── laffybot-backend.dist/    # 编译后的 Python 模块
├── laffybot-backend.app/     # macOS 应用包（仅 macOS）
└── ... (依赖库 .so/.dll/.dylib)
```

**输出目录命名**（遵循 Tauri sidecar 命名规范）：
- Linux x64: `laffybot-backend-x86_64-unknown-linux-gnu/`
- Windows x64: `laffybot-backend-x86_64-pc-windows-msvc/`
- macOS ARM: `laffybot-backend-aarch64-apple-darwin/`

### 3.2 Tauri Sidecar 管理器

**职责**：管理 Python 后端进程的生命周期。

**行为**：
- 应用启动时：检测后端端口是否可用，不可用则启动 sidecar
- 应用关闭时：发送终止信号，等待后端进程退出
- 健康检查：定期探测 `http://localhost:8000/api/v1/health`

**错误处理**：
| 场景 | 行为 |
|------|------|
| 后端启动失败 | 显示错误对话框，允许用户重试或查看日志 |
| 后端意外退出 | 自动重启（最多 3 次），超过限制则提示用户 |
| 端口被占用 | 尝试使用备用端口，或提示用户关闭占用进程 |

### 3.3 GitHub Actions 发布 Workflow

**触发条件**：推送 tag `v*`（如 `v0.1.0`）

**构建矩阵**：
| Runner | 目标平台 | 输出格式 |
|--------|----------|----------|
| `ubuntu-latest` | Linux x64 | .deb, .AppImage |
| `windows-latest` | Windows x64 | .msi, .exe (NSIS) |
| `macos-latest` | macOS ARM | .dmg |

**步骤**（每个平台）：
1. 检出代码
2. 安装 Python 3.12 + uv + Nuitka
3. 安装 C 编译器（gcc/clang/MSVC）
4. 安装 Node.js + pnpm
5. 安装 Rust 工具链
6. Nuitka 编译后端
7. 放置 sidecar 到 `ui/src-tauri/binaries/`
8. Tauri build
9. 上传产物

**发布步骤**：
- 创建 GitHub Release（使用 tag 名称）
- 上传所有平台安装包
- 生成 Release Notes（自动从 commits 提取）

---

## 4. 文件变更清单

### 4.1 新增文件

| 文件 | 职责 |
|------|------|
| `nuitka-build.py` | Nuitka 编译脚本（跨平台） |
| `ui/src-tauri/binaries/.gitkeep` | 占位目录，存放 sidecar 二进制 |
| `ui/src-tauri/src/sidecar.rs` | Sidecar 进程管理逻辑 |
| `.github/workflows/release.yml` | GitHub Actions 发布 workflow |

### 4.2 修改文件

| 文件 | 变更内容 |
|------|----------|
| `ui/src-tauri/tauri.conf.json` | 添加 `bundle.externalBin`，扩展 `targets` |
| `ui/src-tauri/Cargo.toml` | 添加 `tauri-plugin-shell` 依赖 |
| `ui/src-tauri/src/lib.rs` | 集成 sidecar 管理器 |
| `.gitignore` | 忽略 `ui/src-tauri/binaries/*`（保留 .gitkeep） |

---

## 5. 集成点

### 5.1 与现有 Tauri 配置的集成

**`tauri.conf.json` 变更**：

```json
{
  "bundle": {
    "active": true,
    "targets": ["deb", "appimage", "msi", "nsis", "dmg"],
    "externalBin": [
      "binaries/laffybot-backend"
    ],
    "icon": [...],
    "linux": { ... },
    "windows": {
      "nsis": {}
    },
    "macOS": {
      "minimumSystemVersion": "10.13"
    }
  }
}
```

### 5.2 与 Python 后端的集成

**启动参数**：
- Sidecar 启动时传递 `--port {port}` 参数
- 后端监听指定端口（默认 8000）

**配置文件处理**：
- 打包时嵌入默认 `config.json`
- 运行时从应用数据目录读取用户配置

### 5.3 与前端的集成

**无需修改前端代码**。前端继续通过 `fetch` 访问 `localhost:8000`，由 Tauri WebView 的 CSP 允许。

---

## 6. 错误处理

### 6.1 构建阶段

| 错误场景 | 处理方式 |
|----------|----------|
| Nuitka 编译失败 | CI 日志输出详细错误，终止构建 |
| C 编译器缺失 | CI 中自动安装 gcc/clang/MSVC |
| 隐式导入缺失 | 在编译脚本中补充 `--include-package` |
| Tauri build 失败 | CI 日志输出详细错误，终止构建 |

### 6.2 运行阶段

| 错误场景 | 处理方式 |
|----------|----------|
| 后端启动超时 | 显示错误对话框，提供"查看日志"按钮 |
| 后端进程崩溃 | 自动重启（最多 3 次），超过限制提示用户 |
| 端口冲突 | 尝试递增端口号（8001, 8002...），上限 8010 |
| 配置文件损坏 | 使用默认配置，提示用户重置 |

---

## 7. 边界情况

### 7.1 平台差异

| 平台 | 特殊处理 |
|------|----------|
| Linux | 依赖 `webkit2gtk-4.1`，需在 CI 中安装；Nuitka 使用 gcc |
| Windows | 依赖 WebView2（Win10 1803+ 已内置）；Nuitka 使用 MSVC |
| macOS | 需配置 `minimumSystemVersion`；Nuitka 使用 clang |

### 7.2 首次启动

- 检查并创建应用数据目录
- 复制默认配置文件（如不存在）
- 初始化数据库文件

### 7.3 升级迁移

- 检测旧版本数据库
- 执行必要的 schema 迁移（已有机制）

---

## 8. 实现顺序

| 阶段 | 内容 | 依赖 |
|------|------|------|
| 1 | 创建 Nuitka 编译脚本，本地验证编译 | 无 |
| 2 | 修改 Tauri 配置，添加 sidecar 声明 | 阶段 1 |
| 3 | 实现 Rust sidecar 管理器 | 阶段 2 |
| 4 | 本地验证完整流程 | 阶段 3 |
| 5 | 创建 GitHub Actions workflow | 阶段 4 |
| 6 | 测试 CI 构建和发布 | 阶段 5 |

---

## 9. 交付清单

- [ ] Nuitka 可成功编译 Python 后端为独立目录
- [ ] 编译后的后端可独立运行，API 正常响应
- [ ] 后端启动时间 < 2 秒
- [ ] Tauri 配置正确声明 sidecar
- [ ] Rust sidecar 管理器可启动/停止后端进程
- [ ] 桌面应用启动时自动启动后端
- [ ] 桌面应用关闭时自动停止后端
- [ ] GitHub Actions 可成功构建三平台安装包
- [ ] 推送 tag 后自动创建 GitHub Release
- [ ] Release 包含所有平台安装包
- [ ] 用户下载安装包后可正常安装和运行

---

## 10. 待决策事项

### 10.1 macOS 通用二进制

**选项**：
| 方案 | 说明 |
|------|------|
| 仅构建 ARM | 适配 Apple Silicon，体积小 |
| 分别构建 ARM/Intel | 两个独立 .dmg，用户按架构选择 |
| 构建 Universal Binary | 单个 .dmg 兼容两种架构，体积翻倍 |

**待决策**：是否需要 Universal Binary？

### 10.2 配置文件位置

**选项**：
| 位置 | 说明 |
|------|------|
| 应用安装目录 | 简单，但可能无写权限 |
| 用户数据目录 | 符合规范，需处理权限 |

**待决策**：配置文件和数据库存放在哪个目录？

---

## 11. 参考

- `docs/ui/desktop-design.md` — 桌面端架构设计
- `docs/ui/tauri-impl-plan.md` — Tauri 实现步骤
- [Tauri Sidecar 文档](https://v2.tauri.app/reference/javascript/shell/)
- [Nuitka 文档](https://nuitka.net/doc/user-manual.html)
- [Nuitka GitHub](https://github.com/Nuitka/Nuitka)
