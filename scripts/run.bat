@echo off
REM ============================================================================
REM scripts\run.bat - PixEagle Launcher (Windows)
REM ============================================================================
REM Launches PixEagle components in Windows Terminal tabs (or fallback cmd windows).
REM
REM Usage:
REM   make run-win                 (recommended with nmake)
REM   scripts\run.bat              (direct)
REM   scripts\run.bat --dev        (development mode)
REM   scripts\run.bat --rebuild    (force dashboard rebuild)
REM   scripts\run.bat -m           (skip MAVLink2REST)
REM   scripts\run.bat -p           (skip Python backend)
REM   scripts\run.bat -k           (skip MAVSDK Server)
REM   scripts\run.bat --help
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

REM Default flags
set "DEV_MODE=0"
set "FORCE_REBUILD=0"
set "RUN_MAVLINK2REST=1"
set "RUN_MAIN_APP=1"
set "RUN_MAVSDK_SERVER=1"

REM Parse arguments
:parse_args
if "%~1"=="" goto :args_done

if /I "%~1"=="--dev" (
    set "DEV_MODE=1"
    shift
    goto :parse_args
)
if /I "%~1"=="-d" (
    set "DEV_MODE=1"
    shift
    goto :parse_args
)
if /I "%~1"=="--rebuild" (
    set "FORCE_REBUILD=1"
    shift
    goto :parse_args
)
if /I "%~1"=="-r" (
    set "FORCE_REBUILD=1"
    shift
    goto :parse_args
)
if /I "%~1"=="-m" (
    set "RUN_MAVLINK2REST=0"
    shift
    goto :parse_args
)
if /I "%~1"=="-p" (
    set "RUN_MAIN_APP=0"
    shift
    goto :parse_args
)
if /I "%~1"=="-k" (
    set "RUN_MAVSDK_SERVER=0"
    shift
    goto :parse_args
)
if /I "%~1"=="--help" goto :show_help
if /I "%~1"=="-h" goto :show_help

call :print_red "[ERROR] Unknown option: %~1"
echo.
echo Use scripts\run.bat --help to see available options
exit /b 1

:show_help
echo.
echo Usage: scripts\run.bat [OPTIONS]
echo.
echo   --dev, -d       Development mode for dashboard
echo   --rebuild, -r   Force dashboard rebuild before serving
echo   -m              Skip MAVLink2REST
echo   -p              Skip Python backend
echo   -k              Skip MAVSDK Server
echo   --help, -h      Show this help message
echo.
exit /b 0

:args_done

REM Component scripts
set "MAVLINK2REST_SCRIPT=%SCRIPTS_DIR%\components\mavlink2rest.bat"
set "DASHBOARD_SCRIPT=%SCRIPTS_DIR%\components\dashboard.bat"
set "MAIN_APP_SCRIPT=%SCRIPTS_DIR%\components\main.bat"
set "MAVSDK_SERVER_SCRIPT=%SCRIPTS_DIR%\components\mavsdk_server.bat"

set /a "TOTAL_COMPONENTS=1"
if "%RUN_MAVLINK2REST%"=="1" set /a "TOTAL_COMPONENTS+=1"
if "%RUN_MAIN_APP%"=="1" set /a "TOTAL_COMPONENTS+=1"
if "%RUN_MAVSDK_SERVER%"=="1" set /a "TOTAL_COMPONENTS+=1"

set "DASHBOARD_ARGS="
if "%DEV_MODE%"=="1" set "DASHBOARD_ARGS=!DASHBOARD_ARGS! --dev"
if "%FORCE_REBUILD%"=="1" set "DASHBOARD_ARGS=!DASHBOARD_ARGS! --rebuild"
set "MAIN_ARGS="
if "%DEV_MODE%"=="1" set "MAIN_ARGS= --dev"

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
echo    Selected components: %TOTAL_COMPONENTS%
if "%RUN_MAVLINK2REST%"=="0" echo      - MAVLink2REST skipped
if "%RUN_MAIN_APP%"=="0" echo      - Python backend skipped
if "%RUN_MAVSDK_SERVER%"=="0" echo      - MAVSDK Server skipped
echo.

REM ============================================================================
REM Verify Scripts Exist
REM ============================================================================
if not exist "%DASHBOARD_SCRIPT%" (
    call :print_red "[ERROR] Dashboard script not found: %DASHBOARD_SCRIPT%"
    exit /b 1
)
if "%RUN_MAIN_APP%"=="1" if not exist "%MAIN_APP_SCRIPT%" (
    call :print_red "[ERROR] Main app script not found: %MAIN_APP_SCRIPT%"
    exit /b 1
)
if "%RUN_MAVLINK2REST%"=="1" if not exist "%MAVLINK2REST_SCRIPT%" (
    call :print_red "[ERROR] MAVLink2REST script not found: %MAVLINK2REST_SCRIPT%"
    exit /b 1
)
if "%RUN_MAVSDK_SERVER%"=="1" if not exist "%MAVSDK_SERVER_SCRIPT%" (
    call :print_red "[ERROR] MAVSDK Server script not found: %MAVSDK_SERVER_SCRIPT%"
    exit /b 1
)

