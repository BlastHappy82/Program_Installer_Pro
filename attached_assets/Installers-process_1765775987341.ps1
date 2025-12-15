# Installers-Process.ps1
# Create a restore point, then run each installer INTERACTIVELY (no silent switches).
param(
    [string]$InstallerFolder = "C:\Users\ricks\Dropbox\Installers",
    [switch]$IncludeSubfolders
)

# -------- Elevation --------
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName  = "powershell.exe"
    $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" " + $MyInvocation.UnboundArguments
    $psi.Verb      = "runas"
    [Diagnostics.Process]::Start($psi) | Out-Null
    exit
}

# -------- System Protection helpers --------
function Ensure-SystemProtection {
    param([string]$Drive = "C:")
    try {
        Enable-ComputerRestore -Drive $Drive -ErrorAction SilentlyContinue
        vssadmin Resize ShadowStorage /For=$Drive /On=$Drive /MaxSize=10% | Out-Null
    } catch {
        Write-Warning "Could not ensure System Protection. Enable it in SystemPropertiesProtection if needed."
    }
}
function Disable-RestorePointThrottle {
    $key = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore"
    New-Item -Path $key -Force | Out-Null
    New-ItemProperty -Path $key -Name "SystemRestorePointCreationFrequency" -Value 0 -PropertyType DWord -Force | Out-Null
}
function New-PreInstallRestorePoint {
    param([string]$Label)
    Write-Host "Creating restore point: $Label"
    Checkpoint-Computer -Description $Label -RestorePointType "MODIFY_SETTINGS"
}

# -------- Prep --------
Ensure-SystemProtection -Drive "C:"
Disable-RestorePointThrottle

if (-not (Test-Path $InstallerFolder)) {
    throw "Installer folder not found: $InstallerFolder"
}

$installedDir = Join-Path $InstallerFolder "_Installed"
$failedDir    = Join-Path $InstallerFolder "_Failed"
$logsDir      = Join-Path $InstallerFolder "_Logs"
New-Item $installedDir -ItemType Directory -Force | Out-Null
New-Item $failedDir    -ItemType Directory -Force | Out-Null
New-Item $logsDir      -ItemType Directory -Force | Out-Null
$csvPath = Join-Path $logsDir ("InstallLog_{0}.csv" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

# Gather installers
if ($IncludeSubfolders) {
    $items = Get-ChildItem -Path $InstallerFolder -File -Recurse |
             Where-Object { $_.Extension -in '.msi', '.exe' } |
             Where-Object { $_.FullName -notmatch '\\_(Installed|Failed|Logs)\\' }
} else {
    $items = Get-ChildItem -Path @("$InstallerFolder\*.msi", "$InstallerFolder\*.exe") -File
}
# Ignore scripts themselves, just in case
$items = $items | Where-Object { $_.Extension -ne '.ps1' }

if (-not $items) {
    Write-Host "No installers found in $InstallerFolder"
    exit 0
}

$results = @()

foreach ($file in $items) {
    $label = "Before installing $($file.BaseName)"
    New-PreInstallRestorePoint -Label $label

    Write-Host ""
    Write-Host "Launching installer: $($file.Name) (interactive)"
    $ext = $file.Extension.ToLower()
    $exitCode = $null

    try {
        if ($ext -eq ".msi") {
            # Interactive MSI
            $p = Start-Process msiexec.exe -ArgumentList "/i `"$($file.FullName)`"" -PassThru -Wait
            $exitCode = $p.ExitCode
        } else {
            # Interactive EXE
            $p = Start-Process -FilePath $file.FullName -PassThru -Wait
            $exitCode = $p.ExitCode
        }
    } catch {
        $exitCode = -1
    }

    $status = if ($exitCode -eq 0) { "Success" } elseif ($exitCode -eq $null) { "Unknown" } else { "Failed" }

    # Move based on status
    try {
        if ($status -eq "Success") {
            Move-Item -LiteralPath $file.FullName -Destination (Join-Path $installedDir $file.Name) -Force
        } else {
            Move-Item -LiteralPath $file.FullName -Destination (Join-Path $failedDir $file.Name) -Force
        }
    } catch {
        Write-Warning "Could not move $($file.Name). It might still be in use."
    }

    $results += [PSCustomObject]@{
        Name       = $file.Name
        FullPath   = $file.FullName
        Type       = $ext
        EndedUtc   = [DateTime]::UtcNow
        ExitCode   = $exitCode
        Status     = $status
    }
}

$results | Export-Csv -NoTypeInformation -Path $csvPath
Write-Host ""
Write-Host "All installers processed."
Write-Host "Log: $csvPath"
Write-Host "Installed moved to: $installedDir"
Write-Host "Failures moved to:  $failedDir"
