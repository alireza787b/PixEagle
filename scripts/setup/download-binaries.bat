@echo off
REM ============================================================================
REM scripts\setup\download-binaries.bat - Download MAVSDK & MAVLink2REST (Windows)
REM ============================================================================
REM Downloads manifest-pinned MAVSDK Server and MAVLink2REST binaries.
REM
REM Usage:
REM   scripts\setup\download-binaries.bat --all
REM   scripts\setup\download-binaries.bat --mavsdk
REM   scripts\setup\download-binaries.bat --mavlink2rest
REM   scripts\setup\download-binaries.bat --all --dry-run
REM
REM Policy:
REM   - Uses scripts\setup\binary-manifest.env as the default source of truth.
REM   - Verifies SHA-256 before installing a binary into bin\.
REM   - Writes bin\binary-provenance.jsonl after verified install/acceptance.
REM   - Does not probe fallback release tags in default setup.
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

set "BIN_DIR=%PIXEAGLE_DIR%\bin"
set "MANIFEST=%PIXEAGLE_BINARY_MANIFEST%"
if not defined MANIFEST set "MANIFEST=%SCRIPTS_DIR%\binary-manifest.env"
set "PROVENANCE_LOG=%BIN_DIR%\binary-provenance.jsonl"

set "DOWNLOAD_MAVSDK=0"
set "DOWNLOAD_MAVLINK2REST=0"
set "DRY_RUN=0"
set "FAILURES=0"

if "%~1"=="" (
    set "DOWNLOAD_MAVSDK=1"
    set "DOWNLOAD_MAVLINK2REST=1"
    goto :done_args
)

:parse_args
if "%~1"=="" goto :done_args
if /I "%~1"=="--all" (
    set "DOWNLOAD_MAVSDK=1"
    set "DOWNLOAD_MAVLINK2REST=1"
) else if /I "%~1"=="--mavsdk" (
    set "DOWNLOAD_MAVSDK=1"
) else if /I "%~1"=="--mavlink2rest" (
    set "DOWNLOAD_MAVLINK2REST=1"
) else if /I "%~1"=="--m2r" (
    set "DOWNLOAD_MAVLINK2REST=1"
) else if /I "%~1"=="--dry-run" (
    set "DRY_RUN=1"
) else if /I "%~1"=="--print-plan" (
    set "DRY_RUN=1"
) else if /I "%~1"=="--help" (
    call :show_help
    exit /b 0
) else if /I "%~1"=="-h" (
    call :show_help
    exit /b 0
) else (
    echo Unknown option: %~1
    exit /b 1
)
shift
goto :parse_args

:done_args
if "%DOWNLOAD_MAVSDK%"=="0" if "%DOWNLOAD_MAVLINK2REST%"=="0" (
    set "DOWNLOAD_MAVSDK=1"
    set "DOWNLOAD_MAVLINK2REST=1"
)

