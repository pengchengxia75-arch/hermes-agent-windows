# ============================================================================
# Hermes Agent Installer for Windows
# ============================================================================
# Installation script for Windows (PowerShell).
# Uses uv for fast Python provisioning and package management.
#
# Usage:
#   $u = "https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1"; $p = "$env:TEMP\hermes-install.ps1"; Invoke-WebRequest -Uri $u -OutFile $p; powershell -ExecutionPolicy Bypass -File $p
#
# Or download and run with options:
#   .\install.ps1 -NoVenv -SkipSetup
#
# ============================================================================

param(
    [switch]$NoVenv,
    [switch]$SkipSetup,
    [string]$Branch = "main",
    [string]$BundleZip = "",
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes",
    [string]$InstallDir = "$env:LOCALAPPDATA\hermes\hermes-agent"
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration
# ============================================================================

$RepoUrlSsh = "git@github.com:pengchengxia75-arch/hermes-agent-windows.git"
$RepoUrlHttps = "https://github.com/pengchengxia75-arch/hermes-agent-windows.git"
$PythonVersion = "3.11"
$NodeVersion = "22"

# ============================================================================
# Helper functions
# ============================================================================

function Write-Banner {
    Write-Host ""
    Write-Host "=== Hermes Agent Installer ===" -ForegroundColor Magenta
    Write-Host "Windows setup for Hermes Agent" -ForegroundColor Magenta
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Invoke-InstallerCommandWithTimeout {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$Description,
        [int]$TimeoutSeconds = 180
    )

    try {
        $process = Start-Process -FilePath $FilePath `
            -ArgumentList $ArgumentList `
            -WindowStyle Hidden `
            -PassThru

        if ($process.WaitForExit($TimeoutSeconds * 1000)) {
            return ($process.ExitCode -eq 0)
        }

        Write-Warn "$Description timed out after ${TimeoutSeconds}s. Skipping and continuing install."
        try { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue } catch { }
        return $false
    } catch {
        Write-Warn "$Description failed to start: $_"
        return $false
    }
}

# ============================================================================
# Dependency checks
# ============================================================================

function Install-Uv {
    Write-Info "Checking for uv package manager..."
    
    # Check if uv is already available
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        $version = uv --version
        $script:UvCmd = "uv"
        Write-Success "uv found ($version)"
        return $true
    }
    
    # Check common install locations
    $uvPaths = @(
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe"
    )
    foreach ($uvPath in $uvPaths) {
        if (Test-Path $uvPath) {
            $script:UvCmd = $uvPath
            $version = & $uvPath --version
            Write-Success "uv found at $uvPath ($version)"
            return $true
        }
    }
    
    # Install uv
    Write-Info "Installing uv (fast Python package manager)..."
    try {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        
        # Find the installed binary
        $uvExe = "$env:USERPROFILE\.local\bin\uv.exe"
        if (-not (Test-Path $uvExe)) {
            $uvExe = "$env:USERPROFILE\.cargo\bin\uv.exe"
        }
        if (-not (Test-Path $uvExe)) {
            # Refresh PATH and try again
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            if (Get-Command uv -ErrorAction SilentlyContinue) {
                $uvExe = (Get-Command uv).Source
            }
        }
        
        if (Test-Path $uvExe) {
            $script:UvCmd = $uvExe
            $version = & $uvExe --version
            Write-Success "uv installed ($version)"
            return $true
        }
        
        Write-Err "uv installed but not found on PATH"
        Write-Info "提示：请关闭当前终端，重新打开后再运行安装命令"
        Write-Info "Try restarting your terminal and re-running"
        return $false
    } catch {
        Write-Err "Failed to install uv"
        Write-Info "Install manually: https://docs.astral.sh/uv/getting-started/installation/"
        return $false
    }
}

function Test-Python {
    Write-Info "Checking Python $PythonVersion..."
    
    # Let uv find or install Python
    try {
        $pythonPath = & $UvCmd python find $PythonVersion 2>$null
        if ($pythonPath) {
            $ver = & $pythonPath --version 2>$null
            Write-Success "Python found: $ver"
            return $true
        }
    } catch { }
    
    # Python not found - use uv to install it (no admin needed!)
    Write-Info "Python $PythonVersion not found, installing via uv..."
    try {
        $uvOutput = & $UvCmd python install $PythonVersion 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonPath = & $UvCmd python find $PythonVersion 2>$null
            if ($pythonPath) {
                $ver = & $pythonPath --version 2>$null
                Write-Success "Python installed: $ver"
                return $true
            }
        } else {
            Write-Warn "uv python install output:"
            Write-Host $uvOutput -ForegroundColor DarkGray
        }
    } catch {
        Write-Warn "uv python install error: $_"
    }

    # Fallback: check if ANY Python 3.10+ is already available on the system
    Write-Info "Trying to find any existing Python 3.10+..."
    foreach ($fallbackVer in @("3.12", "3.13", "3.10")) {
        try {
            $pythonPath = & $UvCmd python find $fallbackVer 2>$null
            if ($pythonPath) {
                $ver = & $pythonPath --version 2>$null
                Write-Success "Found fallback: $ver"
                $script:PythonVersion = $fallbackVer
                return $true
            }
        } catch { }
    }

    # Fallback: try system python
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $sysVer = python --version 2>$null
        if ($sysVer -match "3\.(1[0-9]|[1-9][0-9])") {
            Write-Success "Using system Python: $sysVer"
            return $true
        }
    }
    
    Write-Err "Failed to install Python $PythonVersion"
    Write-Info "Install Python 3.11 manually, then re-run this script:"
    Write-Info "  https://www.python.org/downloads/"
    Write-Info "  Or: winget install Python.Python.3.11"
    return $false
}

function Test-Git {
    Write-Info "Checking Git..."
    
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $version = git --version
        Write-Success "Git found ($version)"
        return $true
    }

    Write-Info "Git not found - installing Git for Windows..."

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try {
            winget install --id Git.Git --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        } catch {
            Write-Warn "winget Git install failed: $_"
        }
    }

    $candidatePaths = @(
        'C:\Program Files\Git\bin',
        'C:\Program Files\Git\cmd',
        'C:\Program Files (x86)\Git\bin',
        'C:\Program Files (x86)\Git\cmd',
        "$env:LOCALAPPDATA\Programs\Git\bin",
        "$env:LOCALAPPDATA\Programs\Git\cmd"
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidatePaths.Count -gt 0) {
        $prepend = ($candidatePaths -join ';' )
        $env:Path = "$prepend;$env:Path"
    } else {
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
    }

    if (Get-Command git -ErrorAction SilentlyContinue) {
        $version = git --version
        Write-Success "Git installed ($version)"
        return $true
    }
    
    Write-Err "Git not found"
    Write-Info "Install manually from: https://git-scm.com/download/win"
    return $false
}

function Test-Node {
    Write-Info "Checking Node.js (for browser tools)..."

    if (Get-Command node -ErrorAction SilentlyContinue) {
        $version = node --version
        Write-Success "Node.js $version found"
        $script:HasNode = $true
        return $true
    }

    # Check our own managed install from a previous run
    $managedNode = "$HermesHome\node\node.exe"
    if (Test-Path $managedNode) {
        $version = & $managedNode --version
        $env:Path = "$HermesHome\node;$env:Path"
        Write-Success "Node.js $version found (Hermes-managed)"
        $script:HasNode = $true
        return $true
    }

    Write-Info "Node.js not found - installing Node.js $NodeVersion LTS..."

    # Try winget first (cleanest on modern Windows)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Info "Installing via winget..."
        try {
            winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
            # Refresh PATH
            $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
            if (Get-Command node -ErrorAction SilentlyContinue) {
                $version = node --version
                Write-Success "Node.js $version installed via winget"
                $script:HasNode = $true
                return $true
            }
        } catch { }
    }

    # Fallback: download binary zip to ~/.hermes/node/
    Write-Info "Downloading Node.js $NodeVersion binary..."
    try {
        $arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }
        $indexUrl = "https://nodejs.org/dist/latest-v${NodeVersion}.x/"
        $indexPage = Invoke-WebRequest -Uri $indexUrl -UseBasicParsing
        $zipName = ($indexPage.Content | Select-String -Pattern "node-v${NodeVersion}\.\d+\.\d+-win-${arch}\.zip" -AllMatches).Matches[0].Value

        if ($zipName) {
            $downloadUrl = "${indexUrl}${zipName}"
            $tmpZip = "$env:TEMP\$zipName"
            $tmpDir = "$env:TEMP\hermes-node-extract"

            Invoke-WebRequest -Uri $downloadUrl -OutFile $tmpZip -UseBasicParsing
            if (Test-Path $tmpDir) { Remove-Item -Recurse -Force $tmpDir }
            Expand-Archive -Path $tmpZip -DestinationPath $tmpDir -Force

            $extractedDir = Get-ChildItem $tmpDir -Directory | Select-Object -First 1
            if ($extractedDir) {
                if (Test-Path "$HermesHome\node") { Remove-Item -Recurse -Force "$HermesHome\node" }
                Move-Item $extractedDir.FullName "$HermesHome\node"
                $env:Path = "$HermesHome\node;$env:Path"

                $version = & "$HermesHome\node\node.exe" --version
                Write-Success "Node.js $version installed to ~/.hermes/node/"
                $script:HasNode = $true

                Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
                Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
                return $true
            }
        }
    } catch {
        Write-Warn "Download failed: $_"
    }

    Write-Warn "Could not auto-install Node.js"
    Write-Info "Install manually: https://nodejs.org/en/download/"
    $script:HasNode = $false
    return $true
}

function Install-SystemPackages {
    $script:HasRipgrep = $false
    $script:HasFfmpeg = $false
    $needRipgrep = $false
    $needFfmpeg = $false

    Write-Info "Checking ripgrep (fast file search)..."
    try {
        if (Get-Command rg -ErrorAction SilentlyContinue) {
            $version = rg --version | Select-Object -First 1
            Write-Success "$version found"
            $script:HasRipgrep = $true
        } else {
            $needRipgrep = $true
        }
    } catch {
        $needRipgrep = $true
        Write-Warn "Found rg on PATH but it could not be executed. Will try to install a working ripgrep."
    }

    Write-Info "Checking ffmpeg (TTS voice messages)..."
    try {
        if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
            Write-Success "ffmpeg found"
            $script:HasFfmpeg = $true
        } else {
            $needFfmpeg = $true
        }
    } catch {
        $needFfmpeg = $true
        Write-Warn "Found ffmpeg on PATH but it could not be executed. Will try to install a working ffmpeg."
    }

    if (-not $needRipgrep) { return }

    # Build description and package lists for each package manager
    $descParts = @()
    $wingetPkgs = @()
    $chocoPkgs = @()
    $scoopPkgs = @()

    if ($needRipgrep) {
        $descParts += "ripgrep for faster file search"
        $wingetPkgs += "BurntSushi.ripgrep.MSVC"
        $chocoPkgs += "ripgrep"
        $scoopPkgs += "ripgrep"
    }
    if ($needFfmpeg) {
        Write-Warn "ffmpeg not found. Hermes can still install and run without it."
        Write-Info "Install later if needed: winget install Gyan.FFmpeg"
    }

    $description = $descParts -join " and "
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue
    $hasChoco = Get-Command choco -ErrorAction SilentlyContinue
    $hasScoop = Get-Command scoop -ErrorAction SilentlyContinue

    # Try winget first (most common on modern Windows)
    if ($hasWinget) {
        Write-Info "Installing $description via winget..."
        $wingetExe = $hasWinget.Source
        foreach ($pkg in $wingetPkgs) {
            $pkgLabel = if ($pkg -like "*FFmpeg*") { "ffmpeg via winget" } else { "$pkg via winget" }
            $timeout = if ($pkg -like "*FFmpeg*") { 90 } else { 120 }
            [void](Invoke-InstallerCommandWithTimeout `
                -FilePath $wingetExe `
                -ArgumentList @("install", $pkg, "--silent", "--accept-package-agreements", "--accept-source-agreements") `
                -Description $pkgLabel `
                -TimeoutSeconds $timeout)
        }
        # Refresh PATH and recheck
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
        if (-not $needRipgrep -and -not $needFfmpeg) { return }
    }

    # Fallback: choco
    if ($hasChoco -and $needRipgrep) {
        Write-Info "Trying Chocolatey..."
        $chocoExe = $hasChoco.Source
        foreach ($pkg in $chocoPkgs) {
            [void](Invoke-InstallerCommandWithTimeout `
                -FilePath $chocoExe `
                -ArgumentList @("install", $pkg, "-y") `
                -Description "$pkg via Chocolatey" `
                -TimeoutSeconds 180)
        }
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed via chocolatey"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed via chocolatey"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
    }

    # Fallback: scoop
    if ($hasScoop -and $needRipgrep) {
        Write-Info "Trying Scoop..."
        $scoopExe = $hasScoop.Source
        foreach ($pkg in $scoopPkgs) {
            [void](Invoke-InstallerCommandWithTimeout `
                -FilePath $scoopExe `
                -ArgumentList @("install", $pkg) `
                -Description "$pkg via Scoop" `
                -TimeoutSeconds 180)
        }
        if ($needRipgrep -and (Get-Command rg -ErrorAction SilentlyContinue)) {
            Write-Success "ripgrep installed via scoop"
            $script:HasRipgrep = $true
            $needRipgrep = $false
        }
        if ($needFfmpeg -and (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            Write-Success "ffmpeg installed via scoop"
            $script:HasFfmpeg = $true
            $needFfmpeg = $false
        }
    }

    # Show manual instructions for anything still missing
    if ($needRipgrep) {
        Write-Warn "ripgrep not installed (file search will use findstr fallback)"
        Write-Info "  winget install BurntSushi.ripgrep.MSVC"
    }

}

# ============================================================================
# Installation
# ============================================================================

function Install-Repository {
    Write-Info "Installing to $InstallDir..."
    
    if (Test-Path $InstallDir) {
        if (Test-Path "$InstallDir\.git") {
            Write-Info "Existing installation found, updating..."
            Push-Location $InstallDir
            $currentOrigin = ""
            try {
                $currentOrigin = (git remote get-url origin 2>$null).Trim()
            } catch { }

            if (-not $currentOrigin) {
                Write-Info "Configuring origin remote..."
                git remote add origin $RepoUrlHttps 2>$null
            } elseif ($currentOrigin -ne $RepoUrlHttps -and $currentOrigin -ne $RepoUrlSsh) {
                Write-Warn "Updating existing origin remote to this fork..."
                git remote set-url origin $RepoUrlHttps
            }

            git -c windows.appendAtomically=false fetch origin
            git -c windows.appendAtomically=false checkout $Branch
            git -c windows.appendAtomically=false pull origin $Branch
            Pop-Location
        } else {
            Write-Err "Directory exists but is not a git repository: $InstallDir"
            Write-Info "Remove it or choose a different directory with -InstallDir"
            throw "Directory exists but is not a git repository: $InstallDir"
        }
    } else {
        $cloneSuccess = $false

        if ($BundleZip -and (Test-Path $BundleZip)) {
            Write-Info "Installing from bundled repository snapshot..."
            try {
                $extractPath = Join-Path $env:TEMP "hermes-agent-bundled-extract"
                if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue }
                Expand-Archive -Path $BundleZip -DestinationPath $extractPath -Force

                if (Test-Path (Join-Path $extractPath "pyproject.toml")) {
                    $extractedDir = Get-Item $extractPath
                } else {
                    $candidateDirs = Get-ChildItem $extractPath -Directory
                    $extractedDir = $candidateDirs | Where-Object { Test-Path (Join-Path $_.FullName "pyproject.toml") } | Select-Object -First 1
                    if (-not $extractedDir) {
                        $extractedDir = $candidateDirs | Select-Object -First 1
                    }
                }

                if ($extractedDir) {
                    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) -ErrorAction SilentlyContinue | Out-Null
                    Move-Item $extractedDir.FullName $InstallDir -Force
                    Write-Success "Installed bundled repository snapshot"

                    Push-Location $InstallDir
                    git -c windows.appendAtomically=false init 2>$null
                    git -c windows.appendAtomically=false config windows.appendAtomically false 2>$null
                    git remote add origin $RepoUrlHttps 2>$null
                    Pop-Location
                    Write-Success "Git repo initialized for future updates"

                    $cloneSuccess = $true
                } else {
                    Write-Warn "Bundled repository snapshot did not contain a valid project root"
                }

                Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue
            } catch {
                Write-Warn "Bundled repository install failed: $_"
            }
        }

        if (-not $cloneSuccess) {
            # Fix Windows git "copy-fd: write returned: Invalid argument" error.
            # Git for Windows can fail on atomic file operations (hook templates,
            # config lock files) due to antivirus, OneDrive, or NTFS filter drivers.
            # The -c flag injects config before any file I/O occurs.
            Write-Info "Configuring git for Windows compatibility..."
            $env:GIT_CONFIG_COUNT = "1"
            $env:GIT_CONFIG_KEY_0 = "windows.appendAtomically"
            $env:GIT_CONFIG_VALUE_0 = "false"
            git config --global windows.appendAtomically false 2>$null

            # Try SSH first, then HTTPS, with -c flag for atomic write fix
            Write-Info "Trying SSH clone..."
            $env:GIT_SSH_COMMAND = "ssh -o BatchMode=yes -o ConnectTimeout=5"
            try {
                git -c windows.appendAtomically=false clone --branch $Branch --recurse-submodules $RepoUrlSsh $InstallDir
                if ($LASTEXITCODE -eq 0) { $cloneSuccess = $true }
            } catch { }
            $env:GIT_SSH_COMMAND = $null
        }
        
        if (-not $cloneSuccess) {
            if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
            Write-Info "SSH failed, trying HTTPS..."
            try {
                git -c windows.appendAtomically=false clone --branch $Branch --recurse-submodules $RepoUrlHttps $InstallDir
                if ($LASTEXITCODE -eq 0) { $cloneSuccess = $true }
            } catch { }
        }

        # Fallback: download ZIP archive (bypasses git file I/O issues entirely)
        if (-not $cloneSuccess) {
            if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
            Write-Warn "Git clone failed - downloading ZIP archive instead..."
            try {
                $zipUrl = "https://github.com/pengchengxia75-arch/hermes-agent-windows/archive/refs/heads/$Branch.zip"
                $zipPath = "$env:TEMP\hermes-agent-$Branch.zip"
                $extractPath = "$env:TEMP\hermes-agent-extract"
                
                Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
                if (Test-Path $extractPath) { Remove-Item -Recurse -Force $extractPath }
                Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
                
                # GitHub ZIPs extract to repo-branch/ subdirectory
                $extractedDir = Get-ChildItem $extractPath -Directory | Select-Object -First 1
                if ($extractedDir) {
                    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) -ErrorAction SilentlyContinue | Out-Null
                    Move-Item $extractedDir.FullName $InstallDir -Force
                    Write-Success "Downloaded and extracted"
                    
                    # Initialize git repo so updates work later
                    Push-Location $InstallDir
                    git -c windows.appendAtomically=false init 2>$null
                    git -c windows.appendAtomically=false config windows.appendAtomically false 2>$null
                    git remote add origin $RepoUrlHttps 2>$null
                    Pop-Location
                    Write-Success "Git repo initialized for future updates"
                    
                    $cloneSuccess = $true
                }
                
                # Cleanup temp files
                Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
                Remove-Item -Recurse -Force $extractPath -ErrorAction SilentlyContinue
            } catch {
                Write-Err "ZIP download also failed: $_"
            }
        }

        if (-not $cloneSuccess) {
            throw "Failed to download repository (tried git clone SSH, HTTPS, and ZIP)"
        }
    }
    
    # Set per-repo config (harmless if it fails)
    Push-Location $InstallDir
    git -c windows.appendAtomically=false config windows.appendAtomically false 2>$null

    # Ensure submodules are initialized and updated
    Write-Info "Initializing submodules..."
    git -c windows.appendAtomically=false submodule update --init --recursive 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Submodule init failed (terminal/RL tools may need manual setup)"
    } else {
        Write-Success "Submodules ready"
    }
    Pop-Location
    
    Write-Success "Repository ready"
}

function Stop-InstallProcesses {
    param([string]$TargetRoot)

    $normalizedRoot = [System.IO.Path]::GetFullPath($TargetRoot)
    $stopped = $false

    Write-Warn "Installer may stop running Hermes processes that are locking the install directory."
    Write-Info "Install root being unlocked: $normalizedRoot"

    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Path -and $_.Path.StartsWith($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)
    }

    foreach ($proc in $procs) {
        try {
            Write-Warn "Stopping process locking install dir: $($proc.ProcessName) ($($proc.Id))"
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            $stopped = $true
        } catch {
            Write-Warn "Could not stop process $($proc.ProcessName) ($($proc.Id))"
        }
    }

    return $stopped
}

function Install-Venv {
    if ($NoVenv) {
        Write-Info "Skipping virtual environment (-NoVenv)"
        return
    }
    
    Write-Info "Creating virtual environment with Python $PythonVersion..."
    
    Push-Location $InstallDir
    
    if (Test-Path "venv") {
        Write-Info "Virtual environment already exists, recreating..."
        try {
            Remove-Item -Recurse -Force "venv" -ErrorAction Stop
        } catch {
            Write-Warn "Existing virtual environment is locked. Trying to stop running Hermes processes..."
            $stopped = Stop-InstallProcesses -TargetRoot $InstallDir
            if ($stopped) {
                Start-Sleep -Seconds 2
            }
            Remove-Item -Recurse -Force "venv" -ErrorAction Stop
        }
    }
    
    # uv creates the venv and pins the Python version in one step
    & $UvCmd venv venv --python $PythonVersion
    
    Pop-Location
    
    Write-Success "Virtual environment ready (Python $PythonVersion)"
}

function Install-Dependencies {
    Write-Info "Installing dependencies..."
    
    Push-Location $InstallDir
    
    if (-not $NoVenv) {
        # Tell uv to install into our venv (no activation needed)
        $env:VIRTUAL_ENV = "$InstallDir\venv"
    }
    
    # Install main package with all extras
    & $UvCmd pip install -e ".[all]"
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Full dependency install failed; retrying with base package only."
        & $UvCmd pip install -e "."
        if ($LASTEXITCODE -ne 0) {
            Write-Err "依赖安装失败，请查看上方错误信息"
            throw "Base dependency install failed"
        }
    }
    
    Write-Success "Main package installed"
    
    # Install optional submodules
    Write-Info "Installing tinker-atropos (RL training backend)..."
    if (Test-Path "tinker-atropos\pyproject.toml") {
        try {
            & $UvCmd pip install -e ".\tinker-atropos" 2>&1 | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
            Write-Success "tinker-atropos installed"
        } catch {
            Write-Warn "tinker-atropos install failed (RL tools may not work)"
        }
    } else {
        Write-Warn "tinker-atropos not found (run: git submodule update --init)"
    }
    
    Pop-Location
    
    Write-Success "All dependencies installed"
}

function Set-PathVariable {
    Write-Info "Setting up hermes command..."
    
    if ($NoVenv) {
        $hermesBin = "$InstallDir"
    } else {
        $hermesBin = "$InstallDir\venv\Scripts"
    }
    
    # Add the venv Scripts dir to user PATH so hermes is globally available
    # On Windows, the hermes.exe in venv\Scripts\ has the venv Python baked in
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    if ($currentPath -notlike "*$hermesBin*") {
        [Environment]::SetEnvironmentVariable(
            "Path",
            "$hermesBin;$currentPath",
            "User"
        )
        Write-Success "Added to user PATH: $hermesBin"
    } else {
        Write-Info "PATH already configured"
    }

    $gitBashCandidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files\Git\usr\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe",
        "C:\Program Files (x86)\Git\usr\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\usr\bin\bash.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    if ($gitBashCandidates.Count -gt 0) {
        $gitBash = $gitBashCandidates[0]
        [Environment]::SetEnvironmentVariable("HERMES_GIT_BASH_PATH", $gitBash, "User")
        $env:HERMES_GIT_BASH_PATH = $gitBash
        Write-Success "Set HERMES_GIT_BASH_PATH=$gitBash"
    }
    
    # Set HERMES_HOME so the Python code finds config/data in the right place.
    # Only needed on Windows where we install to %LOCALAPPDATA%\hermes instead
    # of the Unix default ~/.hermes
    $currentHermesHome = [Environment]::GetEnvironmentVariable("HERMES_HOME", "User")
    if (-not $currentHermesHome -or $currentHermesHome -ne $HermesHome) {
        [Environment]::SetEnvironmentVariable("HERMES_HOME", $HermesHome, "User")
        Write-Success "Set HERMES_HOME=$HermesHome"
    }
    $env:HERMES_HOME = $HermesHome
    
    # Update current session
    $env:Path = "$hermesBin;$env:Path"
    
    Write-Success "hermes command ready"
}

function Copy-ConfigTemplates {
    Write-Info "Setting up configuration files..."
    
    # Create ~/.hermes directory structure
    New-Item -ItemType Directory -Force -Path "$HermesHome\cron" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\sessions" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\logs" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\pairing" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\hooks" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\image_cache" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\audio_cache" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\memories" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\skills" | Out-Null
    New-Item -ItemType Directory -Force -Path "$HermesHome\whatsapp\session" | Out-Null
    
    # Create .env
    $envPath = "$HermesHome\.env"
    if (-not (Test-Path $envPath)) {
        $examplePath = "$InstallDir\.env.example"
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $envPath
            Write-Success "Created ~/.hermes/.env from template"
        } else {
            New-Item -ItemType File -Force -Path $envPath | Out-Null
            Write-Success "Created ~/.hermes/.env"
        }
    } else {
        Write-Info "~/.hermes/.env already exists, keeping it"
    }
    
    # Create config.yaml
    $configPath = "$HermesHome\config.yaml"
    if (-not (Test-Path $configPath)) {
        $examplePath = "$InstallDir\cli-config.yaml.example"
        if (Test-Path $examplePath) {
            Copy-Item $examplePath $configPath
            Write-Success "Created ~/.hermes/config.yaml from template"
        }
    } else {
        Write-Info "~/.hermes/config.yaml already exists, keeping it"
    }
    
    # Create SOUL.md if it doesn't exist (global persona file)
    $soulPath = "$HermesHome\SOUL.md"
    if (-not (Test-Path $soulPath)) {
        @"
You are Hermes Agent, an intelligent AI assistant created by Nous Research.
You are helpful, knowledgeable, and direct. You assist users with a wide
range of tasks including answering questions, writing and editing code,
analyzing information, creative work, and executing actions via your tools.
You communicate clearly, admit uncertainty when appropriate, and prioritize
being genuinely useful over being verbose unless otherwise directed below.
Be targeted and efficient in your exploration and investigations.
Do not claim to be Claude Code, Codex, OpenClaw, or any other agent product.
If asked who you are, identify yourself simply as Hermes Agent.
"@ | Set-Content -Path $soulPath -Encoding UTF8
        Write-Success "Created ~/.hermes/SOUL.md (edit to customize personality)"
    }
    
    Write-Success "Configuration directory ready: ~/.hermes/"
    
    # Seed bundled skills into ~/.hermes/skills/ (manifest-based, one-time per skill)
    Write-Info "Syncing bundled skills to ~/.hermes/skills/ ..."
    $pythonExe = "$InstallDir\venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        try {
            & $pythonExe "$InstallDir\tools\skills_sync.py" 2>$null
            Write-Success "Skills synced to ~/.hermes/skills/"
        } catch {
            # Fallback: simple directory copy
            $bundledSkills = "$InstallDir\skills"
            $userSkills = "$HermesHome\skills"
            if ((Test-Path $bundledSkills) -and -not (Get-ChildItem $userSkills -Exclude '.bundled_manifest' -ErrorAction SilentlyContinue)) {
                Copy-Item -Path "$bundledSkills\*" -Destination $userSkills -Recurse -Force -ErrorAction SilentlyContinue
                Write-Success "Skills copied to ~/.hermes/skills/"
            }
        }
    }
}

function Install-NodeDeps {
    if (-not $HasNode) {
        Write-Info "Skipping Node.js dependencies (Node not installed)"
        return
    }
    
    Push-Location $InstallDir
    
    if (Test-Path "package.json") {
        Write-Info "Installing Node.js dependencies (browser tools)..."
        $npmExe = (Get-Command npm -ErrorAction SilentlyContinue).Source
        if ($npmExe -and (Invoke-InstallerCommandWithTimeout -FilePath $npmExe -ArgumentList @("install", "--silent") -Description "npm install for browser tools" -TimeoutSeconds 60)) {
            Write-Success "Node.js dependencies installed"
        } else {
            Write-Warn "npm install skipped or failed (browser tools may not work)"
        }
    }
    
    # Install WhatsApp bridge dependencies
    $bridgeDir = "$InstallDir\scripts\whatsapp-bridge"
    if (Test-Path "$bridgeDir\package.json") {
        Write-Info "Installing WhatsApp bridge dependencies..."
        Push-Location $bridgeDir
        $npmExe = (Get-Command npm -ErrorAction SilentlyContinue).Source
        if ($npmExe -and (Invoke-InstallerCommandWithTimeout -FilePath $npmExe -ArgumentList @("install", "--silent") -Description "npm install for WhatsApp bridge" -TimeoutSeconds 60)) {
            Write-Success "WhatsApp bridge dependencies installed"
        } else {
            Write-Warn "WhatsApp bridge npm install skipped or failed (WhatsApp may not work)"
        }
        Pop-Location
    }
    
    Pop-Location
}

function Invoke-SetupWizard {
    if ($SkipSetup) {
        Write-Info "Skipping setup wizard (-SkipSetup)"
        return
    }

    Write-Host ""
    Write-Info "Skipping automatic setup during install."
    Write-Info "Run 'hermes setup' in a new terminal after installation."
    Write-Host ""
}

function Start-GatewayIfConfigured {
    $envPath = "$HermesHome\.env"
    if (-not (Test-Path $envPath)) { return }

    $hasMessaging = $false
    $content = Get-Content $envPath -ErrorAction SilentlyContinue
    foreach ($var in @("TELEGRAM_BOT_TOKEN", "DISCORD_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "WHATSAPP_ENABLED")) {
        $match = $content | Where-Object { $_ -match "^${var}=.+" -and $_ -notmatch "your-token-here" }
        if ($match) { $hasMessaging = $true; break }
    }

    if (-not $hasMessaging) { return }

    $hermesCmd = "$InstallDir\venv\Scripts\hermes.exe"
    if (-not (Test-Path $hermesCmd)) {
        $hermesCmd = "hermes"
    }

    # If WhatsApp is enabled but not yet paired, run foreground for QR scan
    $whatsappEnabled = $content | Where-Object { $_ -match "^WHATSAPP_ENABLED=true" }
    $whatsappSession = "$HermesHome\whatsapp\session\creds.json"
    if ($whatsappEnabled -and -not (Test-Path $whatsappSession)) {
        Write-Host ""
        Write-Info "WhatsApp is enabled but not yet paired."
        Write-Info "Running 'hermes whatsapp' to pair via QR code..."
        Write-Host ""
        $response = Read-Host "Pair WhatsApp now? [Y/n]"
        if ($response -eq "" -or $response -match "^[Yy]") {
            try {
                & $hermesCmd whatsapp
            } catch {
                # Expected after pairing completes
            }
        }
    }

    Write-Host ""
    Write-Info "Messaging platform token detected!"
    Write-Info "The gateway handles messaging platforms and cron job execution."
    Write-Host ""
    $response = Read-Host "Would you like to start the gateway now? [Y/n]"

    if ($response -eq "" -or $response -match "^[Yy]") {
        Write-Info "Starting gateway in background..."
        try {
            $logFile = "$HermesHome\logs\gateway.log"
            Start-Process -FilePath $hermesCmd -ArgumentList "gateway" `
                -RedirectStandardOutput $logFile `
                -RedirectStandardError "$HermesHome\logs\gateway-error.log" `
                -WindowStyle Hidden
            Write-Success "Gateway started! Your bot is now online."
            Write-Info "Logs: $logFile"
            Write-Info "To stop: close the gateway process from Task Manager"
        } catch {
            Write-Warn "Failed to start gateway. Run manually: hermes gateway"
        }
    } else {
        Write-Info "Skipped. Start the gateway later with: hermes gateway"
    }
}

