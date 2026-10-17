#!/bin/bash
# update.sh — Pulls latest changes for all workspace repos.

ROOT_DIR="$HOME/ai-workspace"

echo "🔄 Updating AI Workspace..."

# Function to update a repo
update_repo() {
  local target="$1"
  if [ -d "$target/.git" ]; then
    echo "⬇️  Pulling $(basename "$target")..."
    git -C "$target" pull --rebase
  else
    echo "⚠️  Skipping $(basename "$target") (not a git repo or missing)"
  fi
}

# Update Library Repos
update_repo "$ROOT_DIR/team-lib"
update_repo "$ROOT_DIR/my-lib"

# Update Project Repos (glob for folders containing .git)
for repo in "$ROOT_DIR/projects"/*; do
  [ -d "$repo/.git" ] && update_repo "$repo"
done

# Re-link skills: a pull can add shared skills (team-lib) or personal ones (my-lib) that the
# harness cannot see until they are linked. link_skills is idempotent, never deletes, and prints
# one line if the skill listing map is stale or not installed.
LINK_SKILLS="$ROOT_DIR/team-lib/executions/link_skills.py"
if [[ -f "$LINK_SKILLS" ]]; then
    echo "🔗 Re-linking skills..."
    python3 "$LINK_SKILLS" --quiet || echo "⚠️  Skill linking incomplete — re-run: python3 $LINK_SKILLS"
fi

# Toolchain updates
TOOLCHAIN_SCRIPT="$ROOT_DIR/team-lib/_admin/configure_toolchain.sh"
if [[ -f "$TOOLCHAIN_SCRIPT" ]]; then
    echo "Checking for toolchain updates..."
    bash "$TOOLCHAIN_SCRIPT" --update-only
fi

echo "✅ Update complete."
