#!/bin/bash
# validate.sh — Comprehensive health check for the Pvragon AI Workspace.
# Verifies directory structure (Functional Topology), git repository
# connections, toolchain, and secrets scaffolding.
#
# Failure philosophy:
#   FAIL = structural problems setup should have prevented (missing dirs/repos)
#   WARN = provisionable-after-setup items (CLI tools, tokens) — actionable,
#          but they must not crash a fresh install's final validation step.

set -e

WORKSPACE_ROOT="$HOME/ai-workspace"
FAILURES=0
WARNINGS=0

# npm-type tools install to the user-level prefix (see configure_toolchain.sh);
# make sure this shell can see them even if ~/.bashrc hasn't been re-sourced.
export PATH="$HOME/.npm-global/bin:$PATH"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# NOTE: use FAILURES=$((FAILURES+1)), never ((FAILURES++)) — the latter
# returns exit status 1 when the pre-increment value is 0, which kills the
# whole script under `set -e` at the FIRST failed check.
log_pass() { echo -e "${GREEN}✅ PASS:${NC} $1"; }
log_fail() { echo -e "${RED}❌ FAIL:${NC} $1"; FAILURES=$((FAILURES+1)); }
log_warn() { echo -e "${YELLOW}⚠️  WARN:${NC} $1"; WARNINGS=$((WARNINGS+1)); }
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
        log_warn "MCP server not configured: $name (run _admin/configure_toolchain.sh)"
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

    local actual_remote
    actual_remote=$(git -C "$path" remote get-url origin 2>/dev/null || echo "none")

    # expected_remote may be a |-separated set: a workspace can legitimately be
    # installed from the private team repo OR from the public reference repo, and
    # hard-coding one of them fails every install of the other.
    if [[ "$expected_remote" == *"|"* ]]; then
        local IFS='|' candidate
        for candidate in $expected_remote; do
            if [[ "$actual_remote" == *"$candidate"* ]]; then
                log_pass "$dir connected to $candidate"
                return
            fi
        done
        log_fail "$dir remote mismatch. Expected one of: $expected_remote, Found: $actual_remote"
        return
    fi

    if [[ -z "$expected_remote" ]]; then
        # Generic check: any remote is fine (your fork, your own repo, etc.)
        if [[ "$actual_remote" != "none" ]]; then
            log_pass "$dir is a git repository (remote: $actual_remote)"
        else
            log_warn "$dir has no git remote configured — add one for backup (gh repo create)"
        fi
        return
    fi

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
if [[ -f "$WORKSPACE_ROOT/personal/secrets/.env" ]]; then
    log_pass "Found personal/secrets/.env"
    # Warn on required-but-empty keys (see .env.template for the full list)
    for key in BASEROW_MCP_TOKEN; do
        if grep -qE "^${key}=.+" "$WORKSPACE_ROOT/personal/secrets/.env" 2>/dev/null; then
            log_pass "Secret set: $key"
        else
            log_warn "Secret not set: $key (edit personal/secrets/.env — see .env.template)"
        fi
    done
else
    log_warn "Missing personal/secrets/.env — copy from .env.template and fill in your keys"
fi

echo "----------------------------------------"

# 2. Layer 1: Team Lib
echo "Checking Layer 1: Team Lib..."
check_dir "team-lib"
check_git_repo "team-lib" "pvragon-ai-library|ai-workspace-reference"

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

# External skill packs.
#
# The property that matters is CONTENT, not mechanism. This block used to test for a
# `.git` inside each pack — i.e. "is this a submodule?" — and hard-coded three pack
# names. Both were wrong: an install from the public reference repo carries the packs as
# plain directories, so three fully-populated packs were reported empty (measured in
# public_workspace_container_test.sh, 2026-08-01), and .gitmodules has since grown past
# the three that were listed here.
#
# Severity splits on which kind of install this is, because the answer differs:
#   .gitmodules present  -> a team install; every declared pack MUST have content (FAIL)
#   no .gitmodules       -> a published install; packs are out of scope there (WARN)
EXT_DIR="$WORKSPACE_ROOT/team-lib/skills/_external"
pack_has_content() { [[ -n "$(find "$1" -name 'SKILL.md' -print -quit 2>/dev/null)" ]]; }

