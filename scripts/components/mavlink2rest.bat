@echo off
REM ============================================================================
REM scripts\components\mavlink2rest.bat - Run MAVLink2REST (Windows)
REM ============================================================================
REM Starts the MAVLink2REST bridge for MAVLink communication.
REM
REM Usage:
REM   scripts\components\mavlink2rest.bat      (from project root)
REM
REM The binary is expected at:
REM   - bin\mavlink2rest.exe (preferred)
REM   - mavlink2rest.exe (legacy root location)
REM
REM If not found, run: make download-binaries
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

REM Configuration - check both bin/ and root locations
set "MAVLINK2REST_BIN="
set "USING_LEGACY=0"

if exist "%PIXEAGLE_DIR%\bin\mavlink2rest.exe" (
    set "MAVLINK2REST_BIN=%PIXEAGLE_DIR%\bin\mavlink2rest.exe"
    goto :found_binary
)

if exist "%PIXEAGLE_DIR%\mavlink2rest.exe" (
    set "MAVLINK2REST_BIN=%PIXEAGLE_DIR%\mavlink2rest.exe"
    set "USING_LEGACY=1"
    goto :found_binary
)

REM Binary not found - show error
echo.
echo [36m========================================================================[0m
echo                         MAVLink2REST Bridge
echo [36m========================================================================[0m
echo.
echo [31m[ERROR] MAVLink2REST binary not found![0m
echo.
echo    Expected locations:
echo      - %PIXEAGLE_DIR%\bin\mavlink2rest.exe (preferred)
echo      - %PIXEAGLE_DIR%\mavlink2rest.exe (legacy)
echo.
echo    To download, run:
echo      make download-binaries
echo    Or:
echo      scripts\setup\download-binaries.bat --mavlink2rest
echo.
pause
exit /b 1

:found_binary
REM Default connection settings (can be overridden by environment variables)
REM Match Linux default to avoid collisions with common GCS listeners on 14550
if not defined MAVLINK_CONNECTION set "MAVLINK_CONNECTION=udpin:127.0.0.1:14569"
if not defined MAVLINK2REST_PORT set "MAVLINK2REST_PORT=8088"

echo.
echo [36m========================================================================[0m
echo                         MAVLink2REST Bridge
echo [36m========================================================================[0m
echo.

if "%USING_LEGACY%"=="1" (
    echo [33m[WARNING] Using legacy location. Please move mavlink2rest.exe to bin\[0m
    echo.
)

echo    Binary:     %MAVLINK2REST_BIN%
echo    Connection: %MAVLINK_CONNECTION%
echo    REST Port:  %MAVLINK2REST_PORT%
echo.

REM Change to project directory
cd /d "%PIXEAGLE_DIR%"

REM Validate and preflight UDP input bind for udpin:*:* connections
set "MAVLINK_SCHEME="
set "MAVLINK_HOST="
set "MAVLINK_INPUT_PORT="
set "MAVLINK_INPUT_PID="
for /f "tokens=1,2,* delims=:" %%A in ("%MAVLINK_CONNECTION%") do (
    set "MAVLINK_SCHEME=%%A"
    set "MAVLINK_HOST=%%B"
    set "MAVLINK_INPUT_PORT=%%C"
)

if /I "!MAVLINK_SCHEME!"=="udpin" (
    set "MAVLINK_INPUT_PORT=!MAVLINK_INPUT_PORT:"=!"
    for /f "tokens=1" %%A in ("!MAVLINK_INPUT_PORT!") do set "MAVLINK_INPUT_PORT=%%~A"

    set "MAVLINK_INPUT_PORT_NON_DIGIT="
    for /f "delims=0123456789" %%A in ("!MAVLINK_INPUT_PORT!") do set "MAVLINK_INPUT_PORT_NON_DIGIT=%%A"
    if "!MAVLINK_INPUT_PORT!"=="" (
        echo [31m[ERROR] Invalid MAVLINK_CONNECTION: %MAVLINK_CONNECTION%[0m
        echo         Expected format: udpin:HOST:PORT
        exit /b 1
    )
    if defined MAVLINK_INPUT_PORT_NON_DIGIT (
        echo [31m[ERROR] Invalid MAVLINK_CONNECTION: %MAVLINK_CONNECTION%[0m
        echo         Expected format: udpin:HOST:PORT
        exit /b 1
    )

    for /f "tokens=5" %%P in ('netstat -ano -p UDP ^| findstr /R /C:":!MAVLINK_INPUT_PORT! " 2^>nul') do (
        set "MAVLINK_INPUT_PID=%%P"
        goto :mavlink_port_check_done
    )
)
:mavlink_port_check_done
if defined MAVLINK_INPUT_PID (
    echo [31m[ERROR] MAVLink UDP input port !MAVLINK_INPUT_PORT! is already in use ^(PID: !MAVLINK_INPUT_PID!^).[0m
    echo         Set a free port via environment variable before launch:
    echo         set MAVLINK_CONNECTION=udpin:127.0.0.1:14570
    exit /b 1
)

REM Check and kill any existing process on the REST port
echo    [*] Checking for existing processes on port %MAVLINK2REST_PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%MAVLINK2REST_PORT% " ^| findstr "LISTENING"') do (
    echo    [*] Killing existing process on port %MAVLINK2REST_PORT% ^(PID: %%a^)
    taskkill /PID %%a /F >nul 2>&1
)

REM Also check for any mavlink2rest processes
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq mavlink2rest.exe" /NH 2^>nul ^| findstr /I "mavlink2rest"') do (
    echo    [*] Killing existing mavlink2rest process ^(PID: %%a^)
    taskkill /PID %%a /F >nul 2>&1
)

REM Small delay to ensure ports are released
timeout /t 1 /nobreak >nul

REM Start MAVLink2REST
echo    [*] Starting MAVLink2REST...
echo.

"%MAVLINK2REST_BIN%" --connect %MAVLINK_CONNECTION% --server 0.0.0.0:%MAVLINK2REST_PORT%

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [31m[ERROR] MAVLink2REST exited with error code: %errorlevel%[0m
    pause
)

endlocal
