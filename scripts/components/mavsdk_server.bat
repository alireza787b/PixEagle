@echo off
REM ============================================================================
REM scripts\components\mavsdk_server.bat - Run MAVSDK Server (Windows)
REM ============================================================================
REM Starts the MAVSDK gRPC bridge binary used when EXTERNAL_MAVSDK_SERVER=true.
REM
REM Usage:
REM   scripts\components\mavsdk_server.bat
REM
REM Expected binary location:
REM   - bin\mavsdk_server_bin.exe
REM
REM If not found, run: scripts\setup\download-binaries.bat --mavsdk
REM ============================================================================

setlocal

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

if /I not "%PIXEAGLE_ALLOW_UNSCOPED_MAVSDK_GRPC%"=="1" (
    echo [ERROR] Native MAVSDK Server startup is outside the Windows Core preview.
    echo         The upstream gRPC listener cannot be restricted to loopback.
    echo         After firewall review, experts may explicitly set:
    echo         PIXEAGLE_ALLOW_UNSCOPED_MAVSDK_GRPC=1
    exit /b 1
)

set "MAVSDK_BIN=%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe"
if exist "%MAVSDK_BIN%" goto :found_binary

echo.
echo [36m========================================================================[0m
echo                           MAVSDK Server
echo [36m========================================================================[0m
echo.
echo [31m[ERROR] MAVSDK Server binary not found![0m
echo.
echo    Expected location:
echo      - %MAVSDK_BIN%
echo.
echo    To download, run:
echo      scripts\setup\download-binaries.bat --mavsdk
echo.
pause
exit /b 1

:found_binary
echo.
echo [36m========================================================================[0m
echo                           MAVSDK Server
echo [36m========================================================================[0m
echo.

echo    Binary: %MAVSDK_BIN%
echo.

REM Change to project directory
cd /d "%PIXEAGLE_DIR%"

if not defined MAVSDK_SERVER_PORT set "MAVSDK_SERVER_PORT=50051"
if not defined PX4_SYSTEM_ADDRESS set "PX4_SYSTEM_ADDRESS=udpin://127.0.0.1:14540"

REM Refuse unknown listeners. Component launchers never terminate by port/name.
echo    [*] Verifying MAVSDK gRPC port %MAVSDK_SERVER_PORT% is free...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%MAVSDK_SERVER_PORT% " ^| findstr "LISTENING"') do (
    echo [31m[ERROR] Port %MAVSDK_SERVER_PORT% is already in use by PID %%a.[0m
    echo         No process was terminated.
    exit /b 1
)

echo    [*] Starting MAVSDK Server...
echo.
"%MAVSDK_BIN%" -p "%MAVSDK_SERVER_PORT%" "%PX4_SYSTEM_ADDRESS%"

if %errorlevel% neq 0 (
    echo.
    echo [31m[ERROR] MAVSDK Server exited with error code: %errorlevel%[0m
    pause
)

endlocal
