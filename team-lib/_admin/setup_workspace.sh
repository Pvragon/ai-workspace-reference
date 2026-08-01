#!/usr/bin/env bash
#
# setup_workspace.sh
# User-facing onboarding script for the Pvragon AI Workspace.
# Creates/updates the ai-workspace scaffold with Functional Topology.
# Generates workspace-manifest.yaml and pvragon-workspace.code-workspace.
# Idempotent: running multiple times will NOT overwrite existing user files.
#
set -euo pipefail

WORKSPACE_ROOT="${HOME}/ai-workspace"
MANIFEST_PATH="${HOME}/.ai-workspace-manifest.yaml"

# Helper: create directory if it doesn't exist
ensure_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        echo "Created directory: $dir"
    fi
}

# Helper: create file if it doesn't exist
ensure_file() {
    local file="$1"
    local content="$2"
    if [[ ! -f "$file" ]]; then
        echo "$content" > "$file"
        echo "Created file: $file"
    fi
}

echo "=== Pvragon AI Workspace Setup ==="

# Default Team Library URL (can be overridden via environment)
TEAM_REPO_URL="${TEAM_REPO_URL:-https://github.com/Pvragon/pvragon-ai-library.git}"

# ============================================================================
# TEAM LIBRARY SETUP (Must happen first)
# ============================================================================

TEAM_LIB_DIR="${WORKSPACE_ROOT}/team-lib"

if [[ ! -d "$TEAM_LIB_DIR/.git" ]]; then
    echo ""
    echo "---> Team Library (team-lib) Setup"

    # Create workspace root if needed
    mkdir -p "$WORKSPACE_ROOT"

    if [[ -d "$TEAM_LIB_DIR" ]]; then
        # Directory exists but is not a git repo - back it up
        echo "    ⚠️  team-lib exists but is not a git repo. Backing up..."
        mv "$TEAM_LIB_DIR" "${TEAM_LIB_DIR}.backup.$(date +%s)"
    fi

    echo "    Cloning team-lib from $TEAM_REPO_URL..."
    if git clone --recurse-submodules "$TEAM_REPO_URL" "$TEAM_LIB_DIR"; then
        echo "    ✅ team-lib cloned successfully."
    else
        echo "    ❌ Failed to clone team-lib. Check your network connection and URL."
        echo "    ℹ️  This is a private repo — you must be authenticated first: gh auth login"
        echo "    URL: $TEAM_REPO_URL"
        exit 1
    fi
else
    echo "    team-lib is already a git repository. Pulling latest..."
    git -C "$TEAM_LIB_DIR" pull || echo "    ⚠️  Git pull failed (continuing anyway)."
fi

# External skill packs live as git submodules (skills/_external/*). A plain
# clone leaves them as empty directories, which breaks skills that depend on
# them (e.g. the humanizer gate). Init is idempotent and safe to re-run.
echo "    Initializing external skill packs..."
# Submodules for a team install; a direct clone from upstream for anyone who installed
# from the public reference repo, which does not republish third-party content. One
# script handles both and reads .gitmodules for the pack list either way.
FETCH_PACKS="${TEAM_LIB_DIR}/_admin/fetch_external_skill_packs.sh"
if [[ -f "$FETCH_PACKS" ]]; then
    bash "$FETCH_PACKS" || echo "    ⚠️  Some packs missing — re-run later: bash $FETCH_PACKS"
else
    git -C "$TEAM_LIB_DIR" submodule update --init --recursive \
        || echo "    ⚠️  Submodule init failed — re-run later: git -C $TEAM_LIB_DIR submodule update --init --recursive"
fi

# ============================================================================
# SKILL DEPENDENCIES (npm packages)
# ============================================================================

echo ""
echo "---> Installing skill dependencies"
if command -v npm &> /dev/null; then
    # Find all skills with package.json and install their dependencies
    find "${TEAM_LIB_DIR}/skills" -name "package.json" -type f 2>/dev/null | while read pkg; do
        skill_dir=$(dirname "$pkg")
        skill_name=$(basename "$skill_dir")
        echo "    Installing npm packages for $skill_name..."
        (cd "$skill_dir" && npm install --silent 2>/dev/null) || echo "    ⚠️  npm install failed for $skill_name"
    done
    echo "    ✅ Skill dependencies installed."
