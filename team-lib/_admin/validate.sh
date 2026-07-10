#!/bin/bash
# validate.sh — Comprehensive health check for the Pvragon AI Workspace.
# Verifies directory structure (Functional Topology) and Git repository connections.

set -e

WORKSPACE_ROOT="$HOME/ai-workspace"
FAILURES=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

log_pass() { echo -e "${GREEN}✅ PASS:${NC} $1"; }
log_fail() { echo -e "${RED}❌ FAIL:${NC} $1"; FAILURES=$((FAILURES+1)); }
log_warn() { echo -e "${YELLOW}⚠️  WARN:${NC} $1"; }
log_info() { echo "ℹ️  $1"; }

check_dir() {
    local dir="$1"
    if [[ -d "$WORKSPACE_ROOT/$dir" ]]; then
        log_pass "Found $dir"
    else
        log_fail "Missing directory: $dir"
    fi
}

check_cli_tool() {
    local name="$1" cmd="$2" hint="${3:-}"
    if eval "$cmd" &>/dev/null; then
        log_pass "CLI tool: $name"
    else
        # Warn, don't fail: CLI tools are provisionable after setup
        # (configure_toolchain.sh) and some are integration-specific.
        log_warn "CLI tool not installed: $name${hint:+ — $hint}"
    fi
}

check_mcp_server() {
    local name="$1"
    if [[ -f "$HOME/.claude.json" ]] && jq -e ".mcpServers.\"$name\"" "$HOME/.claude.json" &>/dev/null; then
        log_pass "MCP server: $name"
    else
        log_fail "MCP server missing: $name"
    fi
}

check_git_repo() {
    local dir="$1"
    local expected_remote="${2:-}"   # optional: substring the remote should contain
    local path="$WORKSPACE_ROOT/$dir"

    if [[ ! -e "$path/.git" ]]; then
        log_fail "$dir is not a git repository (missing .git)"
        return
    fi

    # Check remote origin
    local actual_remote=$(git -C "$path" remote get-url origin 2>/dev/null || echo "none")

    if [[ -z "$expected_remote" ]]; then
        # Generic check: any remote is fine (your fork, your own repo, etc.)
        if [[ "$actual_remote" != "none" ]]; then
            log_pass "$dir is a git repository (remote: $actual_remote)"
        else
            log_warn "$dir has no git remote configured — add one for backup"
        fi
        return
    fi

    # Normalize URLs for comparison (remove .git suffix, handle ssh vs https)
    # Simple check: does it contain the repo name?
    if [[ "$actual_remote" == *"$expected_remote"* ]]; then
        log_pass "$dir connected to $expected_remote"
    else
        log_fail "$dir remote mismatch. Expected: $expected_remote, Found: $actual_remote"
    fi
}

echo "🔍 Validating workspace at $WORKSPACE_ROOT..."
echo "----------------------------------------"

# 1. Layer 0: Personal
echo "Checking Layer 0: Personal..."
check_dir "personal"
check_dir "personal/notes"
check_dir "personal/preferences"
check_dir "personal/scratch"
check_dir "personal/secrets"

echo "----------------------------------------"

# 2. Layer 1: Team Lib
echo "Checking Layer 1: Team Lib..."
check_dir "team-lib"
check_git_repo "team-lib"   # any remote is valid — your fork of ai-workspace-reference or your own team repo

# Subdirectories
check_dir "team-lib/_admin"
check_dir "team-lib/context/global"
check_dir "team-lib/context/indexed"
check_dir "team-lib/directives"
check_dir "team-lib/executions"
check_dir "team-lib/harnesses"
check_dir "team-lib/logs"
check_dir "team-lib/personas"
check_dir "team-lib/registry"
check_dir "team-lib/skills"
check_dir "team-lib/skills/_external"
check_dir "team-lib/skills/_external/anthropics"
check_git_repo "team-lib/skills/_external/anthropics" "anthropics/skills"
check_dir "team-lib/skills/_external/rezvani-claude-skills"
check_git_repo "team-lib/skills/_external/rezvani-claude-skills" "alirezarezvani/claude-skills"

# Governance Directive
if [[ -f "$WORKSPACE_ROOT/team-lib/directives/team-library-governance.md" ]]; then
    log_pass "Found team-library-governance.md"
else
    log_fail "Missing governance directive: team-lib/directives/team-library-governance.md"
fi

echo "----------------------------------------"

# 3. Layer 2: My Lib
echo "Checking Layer 2: My Lib..."
check_dir "my-lib"
check_git_repo "my-lib"   # any remote is valid — your own private repo

# Subdirectories
check_dir "my-lib/archive"
check_dir "my-lib/backlog"
check_dir "my-lib/config"
check_dir "my-lib/context/global"
check_dir "my-lib/context/indexed"
check_dir "my-lib/directives"
check_dir "my-lib/executions"
check_dir "my-lib/harnesses"
check_dir "my-lib/logs"
check_dir "my-lib/personas"
check_dir "my-lib/registry"
check_dir "my-lib/runtime"
check_dir "my-lib/runtime/deliverables"
check_dir "my-lib/runtime/intermediates"
check_dir "my-lib/runtime/logs"
check_dir "my-lib/skills"

echo "----------------------------------------"

# 4. Layer 3: Projects
echo "Checking Layer 3: Projects..."
check_dir "projects"

echo "----------------------------------------"

# 5. Toolchain
echo "Checking Toolchain..."
check_cli_tool "gh" "gh --version" "install: sudo apt-get install -y gh"
check_cli_tool "gws" "gws --version" "optional, Google Workspace integration: npm install -g @googleworkspace/cli"
check_cli_tool "restish" "restish --version" "optional, REST-API integrations: https://rest.sh"
if [[ -f "$HOME/.claude.json" ]]; then
    # Baserow is optional (see toolchain.yaml) — informational only
    if jq -e '.mcpServers."baserow"' "$HOME/.claude.json" &>/dev/null; then
        log_pass "MCP server: baserow (optional)"
    else
        log_info "Optional MCP server not configured: baserow"
    fi
else
    log_info "~/.claude.json not found — skipping MCP validation"
fi
echo "----------------------------------------"

if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}✨ All checks passed! Workspace is valid.${NC}"
    exit 0
else
    echo -e "${RED}⚠️  Validation failed with $FAILURES errors.${NC}"
    exit 1
fi
