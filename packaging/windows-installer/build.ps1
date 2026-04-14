param(
    [string]$PythonExe = "py",
    [string]$PythonVersionArg = "-3.13",
    [string]$Name = "HermesInstaller"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot | Split-Path -Parent
$Bootstrap = Join-Path $PSScriptRoot "bootstrap.py"
$InstallScript = Join-Path $RepoRoot "scripts\install.ps1"
$DistDir = Join-Path $PSScriptRoot "dist"
$BuildDir = Join-Path $PSScriptRoot "build"
$SpecDir = $PSScriptRoot
$BundleStage = Join-Path $env:TEMP "hermes-installer-repo-stage"
$BundleZip = Join-Path $env:TEMP "hermes-agent-bundle.zip"

Write-Host "[INFO] Building Windows installer EXE..." -ForegroundColor Cyan

function New-RepoBundle {
  if (Test-Path $BundleZip) {
    Remove-Item -Force $BundleZip
  }
  $pyArgs = @()
  if ($PythonVersionArg) {
    $pyArgs += $PythonVersionArg
  }
  $pyArgs += @("-")

  $pythonScript = @'
from pathlib import Path
import zipfile

repo_root = Path(r"__REPO_ROOT__")
bundle_zip = Path(r"__BUNDLE_ZIP__")

exclude_dir_names = {".git", ".pytest_cache", "__pycache__", ".hermes"}
exclude_prefixes = (
    "packaging/windows-installer/build/",
    "packaging/windows-installer/dist/",
)
exclude_files = {"cli-config.yaml"}

bundle_zip.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in repo_root.rglob("*"):
        rel = path.relative_to(repo_root).as_posix()
        if any(part in exclude_dir_names for part in path.parts):
            continue
        if any(rel.startswith(prefix) for prefix in exclude_prefixes):
            continue
        if path.is_file() and path.name in exclude_files:
            continue
        if path.is_file():
            zf.write(path, rel)
'@

  $pythonScript = $pythonScript.Replace("__REPO_ROOT__", $RepoRoot.Replace("\", "\\"))
  $pythonScript = $pythonScript.Replace("__BUNDLE_ZIP__", $BundleZip.Replace("\", "\\"))

  $pythonScript | & $PythonExe @pyArgs
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path $BundleZip)) {
    throw "Failed to create repository bundle"
  }
}

function Invoke-Build {
  param(
    [string]$ArtifactName,
    [switch]$Windowed
  )

  $AddDataScriptArg = "$InstallScript;scripts"
  $AddDataBundleArg = "$BundleZip;repo"
  $pyArgs = @()
  if ($PythonVersionArg) {
    $pyArgs += $PythonVersionArg
  }
  $pyArgs += @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", $ArtifactName,
    "--distpath", $DistDir,
    "--workpath", (Join-Path $BuildDir $ArtifactName),
    "--specpath", $SpecDir,
    "--add-data", $AddDataScriptArg,
    "--add-data", $AddDataBundleArg
  )
  if ($Windowed) {
    $pyArgs += "--windowed"
  }
  $pyArgs += $Bootstrap

  & $PythonExe @pyArgs
}

New-RepoBundle
Invoke-Build -ArtifactName $Name -Windowed
Invoke-Build -ArtifactName "${Name}Console"

Write-Host "[OK] Build complete:" -ForegroundColor Green
Write-Host "  $DistDir\$Name.exe"
Write-Host "  $DistDir\${Name}Console.exe"
