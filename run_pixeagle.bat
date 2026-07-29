@echo off
echo [NOTE] run_pixeagle.bat is a compatibility alias for scripts\run.bat.
call "%~dp0scripts\run.bat" %*
exit /b %ERRORLEVEL%
