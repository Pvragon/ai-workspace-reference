#!/usr/bin/env bash
# ---
# template: execution
# version: 1.0.0
# summary: "Installs the agent memory system end to end: bootstrap the memory data, register the
#   harness hooks, install the nightly cron, then prove the wiring with verify_memory_install.py.
#   Idempotent and safe to re-run. Handles the case setup cannot avoid — a workspace that has no
#   named agent yet — by wiring the agent-independent half and exiting 2 (DEFERRED) rather than
#   reporting success, so a half-install is never mistaken for a finished one."
# created: 2026-07-31
# last_updated: 2026-07-31
# maintainer: pvragon
# ---
#
# Why this script exists
# ----------------------
# setup_workspace.sh produced a populated library but not a running agent: no
# reinforcement hook, no nightly dream cycle, no memory index. ONBOARDING.md named the
# three scripts as manual steps and nothing chained them, so an install that skipped
# Phase 7.5 looked identical to one that completed it.
#
# The ordering problem this solves
# --------------------------------
# The memory data install needs an agent home, and the agent does not exist until the
# choose-name ceremony, which happens INSIDE the agent's first session — after setup has
# already finished. So setup genuinely cannot complete this install. It can wire the
# agent-independent half (the hooks resolve their agent lazily and are designed to exit 0
# when there is none), and it must say plainly that the rest is pending.
#
# Exit codes are the contract:
#   0  COMPLETE — memory bootstrapped, hooks registered, cron installed, verify passed
#   2  DEFERRED — no agent yet; hooks wired, memory + cron pending. NOT a failure.
#   1  FAILED   — something that should have worked did not
#
# Deliberately no `set -e`: every step is checked explicitly so a failure is reported
# with its context instead of vanishing into an early exit.

set -uo pipefail

# Resolve our own location so this works from any clone path (the container harness
# runs it from a fresh checkout, not from ~/ai-workspace).
ADMIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXEC_DIR="$(cd "${ADMIN_DIR}/../executions" && pwd 2>/dev/null || echo "")"
WORKSPACE_ROOT="${PVRAGON_WORKSPACE:-$HOME/ai-workspace}"

# The memory chain is stdlib-only (verified: agent_paths, bootstrap_memory,
# install_memory_hooks, verify_memory_install and every hook import nothing outside the
# standard library). So it does NOT need my-lib/.venv, and a failed venv step upstream
# must not prevent memory from installing.
PY="${PYTHON:-python3}"

APPLY=1
CRON_FLAG=""
AGENT_NAME=""

usage() {
    cat <<'EOF'
install_memory.sh — install the agent memory system (idempotent).

  --dry-run        report what would change; write nothing
  --apply          accepted and ignored — installing is already the default
  --no-cron        register hooks but skip the nightly crontab entries
  --agent NAME     scaffold an agent home of this name first (non-interactive installs:
                   CI, containers, or anyone who does not want the naming ceremony)
  -h, --help       this text

Exit: 0 complete, 2 deferred (no agent yet — re-run after choose-name), 1 failed.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) APPLY=0; shift ;;
        # Applying IS the default here, but every script this chains takes --apply,
        # so accept it rather than erroring on the reflex.
        --apply)   APPLY=1; shift ;;
        --no-cron) CRON_FLAG="--no-cron"; shift ;;
        --agent)   AGENT_NAME="${2:-}"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "install_memory.sh: unknown argument '$1'" >&2; usage >&2; exit 1 ;;
    esac
done

APPLY_FLAG=""
TAG="  [dry-run]"
if [[ $APPLY -eq 1 ]]; then
    APPLY_FLAG="--apply"
    TAG=""
fi

echo ""
echo "=== Agent Memory System ==="

if [[ -z "$EXEC_DIR" || ! -d "$EXEC_DIR" ]]; then
    echo "    ❌ executions/ not found next to _admin/ — is this a complete team-lib clone?"
    exit 1
fi

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "    ❌ $PY not found. Install Python 3, then re-run: bash ${ADMIN_DIR}/install_memory.sh"
    exit 1
fi

# ---------------------------------------------------------------- agent check ----
# Three states, kept distinct on purpose: resolvable / absent / ambiguous. Collapsing
# "cannot tell" into "fine, continue" is exactly how a half-install passes for a whole
# one, so each state gets its own branch and its own exit code.
AGENT_STATUS="absent"
if [[ -n "$AGENT_NAME" ]]; then
    # bootstrap --agent scaffolds the home, so treat this as resolvable up front.
    AGENT_STATUS="named"
elif "$PY" "${EXEC_DIR}/agent_paths.py" --json >/dev/null 2>&1; then
    AGENT_STATUS="resolvable"
elif [[ -d "${WORKSPACE_ROOT}/agents" ]] \
     && [[ $(find "${WORKSPACE_ROOT}/agents" -mindepth 2 -maxdepth 2 -name identity.md 2>/dev/null | wc -l) -gt 1 ]]; then
    AGENT_STATUS="ambiguous"
fi

