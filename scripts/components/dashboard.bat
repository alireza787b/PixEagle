@echo off
REM ============================================================================
REM scripts\components\dashboard.bat - Run PixEagle Dashboard (Windows)
REM ============================================================================
REM Starts the React dashboard with optional development mode.
REM
REM Usage:
REM   scripts\components\dashboard.bat          (production build)
REM   scripts\components\dashboard.bat --dev    (development mode with hot-reload)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

REM Configuration
set "DASHBOARD_DIR=%PIXEAGLE_DIR%\dashboard"
set "CACHE_DIR=%DASHBOARD_DIR%\.pixeagle_cache"
set "BUILD_DIR=%DASHBOARD_DIR%\build"

REM Parse arguments
set "DEV_MODE=0"
if "%~1"=="--dev" set "DEV_MODE=1"
if "%~1"=="-d" set "DEV_MODE=1"

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

REM Check and kill any existing process on the dashboard port (3000)
echo    [*] Checking for existing processes on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo    [*] Killing existing process on port 3000 ^(PID: %%a^)
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
call npm start
goto :check_exit

:prod_mode
echo    [*] Checking for cached build...

REM Create cache directory if needed
if not exist "%CACHE_DIR%" mkdir "%CACHE_DIR%"

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
echo    [*] Starting production server on port 3000...
echo.

REM Check if serve is installed globally
where serve >nul 2>&1
if errorlevel 1 goto :use_npx_serve

REM Use global serve
serve -s build -l 3000
goto :check_exit

:use_npx_serve
REM Use npx serve
call npx serve -s build -l 3000
goto :check_exit

:check_exit
if errorlevel 1 (
    echo.
    echo [31m[ERROR] Dashboard exited with error code[0m
    pause
)

endlocal
