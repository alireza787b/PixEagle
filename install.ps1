# ============================================================================
# install.ps1 - PixEagle Bootstrap Installer (Windows PowerShell)
# ============================================================================
# One-liner installation for PixEagle vision-based drone tracking system.
#
# Usage:
#   irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex
#
# Or with custom install directory:
#   $env:PIXEAGLE_HOME = "D:\Projects\PixEagle"; irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex
#
# What this script does:
#   1. Checks system prerequisites (git, python)
#   2. Clones PixEagle repository (or updates if exists)
#   3. Runs the initialization script (scripts\init.bat)
#   4. Displays next steps
#
# Environment variables:
#   PIXEAGLE_HOME    - Installation directory (default: ~\PixEagle)
#   PIXEAGLE_BRANCH  - Git branch to clone (default: main)
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Ensure we're running in a proper terminal
$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration
# ============================================================================
$RepoUrl = "https://github.com/alireza787b/PixEagle.git"
$DefaultBranch = "main"
$DefaultHome = Join-Path $env:USERPROFILE "PixEagle"

# Use environment variables if set, otherwise use defaults
$InstallDir = if ($env:PIXEAGLE_HOME) { $env:PIXEAGLE_HOME } else { $DefaultHome }
$Branch = if ($env:PIXEAGLE_BRANCH) { $env:PIXEAGLE_BRANCH } else { $DefaultBranch }

# ============================================================================
# Functions
# ============================================================================

function Write-Banner {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "  _____ _      ______            _       " -ForegroundColor Cyan
    Write-Host " |  __ (_)    |  ____|          | |      " -ForegroundColor Cyan
    Write-Host " | |__) |__  _| |__   __ _  __ _| | ___  " -ForegroundColor Cyan
    Write-Host " |  ___/ \ \/ /  __| / _`` |/ _`` | |/ _ \ " -ForegroundColor Cyan
    Write-Host " | |   | |>  <| |___| (_| | (_| | |  __/ " -ForegroundColor Cyan
    Write-Host " |_|   |_/_/\_\______\__,_|\__, |_|\___| " -ForegroundColor Cyan
    Write-Host "                           __/ |        " -ForegroundColor Cyan
    Write-Host "                          |___/         " -ForegroundColor Cyan
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "          PixEagle Bootstrap Installer (Windows)" -ForegroundColor White
    Write-Host "          Vision-Based Drone Tracking System" -ForegroundColor Gray
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "   [*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "   [X] $Message" -ForegroundColor Red
}

function Write-Warning {
    param([string]$Message)
    Write-Host "   [!] $Message" -ForegroundColor Yellow
}

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    $missing = @()

    # Check git
    try {
        $gitVersion = git --version 2>$null
        if ($gitVersion) {
            Write-Success "git $($gitVersion -replace 'git version ', '')"
        } else {
            $missing += "git"
        }
    } catch {
        $missing += "git"
    }

    # Check Python
    try {
        $pythonVersion = python --version 2>$null
        if ($pythonVersion) {
            Write-Success "python $($pythonVersion -replace 'Python ', '')"
        } else {
            $missing += "python"
        }
    } catch {
        $missing += "python"
    }

    # Check Node.js (optional but recommended)
    try {
        $nodeVersion = node --version 2>$null
        if ($nodeVersion) {
            Write-Success "node $nodeVersion"
        } else {
            Write-Warning "Node.js not found (needed for dashboard)"
        }
    } catch {
        Write-Warning "Node.js not found (needed for dashboard)"
    }

    # Report missing prerequisites
    if ($missing.Count -gt 0) {
        Write-Host ""
        Write-Error "Missing prerequisites: $($missing -join ', ')"
        Write-Host ""
        Write-Host "   Please install the missing prerequisites:"
        Write-Host ""
        if ($missing -contains "git") {
            Write-Host "   Git: https://git-scm.com/download/win" -ForegroundColor Cyan
        }
        if ($missing -contains "python") {
            Write-Host "   Python: https://www.python.org/downloads/" -ForegroundColor Cyan
        }
        Write-Host ""
        Write-Host "   After installation, restart PowerShell and run this script again."
        Write-Host ""
        exit 1
    }
}