function Write-Completion {
    $currentSessionCommand = "& '$InstallDir\venv\Scripts\hermes.exe'"
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "                Installation Complete                       " -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your files:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   Config:    " -NoNewline -ForegroundColor Yellow
    Write-Host "$HermesHome\config.yaml"
    Write-Host "   API Keys:  " -NoNewline -ForegroundColor Yellow
    Write-Host "$HermesHome\.env"
    Write-Host "   Data:      " -NoNewline -ForegroundColor Yellow
    Write-Host "$HermesHome\cron, sessions, logs"
    Write-Host "   Code:      " -NoNewline -ForegroundColor Yellow
    Write-Host $InstallDir
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   hermes              " -NoNewline -ForegroundColor Green
    Write-Host "Start chatting"
    Write-Host "   hermes setup        " -NoNewline -ForegroundColor Green
    Write-Host "Configure API keys and settings"
    Write-Host "   hermes config       " -NoNewline -ForegroundColor Green
    Write-Host "View or edit configuration"
    Write-Host "   hermes gateway      " -NoNewline -ForegroundColor Green
    Write-Host "Start messaging gateway (Telegram, Discord, etc.)"
    Write-Host "   hermes update       " -NoNewline -ForegroundColor Green
    Write-Host "Update to latest version"
    Write-Host ""
    Write-Host "Restart your terminal for PATH changes to take effect." -ForegroundColor Yellow
    Write-Host "If you stay in this same PowerShell window, Hermes may still read old ~/.hermes settings." -ForegroundColor Yellow
    Write-Host "To use the new install right now in this window:" -ForegroundColor Yellow
    Write-Host "  `$env:HERMES_HOME = '$HermesHome'" -ForegroundColor Yellow
    Write-Host "  `$env:HERMES_GIT_BASH_PATH = '$GitBashPath'" -ForegroundColor Yellow
    Write-Host "  $currentSessionCommand setup" -ForegroundColor Yellow
    Write-Host ""
    if (-not $HasNode) {
        Write-Host "Note: Node.js could not be installed automatically." -ForegroundColor Yellow
        Write-Host "Browser tools need Node.js. Install manually:" -ForegroundColor Yellow
        Write-Host "  https://nodejs.org/en/download/" -ForegroundColor Yellow
        Write-Host ""
    }
    if (-not $HasRipgrep) {
        Write-Host "Note: ripgrep (rg) was not installed. For faster file search:" -ForegroundColor Yellow
        Write-Host "  winget install BurntSushi.ripgrep.MSVC" -ForegroundColor Yellow
        Write-Host ""
    }
}