else
    echo "    ⚠️  npm not found. Some skills require Node.js dependencies."
    echo "    → Run setup_system.sh first to install Node.js, then re-run this script."
fi

# ============================================================================
# INTEGRATION DEPENDENCIES (npm packages; + headless Chromium for excalidraw-cli)
# ============================================================================

echo ""
echo "---> Installing integration dependencies"
if command -v npm &> /dev/null; then
    # maxdepth 2 so we match integrations/<name>/package.json, never nested node_modules
    find "${TEAM_LIB_DIR}/integrations" -maxdepth 2 -name "package.json" -type f 2>/dev/null | while read pkg; do
        int_dir=$(dirname "$pkg")
        int_name=$(basename "$int_dir")
        echo "    Installing npm packages for $int_name..."
        (cd "$int_dir" && npm install --silent 2>/dev/null) || echo "    ⚠️  npm install failed for $int_name"
    done
    # excalidraw-cli renders Mermaid→Excalidraw via a real browser, so it needs a
    # one-time Chromium download that `npm install` does not fetch (~180MB).
    excal_dir="${TEAM_LIB_DIR}/integrations/excalidraw-cli"
    if [ -d "$excal_dir" ]; then
        echo "    Installing Chromium for excalidraw-cli (one-time, ~180MB)..."
        (cd "$excal_dir" && npx playwright install chromium 2>/dev/null) \
            || echo "    ⚠️  Chromium install failed — run later: cd $excal_dir && npx playwright install chromium"
    fi
    echo "    ✅ Integration dependencies installed."
else
    echo "    ⚠️  npm not found. Some integrations require Node.js dependencies."
fi

# ============================================================================
# DIRECTORY STRUCTURE (Functional Topology)
# ============================================================================

# Layer 0: Personal (human-only)
ensure_dir "${WORKSPACE_ROOT}/personal/notes"
ensure_dir "${WORKSPACE_ROOT}/personal/scratch"
ensure_dir "${WORKSPACE_ROOT}/personal/preferences"
ensure_dir "${WORKSPACE_ROOT}/personal/secrets"

# Layer 1: Team Library — all content comes from the git clone above.
# Do NOT scaffold team-lib subdirectories here: creating empty dirs (especially
# under skills/_external/) masks a broken clone or uninitialized submodules.

# Layer 2: Private Library (Private Repo - personal overlay)
ensure_dir "${WORKSPACE_ROOT}/my-lib/archive"
ensure_dir "${WORKSPACE_ROOT}/my-lib/backlog"
ensure_dir "${WORKSPACE_ROOT}/my-lib/config"
ensure_dir "${WORKSPACE_ROOT}/my-lib/directives"
ensure_dir "${WORKSPACE_ROOT}/my-lib/context/global"
ensure_dir "${WORKSPACE_ROOT}/my-lib/context/indexed"
ensure_dir "${WORKSPACE_ROOT}/my-lib/personas"
ensure_dir "${WORKSPACE_ROOT}/my-lib/skills"
ensure_dir "${WORKSPACE_ROOT}/my-lib/executions"
ensure_dir "${WORKSPACE_ROOT}/my-lib/harnesses"
ensure_dir "${WORKSPACE_ROOT}/my-lib/registry"
ensure_dir "${WORKSPACE_ROOT}/my-lib/logs"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/.tmp"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/.tmp/_archive"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/deliverables"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/deliverables/_archive"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/logs"

# Layer 3: Workbench
ensure_dir "${WORKSPACE_ROOT}/projects"

# Cross-cutting: agent identity & memory. Populated by the choose-name
# ceremony on the agent's first session (see ONBOARDING.md, final phase).
ensure_dir "${WORKSPACE_ROOT}/agents"

# ============================================================================
# GIT IDENTITY (required before any commit can succeed)
# ============================================================================
# A blank machine has no user.name/user.email; the first commit anyone (or any
# agent) makes would die with git's exit-128 identity error. Prompt once here.

