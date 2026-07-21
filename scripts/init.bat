@echo off
setlocal enabledelayedexpansion

if /I not "%PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS%"=="1" (
    echo [ERROR] Native Windows setup is experimental and is not parity-verified.
    echo         Use the maintained Linux installer through WSL for normal setup.
    echo         Contributors may explicitly opt in with:
    echo         set PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1
    exit /b 1
)

REM ============================================================================
REM scripts\init.bat - PixEagle Setup Wizard for Windows
REM ============================================================================
REM Sets up the complete PixEagle environment:
REM   - Python virtual environment
REM   - Python dependencies
REM   - Node.js dashboard
REM   - Configuration defaults
REM   - MAVSDK and MAVLink2REST binaries
REM
REM Usage: scripts\init.bat
REM ============================================================================

REM Get script directory and PixEagle root
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%I in ("%SCRIPTS_DIR%\..") do set "PIXEAGLE_DIR=%%~fI"

REM Match scripts/lib/common.sh: explicit override, existing .venv, legacy
REM venv, then .venv for a fresh installation.
if defined PIXEAGLE_VENV_DIR (
    pushd "%PIXEAGLE_DIR%"
    for %%I in ("%PIXEAGLE_VENV_DIR%") do set "VENV_DIR=%%~fI"
    popd
) else if exist "%PIXEAGLE_DIR%\.venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
) else if exist "%PIXEAGLE_DIR%\venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\venv"
) else if exist "%PIXEAGLE_DIR%\.venv" (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
) else (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
)
set "VENV_ACTIVATE=%VENV_DIR%\Scripts\activate.bat"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

REM Load common variables
call "%SCRIPTS_DIR%\lib\common.bat"

