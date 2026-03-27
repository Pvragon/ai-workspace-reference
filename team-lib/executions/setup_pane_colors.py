#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Installs the Claude Code tmux pane-color notification system. Deploys pane-color.sh and merges hooks into ~/.claude/settings.json so tmux panes change background while Claude is working."
# created: 2026-03-26
# last_updated: 2026-03-26
# maintainer: pvragon
# ---
"""
Setup Pane Colors

Installs the tmux pane-color notification system for Claude Code. When active,
tmux pane backgrounds change to a branded color while Claude is working and
revert to default when Claude is waiting for input. Works per-pane so multiple
Claude sessions can run independently.

Usage:
    python3 setup_pane_colors.py
    python3 setup_pane_colors.py --working-color '#1a2b3c'
    python3 setup_pane_colors.py --accent-color '#E7511F'
    python3 setup_pane_colors.py --dry-run
    python3 setup_pane_colors.py --uninstall
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# --- Defaults ---

DEFAULT_WORKING_COLOR = "#112328"
DEFAULT_ACCENT_COLOR = "#E7511F"

def _build_pane_color_script(working_color: str, accent_rgb: str) -> str:
    """Build the pane-color.sh script content with colors baked in."""
    return f"""#!/usr/bin/env bash
# Set tmux pane background to signal Claude state.
# Uses per-pane styling (not global) so multiple Claude windows work independently.
#
# Usage: pane-color.sh working|waiting|reset

PANE="${{TMUX_PANE}}"
[ -z "$PANE" ] && exit 0

# Check if tmux supports allow-passthrough (3.3+) for accent color remapping
TMUX_VER=$(tmux -V | grep -oP '[\\d.]+')
HAS_PASSTHROUGH=false
if printf '%s\\n' "3.3" "$TMUX_VER" | sort -V | head -1 | grep -q "^3.3"; then
  HAS_PASSTHROUGH=true
fi

case "${{1:-reset}}" in
  working)
    tmux select-pane -t "$PANE" -P 'bg={working_color}'
    # Remap ANSI bright blue (12) to accent color (tmux 3.3+ only)
    if $HAS_PASSTHROUGH; then
      TTY=$(tmux display-message -t "$PANE" -p '#{{pane_tty}}')
      [ -n "$TTY" ] && printf '\\033]4;12;rgb:{accent_rgb}\\033\\\\' > "$TTY"
    fi
    ;;
  waiting)
    tmux select-pane -t "$PANE" -P 'default'
    if $HAS_PASSTHROUGH; then
      TTY=$(tmux display-message -t "$PANE" -p '#{{pane_tty}}')
      [ -n "$TTY" ] && printf '\\033]104;12\\033\\\\' > "$TTY"
    fi
    ;;
  reset|*)
    tmux select-pane -t "$PANE" -P 'default'
    if $HAS_PASSTHROUGH; then
      TTY=$(tmux display-message -t "$PANE" -p '#{{pane_tty}}')
      [ -n "$TTY" ] && printf '\\033]104;12\\033\\\\' > "$TTY"
    fi
    ;;