# ============================================================================
# Main
# ============================================================================

function Main {
    Write-Banner
    
    if (-not (Install-Uv)) { throw "uv installation failed - cannot continue" }
    if (-not (Test-Python)) { throw "Python $PythonVersion not available - cannot continue" }
    if (-not (Test-Git)) { throw "Git not found - install from https://git-scm.com/download/win" }
    [void](Test-Node)              # Auto-installs if missing
    Install-SystemPackages         # ripgrep + ffmpeg in one step
    
    Install-Repository
    Install-Venv
    Install-Dependencies
    Install-NodeDeps
    Set-PathVariable
    Copy-ConfigTemplates
    Invoke-SetupWizard
    Start-GatewayIfConfigured
    
    Write-Completion
}

# Wrap in try/catch so errors don't kill the terminal when run via:
#   irm https://...install.ps1 | iex
# (exit/throw inside iex kills the entire PowerShell session)
try {
    Main
} catch {
    Write-Host ""
    Write-Err "Installation failed: $_"
    Write-Host ""
    Write-Info "If the error is unclear, try downloading and running the script directly:"
    Write-Host "  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/pengchengxia75-arch/hermes-agent-windows/main/scripts/install.ps1' -OutFile install.ps1" -ForegroundColor Yellow
    Write-Host "  .\install.ps1" -ForegroundColor Yellow
    Write-Host ""
}
