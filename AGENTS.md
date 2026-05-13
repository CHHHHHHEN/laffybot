## Project Environment
- Use `uv` to manage python environment and run python commands. e.g. `uv run ruff`, `uv run mypy`.
- Use `pnpm` to manage ui/ dependencies and run ui commands.

## Python 代码质量 (laffybot/)
- `uv run ruff check .` — ruff 语法检查
- `uv run ruff format --check .` — ruff 格式检查
- `uv run mypy laffybot/` — mypy 类型检查
- `uv run ruff check . && uv run ruff format --check . && uv run mypy laffybot/` — 三者一起跑

## UI 代码质量 (ui/)
- `pnpm run typecheck` — TypeScript 类型检查（对标 mypy）
- `pnpm run lint` — ESLint 语法检查（对标 ruff）
- `pnpm run check` — typecheck + lint 一起跑
- `pnpm run build` — 完整构建（包含 typecheck）

## Rules
- Before write documents, read `docs/readme-document-content-guidelines.md`
- Read `README.md` and `docs` to know basic information about project.