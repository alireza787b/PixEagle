@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM run_pixeagle.bat - PixEagle System Launcher for Windows
REM ============================================================================
REM Starts all PixEagle services: Main App, Dashboard, MAVLink2REST, MAVSDK
REM
REM Usage: run_pixeagle.bat [OPTIONS]
REM   --dev, -d     Development mode
REM   --rebuild     Force dashboard rebuild
REM   -m            Skip MAVLink2REST
REM   -p            Skip Python app
REM   -k            Skip MAVSDK Server
REM ============================================================================

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Load common variables
call "%SCRIPT_DIR%\scripts\common.bat"

REM Configuration
set "TOTAL_STEPS=6"

REM Component flags (all enabled by default)
set "RUN_MAVLINK2REST=true"
set "RUN_DASHBOARD=true"
set "RUN_MAIN_APP=true"
set "RUN_MAVSDK=true"

REM Mode flags
set "DEV_MODE=false"
set "FORCE_REBUILD=false"

REM Ports
set "M2R_PORT=8088"
set "BACKEND_PORT=5077"
set "DASHBOARD_PORT=3000"
set "WS_PORT=5551"

REM Paths
set "VENV_DIR=%SCRIPT_DIR%\venv"
set "CONFIG_FILE=%SCRIPT_DIR%\configs\config.yaml"
set "M2R_SCRIPT=%SCRIPT_DIR%\src\tools\mavlink2rest\run_mavlink2rest.bat"
set "DASHBOARD_SCRIPT=%SCRIPT_DIR%\run_dashboard.bat"
set "MAIN_SCRIPT=%SCRIPT_DIR%\run_main.bat"
set "MAVSDK_BIN=%SCRIPT_DIR%\mavsdk_server_bin.exe"
set "MAVSDK_DL=%SCRIPT_DIR%\src\tools\download_mavsdk_server.bat"

REM Parse arguments
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--dev" ( set "DEV_MODE=true" & shift & goto :parse_args )
if /i "%~1"=="-d" ( set "DEV_MODE=true" & shift & goto :parse_args )
if /i "%~1"=="--rebuild" ( set "FORCE_REBUILD=true" & shift & goto :parse_args )
if /i "%~1"=="-r" ( set "FORCE_REBUILD=true" & shift & goto :parse_args )
if /i "%~1"=="-m" ( set "RUN_MAVLINK2REST=false" & shift & goto :parse_args )
if /i "%~1"=="-p" ( set "RUN_MAIN_APP=false" & shift & goto :parse_args )
if /i "%~1"=="-k" ( set "RUN_MAVSDK=false" & shift & goto :parse_args )
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
echo Unknown option: %~1
exit /b 1
:args_done

REM Display header
cls
call :show_header

REM Git info
for /f "tokens=*" %%a in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "GIT_BRANCH=%%a"
for /f "tokens=*" %%a in ('git rev-parse --short HEAD 2^>nul') do set "GIT_COMMIT=%%a"
if defined GIT_BRANCH echo   Branch: %CYAN%%GIT_BRANCH%%NC%  Commit: %GIT_COMMIT%
if "%DEV_MODE%"=="true" echo   %YELLOW%Development Mode%NC%
echo.

REM ============================================================================
REM Step 1: Pre-flight Checks
REM ============================================================================
call :step 1 "Pre-flight Checks"

if not exist "%VENV_DIR%" (
    call :error "Virtual environment not found"
    echo       Run: init_pixeagle.bat
    pause
    exit /b 1
)
call :ok "Virtual environment"

if not exist "%CONFIG_FILE%" (
    call :error "Configuration not found: %CONFIG_FILE%"
    echo       Run: init_pixeagle.bat
    pause
    exit /b 1
)
call :ok "Configuration file"

"%VENV_DIR%\Scripts\python.exe" -c "import cv2, numpy" 2>nul
if %errorlevel% neq 0 (
    call :warn "Some dependencies may be missing"
) else (
    call :ok "Python dependencies"
)

if "%RUN_MAVSDK%"=="true" (
    if not exist "%MAVSDK_BIN%" (
        call :warn "MAVSDK Server not found"
    ) else (
        call :ok "MAVSDK Server"
    )
)

