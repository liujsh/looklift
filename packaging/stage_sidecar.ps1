param(
    [string]$Source = ""
)

$ErrorActionPreference = "Stop"
$packagingDir = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent $packagingDir
if (-not $Source) {
    $Source = Join-Path $repoRoot "build\pyinstaller\dist\looklift-engine"
}
$sourceDir = (Resolve-Path -LiteralPath $Source).Path
$targetDir = Join-Path $repoRoot "frontend\src-tauri\binaries"
$expectedRoot = (Resolve-Path -LiteralPath (Join-Path $repoRoot "frontend\src-tauri")).Path
$resolvedParent = (Resolve-Path -LiteralPath (Split-Path -Parent $targetDir)).Path
if ($resolvedParent -ne $expectedRoot) {
    throw "sidecar 暂存目录超出 frontend/src-tauri：$targetDir"
}

if (Test-Path -LiteralPath $targetDir) {
    Remove-Item -LiteralPath $targetDir -Recurse -Force
}
New-Item -ItemType Directory -Path $targetDir | Out-Null

Copy-Item -LiteralPath (Join-Path $sourceDir "looklift-engine.exe") `
    -Destination (Join-Path $targetDir "looklift-engine-x86_64-pc-windows-msvc.exe")
Copy-Item -LiteralPath (Join-Path $sourceDir "_internal") `
    -Destination (Join-Path $targetDir "_internal") -Recurse

Write-Output "sidecar 已暂存到 $targetDir"
