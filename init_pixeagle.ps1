# init_pixeagle.ps1
# Initialization script for the PixEagle project on Windows
# This script sets up the environment for PixEagle, including Python virtual environment,
# installs required Python packages, and handles the configuration files.
# It also informs the user about additional dependencies like Node.js and npm.

# Function to display the PixEagle banner
function Display-Banner {
    Write-Host ""
    Write-Host "██████╗ ██╗  ██████╗ ███████╗  ███████╗ █████╗ ██████╗  ██╗     ███████╗"
    Write-Host "██╔══██╗██║ ██╔══██╗██╔════╝     ██╔════╝██╔══██╗██╔════╝ ██║     ██╔════╝"
    Write-Host "██████╔╝██║ ██║  █████ █████╗    ███████║██  ███╗██ █████╗██      █████  "
    Write-Host "██╔═══╝ ██║ ██║ ██╔══██╗██╔══╝   ██╔══╝  ██╔══██║██║   ██║██║     ██╔══╝  "
    Write-Host "██║     ██║ ██║ ██████╔╝███████╗ ███████╗██║  ██║╚██████╔╝███████╗███████╗"
    Write-Host "╚═╝     ╚═╝╚═╝        ╚═════╝ ╚══════╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
    Write-Host ""
    Write-Host "Welcome to PixEagle Initialization Script"
    Write-Host ""
    Write-Host "For more information and latest documentation, visit:"
    Write-Host "👉 GitHub: https://github.com/alireza787b/PixEagle`n"
    Start-Sleep -Seconds 1
}

# Function to check Python version
function Check-PythonVersion {
    $pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonPath) {
        Write-Host "❌ Python 3 is not installed or not in PATH. Please install Python 3.9 or later."
        exit 1
    }

    $pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $requiredVersion = "3.9"

    if ([Version]$pythonVersion -ge [Version]$requiredVersion) {
        Write-Host "✅ Python version $pythonVersion detected."
    } else {
        Write-Host "❌ Python version $pythonVersion detected. Python 3.9 or later is required."
        exit 1
    }
}

# Function to create virtual environment
function Create-VirtualEnv {
    if (-not (Test-Path "venv")) {
        Write-Host "📁 Virtual environment not found. Creating one..."
        python -m venv venv
        Write-Host "✅ Virtual environment created."
    } else {
        Write-Host "✅ Virtual environment already exists."
    }
}

# Function to activate virtual environment and install requirements
function Install-Requirements {
    $venvActivate = ".\venv\Scripts\Activate.ps1"
    if (-not (Test-Path $venvActivate)) {
        Write-Host "❌ Virtual environment activation script not found."
        exit 1
    }

    Write-Host "📦 Installing Python dependencies from requirements.txt..."
    & $venvActivate
    pip install --upgrade pip
    pip install -r requirements.txt
    Write-Host "✅ Python dependencies installed."
    deactivate
}

# Function to create config.yaml from config_default.yaml
function Create-Config {
    Copy-Item $DefaultConfig -Destination $UserConfig -Force
    Write-Host "`n✅ Created '$UserConfig' from '$DefaultConfig'."
}

# Function to generate .env file from dashboard env_default.yaml
function Generate-DashboardEnv {
    Write-Host "🔄 Generating '.env' file in '$DashboardDir' from '$DashboardDefaultConfig'..."

    $dashboardEnvFile = Join-Path $DashboardDir ".env"
    if (Test-Path $dashboardEnvFile) {
        Write-Host "⚠️  .env file '$dashboardEnvFile' already exists."
        Write-Host "Do you want to overwrite it with default values?"
        Write-Host "⚠️  Warning: This will overwrite your current .env file and cannot be undone."
        $choice = Read-Host "Type 'yes' to overwrite or 'no' to keep your existing .env file [yes/no]"
        switch ($choice.ToLower()) {
            'yes' { }
            'no' {
                Write-Host "👍 Keeping existing .env file '$dashboardEnvFile'."
                return
            }
            default {
                Write-Host "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
                exit 1
            }
        }
    }

    # Ensure the PowerShell-Yaml module is installed
    if (-not (Get-Module -ListAvailable -Name powershell-yaml)) {
        Write-Host "ℹ️  Installing 'powershell-yaml' module..."
        Install-Module -Name powershell-yaml -Scope CurrentUser -Force
    }

    Import-Module powershell-yaml
    $config = Import-Yaml -Path $DashboardDefaultConfig
    $envData = @()
    foreach ($key in $config.Keys) {
        $value = $config[$key]
        $envData += "$key=$value"
    }
    $envData | Out-File -FilePath $dashboardEnvFile -Encoding UTF8
    Write-Host "✅ Generated '.env' file."
}

