@echo off
call "%~dp0windows\runtime.bat" restart %*
exit /b %ERRORLEVEL%
