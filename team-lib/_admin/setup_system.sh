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
# python3-yaml is REQUIRED: _admin/parse_toolchain.py imports yaml with the
# system python3 — without this package, toolchain provisioning crashes.
run_cmd "apt-get install -y python3 python3-pip python3-venv python3-yaml"

# Node.js
#
# Ubuntu 24.04 ships Node 18.19. Both required npm tools — @anthropic-ai/claude-code and
# @googleworkspace/cli — declare `engines: node >= 22`, so apt's Node leaves the two CLIs
# this workspace is built around running on an engine their authors do not support.
#
# The key is FETCHED and dearmored, never piped into a shell. `curl … | bash` is exactly
# the dropper shape skills/scan-for-malware exists to eradicate, and an installer that
# teaches the habit is worse than the version it fixes.
echo "    ... Node.js 22 and npm"
node_major=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/')
if [[ -n "${node_major:-}" && "$node_major" -ge 22 ]]; then
    echo "        Node $(node -v) already satisfies >= 22"
elif [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] add NodeSource repo for Node 22, then apt-get install -y nodejs"
else
    nodesource_ok=true
    apt-get install -y ca-certificates curl gnupg >/dev/null 2>&1 || nodesource_ok=false
    install -m 0755 -d /etc/apt/keyrings
    if [[ "$nodesource_ok" == "true" ]] \
        && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
             | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg 2>/dev/null; then
        chmod a+r /etc/apt/keyrings/nodesource.gpg
        echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
            > /etc/apt/sources.list.d/nodesource.list
        apt-get update -qq
        apt-get install -y nodejs || nodesource_ok=false
    else
        nodesource_ok=false
    fi
    if [[ "$nodesource_ok" != "true" ]]; then
        echo "    ⚠️  NodeSource unavailable — falling back to the distro's Node."
        echo "        Claude Code and gws require Node >= 22 and may misbehave on it."
        rm -f /etc/apt/sources.list.d/nodesource.list
        apt-get update -qq
        run_cmd "apt-get install -y nodejs npm"
    fi
fi

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
check_tool "gh" "gh --version | head -n 1"

echo ""

if [[ "$has_error" == "true" ]]; then
    echo "⚠️  Setup finished with errors. Some tools are missing."
    exit 1
else
    echo "✨ System setup complete! You are ready to run setup_workspace.sh."
    exit 0
fi
