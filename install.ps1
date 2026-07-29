# ============================================================================
# install.ps1 - PixEagle Bootstrap Installer (Windows PowerShell)
# ============================================================================
# One-line bootstrap for the native Windows x64 Core local-lab preview.
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
#   3. Reconciles the Core runtime and dashboard (scripts\init.bat)
#   4. Displays next steps
#
# Environment variables:
#   PIXEAGLE_HOME                   - Installation directory (default: ~\PixEagle)
#   PIXEAGLE_BRANCH                 - Git branch to clone (default: main)
#   PIXEAGLE_WINDOWS_NONINTERACTIVE - CI/automation only; selects setup defaults
#   PIXEAGLE_WINDOWS_SKIP_SOURCE_UPDATE - CI only; use the existing checkout
#
# Project: PixEagle
# Repository: https://github.com/alireza787b/PixEagle
# ============================================================================

# Ensure we're running in a proper terminal
$ErrorActionPreference = "Stop"

if ($env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS -ne "1") {
    Write-Host "[ERROR] Native Windows bootstrap is experimental and not parity-verified." -ForegroundColor Red
    Write-Host "        Use the maintained Linux installer through WSL for normal setup."
    Write-Host "        Contributors may opt in with `$env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS = '1'."
    throw "PixEagle native Windows preview requires explicit opt-in"
}

# ============================================================================
# Configuration
# ============================================================================
$RepoUrl = "https://github.com/alireza787b/PixEagle.git"
$DefaultBranch = "main"
$DefaultHome = Join-Path $env:USERPROFILE "PixEagle"

# Use environment variables if set, otherwise use defaults
$InstallDir = if ($env:PIXEAGLE_HOME) { $env:PIXEAGLE_HOME } else { $DefaultHome }
$Branch = if ($env:PIXEAGLE_BRANCH) { $env:PIXEAGLE_BRANCH } else { $DefaultBranch }
$StagedConfigRelative = "configs\.config_default_preupdate.yaml"
$NonInteractive = $env:PIXEAGLE_WINDOWS_NONINTERACTIVE -eq "1"
$SkipSourceUpdate = $env:PIXEAGLE_WINDOWS_SKIP_SOURCE_UPDATE -eq "1"

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
    Write-Host "          PixEagle Windows x64 Core Preview" -ForegroundColor White
    Write-Host "          Local bundled-video lab runtime" -ForegroundColor Gray
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

function Enter-BootstrapLock {
    $normalized = [System.IO.Path]::GetFullPath($InstallDir).ToLowerInvariant()
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($normalized))
    } finally {
        $sha.Dispose()
    }
    $name = ([System.BitConverter]::ToString($digest)).Replace("-", "").ToLowerInvariant()
    $path = Join-Path ([System.IO.Path]::GetTempPath()) "pixeagle-windows-$name.lock"
    try {
        return [System.IO.File]::Open(
            $path,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch [System.IO.IOException] {
        throw "Another PixEagle Windows bootstrap/update owns this installation"
    }
}

function Set-OwnerOnlyFileAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if (-not $currentSid) {
        throw "Could not resolve the current Windows user SID"
    }

    $acl = [System.Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($currentSid)
    $acl.SetAccessRuleProtection($true, $false)
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $currentSid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop

    $verifiedAcl = Get-Acl -LiteralPath $Path -ErrorAction Stop
    $verifiedOwnerSid = $verifiedAcl.GetOwner(
        [System.Security.Principal.SecurityIdentifier]
    )
    $rules = @($verifiedAcl.GetAccessRules(
        $true,
        $true,
        [System.Security.Principal.SecurityIdentifier]
    ))
    if ($verifiedOwnerSid.Value -ne $currentSid.Value -or
        $rules.Count -ne 1 -or
        $rules[0].IdentityReference.Value -ne $currentSid.Value) {
        throw "Could not verify an owner-only ACL"
    }
}

function Test-RegularFileNoReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.File]::Exists($Path)) { return $false }
    $item = Get-Item -LiteralPath $Path -Force
    return (-not $item.PSIsContainer) -and
        (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) -and
        ($item.Length -gt 0)
}

