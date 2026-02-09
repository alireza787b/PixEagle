@echo off
REM ============================================================================
REM scripts\components\mavsdk_server.bat - Run MAVSDK Server (Windows)
REM ============================================================================
REM Starts the MAVSDK gRPC bridge binary used when EXTERNAL_MAVSDK_SERVER=true.
REM
REM Usage:
REM   scripts\components\mavsdk_server.bat
REM
REM Expected binary locations:
REM   - bin\mavsdk_server_bin.exe (preferred)
REM   - mavsdk_server_bin.exe (legacy root location)
REM
REM If not found, run: scripts\setup\download-binaries.bat --mavsdk
REM ============================================================================

setlocal

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

REM Locate binary
set "MAVSDK_BIN="
set "USING_LEGACY=0"

if exist "%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe" (
    set "MAVSDK_BIN=%PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe"
    goto :found_binary
)

if exist "%PIXEAGLE_DIR%\mavsdk_server_bin.exe" (
    set "MAVSDK_BIN=%PIXEAGLE_DIR%\mavsdk_server_bin.exe"
    set "USING_LEGACY=1"
    goto :found_binary
)

echo.
echo [36m========================================================================[0m
echo                           MAVSDK Server
echo [36m========================================================================[0m
echo.
echo [31m[ERROR] MAVSDK Server binary not found![0m
echo.
echo    Expected locations:
echo      - %PIXEAGLE_DIR%\bin\mavsdk_server_bin.exe (preferred)
echo      - %PIXEAGLE_DIR%\mavsdk_server_bin.exe (legacy)
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

if "%USING_LEGACY%"=="1" (
    echo [33m[WARNING] Using legacy location. Please move mavsdk_server_bin.exe to bin\[0m
    echo.
)

echo    Binary: %MAVSDK_BIN%
echo.

REM Change to project directory
cd /d "%PIXEAGLE_DIR%"

REM Kill existing processes to avoid duplicate server instances
echo    [*] Checking for existing MAVSDK Server instances...
taskkill /IM mavsdk_server_bin.exe /F >nul 2>&1
taskkill /IM mavsdk_server.exe /F >nul 2>&1

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":50051 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo    [*] Starting MAVSDK Server...
echo.
"%MAVSDK_BIN%"

if %errorlevel% neq 0 (
    echo.
    echo [31m[ERROR] MAVSDK Server exited with error code: %errorlevel%[0m
    pause
)

endlocal