REM Configuration
set "TOTAL_STEPS=9"
set "MIN_PYTHON_VERSION=3.9"
set "MAX_TESTED_PYTHON_MINOR=12"
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

        if !PY_MAJOR! gtr 3 (
            call :warn "Python !PYTHON_VERSION! is newer than tested range (3.9-3.%MAX_TESTED_PYTHON_MINOR%)"
            call :warn "If installation fails, use Python 3.10-3.12 for best compatibility"
        ) else if !PY_MAJOR! equ 3 if !PY_MINOR! gtr %MAX_TESTED_PYTHON_MINOR% (
            call :warn "Python !PYTHON_VERSION! is newer than tested range (3.9-3.%MAX_TESTED_PYTHON_MINOR%)"
            call :warn "If installation fails, use Python 3.10-3.12 for best compatibility"
        )
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
if not exist "%PIXEAGLE_DIR%\requirements.txt" (
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

cd /d "%PIXEAGLE_DIR%"

if not defined VENV_DIR (
    call :error "Virtual-environment path is empty"
    exit /b 1
)
if /i "%VENV_DIR%"=="%PIXEAGLE_DIR%" (
    call :error "PIXEAGLE_VENV_DIR must point to a dedicated directory"
    exit /b 1
)

if exist "%VENV_ACTIVATE%" (
    call :info "Existing virtual environment found - reusing"
    call :ok "Virtual environment ready"
    goto :step4
)

if exist "%VENV_DIR%" (
    if defined PIXEAGLE_VENV_DIR (
        call :error "Configured virtual environment is incomplete: %VENV_DIR%"
        echo       Remove or repair it explicitly; setup will not delete a custom path.
        exit /b 1
    )
    call :warn "Removing corrupted virtual environment..."
    rmdir /s /q "%VENV_DIR%" 2>nul
)

echo       Creating venv...
python -m venv "%VENV_DIR%" 2>&1
if %errorlevel% neq 0 (
    call :error "Failed to create virtual environment"
    pause
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
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

call "%VENV_ACTIVATE%"

for /f %%a in ('findstr /r /c:"^[^#]" requirements.txt ^| find /c /v ""') do set "PKG_COUNT=%%a"
call :info "Installing %PKG_COUNT% packages"
call :warn "Large packages may take several minutes"
echo.

echo       Upgrading pip and wheel tooling...
python -m pip install --upgrade pip wheel
if !errorlevel! neq 0 (
    call :warn "pip/wheel upgrade failed - continuing with existing tooling"
)

if !PY_MAJOR! equ 3 if !PY_MINOR! geq 13 (
    echo.
    call :warn "Python !PYTHON_VERSION! detected - pre-installing NumPy 2.x wheel for compatibility"
    python -m pip install --only-binary=:all: "numpy>=2.1.0,<3.0"
    if !errorlevel! neq 0 (
        call :warn "NumPy pre-install failed (non-fatal). requirements.txt includes a fallback marker."
    )
)

echo       Installing packages...
python -m pip install --prefer-binary -r requirements.txt
if !errorlevel! neq 0 (
    call :error "Some packages failed to install"
    echo       Common fixes:
    echo         1. Use Python 3.10-3.12 for best wheel availability
    echo         2. Re-run: python -m pip install --upgrade pip wheel
    echo         3. Remove or repair "%VENV_DIR%" and run scripts\init.bat again
    call "%VENV_DIR%\Scripts\deactivate.bat" 2>nul
    pause
    exit /b 1
)

python -c "import cv2; import numpy" 2>nul
if !errorlevel! equ 0 (
    call :ok "Dependencies installed successfully"
) else (
    call :error "Core packages not installed correctly"
    call "%VENV_DIR%\Scripts\deactivate.bat" 2>nul
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

if not exist "%PIXEAGLE_DIR%\dashboard" (
    call :warn "Dashboard directory not found"
    goto :step7
)

if "%NODE_OK%"=="false" (
    call :warn "Node.js required - skipping dashboard"
    echo       Install Node.js, then run: cd dashboard ^&^& npm install
    goto :step7
)

pushd "%PIXEAGLE_DIR%\dashboard"
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
REM Step 7: Configuration Defaults
REM ============================================================================
call :step 7 "Preparing Configuration Defaults"

set "CONFIG_DIR=%PIXEAGLE_DIR%\configs"
set "DEFAULT_CONFIG=%CONFIG_DIR%\config_default.yaml"
set "USER_CONFIG=%CONFIG_DIR%\config.yaml"
set "DASHBOARD_DEFAULT=%PIXEAGLE_DIR%\dashboard\env_default.yaml"
set "DASHBOARD_ENV=%PIXEAGLE_DIR%\dashboard\.env"
set "STAGED_DEFAULTS=%CONFIG_DIR%\.config_default_preupdate.yaml"
set "CONFIG_SYNC_SCRIPT=%PIXEAGLE_DIR%\scripts\setup\config-sync-status.py"
set "CONFIG_DEFAULTS_READY=false"

if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"

if not exist "%DEFAULT_CONFIG%" (
    call :error "Default config not found"
    goto :step8
)

if exist "%USER_CONFIG%" (
    call :info "Keeping existing configs\config.yaml"
    call :info "Use reset-config or a setup profile when you intentionally want a new local runtime config"
) else (
    call :ok "Using checked-in defaults from configs\config_default.yaml"
    call :info "No configs\config.yaml created; setup profiles create local overrides only when needed"
)

if not exist "%VENV_PYTHON%" (
    call :warn "Config lifecycle Python is unavailable"
) else if not exist "%CONFIG_SYNC_SCRIPT%" (
    call :warn "Config lifecycle status script is unavailable"
) else (
    if exist "%STAGED_DEFAULTS%" (
        "%VENV_PYTHON%" "%CONFIG_SYNC_SCRIPT%" --initialize-baseline-from "%STAGED_DEFAULTS%"
        if !errorlevel! equ 0 (
            del /f /q "%STAGED_DEFAULTS%" 2>nul
            if exist "%STAGED_DEFAULTS%" (
                call :warn "Consumed config baseline could not be removed"
            ) else (
                set "CONFIG_DEFAULTS_READY=true"
                call :ok "Pre-update config baseline consumed"
            )
        ) else (
            call :warn "Could not consume the preserved pre-update config baseline"
        )
    ) else (
        "%VENV_PYTHON%" "%CONFIG_SYNC_SCRIPT%" --initialize-baseline
        if !errorlevel! equ 0 (
            set "CONFIG_DEFAULTS_READY=true"
            call :ok "Config update baseline and retirement status checked"
        ) else (
            call :warn "Could not initialize or report config update metadata"
        )
    )
)
if not "!CONFIG_DEFAULTS_READY!"=="true" (
    call :warn "Configuration lifecycle is degraded; rerun scripts\init.bat after fixing the error"
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

set "MAVSDK_SCRIPT=%SCRIPTS_DIR%\setup\download-binaries.bat"

if not exist "%MAVSDK_SCRIPT%" (
    call :warn "Download script not found"
    goto :step9
)

if exist "%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe" (
    call :info "MAVSDK Server binary exists; verifying manifest checksum"
    call "%MAVSDK_SCRIPT%" --mavsdk
    if !errorlevel! equ 0 (
        call :ok "MAVSDK Server binary verified"
    ) else (
        call :warn "Existing MAVSDK Server failed verification"
    )
    goto :step9
)

echo.
call :info "MAVSDK Server required for drone communication"
set /p "REPLY=       Download now? [Y/n]: "
echo.

if /i not "!REPLY!"=="n" (
    call "%MAVSDK_SCRIPT%" --mavsdk
    if !errorlevel! equ 0 (
        call :ok "MAVSDK Server installed"
    ) else (
        call :warn "Download failed - install manually later"
    )
) else (
    call :info "Skipped - run scripts\setup\download-binaries.bat --mavsdk later"
)

:step9
REM ============================================================================
REM Step 9: MAVLink2REST
REM ============================================================================
call :step 9 "MAVLink2REST Server"

set "M2R_SCRIPT=%SCRIPTS_DIR%\setup\download-binaries.bat"

if not exist "%M2R_SCRIPT%" (
    call :warn "Download script not found"
    goto :summary
)

if exist "%PIXEAGLE_DIR%\bin\mavlink2rest.exe" (
    call :info "MAVLink2REST binary exists; verifying manifest checksum"
    call "%M2R_SCRIPT%" --mavlink2rest
    if !errorlevel! equ 0 (
        call :ok "MAVLink2REST binary verified"
    ) else (
        call :warn "Existing MAVLink2REST failed verification"
    )
    goto :summary
)

echo.
call :info "MAVLink2REST provides REST API for MAVLink"
set /p "REPLY=       Download now? [Y/n]: "
echo.

if /i not "!REPLY!"=="n" (
    call "%M2R_SCRIPT%" --mavlink2rest
    if !errorlevel! equ 0 (
        call :ok "MAVLink2REST installed"
    ) else (
        call :warn "Download failed - install manually later"
    )
) else (
    call :info "Skipped - run scripts\setup\download-binaries.bat --mavlink2rest later"
)

:summary
REM Deactivate venv
call "%VENV_DIR%\Scripts\deactivate.bat" 2>nul

if not "%CONFIG_DEFAULTS_READY%"=="true" (
    echo.
    echo ============================================================
    echo   %RED%Setup Incomplete%NC%
    echo ============================================================
    echo.
    call :error "Configuration lifecycle validation failed"
    echo       Do not start PixEagle yet.
    echo       Resolve the warning above, then rerun scripts\init.bat.
    echo       A preserved pre-update baseline is never deleted after failure.
    echo.
    pause
    exit /b 1
)

REM ============================================================================
REM Summary
REM ============================================================================

set "MAVSDK_STATUS=%RED%Not installed%NC%"
if exist "%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe" set "MAVSDK_STATUS=%GREEN%Installed%NC%"

set "M2R_STATUS=%RED%Not installed%NC%"
if exist "%PIXEAGLE_DIR%\bin\mavlink2rest.exe" set "M2R_STATUS=%GREEN%Installed%NC%"

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
echo   %CHECK% Configuration defaults ready
echo.
echo   MAVSDK Server:   %MAVSDK_STATUS%
echo   MAVLink2REST:    %M2R_STATUS%
echo.
echo   %CYAN%Next Steps:%NC%
echo   1. Run: %BOLD%scripts\run.bat%NC%
echo   2. Optional QGC field video:
echo      %BOLD%"%VENV_PYTHON%" scripts\setup\apply-setup-profile.py --profile field_qgc_video --gcs-host ^<gcs-ip^>%NC%
echo   Guarded QGC HTTPS/WSS direct media profiles must be generated on the Linux PixEagle deployment host.
echo.
if not exist "%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe" (
    echo   Optional: %BOLD%scripts\setup\download-binaries.bat --mavsdk%NC%
)
if not exist "%PIXEAGLE_DIR%\bin\mavlink2rest.exe" (
    echo   Optional: %BOLD%scripts\setup\download-binaries.bat --mavlink2rest%NC%
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
