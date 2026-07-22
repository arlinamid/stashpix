#requires -Version 5.1
<#
.SYNOPSIS
    Build the standalone bundle (PyInstaller) and the Windows MSI (WiX v4+).

.DESCRIPTION
    Run from anywhere; paths are resolved relative to the repository root.
    Steps:
      1. PyInstaller  -> dist/stashpix/ (stashpix.exe + stashpix-gui.exe + _internal)
      2. wix build    -> packaging/out/stashpix-<version>.msi

.PARAMETER Version
    Product version written into the MSI. Defaults to 1.4.0.

.PARAMETER SkipBundle
    Reuse an existing dist/stashpix and only (re)build the MSI.

.EXAMPLE
    packaging\build.ps1
    packaging\build.ps1 -Version 1.4.0
#>
param(
    [string]$Version = "1.4.0",
    [switch]$SkipBundle
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist\\stashpix"
$OutDir = Join-Path $PSScriptRoot "out"
$Spec = Join-Path $PSScriptRoot "pyinstaller\stashpix.spec"
$Wxs = Join-Path $PSScriptRoot "wix\Package.wxs"
$Msi = Join-Path $OutDir "stashpix-$Version.msi"
$IconFile = Join-Path $Root "assets\icon.ico"

Push-Location $Root
try {
    if (-not $SkipBundle) {
        Write-Host "==> PyInstaller bundle" -ForegroundColor Cyan
        python -m PyInstaller $Spec --noconfirm --distpath (Join-Path $Root "dist") `
            --workpath (Join-Path $Root "build")
    }
    if (-not (Test-Path (Join-Path $Dist "stashpix.exe"))) {
        throw "Bundle not found at $Dist (did PyInstaller succeed?)"
    }

    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

    Write-Host "==> WiX MSI" -ForegroundColor Cyan
    wix build $Wxs -acceptEula wix7 -arch x64 `
        -d StageDir="$Dist" -d Version="$Version" -d IconFile="$IconFile" -o $Msi

    Write-Host "`nDone:" -ForegroundColor Green
    Write-Host "  bundle : $Dist"
    Write-Host "  msi    : $Msi"
}
finally {
    Pop-Location
}
