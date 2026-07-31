#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: "Single source of truth for where an agent's identity, memory, lenses and meditation
#   library live. Every memory-system script imports this instead of hardcoding a path, which is
#   what makes the system portable to any agent name on any machine. Resolution order:
#   $PVRAGON_AGENT_HOME -> config file -> $PVRAGON_AGENT (name) -> auto-detect the single directory
#   under ~/ai-workspace/agents/ that contains an identity.md. Raises a clear, actionable error when
#   it cannot decide, and never guesses between two candidates."
# created: 2026-07-30
# last_updated: 2026-07-30
# maintainer: pvragon
# ---
"""agent_paths.py — resolve the agent's on-disk home and its memory subdirectories.

Why this exists
---------------
The memory system was built for one agent and hardcoded that agent's directory in
eleven separate scripts. That is fine for one machine and fatal for reuse. This
module centralises the decision so a second agent, on a second machine, with a
different name, needs zero code edits.

Resolution order (first hit wins)
---------------------------------
1. ``$PVRAGON_AGENT_HOME`` — an absolute path to the agent directory. Explicit,
   wins over everything. Use this in CI, containers, or for a second agent.
2. ``<workspace>/personal/config/agent.json`` — ``{"agent_home": "..."}`` or
   ``{"agent": "<name>"}``. The normal way to pin a choice durably.
3. ``$PVRAGON_AGENT`` — a bare agent NAME, resolved under ``<workspace>/agents/``.
4. Auto-detect — directories under ``<workspace>/agents/`` containing an
   ``identity.md``. If exactly one, use it. (This is why a plain ``runtime/``
   scratch directory sitting beside the agents is not mistaken for an agent.)

If step 4 finds zero or more than one candidate, we raise instead of guessing.
Guessing here would silently write one agent's memory into another's directory.

The workspace root itself is ``$PVRAGON_WORKSPACE`` or ``~/ai-workspace``.

Everything is computed lazily and cached, so importing this module is free and
scripts that never touch the agent directory (e.g. a --help run) never fail.

CLI
---
    python3 agent_paths.py            # print the resolved paths
    python3 agent_paths.py --json     # machine-readable
    python3 agent_paths.py --check    # exit 1 if resolution fails or dirs are missing
"""

from __future__ import annotations

import functools
import json
import os
import sys
from pathlib import Path

__all__ = [
    "workspace", "agent_home", "memory_dir", "meditations_dir", "lenses_dir",
    "handoffs_dir",
    "journal_dir", "shortterm_dir", "state_dir", "exec_dir", "backlog_dir",
    "AgentResolutionError", "TOPIC_PREFIXES",
]

#: Filename prefixes that mark a file as a T2 topic memory. Shared so every
#: consumer agrees on what counts as a memory file.
TOPIC_PREFIXES = ("feedback_", "project_", "reference_", "user_", "process_", "handoff_")

#: A directory is an agent home iff it contains this file.
AGENT_MARKER = "identity.md"


class AgentResolutionError(RuntimeError):
    """Raised when the agent home cannot be determined unambiguously."""


@functools.lru_cache(maxsize=1)
def workspace() -> Path:
    """The workspace root ($PVRAGON_WORKSPACE, else ~/ai-workspace)."""
    env = os.environ.get("PVRAGON_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "ai-workspace").resolve()


def _from_config() -> Path | None:
    cfg = workspace() / "personal/config/agent.json"
    if not cfg.is_file():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    home = data.get("agent_home")
    if home:
        return Path(home).expanduser()
    name = data.get("agent")
    if name:
        return workspace() / "agents" / name
    return None


def _candidates() -> list[Path]:
    root = workspace() / "agents"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / AGENT_MARKER).is_file())


