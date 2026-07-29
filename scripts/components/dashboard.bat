@echo off
REM ============================================================================
REM scripts\components\dashboard.bat - Run PixEagle Dashboard (Windows)
REM ============================================================================
REM Starts the React dashboard with optional development mode.
REM
REM Usage:
REM   scripts\components\dashboard.bat          (production build)
REM   scripts\components\dashboard.bat --dev    (development mode with hot-reload)
REM   scripts\components\dashboard.bat --rebuild (force production rebuild)
REM   scripts\components\dashboard.bat --port 3040
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"
call "%PIXEAGLE_DIR%\scripts\lib\ports.bat"

REM Configuration
set "DASHBOARD_DIR=%PIXEAGLE_DIR%\dashboard"
set "CACHE_DIR=%DASHBOARD_DIR%\.pixeagle_cache"
set "BUILD_DIR=%DASHBOARD_DIR%\build"
set "DASHBOARD_PORT=%PIXEAGLE_PORT_DASHBOARD%"
if not defined PIXEAGLE_DASHBOARD_HOST set "PIXEAGLE_DASHBOARD_HOST=127.0.0.1"
if not defined PIXEAGLE_DASHBOARD_EXPOSURE_MODE set "PIXEAGLE_DASHBOARD_EXPOSURE_MODE=local_only"

