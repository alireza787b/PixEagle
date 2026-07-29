@echo off
setlocal

set "SCRIPTS_DIR=%~dp0"
for %%I in ("%SCRIPTS_DIR%\..") do set "PIXEAGLE_DIR=%%~fI"
set "SETUP_SCRIPT=%PIXEAGLE_DIR%\scripts\windows\setup.py"

if /I not "%PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS%"=="1" (
    echo [ERROR] Native Windows support is a Core local-lab preview.
    echo         Review docs\WINDOWS_SETUP.md, then set:
    echo         set PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1
    exit /b 1
)

if not exist "%SETUP_SCRIPT%" (
    echo [ERROR] Windows setup controller not found:
    echo         %SETUP_SCRIPT%
    exit /b 1
)

set "PYTHON_COMMAND="
set "PYTHON_PROBE=import platform,struct,sys; supported=sys.version_info[:2] in {(3,11),(3,12)} and platform.machine().strip().lower() in {'amd64','x86_64'} and struct.calcsize('P')*8 == 64; raise SystemExit(0 if supported else 1)"
where py.exe >nul 2>&1
if not errorlevel 1 (
    py.exe -3.12 -c "%PYTHON_PROBE%" >nul 2>&1
    if not errorlevel 1 set "PYTHON_COMMAND=py.exe -3.12"
    if not defined PYTHON_COMMAND (
        py.exe -3.11 -c "%PYTHON_PROBE%" >nul 2>&1
        if not errorlevel 1 set "PYTHON_COMMAND=py.exe -3.11"
    )
)
if not defined PYTHON_COMMAND (
    where python.exe >nul 2>&1
    if not errorlevel 1 (
        python.exe -c "%PYTHON_PROBE%" >nul 2>&1
        if not errorlevel 1 set "PYTHON_COMMAND=python.exe"
    )
)
if not defined PYTHON_COMMAND (
    echo [ERROR] CPython 3.11 or 3.12 x64 was not found.
    echo         Install it from https://www.python.org/downloads/windows/
    exit /b 1
)

pushd "%PIXEAGLE_DIR%"
%PYTHON_COMMAND% "%SETUP_SCRIPT%" %*
set "SETUP_EXIT=%ERRORLEVEL%"
popd
exit /b %SETUP_EXIT%
