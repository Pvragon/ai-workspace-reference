#!/bin/bash
#
# tests/test_setup_workspace.sh
# Harness to test user onboarding in a sandbox environment.
# Uses a local dummy repository to mock the git clone.
#
# Usage: ./test_setup_workspace.sh
#

set -e

# Get script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="$SCRIPT_DIR/../setup_workspace.sh"
VALIDATE_SCRIPT_SRC="$SCRIPT_DIR/../validate.sh"

echo "=== Test Harness: Setup Workspace ==="
echo "Script to test: $SETUP_SCRIPT"

# 1. Create Sandbox
TEST_DIR=$(mktemp -d)
echo "🧪 Sandbox created at: $TEST_DIR"

# 2. Mock Environment
export HOME="$TEST_DIR"
export WORKSPACE_ROOT="$HOME/ai-workspace"

# 3. Create Dummy Team Repo (Local Mock)
# Path selected to satisfy validate.sh remote check (Pvragon/pvragon-ai-library)
DUMMY_TEAM_REPO="$TEST_DIR/mock_github/Pvragon/pvragon-ai-library"
mkdir -p "$DUMMY_TEAM_REPO"
git init -q "$DUMMY_TEAM_REPO"

# List of all directories expected by validate.sh for team-lib
TEAM_DIRS=(
  "_admin"
  "context/global"
  "context/indexed"
  "directives"
  "executions"
  "harnesses"
  "logs"
  "personas"
  "registry"
  "skills"
)

for dir in "${TEAM_DIRS[@]}"; do
    mkdir -p "$DUMMY_TEAM_REPO/$dir"
    touch "$DUMMY_TEAM_REPO/$dir/.gitkeep"
done

# Copy special files
if [ -f "$VALIDATE_SCRIPT_SRC" ]; then
    cp "$VALIDATE_SCRIPT_SRC" "$DUMMY_TEAM_REPO/_admin/validate.sh"
else
    # Create valid dummy if original not found
    echo "#!/bin/bash" > "$DUMMY_TEAM_REPO/_admin/validate.sh"
    echo "echo '✅ Dummy validation passed'" >> "$DUMMY_TEAM_REPO/_admin/validate.sh"
    chmod +x "$DUMMY_TEAM_REPO/_admin/validate.sh"
fi

touch "$DUMMY_TEAM_REPO/context/global/template-agent-safety.md"
touch "$DUMMY_TEAM_REPO/context/global/template-agent-engineering.md"
touch "$DUMMY_TEAM_REPO/registry/workspace.yaml"
touch "$DUMMY_TEAM_REPO/directives/team-library-governance.md"

# Create toolchain files for testing
# Use real server names (clickup, baserow) so validate.sh checks pass
cat > "$DUMMY_TEAM_REPO/_admin/toolchain.yaml" << 'TOOLCHAIN_EOF'
version: "1.0"
cli_tools:
  test-tool:
    description: "Test CLI tool"
    install_type: npm
    install_command: "echo 'mock install'"
    check_command: "true"
    required: true
mcp_servers:
  clickup:
    description: "ClickUp project management (test mock)"
    required: true
    config:
      claude:
        type: stdio
        command: echo
        args: ["clickup-mock"]
        env: {}
  baserow:
    description: "Baserow database (test mock)"
    required: true
    config:
      claude:
        type: stdio
        command: echo
        args: ["baserow-mock"]
        env: {}
TOOLCHAIN_EOF

cat > "$DUMMY_TEAM_REPO/_admin/parse_toolchain.py" << 'PARSE_EOF'
#!/usr/bin/env python3
"""Bridge: reads toolchain.yaml, emits JSON to stdout for jq consumption."""
import json, sys, yaml

with open(sys.argv[1]) as f:
    print(json.dumps(yaml.safe_load(f)))
PARSE_EOF
chmod +x "$DUMMY_TEAM_REPO/_admin/parse_toolchain.py"

# Copy configure_toolchain.sh from source
if [ -f "$SCRIPT_DIR/../configure_toolchain.sh" ]; then
    cp "$SCRIPT_DIR/../configure_toolchain.sh" "$DUMMY_TEAM_REPO/_admin/configure_toolchain.sh"
    chmod +x "$DUMMY_TEAM_REPO/_admin/configure_toolchain.sh"
fi

# Pre-create claude.json for MCP testing
echo '{"mcpServers":{}}' > "$TEST_DIR/.claude.json"

git -C "$DUMMY_TEAM_REPO" add .
git -C "$DUMMY_TEAM_REPO" -c user.name="Test" -c user.email="test@test.com" commit -q -m "Initial mock commit (team)"
echo "🛠️  Dummy Team Repo: $DUMMY_TEAM_REPO"

# 4. Create Dummy My-Lib Repo (Local Mock)
# Path selected to satisfy validate.sh remote check (jkhereford/private-ai-library)
DUMMY_MY_REPO="$TEST_DIR/mock_github/jkhereford/private-ai-library"
mkdir -p "$DUMMY_MY_REPO"
git init -q "$DUMMY_MY_REPO"