if [[ -z "$(git config --global user.name 2>/dev/null || true)" ]]; then
    echo ""
    echo "---> Git identity is not configured yet."
    read -p "    Your full name (for git commits): " git_name
    read -p "    Your work email (for git commits): " git_email
    git config --global user.name "$git_name"
    git config --global user.email "$git_email"
    echo "    ✅ Git identity set."
fi

# Team convention: new repos start on 'main' (fresh git defaults to 'master')
if [[ -z "$(git config --global init.defaultBranch 2>/dev/null || true)" ]]; then
    git config --global init.defaultBranch main
fi

# ============================================================================
# INTERACTIVE MY-LIB SETUP
# ============================================================================

MY_LIB_DIR="${WORKSPACE_ROOT}/my-lib"

if [[ ! -d "$MY_LIB_DIR/.git" ]]; then
    echo ""
    echo "---> Private Library (my-lib) Setup"
    echo "    1) Clone existing repository"
    echo "    2) Create new local repository"
    echo "    3) Skip (use existing directory as-is)"

    valid_choice=false
    while [ "$valid_choice" = false ]; do
        read -p "    Select option [1-3]: " choice
        case $choice in
            1)
                while true; do
                    read -p "    Enter Git Clone URL: " git_url
                    if [ -z "$git_url" ]; then
                        echo "    URL cannot be empty."
                        continue
                    fi

                    # Backup existing directory if it exists
                    if [[ -d "$MY_LIB_DIR" ]]; then
                        mv "$MY_LIB_DIR" "${MY_LIB_DIR}.backup.$(date +%s)"
                    fi

                    if git clone "$git_url" "$MY_LIB_DIR"; then
                        valid_choice=true
                        break
                    else
                        echo "    ❌ Clone failed. Check URL and try again."
                        echo "    (Type 'skip' to skip cloning)"
                        if [[ "$git_url" == "skip" ]]; then
                            echo "    Skipping my-lib clone."
                            mkdir -p "$MY_LIB_DIR"
                            valid_choice=true
                            break
                        fi
                    fi
                done
                ;;
            2)
                echo "    Initializing new git repo..."
                git init "$MY_LIB_DIR"
                ensure_file "$MY_LIB_DIR/.gitignore" "/runtime/
.venv/
node_modules/
__pycache__/
.env
"
                ensure_file "$MY_LIB_DIR/README.md" "# my-lib
Private AI Library.
"
                echo "    ✅ Repo initialized."
                # Offer to create a private GitHub remote so the lab is backed
                # up from day one (requires gh, authenticated).
                if command -v gh &>/dev/null && gh auth status &>/dev/null; then
                    read -p "    Create a private GitHub repo as its remote? [Y/n]: " make_remote
                    if [[ ! "$make_remote" =~ ^[Nn] ]]; then
                        read -p "    Repo name [$(whoami)-ai-library]: " repo_name
                        repo_name="${repo_name:-$(whoami)-ai-library}"
                        (cd "$MY_LIB_DIR" && \
                            git add -A && git commit -qm "Initialize my-lib" && \
                            gh repo create "$repo_name" --private --source=. --remote=origin --push) \
                            && echo "    ✅ Private remote created and pushed." \
                            || echo "    ⚠️  Remote creation failed — you can do it later: gh repo create"
                    fi
                else
                    echo "    ℹ️  Tip: back this up later with: gh repo create $(whoami)-ai-library --private --source=. --push"
                fi
                valid_choice=true
                ;;
            3)
                echo "    Skipping my-lib git setup."
                valid_choice=true
                ;;
            *)
                echo "    Invalid option."
                ;;
        esac
    done
else
    echo "    my-lib is already a git repository. Skipping setup."
fi

# ============================================================================
# PYTHON ENVIRONMENT SETUP
# ============================================================================

echo ""
echo "=== Python Environment Setup ==="

VENV_DIR="${MY_LIB_DIR}/.venv"
BASE_REQS="${WORKSPACE_ROOT}/team-lib/_admin/base-requirements.txt"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "    Creating Python virtual environment at ${VENV_DIR}..."
    python3 -m venv "$VENV_DIR"
    echo "    ✅ Virtual environment created."
