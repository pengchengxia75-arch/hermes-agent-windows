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

Write-Host "[INFO] Building Windows installer EXE..." -ForegroundColor Cyan

function Invoke-Build {
  param(
    [string]$ArtifactName,
    [switch]$Windowed
  )

  $AddDataArg = "$InstallScript;scripts"
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
    "--add-data", $AddDataArg
  )
  if ($Windowed) {
    $pyArgs += "--windowed"
  }
  $pyArgs += $Bootstrap

  & $PythonExe @pyArgs
}

Invoke-Build -ArtifactName $Name -Windowed
Invoke-Build -ArtifactName "${Name}Console"

Write-Host "[OK] Build complete:" -ForegroundColor Green
Write-Host "  $DistDir\$Name.exe"
Write-Host "  $DistDir\${Name}Console.exe"
