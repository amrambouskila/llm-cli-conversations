@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM              CONFIGURATION (EDIT THESE ONLY)
REM ============================================================
set "SERVICE_PREFIX=llm-cli-conversation-export"
set "COMPOSE_FILE=docker-compose.yml"
if "%PORT%"=="" set "PORT=5050"
if "%POSTGRES_PORT%"=="" set "POSTGRES_PORT=5432"
if "%SUMMARY_MODEL%"=="" set "SUMMARY_MODEL=claude-sonnet-4-6"
if "%GRAPHIFY_MODEL%"=="" set "GRAPHIFY_MODEL=claude-sonnet-4-6"

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "SUMMARY_DIR=%SCRIPT_DIR%browser_state\summaries"
set "GRAPHIFY_OUT=%SCRIPT_DIR%graphify-out"

REM ============================================================
REM                  PARSE ARGUMENTS
REM ============================================================
set "SKIP_EXPORT=false"
set "EXPORT_ONLY=false"
set "FILTER="

:parse_args
if "%~1"=="" goto :done_args
if /I "%~1"=="--skip-export" (
    set "SKIP_EXPORT=true"
    shift
    goto :parse_args
)
if /I "%~1"=="--export-only" (
    set "EXPORT_ONLY=true"
    shift
    goto :parse_args
)
if /I "%~1"=="--help" goto :show_help
if /I "%~1"=="-h" goto :show_help
set "FILTER=%~1"
shift
goto :parse_args

:show_help
echo Usage: %~nx0 [OPTIONS] [project-filter]
echo.
echo Options:
echo   --skip-export   Start browser without re-exporting conversations
echo   --export-only   Export conversations only, don't start browser
echo   -h, --help      Show this help
echo.
echo Arguments:
echo   project-filter  Only export projects matching this string
echo.
echo Environment:
echo   PORT              Server port (default: 5050)
echo   SUMMARY_MODEL     Claude model for summaries (default: claude-sonnet-4-6)
echo   GRAPHIFY_MODEL    Claude model for concept graph (default: claude-sonnet-4-6)
exit /b 0

:done_args

REM Handle --export-only after all args are parsed (so FILTER is set)
if "%EXPORT_ONLY%"=="true" (
    call :find_python
    call :run_export
    echo Export complete. Markdown files are in: %SCRIPT_DIR%markdown\
    exit /b 0
)

REM ============================================================
REM               CHECK DOCKER
REM ============================================================
where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or not on PATH.
    echo   Install Docker Desktop: https://www.docker.com/products/docker-desktop/
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker daemon is not running. Please start Docker Desktop.
    exit /b 1
)

REM ============================================================
REM               EXPORT CONVERSATIONS
REM ============================================================
if "%SKIP_EXPORT%"=="true" goto :check_markdown

call :find_python
call :run_export

:check_markdown
if not exist "%SCRIPT_DIR%markdown\*.md" (
    echo ERROR: No markdown files found in .\markdown\
    echo   Run without --skip-export to generate them first.
    exit /b 1
)

REM ============================================================
REM                     RUN DOCKER COMPOSE
REM ============================================================
echo ==^> Starting Docker Compose...
docker compose -f "%COMPOSE_FILE%" up --build -d

REM Start watchers
call :start_summary_watcher
call :start_graph_watcher

echo.
echo ==============================
echo Services running:
echo   Browser:    http://localhost:%PORT%
echo   Postgres:   localhost:%POSTGRES_PORT% (conversations/conversations)
echo.
echo Press k + Enter = stop but keep images
echo Press q + Enter = stop ^& remove images
echo Press v + Enter = stop, remove images, volumes (pgdata) ^& generated data
echo Press r + Enter = full reset ^& restart (wipe, re-export, rebuild)
echo ==============================

REM Auto-open browser
timeout /t 2 /nobreak >nul
start http://localhost:%PORT%

