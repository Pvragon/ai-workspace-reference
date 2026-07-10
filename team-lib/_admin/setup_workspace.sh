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

# Default Team Library URL (can be overridden via environment).
# For a NEW workspace bootstrapped from the public reference, this repo IS
# your starting team-lib — fork it, then point TEAM_REPO_URL at your fork
# (or later at your own team's private library repo).
TEAM_REPO_URL="${TEAM_REPO_URL:-https://github.com/Pvragon/ai-workspace-reference.git}"

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
    CLONE_TMP="$(mktemp -d)"
    if git clone "$TEAM_REPO_URL" "$CLONE_TMP/repo"; then
        if [[ -d "$CLONE_TMP/repo/team-lib/_admin" ]]; then
            # Reference-layout repo (wraps the whole workspace, team-lib is a
            # subdirectory): extract the team-lib subtree and start it as a
            # fresh local repo. Add your own remote later when you create
            # your team's library repo.
            echo "    Detected reference layout — extracting team-lib/ subtree..."
            mv "$CLONE_TMP/repo/team-lib" "$TEAM_LIB_DIR"
            # -c identity overrides: a fresh machine has no git user.name/email
            # configured yet, and a bare `git commit` would die with exit 128
            (cd "$TEAM_LIB_DIR" && git init -q && git add -A && \
                git -c user.name="Workspace Setup" -c user.email="setup@ai-workspace.local" \
                    commit -qm "Bootstrap team-lib from $TEAM_REPO_URL")
        else
            # Team-lib-rooted repo: use the clone directly
            mv "$CLONE_TMP/repo" "$TEAM_LIB_DIR"
        fi
        rm -rf "$CLONE_TMP"
        echo "    ✅ team-lib set up successfully."
    else
        rm -rf "$CLONE_TMP"
        echo "    ❌ Failed to clone team-lib. Check your network connection and URL."
        echo "    URL: $TEAM_REPO_URL"
        exit 1
    fi
else
    echo "    team-lib is already a git repository. Pulling latest..."
    git -C "$TEAM_LIB_DIR" pull || echo "    ⚠️  Git pull failed (continuing anyway)."
fi

# ============================================================================
# EXTERNAL SKILL PACKS (public repos, cloned into skills/_external)
# ============================================================================

EXT_DIR="${TEAM_LIB_DIR}/skills/_external"
clone_external_pack() {
    local dir="$1" url="$2"
    if [[ ! -d "$EXT_DIR/$dir/.git" ]]; then
        echo "    Cloning external skill pack: $dir..."
        rm -rf "$EXT_DIR/$dir"
        git clone --depth 1 "$url" "$EXT_DIR/$dir" || echo "    ⚠️  Failed to clone $dir (continuing — re-run later)"
    fi
}
mkdir -p "$EXT_DIR"
clone_external_pack "anthropics" "https://github.com/anthropics/skills.git"
clone_external_pack "rezvani-claude-skills" "https://github.com/alirezarezvani/claude-skills.git"

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
# DIRECTORY STRUCTURE (Functional Topology)
# ============================================================================

# Layer 0: Personal (human-only)
ensure_dir "${WORKSPACE_ROOT}/personal/notes"
ensure_dir "${WORKSPACE_ROOT}/personal/scratch"
ensure_dir "${WORKSPACE_ROOT}/personal/preferences"
ensure_dir "${WORKSPACE_ROOT}/personal/secrets"

# Layer 1: Pvragon Library - directories are created by git clone above
# Only ensure subdirs if somehow missing (shouldn't happen with valid clone)
ensure_dir "${WORKSPACE_ROOT}/team-lib/directives"
ensure_dir "${WORKSPACE_ROOT}/team-lib/context/global"
ensure_dir "${WORKSPACE_ROOT}/team-lib/context/indexed"
ensure_dir "${WORKSPACE_ROOT}/team-lib/personas"
ensure_dir "${WORKSPACE_ROOT}/team-lib/skills"
ensure_dir "${WORKSPACE_ROOT}/team-lib/skills/_external"
ensure_dir "${WORKSPACE_ROOT}/team-lib/skills/_external/anthropics"
ensure_dir "${WORKSPACE_ROOT}/team-lib/skills/_external/rezvani-claude-skills"
ensure_dir "${WORKSPACE_ROOT}/team-lib/executions"
ensure_dir "${WORKSPACE_ROOT}/team-lib/harnesses"
ensure_dir "${WORKSPACE_ROOT}/team-lib/registry"
ensure_dir "${WORKSPACE_ROOT}/team-lib/logs"

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
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/intermediates"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/deliverables"
ensure_dir "${WORKSPACE_ROOT}/my-lib/runtime/logs"

