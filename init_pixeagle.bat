:: init_pixeagle.bat
:: Initialization script for the PixEagle project on Windows
:: This script sets up the environment for PixEagle, including Python virtual environment,
:: installs required Python packages, and handles the configuration file.
:: It also informs the user about additional dependencies like Node.js and npm.

@echo off
setlocal EnableDelayedExpansion

:: Function to display the Pix Eagle banner
call :display_banner

:: Check Python version
call :check_python_version

:: Create virtual environment if not exists
call :create_virtualenv

:: Install requirements
call :install_requirements

:: Define directories and config files
set BASE_DIR=%cd%
set CONFIG_DIR=%BASE_DIR%\configs
set DEFAULT_CONFIG=%CONFIG_DIR%\config_default.yaml
set USER_CONFIG=%CONFIG_DIR%\config.yaml

:: Inform the user about the base directory
echo.
echo Using base directory: '%BASE_DIR%'

:: Check if configs directory exists
if not exist "%CONFIG_DIR%" (
    echo 🗂  Configuration directory '%CONFIG_DIR%' does not exist. Creating it now...
    mkdir "%CONFIG_DIR%"
    echo ✅ Directory '%CONFIG_DIR%' created.
)

:: Check if config_default.yaml exists
if not exist "%DEFAULT_CONFIG%" (
    echo ❌ Error: Default configuration file '%DEFAULT_CONFIG%' not found.
    echo Please ensure that '%DEFAULT_CONFIG%' exists in the '%CONFIG_DIR%' directory.
    exit /b 1
)

:: Check if config.yaml exists
if not exist "%USER_CONFIG%" (
    echo ⚙️  User configuration file '%USER_CONFIG%' does not exist.
    call :create_config
) else (
    echo ⚠️  User configuration file '%USER_CONFIG%' already exists.
    echo Do you want to reset it to default values?
    echo ⚠️  Warning: This will overwrite your current configuration and cannot be undone.
    set /p choice=Type 'yes' to reset or 'no' to keep your existing configuration [yes/no]: 
    if /i "%choice%"=="yes" (
        call :create_config
        echo ✅ Configuration file '%USER_CONFIG%' has been reset to default values.
    ) else if /i "%choice%"=="no" (
        echo 👍 Keeping existing configuration file '%USER_CONFIG%'.
    ) else (
        echo ❌ Invalid input. Please run the script again and type 'yes' or 'no'.
        exit /b 1
    )
)

echo.
echo 🎉 Initialization complete.
echo 🚀 You can now start using PixEagle. Happy flying!
echo.
echo 📢 Note:
echo 👉 You might need to install Node.js and npm if they are not already installed.
echo    You can install them by visiting https://nodejs.org/
echo 👉 Please edit '%USER_CONFIG%' to configure settings like video source and other parameters according to your system.
pause
exit /b

:display_banner
echo.
echo ██████╗ ██╗  ██████╗ ███████╗     ███████╗ █████╗  ██████╗ ██╗     ███████╗
echo ██╔══██╗██║ ██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝
echo ██████╔╝██║ ██║       ╔╝█████╗       █████╗  ███████║██║  ███╗██║     █████╗
echo ██╔═══╝ ██║ ██║ ██╔══██╗██╔══╝       ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝
echo ██║     ██║ ██║ ██████╔╝███████╗     ███████╗██║  ██║╚██████╔╝███████╗███████╗
echo ╚═╝     ╚═╝╚═╝        ╚═════╝ ╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝
echo.
echo Welcome to Pix Eagle Initialization Script
echo.
echo For more information and latest documentation, visit:
echo 👉 GitHub: https://github.com/alireza787b/PixEagle
echo.
goto :EOF

:check_python_version
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Python is not installed. Please install Python 3.9 or later.
    exit /b 1
)
for /f "tokens=2 delims=[]" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
set PYTHON_MAJOR=%PYTHON_VERSION:~0,1%
set PYTHON_MINOR=%PYTHON_VERSION:~2,1%
if %PYTHON_MAJOR% GTR 3 (
    echo ✅ Python version %PYTHON_VERSION% detected.
) else if %PYTHON_MAJOR% EQU 3 (
    if %PYTHON_MINOR% GEQ 9 (
        echo ✅ Python version %PYTHON_VERSION% detected.
    ) else (
        echo ❌ Python version %PYTHON_VERSION% detected. Python 3.9 or later is required.
        exit /b 1
    )
) else (
    echo ❌ Python version %PYTHON_VERSION% detected. Python 3.9 or later is required.
    exit /b 1
)
goto :EOF

:create_virtualenv
if not exist venv (
    echo 📁 Virtual environment not found. Creating one...
    python -m venv venv
    echo ✅ Virtual environment created.
) else (
    echo ✅ Virtual environment already exists.
)
goto :EOF

:install_requirements
call venv\Scripts\activate
echo 📦 Installing Python dependencies from requirements.txt...
pip install --upgrade pip
pip install -r requirements.txt
echo ✅ Python dependencies installed.
call venv\Scripts\deactivate
goto :EOF

:create_config
copy "%DEFAULT_CONFIG%" "%USER_CONFIG%"
echo.
echo ✅ Created '%USER_CONFIG%' from '%DEFAULT_CONFIG%'.
goto :EOF
