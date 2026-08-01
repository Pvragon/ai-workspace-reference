#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Writes each external skill pack's currently-checked-out commit into .gitmodules as
#   submodule.<name>.commit, so an install that has no gitlinks (anyone installing from the
#   public reference repo) can pin to the same commit the team tested instead of tracking
#   upstream HEAD. Run after bumping a submodule."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Why a custom key rather than a lock file
# ----------------------------------------
# A gitlink carries the pin, but gitlinks are exactly what the public repo does not have —
# it publishes .gitmodules as a plain file and clones the packs from source. A separate
# lock file would be a second place to record the same fact, and the two would drift on the
# first submodule bump nobody ran this for. `submodule.<name>.commit` is ignored by git and
# lives in the file already published, so the pack list and its pins stay one artifact.
#
# Measured 2026-08-01: unpinned, a container install fetched upstream HEAD and ended with
# 526 external skills where this machine's pinned checkouts give 88 — a different, larger,
# unvetted surface, installed by a script, in a workspace that ships a malware eradicator.
#
# Usage: update_external_pack_pins.sh [--check]
#   --check   report drift between .gitmodules pins and the checked-out commits; write nothing

set -uo pipefail

ADMIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEAM_LIB="$(cd "${ADMIN_DIR}/.." && pwd)"
GITMODULES="${TEAM_LIB}/.gitmodules"
CHECK_ONLY=false
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=true

if [[ ! -f "$GITMODULES" ]]; then
    echo "    ℹ️  No .gitmodules — nothing to pin."
    exit 0
fi

updated=0; current=0; missing=0
while read -r key path; do
    name="${key#submodule.}"; name="${name%.path}"
    sha=$(git -C "$TEAM_LIB" rev-parse "HEAD:${path}" 2>/dev/null || true)
    if [[ -z "$sha" ]]; then
        echo "    ⚠️  ${path}: no gitlink — cannot pin (is it a submodule here?)"
        missing=$((missing+1))
        continue
    fi
    pinned=$(git config -f "$GITMODULES" --get "submodule.${name}.commit" 2>/dev/null || true)
    if [[ "$pinned" == "$sha" ]]; then
        current=$((current+1))
        continue
    fi
    if [[ "$CHECK_ONLY" == "true" ]]; then
        echo "    ⚠️  ${path}: pin ${pinned:-<none>} != checked-out ${sha:0:12}"
        updated=$((updated+1))
        continue
    fi
    git config -f "$GITMODULES" "submodule.${name}.commit" "$sha"
    echo "    pinned ${path} -> ${sha:0:12}"
    updated=$((updated+1))
done < <(git config -f "$GITMODULES" --get-regexp '^submodule\..*\.path$' 2>/dev/null)

if [[ "$CHECK_ONLY" == "true" ]]; then
    echo "    Pins: $current current, $updated stale, $missing unpinnable."
    [[ $updated -eq 0 && $missing -eq 0 ]]
else
    echo "    Pins: $updated written, $current already current, $missing unpinnable."
    [[ $missing -eq 0 ]]
fi