else
    echo "    ℹ️  Virtual environment already exists at ${VENV_DIR}"
fi

# Install team-lib base requirements
if [[ -f "$BASE_REQS" ]]; then
    echo "    Installing team-lib base requirements..."
    "$VENV_DIR/bin/pip" install --quiet -r "$BASE_REQS"
    echo "    ✅ Team-lib base requirements installed."
fi

# Install personal requirements if they exist
if [[ -f "${MY_LIB_DIR}/requirements.txt" ]]; then
    echo "    Installing my-lib personal requirements..."
    "$VENV_DIR/bin/pip" install --quiet -r "${MY_LIB_DIR}/requirements.txt"
    echo "    ✅ Personal requirements installed."
fi

# ============================================================================
# TOOLCHAIN PROVISIONING (CLI tools + MCP servers)
# ============================================================================

echo ""
echo "=== Team Toolchain Setup ==="

TOOLCHAIN_SCRIPT="${WORKSPACE_ROOT}/team-lib/_admin/configure_toolchain.sh"
if [[ -f "$TOOLCHAIN_SCRIPT" ]]; then
    # Never let toolchain provisioning abort the rest of setup — it can be
    # re-run standalone at any time.
    bash "$TOOLCHAIN_SCRIPT" || echo "    ⚠️  Toolchain provisioning incomplete — re-run later: bash $TOOLCHAIN_SCRIPT"
else
    echo "    ⚠️  Toolchain script not found. Skipping."
fi

# ============================================================================
# AGENT INSTRUCTION FILES (AGENTS.md, CLAUDE.md, GEMINI.md)
# ============================================================================
# These files tell AI agents how to operate in this workspace.
# We copy from team-lib template if files don't exist.

AGENTS_TEMPLATE="${WORKSPACE_ROOT}/team-lib/context/indexed/templates/template-agent-automation-user.md"

if [[ ! -f "$MY_LIB_DIR/AGENTS.md" ]]; then
    if [[ -f "$AGENTS_TEMPLATE" ]]; then
        echo "    Creating AGENTS.md from team-lib template..."
        cp "$AGENTS_TEMPLATE" "$MY_LIB_DIR/AGENTS.md"
    else
        echo "    ⚠️  Template not found. Creating minimal AGENTS.md..."
        ensure_file "$MY_LIB_DIR/AGENTS.md" "# Agent Instructions

