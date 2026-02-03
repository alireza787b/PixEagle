@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM download_mavlink2rest.bat - MAVLink2REST Server Downloader for Windows
REM ============================================================================
REM Downloads the MAVLink2REST binary for Windows x86_64.
REM
REM Usage: download_mavlink2rest.bat
REM ============================================================================

REM Get script and PixEagle directories
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fA"

REM Load common variables
call "%PIXEAGLE_DIR%\scripts\common.bat"

REM Configuration
set "MAVLINK2REST_VERSION=1.0.0"
set "GITHUB_REPO=mavlink/mavlink2rest"
set "GITHUB_BASE_URL=https://github.com/%GITHUB_REPO%/releases/download"
set "BINARY_NAME=mavlink2rest-x86_64-pc-windows-msvc.exe"
set "BINARY_URL=%GITHUB_BASE_URL%/%MAVLINK2REST_VERSION%/%BINARY_NAME%"
set "BINARY_PATH=%PIXEAGLE_DIR%\mavlink2rest.exe"

REM Display header
echo.
echo ============================================================
echo   MAVLink2REST Server Downloader
echo ============================================================
echo   Version: %MAVLINK2REST_VERSION%
echo   Binary:  %BINARY_NAME%
echo ============================================================
echo.

REM ============================================================================
REM Step 1: Platform Detection
REM ============================================================================
echo %CYAN%[1/4]%NC% Detecting Platform
echo.

if not "%OS%"=="Windows_NT" (
    call :print_error "This script is for Windows only"
    goto :show_manual
)
call :print_ok "OS: Windows"

if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    call :print_ok "Architecture: x64 (AMD64)"
) else if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    if "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
        call :print_ok "Architecture: x64 (via WoW64)"
    ) else (
        call :print_warn "32-bit Windows - may not work correctly"
    )
) else (
    call :print_warn "Unknown architecture: %PROCESSOR_ARCHITECTURE%"
)

call :print_info "Binary: %BINARY_NAME%"
echo.

REM ============================================================================
REM Step 2: Check Existing Installation
REM ============================================================================
echo %CYAN%[2/4]%NC% Checking Existing Installation
echo.

if exist "%BINARY_PATH%" (
    for %%A in ("%BINARY_PATH%") do set "EXISTING_SIZE=%%~zA"
    set /a "EXISTING_SIZE_MB=!EXISTING_SIZE! / 1024 / 1024"

    call :print_warn "Existing binary found (!EXISTING_SIZE_MB! MB)"
    echo       Location: %BINARY_PATH%
    echo.
    set /p "REPLY=       Backup and replace? [Y/n]: "
    echo.

    if /i "!REPLY!"=="n" (
        call :print_info "Keeping existing binary"
        echo.
        goto :eof
    )

    REM Backup existing binary
    for /f "tokens=2 delims==" %%a in ('wmic os get localdatetime /value 2^>nul') do set "dt=%%a"
    set "BACKUP_NAME=%BINARY_PATH%.backup.!dt:~0,8!_!dt:~8,6!"
    move "%BINARY_PATH%" "!BACKUP_NAME!" >nul 2>&1
    if !errorlevel! equ 0 (
        call :print_ok "Backup created"
    ) else (
        call :print_warn "Could not backup - will overwrite"
    )
) else (
    call :print_info "No existing binary found"
)
echo.

REM ============================================================================
REM Step 3: Download Binary
REM ============================================================================
echo %CYAN%[3/4]%NC% Downloading Binary
echo.

call :print_info "Version: %MAVLINK2REST_VERSION%"
call :print_info "Size: ~37 MB"
echo       URL: %BINARY_URL%
echo.

set /p "REPLY=       Proceed with download? [Y/n]: "
echo.

if /i "!REPLY!"=="n" (
    call :print_info "Download cancelled"
    goto :show_manual
)

REM Check for download tool
set "DOWNLOAD_TOOL="

where curl.exe >nul 2>&1
if %errorlevel% equ 0 (
    set "DOWNLOAD_TOOL=curl"
    call :print_info "Using curl"
)

