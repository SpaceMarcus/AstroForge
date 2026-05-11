Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $workspace

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$versionsDir = Join-Path $workspace "versions"
$distDir = Join-Path $workspace "dist"
$buildDir = Join-Path $workspace "build"

New-Item -ItemType Directory -Force -Path $versionsDir | Out-Null

if (Test-Path $distDir) {
    Get-ChildItem -Path $distDir -File -Filter "*.exe" | ForEach-Object {
        $archivedName = "{0}_v{1}{2}" -f $_.BaseName, $timestamp, $_.Extension
        Move-Item -LiteralPath $_.FullName -Destination (Join-Path $versionsDir $archivedName)
    }
}

if (Test-Path $buildDir) {
    $archivedBuildDir = Join-Path $versionsDir ("build_" + $timestamp)
    Move-Item -LiteralPath $buildDir -Destination $archivedBuildDir
}

python -m PyInstaller --clean --noconfirm RocketEnginePredesign.spec

$latestExe = Join-Path $distDir "AstraForge.exe"
if (-not (Test-Path $latestExe)) {
    throw "Expected EXE was not created at $latestExe"
}

$versionedExe = Join-Path $distDir ("AstraForge_v" + $timestamp + ".exe")
Copy-Item -LiteralPath $latestExe -Destination $versionedExe

Write-Host "Latest EXE: $latestExe"
Write-Host "Versioned EXE: $versionedExe"