:wait_choice
set /p "CHOICE=Enter selection (k/q/v/r): "
echo.
if /I "%CHOICE%"=="k" goto stop_only
if /I "%CHOICE%"=="q" goto full_cleanup
if /I "%CHOICE%"=="v" goto full_cleanup_with_volumes
if /I "%CHOICE%"=="r" goto full_reset
echo Invalid selection. Enter k, q, v, or r.
goto wait_choice

REM ============================================================
REM            k = STOP BUT KEEP IMAGE
REM ============================================================
:stop_only
echo.
echo Stopping containers but keeping images...
call :stop_summary_watcher
call :stop_graph_watcher
docker compose -f "%COMPOSE_FILE%" down
goto end_script

REM ============================================================
REM            q = STOP + REMOVE IMAGES (keep data)
REM ============================================================
:full_cleanup
echo.
echo Stopping and removing all containers...
call :stop_summary_watcher
call :stop_graph_watcher
docker compose -f "%COMPOSE_FILE%" down --remove-orphans
call :remove_images
goto end_script

REM ============================================================
REM            v = FULL CLEANUP (containers + images + volumes + data)
REM ============================================================
:full_cleanup_with_volumes
echo.
echo Stopping and removing all containers and volumes...
call :stop_summary_watcher
call :stop_graph_watcher
docker compose -f "%COMPOSE_FILE%" down --volumes --remove-orphans
call :remove_images
call :wipe_generated_data
goto end_script

REM ============================================================
REM            r = FULL RESET & RESTART
REM ============================================================
:full_reset
echo.
echo ==^> Full reset ^& restart...

call :stop_summary_watcher
call :stop_graph_watcher
docker compose -f "%COMPOSE_FILE%" down --volumes --remove-orphans
call :remove_images
call :wipe_generated_data

call :find_python
call :run_export

echo ==^> Rebuilding Docker image...
docker compose -f "%COMPOSE_FILE%" up --build -d

call :start_summary_watcher
call :start_graph_watcher

echo.
echo ==============================
echo Services restarted:
echo   Browser:    http://localhost:%PORT%
echo   Postgres:   localhost:%POSTGRES_PORT% (conversations/conversations)
echo.
echo Press k + Enter = stop but keep images
echo Press q + Enter = stop ^& remove images
echo Press v + Enter = stop, remove images, volumes (pgdata) ^& generated data
echo Press r + Enter = full reset ^& restart (wipe, re-export, rebuild)
echo ==============================

timeout /t 2 /nobreak >nul
start http://localhost:%PORT%

REM Loop back to wait for next selection
goto wait_choice

REM ============================================================
REM                     SUBROUTINES
REM ============================================================

:find_python
set "PYTHON="
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python"
    goto :eof
)
where python3 >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=python3"
    goto :eof
)
echo ERROR: Python is not installed or not on PATH.
exit /b 1

:run_export
echo ==^> Exporting conversations...
if not "%FILTER%"=="" (
    %PYTHON% convert_export.py %FILTER%
) else (
    %PYTHON% convert_export.py
)
echo.
REM Also export Codex sessions if available
set "CODEX_SRC=%CODEX_SESSIONS_DIR%"
if "%CODEX_SRC%"=="" set "CODEX_SRC=%USERPROFILE%\.codex\sessions"
if exist "%CODEX_SRC%" (
    echo ==^> Exporting Codex sessions...
    %PYTHON% convert_codex_sessions.py "%CODEX_SRC%" "%SCRIPT_DIR%markdown_codex"
    echo.
)
goto :eof

:remove_images
echo.
echo Searching for project images...
set "TARGET_IMAGE="
for /f "delims=" %%I in ('
    docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr /I "^%SERVICE_PREFIX%"
') do (
    set "TARGET_IMAGE=%%I"
    echo Found image: %%I
    echo Removing image %%I...
    docker rmi -f "%%I" 2>nul
)
REM Remove the pgvector image used by the postgres service
docker images --format "{{.Repository}}:{{.Tag}}" | findstr /I "^pgvector/pgvector" >nul 2>&1
if not errorlevel 1 (
    echo Found image: pgvector/pgvector:pg16
    echo Removing image pgvector/pgvector:pg16...
    docker rmi -f pgvector/pgvector:pg16 2>nul
    set "TARGET_IMAGE=pgvector/pgvector:pg16"
)
if not defined TARGET_IMAGE (
    echo No project images found.
)
goto :eof