# 🚨 CRITICAL PROTOCOLS
### ARTIFACT MIRRORING RULE (Anti-Data Loss)
**You are working in an ephemeral environment.** Any files you create in session-specific folders (like /brain/ or /tmp/) WILL BE LOST after this session.
*   **Final Deliverables**: MUST be mirrored to **my-lib/runtime/deliverables/**.
*   **Intermediate Files**: MUST be mirrored to **my-lib/runtime/.tmp/**.
*   **Action**: When you create a file in an artifact directory, immediately run cp or write_to_file to save a copy in the permanent my-lib/runtime/ structure.

Read team-lib/context/indexed/templates/template-agent-automation-user.md for full instructions.
"
    fi
fi

if [[ ! -f "$MY_LIB_DIR/CLAUDE.md" ]]; then
    echo "    Creating CLAUDE.md (pointer to AGENTS.md)..."
    ensure_file "$MY_LIB_DIR/CLAUDE.md" "# claude.md (local)

READ ~/ai-workspace/my-lib/AGENTS.md BEFORE ANYTHING

# Local specific tweaks for Claude
## - insert model-specific tweaks here
"
fi

if [[ ! -f "$MY_LIB_DIR/GEMINI.md" ]]; then
    echo "    Creating GEMINI.md (pointer to AGENTS.md)..."
    ensure_file "$MY_LIB_DIR/GEMINI.md" "# gemini.md (local)

READ ~/ai-workspace/my-lib/AGENTS.md BEFORE ANYTHING

# Local specific tweaks for Gemini
## - insert model-specific tweaks here
"
fi

# ============================================================================
# ROOT-LEVEL INDEX.MD
# ============================================================================

ensure_file "${WORKSPACE_ROOT}/index.md" "# AI Workspace (Functional Topology)

## Purpose
Root of the Pvragon AI Workspace—a 4-layer functional hierarchy for agentic development and automation.

## Layers

| Layer | Directory | Purpose |
|-------|-----------|---------|
| **0** | \`personal/\` | Local machine overrides (human-only) |
| **1** | \`team-lib/\` | System Standard Library (shared OS) |
| **2** | \`my-lib/\` | User Extension Library (personal overlay) |
| **3** | \`projects/\` | Active Development Factory (all projects) |

## Operational Modes

| Mode | Location | Behavior |
|------|----------|----------|
| STOP | Root (\`~/ai-workspace/\`) | No work permitted; route to scope |
| Automation | Libraries (\`team-lib/\`, \`my-lib/\`) | DOE automator mode |
| Engineering | Workbench (\`projects/*\`) | Builder mode; read specs, write code |

## Root Files
- \`pvragon-workspace.code-workspace\` → The Multi-Root configuration file. Open this in VS Code.

## Key Rule
**Do not work at root.** Navigate to a numbered scope first.
"

# ============================================================================
# CONTENT GENERATION (SCAFFOLDING)
# ============================================================================

# Personal Index
ensure_file "${WORKSPACE_ROOT}/personal/index.md" "# personal

Private human workspace. Agents should not access unless directed.

- \`notes/\` - Personal notes
- \`scratch/\` - Temporary work
- \`preferences/\` - Personal config
"

# Personal Preferences Template
ensure_file "${WORKSPACE_ROOT}/personal/preferences/personal.md" "# Personal Preferences

User: $(whoami)
"

# Secrets template — the canonical env file every execution script sources.
# ONBOARDING.md's \"Get your keys\" section explains where each value comes from.
ensure_file "${WORKSPACE_ROOT}/personal/secrets/.env.template" "# Pvragon AI Workspace — secrets file
# Copy real values in place of the placeholders. This file is the template;
# the live copy is .env in this same directory. NEVER commit either one,
# and never paste values into chat with an agent.

# ── Team-shared (ask your team lead — one value provisioned for/by the team) ──
BASEROW_MCP_TOKEN=          # Baserow MCP database access (required)
CLICKUP_WORKSPACE_ID=       # shared team constant — same for everyone
PULSE_CHANNEL_ID=           # shared team constant — same for everyone

# ── Per-user (generate your own from each service's settings page) ──
GOOGLE_WORKSPACE_EMAIL=     # your own @pvragon.com address
# CLICKUP_API_TOKEN=        # ClickUp → Settings → Apps → API Token (pk_...)
# ANTHROPIC_API_KEY=        # only for direct API scripting; Claude Code has its own login

# ── Project/role-specific — DO NOT request these until a project needs them ──
# Added when you're assigned to the relevant project (Acme Health, etc.).
# Ask the project lead; never copy another person's values.
"
if [[ ! -f "${WORKSPACE_ROOT}/personal/secrets/.env" ]]; then
    cp "${WORKSPACE_ROOT}/personal/secrets/.env.template" "${WORKSPACE_ROOT}/personal/secrets/.env"
    echo "Created file: ${WORKSPACE_ROOT}/personal/secrets/.env (fill in your keys)"
fi

# NOTE: team-lib content (README, index files) comes from the clone — the repo
# is the single source of truth. Scaffolding team-lib content here caused the
# embedded copies to drift from the real ones; removed 2026-07-16.
# Projects Index
ensure_file "${WORKSPACE_ROOT}/projects/index.md" "# projects

## Purpose
Active Development Factory—container for all project repositories (private and team).

## What Belongs Here
- All project repositories (private and team)
- Each project in its own subdirectory
- Projects follow the standard structure: \`src/\`, \`docs/specs/\`, \`docs/context/\`, \`docs/directives/\`

## Operational Mode
When working in this directory, agents operate in **Engineering Mode**:
- Read \`docs/specs/\` for requirements
- Read \`docs/context/\` for background
- Write source code, run tests
"

# ============================================================================
# MANIFEST & WORKSPACE GENERATION
# ============================================================================

# Helper: report a repo's GitHub slug (owner/repo) or "null" if no remote.
# Keeps the manifest honest per-user instead of hardcoding anyone's repos.
repo_slug() {
    local dir="$1"
    local url
    url=$(git -C "$dir" remote get-url origin 2>/dev/null || true)
    if [[ -n "$url" ]]; then
        echo "$url" | sed -E 's#^(https://github.com/|git@github.com:)##; s#\.git$##'
    else
        echo "null"
    fi
}

generate_manifest() {
    local manifest_file="$1"
    local workspace_root="$2"
    local team_lib_slug my_lib_slug
    team_lib_slug=$(repo_slug "$workspace_root/team-lib")
    my_lib_slug=$(repo_slug "$workspace_root/my-lib")

    cat > "$manifest_file" << EOF
# workspace-manifest.yaml
# Generated by: setup_workspace.sh on $(date)
# Location: $manifest_file
# Purpose: Single source of truth for workspace paths across all machines

version: "1.0"
generated_at: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
workspace_layout: "multi-root"
workspace_root: $workspace_root
governance_directive: "team-lib/directives/team-library-governance.md"

roots:
  personal:
    path: $workspace_root/personal
    role: user-local
    description: "Private human workspace - notes, secrets, preferences"
    is_git_repo: false
    is_gitignored: true
    key_subdirs:
      notes: notes/
      scratch: scratch/
      preferences: preferences/
      secrets: secrets/

  team_lib:
    path: $workspace_root/team-lib
    role: shared-sop
    description: "Shared team library - SOPs, directives, templates"
    is_git_repo: true
    github_repo: $team_lib_slug
    is_gitignored: false
    key_subdirs:
      registry: registry/
      directives: directives/
      skills: skills/
      personas: personas/
      context_source: context/
      executions: executions/
      harnesses: harnesses/
      admin: _admin/

  my_lib:
    path: $workspace_root/my-lib
    role: user-directives
    description: "Personal overlay library - user directives & scripts"
    is_git_repo: true
    github_repo: $my_lib_slug
    is_gitignored: false
    key_subdirs:
      archive: archive/
      backlog: backlog/
      registry: registry/
      directives: directives/
      skills: skills/
      personas: personas/
      context_source: context/
      executions: executions/
      harnesses: harnesses/
      runtime: runtime/

  projects:
    path: $workspace_root/projects
    role: active-repos
    description: "Active development - all project repositories"
    is_git_repo: false
    contains_git_repos: true
    key_subdirs: {}

context_layers:
  - team_lib
  - my_lib
  - personal
EOF
    echo "Created manifest: $manifest_file"
}

generate_code_workspace() {
    local workspace_file="$1"
    local workspace_root="$2"

    cat > "$workspace_file" << EOF
{
  "folders": [
    {
      "name": "0 📝 /personal",
      "path": "personal"
    },
    {
      "name": "1 📚 /team-lib",
      "path": "team-lib"
    },
    {
      "name": "2 🔧 /my-lib",
      "path": "my-lib"
    },
    {
      "name": "3 🚀 /projects",
      "path": "projects"
    }
  ],
  "settings": {
    "files.exclude": {
      "**/.git": true,
      "**/__pycache__": true,
      "**/node_modules": true,
      "**/.DS_Store": true
    },
    "search.exclude": {
      "**/.git": true,
      "**/node_modules": true
    },
    "editor.formatOnSave": true,
    "files.trimTrailingWhitespace": true
  }
}
EOF
    echo "Created workspace file: $workspace_file"
}