if [[ -f "$WORKSPACE_ROOT/team-lib/.gitmodules" ]]; then
    declared=$(git -C "$WORKSPACE_ROOT/team-lib" config -f .gitmodules \
        --get-regexp '^submodule\..*\.path$' 2>/dev/null | awk '{print $2}')
    if [[ -z "$declared" ]]; then
        log_warn "team-lib/.gitmodules declares no submodules — nothing to check"
    fi
    for path in $declared; do
        pack=$(basename "$path")
        if pack_has_content "$WORKSPACE_ROOT/team-lib/$path"; then
            log_pass "External skill pack populated: $pack"
        else
            log_fail "External skill pack empty: $pack — run: git -C ~/ai-workspace/team-lib submodule update --init --recursive"
        fi
    done
elif [[ -d "$EXT_DIR" ]] && pack_has_content "$EXT_DIR"; then
    log_pass "External skill packs present (published install, no submodules)"
else
    log_warn "No external skill packs — skills that depend on them (e.g. the humanizer gate) will not resolve"
fi

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
check_git_repo "my-lib"   # generic: any remote OK, none = warn

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
check_dir "my-lib/runtime/.tmp"
check_dir "my-lib/runtime/logs"
check_dir "my-lib/skills"

echo "----------------------------------------"

# 4. Layer 3: Projects + agents
echo "Checking Layer 3: Projects..."
check_dir "projects"
check_dir "agents"

echo "----------------------------------------"

# 4b. Agent memory system
#
# A missing memory install is invisible: the library looks complete, the agent
# answers normally, and it simply never remembers anything. So it gets a check.
#
# Severity depends on whether an agent exists yet, because setup CANNOT install
# memory before the choose-name ceremony:
#   no agent   -> WARN (deferred; a legitimate post-setup to-do)
#   agent, unwired -> FAIL (the installer should have run and did not)
echo "Checking Agent Memory..."
MEM_EXEC="$WORKSPACE_ROOT/team-lib/executions"
MEM_INSTALLER="$WORKSPACE_ROOT/team-lib/_admin/install_memory.sh"

if [[ ! -d "$MEM_EXEC" ]]; then
    log_warn "team-lib/executions missing — cannot check the memory system"
elif python3 "$MEM_EXEC/agent_paths.py" --json &>/dev/null; then
    AGENT_HOME=$(python3 -c "import sys; sys.path.insert(0,'$MEM_EXEC'); import agent_paths; print(agent_paths.agent_home())" 2>/dev/null || echo "")
    log_pass "Agent home resolved: ${AGENT_HOME:-unknown}"

    # Hooks — the reinforcement half. Registered in the harness, not the workspace.
    hooks_missing=""
    for hook in update_memory_access.py inject_lens.py allow_memory_writes.py; do
        if grep -q "$hook" "$HOME/.claude/settings.json" 2>/dev/null; then
            log_pass "Memory hook registered: $hook"
        else
            hooks_missing="yes"
            log_fail "Memory hook NOT registered: $hook — run: bash $MEM_INSTALLER"
        fi
    done

    # Index — the data half. Its absence means bootstrap never ran.
    if [[ -n "$AGENT_HOME" && -f "$AGENT_HOME/memory/MEMORY.md" ]]; then
        log_pass "Memory index present: MEMORY.md"
    else
        log_fail "No memory/MEMORY.md — run: bash $MEM_INSTALLER"
    fi

    # Cron — soft by design: some hosts schedule differently (verify_memory_install
    # treats it the same way), so a missing entry is a to-do, not a broken install.
    if crontab -l 2>/dev/null | grep -q "pvragon-memory"; then
        log_pass "Nightly dream cycle scheduled (cron)"
    else
        log_warn "No nightly dream-cycle cron — run: bash $MEM_INSTALLER"
    fi
