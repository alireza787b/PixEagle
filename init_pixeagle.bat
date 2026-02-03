@echo off
REM ============================================================================
REM init_pixeagle.bat - DEPRECATED: Use scripts\init.bat
REM ============================================================================
REM This wrapper script is deprecated and will be removed in v6.0.
REM Please update your workflow to use the new entry points.
REM
REM New usage:
REM   make init-win              (with nmake/make)
REM   scripts\init.bat           (direct)
REM
REM Project: PixEagle
REM Repository: https://github.com/alireza787b/PixEagle
REM ============================================================================

echo.
echo [33m========================================================================[0m
echo [33m   [!] DEPRECATION WARNING[0m
echo [33m========================================================================[0m
echo.
echo    init_pixeagle.bat is deprecated and will be removed in v6.0
echo.
echo    Please use one of these alternatives:
echo      [36mmake init-win[0m          (with nmake/make)
echo      [36mscripts\init.bat[0m       (direct)
echo.
echo [33m========================================================================[0m
echo.
echo    Continuing in 3 seconds...
timeout /t 3 /nobreak >nul
echo.

REM Forward to the new script location
call "%~dp0scripts\init.bat" %*
