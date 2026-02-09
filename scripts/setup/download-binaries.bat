@echo off
REM ============================================================================
REM scripts\setup\download-binaries.bat - Download MAVSDK & MAVLink2REST (Windows)
REM ============================================================================
REM Downloads pre-built binaries for MAVSDK Server and MAVLink2REST.
REM
REM Usage:
REM   scripts\setup\download-binaries.bat --all          (download both)
REM   scripts\setup\download-binaries.bat --mavsdk       (MAVSDK only)
REM   scripts\setup\download-binaries.bat --mavlink2rest (MAVLink2REST only)
REM
REM Notes:
REM   - Uses multiple release tags as fallback to handle upstream tag changes.
REM   - Validates downloaded files to avoid accepting HTML error pages as binaries.
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
set "MAVSDK_TAG_CANDIDATES=v3.15.0 v3.12.0 v3.11.0 v2.3.1"
set "MAVSDK_ASSET_CANDIDATES=mavsdk_server_win32.exe mavsdk_server_windows_x64.exe mavsdk_server_windows-x64.exe mavsdk_server_win64.exe"
set "MAVLINK2REST_TAG_CANDIDATES=1.0.0 t0.11.25 t0.11.24 t0.11.21 t0.11.20 0.11.20"
set "MAVLINK2REST_ASSET_CANDIDATE=mavlink2rest-x86_64-pc-windows-msvc.exe"

REM Parse arguments
set "DOWNLOAD_MAVSDK=0"
set "DOWNLOAD_MAVLINK2REST=0"
set "FAILURES=0"

if "%~1"=="" (
    echo Usage: download-binaries.bat [--all ^| --mavsdk ^| --mavlink2rest]
    exit /b 1
)

:parse_args
if "%~1"=="" goto :done_args
if /I "%~1"=="--all" (
    set "DOWNLOAD_MAVSDK=1"
    set "DOWNLOAD_MAVLINK2REST=1"
)
if /I "%~1"=="--mavsdk" set "DOWNLOAD_MAVSDK=1"
if /I "%~1"=="--mavlink2rest" set "DOWNLOAD_MAVLINK2REST=1"
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
    call :download_mavsdk
    if !errorlevel! neq 0 set /a "FAILURES+=1"
    echo.
)

