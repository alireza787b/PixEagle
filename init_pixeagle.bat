@echo off
REM init_pixeagle.bat
REM Initialization script for the PixEagle project on Windows
REM This script checks for the existence of configs\config.ini in the user's home directory
REM If it does not exist, it creates it by copying configs\config_default.ini
REM If it exists, it warns the user and asks if they want to reset to default values

REM Configurable base directory (change this if needed)
set "BASE_DIR=%USERPROFILE%\PixEagle"
set "CONFIG_DIR=%BASE_DIR%\configs"
set "DEFAULT_CONFIG=%CONFIG_DIR%\config_default.ini"
set "USER_CONFIG=%CONFIG_DIR%\config.ini"

REM Function to create config.ini from config_default.ini
:CREATE_CONFIG
copy "%DEFAULT_CONFIG%" "%USER_CONFIG%" >nul
echo.
echo ✅ Created '%USER_CONFIG%' from '%DEFAULT_CONFIG%'.
goto :EOF

REM Function to display the Pix Eagle banner
:DISPLAY_BANNER
echo.
echo ██████╗ ██╗  ██╗██████╗ ███████╗     ███████╗ █████╗  ██████╗ ██╗     ███████╗
echo ██╔══██╗██║  ██║██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝
echo ██████╔╝███████║██████╔╝█████╗       █████╗  ███████║██║  ███╗██║     █████╗  
echo ██╔═══╝ ██╔══██║██╔══██╗██╔══╝       ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝  
echo ██║     ██║  ██║██║  ██║███████╗     ███████╗██║  ██║╚██████╔╝███████╗███████╗
echo ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝
echo.
echo Welcome to Pix Eagle Initialization Script
echo.
echo For more information and latest documentation, visit:
echo 👉 GitHub: https://github.com/alireza787b/PixEagle
echo.
goto :EOF



REM Main script starts here
call :DISPLAY_BANNER

REM Inform the user about the base directory
echo Using base directory: '%BASE_DIR%'
echo.

REM Check if configs directory exists
if not exist "%CONFIG_DIR%" (
    echo 🗂  Configuration directory '%CONFIG_DIR%' does not exist. Creating it now...
    mkdir "%CONFIG_DIR%"
    echo ✅ Directory '%CONFIG_DIR%' created.
    echo.
)

REM Check if config_default.ini exists
if not exist "%DEFAULT_CONFIG%" (
    echo ❌ Error: Default configuration file '%DEFAULT_CONFIG%' not found.
    echo Please ensure that '%DEFAULT_CONFIG%' exists in the '%CONFIG_DIR%' directory.
    pause
    exit /b 1
)

REM Check if config.ini exists
if not exist "%USER_CONFIG%" (
    echo ⚙️  User configuration file '%USER_CONFIG%' does not exist.
    call :CREATE_CONFIG
) else (
    echo ⚠️  User configuration file '%USER_CONFIG%' already exists.
    echo Do you want to reset it to default values?
    echo ⚠️  Warning: This will overwrite your current configuration and cannot be undone.
    set /p choice=Type 'yes' to reset or 'no' to keep your existing configuration [yes/no]: 
    if /i "%choice%"=="yes" (
        call :CREATE_CONFIG
        echo ✅ Configuration file '%USER_CONFIG%' has been reset to default values.
        echo.
    ) else if /i "%choice%"=="no" (
        echo 👍 Keeping existing configuration file '%USER_CONFIG%'.
        echo.
    ) else (
        echo ❌ Invalid input. Please run the script again and type 'yes' or 'no'.
        pause
        exit /b 1
    )
)

echo 🎉 Initialization complete.
echo.
echo 🚀 You can now start using PixEagle. Happy flying!
echo.
pause
