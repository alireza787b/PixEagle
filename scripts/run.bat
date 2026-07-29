@echo off
call "%~dp0windows\runtime.bat" start %*
exit /b %ERRORLEVEL%