if [[ "$AGENT_STATUS" == "ambiguous" ]]; then
    echo "    ❌ More than one agent home found under ${WORKSPACE_ROOT}/agents."
    echo "       Refusing to guess — writing one agent's memory into another's is unrecoverable."
    echo "       Pin one, then re-run:  PVRAGON_AGENT=<name> bash ${ADMIN_DIR}/install_memory.sh"
    exit 1
fi

# ------------------------------------------------------- deferred (no agent) ----
if [[ "$AGENT_STATUS" == "absent" ]]; then
    echo "    ℹ️  No agent exists yet — that is expected on a first install."
    echo "       The agent names itself in its first session (ONBOARDING Phase 7), which"
    echo "       is what creates the home this install writes into."
    echo ""
    echo "    ---> Wiring the agent-independent half now (hooks; cron deferred)"

    # Hooks resolve their agent lazily and exit 0 when there is none — a designed,
    # tested state (verify_memory_install.py asserts it). Cron is NOT installed yet:
    # a nightly job that fails every night until someone runs the ceremony is worse
    # than one installed by the same script ten minutes later.
    if [[ $APPLY -eq 1 ]]; then
        if "$PY" "${EXEC_DIR}/install_memory_hooks.py" --apply --no-cron; then
            echo "    ✅ Hooks registered (they no-op safely until an agent exists)."
        else
            echo "    ⚠️  Hook registration failed — re-run after naming your agent."
        fi
    else
        "$PY" "${EXEC_DIR}/install_memory_hooks.py" --no-cron || true
    fi

    cat <<EOF

    ⏸  MEMORY INSTALL DEFERRED — this is the intended sequence, not a shortfall.

       The naming ceremony is a christening: it happens once the workspace exists,
       and the agent chooses its own name. Setup deliberately does not pre-empt
       that by inventing one. So the order is, and should be:

           workspace setup  ->  the ceremony  ->  memory

       After your agent has named itself (ONBOARDING Phase 7), run:

           bash ${ADMIN_DIR}/install_memory.sh

       Until then the agent has no memory: every session starts from nothing.
       validate.sh reports this state, so it will keep reminding you.
EOF
    exit 2
fi

# ------------------------------------------------------------ full install ----
FAILED=0

echo ""
echo "    ---> 1/3 Bootstrapping memory data${TAG}"
BOOTSTRAP_ARGS=()
[[ -n "$AGENT_NAME" ]] && BOOTSTRAP_ARGS+=(--agent "$AGENT_NAME")
[[ -n "$APPLY_FLAG" ]] && BOOTSTRAP_ARGS+=("$APPLY_FLAG")
if "$PY" "${EXEC_DIR}/bootstrap_memory.py" "${BOOTSTRAP_ARGS[@]}"; then
    echo "    ✅ Memory data bootstrapped."
else
    echo "    ❌ bootstrap_memory.py failed."
    FAILED=1
fi

# A named agent only becomes resolvable once its home is on disk, which the step above
# just did. Pin it for the remaining steps so they cannot pick a different candidate.
if [[ -n "$AGENT_NAME" && $APPLY -eq 1 ]]; then
    export PVRAGON_AGENT="$AGENT_NAME"
fi

echo ""
echo "    ---> 2/3 Registering hooks${CRON_FLAG:+ (cron skipped)}${TAG}"
HOOK_ARGS=()
[[ -n "$APPLY_FLAG" ]] && HOOK_ARGS+=("$APPLY_FLAG")
[[ -n "$CRON_FLAG" ]] && HOOK_ARGS+=("$CRON_FLAG")
if "$PY" "${EXEC_DIR}/install_memory_hooks.py" "${HOOK_ARGS[@]}"; then
    echo "    ✅ Hooks registered${CRON_FLAG:+ (no cron, as requested)}."
else
    echo "    ❌ install_memory_hooks.py failed."
    FAILED=1
fi

echo ""
if [[ $APPLY -eq 0 ]]; then
    echo "    ---> 3/3 Verification skipped (dry run — there is nothing installed to verify)"
    echo ""
    echo "=== Dry run complete. Re-run without --dry-run to install. ==="
    exit 0
fi

echo "    ---> 3/3 Verifying the wiring is live"
# This is the whole point of the chain: files existing is not the same as hooks firing.
# A disconnected hook is invisible — memories just stop gaining strength, silently.
if "$PY" "${EXEC_DIR}/verify_memory_install.py"; then
    echo "    ✅ Verified: the memory system is wired and firing."
else
    echo "    ❌ verify_memory_install.py reported a hard failure (see above)."
    echo "       Diagnose with:  ${PY} ${EXEC_DIR}/verify_memory_install.py --verbose"
    FAILED=1
fi

echo ""
if [[ $FAILED -eq 0 ]]; then
    echo "=== Memory system installed. ==="
    exit 0
fi
echo "=== Memory install INCOMPLETE — see the errors above. ==="
echo "    Re-run once fixed:  bash ${ADMIN_DIR}/install_memory.sh"
exit 1
