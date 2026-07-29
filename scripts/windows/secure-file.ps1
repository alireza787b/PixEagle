param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [switch]$Directory
)

$ErrorActionPreference = "Stop"

$item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
if (($Directory -and -not $item.PSIsContainer) -or
    (-not $Directory -and $item.PSIsContainer) -or
    (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw "Credential path type is invalid or uses a reparse point: $Path"
}

$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
if (-not $currentSid) {
    throw "Could not resolve the current Windows user SID"
}

$acl = if ($Directory) {
    [System.Security.AccessControl.DirectorySecurity]::new()
} else {
    [System.Security.AccessControl.FileSecurity]::new()
}
$acl.SetOwner($currentSid)
$acl.SetAccessRuleProtection($true, $false)
$rule = if ($Directory) {
    [System.Security.AccessControl.FileSystemAccessRule]::new(
        $currentSid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        (
            [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
            [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
        ),
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
} else {
    [System.Security.AccessControl.FileSystemAccessRule]::new(
        $currentSid,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
}
$acl.SetAccessRule($rule)
if ($Directory) {
    [System.IO.Directory]::SetAccessControl($item.FullName, $acl)
    $verified = [System.IO.Directory]::GetAccessControl(
        $item.FullName,
        [System.Security.AccessControl.AccessControlSections]::All
    )
} else {
    [System.IO.File]::SetAccessControl($item.FullName, $acl)
    $verified = [System.IO.File]::GetAccessControl(
        $item.FullName,
        [System.Security.AccessControl.AccessControlSections]::All
    )
}
$owner = $verified.GetOwner(
    [System.Security.Principal.SecurityIdentifier]
)
$rules = @($verified.GetAccessRules(
    $true,
    $true,
    [System.Security.Principal.SecurityIdentifier]
))
$fullControl = [System.Security.AccessControl.FileSystemRights]::FullControl
if ($owner.Value -ne $currentSid.Value -or
    $rules.Count -ne 1 -or
    $rules[0].IdentityReference.Value -ne $currentSid.Value -or
    $rules[0].AccessControlType -ne
        [System.Security.AccessControl.AccessControlType]::Allow -or
    (($rules[0].FileSystemRights -band $fullControl) -ne $fullControl)) {
    throw "Could not verify an owner-only credential ACL: $Path"
}

$kind = if ($Directory) { "directory" } else { "file" }
Write-Host "   [OK] Dashboard credential $kind ACL is owner-only"
