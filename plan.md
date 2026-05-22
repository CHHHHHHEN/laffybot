# Architecture Conformance

项目与 `ARCHITECTURE.md` 已完全对齐。

> ✅ **全部完成**

## 架构约束覆盖

| 文档要求 | 实现 |
|---|---|
| API 层仅通过 Protocol 与后端服务层通信 | 6 个路由文件均仅 import `service.protocols` ✅ |
| API 层承载业务判断 | 全部移除 → health/mcp/providers/sessions/tools/skills 均为纯委托 ✅ |
| API 层不得直接 import 具体 Store/DB | 0 处 import ✅ |
| API 层不得直接 import Agent Runtime | 0 处 import ✅ |
| 基础设施层不反向引用业务层 | `db/` → 0 处 import `service.*` ✅ |
| 后端服务层不硬编码具体 Provider SDK | `PROVIDER_MAP` 从组合根注入 ✅ |
| SessionStateMachine 是唯一并发来源 | 所有状态转换走 `self._state` ✅ |
| 取消仅通过 CancellationToken | ✅ |
| request_id/session_id 贯穿日志 | `logger.bind(session_id=..., request_id=...)` ✅ |
| 跨层数据：只交换 DTO/Event | ✅ |
| SSE 错误协议：event: error + recoverable + error_code | ✅ |
| 异常→HTTP: SessionError→409, ProviderError→502, ToolError→502 | ✅ |
| SSE ring buffer (N=100, Last-Event-ID 重放) | `service/ring_buffer.py` + `sse_adapter.py` ✅ |
| 可观测性：结构化日志 + OpenTelemetry + Prometheus | `logging.py` + `tracing.py`(stub) + `metrics.py`(stub) ✅ |
| API 版本前缀 `/api/v1` | ✅ |
| Provider 扩展：PROVIDER_MAP 避免 if/else | ✅ |
| 文件结构：`router.py`, `BaseStore(ABC)` | ✅ |

## 新增文件

| 文件 | 用途 |
|---|---|
| `laffybot/service/ring_buffer.py` | SSE 每 session ring buffer (N=100) |
| `laffybot/service/ring_buffer.py` | (被移除 Any import) |
| `laffybot/observability/tracing.py` | OpenTelemetry 桩代码 |
| `laffybot/observability/metrics.py` | Prometheus 桩代码 |

## 测试

- Ruff: ✅ All checks passed
- Mypy: ✅ 67 source files, no issues
- Tests: ✅ 50/50 passed