function Test-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        Get-Item -LiteralPath $Path -Force -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-SupportedPythonInvocation {
    $probe = @'
import platform
import struct
import sys
supported_version = sys.version_info[:2] in {(3, 11), (3, 12)}
supported_arch = (
    platform.machine().strip().lower() in {"amd64", "x86_64"}
    and struct.calcsize("P") * 8 == 64
)
raise SystemExit(0 if supported_version and supported_arch else 1)
'@
    $candidates = @(
        [pscustomobject]@{ Command = "py.exe"; Prefix = @("-3.12") },
        [pscustomobject]@{ Command = "py.exe"; Prefix = @("-3.11") },
        [pscustomobject]@{ Command = "python.exe"; Prefix = @() }
    )

    foreach ($candidate in $candidates) {
        $resolved = Get-Command $candidate.Command -CommandType Application -ErrorAction SilentlyContinue
        if (-not $resolved) { continue }

        $probeArgs = @($candidate.Prefix) + @("-c", $probe)
        & $resolved.Source @probeArgs *> $null
        if ($LASTEXITCODE -ne 0) { continue }

        $versionArgs = @($candidate.Prefix) + @("--version")
        $version = (& $resolved.Source @versionArgs 2>&1 | Out-String).Trim()
        return [pscustomobject]@{
            Executable = $resolved.Source
            Prefix = @($candidate.Prefix)
            Version = $version
        }
    }

    return $null
}

function Get-PixEagleVenvPython {
    if ($env:PIXEAGLE_VENV_DIR) {
        $venvDir = if ([System.IO.Path]::IsPathRooted($env:PIXEAGLE_VENV_DIR)) {
            $env:PIXEAGLE_VENV_DIR
        } else {
            Join-Path $InstallDir $env:PIXEAGLE_VENV_DIR
        }
    } elseif (Test-Path -LiteralPath (Join-Path $InstallDir ".venv\Scripts\python.exe")) {
        $venvDir = Join-Path $InstallDir ".venv"
    } elseif (Test-Path -LiteralPath (Join-Path $InstallDir "venv\Scripts\python.exe")) {
        $venvDir = Join-Path $InstallDir "venv"
    } else {
        $venvDir = Join-Path $InstallDir ".venv"
    }
    return Join-Path $venvDir "Scripts\python.exe"
}

function Test-StagedDefaultsContent {
    param([Parameter(Mandatory = $true)][string]$Path)

    $python = Get-PixEagleVenvPython
    $pythonPrefix = @()
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        $pythonInvocation = Get-SupportedPythonInvocation
        if (-not $pythonInvocation) {
            throw "CPython 3.11 or 3.12 x64 is unavailable for staged defaults validation"
        }
        $python = $pythonInvocation.Executable
        $pythonPrefix = @($pythonInvocation.Prefix)
    }
    $validationScript = @'
import pathlib
import sys
import yaml

value = yaml.safe_load(pathlib.Path(sys.argv[1]).read_bytes())
if not isinstance(value, dict) or not value:
    raise SystemExit("staged defaults must contain a non-empty YAML mapping")
'@
    $validationArgs = $pythonPrefix + @("-c", $validationScript, $Path)
    & $python @validationArgs
    if ($LASTEXITCODE -ne 0) {
        throw "staged defaults failed YAML integrity validation"
    }
}

