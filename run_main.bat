@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM run_main.bat - PixEagle Python Backend Runner
REM ============================================================================
REM Runs the main Python application with auto-restart support.
REM
REM Usage: run_main.bat [--dev]
REM   --dev, -d  Development mode with enhanced debugging
REM ============================================================================

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

REM Load common variables
call "%SCRIPT_DIR%\scripts\common.bat"

REM Configuration
set "VENV_DIR=%SCRIPT_DIR%\venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"
set "MAIN_SCRIPT=%SCRIPT_DIR%\src\main.py"
set "DEV_MODE=false"
set "RESTART_CODE=42"

REM Parse arguments
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--dev" ( set "DEV_MODE=true" & shift & goto :parse_args )
if /i "%~1"=="-d" ( set "DEV_MODE=true" & shift & goto :parse_args )
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
shift
goto :parse_args
:args_done

REM Display header
echo.
echo ============================================================
echo   PixEagle Main Application
echo ============================================================
if "%DEV_MODE%"=="true" (
    echo   Mode: %YELLOW%Development%NC%
) else (
    echo   Mode: Production
)
echo ============================================================
echo.

REM Check virtual environment
if not exist "%VENV_DIR%" (
    echo %RED%%CROSS%%NC% Virtual environment not found
    echo       Run: init_pixeagle.bat
    pause
    exit /b 1
)
echo %GREEN%%CHECK%%NC% Virtual environment found

REM Check Python
if not exist "%PYTHON%" (
    echo %RED%%CROSS%%NC% Python interpreter not found
    pause
    exit /b 1
)
echo %GREEN%%CHECK%%NC% Python interpreter ready

REM Check main script
if not exist "%MAIN_SCRIPT%" (
    echo %RED%%CROSS%%NC% Main script not found: %MAIN_SCRIPT%
    pause
    exit /b 1
)
echo %GREEN%%CHECK%%NC% Main script found
echo.

REM Set development environment variables
if "%DEV_MODE%"=="true" (
    set "PIXEAGLE_DEV_MODE=true"
    set "FLASK_DEBUG=1"
    set "PYTHONUNBUFFERED=1"
    echo %BLUE%%INFO%%NC% Development environment set
    echo.
)

REM Run with restart loop
:restart_loop
echo %ARROW% Starting PixEagle backend...
echo.

"%PYTHON%" "%MAIN_SCRIPT%"
set "EXIT_CODE=%errorlevel%"

if "%EXIT_CODE%"=="%RESTART_CODE%" (
    echo.
    echo ============================================================
    echo   %YELLOW%Restart Requested (Exit Code 42)%NC%
    echo ============================================================
    echo   Restarting in 2 seconds...
    timeout /t 2 /nobreak >nul
    echo.
    goto :restart_loop
)

if "%EXIT_CODE%"=="0" (
    echo.
    echo %GREEN%%CHECK%%NC% Application exited normally
) else (
    echo.
    echo %RED%%CROSS%%NC% Application exited with code: %EXIT_CODE%
)

echo.
echo ============================================================
echo   Application Stopped
echo ============================================================
echo.
pause
exit /b %EXIT_CODE%

:show_help
echo.
echo ============================================================
echo   PixEagle Main Application - Help
echo ============================================================
echo.
echo   Usage: run_main.bat [OPTIONS]
echo.
echo   Options:
echo     --dev, -d   Development mode (enhanced debugging)
echo     --help, -h  Show this help
echo.
echo   Exit Codes:
echo     0   Normal exit
echo     42  Restart requested (auto-restarts)
echo.
echo ============================================================
exit /b 0