function Install-OrUpdate {
    Write-Info "Installing to: $InstallDir"

    $gitDir = Join-Path $InstallDir ".git"

    if (Test-Path $gitDir) {
        # Existing installation - update
        Write-Warning "Existing installation found"
        Write-Host ""
        $response = Read-Host "   Update existing installation? [Y/n]"

        if ([string]::IsNullOrEmpty($response) -or $response -match "^[Yy]") {
            Write-Info "Updating repository..."
            Push-Location $InstallDir

            try {
                # Check for local changes
                $status = git status --porcelain 2>$null
                if ($status) {
                    Write-Warning "Stashing local changes..."
                    git stash push -m "Pre-update stash $(Get-Date -Format 'yyyyMMdd_HHmmss')"
                }

                git fetch origin
                git checkout $Branch
                git pull origin $Branch
                Write-Success "Repository updated"
            } finally {
                Pop-Location
            }
        } else {
            Write-Info "Skipping update"
        }
    } else {
        # Fresh installation
        if (Test-Path $InstallDir) {
            Write-Error "Directory exists but is not a git repository: $InstallDir"
            Write-Host ""
            Write-Host "   Please remove or rename the existing directory:"
            Write-Host "   Remove-Item -Recurse -Force '$InstallDir'" -ForegroundColor Cyan
            Write-Host ""
            exit 1
        }

        Write-Info "Cloning repository (branch: $Branch)..."

        # Create parent directory if needed
        $parentDir = Split-Path $InstallDir -Parent
        if (-not (Test-Path $parentDir)) {
            New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
        }

        # Clone with shallow depth for faster download
        git clone --depth 1 --branch $Branch $RepoUrl $InstallDir

        Write-Success "Repository cloned"
    }
}

function Start-Initialization {
    Write-Info "Running initialization script..."
    Write-Host ""

    Push-Location $InstallDir

    try {
        $initScript = Join-Path $InstallDir "scripts\init.bat"
        $legacyInitScript = Join-Path $InstallDir "init_pixeagle.bat"

        if (Test-Path $initScript) {
            & cmd /c $initScript
        } elseif (Test-Path $legacyInitScript) {
            # Fallback to old location
            & cmd /c $legacyInitScript
        } else {
            Write-Error "Initialization script not found"
            exit 1
        }
    } finally {
        Pop-Location
    }
}

function Show-Success {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "                    [OK] Installation Complete!" -ForegroundColor Green
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   PixEagle has been installed to: " -NoNewline
    Write-Host "$InstallDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Next Steps:" -ForegroundColor White
    Write-Host "   1. " -NoNewline
    Write-Host "cd $InstallDir" -ForegroundColor Cyan
    Write-Host "   2. Edit " -NoNewline
    Write-Host "configs\config.yaml" -ForegroundColor Cyan -NoNewline
    Write-Host " for your setup"
    Write-Host "   3. " -NoNewline
    Write-Host "scripts\run.bat" -ForegroundColor Cyan -NoNewline
    Write-Host " to start all services"
    Write-Host ""
    Write-Host "   Quick Commands:" -ForegroundColor White
    Write-Host "   " -NoNewline
    Write-Host "scripts\run.bat" -ForegroundColor Cyan -NoNewline
    Write-Host "        - Run all services"
    Write-Host "   " -NoNewline
    Write-Host "scripts\run.bat --dev" -ForegroundColor Cyan -NoNewline
    Write-Host "  - Run in development mode"
    Write-Host "   " -NoNewline
    Write-Host "scripts\stop.bat" -ForegroundColor Cyan -NoNewline
    Write-Host "       - Stop all services"
    Write-Host ""
    Write-Host "   Documentation:" -ForegroundColor White
    Write-Host "   https://github.com/alireza787b/PixEagle" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================================
# Main
# ============================================================================

function Main {
    Write-Banner

    Write-Host "Starting PixEagle installation..." -ForegroundColor White
    Write-Host ""

    Test-Prerequisites
    Install-OrUpdate
    Start-Initialization
    Show-Success
}

Main