REM ============================================================================
REM Step 2: Cleanup Previous Sessions
REM ============================================================================
call :step 2 "Cleaning Up"

if "%RUN_MAVLINK2REST%"=="true" call :kill_port %M2R_PORT% "MAVLink2REST"
if "%RUN_MAIN_APP%"=="true" (
    call :kill_port %BACKEND_PORT% "Backend"
    call :kill_port %WS_PORT% "WebSocket"
)
if "%RUN_DASHBOARD%"=="true" call :kill_port %DASHBOARD_PORT% "Dashboard"

REM ============================================================================
REM Step 3: Load Configuration
REM ============================================================================
call :step 3 "Configuration"

call :get_lan_ip

call :info "MAVLink2REST: http://%LAN_IP%:%M2R_PORT%"
call :info "Backend API:  http://%LAN_IP%:%BACKEND_PORT%"
call :info "Dashboard:    http://%LAN_IP%:%DASHBOARD_PORT%"

REM Verify scripts exist
if "%RUN_MAIN_APP%"=="true" if not exist "%MAIN_SCRIPT%" (
    call :error "Main script not found"
    pause
    exit /b 1
)
if "%RUN_DASHBOARD%"=="true" if not exist "%DASHBOARD_SCRIPT%" (
    call :error "Dashboard script not found"
    pause
    exit /b 1
)
if "%RUN_MAVLINK2REST%"=="true" if not exist "%M2R_SCRIPT%" (
    call :error "MAVLink2REST script not found"
    pause
    exit /b 1
)

REM ============================================================================
REM Step 4: Start Services
REM ============================================================================
call :step 4 "Starting Services"

REM Handle MAVSDK download if needed
if "%RUN_MAVSDK%"=="true" if not exist "%MAVSDK_BIN%" (
    call :warn "MAVSDK Server not installed"
    echo.
    set /p "REPLY=       Download now? [Y/n]: "
    echo.
    if /i not "!REPLY!"=="n" (
        if exist "%MAVSDK_DL%" (
            call "%MAVSDK_DL%"
            if !errorlevel! neq 0 set "RUN_MAVSDK=false"
        ) else (
            set "RUN_MAVSDK=false"
        )
    ) else (
        set "RUN_MAVSDK=false"
    )
)

REM Count components
set "COUNT=0"
if "%RUN_MAIN_APP%"=="true" set /a "COUNT+=1"
if "%RUN_MAVLINK2REST%"=="true" set /a "COUNT+=1"
if "%RUN_DASHBOARD%"=="true" set /a "COUNT+=1"
if "%RUN_MAVSDK%"=="true" if exist "%MAVSDK_BIN%" set /a "COUNT+=1"

echo       Starting %COUNT% services...
echo.

REM Launch services
if "%RUN_MAIN_APP%"=="true" (
    set "CMD=%MAIN_SCRIPT%"
    if "%DEV_MODE%"=="true" set "CMD=%MAIN_SCRIPT% --dev"
    start "PixEagle - Main" /D "%SCRIPT_DIR%" cmd /k "!CMD!"
    call :ok "Started Main App"
)

if "%RUN_MAVLINK2REST%"=="true" (
    start "PixEagle - MAVLink2REST" /D "%SCRIPT_DIR%" cmd /k "%M2R_SCRIPT%"
    call :ok "Started MAVLink2REST"
)

if "%RUN_DASHBOARD%"=="true" (
    set "CMD=%DASHBOARD_SCRIPT%"
    if "%DEV_MODE%"=="true" set "CMD=%DASHBOARD_SCRIPT% -d"
    if "%FORCE_REBUILD%"=="true" set "CMD=!CMD! -f"
    start "PixEagle - Dashboard" /D "%SCRIPT_DIR%" cmd /k "!CMD!"
    call :ok "Started Dashboard"
)

if "%RUN_MAVSDK%"=="true" if exist "%MAVSDK_BIN%" (
    start "PixEagle - MAVSDK" /D "%SCRIPT_DIR%" cmd /k "%MAVSDK_BIN%"
    call :ok "Started MAVSDK Server"
)

REM ============================================================================
REM Step 5: Wait for Services
REM ============================================================================
call :step 5 "Waiting for Services"

