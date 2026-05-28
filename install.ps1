# CarbonClaw One-Line Installer for Windows
# Requires: Python 3.12+, git, uv

Write-Host "🤖 Installing CarbonClaw..." -ForegroundColor Cyan

# 1. Determine if we are already inside the CarbonClaw repository root
$isRepoRoot = $false
if (Test-Path "pyproject.toml") {
    $content = Get-Content "pyproject.toml" -Raw
    if ($content -match 'name = "carbonclaw"') {
        Write-Host "🌿 Detected CarbonClaw repository root. Skipping clone." -ForegroundColor Green
        Write-Host "🧹 Cleaning local repository..." -ForegroundColor Cyan
        git restore .
        $isRepoRoot = $true
    }
}

if (-not $isRepoRoot) {
    if (-not (Test-Path "carbonclaw")) {
        Write-Host "📥 Cloning CarbonClaw repository..." -ForegroundColor Cyan
        git clone https://github.com/chakkritte/carbonclaw.git
        if (-not $?) {
            Write-Host "❌ Failed to clone repository." -ForegroundColor Red
            return
        }
        Set-Location carbonclaw
    } else {
        Write-Host "📂 Entering existing carbonclaw directory..." -ForegroundColor Cyan
        Set-Location carbonclaw
        # Safety check: if we entered the package directory instead of the repo root, step up
        if (-not (Test-Path "pyproject.toml") -and (Test-Path "..\pyproject.toml")) {
            Set-Location ..
        }
        Write-Host "🧹 Cleaning local repository..." -ForegroundColor Cyan
        git restore .
        Write-Host "🔄 Updating repository..." -ForegroundColor Cyan
        git pull origin main
        if (-not $?) {
            Write-Host "⚠️ Git pull failed. Continuing with local codebase..." -ForegroundColor Yellow
        }
    }
}

# 2. Check for and auto-install uv if missing
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "🔍 'uv' not found. Installing 'uv' automatically..." -ForegroundColor Yellow
    try {
        # Execute Astral's official PowerShell installer
        Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)
        
        # Refresh the current session's PATH environment variables
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
        
        # Double check if uv can be found now
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            # Check default path if the path refresh wasn't fully reflected
            $defaultUvBin = Join-Path $HOME ".local\bin"
            $defaultUvPath = Join-Path $defaultUvBin "uv.exe"
            if (Test-Path $defaultUvPath) {
                $env:Path += ";$defaultUvBin"
            }
        }
    } catch {
        Write-Host "❌ Failed to install 'uv' automatically." -ForegroundColor Red
        Write-Host "Please install it manually: https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Red
        return
    }

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "❌ 'uv' was installed but could not be located in PATH. Please restart your terminal and run setup again." -ForegroundColor Red
        return
    } else {
        Write-Host "✅ 'uv' installed and configured successfully!" -ForegroundColor Green
    }
}

# 3. Setup environment and dependencies
Write-Host "📦 Syncing dependencies (this may take a minute or two)..." -ForegroundColor Cyan
uv sync --all-extras
if (-not $?) {
    Write-Host "❌ uv sync failed." -ForegroundColor Red
    Write-Host "💡 Troubleshooting Tip: " -ForegroundColor Yellow -NoNewline
    Write-Host "If you encountered 'Access is denied' (os error 5), another process (like VS Code, PyCharm, or an active python terminal) is likely locking the virtual environment (.venv)." -ForegroundColor White
    Write-Host "To resolve this:" -ForegroundColor White
    Write-Host "  1. Close any open code editors, IDEs, or Python processes." -ForegroundColor White
    Write-Host "  2. Manually delete the '.venv' directory by running:" -ForegroundColor White
    Write-Host "     Remove-Item -Recurse -Force .venv" -ForegroundColor Yellow
    Write-Host "  3. Re-run this installer script." -ForegroundColor White
}




# 3.1 Install globally (optional but recommended for global path access)
Write-Host "🌍 Installing 'carbonclaw' command globally..." -ForegroundColor Cyan
uv tool install . --force
if (-not $?) {
    Write-Host "❌ uv tool install failed." -ForegroundColor Red
    return
}

# 4. Install playwright browsers
Write-Host "🌐 Installing browser binaries (downloading Chromium, approx. 120MB)..." -ForegroundColor Cyan
uv run playwright install chromium
if (-not $?) {
    Write-Host "❌ Playwright install failed." -ForegroundColor Red
    return
}

# 5. Done
Write-Host ""
Write-Host "✅ CarbonClaw installed successfully!" -ForegroundColor Green
Write-Host "🚀 Run 'carbonclaw chat' to start." -ForegroundColor Green
