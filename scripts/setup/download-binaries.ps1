#requires -Version 5.1

<#
.SYNOPSIS
Downloads manifest-pinned PixEagle companion binaries on native Windows x64.

.DESCRIPTION
This is the canonical native-Windows binary download transaction. It reads
scripts/setup/binary-manifest.env, stages each download in bin/ under a unique
name, verifies SHA-256 and the x64 PE structure, and atomically publishes only
when the final path is absent.

Native Windows support remains experimental. Set
PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1 before running this script.
#>

[CmdletBinding()]
param(
    [switch]$All,
    [switch]$Mavsdk,
    [Alias("M2r")]
    [switch]$Mavlink2rest,
    [switch]$DryRun,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:PlatformKey = "WINDOWS_X86_64"
$script:MinimumPeLength = 128
$script:PeMachineAmd64 = 0x8664
$script:Pe32PlusMagic = 0x020B

function Write-Info {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "   [*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "   [OK] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "   [!] $Message" -ForegroundColor Yellow
}

function Show-Usage {
    Write-Host @"
PixEagle Binary Downloader (experimental native Windows x64)

Usage:
  powershell -NoProfile -File scripts\setup\download-binaries.ps1 [-All | -Mavsdk | -Mavlink2rest] [-DryRun]
  scripts\setup\download-binaries.bat [--all | --mavsdk | --mavlink2rest] [--dry-run]

No selection downloads both binaries. Dry-run reads the manifest and prints the
plan without creating directories, locks, temporary files, or provenance.
"@
}

function Test-PathEntry {
    param([Parameter(Mandatory = $true)][string]$Path)

    try {
        Get-Item -LiteralPath $Path -Force -ErrorAction Stop | Out-Null
        return $true
    } catch [System.Management.Automation.ItemNotFoundException] {
        return $false
    }
}

function Assert-RegularFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Purpose,
        [switch]$AllowEmpty
    )

    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer) {
        throw "$Purpose is a directory, not a regular file: $Path"
    }
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Purpose must not be a reparse point: $Path"
    }
    if (-not $AllowEmpty -and $item.Length -le 0) {
        throw "$Purpose is empty: $Path"
    }
}

function Assert-SafeDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-PathEntry -Path $Path) {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (-not $item.PSIsContainer) {
            throw "Binary output path is not a directory: $Path"
        }
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Binary output directory must not be a reparse point: $Path"
        }
        return
    }

    [System.IO.Directory]::CreateDirectory($Path) | Out-Null
    $created = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (-not $created.PSIsContainer -or
        ($created.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Could not create a regular binary output directory: $Path"
    }
}

function Read-BinaryManifest {
    param([Parameter(Mandatory = $true)][string]$Path)

    Assert-RegularFile -Path $Path -Purpose "Binary manifest"
    $values = @{}
    $lineNumber = 0

    foreach ($rawLine in [System.IO.File]::ReadAllLines($Path)) {
        $lineNumber += 1
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $separator = $line.IndexOf("=")
        if ($separator -le 0) {
            throw "Invalid manifest assignment at ${Path}:$lineNumber"
        }

        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($key -notmatch "^[A-Z][A-Z0-9_]*$") {
            throw "Invalid manifest key '$key' at ${Path}:$lineNumber"
        }
        if ($values.ContainsKey($key)) {
            throw "Duplicate manifest key '$key' at ${Path}:$lineNumber"
        }
        if (-not $value) {
            throw "Empty manifest value for '$key' at ${Path}:$lineNumber"
        }
        $values[$key] = $value
    }

    return $values
}

function Get-RequiredManifestValue {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Manifest,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if (-not $Manifest.ContainsKey($Key) -or -not $Manifest[$Key]) {
        throw "Binary manifest is missing required key: $Key"
    }
    return [string]$Manifest[$Key]
}

function Assert-HttpsUri {
    param(
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][string]$Purpose
    )

    [System.Uri]$uri = $null
    if (-not [System.Uri]::TryCreate(
        $Value,
        [System.UriKind]::Absolute,
        [ref]$uri
    )) {
        throw "$Purpose is not an absolute URI: $Value"
    }
    if ($uri.Scheme -ne [System.Uri]::UriSchemeHttps) {
        throw "$Purpose must use HTTPS: $Value"
    }
    if (-not $uri.Host -or $uri.UserInfo) {
        throw "$Purpose contains an invalid host or embedded credentials: $Value"
    }
    return $uri
}

