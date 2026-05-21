@echo off
REM Laffybot development launcher (Windows)

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

set BACKEND_PORT=8000
set FRONTEND_PORT=1420

set TAURI_MODE=false
set BACKEND_ONLY=false
set FRONTEND_ONLY=false

:parse_args
if "%~1"=="" goto :check_args
if "%~1"=="--tauri" (
    set TAURI_MODE=true
    shift
    goto :parse_args
)
if "%~1"=="--backend" (
    set BACKEND_ONLY=true
    shift
    goto :parse_args
)
if "%~1"=="--frontend" (
    set FRONTEND_ONLY=true
    shift
    goto :parse_args
)
if "%~1"=="--help" goto :usage
if "%~1"=="-h" goto :usage
echo Unknown option: %~1
goto :usage

:usage
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   --tauri      Start Tauri desktop instead of web frontend
echo   --backend    Start backend only
echo   --frontend   Start web frontend only
echo   --help       Show this help
echo.
echo Examples:
echo   %~nx0              Start backend + web frontend
echo   %~nx0 --tauri      Start backend + Tauri desktop
echo   %~nx0 --backend    Start backend only
exit /b 0

:check_args
if "%BACKEND_ONLY%"=="true" if "%FRONTEND_ONLY%"=="true" (
    echo Error: --backend and --frontend are mutually exclusive
    exit /b 1
)

if "%FRONTEND_ONLY%"=="true" (
    echo [Frontend] Starting Vite dev server on port %FRONTEND_PORT%...
    cd ui
    pnpm run dev
    exit /b 0
)

if "%BACKEND_ONLY%"=="true" (
    echo [Backend] Starting on port %BACKEND_PORT%...
    uv run laffybot --config config.json
    exit /b 0
)

echo [Backend] Starting on port %BACKEND_PORT%...
start /b uv run laffybot --config config.json

timeout /t 2 /nobreak >nul

if "%TAURI_MODE%"=="true" (
    echo [Tauri] Starting Tauri dev mode...
    cd ui
    pnpm run tauri dev
) else (
    echo [Frontend] Starting Vite dev server on port %FRONTEND_PORT%...
    cd ui
    pnpm run dev
)
