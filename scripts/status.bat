@echo off
call "%~dp0windows\runtime.bat" status %*
exit /b %ERRORLEVEL%