function Stage-PreUpdateDefaults {
    $sourcePath = Join-Path $InstallDir "configs\config_default.yaml"
    $stagedPath = Join-Path $InstallDir $StagedConfigRelative
    $tempPath = $null

    try {
        if (-not (Test-RegularFileNoReparsePoint -Path $sourcePath)) {
            throw "configs\config_default.yaml is not a non-empty regular file"
        }

        if (Test-PathEntry -Path $stagedPath) {
            if (-not (Test-RegularFileNoReparsePoint -Path $stagedPath)) {
                throw "pending pre-update defaults are not a regular file"
            }
            Set-OwnerOnlyFileAcl -Path $stagedPath
            Test-StagedDefaultsContent -Path $stagedPath
            Write-Info "Keeping the pending pre-update defaults baseline"
            return $true
        }

        $tempPath = "$stagedPath.tmp.$PID.$([guid]::NewGuid().ToString('N'))"
        [System.IO.File]::Copy($sourcePath, $tempPath, $false)
        Set-OwnerOnlyFileAcl -Path $tempPath
        if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne
            (Get-FileHash -LiteralPath $tempPath -Algorithm SHA256).Hash) {
            throw "the staged defaults copy did not verify"
        }
        Test-StagedDefaultsContent -Path $tempPath

        # Move within the same directory publishes the file atomically and
        # refuses to replace a baseline created concurrently.
        [System.IO.File]::Move($tempPath, $stagedPath)
        $tempPath = $null
        Set-OwnerOnlyFileAcl -Path $stagedPath
        Write-Success "Pre-update config defaults preserved"
        return $true
    } catch {
        Write-Error "Could not preserve pre-update defaults: $($_.Exception.Message)"
        return $false
    } finally {
        if ($tempPath -and [System.IO.File]::Exists($tempPath)) {
            Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
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

    # Accept the standard Python launcher or a supported python.exe on PATH.
    $pythonInvocation = Get-SupportedPythonInvocation
    if ($pythonInvocation) {
        Write-Success "$($pythonInvocation.Version) x64"
    } else {
        $missing += "python"
    }

    # Node.js is part of the Core dashboard contract.
    try {
        $nodeVersion = node --version 2>$null
        if ($nodeVersion) {
            Write-Success "node $nodeVersion"
        } else {
            $missing += "node"
        }
    } catch {
        $missing += "node"
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
        if ($missing -contains "node") {
            Write-Host "   Node.js 24: https://nodejs.org/en/download" -ForegroundColor Cyan
        }
        Write-Host ""
        Write-Host "   After installation, restart PowerShell and run this script again."
        Write-Host ""
        throw "Missing Windows Core preview prerequisites: $($missing -join ', ')"
    }
}

function Stop-OwnedRuntimeForUpdate {
    $python = Get-PixEagleVenvPython
    $controller = Join-Path $InstallDir "scripts\windows\runtime.py"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
        -not (Test-Path -LiteralPath $controller -PathType Leaf)) {
        return
    }

    & $python $controller status --quiet *> $null
    $statusExitCode = $LASTEXITCODE
    if ($statusExitCode -eq 3) {
        return
    }
    if ($statusExitCode -notin @(0, 4)) {
        throw "The existing Windows runtime receipt could not be validated"
    }

    Write-Warning "An exact receipt-owned PixEagle runtime is active"
    $response = Read-Host "   Stop it before update? [Y/n]"
    if (-not ([string]::IsNullOrEmpty($response) -or $response -match "^[Yy]")) {
        throw "Update requires a stopped runtime; no source changes were made"
    }
    & $python $controller stop
    if ($LASTEXITCODE -ne 0) {
        throw "The exact receipt-owned runtime did not stop cleanly"
    }
    Write-Success "Owned Windows runtime stopped"
}

function Assert-NoWindowsRuntimeReceipt {
    $statePath = Join-Path $InstallDir ".pixeagle_runtime\windows\runtime.json"
    if (Test-PathEntry -Path $statePath) {
        throw (
            "A Windows runtime became active before source update. " +
            "No source changes were made; stop it and retry."
        )
    }
}

