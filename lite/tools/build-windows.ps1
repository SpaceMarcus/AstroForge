param([switch]$SkipWebBuild)
$ErrorActionPreference = 'Stop'
$liteRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $liteRoot '..')).Path
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Development Python environment not found at .venv/Scripts/python.exe' }
if (-not $SkipWebBuild) {
    & node (Join-Path $PSScriptRoot 'build.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'Web build failed.' }
}
$webAssets = Join-Path $liteRoot 'dist'
if (-not (Test-Path -LiteralPath (Join-Path $webAssets 'index.html'))) { throw 'Web assets are missing. Run npm run build first.' }
$distOutput = Join-Path $repoRoot 'outputs/astroforge-lite-windows'
$buildWork = Join-Path $liteRoot 'build-windows'
New-Item -ItemType Directory -Path $distOutput, $buildWork -Force | Out-Null
& $pythonExe -m PyInstaller --noconfirm --onefile --windowed --name AstroForge-2.0-Lite --distpath $distOutput --workpath (Join-Path $buildWork 'work') --specpath $buildWork --add-data "${webAssets}:web" (Join-Path $PSScriptRoot 'windows_launcher.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows executable build failed.' }
$exePath = Join-Path $distOutput 'AstroForge-2.0-Lite.exe'
$smoke = Start-Process -FilePath $exePath -ArgumentList '--smoke-test' -WindowStyle Hidden -PassThru -Wait
if ($smoke.ExitCode -ne 0) { throw "Packaged smoke test failed with exit code $($smoke.ExitCode)." }
Write-Output "Windows executable built and smoke-tested: $exePath"
