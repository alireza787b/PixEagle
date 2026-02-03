@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM run_dashboard.bat - PixEagle Dashboard Server
REM ============================================================================
REM Runs the React dashboard in development or production mode.
REM
REM Usage: run_dashboard.bat [-d] [-f] [PORT]
REM   -d, --development  Development mode with hot-reload
REM   -f, --force        Force rebuild
REM   PORT               Server port (default: 3000)
REM ============================================================================

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Load common variables
call "%SCRIPT_DIR%\scripts\common.bat"

REM Defaults
set "MODE=production"
set "PORT=3000"
set "DASHBOARD_DIR=%SCRIPT_DIR%\dashboard"
set "FORCE_REBUILD=false"

REM Parse arguments
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="-d" ( set "MODE=development" & shift & goto :parse_args )
if /i "%~1"=="--development" ( set "MODE=development" & shift & goto :parse_args )
if /i "%~1"=="-f" ( set "FORCE_REBUILD=true" & shift & goto :parse_args )
if /i "%~1"=="--force" ( set "FORCE_REBUILD=true" & shift & goto :parse_args )
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="--help" goto :show_help
REM Check if numeric (port)
echo %~1| findstr /r "^[0-9][0-9]*$" >nul
if %errorlevel% equ 0 ( set "PORT=%~1" & shift & goto :parse_args )
set "DASHBOARD_DIR=%~1"
shift
goto :parse_args
:args_done

REM Display header
echo.
echo ============================================================
echo   PixEagle Dashboard Server
echo ============================================================
echo   Mode: %MODE%
echo   Port: %PORT%
echo   Directory: %DASHBOARD_DIR%
echo ============================================================
echo.

REM Verify directory
if not exist "%DASHBOARD_DIR%" (
    call :error "Dashboard directory not found"
    echo       Expected: %DASHBOARD_DIR%
    pause
    exit /b 1
)
cd /d "%DASHBOARD_DIR%"

REM Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    call :error "Node.js not installed"
    echo       Download: https://nodejs.org/en/download
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node -v') do call :ok "Node.js %%v"

REM Check npm
where npm >nul 2>&1
if %errorlevel% neq 0 (
    call :error "npm not found"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('npm -v') do call :ok "npm %%v"
echo.

REM Install dependencies if needed
if not exist "node_modules" (
    call :info "Installing dependencies..."
    call :npm_install
    if !errorlevel! neq 0 (
        call :error "Failed to install dependencies"
        pause
        exit /b 1
    )
) else (
    call :ok "Dependencies ready"
)

REM Check/kill existing process on port
call :check_port %PORT%
if "%PORT_IN_USE%"=="1" (
    call :warn "Port %PORT% in use - killing process"
    taskkill /PID %PORT_PID% /F >nul 2>&1
    if !errorlevel! equ 0 (
        call :ok "Port freed"
    )
) else (
    call :ok "Port %PORT% available"
)
echo.

REM Start server
if "%MODE%"=="development" (
    echo Starting development server...
    echo.
    set "PORT=%PORT%"
    call npm start
) else (
    REM Production mode - build if needed
    if "%FORCE_REBUILD%"=="true" (
        call :info "Force rebuild requested"
        set "NEEDS_BUILD=1"
    ) else if not exist "build" (
        call :info "No build found - building..."
        set "NEEDS_BUILD=1"
    ) else (
        call :ok "Using cached build"
        set "NEEDS_BUILD=0"
    )

    if "!NEEDS_BUILD!"=="1" (
        echo.
        echo Building for production...
        call npm run build
        if !errorlevel! neq 0 (
            call :error "Build failed"
            pause
            exit /b 1
        )
        call :ok "Build complete"
    )

    REM Get LAN IP
    call :get_lan_ip

    echo.
    echo ============================================================
    echo   %GREEN%Dashboard Ready%NC%
    echo ============================================================
    echo.
    echo   Local:   http://localhost:%PORT%
    echo   Network: http://%LAN_IP%:%PORT%
    echo.
    echo   Press Ctrl+C to stop
    echo.
    echo ============================================================
    echo.

    set "NO_UPDATE_NOTIFIER=1"
    call npx serve -s build -l %PORT% --no-clipboard
)

exit /b 0

REM ============================================================================
REM Functions
REM ============================================================================

:ok
echo   %GREEN%%CHECK%%NC% %~1
goto :eof

:error
echo   %RED%%CROSS%%NC% %~1
goto :eof

:warn
echo   %YELLOW%%WARN%%NC% %~1
goto :eof

:info
echo   %BLUE%%INFO%%NC% %~1
goto :eof

:check_port
set "PORT_IN_USE=0"
set "PORT_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%~1 " ^| findstr "LISTENING" 2^>nul') do (
    set "PORT_PID=%%a"
    set "PORT_IN_USE=1"
)
goto :eof

:get_lan_ip
set "LAN_IP=localhost"
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    for /f "tokens=*" %%b in ("%%a") do (
        set "LAN_IP=%%b"
        set "LAN_IP=!LAN_IP: =!"
        goto :eof
    )
)
goto :eof

:npm_install
echo.
REM Try npm ci first
if exist "package-lock.json" (
    call npm ci
    if !errorlevel! equ 0 (
        call :ok "Dependencies installed (npm ci)"
        exit /b 0
    )
)
REM Fallback to npm install
call npm install
if !errorlevel! equ 0 (
    call :ok "Dependencies installed (npm install)"
    exit /b 0
)
exit /b 1

:show_help
echo.
echo ============================================================
echo   PixEagle Dashboard Server - Help
echo ============================================================
echo.
echo   Usage: run_dashboard.bat [OPTIONS] [PORT]
echo.
echo   Options:
echo     -d, --development  Development mode (hot-reload)
echo     -f, --force        Force rebuild
echo     -h, --help         Show this help
echo.
echo   Examples:
echo     run_dashboard.bat              Production on port 3000
echo     run_dashboard.bat -d           Development mode
echo     run_dashboard.bat 4000         Production on port 4000
echo     run_dashboard.bat -d 4000      Development on port 4000
echo.
echo ============================================================
exit /b 0