@functools.lru_cache(maxsize=1)
def agent_home() -> Path:
    """Resolve the agent directory. See module docstring for the order."""
    env = os.environ.get("PVRAGON_AGENT_HOME")
    if env:
        return Path(env).expanduser().resolve()

    cfg = _from_config()
    if cfg:
        return cfg.resolve()

    name = os.environ.get("PVRAGON_AGENT")
    if name:
        return (workspace() / "agents" / name).resolve()

    found = _candidates()
    if len(found) == 1:
        return found[0].resolve()

    root = workspace() / "agents"
    if not found:
        raise AgentResolutionError(
            f"No agent found. Looked for a directory containing '{AGENT_MARKER}' under {root}.\n"
            f"Fix by any one of:\n"
            f"  - create {root}/<your-agent>/{AGENT_MARKER}\n"
            f"  - export PVRAGON_AGENT_HOME=/path/to/agent\n"
            f"  - write {workspace()}/personal/config/agent.json "
            f'as {{"agent": "<your-agent>"}}'
        )
    names = ", ".join(p.name for p in found)
    raise AgentResolutionError(
        f"Ambiguous agent: {len(found)} candidates under {root} ({names}).\n"
        f"Refusing to guess — writing to the wrong agent's memory is unrecoverable.\n"
        f"Pin one with PVRAGON_AGENT=<name>, PVRAGON_AGENT_HOME=<path>, or "
        f'{workspace()}/personal/config/agent.json as {{"agent": "<name>"}}'
    )


def memory_dir() -> Path:
    """T2 topic memories, the index, and current-state live here."""
    return agent_home() / "memory"


def shortterm_dir() -> Path:
    """T1 episodic: dated facts + residue files."""
    return memory_dir() / "short-term"


def journal_dir() -> Path:
    """Dream-journal residue from reflective wakes."""
    return memory_dir() / "dream-journal"


def meditations_dir() -> Path:
    """The contemplation-object library."""
    return agent_home() / "meditations"


def lenses_dir() -> Path:
    """T3 situational lenses, injected by hook on a trigger match."""
    return agent_home() / "lenses"


def handoffs_dir() -> Path:
    """Session-rotation briefs, plus `.pending-enrichment/` pointers.

    Written by /handoff and read back by /session-debrief, which appends a
    "Debrief addendum" to the brief once it has findings the brief predates. Both
    sides must resolve the SAME directory or the addendum lands where nobody looks,
    so they resolve it here rather than each writing a literal path.
    """
    return agent_home() / "handoffs"


def state_dir() -> Path:
    """Scheduler/hook scratch state. Inside the agent home so it travels with it."""
    return agent_home() / "runtime" / "state"


def exec_dir() -> Path:
    """Directory holding these scripts — how siblings invoke each other."""
    return Path(__file__).resolve().parent


def backlog_dir() -> Path | None:
    """Optional. Where aged-out workstreams are formalised; None if absent."""
    override = os.environ.get("PVRAGON_BACKLOG_DIR")
    if override:
        p = Path(override).expanduser()
        return p if p.is_dir() else None
    for cand in (workspace() / "my-lib/backlog", agent_home() / "backlog"):
        if cand.is_dir():
            return cand
    return None


def _report() -> dict:
    return {
        "workspace": str(workspace()),
        "agent_home": str(agent_home()),
        "memory_dir": str(memory_dir()),
        "shortterm_dir": str(shortterm_dir()),
        "journal_dir": str(journal_dir()),
        "meditations_dir": str(meditations_dir()),
        "lenses_dir": str(lenses_dir()),
        "handoffs_dir": str(handoffs_dir()),
        "state_dir": str(state_dir()),
        "exec_dir": str(exec_dir()),
        "backlog_dir": str(backlog_dir()) if backlog_dir() else None,
    }


def main() -> int:
    as_json = "--json" in sys.argv
    check = "--check" in sys.argv
    try:
        rep = _report()
    except AgentResolutionError as exc:
        print(f"agent resolution FAILED:\n{exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(rep, indent=2))
    else:
        width = max(len(k) for k in rep)
        for k, v in rep.items():
            print(f"{k:<{width}}  {v}")
    if check:
        missing = [k for k, v in rep.items()
                   if v and k.endswith("_dir") and k != "backlog_dir" and not Path(v).is_dir()]
        if missing:
            print(f"\nmissing directories: {', '.join(missing)}\n"
                  f"run bootstrap_memory.py --apply to create them", file=sys.stderr)
            return 1
        print("\nall required directories present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