function Install-OrUpdate {
    Write-Info "Installing to: $InstallDir"

    $gitDir = Join-Path $InstallDir ".git"

    if (Test-Path $gitDir) {
        # Existing installation - update
        Push-Location $InstallDir

        try {
            # Get current version info
            $currentCommit = git rev-parse --short HEAD 2>$null
            if (-not $currentCommit) { $currentCommit = "unknown" }
            $currentBranch = git branch --show-current 2>$null
            if (-not $currentBranch) { $currentBranch = "unknown" }

            Write-Host ""
            Write-Warning "Existing installation found"
            Write-Host "      Current: " -NoNewline
            Write-Host "$currentBranch" -ForegroundColor Cyan -NoNewline
            Write-Host " @ " -NoNewline
            Write-Host "$currentCommit" -ForegroundColor Cyan
            Write-Host ""

            # Check for local changes. Existing installs must be clean before
            # the installer updates them.
            $rawStatus = @(git status --porcelain --untracked-files=all 2>$null)
            $statusExitCode = $LASTEXITCODE
            if ($statusExitCode -ne 0) {
                Write-Error "Cannot inspect the existing checkout; refusing automatic update"
                Write-Host ""
                Write-Host "   Repair repository ownership/integrity and confirm git status succeeds."
                Write-Host ""
                throw "Cannot inspect the existing checkout"
            }
            $status = @(
                $rawStatus |
                    Where-Object { $_ -ne "?? $($StagedConfigRelative -replace '\\', '/')" }
            )
            if ($status) {
                Write-Warning "Local changes detected:"
                $staged = git diff --cached --name-only 2>$null
                $unstaged = git diff --name-only 2>$null
                $untracked = @(
                    git ls-files --others --exclude-standard 2>$null |
                        Where-Object { $_ -ne ($StagedConfigRelative -replace '\\', '/') }
                )

                if ($staged) { Write-Host "      " -NoNewline; Write-Host "* Staged changes" -ForegroundColor Yellow }
                if ($unstaged) { Write-Host "      " -NoNewline; Write-Host "* Unstaged changes" -ForegroundColor Yellow }
                if ($untracked) { Write-Host "      " -NoNewline; Write-Host "* Untracked files" -ForegroundColor Yellow }
                Write-Host ""
            }

            if ($SkipSourceUpdate) {
                $response = "n"
                Write-Info "Source update skipped by the automation contract"
            } elseif ($NonInteractive) {
                $response = "y"
                Write-Info "Noninteractive update selected"
            } else {
                $response = Read-Host "   Update to latest version? [Y/n]"
            }

            if ([string]::IsNullOrEmpty($response) -or $response -match "^[Yy]") {
                Write-Info "Updating repository..."

                if ($status) {
                    Write-Error "Existing checkout has local changes; refusing automatic update"
                    Write-Host ""
                    Write-Host "   Commit or stash manually, then rerun the installer."
                    Write-Host ""
                    throw "Existing checkout has local changes"
                }

                if ($currentBranch -ne $Branch) {
                    Write-Error "Current branch '$currentBranch' does not match requested branch '$Branch'"
                    Write-Host ""
                    Write-Host "   Checkout the target branch manually, then rerun:"
                    Write-Host "   cd $InstallDir; git checkout $Branch" -ForegroundColor Cyan
                    Write-Host ""
                    throw "Existing checkout is on a different branch"
                }

                Stop-OwnedRuntimeForUpdate

                $sourceLock = $null
                try {
                    $sourceLock = Enter-BootstrapLock
                    Assert-NoWindowsRuntimeReceipt

                    Write-Info "Preserving the current config defaults before update..."
                    if (-not (Stage-PreUpdateDefaults)) {
                        Write-Error "Update stopped before changing the source checkout"
                        throw "Could not preserve pre-update defaults"
                    }

                    # Fetch latest
                    Write-Info "Fetching latest changes..."
                    git fetch --prune origin "+refs/heads/${Branch}:refs/remotes/origin/${Branch}"
                    if ($LASTEXITCODE -ne 0) {
                        Write-Error "Fetch failed for origin/$Branch; no update was attempted"
                        throw "Git fetch failed"
                    }
                    git rev-parse --verify "origin/$Branch^{commit}" *> $null
                    if ($LASTEXITCODE -ne 0) {
                        Write-Error "Fetched ref is not available: origin/$Branch"
                        throw "Fetched branch ref is invalid"
                    }

                    # Get remote version info
                    $remoteCommit = git rev-parse --short "origin/$Branch" 2>$null
                    if (-not $remoteCommit) { $remoteCommit = "unknown" }

                    if ($currentCommit -eq $remoteCommit) {
                        Write-Success "Already up to date ($currentCommit)"
                    } else {
                        Write-Host "      Updating: " -NoNewline
                        Write-Host "$currentCommit" -ForegroundColor Cyan -NoNewline
                        Write-Host " -> " -NoNewline
                        Write-Host "$remoteCommit" -ForegroundColor Cyan

                        git merge --ff-only "origin/$Branch"
                        if ($LASTEXITCODE -ne 0) {
                            Write-Error "Fast-forward update was not possible; no merge or reset was attempted"
                            Write-Host ""
                            Write-Host "   Inspect and resolve manually:"
                            Write-Host "   cd $InstallDir; git log --oneline --graph --decorate HEAD origin/$Branch" -ForegroundColor Cyan
                            Write-Host ""
                            throw "Fast-forward update was not possible"
                        }

                        Write-Success "Repository updated to $remoteCommit"
                    }
                } finally {
                    if ($sourceLock) {
                        $sourceLock.Dispose()
                    }
                }
            } else {
                Write-Info "Skipping update - using existing version"
            }
        } finally {
            Pop-Location
        }
    } else {
        # Fresh installation
        $sourceLock = $null
        try {
            $sourceLock = Enter-BootstrapLock
            if (Test-Path $InstallDir) {
                Write-Error "Directory exists but is not a git repository: $InstallDir"
                Write-Host ""
                Write-Host "   Options:"
                Write-Host "   1. Remove it:  " -NoNewline
                Write-Host "Remove-Item -Recurse -Force '$InstallDir'" -ForegroundColor Cyan
                Write-Host "   2. Rename it:  " -NoNewline
                Write-Host "Rename-Item '$InstallDir' '${InstallDir}.backup'" -ForegroundColor Cyan
                Write-Host ""
                throw "Install directory exists but is not a Git checkout"
            }

            Write-Info "Cloning repository (branch: $Branch)..."

            # Create parent directory if needed
            $parentDir = Split-Path $InstallDir -Parent
            if (-not (Test-Path $parentDir)) {
                New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
            }

            # Clone with shallow depth for faster download
            git clone --depth 1 --branch $Branch $RepoUrl $InstallDir
            if ($LASTEXITCODE -ne 0) {
                Write-Error "Repository clone failed; setup was not started"
                throw "Repository clone failed"
            }

            Push-Location $InstallDir
            $newCommit = git rev-parse --short HEAD 2>$null
            $revParseExitCode = $LASTEXITCODE
            Pop-Location
            if ($revParseExitCode -ne 0 -or -not $newCommit) {
                Write-Error "Cloned source could not be verified as a Git commit"
                throw "Cloned source verification failed"
            }

            Write-Success "Repository cloned ($newCommit)"
        } finally {
            if ($sourceLock) {
                $sourceLock.Dispose()
            }
        }
    }
}