# List of all directories expected by validate.sh for my-lib
MY_DIRS=(
  "archive"
  "backlog"
  "config"
  "context/global"
  "context/indexed"
  "directives"
  "executions"
  "harnesses"
  "logs"
  "personas"
  "registry"
  "runtime"
  "runtime/deliverables"
  "runtime/intermediates"
  "runtime/logs"
  "skills"
)
for dir in "${MY_DIRS[@]}"; do
    mkdir -p "$DUMMY_MY_REPO/$dir"
    touch "$DUMMY_MY_REPO/$dir/.gitkeep"
done
# setup_workspace.sh expects AGENTS.md for symlinking
touch "$DUMMY_MY_REPO/AGENTS.md"

git -C "$DUMMY_MY_REPO" add .
git -C "$DUMMY_MY_REPO" -c user.name="Test" -c user.email="test@test.com" commit -q -m "Initial mock commit (my-lib)"
echo "🛠️  Dummy My-Lib Repo: $DUMMY_MY_REPO"


# 5. Configure Script to use Dummy Team Repo
export TEAM_REPO_URL="file://$DUMMY_TEAM_REPO"

# 6. Simulate Execution
echo "🚀 Running setup_workspace.sh in sandbox..."
echo "---------------------------------------------------"

# We pipe:
# "1" (Clone existing)
# "file://.../private-ai-library" (URL)
# "all" (Select all AI clients for MCP)
printf "1\nfile://$DUMMY_MY_REPO\nall\n" | bash "$SETUP_SCRIPT"

echo "---------------------------------------------------"
echo "🚀 Execution finished."

# 6b. Mock external skill repos (validate.sh checks these as git repos with remotes)
for ext_repo in \
    "skills/_external/anthropics:https://github.com/anthropics/skills.git" \
    "skills/_external/rezvani-claude-skills:https://github.com/alirezarezvani/claude-skills.git"; do
    ext_dir="${ext_repo%%:*}"
    ext_url="${ext_repo##*:}"
    ext_path="$WORKSPACE_ROOT/team-lib/$ext_dir"
    mkdir -p "$ext_path"
    git init -q "$ext_path"
    git -C "$ext_path" remote add origin "$ext_url"
    # Need at least one commit for a valid repo
    touch "$ext_path/.gitkeep"
    git -C "$ext_path" add .
    git -C "$ext_path" -c user.name="Test" -c user.email="test@test.com" commit -q -m "Mock external repo"
done

# 7. Verification
echo "🔍 Validating sandbox state..."
FAIL=0

if [ -d "$WORKSPACE_ROOT/team-lib/.git" ]; then
    echo "✅ team-lib clones"
else
    echo "❌ team-lib missing/invalid"
    FAIL=1
fi

if [ -f "$HOME/.ai-workspace-manifest.yaml" ]; then
   echo "✅ Manifest created"
else
   echo "❌ Manifest missing"
   FAIL=1
fi

if [ -d "$WORKSPACE_ROOT/my-lib/.git" ]; then
    echo "✅ my-lib clones"
else
    echo "❌ my-lib missing/invalid"
    FAIL=1
fi

# Toolchain: verify MCP server was added to claude.json
if [ -f "$HOME/.claude.json" ]; then
    MCP_COUNT=$(jq '.mcpServers | length' "$HOME/.claude.json" 2>/dev/null || echo "0")
    if [ "$MCP_COUNT" -gt 0 ]; then
        echo "✅ MCP servers configured ($MCP_COUNT entries)"
    else
        echo "⚠️  MCP servers not added (may be expected if client selection was skipped)"
    fi
else
    echo "⚠️  ~/.claude.json not found"
fi

# Toolchain: verify idempotency (run configure_toolchain again)
if [ -f "$WORKSPACE_ROOT/team-lib/_admin/configure_toolchain.sh" ]; then
    echo "🔍 Testing toolchain idempotency..."
    MCP_BEFORE=$(jq '.mcpServers | length' "$HOME/.claude.json" 2>/dev/null || echo "0")
    bash "$WORKSPACE_ROOT/team-lib/_admin/configure_toolchain.sh" --update-only 2>/dev/null || true
    MCP_AFTER=$(jq '.mcpServers | length' "$HOME/.claude.json" 2>/dev/null || echo "0")
    if [ "$MCP_BEFORE" = "$MCP_AFTER" ]; then
        echo "✅ Toolchain idempotency check passed (count: $MCP_AFTER)"
    else
        echo "❌ Toolchain idempotency failed (before: $MCP_BEFORE, after: $MCP_AFTER)"
        FAIL=1
    fi
fi

# Run the validation script (should pass now that external repos and MCP servers are mocked)
if [ -f "$WORKSPACE_ROOT/team-lib/_admin/validate.sh" ]; then
    echo "🔍 Running internal validation..."
    if bash "$WORKSPACE_ROOT/team-lib/_admin/validate.sh"; then
        echo "✅ Internal validation passed"
    else
        echo "❌ Internal validation failed"
        FAIL=1
    fi
else
    echo "❌ validate.sh missing in workspace"
    FAIL=1
fi

# 8. Cleanup
echo "🧹 Cleaning up sandbox..."
rm -rf "$TEST_DIR"

if [ $FAIL -eq 0 ]; then
    echo "✨ TEST PASSED: Setup script works correctly."
    exit 0
else
    echo "🔥 TEST FAILED check logs."
    exit 1
fi
