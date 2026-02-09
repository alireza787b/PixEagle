@echo off
REM ============================================================================
REM ports.bat - Shared port defaults and resolution helpers for PixEagle (Win)
REM ============================================================================

setlocal EnableDelayedExpansion

if not defined PIXEAGLE_DIR (
    set "LIB_DIR=%~dp0"
    set "LIB_DIR=%LIB_DIR:~0,-1%"
    for %%I in ("%LIB_DIR%\..") do set "PIXEAGLE_DIR=%%~fI"
)

set "PORT_DASHBOARD=3040"
set "PORT_BACKEND=5077"
set "PORT_MAVLINK2REST=8088"
set "PORT_WEBSOCKET=5551"

if exist "%PIXEAGLE_DIR%\dashboard\env_default.yaml" (
    for /f "tokens=1,* delims=:" %%A in ('findstr /R /B /C:"PORT[ ]*:" "%PIXEAGLE_DIR%\dashboard\env_default.yaml" 2^>nul') do (
        set "CANDIDATE=%%B"
        set "CANDIDATE=!CANDIDATE: =!"
        set "CANDIDATE=!CANDIDATE:"=!"
        for /f "tokens=1 delims=#" %%P in ("!CANDIDATE!") do set "CANDIDATE=%%P"
        echo !CANDIDATE! | findstr /R "^[0-9][0-9]*$" >nul && set "PORT_DASHBOARD=!CANDIDATE!"
    )
)

if exist "%PIXEAGLE_DIR%\dashboard\.env" (
    for /f "tokens=1,* delims==" %%A in ('findstr /R /B /C:"PORT=[0-9][0-9]*$" "%PIXEAGLE_DIR%\dashboard\.env" 2^>nul') do (
        set "CANDIDATE=%%B"
        set "CANDIDATE=!CANDIDATE: =!"
        echo !CANDIDATE! | findstr /R "^[0-9][0-9]*$" >nul && set "PORT_DASHBOARD=!CANDIDATE!"
    )
)

if exist "%PIXEAGLE_DIR%\configs\config.yaml" (
    for /f "tokens=1,* delims=:" %%A in ('findstr /R /B /C:"[ ]*HTTP_STREAM_PORT[ ]*:" "%PIXEAGLE_DIR%\configs\config.yaml" 2^>nul') do (
        set "CANDIDATE=%%B"
        set "CANDIDATE=!CANDIDATE: =!"
        set "CANDIDATE=!CANDIDATE:"=!"
        for /f "tokens=1 delims=#" %%P in ("!CANDIDATE!") do set "CANDIDATE=%%P"
        echo !CANDIDATE! | findstr /R "^[0-9][0-9]*$" >nul && set "PORT_BACKEND=!CANDIDATE!"
    )
)

endlocal & (
    set "PIXEAGLE_PORT_DASHBOARD=%PORT_DASHBOARD%"
    set "PIXEAGLE_PORT_BACKEND=%PORT_BACKEND%"
    set "PIXEAGLE_PORT_MAVLINK2REST=%PORT_MAVLINK2REST%"
    set "PIXEAGLE_PORT_WEBSOCKET=%PORT_WEBSOCKET%"
)
exit /b 0