function New-DownloadSpec {
    param(
        [Parameter(Mandatory = $true)][hashtable]$Manifest,
        [Parameter(Mandatory = $true)][string]$Prefix,
        [Parameter(Mandatory = $true)][string]$Component,
        [Parameter(Mandatory = $true)][string]$OutputName,
        [Parameter(Mandatory = $true)][string]$BinDirectory
    )

    $version = Get-RequiredManifestValue -Manifest $Manifest -Key "${Prefix}_VERSION"
    $baseUrl = Get-RequiredManifestValue -Manifest $Manifest -Key "${Prefix}_BASE_URL"
    $releaseUrl = Get-RequiredManifestValue -Manifest $Manifest -Key "${Prefix}_RELEASE_URL"
    $assetKey = "{0}_ASSET_{1}" -f $Prefix, $script:PlatformKey
    $shaKey = "{0}_SHA256_{1}" -f $Prefix, $script:PlatformKey
    $asset = Get-RequiredManifestValue -Manifest $Manifest -Key $assetKey
    $expectedSha = (
        Get-RequiredManifestValue -Manifest $Manifest -Key $shaKey
    ).ToLowerInvariant()

    if ($expectedSha -notmatch "^[0-9a-f]{64}$") {
        throw "Manifest SHA-256 for $Component must contain exactly 64 hexadecimal characters"
    }
    if (-not $asset.EndsWith(".exe", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Manifest asset for $Component is not a Windows executable: $asset"
    }
    if ([System.IO.Path]::GetFileName($asset) -ne $asset) {
        throw "Manifest asset for $Component must be a filename, not a path: $asset"
    }

    $downloadUrl = "{0}/{1}/{2}" -f (
        $baseUrl.TrimEnd("/")
    ), [System.Uri]::EscapeDataString($version), [System.Uri]::EscapeDataString($asset)
    $downloadUri = Assert-HttpsUri -Value $downloadUrl -Purpose "$Component download URL"
    $releaseUri = Assert-HttpsUri -Value $releaseUrl -Purpose "$Component release URL"

    return [pscustomobject]@{
        Component = $Component
        Version = $version
        ReleaseUrl = $releaseUri.AbsoluteUri
        Asset = $asset
        DownloadUri = $downloadUri
        ExpectedSha256 = $expectedSha
        OutputName = $OutputName
        OutputPath = [System.IO.Path]::GetFullPath(
            (Join-Path $BinDirectory $OutputName)
        )
    }
}

function Assert-NativeWindowsX64 {
    if ($env:OS -ne "Windows_NT") {
        throw "This downloader supports native Windows only"
    }

    try {
        $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    } catch {
        throw "Could not determine the Windows operating-system architecture"
    }

    if ($architecture.ToString() -ne "X64") {
        throw "Native Windows $architecture is not supported in this milestone; Windows x64 is required"
    }
}

function Assert-ExperimentalWindowsGate {
    if ($env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS -ne "1") {
        throw (
            "Native Windows support is experimental. Set " +
            "PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1 to opt in."
        )
    }
}

function Assert-X64PeImage {
    param([Parameter(Mandatory = $true)][string]$Path)

    Assert-RegularFile -Path $Path -Purpose "Executable candidate"
    $stream = $null
    $reader = $null

    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        if ($stream.Length -lt $script:MinimumPeLength) {
            throw "Executable candidate is too short to contain valid PE headers: $Path"
        }

        $reader = [System.IO.BinaryReader]::new($stream)
        if ($reader.ReadUInt16() -ne 0x5A4D) {
            throw "Executable candidate does not contain an MZ header: $Path"
        }

        $stream.Position = 0x3C
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0x40 -or $peOffset -gt ($stream.Length - 24)) {
            throw "Executable candidate has an invalid PE header offset: $Path"
        }

        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Executable candidate does not contain a PE signature: $Path"
        }

        $machine = $reader.ReadUInt16()
        $sectionCount = $reader.ReadUInt16()
        if ($machine -ne $script:PeMachineAmd64) {
            throw ("Executable candidate machine 0x{0:X4} is not Windows x64 (0x8664): {1}" -f $machine, $Path)
        }
        if ($sectionCount -le 0) {
            throw "Executable candidate has no PE sections: $Path"
        }

        $stream.Position = $peOffset + 20
        $optionalHeaderSize = $reader.ReadUInt16()
        $characteristics = $reader.ReadUInt16()
        $optionalHeaderStart = $peOffset + 24
        if ($optionalHeaderSize -lt 60 -or
            ($optionalHeaderStart + $optionalHeaderSize) -gt $stream.Length) {
            throw "Executable candidate has an invalid optional PE header: $Path"
        }
        $sectionTableEnd = (
            $optionalHeaderStart + $optionalHeaderSize + (40 * $sectionCount)
        )
        if ($sectionTableEnd -gt $stream.Length) {
            throw "Executable candidate has a truncated PE section table: $Path"
        }
        if (($characteristics -band 0x0002) -eq 0) {
            throw "PE image is not marked executable: $Path"
        }

        $stream.Position = $optionalHeaderStart
        if ($reader.ReadUInt16() -ne $script:Pe32PlusMagic) {
            throw "Executable candidate is not a 64-bit PE32+ image: $Path"
        }

        $stream.Position = $optionalHeaderStart + 56
        if ($reader.ReadUInt32() -eq 0) {
            throw "Executable candidate has an invalid PE image size: $Path"
        }
    } finally {
        if ($reader) {
            $reader.Dispose()
        } elseif ($stream) {
            $stream.Dispose()
        }
    }
}