REM ============================================================================
REM Launch Components
REM ============================================================================
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

set "FIRST_COMPONENT=1"
set "CURRENT_COMPONENT=0"

if "!USE_WT!"=="1" (
    REM Use Windows Terminal with tabs
    echo          Using Windows Terminal with tabs
    echo.
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
)

if "%RUN_MAVLINK2REST%"=="1" (
    set /a "CURRENT_COMPONENT+=1"
    echo    [!CURRENT_COMPONENT!/%TOTAL_COMPONENTS%] Starting MAVLink2REST...
    if "!USE_WT!"=="1" (
        if "!FIRST_COMPONENT!"=="1" (
            start "" wt -d "%PIXEAGLE_DIR%" --title "MAVLink2REST" cmd /k "call ""%MAVLINK2REST_SCRIPT%"""
            set "FIRST_COMPONENT=0"
        ) else (
            start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "MAVLink2REST" cmd /k "call ""%MAVLINK2REST_SCRIPT%"""
        )
    ) else (
        start "MAVLink2REST" cmd /k "cd /d %PIXEAGLE_DIR% && call ""%MAVLINK2REST_SCRIPT%"""
    )
    timeout /t 3 /nobreak >nul
)

set /a "CURRENT_COMPONENT+=1"
if "%DEV_MODE%"=="1" (
    echo    [!CURRENT_COMPONENT!/%TOTAL_COMPONENTS%] Starting Dashboard ^(Dev^)...
) else (
    echo    [!CURRENT_COMPONENT!/%TOTAL_COMPONENTS%] Starting Dashboard...
)
if "!USE_WT!"=="1" (
    if "!FIRST_COMPONENT!"=="1" (
        if "%DEV_MODE%"=="1" (
            start "" wt -d "%PIXEAGLE_DIR%" --title "Dashboard (Dev)" cmd /k "call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
        ) else (
            start "" wt -d "%PIXEAGLE_DIR%" --title "Dashboard" cmd /k "call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
        )
        set "FIRST_COMPONENT=0"
    ) else (
        if "%DEV_MODE%"=="1" (
            start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "Dashboard (Dev)" cmd /k "call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
        ) else (
            start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "Dashboard" cmd /k "call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
        )
    )
) else (
    if "%DEV_MODE%"=="1" (
        start "Dashboard (Dev)" cmd /k "cd /d %PIXEAGLE_DIR% && call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
    ) else (
        start "Dashboard" cmd /k "cd /d %PIXEAGLE_DIR% && call ""%DASHBOARD_SCRIPT%""!DASHBOARD_ARGS!"
    )
)
timeout /t 5 /nobreak >nul

if "%RUN_MAIN_APP%"=="1" (
    set /a "CURRENT_COMPONENT+=1"
    echo    [!CURRENT_COMPONENT!/%TOTAL_COMPONENTS%] Starting Main Application...
    if "!USE_WT!"=="1" (
        if "!FIRST_COMPONENT!"=="1" (
            start "" wt -d "%PIXEAGLE_DIR%" --title "PixEagle Main" cmd /k "call ""%MAIN_APP_SCRIPT%""!MAIN_ARGS!"
            set "FIRST_COMPONENT=0"
        ) else (
            start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "PixEagle Main" cmd /k "call ""%MAIN_APP_SCRIPT%""!MAIN_ARGS!"
        )
    ) else (
        start "PixEagle Main" cmd /k "cd /d %PIXEAGLE_DIR% && call ""%MAIN_APP_SCRIPT%""!MAIN_ARGS!"
    )
    timeout /t 3 /nobreak >nul
)

if "%RUN_MAVSDK_SERVER%"=="1" (
    set /a "CURRENT_COMPONENT+=1"
    echo    [!CURRENT_COMPONENT!/%TOTAL_COMPONENTS%] Starting MAVSDK Server...
    if "!USE_WT!"=="1" (
        if "!FIRST_COMPONENT!"=="1" (
            start "" wt -d "%PIXEAGLE_DIR%" --title "MAVSDK Server" cmd /k "call ""%MAVSDK_SERVER_SCRIPT%"""
            set "FIRST_COMPONENT=0"
        ) else (
            start "" wt -w 0 new-tab -d "%PIXEAGLE_DIR%" --title "MAVSDK Server" cmd /k "call ""%MAVSDK_SERVER_SCRIPT%"""
        )
    ) else (
        start "MAVSDK Server" cmd /k "cd /d %PIXEAGLE_DIR% && call ""%MAVSDK_SERVER_SCRIPT%"""
    )
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
echo      - Dashboard:    http://localhost:3000
if "%RUN_MAVLINK2REST%"=="1" echo      - MAVLink2REST: http://localhost:8088
if "%RUN_MAIN_APP%"=="1" echo      - Backend:      http://localhost:5077
if "%RUN_MAVSDK_SERVER%"=="1" echo      - MAVSDK gRPC:   localhost:50051
echo.
if "%DEV_MODE%"=="1" (
    call :print_yellow "    Development mode: Hot-reload enabled for dashboard"
)
if "%FORCE_REBUILD%"=="1" (
    call :print_yellow "    Dashboard rebuild was requested"
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
