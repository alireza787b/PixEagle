@echo off
REM ============================================================================
REM run_pixeagle.bat - DEPRECATED: Use scripts\run.bat
REM ============================================================================
REM This wrapper script is deprecated and will be removed in v6.0.
REM Please update your workflow to use the new entry points.
REM
REM New usage:
REM   make run-win               (with nmake/make)
REM   make dev-win               (development mode)
REM   scripts\run.bat            (direct)
REM   scripts\run.bat --dev      (development mode)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

echo.
echo [33m========================================================================[0m
echo [33m   [!] DEPRECATION WARNING[0m
echo [33m========================================================================[0m
echo.
echo    run_pixeagle.bat is deprecated and will be removed in v6.0
echo.
echo    Please use one of these alternatives:
echo      [36mmake run-win[0m           (with nmake/make)
echo      [36mmake dev-win[0m           (development mode)
echo      [36mscripts\run.bat[0m        (direct)
echo.
echo [33m========================================================================[0m
echo.
echo    Continuing in 3 seconds...
timeout /t 3 /nobreak >nul
echo.

REM Forward to the new script location
call "%~dp0scripts\run.bat" %*
