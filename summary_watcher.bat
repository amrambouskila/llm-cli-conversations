@echo off
setlocal enabledelayedexpansion

if "%SUMMARY_MODEL%"=="" set "SUMMARY_MODEL=claude-sonnet-4-6"
set "SUMMARY_DIR=%~dp0browser_state\summaries"
set "PID_FILE=%~dp0browser_state\summary_watcher.pid"

REM Write our own PID to file so the service script can kill us
for /f "tokens=2" %%P in ('tasklist /v /fi "WINDOWTITLE eq summary_watcher" /fo list 2^>nul ^| findstr /i "PID"') do (
    echo %%P> "%PID_FILE%"
)

:loop
for %%F in ("%SUMMARY_DIR%\*.pending") do (
    if exist "%%F" (
        set "BASENAME=%%~nF"
        set "INPUT=%SUMMARY_DIR%\!BASENAME!.input"
        set "OUTPUT=%SUMMARY_DIR%\!BASENAME!.md"

        if exist "!INPUT!" (
            REM Safety net only: backend hierarchical summarization keeps
            REM individual jobs around 80K chars. Anything larger than 400K
            REM (~100K tokens) gets head/tail truncated so it still fits in
            REM the sonnet context window.
            for %%S in ("!INPUT!") do set "FSIZE=%%~zS"
            set "TRUNCATED=%TEMP%\claude_summary_input.tmp"

            if !FSIZE! GTR 400000 (
                powershell -NoProfile -Command "$c=[IO.File]::ReadAllText('!INPUT!'); $len=$c.Length; $cut=$len-400000; [IO.File]::WriteAllText('!TRUNCATED!', $c.Substring(0,200000)+\"`n`n[... $cut characters truncated for summary ...]`n`n\"+$c.Substring($len-200000))"
            ) else (
                copy /y "!INPUT!" "!TRUNCATED!" >nul 2>&1
            )

            claude -p --model %SUMMARY_MODEL% "You are a summarization tool. Your ONLY job is to output a summary. Do NOT ask for permission, clarification, or confirmation. Do NOT say you need more context. Do NOT refuse. Just summarize whatever text is provided to the best of your ability. Your first line MUST be exactly: TITLE: <short title under 8 words>. Then a blank line, then a concise summary (under 300 words, markdown). Focus on: what the user asked for, what was done, and the outcome. If the text is truncated or incomplete, summarize what you can see." < "!TRUNCATED!" > "!OUTPUT!.tmp" 2>nul
            if exist "!OUTPUT!.tmp" (
                move /y "!OUTPUT!.tmp" "!OUTPUT!" >nul
            ) else (
                echo TITLE: Summary failed> "!OUTPUT!"
                echo.>> "!OUTPUT!"
                echo **Summary generation failed.** The input may be too large or the claude CLI may not be authenticated.>> "!OUTPUT!"
            )
            del /f "!TRUNCATED!" 2>nul
        )
        del /f "%%F" 2>nul
        del /f "!INPUT!" 2>nul
        del /f "!OUTPUT!.tmp" 2>nul
    )
)

timeout /t 2 /nobreak >nul
goto loop
