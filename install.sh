#!/bin/bash
set -e

# CarbonClaw One-Line Installer
# Requires: python3.12+, git, uv

echo "🤖 Installing CarbonClaw..."

# 1. Determine if we are already inside the CarbonClaw repository root
if [ -f "pyproject.toml" ] && grep -q 'name = "carbonclaw"' pyproject.toml 2>/dev/null; then
    echo "🌿 Detected CarbonClaw repository root. Skipping clone."
else
    # Clone or enter directory
    if [ ! -d "carbonclaw" ]; then
        echo "📥 Cloning CarbonClaw repository..."
        git clone https://github.com/chakkritte/carbonclaw.git
        cd carbonclaw
    else
        echo "📂 Entering existing carbonclaw directory..."
        cd carbonclaw
        # Safety check: if we entered the package directory instead of the repo root, step up
        if [ ! -f "pyproject.toml" ] && [ -f "../pyproject.toml" ]; then
            cd ..
        fi
        echo "🔄 Updating repository..."
        git pull origin main || echo "⚠️ Git pull failed. Continuing with local codebase..."
    fi
fi

# 2. Check for uv
if ! command -v uv &> /dev/null; then
    echo "❌ 'uv' not found. Please install it first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 3. Setup environment and dependencies
echo "📦 Syncing dependencies (this may take a minute or two)..."
uv sync --all-extras

# 3.1 Install globally (optional but recommended for global path access)
echo "🌍 Installing 'carbonclaw' command globally..."
uv tool install . --force

# 4. Install playwright browsers
echo "🌐 Installing browser binaries (downloading Chromium, approx. 120MB)..."
uv run playwright install chromium

# 5. Done
echo ""
echo "✅ CarbonClaw installed successfully!"
echo "🚀 Run 'uv run carbonclaw chat' to start."