function Start-Initialization {
    Write-Info "Running initialization script..."
    Write-Host ""

    Push-Location $InstallDir

    $initExitCode = 0
    try {
        $initScript = Join-Path $InstallDir "scripts\init.bat"

        if (Test-Path $initScript) {
            $initCommand = "`"$initScript`""
            if ($NonInteractive) {
                $initCommand += " --non-interactive --without-sidecars"
            }
            & $env:COMSPEC /d /s /c $initCommand
            $initExitCode = $LASTEXITCODE
        } else {
            Write-Error "Canonical initialization script not found: $initScript"
            throw "Canonical Windows initialization script not found"
        }
    } finally {
        Pop-Location
    }

    if ($initExitCode -ne 0) {
        Write-Error "Initialization reported a failure (exit $initExitCode)"
        throw "Windows Core initialization failed"
    }
    $stagedPath = Join-Path $InstallDir $StagedConfigRelative
    if (Test-PathEntry -Path $stagedPath) {
        Write-Error "Configuration update baseline is still pending after initialization"
        Write-Host "   Re-run scripts\init.bat; the preserved baseline was not deleted."
        throw "Configuration update baseline remains pending"
    }
}

function Show-Success {
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host "                  [OK] Core Setup Complete" -ForegroundColor Green
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   PixEagle has been installed to: " -NoNewline
    Write-Host "$InstallDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Next Steps:" -ForegroundColor White
    Write-Host "   1. " -NoNewline
    Write-Host "cd $InstallDir" -ForegroundColor Cyan
    Write-Host "   2. " -NoNewline
    Write-Host "scripts\run.bat" -ForegroundColor Cyan -NoNewline
    Write-Host " to start the local Core lab"
    Write-Host "   3. Open http://127.0.0.1:3040"
    Write-Host "      Sign in with the dashboard account selected during setup."
    Write-Host ""
    Write-Host "   Quick Commands:" -ForegroundColor White
    Write-Host "   " -NoNewline
    Write-Host "scripts\run.bat" -ForegroundColor Cyan -NoNewline
    Write-Host "        - Start and prove backend/dashboard readiness"
    Write-Host "   " -NoNewline
    Write-Host "scripts\status.bat" -ForegroundColor Cyan -NoNewline
    Write-Host "     - Verify exact owned processes"
    Write-Host "   " -NoNewline
    Write-Host "scripts\stop.bat" -ForegroundColor Cyan -NoNewline
    Write-Host "       - Stop only receipt-owned processes"
    Write-Host ""
    Write-Host "   Documentation:" -ForegroundColor White
    Write-Host "   docs\WINDOWS_SETUP.md" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "========================================================================" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================================
# Main
# ============================================================================

function Main {
    Write-Banner

    Write-Host "Starting PixEagle Windows Core preview setup..." -ForegroundColor White
    Write-Host ""

    Test-Prerequisites
    Install-OrUpdate
    Start-Initialization
    Show-Success
}

Main