esac
"""

HOOKS_CONFIG = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": 'JSON=$(cat); echo "$JSON" | grep -q \'"agent_id"\' && exit 0; ~/.claude/pane-color.sh waiting',
                }
            ]
        }
    ],
    "PreToolUse": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "~/.claude/pane-color.sh working",
                }
            ]
        }
    ],
    "UserPromptSubmit": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "~/.claude/pane-color.sh working",
                }
            ]
        }
    ],
    "Notification": [
        {
            "matcher": "permission_prompt",
            "hooks": [
                {
                    "type": "command",
                    "command": 'JSON=$(cat); echo "$JSON" | grep -q \'"agent_id"\' && exit 0; ~/.claude/pane-color.sh waiting',
                }
            ],
        },
        {
            "matcher": "elicitation_dialog",
            "hooks": [
                {
                    "type": "command",
                    "command": 'JSON=$(cat); echo "$JSON" | grep -q \'"agent_id"\' && exit 0; ~/.claude/pane-color.sh waiting',
                }
            ],
        },
    ],
}


def check_prerequisites() -> list[str]:
    """Check that tmux is installed and available."""
    issues = []
    if not shutil.which("tmux"):
        issues.append("tmux is not installed or not in PATH")
    else:
        result = subprocess.run(
            ["tmux", "-V"], capture_output=True, text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            issues.append(f"INFO: detected {version}")
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        issues.append("~/.claude directory does not exist — is Claude Code installed?")
    return issues


def render_script(working_color: str, accent_color: str) -> str:
    """Render pane-color.sh with the given colors."""
    accent_hex = accent_color.lstrip("#")
    accent_rgb = f"{accent_hex[0:2]}/{accent_hex[2:4]}/{accent_hex[4:6]}"
    return _build_pane_color_script(working_color, accent_rgb)


def install_script(working_color: str, accent_color: str, dry_run: bool = False) -> dict:
    """Write pane-color.sh to ~/.claude/."""
    dest = Path.home() / ".claude" / "pane-color.sh"
    content = render_script(working_color, accent_color)

    if dry_run:
        return {"status": "ok", "action": "dry-run", "path": str(dest)}

    dest.write_text(content)
    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
    return {"status": "ok", "action": "installed", "path": str(dest)}


def merge_hooks(dry_run: bool = False) -> dict:
    """Merge pane-color hooks into ~/.claude/settings.json without clobbering."""
    settings_path = Path.home() / ".claude" / "settings.json"

    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}

    existing_hooks = settings.get("hooks", {})
    merged_keys = []
    skipped_keys = []

    for hook_name, hook_value in HOOKS_CONFIG.items():
        if hook_name in existing_hooks:
            # Check if pane-color.sh is already referenced
            existing_str = json.dumps(existing_hooks[hook_name])
            if "pane-color.sh" in existing_str:
                skipped_keys.append(hook_name)
                continue
            # Append our hooks to existing ones
            existing_hooks[hook_name].extend(hook_value)
            merged_keys.append(hook_name)
        else:
            existing_hooks[hook_name] = hook_value
            merged_keys.append(hook_name)

    settings["hooks"] = existing_hooks

    if dry_run:
        return {
            "status": "ok",
            "action": "dry-run",
            "merged": merged_keys,
            "skipped": skipped_keys,
            "path": str(settings_path),
        }

    # Back up existing settings
    if settings_path.exists():
        backup = settings_path.with_suffix(".json.bak")
        shutil.copy2(settings_path, backup)

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    return {
        "status": "ok",
        "action": "merged",
        "merged": merged_keys,
        "skipped": skipped_keys,
        "backup": str(settings_path.with_suffix(".json.bak")),
        "path": str(settings_path),
    }


def uninstall(dry_run: bool = False) -> dict:
    """Remove pane-color.sh and hooks from settings.json."""
    script_path = Path.home() / ".claude" / "pane-color.sh"
    settings_path = Path.home() / ".claude" / "settings.json"
    actions = []

    # Remove script
    if script_path.exists():
        if not dry_run:
            script_path.unlink()
        actions.append(f"removed {script_path}")
    else:
        actions.append("pane-color.sh not found (already removed?)")

    # Remove hooks from settings
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {})
        cleaned = {}
        for hook_name, hook_list in hooks.items():
            filtered = [
                h for h in hook_list
                if "pane-color.sh" not in json.dumps(h)
            ]
            if filtered:
                cleaned[hook_name] = filtered
        if cleaned != hooks:
            settings["hooks"] = cleaned
            if not dry_run:
                backup = settings_path.with_suffix(".json.bak")
                shutil.copy2(settings_path, backup)
                settings_path.write_text(json.dumps(settings, indent=2) + "\n")
            actions.append("removed pane-color hooks from settings.json")
        else:
            actions.append("no pane-color hooks found in settings.json")

    return {"status": "ok", "action": "dry-run" if dry_run else "uninstalled", "details": actions}


def run(
    working_color: str = DEFAULT_WORKING_COLOR,
    accent_color: str = DEFAULT_ACCENT_COLOR,
    dry_run: bool = False,
    uninstall_flag: bool = False,
) -> dict:
    """Importable entry point for programmatic use.

    Args:
        working_color: Hex color for pane background when Claude is working (default: #112328).
        accent_color: Hex color for ANSI accent remap on tmux 3.3+ (default: #E7511F).
        dry_run: If True, show what would happen without making changes.
        uninstall_flag: If True, remove pane-color.sh and hooks.

    Returns:
        dict with keys: status, script_result, hooks_result (on install)
        dict with keys: status, action, details (on uninstall)
    """
    if uninstall_flag:
        return uninstall(dry_run)

    # Validate colors
    for label, color in [("working_color", working_color), ("accent_color", accent_color)]:
        color = color.lstrip("#")
        if len(color) != 6:
            return {"status": "error", "error": f"{label} must be a 6-digit hex color, got: #{color}"}
        try:
            int(color, 16)
        except ValueError:
            return {"status": "error", "error": f"{label} is not valid hex: #{color}"}

    # Check prerequisites
    prereqs = check_prerequisites()
    errors = [p for p in prereqs if not p.startswith("INFO:")]
    if errors:
        return {"status": "error", "error": "; ".join(errors)}

    script_result = install_script(working_color, accent_color, dry_run)
    if script_result["status"] != "ok":
        return script_result

    hooks_result = merge_hooks(dry_run)
    if hooks_result["status"] != "ok":
        return hooks_result

    tmux_info = [p for p in prereqs if p.startswith("INFO:")]

    return {
        "status": "ok",
        "script": script_result,
        "hooks": hooks_result,
        "tmux": tmux_info[0] if tmux_info else "unknown",
        "note": "Restart Claude Code sessions for hooks to take effect. Accent colors require tmux 3.3+.",
    }


def main() -> None:
    """CLI entry point — thin wrapper around run()."""
    parser = argparse.ArgumentParser(
        description="Install the Claude Code tmux pane-color notification system."
    )
    parser.add_argument(
        "--working-color",
        default=DEFAULT_WORKING_COLOR,
        help=f"Hex color for working state background (default: {DEFAULT_WORKING_COLOR})",
    )
    parser.add_argument(
        "--accent-color",
        default=DEFAULT_ACCENT_COLOR,
        help=f"Hex color for ANSI accent remap on tmux 3.3+ (default: {DEFAULT_ACCENT_COLOR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove pane-color.sh and hooks from settings",
    )
    args = parser.parse_args()

    result = run(
        working_color=args.working_color,
        accent_color=args.accent_color,
        dry_run=args.dry_run,
        uninstall_flag=args.uninstall,
    )

    if result["status"] == "error":
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("[DRY-RUN] No changes made.")

    if args.uninstall or result.get("action") == "dry-run":
        for detail in result.get("details", []):
            print(f"  {detail}")
    else:
        print(f"Script: {result['script']['action']} -> {result['script']['path']}")
        hooks = result["hooks"]
        if hooks["merged"]:
            print(f"Hooks merged: {', '.join(hooks['merged'])}")
        if hooks["skipped"]:
            print(f"Hooks skipped (already present): {', '.join(hooks['skipped'])}")
        if hooks.get("backup"):
            print(f"Settings backup: {hooks['backup']}")
        print(f"Tmux: {result['tmux']}")
        print(f"\nNote: {result['note']}")


if __name__ == "__main__":
    main()