REM Parse arguments
set "DEV_MODE=0"
set "FORCE_REBUILD=0"

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--dev" set "DEV_MODE=1"
if /I "%~1"=="-d" set "DEV_MODE=1"
if /I "%~1"=="--rebuild" set "FORCE_REBUILD=1"
if /I "%~1"=="-r" set "FORCE_REBUILD=1"
if /I "%~1"=="--force" set "FORCE_REBUILD=1"
if /I "%~1"=="-f" set "FORCE_REBUILD=1"
if /I "%~1"=="--port" (
    if "%~2"=="" (
        echo [31m[ERROR] Missing value for --port[0m
        exit /b 1
    )
    set "DASHBOARD_PORT=%~2"
    shift
)
if /I "%~1"=="--help" goto :show_help
if /I "%~1"=="-h" goto :show_help
shift
goto :parse_args

:show_help
echo Usage: scripts\components\dashboard.bat [--dev^|-d] [--rebuild^|-r] [--port PORT]
echo.
echo   --dev, -d       Start React dashboard in development mode
echo   --rebuild, -r   Force production rebuild before serving
echo   --port PORT     Dashboard HTTP port ^(default from dashboard/.env or 3040^)
echo.
exit /b 0

:args_done

if /I not "%PIXEAGLE_DASHBOARD_EXPOSURE_MODE%"=="local_only" if /I not "%PIXEAGLE_DASHBOARD_EXPOSURE_MODE%"=="trusted_lan_legacy" (
    echo [31m[ERROR] Invalid PIXEAGLE_DASHBOARD_EXPOSURE_MODE: %PIXEAGLE_DASHBOARD_EXPOSURE_MODE%[0m
    exit /b 1
)
if /I not "%PIXEAGLE_DASHBOARD_HOST%"=="127.0.0.1" if /I not "%PIXEAGLE_DASHBOARD_HOST%"=="localhost" if /I not "%PIXEAGLE_DASHBOARD_EXPOSURE_MODE%"=="trusted_lan_legacy" (
    echo [31m[ERROR] Non-loopback dashboard bind requires PIXEAGLE_DASHBOARD_EXPOSURE_MODE=trusted_lan_legacy[0m
    exit /b 1
)
if /I "%PIXEAGLE_DASHBOARD_EXPOSURE_MODE%"=="trusted_lan_legacy" if /I not "%PIXEAGLE_DASHBOARD_HOST%"=="127.0.0.1" if /I not "%PIXEAGLE_DASHBOARD_HOST%"=="localhost" (
    echo [33m[WARNING] trusted_lan_legacy dashboard exposure is unauthenticated and not production-approved.[0m
)

REM Normalize and validate port (handles accidental quotes/whitespace from callers)
set "DASHBOARD_PORT=!DASHBOARD_PORT:"=!"
for /f "tokens=1" %%A in ("!DASHBOARD_PORT!") do set "DASHBOARD_PORT=%%~A"

set "DASHBOARD_PORT_NON_DIGIT="
for /f "delims=0123456789" %%A in ("!DASHBOARD_PORT!") do set "DASHBOARD_PORT_NON_DIGIT=%%A"
if "!DASHBOARD_PORT!"=="" (
    echo [31m[ERROR] Invalid dashboard port: %DASHBOARD_PORT%[0m
    exit /b 1
)
if defined DASHBOARD_PORT_NON_DIGIT (
    echo [31m[ERROR] Invalid dashboard port: %DASHBOARD_PORT%[0m
    exit /b 1
)
set /a DASHBOARD_PORT_NUM=!DASHBOARD_PORT! >nul 2>&1
if !DASHBOARD_PORT_NUM! lss 1 (
    echo [31m[ERROR] Invalid dashboard port: %DASHBOARD_PORT%[0m
    exit /b 1
)
if !DASHBOARD_PORT_NUM! gtr 65535 (
    echo [31m[ERROR] Invalid dashboard port: %DASHBOARD_PORT%[0m
    exit /b 1
)

echo.
echo [36m========================================================================[0m
if "%DEV_MODE%"=="1" (
    echo                  PixEagle Dashboard - Development Mode
) else (
    echo                  PixEagle Dashboard - Production Build
)
echo [36m========================================================================[0m
echo.

REM Check if dashboard directory exists
if not exist "%DASHBOARD_DIR%" (
    echo [31m[ERROR] Dashboard directory not found at: %DASHBOARD_DIR%[0m
    pause
    exit /b 1
)

REM Change to dashboard directory
cd /d "%DASHBOARD_DIR%"

REM A component launcher never terminates an unknown port owner.
echo    [*] Verifying dashboard port %DASHBOARD_PORT% is free...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%DASHBOARD_PORT% " ^| findstr "LISTENING"') do (
    echo [31m[ERROR] Port %DASHBOARD_PORT% is already in use by PID %%a.[0m
    echo         No process was terminated. Use scripts\status.bat or choose another port.
    exit /b 1
)

REM Check if node_modules exists
if not exist "%DASHBOARD_DIR%\node_modules" (
    echo [31m[ERROR] Dashboard dependencies are missing.[0m
    echo         Run scripts\init.bat; runtime launchers never mutate dependencies.
    exit /b 1
)

REM Branch based on mode
if "%DEV_MODE%"=="1" goto :dev_mode
goto :prod_mode

:dev_mode
echo    [*] Starting dashboard in development mode...
echo    [*] Hot-reload enabled - changes will auto-refresh
echo.
set "PORT=%DASHBOARD_PORT%"
set "HOST=%PIXEAGLE_DASHBOARD_HOST%"
call npm start
goto :check_exit

:prod_mode
echo    [*] Checking for cached build...

REM Create cache directory if needed
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"

if "%FORCE_REBUILD%"=="1" (
    echo [31m[ERROR] Runtime launchers do not rebuild application assets.[0m
    echo         Run scripts\init.bat --force-dashboard --without-sidecars.
    exit /b 1
)

node "%PIXEAGLE_DIR%\scripts\lib\dashboard_contract.js" build-complete "%DASHBOARD_DIR%"
if errorlevel 1 (
    echo [31m[ERROR] Dashboard production build is incomplete.[0m
    echo         Run scripts\init.bat.
    exit /b 1
)

:serve_build
echo.
echo    [*] Starting production server on port %DASHBOARD_PORT%...
echo.

node "%DASHBOARD_DIR%\node_modules\serve\build\main.js" -s build -l tcp://%PIXEAGLE_DASHBOARD_HOST%:%DASHBOARD_PORT%
goto :check_exit

:check_exit
if errorlevel 1 (
    echo.
    echo [31m[ERROR] Dashboard exited with error code[0m
    pause
)

endlocal