echo ""
echo "=== Generating workspace manifest ==="
generate_manifest "$MANIFEST_PATH" "$WORKSPACE_ROOT"

echo ""
echo "=== Generating VS Code workspace ==="
# User prefers "pvragon-workspace.code-workspace"
generate_code_workspace "${WORKSPACE_ROOT}/pvragon-workspace.code-workspace" "${WORKSPACE_ROOT}"

# ============================================================================
# SET ENVIRONMENT VARIABLE
# ============================================================================

echo ""
echo "=== Setting up environment variable ==="
if ! grep -q "WORKSPACE_MANIFEST_PATH" "$HOME/.bashrc" 2>/dev/null; then
    echo "" >> "$HOME/.bashrc"
    echo "# Pvragon AI Workspace" >> "$HOME/.bashrc"
    echo "export WORKSPACE_MANIFEST_PATH=\"$MANIFEST_PATH\"" >> "$HOME/.bashrc"
    echo "    ✅ Added manifest export to ~/.bashrc"
else
    echo "    ℹ️  Manifest export already in ~/.bashrc"
fi

# ============================================================================
# SKILL EXPOSURE
# ============================================================================
# The harness finds skills at ~/.claude/skills, which is a symlink to the personal layer;
# shared skills reach the agent as pointers placed inside it. Nothing created either link —
# they had accumulated by hand on the machine that invented the convention. A fresh install
# therefore finished with the whole shared library present and none of it invocable
# (measured in harnesses/public_workspace_container_test.sh, 2026-08-01).