function Get-VerifiedSha256 {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    Assert-X64PeImage -Path $Path
    $actualSha = (
        Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop
    ).Hash.ToLowerInvariant()
    if ($actualSha -ne $ExpectedSha256) {
        throw "SHA-256 mismatch (expected $ExpectedSha256, actual $actualSha)"
    }
    return $actualSha
}

function Enter-ExclusiveDownloadLock {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$TimeoutSeconds = 15
    )

    if (Test-PathEntry -Path $Path) {
        Assert-RegularFile -Path $Path -Purpose "Downloader lock" -AllowEmpty
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $announcedWait = $false
    while ($true) {
        try {
            return [System.IO.File]::Open(
                $Path,
                [System.IO.FileMode]::OpenOrCreate,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
        } catch [System.IO.IOException] {
            if ([DateTime]::UtcNow -ge $deadline) {
                throw "Timed out waiting for the exclusive downloader lock: $Path"
            }
            if (-not $announcedWait) {
                Write-Info "Another verified downloader transaction holds the lock; waiting"
                $announcedWait = $true
            }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Assert-ProvenanceLog {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-PathEntry -Path $Path)) {
        return
    }

    Assert-RegularFile -Path $Path -Purpose "Binary provenance log" -AllowEmpty
    $lineNumber = 0
    foreach ($line in [System.IO.File]::ReadLines($Path)) {
        $lineNumber += 1
        if (-not $line.Trim()) {
            continue
        }
        try {
            $record = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            throw (
                "Existing provenance log is not valid JSONL at line $lineNumber. " +
                "It was left untouched: $Path"
            )
        }
        foreach ($requiredField in @(
            "timestamp_utc",
            "component",
            "actual_sha256",
            "output_path"
        )) {
            if ($record.PSObject.Properties.Name -notcontains $requiredField) {
                throw (
                    "Existing provenance record $lineNumber lacks '$requiredField'. " +
                    "The log was left untouched: $Path"
                )
            }
        }
    }
}

function Add-ProvenanceRecord {
    param(
        [Parameter(Mandatory = $true)]$Spec,
        [Parameter(Mandatory = $true)][string]$ActualSha256,
        [Parameter(Mandatory = $true)][string]$VerificationMode,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$ProvenancePath
    )

    Assert-ProvenanceLog -Path $ProvenancePath
    $record = [ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString(
            "yyyy-MM-ddTHH:mm:ss.fffZ",
            [System.Globalization.CultureInfo]::InvariantCulture
        )
        component = $Spec.Component
        version = $Spec.Version
        platform_key = $script:PlatformKey
        asset = $Spec.Asset
        url = $Spec.DownloadUri.AbsoluteUri
        release_url = $Spec.ReleaseUrl
        expected_sha256 = $Spec.ExpectedSha256
        actual_sha256 = $ActualSha256
        verification_mode = $VerificationMode
        output_path = $Spec.OutputPath
        manifest_path = $ManifestPath
    }
    $json = ConvertTo-Json -InputObject $record -Compress -Depth 3
    $encoding = [System.Text.UTF8Encoding]::new($false)
    $bytes = $encoding.GetBytes($json + [Environment]::NewLine)
    $stream = $null

    try {
        $stream = [System.IO.File]::Open(
            $ProvenancePath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::Read
        )
        [void]$stream.Seek(0, [System.IO.SeekOrigin]::End)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        if ($stream) {
            $stream.Dispose()
        }
    }
}

function Invoke-HttpsDownload {
    param(
        [Parameter(Mandatory = $true)][System.Uri]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    [System.Net.ServicePointManager]::SecurityProtocol = (
        [System.Net.ServicePointManager]::SecurityProtocol -bor
        [System.Net.SecurityProtocolType]::Tls12
    )
    Add-Type -AssemblyName System.Net.Http

    $handler = $null
    $client = $null
    $response = $null
    $stream = $null
    try {
        $handler = [System.Net.Http.HttpClientHandler]::new()
        $handler.AllowAutoRedirect = $true
        $client = [System.Net.Http.HttpClient]::new($handler)
        $client.Timeout = [TimeSpan]::FromMinutes(15)
        $client.DefaultRequestHeaders.UserAgent.ParseAdd(
            "PixEagle-Windows-Binary-Downloader/1.0"
        )

        $response = $client.GetAsync(
            $Uri,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "HTTPS download returned HTTP $([int]$response.StatusCode) for $Uri"
        }
        if ($response.RequestMessage.RequestUri.Scheme -ne
            [System.Uri]::UriSchemeHttps) {
            throw "HTTPS download redirected to a non-HTTPS URI"
        }

        $stream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $copyTask = $response.Content.CopyToAsync($stream)
        $copyTask.GetAwaiter().GetResult()
        $stream.Flush($true)
    } finally {
        if ($stream) {
            $stream.Dispose()
        }
        if ($response) {
            $response.Dispose()
        }
        if ($client) {
            $client.Dispose()
        }
        if ($handler) {
            $handler.Dispose()
        }
    }
}

function Remove-OwnedStagingFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$BinDirectory,
        [Parameter(Mandatory = $true)][string]$OwnershipToken
    )

    if (-not (Test-PathEntry -Path $Path)) {
        return
    }

    $expectedPrefix = [System.IO.Path]::GetFullPath($BinDirectory).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith(
        $expectedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or -not $fullPath.EndsWith(
        ".$OwnershipToken.tmp",
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        Write-Warning "Refusing to remove an unowned staging path: $Path"
        return
    }

    try {
        Assert-RegularFile -Path $fullPath -Purpose "Owned staging file" -AllowEmpty
        [System.IO.File]::Delete($fullPath)
    } catch {
        Write-Warning "Could not remove owned staging file '$fullPath': $($_.Exception.Message)"
    }
}

function Show-DownloadPlan {
    param(
        [Parameter(Mandatory = $true)]$Spec,
        [Parameter(Mandatory = $true)][string]$ProvenancePath
    )

    Write-Host ""
    Write-Info $Spec.Component
    Write-Host "      Version:         $($Spec.Version)"
    Write-Host "      Release:         $($Spec.ReleaseUrl)"
    Write-Host "      Asset:           $($Spec.Asset)"
    Write-Host "      URL:             $($Spec.DownloadUri.AbsoluteUri)"
    Write-Host "      Expected SHA256: $($Spec.ExpectedSha256)"
    Write-Host "      Output:          $($Spec.OutputPath)"
    Write-Host "      Provenance:      $ProvenancePath"
}

function Invoke-Downloader {
    Assert-ExperimentalWindowsGate
    Assert-NativeWindowsX64

    $projectRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..\..")
    )
    $binDirectory = [System.IO.Path]::GetFullPath(
        (Join-Path $projectRoot "bin")
    )
    $defaultManifest = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "binary-manifest.env")
    )
    $manifestPath = if ($env:PIXEAGLE_BINARY_MANIFEST) {
        [System.IO.Path]::GetFullPath($env:PIXEAGLE_BINARY_MANIFEST)
    } else {
        $defaultManifest
    }
    $provenancePath = Join-Path $binDirectory "binary-provenance.jsonl"
    $lockPath = Join-Path $binDirectory ".download-binaries.lock"

    $manifest = Read-BinaryManifest -Path $manifestPath
    $downloadAll = $All -or (-not $Mavsdk -and -not $Mavlink2rest)
    $specs = @()
    if ($downloadAll -or $Mavsdk) {
        $specs += New-DownloadSpec `
            -Manifest $manifest `
            -Prefix "PIXEAGLE_BINARY_MAVSDK" `
            -Component "MAVSDK Server" `
            -OutputName "mavsdk_server_bin.exe" `
            -BinDirectory $binDirectory
    }
    if ($downloadAll -or $Mavlink2rest) {
        $specs += New-DownloadSpec `
            -Manifest $manifest `
            -Prefix "PIXEAGLE_BINARY_MAVLINK2REST" `
            -Component "MAVLink2REST" `
            -OutputName "mavlink2rest.exe" `
            -BinDirectory $binDirectory
    }

    Write-Host ""
    Write-Host "PixEagle Binary Downloader" -ForegroundColor Cyan
    Write-Host "Experimental native Windows x64"
    Write-Host "Manifest: $manifestPath"
    foreach ($spec in $specs) {
        Show-DownloadPlan -Spec $spec -ProvenancePath $provenancePath
    }

    if ($DryRun) {
        Write-Host ""
        Write-Success "Dry run complete; no files or directories were modified"
        return
    }

    Assert-SafeDirectory -Path $binDirectory
    $lockStream = $null
    $staged = @()
    try {
        $lockStream = Enter-ExclusiveDownloadLock -Path $lockPath
        Assert-ProvenanceLog -Path $provenancePath

        $states = @()
        foreach ($spec in $specs) {
            if (Test-PathEntry -Path $spec.OutputPath) {
                try {
                    $actualSha = Get-VerifiedSha256 `
                        -Path $spec.OutputPath `
                        -ExpectedSha256 $spec.ExpectedSha256
                } catch {
                    throw (
                        "$($spec.Component) destination exists but is not the " +
                        "manifest-verified Windows x64 binary. It was left untouched: " +
                        "$($spec.OutputPath). $($_.Exception.Message)"
                    )
                }
                $states += [pscustomobject]@{
                    Spec = $spec
                    Existing = $true
                    ActualSha256 = $actualSha
                }
            } else {
                $states += [pscustomobject]@{
                    Spec = $spec
                    Existing = $false
                    ActualSha256 = $null
                }
            }
        }

        foreach ($state in $states) {
            if ($state.Existing) {
                continue
            }

            $token = "$PID.$([Guid]::NewGuid().ToString('N'))"
            $tempPath = Join-Path $binDirectory (
                ".$($state.Spec.OutputName).download.$token.tmp"
            )
            $stage = [pscustomobject]@{
                Spec = $state.Spec
                TempPath = $tempPath
                OwnershipToken = $token
                ActualSha256 = $null
            }
            $staged += $stage

            Write-Info "Downloading $($state.Spec.Component)"
            Invoke-HttpsDownload `
                -Uri $state.Spec.DownloadUri `
                -Destination $stage.TempPath
            $stage.ActualSha256 = Get-VerifiedSha256 `
                -Path $stage.TempPath `
                -ExpectedSha256 $state.Spec.ExpectedSha256
            Write-Success "$($state.Spec.Component) staging file verified"
        }

        foreach ($state in $states) {
            if ($state.Existing) {
                Add-ProvenanceRecord `
                    -Spec $state.Spec `
                    -ActualSha256 $state.ActualSha256 `
                    -VerificationMode "existing_sha256_pe_x64" `
                    -ManifestPath $manifestPath `
                    -ProvenancePath $provenancePath
                Write-Success "Keeping verified existing $($state.Spec.Component)"
                continue
            }

            $stage = $staged | Where-Object {
                $_.Spec.OutputPath -eq $state.Spec.OutputPath
            } | Select-Object -First 1
            if (-not $stage) {
                throw "Internal staging state is missing for $($state.Spec.Component)"
            }
            if (Test-PathEntry -Path $state.Spec.OutputPath) {
                throw (
                    "Destination appeared during download and was left untouched: " +
                    $state.Spec.OutputPath
                )
            }

            [System.IO.File]::Move($stage.TempPath, $state.Spec.OutputPath)
            Add-ProvenanceRecord `
                -Spec $state.Spec `
                -ActualSha256 $stage.ActualSha256 `
                -VerificationMode "download_sha256_pe_x64" `
                -ManifestPath $manifestPath `
                -ProvenancePath $provenancePath
            Write-Success "$($state.Spec.Component) published atomically"
        }

        Write-Host ""
        Write-Success "Requested Windows x64 binaries are manifest-verified"
        Write-Host "   Provenance: $provenancePath"
        Write-Host "   This does not prove PX4, MAVSDK, MAVLink2REST, SITL, or field runtime success."
    } finally {
        foreach ($stage in $staged) {
            Remove-OwnedStagingFile `
                -Path $stage.TempPath `
                -BinDirectory $binDirectory `
                -OwnershipToken $stage.OwnershipToken
        }
        if ($lockStream) {
            $lockStream.Dispose()
        }
    }
}

if ($Help) {
    Show-Usage
    exit 0
}

try {
    Invoke-Downloader
    exit 0
} catch {
    Write-Host ""
    Write-Host "   [X] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
