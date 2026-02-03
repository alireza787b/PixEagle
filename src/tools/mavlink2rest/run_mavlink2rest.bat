@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM run_mavlink2rest.bat - MAVLink2REST Server Runner
REM ============================================================================
REM Runs the mavlink2rest binary with specified or default settings.
REM
REM Usage: run_mavlink2rest.bat [MAVLINK_SRC] [SERVER_BIND]
REM
REM Example:
REM   run_mavlink2rest.bat "udpin:0.0.0.0:14550" "0.0.0.0:8088"
REM ============================================================================

REM Get base directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%A in ("%SCRIPT_DIR%\..\..\..") do set "BASE_DIR=%%~fA"

REM Load common variables
call "%BASE_DIR%\scripts\common.bat"

REM Configuration
set "DEFAULT_MAVLINK_SRC=udpin:127.0.0.1:14569"
set "DEFAULT_SERVER_BIND=0.0.0.0:8088"
set "MAVLINK2REST_BIN=%BASE_DIR%\mavlink2rest.exe"

REM Check for help
if /i "%~1"=="-h" goto :show_help
if /i "%~1"=="--help" goto :show_help

REM Parse arguments or use defaults
set "MAVLINK_SRC=%~1"
set "SERVER_BIND=%~2"
if "%MAVLINK_SRC%"=="" set "MAVLINK_SRC=%DEFAULT_MAVLINK_SRC%"
if "%SERVER_BIND%"=="" set "SERVER_BIND=%DEFAULT_SERVER_BIND%"

REM Check binary exists
if not exist "%MAVLINK2REST_BIN%" (
    echo.
    echo %RED%%CROSS%%NC% MAVLink2REST binary not found
    echo.
    echo   Expected: %MAVLINK2REST_BIN%
    echo.
    echo   Download using:
    echo   %BASE_DIR%\src\tools\download_mavlink2rest.bat
    echo.
    pause
    exit /b 1
)

REM Display configuration
echo.
echo ============================================================
echo   MAVLink2REST Server
echo ============================================================
echo   MAVLink Source: %MAVLINK_SRC%
echo   Server Bind:    %SERVER_BIND%
echo   Binary:         %MAVLINK2REST_BIN%
echo ============================================================
echo.

REM Run
"%MAVLINK2REST_BIN%" -c "%MAVLINK_SRC%" -s "%SERVER_BIND%"

set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 (
    echo.
    echo MAVLink2REST exited with code: %EXIT_CODE%
)

exit /b %EXIT_CODE%

:show_help
echo.
echo ============================================================
echo   MAVLink2REST Server Runner - Help
echo ============================================================
echo.
echo   Usage: run_mavlink2rest.bat [MAVLINK_SRC] [SERVER_BIND]
echo.
echo   Arguments:
echo     MAVLINK_SRC   MAVLink source (default: %DEFAULT_MAVLINK_SRC%)
echo     SERVER_BIND   Server bind address (default: %DEFAULT_SERVER_BIND%)
echo.
echo   Examples:
echo     run_mavlink2rest.bat
echo     run_mavlink2rest.bat "udpin:0.0.0.0:14550" "0.0.0.0:8088"
echo     run_mavlink2rest.bat "serial:COM3:115200" "127.0.0.1:8088"
echo.
echo   Installation:
echo     %BASE_DIR%\src\tools\download_mavlink2rest.bat
echo.
echo ============================================================
exit /b 0