if "%RUN_MAVLINK2REST%"=="true" call :wait_port %M2R_PORT% "MAVLink2REST" 15
if "%RUN_MAIN_APP%"=="true" call :wait_port %BACKEND_PORT% "Backend" 15
if "%RUN_DASHBOARD%"=="true" call :wait_port %DASHBOARD_PORT% "Dashboard" 20

REM ============================================================================
REM Step 6: Summary
REM ============================================================================
call :step 6 "System Ready"

call :ok "Services running in %COUNT% windows"

echo.
echo ============================================================
echo   %GREEN%PixEagle Running!%NC%
echo ============================================================
echo.
echo   %BOLD%Service URLs:%NC%
echo   Dashboard:    %CYAN%http://%LAN_IP%:%DASHBOARD_PORT%%NC%
echo   Backend API:  %CYAN%http://%LAN_IP%:%BACKEND_PORT%%NC%
echo   MAVLink2REST: %CYAN%http://%LAN_IP%:%M2R_PORT%%NC%
echo.
echo   Local: http://localhost:%DASHBOARD_PORT%
echo.
echo   %BOLD%To Stop:%NC% Close all PixEagle windows
echo.
echo ============================================================
echo.
echo Press any key to close this window...
pause >nul
exit /b 0

REM ============================================================================
REM Functions
REM ============================================================================

:show_header
echo.
echo %CYAN%============================================================%NC%
echo.
echo  %CYAN% _____ _      ______            _       %NC%
echo  %CYAN%^|  __ (_)    ^|  ____^|          ^| ^|      %NC%
echo  %CYAN%^| ^|__) ^|__  _^| ^|__   __ _  __ _^| ^| ___ %NC%
echo  %CYAN%^|  ___/ \ \/ /  __^| / _` ^|/ _` ^| ^|/ _ \%NC%
echo  %CYAN%^| ^|   ^| ^|^>  ^<^| ^|___^| (_^| ^| (_^| ^| ^|  __/%NC%
echo  %CYAN%^|_^|   ^|_/_/\_\______\__,_^|\__, ^|_^|\___^|%NC%
echo  %CYAN%                           __/ ^|       %NC%
echo  %CYAN%                          ^|___/        %NC%
echo.
echo %CYAN%============================================================%NC%
echo   %BOLD%PixEagle System Launcher%NC%
goto :eof

:step
echo.
echo %CYAN%[%~1/%TOTAL_STEPS%]%NC% %~2
echo.
goto :eof

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

:kill_port
set "_port=%~1"
set "_name=%~2"
set "_pid="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%_port% " ^| findstr "LISTENING" 2^>nul') do set "_pid=%%a"
if defined _pid (
    taskkill /PID %_pid% /F >nul 2>&1
    if !errorlevel! equ 0 (
        call :ok "Freed port %_port% (%_name%)"
    ) else (
        call :warn "Could not free port %_port%"
    )
) else (
    call :ok "Port %_port% free (%_name%)"
)
goto :eof

:wait_port
set "_port=%~1"
set "_name=%~2"
set "_max=%~3"
if "%_max%"=="" set "_max=15"
echo       Waiting for %_name%...
set "_ready=0"
for /l %%i in (1,1,%_max%) do (
    if !_ready! equ 0 (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%_port% " ^| findstr "LISTENING" 2^>nul') do set "_ready=1"
        if !_ready! equ 0 timeout /t 1 /nobreak >nul
    )
)
if %_ready% equ 1 (
    call :ok "%_name% ready"
) else (
    call :warn "%_name% may not be ready"
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

:show_help
echo.
echo ============================================================
echo   PixEagle System Launcher - Help
echo ============================================================
echo.
echo   Usage: run_pixeagle.bat [OPTIONS]
echo.
echo   Options:
echo     --dev, -d      Development mode (hot-reload)
echo     --rebuild, -r  Force dashboard rebuild
echo     -m             Skip MAVLink2REST
echo     -p             Skip Python app
echo     -k             Skip MAVSDK Server
echo     --help, -h     Show this help
echo.
echo   Examples:
echo     run_pixeagle.bat             Start all services
echo     run_pixeagle.bat --dev       Development mode
echo     run_pixeagle.bat -m -k       Skip MAVLink2REST and MAVSDK
echo.
echo ============================================================
exit /b 0
