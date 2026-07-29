@echo off
echo [NOTE] init_pixeagle.bat is a compatibility alias for scripts\init.bat.
call "%~dp0scripts\init.bat" %*
exit /b %ERRORLEVEL%