REM ============================================================================
REM Download MAVLink2REST
REM ============================================================================
if "%DOWNLOAD_MAVLINK2REST%"=="1" (
    call :download_mavlink2rest
    if !errorlevel! neq 0 set /a "FAILURES+=1"
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

if !FAILURES! gtr 0 (
    echo [31m[ERROR] One or more requested downloads failed.[0m
    endlocal
    exit /b 1
)

endlocal
exit /b 0

REM ============================================================================
REM Subroutines
REM ============================================================================

:download_mavsdk
set "MAVSDK_BIN=%BIN_DIR%\mavsdk_server_bin.exe"

echo    [1] Downloading MAVSDK Server...

if exist "!MAVSDK_BIN!" (
    echo        [!] MAVSDK Server already exists, skipping...
    echo            Delete %BIN_DIR%\mavsdk_server_bin.exe to re-download
    exit /b 0
)

set "MAVSDK_OK=0"
for %%T in (%MAVSDK_TAG_CANDIDATES%) do (
    if "!MAVSDK_OK!"=="0" (
        for %%A in (%MAVSDK_ASSET_CANDIDATES%) do (
            if "!MAVSDK_OK!"=="0" (
                set "MAVSDK_URL=https://github.com/mavlink/MAVSDK/releases/download/%%T/%%A"
                call :try_download "!MAVSDK_URL!" "!MAVSDK_BIN!" "MAVSDK Server"
                if !errorlevel! equ 0 (
                    set "MAVSDK_OK=1"
                    set "MAVSDK_SELECTED_TAG=%%T"
                    set "MAVSDK_SELECTED_ASSET=%%A"
                )
            )
        )
    )
)

if "!MAVSDK_OK!"=="1" (
    echo [32m       [OK] MAVSDK Server downloaded successfully[0m
    echo           Tag: !MAVSDK_SELECTED_TAG!
    echo           Asset: !MAVSDK_SELECTED_ASSET!
    exit /b 0
)

echo [31m       [ERROR] Failed to download MAVSDK Server[0m
echo           Tried tags: %MAVSDK_TAG_CANDIDATES%
if exist "!MAVSDK_BIN!" del /q "!MAVSDK_BIN!" >nul 2>&1
exit /b 1

:download_mavlink2rest
set "MAVLINK2REST_BIN=%BIN_DIR%\mavlink2rest.exe"

echo    [2] Downloading MAVLink2REST...

if exist "!MAVLINK2REST_BIN!" (
    echo        [!] MAVLink2REST already exists, skipping...
    echo            Delete %BIN_DIR%\mavlink2rest.exe to re-download
    exit /b 0
)

set "M2R_OK=0"
for %%T in (%MAVLINK2REST_TAG_CANDIDATES%) do (
    if "!M2R_OK!"=="0" (
        set "M2R_URL=https://github.com/mavlink/mavlink2rest/releases/download/%%T/%MAVLINK2REST_ASSET_CANDIDATE%"
        call :try_download "!M2R_URL!" "!MAVLINK2REST_BIN!" "MAVLink2REST"
        if !errorlevel! equ 0 (
            set "M2R_OK=1"
            set "M2R_SELECTED_TAG=%%T"
        )
    )
)

if "!M2R_OK!"=="1" (
    echo [32m       [OK] MAVLink2REST downloaded successfully[0m
    echo           Tag: !M2R_SELECTED_TAG!
    echo           Asset: %MAVLINK2REST_ASSET_CANDIDATE%
    exit /b 0
)

echo [31m       [ERROR] Failed to download MAVLink2REST[0m
echo           Tried tags: %MAVLINK2REST_TAG_CANDIDATES%
if exist "!MAVLINK2REST_BIN!" del /q "!MAVLINK2REST_BIN!" >nul 2>&1
exit /b 1

:try_download
set "TRY_URL=%~1"
set "TRY_DEST=%~2"
set "TRY_NAME=%~3"

echo        Trying: !TRY_URL!
powershell -NoProfile -Command "& {$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '!TRY_URL!' -OutFile '!TRY_DEST!' -UseBasicParsing}" >nul 2>&1
if !errorlevel! neq 0 (
    if exist "!TRY_DEST!" del /q "!TRY_DEST!" >nul 2>&1
    exit /b 1
)

call :validate_binary "!TRY_DEST!" "!TRY_NAME!"
if !errorlevel! neq 0 (
    if exist "!TRY_DEST!" del /q "!TRY_DEST!" >nul 2>&1
    exit /b 1
)

exit /b 0

:validate_binary
set "BIN_FILE=%~1"
set "BIN_NAME=%~2"

powershell -NoProfile -Command "& { $p='!BIN_FILE!'; if (-not (Test-Path -LiteralPath $p)) { exit 1 }; $item=Get-Item -LiteralPath $p; if ($item.Length -lt 1000000) { exit 2 }; $fs=[System.IO.File]::OpenRead($p); try { $b1=$fs.ReadByte(); $b2=$fs.ReadByte() } finally { $fs.Dispose() }; if ($b1 -ne 77 -or $b2 -ne 90) { exit 3 }; exit 0 }" >nul 2>&1
set "VALIDATION_CODE=!errorlevel!"

if "!VALIDATION_CODE!"=="0" exit /b 0
if "!VALIDATION_CODE!"=="2" echo        [!] Rejected !BIN_NAME!: file too small
if "!VALIDATION_CODE!"=="3" echo        [!] Rejected !BIN_NAME!: invalid executable header
exit /b 1
