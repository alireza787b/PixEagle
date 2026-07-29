@echo off
setlocal

REM Thin compatibility wrapper for the canonical PowerShell downloader.
REM Native Windows support remains behind PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1.

set "DOWNLOADER=%~dp0download-binaries.ps1"
set "SELECT_ALL="
set "SELECT_MAVSDK="
set "SELECT_MAVLINK2REST="
set "DRY_RUN="

if not exist "%DOWNLOADER%" (
    echo [ERROR] PowerShell downloader not found: %DOWNLOADER%
    exit /b 1
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Windows PowerShell 5.1 or newer is required.
    exit /b 1
)

if "%~1"=="" set "SELECT_ALL=-All"

:parse_args
if "%~1"=="" goto :run
if /I "%~1"=="--all" (
    set "SELECT_ALL=-All"
) else if /I "%~1"=="--mavsdk" (
    set "SELECT_MAVSDK=-Mavsdk"
) else if /I "%~1"=="--mavlink2rest" (
    set "SELECT_MAVLINK2REST=-Mavlink2rest"
) else if /I "%~1"=="--m2r" (
    set "SELECT_MAVLINK2REST=-Mavlink2rest"
) else if /I "%~1"=="--dry-run" (
    set "DRY_RUN=-DryRun"
) else if /I "%~1"=="--print-plan" (
    set "DRY_RUN=-DryRun"
) else if /I "%~1"=="--help" (
    goto :show_help
) else if /I "%~1"=="-h" (
    goto :show_help
) else (
    echo [ERROR] Unknown option. Run with --help to list supported options.
    exit /b 1
)
shift
goto :parse_args

:show_help
powershell.exe -NoLogo -NoProfile -File "%DOWNLOADER%" -Help
set "RESULT=%ERRORLEVEL%"
endlocal & exit /b %RESULT%

:run
if not defined SELECT_ALL if not defined SELECT_MAVSDK if not defined SELECT_MAVLINK2REST (
    set "SELECT_ALL=-All"
)

powershell.exe -NoLogo -NoProfile -File "%DOWNLOADER%" %SELECT_ALL% %SELECT_MAVSDK% %SELECT_MAVLINK2REST% %DRY_RUN%
set "RESULT=%ERRORLEVEL%"
endlocal & exit /b %RESULT%
