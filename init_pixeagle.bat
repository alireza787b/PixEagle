@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM init_pixeagle.bat - PixEagle Setup Wizard for Windows
REM ============================================================================
REM Sets up the complete PixEagle environment:
REM   - Python virtual environment
REM   - Python dependencies
REM   - Node.js dashboard
REM   - Configuration files
REM   - MAVSDK and MAVLink2REST binaries
REM
REM Usage: init_pixeagle.bat
REM ============================================================================

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Load common variables
call "%SCRIPT_DIR%\scripts\common.bat"

REM Configuration
set "TOTAL_STEPS=9"
set "MIN_PYTHON_VERSION=3.9"
set "REQUIRED_DISK_MB=500"

REM Clear screen and display header
cls
call :show_header

REM ============================================================================
REM Step 1: Check System Requirements
REM ============================================================================
call :step 1 "Checking System Requirements"

set "ERRORS=0"

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    call :error "Python 3 not installed"
    echo       Download: https://www.python.org/downloads/
    set /a "ERRORS+=1"
) else (
    for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PYTHON_VERSION=%%v"

    for /f "tokens=1,2 delims=." %%a in ("!PYTHON_VERSION!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )

    if !PY_MAJOR! lss 3 (
        call :error "Python %MIN_PYTHON_VERSION%+ required (found !PYTHON_VERSION!)"
        set /a "ERRORS+=1"
    ) else if !PY_MAJOR! equ 3 if !PY_MINOR! lss 9 (
        call :error "Python %MIN_PYTHON_VERSION%+ required (found !PYTHON_VERSION!)"
        set /a "ERRORS+=1"
    ) else (
        call :ok "Python !PYTHON_VERSION!"
    )
)

REM Check disk space
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free / 1MB)"') do set "AVAILABLE_MB=%%a"

if %AVAILABLE_MB% lss %REQUIRED_DISK_MB% (
    call :error "Insufficient disk space (%AVAILABLE_MB%MB / %REQUIRED_DISK_MB%MB required)"
    set /a "ERRORS+=1"
) else (
    call :ok "Disk space: %AVAILABLE_MB% MB available"
)

REM Check PixEagle directory
if not exist "requirements.txt" (
    call :error "Not in PixEagle directory (requirements.txt not found)"
    set /a "ERRORS+=1"
) else (
    call :ok "PixEagle directory verified"
)

if %ERRORS% gtr 0 (
    echo.
    call :error "System check failed with %ERRORS% error(s)"
    echo.
    pause
    exit /b 1
)

REM ============================================================================
REM Step 2: System Prerequisites
REM ============================================================================
call :step 2 "Checking Prerequisites"

where curl.exe >nul 2>&1
if %errorlevel% equ 0 (
    call :ok "curl.exe available"
) else (
    call :info "curl.exe not found - will use PowerShell"
)

where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=3" %%v in ('git --version') do call :ok "Git %%v"
) else (
    call :info "Git not installed (optional)"
)

REM ============================================================================
REM Step 3: Python Virtual Environment
REM ============================================================================
call :step 3 "Setting up Virtual Environment"

if exist "venv\Scripts\activate.bat" (
    call :info "Existing venv found - reusing"
    call :ok "Virtual environment ready"
    goto :step4
)

if exist "venv" (
    call :warn "Removing corrupted venv..."
    rmdir /s /q venv 2>nul
)

echo       Creating venv...
python -m venv venv 2>&1
if %errorlevel% neq 0 (
    call :error "Failed to create virtual environment"
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    call :error "Virtual environment creation failed"
    pause
    exit /b 1
)

call :ok "Virtual environment created"

:step4
REM ============================================================================
REM Step 4: Python Dependencies
REM ============================================================================
call :step 4 "Installing Python Dependencies"

call venv\Scripts\activate.bat

for /f %%a in ('findstr /r /c:"^[^#]" requirements.txt ^| find /c /v ""') do set "PKG_COUNT=%%a"
call :info "Installing %PKG_COUNT% packages"
call :warn "Large packages may take several minutes"
echo.

