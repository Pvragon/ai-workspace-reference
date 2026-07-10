#!/usr/bin/env bash
#
# setup_system.sh
# Installs core OS dependencies for the Pvragon AI Workspace.
#
# Usage: sudo ./setup_system.sh [--dry-run]
#

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "🔍 DRY RUN: No changes will be made."
fi

if [[ $EUID -ne 0 ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "⚠️  [DRY-RUN] Not running as root. Installation commands would fail in real run."
    else
        echo "❌ Error: This script must be run as root (sudo)."
        echo "   Usage: sudo ./setup_system.sh"
        exit 1
    fi
fi

echo "=== System Setup for AI Workspace ==="

if ! command -v apt-get &> /dev/null; then
    echo "❌ Error: 'apt-get' not found. This script supports Debian/Ubuntu systems."
    exit 1
fi

# Helper to run or dry-run commands
run_cmd() {
    local cmd="$*"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[DRY-RUN] $cmd"
    else
        echo "EXEC: $cmd"
        eval "$cmd"
    fi
}

echo "--> Updating package sources..."
run_cmd "apt-get update"

echo "--> Installing core utilities..."
# curl, wget, unzip, jq, tree, build-essential, software-properties-common, ripgrep, sqlite3
run_cmd "apt-get install -y curl wget unzip jq tree build-essential software-properties-common ripgrep sqlite3 gh"

echo "--> Installing Runtime Dependencies..."

# Git
echo "    ... Git"
run_cmd "apt-get install -y git"

# Python
echo "    ... Python3, Pip, Venv"
run_cmd "apt-get install -y python3 python3-pip python3-venv python3-yaml"

# Node.js
echo "    ... Node.js and npm"
run_cmd "apt-get install -y nodejs npm"

if [[ "$DRY_RUN" == "true" ]]; then
    echo ""
    echo "✅ Dry run complete. No changes made."
    exit 0
fi

echo ""
echo "=== Validation ==="
has_error=false

check_tool() {
    local tool="$1"
    local cmd="$2"
    if command -v "$tool" &> /dev/null; then
        echo "✅ $tool: $($cmd)"
    else
        echo "❌ $tool: MISSING"
        has_error=true
    fi
}

check_tool "git" "git --version"
check_tool "python3" "python3 --version"
check_tool "pip3" "pip3 --version"
check_tool "node" "node --version"
check_tool "npm" "npm --version"
check_tool "rg" "rg --version | head -n 1"
check_tool "sqlite3" "sqlite3 --version"

echo ""

if [[ "$has_error" == "true" ]]; then
    echo "⚠️  Setup finished with errors. Some tools are missing."
    exit 1
else
    echo "✨ System setup complete! You are ready to run setup_workspace.sh."
    exit 0
fi