else
    log_warn "No agent named yet — memory install deferred (expected on a fresh setup)"
    log_info "   After GETTING_STARTED.md Phase 7 (choose-name), run: bash $MEM_INSTALLER"
fi

echo "----------------------------------------"

# 4c. Skill exposure
#
# A library the harness cannot see is not a library. ~/.claude/skills is the only path the
# harness reads; shared skills reach it as pointers inside the personal layer. Both links
# were previously created by hand, so this was invisible on any established machine.
echo "Checking Skill Exposure..."
if [[ ! -e "$HOME/.claude/skills" ]]; then
    log_fail "~/.claude/skills does not exist — the agent can invoke NO skills. Run: python3 $WORKSPACE_ROOT/team-lib/executions/link_skills.py"
else
    log_pass "Harness skill path present: ~/.claude/skills"
    visible=$(find -L "$HOME/.claude/skills" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)
    shared=$(find "$WORKSPACE_ROOT/team-lib/skills" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l)
    if [[ "$visible" -eq 0 ]]; then
        log_fail "No skills visible to the harness — run: python3 $WORKSPACE_ROOT/team-lib/executions/link_skills.py"
    elif [[ "$shared" -gt 0 && "$visible" -lt "$shared" ]]; then
        log_warn "Only $visible skill(s) visible to the harness; team-lib alone ships $shared — run: python3 $WORKSPACE_ROOT/team-lib/executions/link_skills.py"
    else
        log_pass "Skills visible to the harness: $visible"
    fi
fi

# 4d. Status line
if [[ -e "$HOME/.claude/statusline.sh" ]]; then
    log_pass "Status line installed"
else
    log_warn "No status line — context %, rate-limit clocks and the findings count are invisible. Run: bash $WORKSPACE_ROOT/team-lib/_admin/install_statusline.sh"
fi

echo "----------------------------------------"

# 5. Toolchain
echo "Checking Toolchain..."
# Node major version gates the two required npm CLIs (claude, gws): both declare
# engines node>=22, and Ubuntu 24.04's apt ships 18.
node_major=$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || true)
if [[ -z "${node_major:-}" ]]; then
    log_warn "Node.js not installed — required by claude and gws (re-run _admin/setup_system.sh)"
elif [[ "$node_major" -lt 22 ]]; then
    log_warn "Node $(node -v) is below the v22 that claude and gws require — re-run: sudo _admin/setup_system.sh"
else
    log_pass "Node.js $(node -v)"
fi

check_cli_tool "gh" "gh --version" "sudo apt-get install -y gh, then: gh auth login"
check_cli_tool "gws" "gws --version" "npm install -g @googleworkspace/cli, then: gws auth login"
check_cli_tool "claude" "claude --version" "npm install -g @anthropic-ai/claude-code"
check_cli_tool "restish" "restish --version" "used by ClickUp API workflows; install when needed"
if [[ -f "$HOME/.claude.json" ]]; then
    # Required MCP servers (keep in sync with toolchain.yaml required: true)
    check_mcp_server "clickup"
    check_mcp_server "baserow"
else
    log_info "~/.claude.json not found — skipping MCP validation"
fi
echo "----------------------------------------"

if [[ $FAILURES -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "${GREEN}✨ All checks passed! Workspace is valid.${NC}"
    exit 0
elif [[ $FAILURES -eq 0 ]]; then
    echo -e "${YELLOW}✅ Structure valid — $WARNINGS warning(s) above are post-setup to-dos.${NC}"
    exit 0
else
    echo -e "${RED}⚠️  Validation failed with $FAILURES error(s) and $WARNINGS warning(s).${NC}"
    exit 1
fi