echo       Upgrading pip...
python -m pip install --upgrade pip -q 2>nul

echo       Installing packages...
python -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    call :error "Some packages failed to install"
    call venv\Scripts\deactivate.bat 2>nul
    pause
    exit /b 1
)

python -c "import cv2; import numpy" 2>nul
if !errorlevel! equ 0 (
    call :ok "Dependencies installed successfully"
) else (
    call :error "Core packages not installed correctly"
    call venv\Scripts\deactivate.bat 2>nul
    pause
    exit /b 1
)

REM ============================================================================
REM Step 5: Node.js Setup
REM ============================================================================
call :step 5 "Checking Node.js"

where node >nul 2>&1
if %errorlevel% neq 0 (
    call :warn "Node.js not installed"
    echo       Download: https://nodejs.org/en/download
    set "NODE_OK=false"
) else (
    for /f "tokens=*" %%v in ('node -v') do set "NODE_VERSION=%%v"
    call :ok "Node.js !NODE_VERSION!"

    where npm >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%v in ('npm -v') do call :ok "npm %%v"
        set "NODE_OK=true"
    ) else (
        call :warn "npm not found"
        set "NODE_OK=false"
    )
)

REM ============================================================================
REM Step 6: Dashboard Dependencies
REM ============================================================================
call :step 6 "Setting up Dashboard"

if not exist "dashboard" (
    call :warn "Dashboard directory not found"
    goto :step7
)

if "%NODE_OK%"=="false" (
    call :warn "Node.js required - skipping dashboard"
    echo       Install Node.js, then run: cd dashboard ^&^& npm install
    goto :step7
)

pushd dashboard
echo       Installing npm packages...
call npm install --silent 2>nul
if !errorlevel! equ 0 (
    call :ok "Dashboard dependencies installed"
) else (
    call :warn "npm install had issues - try manually"
)
popd

:step7
REM ============================================================================
REM Step 7: Configuration Files
REM ============================================================================
call :step 7 "Generating Configuration"

set "CONFIG_DIR=%SCRIPT_DIR%\configs"
set "DEFAULT_CONFIG=%CONFIG_DIR%\config_default.yaml"
set "USER_CONFIG=%CONFIG_DIR%\config.yaml"
set "DASHBOARD_DEFAULT=%SCRIPT_DIR%\dashboard\env_default.yaml"
set "DASHBOARD_ENV=%SCRIPT_DIR%\dashboard\.env"

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

if not exist "%DEFAULT_CONFIG%" (
    call :error "Default config not found"
    goto :step8
)

if exist "%USER_CONFIG%" (
    echo.
    call :warn "Existing config.yaml found"
    set /p "REPLY=       Replace with latest default? [y/N]: "
    echo.

    if /i "!REPLY!"=="y" (
        for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value 2^>nul') do set "dt=%%a"
        copy "%USER_CONFIG%" "%USER_CONFIG%.backup.!dt:~0,8!" >nul 2>&1
        copy "%DEFAULT_CONFIG%" "%USER_CONFIG%" >nul 2>&1
        call :ok "Config replaced (backup created)"
    ) else (
        call :info "Keeping existing config"
    )
) else (
    copy "%DEFAULT_CONFIG%" "%USER_CONFIG%" >nul 2>&1
    call :ok "Created config.yaml"
)

if exist "%DASHBOARD_DEFAULT%" (
    if not exist "%DASHBOARD_ENV%" (
        python -c "import yaml; f=open(r'%DASHBOARD_DEFAULT%','r'); c=yaml.safe_load(f); f.close(); e=open(r'%DASHBOARD_ENV%','w'); [e.write(f'{k}={v}\n') for k,v in c.items()]; e.close()" 2>nul
        if !errorlevel! equ 0 (
            call :ok "Created dashboard .env"
        )
    ) else (
        call :info "Dashboard .env exists"
    )
)

:step8
REM ============================================================================
REM Step 8: MAVSDK Server
REM ============================================================================
call :step 8 "MAVSDK Server"

