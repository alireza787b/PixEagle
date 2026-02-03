@echo off
REM ============================================================================
REM scripts\run.bat - PixEagle Launcher (Windows)
REM ============================================================================
REM Launches all PixEagle components in separate Windows Terminal tabs.
REM
REM Usage:
REM   make run-win                 (recommended with nmake)
REM   scripts\run.bat              (direct)
REM   scripts\run.bat --dev        (development mode)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script directory
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..") do set "PIXEAGLE_DIR=%%~fi"

REM Source common functions
call "%SCRIPTS_DIR%\lib\common.bat"

REM Parse arguments
set "DEV_MODE=0"
if "%~1"=="--dev" set "DEV_MODE=1"
if "%~1"=="-d" set "DEV_MODE=1"

REM Component scripts
set "MAVLINK2REST_SCRIPT=%SCRIPTS_DIR%\components\mavlink2rest.bat"
set "DASHBOARD_SCRIPT=%SCRIPTS_DIR%\components\dashboard.bat"
set "MAIN_APP_SCRIPT=%SCRIPTS_DIR%\components\main.bat"

REM ============================================================================
REM Banner
REM ============================================================================
echo.
call :print_cyan "========================================================================"
if "%DEV_MODE%"=="1" (
    echo               PixEagle Launcher - DEVELOPMENT MODE
) else (
    echo               PixEagle Launcher - Production Mode
)
call :print_cyan "========================================================================"
echo.

REM ============================================================================
REM Verify Scripts Exist
REM ============================================================================
if not exist "%MAVLINK2REST_SCRIPT%" (
    call :print_red "[ERROR] MAVLink2REST script not found: %MAVLINK2REST_SCRIPT%"
    exit /b 1
)
if not exist "%DASHBOARD_SCRIPT%" (
    call :print_red "[ERROR] Dashboard script not found: %DASHBOARD_SCRIPT%"
    exit /b 1
)
if not exist "%MAIN_APP_SCRIPT%" (
    call :print_red "[ERROR] Main app script not found: %MAIN_APP_SCRIPT%"
    exit /b 1
)

REM ============================================================================
REM Launch Components
REM ============================================================================
echo    [1/3] Starting MAVLink2REST...

REM Check if Windows Terminal is available and working
REM Note: 'where wt' may succeed but wt may not run if just installed (needs terminal restart)
set "USE_WT=0"
where wt >nul 2>&1
if %errorlevel% equ 0 (
    REM Test if wt actually works by running a quick test
    wt --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "USE_WT=1"
    )
)

if "!USE_WT!"=="1" (
    REM Use Windows Terminal with tabs
    echo          Using Windows Terminal with tabs

    REM Start MAVLink2REST in first tab
    start "" wt -d "%PIXEAGLE_DIR%" --title "MAVLink2REST" cmd /k "call %MAVLINK2REST_SCRIPT%"
    timeout /t 3 /nobreak >nul

    echo    [2/3] Starting Dashboard...
    if "%DEV_MODE%"=="1" (
        start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "Dashboard (Dev)" cmd /k "call %DASHBOARD_SCRIPT% --dev"
    ) else (
        start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "Dashboard" cmd /k "call %DASHBOARD_SCRIPT%"
    )
    timeout /t 5 /nobreak >nul

    echo    [3/3] Starting Main Application...
    start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "PixEagle Main" cmd /k "call %MAIN_APP_SCRIPT%"
) else (
    REM Fallback to separate cmd windows
    echo          Using separate windows ^(Windows Terminal not available^)
    echo.
    call :print_yellow "    TIP: For a better experience with tabs, install Windows Terminal:"
    echo          winget install Microsoft.WindowsTerminal
    echo          Or download from: https://aka.ms/terminal
    echo.
    call :print_yellow "    NOTE: If you just installed Windows Terminal, restart your terminal first."
    echo.

    start "MAVLink2REST" cmd /k "cd /d %PIXEAGLE_DIR% && call %MAVLINK2REST_SCRIPT%"
    timeout /t 3 /nobreak >nul

    echo    [2/3] Starting Dashboard...
    if "%DEV_MODE%"=="1" (
        start "Dashboard (Dev)" cmd /k "cd /d %PIXEAGLE_DIR% && call %DASHBOARD_SCRIPT% --dev"
    ) else (
        start "Dashboard" cmd /k "cd /d %PIXEAGLE_DIR% && call %DASHBOARD_SCRIPT%"
    )
    timeout /t 5 /nobreak >nul

    echo    [3/3] Starting Main Application...
    start "PixEagle Main" cmd /k "cd /d %PIXEAGLE_DIR% && call %MAIN_APP_SCRIPT%"
)

REM ============================================================================
REM Summary
REM ============================================================================
echo.
call :print_cyan "========================================================================"
call :print_green "                    [OK] All Services Launched"
call :print_cyan "========================================================================"
echo.
echo    Services:
echo      - MAVLink2REST: http://localhost:8088
echo      - Dashboard:    http://localhost:3000
echo      - Backend:      http://localhost:5077
echo.
if "%DEV_MODE%"=="1" (
    call :print_yellow "    Development mode: Hot-reload enabled for dashboard"
)
echo.
echo    To stop all services: make stop-win  or  scripts\stop.bat
echo.

endlocal
exit /b 0

REM ============================================================================
REM Helper Functions
REM ============================================================================
:print_cyan
echo [36m%~1[0m
exit /b 0

:print_green
echo [32m%~1[0m
exit /b 0

:print_yellow
echo [33m%~1[0m
exit /b 0

:print_red
echo [31m%~1[0m
exit /b 0
