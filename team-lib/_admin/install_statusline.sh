#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Installs the shared status line: points ~/.claude/statusline.sh at team-lib's copy and
#   registers the statusLine command in settings.json. Idempotent; never clobbers a real file
#   without backing it up. Without it a teammate has findings.py writing a statusline segment
#   that nothing renders."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# A POINTER, not a copy. The status line is a shared capability, so there is one implementation
# — _admin/statusline.sh — and the harness path links to it. Copying it into ~/.claude would
# recreate exactly the arrangement that let the agent-layer copy drift from the working copy.
#
# Usage: install_statusline.sh [--dry-run]

set -uo pipefail

ADMIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="${ADMIN_DIR}/statusline.sh"
CLAUDE_HOME="${HOME}/.claude"
TARGET="${CLAUDE_HOME}/statusline.sh"
SETTINGS="${CLAUDE_HOME}/settings.json"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

if [[ ! -f "$SOURCE" ]]; then
    echo "    ❌ No statusline at $SOURCE"
    exit 1
fi

run() { if [[ "$DRY_RUN" == "true" ]]; then echo "    🔍 would: $*"; else "$@"; fi; }

# --- the pointer ---
if [[ -L "$TARGET" && "$(readlink -f "$TARGET")" == "$(readlink -f "$SOURCE")" ]]; then
    echo "    ✅ ~/.claude/statusline.sh already points at team-lib"
else
    if [[ -e "$TARGET" && ! -L "$TARGET" ]]; then
        # A real file here predates the shared version, and may carry local edits nobody
        # wrote down. Keep it; a lost customisation is worse than a stale backup.
        echo "    ℹ️  Backing up existing ${TARGET} -> ${TARGET}.pre-teamlib"
        run cp "$TARGET" "${TARGET}.pre-teamlib"
    fi
    run mkdir -p "$CLAUDE_HOME"
    run rm -f "$TARGET"
    run ln -s "$SOURCE" "$TARGET"
    echo "    ✅ ~/.claude/statusline.sh -> $SOURCE"
fi
run chmod +x "$SOURCE"

# --- the registration ---
# Written with python3 rather than jq so this works on a box where the toolchain step has not
# run yet; settings.json is the harness's file and must never be corrupted by a partial write.
if [[ "$DRY_RUN" == "true" ]]; then
    echo "    🔍 would register statusLine in $SETTINGS"
    exit 0
fi

python3 - "$SETTINGS" <<'PY'
import json, os, sys, tempfile

path = sys.argv[1]
try:
    with open(path) as fh:
        data = json.load(fh)
except FileNotFoundError:
    data = {}
except ValueError as exc:
    print(f"    ❌ {path} is not valid JSON ({exc}) — leaving it alone")
    sys.exit(1)

want = {"type": "command", "command": "~/.claude/statusline.sh"}
if data.get("statusLine") == want:
    print("    ✅ statusLine already registered")
    sys.exit(0)
if "statusLine" in data and data["statusLine"] != want:
    print(f"    ℹ️  statusLine already set to something else — leaving it: {data['statusLine']}")
    sys.exit(0)

data["statusLine"] = want
os.makedirs(os.path.dirname(path), exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
with os.fdopen(fd, "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
os.replace(tmp, path)          # atomic: a half-written settings.json breaks every session
print("    ✅ statusLine registered in settings.json")
PY