set "MAVSDK_BIN=%SCRIPT_DIR%\mavsdk_server_bin.exe"
set "MAVSDK_SCRIPT=%SCRIPT_DIR%\src\tools\download_mavsdk_server.bat"

if exist "%MAVSDK_BIN%" (
    call :ok "MAVSDK Server already installed"
    goto :step9
)

if not exist "%MAVSDK_SCRIPT%" (
    call :warn "Download script not found"
    goto :step9
)

echo.
call :info "MAVSDK Server required for drone communication"
set /p "REPLY=       Download now? [Y/n]: "
echo.

if /i not "!REPLY!"=="n" (
    call "%MAVSDK_SCRIPT%"
    if !errorlevel! equ 0 (
        call :ok "MAVSDK Server installed"
    ) else (
        call :warn "Download failed - install manually later"
    )
) else (
    call :info "Skipped - run download_mavsdk_server.bat later"
)

:step9
REM ============================================================================
REM Step 9: MAVLink2REST
REM ============================================================================
call :step 9 "MAVLink2REST Server"

set "M2R_BIN=%SCRIPT_DIR%\mavlink2rest.exe"
set "M2R_SCRIPT=%SCRIPT_DIR%\src\tools\download_mavlink2rest.bat"

if exist "%M2R_BIN%" (
    call :ok "MAVLink2REST already installed"
    goto :summary
)

if not exist "%M2R_SCRIPT%" (
    call :warn "Download script not found"
    goto :summary
)

echo.
call :info "MAVLink2REST provides REST API for MAVLink"
set /p "REPLY=       Download now? [Y/n]: "
echo.

if /i not "!REPLY!"=="n" (
    call "%M2R_SCRIPT%"
    if !errorlevel! equ 0 (
        call :ok "MAVLink2REST installed"
    ) else (
        call :warn "Download failed - install manually later"
    )
) else (
    call :info "Skipped - run download_mavlink2rest.bat later"
)

:summary
REM Deactivate venv
call venv\Scripts\deactivate.bat 2>nul

REM ============================================================================
REM Summary
REM ============================================================================

set "MAVSDK_STATUS=%RED%Not installed%NC%"
if exist "%SCRIPT_DIR%\mavsdk_server_bin.exe" set "MAVSDK_STATUS=%GREEN%Installed%NC%"

set "M2R_STATUS=%RED%Not installed%NC%"
if exist "%SCRIPT_DIR%\mavlink2rest.exe" set "M2R_STATUS=%GREEN%Installed%NC%"

echo.
echo ============================================================
echo   %GREEN%Setup Complete!%NC%
echo ============================================================
echo.
echo   %CHECK% Python %PYTHON_VERSION% virtual environment
echo   %CHECK% Python dependencies installed
if "%NODE_OK%"=="true" (
    echo   %CHECK% Node.js %NODE_VERSION%
    echo   %CHECK% Dashboard dependencies
) else (
    echo   %WARN% Node.js needs manual setup
)
echo   %CHECK% Configuration files
echo.
echo   MAVSDK Server:   %MAVSDK_STATUS%
echo   MAVLink2REST:    %M2R_STATUS%
echo.
echo   %CYAN%Next Steps:%NC%
echo   1. Edit %BOLD%configs\config.yaml%NC% for your setup
echo   2. Run: %BOLD%run_pixeagle.bat%NC%
echo.
if not exist "%SCRIPT_DIR%\mavsdk_server_bin.exe" (
    echo   Optional: %BOLD%src\tools\download_mavsdk_server.bat%NC%
)
if not exist "%SCRIPT_DIR%\mavlink2rest.exe" (
    echo   Optional: %BOLD%src\tools\download_mavlink2rest.bat%NC%
)
echo.
echo ============================================================
echo.
pause
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
echo   %BOLD%PixEagle Windows Setup%NC%
echo   Vision-Based Drone Tracking System
echo   https://github.com/alireza787b/PixEagle
echo %CYAN%============================================================%NC%
echo.
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
