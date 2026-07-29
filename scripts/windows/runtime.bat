@echo off
setlocal

set "WINDOWS_DIR=%~dp0"
for %%I in ("%WINDOWS_DIR%\..\..") do set "PIXEAGLE_DIR=%%~fI"

if defined PIXEAGLE_VENV_DIR (
    pushd "%PIXEAGLE_DIR%"
    for %%I in ("%PIXEAGLE_VENV_DIR%") do set "VENV_DIR=%%~fI"
    popd
) else if exist "%PIXEAGLE_DIR%\.venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
) else if exist "%PIXEAGLE_DIR%\venv\Scripts\python.exe" (
    set "VENV_DIR=%PIXEAGLE_DIR%\venv"
) else (
    set "VENV_DIR=%PIXEAGLE_DIR%\.venv"
)

set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "CONTROLLER=%WINDOWS_DIR%runtime.py"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] PixEagle virtual-environment interpreter not found:
    echo         %PYTHON_EXE%
    echo         Run scripts\init.bat first.
    exit /b 1
)
if not exist "%CONTROLLER%" (
    echo [ERROR] Windows runtime controller not found:
    echo         %CONTROLLER%
    exit /b 1
)
if "%~1"=="" (
    echo [ERROR] Windows runtime command is required.
    exit /b 1
)

"%PYTHON_EXE%" "%CONTROLLER%" %*
exit /b %ERRORLEVEL%
