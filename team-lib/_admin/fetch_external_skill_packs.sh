#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Fetches the third-party skill packs into skills/_external from their upstream
#   repos, for installs where they are not git submodules — i.e. anyone who installed from
#   the public reference repo. Reads .gitmodules, so the pack list has exactly one source.
#   Idempotent: a pack that already has content is left alone."
# created: 2026-08-01
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
#
# Why this exists
# ---------------
# The packs are third-party repos. A team install gets them as submodules; the public
# reference repo does not republish their content, because redistributing three other
# people's repositories is a licensing decision we have no reason to make when a clone
# from source costs one command. Without this script a public installer ends up with
# `skills/_external/` empty and every ext-* skill — including the humanizer gate that
# AGENTS.md makes a hard rule — pointing at nothing.
#
# The pack list comes from .gitmodules and nowhere else. A second manifest would be a
# second thing to forget to update.
#
# Usage: fetch_external_skill_packs.sh [--dry-run]

set -uo pipefail

ADMIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEAM_LIB="$(cd "${ADMIN_DIR}/.." && pwd)"
GITMODULES="${TEAM_LIB}/.gitmodules"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

if [[ ! -f "$GITMODULES" ]]; then
    echo "    ℹ️  No .gitmodules — nothing to fetch."
    exit 0
fi

# A pack already provided by a submodule checkout must not be touched.
if git -C "$TEAM_LIB" rev-parse --git-dir &>/dev/null \
   && [[ -n "$(git -C "$TEAM_LIB" submodule status 2>/dev/null)" ]]; then
    git -C "$TEAM_LIB" submodule update --init --recursive 2>/dev/null \
        || echo "    ⚠️  Submodule init incomplete; falling through to direct clones."
fi

fetched=0; present=0; failed=0
while read -r key path; do
    name="${key#submodule.}"; name="${name%.path}"
    url=$(git config -f "$GITMODULES" --get "submodule.${name}.url" 2>/dev/null || true)
    target="${TEAM_LIB}/${path}"
    pack=$(basename "$path")

    if [[ -n "$(find "$target" -name 'SKILL.md' -print -quit 2>/dev/null)" ]]; then
        present=$((present+1))
        continue
    fi
    if [[ -z "$url" ]]; then
        echo "    ⚠️  $pack: no url in .gitmodules — skipped"
        failed=$((failed+1))
        continue
    fi
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "    🔍 would clone $url -> $path"
        fetched=$((fetched+1))
        continue
    fi

    echo "    Fetching $pack from $url..."
    mkdir -p "$(dirname "$target")"
    rm -rf "$target"
    if git clone --depth 1 --quiet "$url" "$target"; then
        # Not a nested repo: the pack is content here, not a tracked submodule, and a
        # stray .git would make the parent repo treat it as an unregistered gitlink.
        rm -rf "${target}/.git"
        fetched=$((fetched+1))
    else
        echo "    ⚠️  $pack: clone failed — retry later: git clone --depth 1 $url $target"
        failed=$((failed+1))
    fi
done < <(git config -f "$GITMODULES" --get-regexp '^submodule\..*\.path$' 2>/dev/null)

echo "    External skill packs: $fetched fetched, $present already present, $failed failed."
[[ $failed -eq 0 ]]
