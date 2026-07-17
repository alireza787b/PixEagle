@echo off
REM ============================================================================
REM scripts\components\main.bat - Run PixEagle Main Application (Windows)
REM ============================================================================
REM Runs the main Python application with the exact virtual-environment interpreter.
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

REM Match setup virtual-environment resolution: explicit override, .venv,
REM legacy venv, then .venv for a fresh installation. Selection is based on
REM the interpreter itself, not an activation script that may be incomplete.
if defined PIXEAGLE_VENV_DIR (
    pushd "%PIXEAGLE_DIR%"
    for %%i in ("%PIXEAGLE_VENV_DIR%") do set "VENV_DIR=%%~fi"
    popd
) else if exist "%PIXEAGLE_DIR%\.venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
) else if exist "%PIXEAGLE_DIR%\venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\venv"
) else (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
)
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

REM Configuration
set "MAIN_SCRIPT=%PIXEAGLE_DIR%\src\main.py"
set "DEV_MODE=0"
set "CHECK_ONLY=0"

if /I "%~1"=="--dev" set "DEV_MODE=1"
if /I "%~1"=="-d" set "DEV_MODE=1"
if /I "%~1"=="--check" set "CHECK_ONLY=1"

echo.
echo [36m========================================================================[0m
if "%DEV_MODE%"=="1" (
    echo                PixEagle Main Application ^(Development^)
) else (
    echo                     PixEagle Main Application
)
echo [36m========================================================================[0m
echo.

REM Check the exact interpreter that will execute PixEagle.
if not exist "%PYTHON_EXE%" (
    echo [31m[ERROR] Virtual environment interpreter not found: %PYTHON_EXE%[0m
    echo         Please run 'make init-win' or 'scripts\init.bat' first.
    if "%CHECK_ONLY%"=="0" pause
    exit /b 1
)

REM Check if main.py exists
if not exist "%MAIN_SCRIPT%" (
    echo [31m[ERROR] Main script not found at: %MAIN_SCRIPT%[0m
    if "%CHECK_ONLY%"=="0" pause
    exit /b 1
)

if "%CHECK_ONLY%"=="1" exit /b 0

REM Change to project directory
cd /d "%PIXEAGLE_DIR%"

REM Never terminate a process merely because it owns a configured port. The
REM backend bind fails with an actionable address-in-use error if another
REM application or PixEagle instance already owns the port.

REM Activation is optional convenience; execution remains pinned to PYTHON_EXE.
if exist "%VENV_DIR%\Scripts\activate.bat" (
    call "%VENV_DIR%\Scripts\activate.bat"
    if errorlevel 1 (
        echo [31m[ERROR] Failed to activate virtual environment: %VENV_DIR%[0m
        pause
        exit /b 1
    )
)

if "%DEV_MODE%"=="1" (
    set "PIXEAGLE_DEV_MODE=true"
    set "FLASK_DEBUG=1"
    set "PYTHONUNBUFFERED=1"
    echo    [*] Development mode enabled for backend
)

echo    [*] Starting main.py...
echo.

"%PYTHON_EXE%" "%MAIN_SCRIPT%"
set "APP_EXIT_CODE=%ERRORLEVEL%"

REM Keep window open if there was an error
if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo [31m[ERROR] Main application exited with error code[0m
    pause
)

endlocal & exit /b %APP_EXIT_CODE%