echo.
echo [36m========================================================================[0m
echo                   PixEagle Binary Downloader (Windows)
echo [36m========================================================================[0m
echo.
echo    Manifest: %MANIFEST%

call :load_manifest || exit /b 1
call :detect_platform || exit /b 1

if "%DRY_RUN%"=="0" if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

if "%DOWNLOAD_MAVSDK%"=="1" (
    call :download_mavsdk
    if !errorlevel! neq 0 set /a "FAILURES+=1"
    echo.
)

if "%DOWNLOAD_MAVLINK2REST%"=="1" (
    call :download_mavlink2rest
    if !errorlevel! neq 0 set /a "FAILURES+=1"
    echo.
)

call :show_summary

if !FAILURES! gtr 0 (
    endlocal
    exit /b 1
)

endlocal
exit /b 0

REM ============================================================================
REM Subroutines
REM ============================================================================

:show_help
echo Usage: scripts\setup\download-binaries.bat [--all ^| --mavsdk ^| --mavlink2rest] [--dry-run]
echo.
echo Environment overrides:
echo   PIXEAGLE_BINARY_MANIFEST
echo   PIXEAGLE_MAVSDK_VERSION / PIXEAGLE_MAVSDK_ASSET / PIXEAGLE_MAVSDK_SHA256
echo   PIXEAGLE_MAVSDK_URL / PIXEAGLE_MAVSDK_BASE_URL
echo   PIXEAGLE_MAVLINK2REST_VERSION / PIXEAGLE_MAVLINK2REST_ASSET / PIXEAGLE_MAVLINK2REST_SHA256
echo   PIXEAGLE_MAVLINK2REST_URL / PIXEAGLE_MAVLINK2REST_BASE_URL
echo   PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1 for explicit lab-only unverified overrides
exit /b 0

:load_manifest
if not exist "%MANIFEST%" (
    echo [31m[ERROR] Binary manifest not found: %MANIFEST%[0m
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%MANIFEST%") do (
    if not "%%A"=="" set "%%A=%%B"
)

if defined PIXEAGLE_MAVSDK_VERSION (
    set "MAVSDK_VERSION=%PIXEAGLE_MAVSDK_VERSION%"
) else (
    set "MAVSDK_VERSION=%PIXEAGLE_BINARY_MAVSDK_VERSION%"
)
if defined PIXEAGLE_MAVLINK2REST_VERSION (
    set "MAVLINK2REST_VERSION=%PIXEAGLE_MAVLINK2REST_VERSION%"
) else (
    set "MAVLINK2REST_VERSION=%PIXEAGLE_BINARY_MAVLINK2REST_VERSION%"
)
if defined PIXEAGLE_MAVSDK_BASE_URL (
    set "MAVSDK_BASE_URL=%PIXEAGLE_MAVSDK_BASE_URL%"
) else (
    set "MAVSDK_BASE_URL=%PIXEAGLE_BINARY_MAVSDK_BASE_URL%"
)
if defined PIXEAGLE_MAVLINK2REST_BASE_URL (
    set "MAVLINK2REST_BASE_URL=%PIXEAGLE_MAVLINK2REST_BASE_URL%"
) else (
    set "MAVLINK2REST_BASE_URL=%PIXEAGLE_BINARY_MAVLINK2REST_BASE_URL%"
)
set "MAVSDK_RELEASE_URL=%PIXEAGLE_BINARY_MAVSDK_RELEASE_URL%"
set "MAVLINK2REST_RELEASE_URL=%PIXEAGLE_BINARY_MAVLINK2REST_RELEASE_URL%"

if not defined MAVSDK_VERSION exit /b 1
if not defined MAVLINK2REST_VERSION exit /b 1
if not defined MAVSDK_BASE_URL exit /b 1
if not defined MAVLINK2REST_BASE_URL exit /b 1
exit /b 0

:detect_platform
set "ARCH=%PROCESSOR_ARCHITECTURE%"
if /I "%ARCH%"=="AMD64" (
    set "PLATFORM_KEY=WINDOWS_X86_64"
) else if /I "%ARCH%"=="ARM64" (
    set "PLATFORM_KEY=WINDOWS_ARM64"
) else (
    echo [31m[ERROR] Unsupported Windows architecture: %ARCH%[0m
    exit /b 1
)
echo    [OK] OS: Windows
echo    [OK] Architecture: %ARCH%
echo    [OK] Manifest platform: %PLATFORM_KEY%
exit /b 0

:resolve_mavsdk
if defined PIXEAGLE_MAVSDK_ASSET (
    set "MAVSDK_ASSET=%PIXEAGLE_MAVSDK_ASSET%"
) else (
    call set "MAVSDK_ASSET=%%PIXEAGLE_BINARY_MAVSDK_ASSET_%PLATFORM_KEY%%%"
)
if defined PIXEAGLE_MAVSDK_SHA256 (
    set "MAVSDK_SHA256=%PIXEAGLE_MAVSDK_SHA256%"
) else (
    call set "MAVSDK_SHA256=%%PIXEAGLE_BINARY_MAVSDK_SHA256_%PLATFORM_KEY%%%"
)
if defined PIXEAGLE_MAVSDK_URL (
    set "MAVSDK_URL=%PIXEAGLE_MAVSDK_URL%"
) else (
    set "MAVSDK_URL=%MAVSDK_BASE_URL%/%MAVSDK_VERSION%/%MAVSDK_ASSET%"
)
if not defined MAVSDK_ASSET exit /b 1
if not defined MAVSDK_URL exit /b 1
exit /b 0

:resolve_mavlink2rest
if defined PIXEAGLE_MAVLINK2REST_ASSET (
    set "M2R_ASSET=%PIXEAGLE_MAVLINK2REST_ASSET%"
) else (
    call set "M2R_ASSET=%%PIXEAGLE_BINARY_MAVLINK2REST_ASSET_%PLATFORM_KEY%%%"
)
if defined PIXEAGLE_MAVLINK2REST_SHA256 (
    set "M2R_SHA256=%PIXEAGLE_MAVLINK2REST_SHA256%"
) else (
    call set "M2R_SHA256=%%PIXEAGLE_BINARY_MAVLINK2REST_SHA256_%PLATFORM_KEY%%%"
)
if defined PIXEAGLE_MAVLINK2REST_URL (
    set "M2R_URL=%PIXEAGLE_MAVLINK2REST_URL%"
) else (
    set "M2R_URL=%MAVLINK2REST_BASE_URL%/%MAVLINK2REST_VERSION%/%M2R_ASSET%"
)
if not defined M2R_ASSET exit /b 1
if not defined M2R_URL exit /b 1
exit /b 0

:print_plan
set "PLAN_NAME=%~1"
set "PLAN_VERSION=%~2"
set "PLAN_RELEASE=%~3"
set "PLAN_ASSET=%~4"
set "PLAN_URL=%~5"
set "PLAN_SHA=%~6"
set "PLAN_OUTPUT=%~7"
echo    [*] %PLAN_NAME%
echo        Version: %PLAN_VERSION%
if defined PLAN_RELEASE echo        Release: %PLAN_RELEASE%
echo        Asset: %PLAN_ASSET%
echo        URL: %PLAN_URL%
if defined PLAN_SHA (
    echo        Expected SHA256: %PLAN_SHA%
) else (
    echo        [WARNING] No expected SHA256 configured
)
echo        Output: %PLAN_OUTPUT%
echo        Provenance log: %PROVENANCE_LOG%
exit /b 0

:download_mavsdk
set "MAVSDK_BIN=%BIN_DIR%\mavsdk_server_bin.exe"
call :resolve_mavsdk || exit /b 1
call :print_plan "MAVSDK Server" "%MAVSDK_VERSION%" "%MAVSDK_RELEASE_URL%" "%MAVSDK_ASSET%" "%MAVSDK_URL%" "%MAVSDK_SHA256%" "%MAVSDK_BIN%"
if "%DRY_RUN%"=="1" exit /b 0

if exist "%MAVSDK_BIN%" (
    call :verify_existing "%MAVSDK_BIN%" "MAVSDK Server" "%MAVSDK_VERSION%" "%MAVSDK_ASSET%" "%MAVSDK_URL%" "%MAVSDK_SHA256%" "existing"
    if !errorlevel! equ 0 exit /b 0
    echo        Replace with pinned manifest binary? [y/N]:
    set /p REPLY=
    if /I not "!REPLY!"=="y" exit /b 1
)

call :download_and_verify "%MAVSDK_URL%" "%MAVSDK_BIN%" "MAVSDK Server" "%MAVSDK_VERSION%" "%MAVSDK_ASSET%" "%MAVSDK_SHA256%"
exit /b !errorlevel!

:download_mavlink2rest
set "M2R_BIN=%BIN_DIR%\mavlink2rest.exe"
call :resolve_mavlink2rest || exit /b 1
call :print_plan "MAVLink2REST" "%MAVLINK2REST_VERSION%" "%MAVLINK2REST_RELEASE_URL%" "%M2R_ASSET%" "%M2R_URL%" "%M2R_SHA256%" "%M2R_BIN%"
if "%DRY_RUN%"=="1" exit /b 0

if exist "%M2R_BIN%" (
    call :verify_existing "%M2R_BIN%" "MAVLink2REST" "%MAVLINK2REST_VERSION%" "%M2R_ASSET%" "%M2R_URL%" "%M2R_SHA256%" "existing"
    if !errorlevel! equ 0 exit /b 0
    echo        Replace with pinned manifest binary? [y/N]:
    set /p REPLY=
    if /I not "!REPLY!"=="y" exit /b 1
)

call :download_and_verify "%M2R_URL%" "%M2R_BIN%" "MAVLink2REST" "%MAVLINK2REST_VERSION%" "%M2R_ASSET%" "%M2R_SHA256%"
exit /b !errorlevel!

:download_and_verify
set "TRY_URL=%~1"
set "TRY_DEST=%~2"
set "TRY_NAME=%~3"
set "TRY_VERSION=%~4"
set "TRY_ASSET=%~5"
set "TRY_SHA=%~6"
set "TRY_TEMP=%TRY_DEST%.tmp"

if not defined TRY_SHA if not "%PIXEAGLE_ALLOW_UNVERIFIED_BINARY%"=="1" (
    echo        [ERROR] %TRY_NAME% has no SHA256. Provide an override SHA256 or set PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1 for lab-only use.
    exit /b 1
)

echo        Downloading: %TRY_URL%
powershell -NoProfile -Command "& {$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%TRY_URL%' -OutFile '%TRY_TEMP%' -UseBasicParsing}" >nul 2>&1
if !errorlevel! neq 0 (
    if exist "%TRY_TEMP%" del /q "%TRY_TEMP%" >nul 2>&1
    echo        [ERROR] Download failed
    exit /b 1
)

call :validate_binary "%TRY_TEMP%" "%TRY_NAME%" || (
    if exist "%TRY_TEMP%" del /q "%TRY_TEMP%" >nul 2>&1
    exit /b 1
)
call :sha256 "%TRY_TEMP%" ACTUAL_SHA || (
    if exist "%TRY_TEMP%" del /q "%TRY_TEMP%" >nul 2>&1
    exit /b 1
)

set "VERIFY_MODE=sha256"
if defined TRY_SHA (
    if /I not "!ACTUAL_SHA!"=="%TRY_SHA%" (
        echo        [ERROR] SHA256 mismatch for %TRY_NAME%
        echo        Expected: %TRY_SHA%
        echo        Actual:   !ACTUAL_SHA!
        del /q "%TRY_TEMP%" >nul 2>&1
        exit /b 1
    )
    echo        [OK] SHA256 verified
) else (
    set "VERIFY_MODE=unverified_override"
    echo        [WARNING] Accepted without checksum because PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1
)

move /y "%TRY_TEMP%" "%TRY_DEST%" >nul
call :record_provenance "%TRY_NAME%" "%TRY_VERSION%" "%TRY_ASSET%" "%TRY_URL%" "%TRY_SHA%" "!ACTUAL_SHA!" "%TRY_DEST%" "!VERIFY_MODE!"
echo        [OK] %TRY_NAME% installed
exit /b 0

:verify_existing
set "EXISTING_PATH=%~1"
set "EXISTING_NAME=%~2"
set "EXISTING_VERSION=%~3"
set "EXISTING_ASSET=%~4"
set "EXISTING_URL=%~5"
set "EXISTING_SHA=%~6"
set "EXISTING_MODE=%~7"
call :validate_binary "%EXISTING_PATH%" "%EXISTING_NAME%" || exit /b 1
call :sha256 "%EXISTING_PATH%" ACTUAL_SHA || exit /b 1
if defined EXISTING_SHA (
    if /I not "!ACTUAL_SHA!"=="%EXISTING_SHA%" (
        echo        [WARNING] %EXISTING_NAME% exists but SHA256 does not match manifest
        echo        Expected: %EXISTING_SHA%
        echo        Actual:   !ACTUAL_SHA!
        exit /b 1
    )
    call :record_provenance "%EXISTING_NAME%" "%EXISTING_VERSION%" "%EXISTING_ASSET%" "%EXISTING_URL%" "%EXISTING_SHA%" "!ACTUAL_SHA!" "%EXISTING_PATH%" "%EXISTING_MODE%_sha256"
    echo        [OK] Existing %EXISTING_NAME% SHA256 verified
    exit /b 0
)
if "%PIXEAGLE_ALLOW_UNVERIFIED_BINARY%"=="1" (
    call :record_provenance "%EXISTING_NAME%" "%EXISTING_VERSION%" "%EXISTING_ASSET%" "%EXISTING_URL%" "" "!ACTUAL_SHA!" "%EXISTING_PATH%" "%EXISTING_MODE%_unverified_override"
    echo        [WARNING] Existing %EXISTING_NAME% accepted without checksum
    exit /b 0
)
echo        [ERROR] Existing %EXISTING_NAME% cannot be verified without a SHA256
exit /b 1

:sha256
set "HASH_FILE=%~1"
set "HASH_OUT_VAR=%~2"
set "HASH_VALUE="
for /f "tokens=1" %%H in ('certutil -hashfile "%HASH_FILE%" SHA256 ^| findstr /R /C:"^[0-9A-Fa-f][0-9A-Fa-f]"') do (
    set "HASH_VALUE=%%H"
)
if not defined HASH_VALUE (
    echo        [ERROR] Could not compute SHA256 for %HASH_FILE%
    exit /b 1
)
set "%HASH_OUT_VAR%=%HASH_VALUE%"
exit /b 0

:validate_binary
set "BIN_FILE=%~1"
set "BIN_NAME=%~2"
powershell -NoProfile -Command "& { $p='%BIN_FILE%'; if (-not (Test-Path -LiteralPath $p)) { exit 1 }; $item=Get-Item -LiteralPath $p; if ($item.Length -lt 1000000) { exit 2 }; $fs=[System.IO.File]::OpenRead($p); try { $b1=$fs.ReadByte(); $b2=$fs.ReadByte() } finally { $fs.Dispose() }; if ($b1 -ne 77 -or $b2 -ne 90) { exit 3 }; exit 0 }" >nul 2>&1
set "VALIDATION_CODE=!errorlevel!"
if "!VALIDATION_CODE!"=="0" exit /b 0
if "!VALIDATION_CODE!"=="2" echo        [WARNING] Rejected %BIN_NAME%: file too small
if "!VALIDATION_CODE!"=="3" echo        [WARNING] Rejected %BIN_NAME%: invalid executable header
exit /b 1

:record_provenance
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
set "PV_NAME=%~1"
set "PV_VERSION=%~2"
set "PV_ASSET=%~3"
set "PV_URL=%~4"
set "PV_EXPECTED_SHA=%~5"
set "PV_ACTUAL_SHA=%~6"
set "PV_DEST=%~7"
set "PV_MODE=%~8"
for /f %%T in ('powershell -NoProfile -Command "(Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')"') do set "PV_TIME=%%T"
>> "%PROVENANCE_LOG%" echo {"timestamp_utc":"%PV_TIME%","component":"%PV_NAME%","version":"%PV_VERSION%","platform_key":"%PLATFORM_KEY%","asset":"%PV_ASSET%","url":"%PV_URL%","expected_sha256":"%PV_EXPECTED_SHA%","actual_sha256":"%PV_ACTUAL_SHA%","verification_mode":"%PV_MODE%","output_path":"%PV_DEST%"}
exit /b 0

:show_summary
echo [36m========================================================================[0m
if "%DRY_RUN%"=="1" (
    echo                         Dry-Run Download Plan
) else if !FAILURES! equ 0 (
    echo                         Download Complete
) else (
    echo                         Download Failed
)
echo [36m========================================================================[0m
echo.
if "%DRY_RUN%"=="1" (
    echo    Dry run: no files were downloaded or modified.
) else if !FAILURES! equ 0 (
    echo    Provenance: %PROVENANCE_LOG%
    echo    The log records downloaded binary version, URL, asset, and SHA-256.
    echo    It does not claim MAVSDK, MAVLink2REST, PX4, SITL, or field runtime success.
) else (
    echo    [ERROR] One or more requested downloads failed.
)
exit /b 0
