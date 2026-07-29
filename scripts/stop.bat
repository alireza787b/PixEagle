@echo off
call "%~dp0windows\runtime.bat" stop %*
exit /b %ERRORLEVEL%
