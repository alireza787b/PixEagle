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

setlocal

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

echo %DASHBOARD_PORT% | findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
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

REM Check and kill any existing process on the dashboard port
echo    [*] Checking for existing processes on port %DASHBOARD_PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%DASHBOARD_PORT% " ^| findstr "LISTENING"') do (
    echo    [*] Killing existing process on port %DASHBOARD_PORT% ^(PID: %%a^)
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Check if node_modules exists
if not exist "%DASHBOARD_DIR%\node_modules" (
    echo    [*] Installing npm dependencies...
    call npm install
    if errorlevel 1 (
        echo [31m[ERROR] npm install failed[0m
        pause
        exit /b 1
    )
)

REM Branch based on mode
if "%DEV_MODE%"=="1" goto :dev_mode
goto :prod_mode

:dev_mode
echo    [*] Starting dashboard in development mode...
echo    [*] Hot-reload enabled - changes will auto-refresh
echo.
set "PORT=%DASHBOARD_PORT%"
call npm start
goto :check_exit

:prod_mode
echo    [*] Checking for cached build...

REM Create cache directory if needed
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"

if "%FORCE_REBUILD%"=="1" (
    echo    [*] Force rebuild requested...
    goto :do_build
)

REM Check if build exists
if not exist "%BUILD_DIR%\index.html" (
    echo    [-] No build found, building...
    goto :do_build
)

echo [32m   [OK] Using cached build[0m
goto :serve_build

:do_build
echo    [*] Building dashboard (this may take a moment)...
call npm run build
if errorlevel 1 (
    echo [31m[ERROR] Build failed[0m
    pause
    exit /b 1
)
echo [32m   [OK] Build complete[0m

:serve_build
echo.
echo    [*] Starting production server on port %DASHBOARD_PORT%...
echo.

REM Check if serve is installed globally
where serve >nul 2>&1
if errorlevel 1 goto :use_npx_serve

REM Use global serve
serve -s build -l %DASHBOARD_PORT%
goto :check_exit

:use_npx_serve
REM Use npx serve
call npx serve -s build -l %DASHBOARD_PORT%
goto :check_exit

:check_exit
if errorlevel 1 (
    echo.
    echo [31m[ERROR] Dashboard exited with error code[0m
    pause
)

endlocal