# Main script starts here
Display-Banner

# Check Python version
Check-PythonVersion

# Create virtual environment if not exists
Create-VirtualEnv

# Install requirements
Install-Requirements

# Define directories and config files
$BaseDir = Get-Location
$ConfigDir = Join-Path $BaseDir "configs"
$DefaultConfig = Join-Path $ConfigDir "config_default.yaml"
$UserConfig = Join-Path $ConfigDir "config.yaml"

# Inform the user about the base directory
Write-Host "`nUsing base directory: '$BaseDir'"

# Check if configs directory exists
if (-not (Test-Path $ConfigDir)) {
    Write-Host "🗂  Configuration directory '$ConfigDir' does not exist. Creating it now..."
    New-Item -Path $ConfigDir -ItemType Directory | Out-Null
    Write-Host "✅ Directory '$ConfigDir' created."
}

# Check if config_default.yaml exists
if (-not (Test-Path $DefaultConfig)) {
    Write-Host "❌ Error: Default configuration file '$DefaultConfig' not found."
    Write-Host "Please ensure that '$DefaultConfig' exists in the '$ConfigDir' directory."
    exit 1
}

# Check if config.yaml exists
if (-not (Test-Path $UserConfig)) {
    Write-Host "⚙️  User configuration file '$UserConfig' does not exist."
    Create-Config
} else {
    Write-Host "⚠️  User configuration file '$UserConfig' already exists."
    Write-Host "Do you want to reset it to default values?"
    Write-Host "⚠️  Warning: This will overwrite your current configuration and cannot be undone."
    $choice = Read-Host "Type 'yes' to reset or 'no' to keep your existing configuration [yes/no]"
    switch ($choice.ToLower()) {
        'yes' {
            Create-Config
            Write-Host "✅ Configuration file '$UserConfig' has been reset to default values."
        }
        'no' {
            Write-Host "👍 Keeping existing configuration file '$UserConfig'."
        }
        default {
            Write-Host "❌ Invalid input. Please run the script again and type 'yes' or 'no'."
            exit 1
        }
    }
}

# Handle dashboard configuration
$DashboardDir = Join-Path $BaseDir "dashboard"
$DashboardDefaultConfig = Join-Path $DashboardDir "env_default.yaml"

# Check if dashboard directory exists
if (-not (Test-Path $DashboardDir)) {
    Write-Host "❌ Dashboard directory '$DashboardDir' does not exist."
    Write-Host "Please ensure that '$DashboardDir' exists."
    exit 1
}

# Check if dashboard default config exists
if (-not (Test-Path $DashboardDefaultConfig)) {
    Write-Host "❌ Error: Default dashboard configuration file '$DashboardDefaultConfig' not found."
    Write-Host "Please ensure that '$DashboardDefaultConfig' exists in the '$DashboardDir' directory."
    exit 1
}

# Generate .env file from dashboard env_default.yaml
Generate-DashboardEnv

Write-Host "`n🎉 Initialization complete."
Write-Host "🚀 You can now start using PixEagle. Happy flying!`n"
Write-Host "📢 Note:"
Write-Host "👉 You might need to install Node.js and npm if they are not already installed."
Write-Host "   It's recommended to refer to the official Node.js website and follow the instructions for your operating system:"
Write-Host "   https://nodejs.org/en/download/package-manager/"
Write-Host "👉 Please edit '$UserConfig' and '$DashboardDir\.env' to configure settings according to your system."

# End of script