:wipe_generated_data
echo.
echo Removing generated data (raw\, markdown\, markdown_codex\, browser_state\, graphify-out\)...
if exist "%SCRIPT_DIR%raw" rmdir /s /q "%SCRIPT_DIR%raw"
if exist "%SCRIPT_DIR%markdown" rmdir /s /q "%SCRIPT_DIR%markdown"
if exist "%SCRIPT_DIR%markdown_codex" rmdir /s /q "%SCRIPT_DIR%markdown_codex"
if exist "%SCRIPT_DIR%browser_state" rmdir /s /q "%SCRIPT_DIR%browser_state"
if exist "%GRAPHIFY_OUT%" rmdir /s /q "%GRAPHIFY_OUT%"
echo Done. Source data in %USERPROFILE%\.claude\projects\ is untouched.
goto :eof

:start_summary_watcher
where claude >nul 2>&1
if errorlevel 1 (
    echo     Note: 'claude' CLI not found — AI summaries disabled.
    echo     Install the AI CLI to enable.
    goto :eof
)
if not exist "%SUMMARY_DIR%" mkdir "%SUMMARY_DIR%"
echo ==^> Starting summary watcher (model: %SUMMARY_MODEL%)...
start "summary_watcher" /min cmd /c "%SCRIPT_DIR%summary_watcher.bat"
REM Wait briefly for watcher to write its PID file
timeout /t 1 /nobreak >nul
goto :eof

:stop_summary_watcher
set "PID_FILE=%SCRIPT_DIR%browser_state\summary_watcher.pid"
REM Kill by PID file (most reliable)
if exist "%PID_FILE%" (
    set /p WATCHER_PID=<"%PID_FILE%"
    taskkill /f /pid !WATCHER_PID! >nul 2>&1
    del /f "%PID_FILE%" 2>nul
)
REM Fallback: kill by window title
taskkill /f /fi "WINDOWTITLE eq summary_watcher" >nul 2>&1
echo     Summary watcher stopped.
goto :eof

:start_graph_watcher
where claude >nul 2>&1
if errorlevel 1 (
    echo     Note: 'claude' CLI not found — concept graph disabled.
    goto :eof
)
python -c "import graphify" >nul 2>&1
if errorlevel 1 (
    echo     Note: graphifyy not installed — concept graph disabled.
    echo     Install to enable: pip install graphifyy
    goto :eof
)
if not exist "%GRAPHIFY_OUT%" mkdir "%GRAPHIFY_OUT%"
REM Clear stale status
if exist "%GRAPHIFY_OUT%\.status" del /f "%GRAPHIFY_OUT%\.status"
if exist "%GRAPHIFY_OUT%\.generate_requested" del /f "%GRAPHIFY_OUT%\.generate_requested"
if exist "%GRAPHIFY_OUT%\.progress" del /f "%GRAPHIFY_OUT%\.progress"
echo ==^> Starting graph watcher (model: %GRAPHIFY_MODEL%)...
start "graph_watcher" /min cmd /c "%SCRIPT_DIR%graph_watcher.bat"
timeout /t 1 /nobreak >nul
goto :eof

:stop_graph_watcher
set "GPID_FILE=%GRAPHIFY_OUT%\graph_watcher.pid"
if exist "%GPID_FILE%" (
    set /p GWATCHER_PID=<"%GPID_FILE%"
    taskkill /f /pid !GWATCHER_PID! >nul 2>&1
    del /f "%GPID_FILE%" 2>nul
)
taskkill /f /fi "WINDOWTITLE eq graph_watcher" >nul 2>&1
echo     Graph watcher stopped.
goto :eof

REM ============================================================
REM                            END
REM ============================================================
:end_script
exit /B
