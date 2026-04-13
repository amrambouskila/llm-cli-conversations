@echo off
setlocal enabledelayedexpansion

if "%GRAPHIFY_MODEL%"=="" set "GRAPHIFY_MODEL=claude-sonnet-4-6"
set "SCRIPT_DIR=%~dp0"
set "GRAPHIFY_OUT=%SCRIPT_DIR%graphify-out"
set "PID_FILE=%GRAPHIFY_OUT%\graph_watcher.pid"

REM Write our own PID to file so the service script can kill us
for /f "tokens=2" %%P in ('tasklist /v /fi "WINDOWTITLE eq graph_watcher" /fo list 2^>nul ^| findstr /i "PID"') do (
    echo %%P> "%PID_FILE%"
)

REM Clear stale status
if exist "%GRAPHIFY_OUT%\.status" del /f "%GRAPHIFY_OUT%\.status"
if exist "%GRAPHIFY_OUT%\.generate_requested" del /f "%GRAPHIFY_OUT%\.generate_requested"

REM Auto-generate on startup
set "GRAPHIFY_MODEL=%GRAPHIFY_MODEL%"
set "GRAPHIFY_OUT=%GRAPHIFY_OUT%"
python "%SCRIPT_DIR%graph_extract.py"

REM Then watch for re-generation requests
:loop
if not exist "%GRAPHIFY_OUT%\.generate_requested" goto :wait

del /f "%GRAPHIFY_OUT%\.generate_requested" 2>nul

REM Clear chunk cache for full re-extraction
del /f "%GRAPHIFY_OUT%\.graphify_chunk_*.json" 2>nul

set "GRAPHIFY_MODEL=%GRAPHIFY_MODEL%"
set "GRAPHIFY_OUT=%GRAPHIFY_OUT%"
python "%SCRIPT_DIR%graph_extract.py"

:wait
timeout /t 3 /nobreak >nul
goto loop