if "%DOWNLOAD_TOOL%"=="" (
    where powershell >nul 2>&1
    if %errorlevel% equ 0 (
        set "DOWNLOAD_TOOL=powershell"
        call :print_info "Using PowerShell"
    )
)

if "%DOWNLOAD_TOOL%"=="" (
    call :print_error "No download tool available"
    goto :show_manual
)

REM Download to temporary file
set "TEMP_FILE=%BINARY_PATH%.tmp"

call :print_info "Downloading..."
echo.

if "%DOWNLOAD_TOOL%"=="curl" (
    curl.exe -L --progress-bar -o "%TEMP_FILE%" "%BINARY_URL%"
    set "DL_RESULT=!errorlevel!"
) else (
    powershell -NoProfile -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'Continue'; try { Invoke-WebRequest -Uri '%BINARY_URL%' -OutFile '%TEMP_FILE%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }}"
    set "DL_RESULT=!errorlevel!"
)

if !DL_RESULT! neq 0 (
    call :print_error "Download failed"
    if exist "%TEMP_FILE%" del "%TEMP_FILE%"
    goto :show_manual
)

call :print_ok "Download completed"
echo.

REM Move temp file to final location
move "%TEMP_FILE%" "%BINARY_PATH%" >nul 2>&1
if !errorlevel! neq 0 (
    call :print_error "Failed to save binary"
    if exist "%TEMP_FILE%" del "%TEMP_FILE%"
    goto :show_manual
)

REM ============================================================================
REM Step 4: Validate Binary
REM ============================================================================
echo %CYAN%[4/4]%NC% Validating Binary
echo.

if not exist "%BINARY_PATH%" (
    call :print_error "Binary not found after download"
    goto :show_manual
)
call :print_ok "Binary exists"

REM Check file size (should be > 1MB)
for %%A in ("%BINARY_PATH%") do set "FILE_SIZE=%%~zA"

if %FILE_SIZE% lss 1000000 (
    call :print_error "Binary too small (%FILE_SIZE% bytes)"
    echo       Expected ^> 1MB - download may have failed
    del "%BINARY_PATH%" 2>nul
    goto :show_manual
)

set /a "FILE_SIZE_MB=%FILE_SIZE% / 1024 / 1024"
call :print_ok "File size: %FILE_SIZE_MB% MB"

REM Skip execution test - MAVLink2REST is a daemon that doesn't exit on --version
call :print_ok "Binary ready (daemon - skipping execution test)"

echo.

REM Success
echo ============================================================
echo   %GREEN%Download Complete!%NC%
echo ============================================================
echo.
echo   %CHECK% MAVLink2REST %MAVLINK2REST_VERSION%
echo   %CHECK% Platform: Windows x86_64
echo   %CHECK% Location: %BINARY_PATH%
echo.
echo   Next: Run %BOLD%run_pixeagle.bat%NC%
echo.
echo ============================================================
echo.
goto :eof

REM ============================================================================
REM Functions
REM ============================================================================

:print_ok
echo   %GREEN%%CHECK%%NC% %~1
goto :eof

:print_error
echo   %RED%%CROSS%%NC% %~1
goto :eof

:print_warn
echo   %YELLOW%%WARN%%NC% %~1
goto :eof

:print_info
echo   %BLUE%%INFO%%NC% %~1
goto :eof

:show_manual
echo.
echo ============================================================
echo   %YELLOW%Manual Download Instructions%NC%
echo ============================================================
echo.
echo   1. Visit MAVLink2REST Releases:
echo      %CYAN%https://github.com/%GITHUB_REPO%/releases/tag/%MAVLINK2REST_VERSION%%NC%
echo.
echo   2. Download Windows binary:
echo      %CYAN%%BINARY_NAME%%NC%
echo.
echo   3. Save to:
echo      %CYAN%%BINARY_PATH%%NC%
echo.
echo ============================================================
echo.
pause
goto :eof