# Layer 3: Workbench
ensure_dir "${WORKSPACE_ROOT}/projects"

# Cross-cutting: agent identity & memory (see agents/example-agent in the
# reference repo for the pattern — copy it to start your own agent)
ensure_dir "${WORKSPACE_ROOT}/agents"

# Admin scripts
ensure_dir "${WORKSPACE_ROOT}/team-lib/_admin"

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
"
                ensure_file "$MY_LIB_DIR/README.md" "# my-lib
Private AI Library.
"
                echo "    ✅ Repo initialized."
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

# Team Lib README (Matches Documentation)
ensure_file "${WORKSPACE_ROOT}/team-lib/README.md" "# Pvragon AI Library

**The standardized operating system for agentic development.**

This repository is the **Layer 1 (Shared)** foundation of the Pvragon AI Workspace. It provides the shared tooling, context, and directives that enable consistent, high-quality agent performance across the team.

---

## 🚀 Quick Start

### [**→ Start Here: Getting Started Guide**](GETTING_STARTED.md)
*Follow this guide to set up your environment from zero to fully functional.*

### [**→ Operating Manual: Workspace Reference**](context/indexed/workspace-reference.md)
*The definitive guide to the workspace topology, layers, and usage rules.*

---

## 🏗️ Functional Stack

A high-level overview of the standard library components:

| Layer | Directory | Purpose |
|-------|-----------|---------|
| **Directives** | \`directives/\` | High-level instructions and behavioral rules (SOPs) |
| **Context** | \`context/\` | Team knowledge base (Global + Indexed packs) |
| **Personas** | \`personas/\` | Team-approved agent identities |
| **Skills** | \`skills/\` | Shared capability modules and tools |
| **Executions** | \`executions/\` | Deterministic scripts for reliable automation |
| **Harnesses** | \`harnesses/\` | Test frameworks and evaluation suites |
| **Registry** | \`registry/\` | Manifests cataloging available resources |
| **Logs** | \`logs/\` | Team execution audits |

## 📂 Directory Structure

\`\`\`
team-lib/
├── _admin/             # Bootstrap, validation, and setup scripts
├── directives/         # Behavioral rules (SOPs)
├── context/            # Knowledge base
│   ├── global/         # Always-on context
│   └── indexed/        # On-demand context packs
├── personas/           # Agent configurations
├── skills/             # Capability modules (Tools)
├── executions/         # Scripts (Actions)
├── harnesses/          # Testing frameworks
├── registry/           # Resource manifests (YAML)
└── logs/               # Execution logs
\`\`\`

## ⚖️ Governance & Standards

**This library is governed by strict quality controls.**
Before contributing, you **must** read the [**Team Library Governance Directive**](directives/team-library-governance.md).

**Key Rules:**
1.  **No Personal Code:** If it has your name or hardcoded home path, it doesn't belong here.
2.  **Pull Request Required:** Direct pushes to \`main\` are forbidden.
3.  **Strict Naming:** \`kebab-case\` for files, \`snake_case\` for python.

## 🤝 How to Contribute

1.  **Create** resources in the appropriate directory (e.g., new SOP in \`directives/\`).
2.  **Register** new resources in the relevant \`registry/\` manifest.
3.  **Test** using \`harnesses/\` before deployment.
4.  **Submit** a Pull Request for review.
"

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

generate_manifest() {
    local manifest_file="$1"
    local workspace_root="$2"

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
    github_repo: null  # set to your team-library repo when you create one
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
    github_repo: null  # set to your private my-lib repo when you create one
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
      "name": "1 🔧 /my-lib",
      "path": "my-lib"
    },
    {
      "name": "2 📚 /team-lib",
      "path": "team-lib"
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
echo ""
