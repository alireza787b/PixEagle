@echo off
REM ============================================================================
REM scripts\setup\download-binaries.bat - Download MAVSDK & MAVLink2REST (Windows)
REM ============================================================================
REM Downloads pre-built binaries for MAVSDK Server and MAVLink2REST.
REM
REM Usage:
REM   scripts\setup\download-binaries.bat --all         (download both)
REM   scripts\setup\download-binaries.bat --mavsdk      (MAVSDK only)
REM   scripts\setup\download-binaries.bat --mavlink2rest (MAVLink2REST only)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

REM Configuration
set "BIN_DIR=%PIXEAGLE_DIR%\bin"
set "MAVSDK_VERSION=v2.3.1"
set "MAVLINK2REST_VERSION=0.11.20"

REM Parse arguments
set "DOWNLOAD_MAVSDK=0"
set "DOWNLOAD_MAVLINK2REST=0"

if "%~1"=="" (
    echo Usage: download-binaries.bat [--all ^| --mavsdk ^| --mavlink2rest]
    exit /b 1
)

:parse_args
if "%~1"=="" goto :done_args
if "%~1"=="--all" (
    set "DOWNLOAD_MAVSDK=1"
    set "DOWNLOAD_MAVLINK2REST=1"
)
if "%~1"=="--mavsdk" set "DOWNLOAD_MAVSDK=1"
if "%~1"=="--mavlink2rest" set "DOWNLOAD_MAVLINK2REST=1"
shift
goto :parse_args
:done_args

echo.
echo [36m========================================================================[0m
echo                   PixEagle Binary Downloader (Windows)
echo [36m========================================================================[0m
echo.

REM Create bin directory if needed
if not exist "%BIN_DIR%" (
    echo    [*] Creating bin directory...
    mkdir "%BIN_DIR%"
)

REM ============================================================================
REM Download MAVSDK Server
REM ============================================================================
if "%DOWNLOAD_MAVSDK%"=="1" (
    echo    [1] Downloading MAVSDK Server %MAVSDK_VERSION%...

    set "MAVSDK_URL=https://github.com/mavlink/MAVSDK/releases/download/%MAVSDK_VERSION%/mavsdk_server_win32.exe"
    set "MAVSDK_BIN=%BIN_DIR%\mavsdk_server_bin.exe"

    REM Check if already exists
    if exist "!MAVSDK_BIN!" (
        echo        [!] MAVSDK Server already exists, skipping...
        echo            Delete %BIN_DIR%\mavsdk_server_bin.exe to re-download
    ) else (
        echo        URL: !MAVSDK_URL!
        echo        Destination: !MAVSDK_BIN!
        echo.

        REM Download using PowerShell
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!MAVSDK_URL!' -OutFile '!MAVSDK_BIN!' -UseBasicParsing}"

        if exist "!MAVSDK_BIN!" (
            echo [32m       [OK] MAVSDK Server downloaded successfully[0m
        ) else (
            echo [31m       [ERROR] Failed to download MAVSDK Server[0m
        )
    )
    echo.
)

REM ============================================================================
REM Download MAVLink2REST
REM ============================================================================
if "%DOWNLOAD_MAVLINK2REST%"=="1" (
    echo    [2] Downloading MAVLink2REST %MAVLINK2REST_VERSION%...

    set "MAVLINK2REST_URL=https://github.com/mavlink/mavlink2rest/releases/download/%MAVLINK2REST_VERSION%/mavlink2rest-x86_64-pc-windows-msvc.exe"
    set "MAVLINK2REST_BIN=%BIN_DIR%\mavlink2rest.exe"

    REM Check if already exists
    if exist "!MAVLINK2REST_BIN!" (
        echo        [!] MAVLink2REST already exists, skipping...
        echo            Delete %BIN_DIR%\mavlink2rest.exe to re-download
    ) else (
        echo        URL: !MAVLINK2REST_URL!
        echo        Destination: !MAVLINK2REST_BIN!
        echo.

        REM Download using PowerShell
        powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!MAVLINK2REST_URL!' -OutFile '!MAVLINK2REST_BIN!' -UseBasicParsing}"

        if exist "!MAVLINK2REST_BIN!" (
            echo [32m       [OK] MAVLink2REST downloaded successfully[0m
        ) else (
            echo [31m       [ERROR] Failed to download MAVLink2REST[0m
        )
    )
    echo.
)

REM ============================================================================
REM Summary
REM ============================================================================
echo [36m========================================================================[0m
echo                         Download Complete
echo [36m========================================================================[0m
echo.
echo    Binaries located in: %BIN_DIR%
echo.

REM List downloaded files
echo    Downloaded files:
dir /b "%BIN_DIR%\*.exe" 2>nul | findstr . >nul
if %errorlevel% equ 0 (
    for %%f in ("%BIN_DIR%\*.exe") do (
        echo      - %%~nxf
    )
) else (
    echo      (none)
)
echo.

endlocal
exit /b 0