echo ""
echo "=== Exposing shared skills to the agent ==="
LINK_SKILLS="${WORKSPACE_ROOT}/team-lib/executions/link_skills.py"
if [[ -f "$LINK_SKILLS" ]]; then
    python3 "$LINK_SKILLS" --quiet || echo "    ⚠️  Skill linking incomplete — re-run later: python3 $LINK_SKILLS"
else
    echo "    ⚠️  link_skills.py not found — shared skills will not be invocable."
fi

# ============================================================================
# AGENT MEMORY SYSTEM
# ============================================================================
# Without this the install is a library, not an agent: no reinforcement hook, no
# nightly dream cycle, no memory index. The installer is idempotent and handles the
# ordering constraint setup cannot avoid — the agent home does not exist until the
# choose-name ceremony in the agent's first session — by wiring the agent-independent
# half now and exiting 2 (DEFERRED). Never let it abort setup; it is re-runnable.

MEMORY_SCRIPT="${WORKSPACE_ROOT}/team-lib/_admin/install_memory.sh"
MEMORY_STATUS="not-run"

if [[ -f "$MEMORY_SCRIPT" ]]; then
    memory_rc=0
    bash "$MEMORY_SCRIPT" || memory_rc=$?
    case $memory_rc in
        0) MEMORY_STATUS="installed" ;;
        2) MEMORY_STATUS="deferred"  ;;
        *) MEMORY_STATUS="failed"
           echo "    ⚠️  Memory install failed — re-run later: bash $MEMORY_SCRIPT" ;;
    esac
else
    echo "    ⚠️  Memory installer not found at $MEMORY_SCRIPT — skipping."
fi

# ============================================================================
# VALIDATION
# ============================================================================

echo ""
echo "=== Running Validation ==="
VALIDATE_SCRIPT="${WORKSPACE_ROOT}/team-lib/_admin/validate.sh"

if [[ -f "$VALIDATE_SCRIPT" ]]; then
    bash "$VALIDATE_SCRIPT" || echo "    ⚠️  Some validation checks failed. Review the output above."
else
    echo "⚠️  Validation script not found at $VALIDATE_SCRIPT"
fi

echo ""
echo "=== Setup complete! ==="
echo "1. Restart your terminal (or run 'source ~/.bashrc')."
echo "2. Open VS Code using: ${WORKSPACE_ROOT}/pvragon-workspace.code-workspace"

# The deferred memory install is the single most-missed step, because nothing about a
# populated library looks unfinished. Say so here, where the user is still reading.
case "$MEMORY_STATUS" in
    deferred)
        echo "3. Name your agent (ONBOARDING Phase 7), then give it memory:"
        echo "       bash $MEMORY_SCRIPT"
        echo "   Until then your agent starts every session from nothing."
        ;;
    failed)
        echo "3. ⚠️  The memory install failed above. Re-run it:"
        echo "       bash $MEMORY_SCRIPT"
        ;;
    installed)
        echo "3. Memory system installed and verified. ✅"
        ;;
esac
echo ""
