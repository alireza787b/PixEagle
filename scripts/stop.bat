@echo off
REM ============================================================================
REM scripts\stop.bat - Stop All PixEagle Services (Windows)
REM ============================================================================
REM Gracefully stops all PixEagle services running in Windows Terminal tabs.
REM
REM Usage:
REM   make stop-win                (recommended with nmake)
REM   scripts\stop.bat             (direct)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal EnableDelayedExpansion

REM Get script directory
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..") do set "PIXEAGLE_DIR=%%~fi"

REM Source common functions
call "%SCRIPTS_DIR%\lib\common.bat"

REM Configuration - ports used by PixEagle services
set "PORTS=3000 5077 5551 8088 50051"

REM ============================================================================
REM Banner
REM ============================================================================
echo.
call :print_cyan "========================================================================"
echo                     Stopping PixEagle Services
call :print_cyan "========================================================================"
echo.

REM ============================================================================
REM Kill Processes on Ports
REM ============================================================================
echo    [*] Cleaning up ports...
echo.

for %%p in (%PORTS%) do (
    REM Find process using the port
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr :%%p ^| findstr LISTENING 2^>nul') do (
        set "PID=%%a"
        if not "!PID!"=="" (
            REM Get process name
            for /f "tokens=1" %%n in ('tasklist /fi "PID eq !PID!" /fo csv /nh 2^>nul ^| findstr /v "INFO:"') do (
                set "PROCNAME=%%~n"
            )

            REM Kill the process
            taskkill /PID !PID! /F >nul 2>&1
            if !errorlevel! equ 0 (
                call :print_green "   [OK] Killed !PROCNAME! on port %%p (PID: !PID!)"
            ) else (
                call :print_yellow "   [!] Could not kill process on port %%p"
            )
        )
    )
)

REM ============================================================================
REM Kill Python processes running PixEagle
REM ============================================================================
echo.
echo    [*] Stopping Python processes...

for /f "tokens=2" %%a in ('tasklist /fi "IMAGENAME eq python.exe" /fo csv /nh 2^>nul ^| findstr /i "python"') do (
    set "PID=%%~a"
    REM Check if this Python process is running PixEagle (check command line)
    wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /i "main.py" >nul 2>&1
    if !errorlevel! equ 0 (
        taskkill /PID !PID! /F >nul 2>&1
        call :print_green "   [OK] Stopped PixEagle main.py (PID: !PID!)"
    )
)

REM ============================================================================
REM Kill Node processes (Dashboard)
REM ============================================================================
echo.
echo    [*] Stopping Node.js processes...

for /f "tokens=2" %%a in ('tasklist /fi "IMAGENAME eq node.exe" /fo csv /nh 2^>nul ^| findstr /i "node"') do (
    set "PID=%%~a"
    wmic process where "ProcessId=!PID!" get CommandLine 2>nul | findstr /i "dashboard" >nul 2>&1
    if !errorlevel! equ 0 (
        taskkill /PID !PID! /F >nul 2>&1
        call :print_green "   [OK] Stopped Dashboard (PID: !PID!)"
    )
)

REM ============================================================================
REM Kill MAVLink2REST
REM ============================================================================
echo.
echo    [*] Stopping MAVLink2REST...

taskkill /IM mavlink2rest.exe /F >nul 2>&1
if !errorlevel! equ 0 (
    call :print_green "   [OK] Stopped MAVLink2REST"
) else (
    echo    [-] MAVLink2REST was not running
)

REM ============================================================================
REM Kill MAVSDK Server
REM ============================================================================
echo.
echo    [*] Stopping MAVSDK Server...

taskkill /IM mavsdk_server_bin.exe /F >nul 2>&1
set "MAVSDK_KILLED=0"
if !errorlevel! equ 0 set "MAVSDK_KILLED=1"
taskkill /IM mavsdk_server.exe /F >nul 2>&1
if !errorlevel! equ 0 set "MAVSDK_KILLED=1"

if "!MAVSDK_KILLED!"=="1" (
    call :print_green "   [OK] Stopped MAVSDK Server"
) else (
    echo    [-] MAVSDK Server was not running
)

REM ============================================================================
REM Summary
REM ============================================================================
echo.
call :print_cyan "========================================================================"
call :print_green "                    [OK] All Services Stopped"
call :print_cyan "========================================================================"
echo.
echo    To start again: make run-win  or  scripts\run.bat
echo.

endlocal
exit /b 0

REM ============================================================================
REM Helper Functions
REM ============================================================================
:print_cyan
echo [36m%~1[0m
exit /b 0

:print_green
echo [32m%~1[0m
exit /b 0

:print_yellow
echo [33m%~1[0m
exit /b 0
