@echo off
REM ============================================================================
REM scripts\components\main.bat - Run PixEagle Main Application (Windows)
REM ============================================================================
REM Activates the virtual environment and runs the main Python application.
REM
REM Usage:
REM   scripts\components\main.bat          (from project root)
REM   scripts\components\main.bat --dev    (development mode env vars)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

setlocal

REM Get script and project directories
set "SCRIPTS_DIR=%~dp0"
set "SCRIPTS_DIR=%SCRIPTS_DIR:~0,-1%"
for %%i in ("%SCRIPTS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fi"

REM Configuration
set "VENV_DIR=%PIXEAGLE_DIR%\venv"
set "MAIN_SCRIPT=%PIXEAGLE_DIR%\src\main.py"
set "DEV_MODE=0"

if /I "%~1"=="--dev" set "DEV_MODE=1"
if /I "%~1"=="-d" set "DEV_MODE=1"

echo.
echo [36m========================================================================[0m
if "%DEV_MODE%"=="1" (
    echo                PixEagle Main Application ^(Development^)
) else (
    echo                     PixEagle Main Application
)
echo [36m========================================================================[0m
echo.

REM Check if virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [31m[ERROR] Virtual environment not found at: %VENV_DIR%[0m
    echo         Please run 'make init-win' or 'scripts\init.bat' first.
    pause
    exit /b 1
)

REM Check if main.py exists
if not exist "%MAIN_SCRIPT%" (
    echo [31m[ERROR] Main script not found at: %MAIN_SCRIPT%[0m
    pause
    exit /b 1
)

REM Change to project directory
cd /d "%PIXEAGLE_DIR%"

REM Check and kill any existing process on the backend port (5077)
echo    [*] Checking for existing processes on port 5077...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5077 " ^| findstr "LISTENING"') do (
    echo    [*] Killing existing process on port 5077 ^(PID: %%a^)
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM Activate virtual environment and run
echo    [*] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

if "%DEV_MODE%"=="1" (
    set "PIXEAGLE_DEV_MODE=true"
    set "FLASK_DEBUG=1"
    set "PYTHONUNBUFFERED=1"
    echo    [*] Development mode enabled for backend
)

echo    [*] Starting main.py...
echo.

python "%MAIN_SCRIPT%"

REM Keep window open if there was an error
if errorlevel 1 (
    echo.
    echo [31m[ERROR] Main application exited with error code[0m
    pause
)

endlocal
