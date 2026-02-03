@echo off
REM ============================================================================
REM common.bat - Shared Variables for PixEagle Scripts (Windows)
REM ============================================================================
REM Sets up environment variables for colors and symbols.
REM Call at the start of each PixEagle batch script.
REM
REM Usage: call "%~dp0scripts\common.bat"
REM ============================================================================

REM Prevent multiple loading
if defined _PIXEAGLE_COMMON_LOADED exit /b 0
set "_PIXEAGLE_COMMON_LOADED=1"

REM ============================================================================
REM Enable ANSI Colors (Windows 10 1909+)
REM ============================================================================
REM Enable Virtual Terminal Processing
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

REM Set UTF-8 codepage
chcp 65001 >nul 2>&1

REM ============================================================================
REM Create Escape Character (Multiple Methods for Reliability)
REM ============================================================================
set "ESC="

REM Method 1: PowerShell (most reliable)
for /f "delims=" %%E in ('powershell -NoProfile -Command "[char]27"') do set "ESC=%%E"

REM Method 2: Fallback using prompt if PowerShell failed
if not defined ESC (
    for /f "tokens=2" %%E in ('prompt $E ^& for %%a in ^(1^) do rem') do set "ESC=%%E"
)

REM ============================================================================
REM Color Definitions
REM ============================================================================
if defined ESC (
    set "RED=%ESC%[91m"
    set "GREEN=%ESC%[92m"
    set "YELLOW=%ESC%[93m"
    set "BLUE=%ESC%[94m"
    set "MAGENTA=%ESC%[95m"
    set "CYAN=%ESC%[96m"
    set "WHITE=%ESC%[97m"
    set "BOLD=%ESC%[1m"
    set "DIM=%ESC%[2m"
    set "NC=%ESC%[0m"
    set "_COLORS_ENABLED=1"
) else (
    REM Fallback: No colors
    set "RED="
    set "GREEN="
    set "YELLOW="
    set "BLUE="
    set "MAGENTA="
    set "CYAN="
    set "WHITE="
    set "BOLD="
    set "DIM="
    set "NC="
    set "_COLORS_ENABLED=0"
)

REM ============================================================================
REM Symbols (Clean ASCII)
REM ============================================================================
set "CHECK=[OK]"
set "CROSS=[X]"
set "WARN=[!]"
set "INFO=[i]"
set "ARROW=-->"
set "BULLET=*"

exit /b 0
