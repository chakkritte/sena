# CarbonClaw One-Line Installer for Windows
# Requires: Python 3.12+, git, uv

Write-Host "🤖 Installing CarbonClaw..." -ForegroundColor Cyan

# 1. Determine if we are already inside the CarbonClaw repository root
$isRepoRoot = $false
if (Test-Path "pyproject.toml") {
    $content = Get-Content "pyproject.toml" -Raw
    if ($content -match 'name = "carbonclaw"') {
        Write-Host "🌿 Detected CarbonClaw repository root. Skipping clone." -ForegroundColor Green
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
        Write-Host "🔄 Updating repository..." -ForegroundColor Cyan
        git pull origin main
        if (-not $?) {
            Write-Host "⚠️ Git pull failed. Continuing with local codebase..." -ForegroundColor Yellow
        }
    }
}

# 2. Check for uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 'uv' not found. Please install it first: https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Red
    Write-Host "Tip: You can install uv in PowerShell via:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Yellow
    return
}

# 3. Setup environment and dependencies
Write-Host "📦 Syncing dependencies (this may take a minute or two)..." -ForegroundColor Cyan
uv sync --all-extras
if (-not $?) {
    Write-Host "❌ uv sync failed." -ForegroundColor Red
    return
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
