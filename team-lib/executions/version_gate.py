#!/usr/bin/env python3
# ---
# template: execution-script
# version: 1.1.0
# summary: PreToolUse hook on `git push` that keeps frontmatter versions honest.
#   For every versioned file whose BODY changed in the commits about to be pushed
#   without its `version:` changing, it bumps the patch level, stamps
#   `last_updated`, syncs any registry entry that records the same version, and
#   commits that as a `chore(version)` commit so the push carries it. Resolves the
#   standing tension between AGENTS.md Op#10 (commit early and often) and the
#   frontmatter versioning rule: a commit is a private checkpoint, a version is a
#   published identity, so the version only has to be right at the publish
#   boundary — which here is the push. Opt out or escalate per-push with
#   [no-version], [minor] or [major] in any commit message in the range.
#   Never blocks: any error defers silently so a push is never lost to this hook.
# created: 2026-07-30
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""Keep frontmatter versions honest at the push boundary.

WHY THIS EXISTS (measured 2026-07-30)
-------------------------------------
AGENTS.md mandates a frontmatter `version:` and says to increment it on
"meaningful changes". Nothing enforced it. Across 90 days the non-`ext-` skill
corpus ran 91 commits against 57 version bumps — 62% — and `last_updated` was
worse at 44%. The distribution was the tell: skills touched once per sitting sat
at 100%, while skills worked iteratively across long sessions collapsed
(session-debrief 23 commits / 6 bumps = 26%).

That is not forgetfulness, it is two rules in tension. Op#10 correctly says to
commit at every logical checkpoint and "when in doubt, commit". The versioning
rule says to increment on meaningful changes. Follow both literally and seven
commits in an afternoon are collectively one minor version — bump on each and the
number inflates into meaninglessness, bump once and six commits ship unversioned.
Nothing said which, so under time pressure it silently became neither.

The resolution is to stop treating a commit and a version as the same unit. A
commit is a private checkpoint for the author's own safety. A version is a
published identity, for consumers: teammates reading team-lib, the drift scan,
the registry. They answer to different audiences. So the version does not have to
be right at every commit — only at the moment content becomes visible to someone
else, which in this workspace is the push.

Hence: commit as often as you like with zero version friction, and let this hook
make the version true exactly once, at the boundary where it starts to matter.

WHY IT BUMPS RATHER THAN BLOCKS
-------------------------------
Blocking would put a judgment call (patch vs minor vs major) in front of the one
action that is already deliberately gated, at the end of a session — precisely
when judgment is worst and precisely how the rule decayed to 62% in the first
place. An under-bumped version is enormously better than a stale one: it is still
monotonic, still distinguishes content, and still lets the drift scan compare.
So the default is patch, applied automatically and reported loudly, with
`[minor]`/`[major]` available when the author already knows better.
"""
import datetime
import json
import os
import re
import subprocess
import sys

# Overridable so the hook can be exercised against a throwaway repo without
# loosening the guard in normal use.
WORKSPACE = os.environ.get("VERSION_GATE_ROOT", os.path.expanduser("~/ai-workspace"))

# Markdown YAML frontmatter, and the `# ---` comment-block used by scripts.
MD_VERSION = re.compile(r"^(version:\s*[\"']?)(\d+)\.(\d+)\.(\d+)([\"']?\s*)$", re.M)
SH_VERSION = re.compile(r"^(#\s*version:\s*)(\d+)\.(\d+)\.(\d+)(\s*)$", re.M)
MD_UPDATED = re.compile(r"^(last_updated:\s*)(\S+)(\s*)$", re.M)
SH_UPDATED = re.compile(r"^(#\s*last_updated:\s*)(\S+)(\s*)$", re.M)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, timeout=25
    ).stdout.strip()


def pick(path):
    """Return (version_re, updated_re) for a path, or (None, None) if unversioned."""
    if path.endswith(".md"):
        return MD_VERSION, MD_UPDATED
    if path.endswith((".py", ".sh")):
        return SH_VERSION, SH_UPDATED
    return None, None


def bump(v, level):
    major, minor, patch = v
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


LAYERS = ("my-lib", "team-lib")

#: The generated public repo, relative to WORKSPACE. Kept in step with
#: registry/mirror.yaml `layers.public`. Never versioned in place — see main().
PUBLIC_LAYER = "projects/ai-workspace-reference"


def counterpart(repo, rel):
    """Absolute path to this file's opposite-layer twin, or None.

    Layers are sibling dirs under the workspace, and mirrored capabilities sit at
    the SAME relative path in each, so the twin is just the other layer's copy.
    """
    name = os.path.basename(repo.rstrip("/"))
    if name not in LAYERS:
        return None
    other = LAYERS[1] if name == LAYERS[0] else LAYERS[0]
    other_repo = os.path.join(os.path.dirname(repo.rstrip("/")), other)
    path = os.path.join(other_repo, rel)
    return (other_repo, path) if os.path.isfile(path) else None


def mirror_bump(repo, rel, orig, new_text, new_version, report, mirrored):
    """Carry a bump across to a byte-identical twin so the mirror survives it.

    Bumping one half of a mirrored pair DESYNCS it — observed 2026-07-30 on
    session-debrief, whose two copies had been made byte-identical minutes earlier
    and were split apart by this very hook. The gate was per-repo and knew nothing
    about the mirror contract.

    The equality test is deliberately strict: the twin is updated ONLY if it still
    matches the pre-bump content exactly. If the two had already diverged, that is
    real drift — someone else's problem to reconcile, and silently overwriting it
    here would destroy their work while looking like routine version hygiene.
    """
    cp = counterpart(repo, rel)
    if cp is None:
        return
    other_repo, path = cp
    try:
        if open(path).read() != orig:
            return  # already divergent -> not a mirror, leave it alone
        open(path, "w").write(new_text)
    except OSError:
        return
    sync_registry(other_repo, rel, new_version, report)
    mirrored.setdefault(other_repo, []).append(rel)
    report.append(f"    mirror: same bump applied to {os.path.basename(other_repo)}/{rel}")


def sync_registry(repo, rel_path, new_version, report):
    """Update any registry entry whose `path:` names this file.

    Registry drift is the same defect one level up — test-multiplayer sat at
    0.1.0 in registry/skills.yaml against a 0.3.4 file. Fixing the file while
    leaving the manifest stale would just move the lie.
    """
    reg_dir = os.path.join(repo, "registry")
    if not os.path.isdir(reg_dir):
        return
    for fname in os.listdir(reg_dir):
        if not fname.endswith(".yaml"):
            continue
        fpath = os.path.join(reg_dir, fname)
        try:
            text = open(fpath).read()
        except OSError:
            continue
        # Find the entry block that declares this path, then the next version: in it.
        m = re.search(
            r'path:\s*["\']?%s["\']?\s*\n(.*?)(^\s*version:\s*")([^"]+)(")'
            % re.escape(rel_path),
            text,
            re.S | re.M,
        )
        if not m or m.group(3) == new_version:
            continue
        updated = text[: m.start(3)] + new_version + text[m.end(3) :]
        open(fpath, "w").write(updated)
        report.append(f"    registry/{fname} synced {m.group(3)} -> {new_version}")


def resolve_pushed_repo(cmd, cwd_hint, note=lambda *a: None):
    """Which repo does this command actually push? Shared by every push-boundary hook.

    A hook sees command TEXT, never the expanded shell, so the target has to be
    inferred. Two forms have already bitten us, both by silently falling through to
    the session cwd — which is whatever directory the PREVIOUS command left behind:

      `git -C $VAR push`       -> literal "$VAR"           (2026-07-31)
      `cd <repo> && git push`  -> the cd is invisible      (2026-08-01)

    The second one made version_gate version the generated public repo while the
    source layer shipped unversioned. This lives in one place precisely so a second
    push-boundary hook cannot re-acquire the same bug independently.

    `note` is an optional logging callback (event, detail).
    """
    repo = None

    m = re.search(r"git\s+-C\s+(\S+)", cmd)
    if m:
        cand = os.path.expanduser(m.group(1))
        if os.path.isdir(cand):
            repo = cand
        else:
            note("unexpanded-C", m.group(1)[:40])

    if repo is None:
        cd = re.search(r"(?:^|&&|;|\|)\s*cd\s+(\S+)", cmd)
        if cd:
            cand = os.path.expanduser(cd.group(1).strip("'\""))
            if os.path.isdir(cand):
                repo = cand
            else:
                note("unexpanded-cd", cd.group(1)[:40])

    repo = repo or cwd_hint or os.getcwd()
    return git(repo, "rev-parse", "--show-toplevel") or repo


HEARTBEAT = os.path.expanduser("~/.claude/version-gate.log")


def beat(event, detail=""):
    """Append one line per invocation, so 'did the gate fire?' is answerable.

    A gate that silently stops firing is indistinguishable from a gate with nothing
    to do — that is the unfalsifiable-safeguard trap, and this one fell into it: it
    was registered, intact, and correct when run by hand, while not actually being
    reached on any real push for hours. Nobody could tell, because success and
    absence looked identical. Now every invocation leaves a trace, and `--self-check`
    compares the last beat against the last push.
    """
    try:
        with open(HEARTBEAT, "a") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{event}\t{detail}\n")
    except OSError:
        pass  # never let logging cost a push


def self_check():
    """Report whether the gate is actually reaching pushes. Exit 1 if it looks dead."""
    if not os.path.exists(HEARTBEAT):
        print("version-gate: NEVER FIRED — no heartbeat log at " + HEARTBEAT)
        print("  The hook is not being invoked. Check ~/.claude/settings.json, and note that")
        print("  an `if:` prefix rule like Bash(git *) will NOT match a compound command such")
        print("  as `cd repo && git push`. Open /hooks once to reload settings after editing.")
        return 1
    lines = [l for l in open(HEARTBEAT).read().splitlines() if l.strip()]
    pushes = [l for l in lines if "\tpush\t" in l or "\tbump\t" in l]
    print(f"version-gate: {len(lines)} invocation(s) logged, {len(pushes)} on a push")
    for l in lines[-5:]:
        print("  " + l)
    if not pushes:
        print("\n  invoked, but never on a push — the command filter is too narrow.")
        return 1
    return 0


def main():
    if "--self-check" in sys.argv:
        sys.exit(self_check())

    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "")
    # Matches ANYWHERE in the command, so compound forms like `cd repo && git push`
    # are caught. The settings-level `if:` filter must stay absent or broad for the
    # same reason: permission-rule syntax is prefix-only and would miss those.
    if not re.search(r"\bgit\s+(-C\s+\S+\s+)?push\b", cmd):
        beat("skip", "not-a-push")
        sys.exit(0)
    beat("push", cmd[:80].replace("\n", " "))

    repo = resolve_pushed_repo(cmd, data.get("cwd"), beat)
    if not repo.startswith(WORKSPACE):
        beat("skip", f"outside workspace: {repo}")
        sys.exit(0)  # not ours to police

    # A GENERATED artifact must never be versioned here. The public reference repo
    # is produced by publish_public_reference.py from team-lib, so its versions are
    # team-lib's versions; bumping them in place makes the derived copy claim a
    # version its source never had, and the next publish silently reverts it.
    # Belt and braces with the cd/-C resolution above: that stops us ARRIVING here
    # by accident, this stops us acting even if we do.
    if os.path.realpath(repo) == os.path.realpath(os.path.join(WORKSPACE, PUBLIC_LAYER)):
        beat("skip", "generated artifact — versions come from the source layer")
        print("[version-gate] SKIPPED — this is the generated public repo. Version it in\n"
              "               team-lib and re-run publish_public_reference.py.", file=sys.stderr)
        sys.exit(0)

    # A hook runs BEFORE its command. So `git add && git commit && git push` in ONE
    # invocation shows us the state as it was BEFORE the commit — the commit we would
    # need to inspect does not exist yet, the outgoing range is empty, and we exit
    # having done nothing. This silently defeated the gate for hours: it was firing
    # correctly and finding nothing, because the commit was still in the future.
    if re.search(r"\bgit\s+(-C\s+\S+\s+)?commit\b", cmd):
        beat("blind", "commit and push in one command — cannot see the pending commit")
        print("[version-gate] NOT CHECKED — this command commits and pushes together, so the\n"
              "               commit does not exist yet when the hook runs. Run the push as a\n"
              "               separate command to let the gate see it.", file=sys.stderr)
        sys.exit(0)

    # --- split-capability advisory ---------------------------------------
    # A push is when a graduation becomes real for someone else, which makes it
    # the enforceable equivalent of "check at graduation time". The graduation
    # SCRIPT is not that point: it went five months unused, and neither real
    # graduation invoked it — a gate inside a tool nobody calls catches nothing.
    #
    # This WARNS rather than blocks, deliberately. Nothing in this hook has ever
    # been able to cost someone a push, and a split is not always a mistake; the
    # cost of a false block is higher than the cost of a loud warning delivered
    # at exactly the right moment. The nightly scan carries the same check as the
    # backstop for anything already on main.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from layer_drift_scan import _split_capabilities  # noqa: E402
        _p = os.path.join(WORKSPACE, "my-lib")
        _s = os.path.join(WORKSPACE, "team-lib")
        if os.path.isdir(_p) and os.path.isdir(_s):
            import pathlib as _pl
            splits = _split_capabilities(_pl.Path(_p), _pl.Path(_s))
            if splits:
                beat("split", ",".join(f["item"] for f in splits))
                print("[version-gate] SPLIT CAPABILITY — team-lib ships only part of "
                      f"{len(splits)} capability(ies):", file=sys.stderr)
                for f in splits:
                    print(f"    {f['item']}: team-lib has {', '.join(f['shared_has'])}"
                          f" but NOT {', '.join(f['personal_only'])}", file=sys.stderr)
                print("    A teammate installing team-lib gets a fragment they cannot use.\n"
                      "    Graduate the missing piece, or record why the split is intended.",
                      file=sys.stderr)
    except Exception:
        pass  # advisory only: never cost anyone a push

    # What is actually about to be pushed?
    rng = git(repo, "rev-list", "--count", "@{u}..HEAD")
    if not rng or rng == "0":
        beat("nothing", "no outgoing commits (or no upstream)")
        sys.exit(0)

    msgs = git(repo, "log", "--format=%B", "@{u}..HEAD").lower()
    if "[no-version]" in msgs:
        beat("optout", "[no-version] in range")
        sys.exit(0)
    level = "major" if "[major]" in msgs else "minor" if "[minor]" in msgs else "patch"

    changed = [f for f in git(repo, "diff", "--name-only", "@{u}..HEAD").splitlines() if f]
    today = git(repo, "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d") or ""

    report, bumped, mirrored = [], [], {}
    for rel in changed:
        ver_re, upd_re = pick(rel)
        if ver_re is None:
            continue
        full = os.path.join(repo, rel)
        if not os.path.isfile(full):
            continue
        try:
            text = open(full).read()
        except OSError:
            continue
        vm = ver_re.search(text)
        if not vm:
            continue  # unversioned file — not in scope

        # Did the version line itself change in this range? If so, respect it.
        diff = git(repo, "diff", "-U0", "@{u}..HEAD", "--", rel)
        if re.search(r"^\+\s*#?\s*version:", diff, re.M):
            continue

        orig = text  # pre-bump content, for the mirror-equality test below
        old = (int(vm.group(2)), int(vm.group(3)), int(vm.group(4)))
        new = bump(old, level)
        new_s = "%d.%d.%d" % new
        text = text[: vm.start()] + f"{vm.group(1)}{new_s}{vm.group(5)}" + text[vm.end():]
        um = upd_re.search(text)
        if um and today:
            text = text[: um.start()] + f"{um.group(1)}{today}{um.group(3)}" + text[um.end():]
        open(full, "w").write(text)

        old_s = "%d.%d.%d" % old
        report.append(f"  {rel}")
        report.append(f"    body changed since last push, version unchanged")
        report.append(f"    -> auto-bumped {old_s} -> {new_s} ({level}), stamped last_updated")
        sync_registry(repo, rel, new_s, report)
        bumped.append(rel)
        mirror_bump(repo, rel, orig, text, new_s, report, mirrored)

    if not bumped:
        beat("nothing", "no versioned file changed without a bump")
        sys.exit(0)

    # Commit the bump BEFORE the push runs, so the push carries it. Without this
    # the version lands in the working tree and the pushed commits stay stale —
    # the exact drift this hook exists to stop.
    git(repo, "add", "--", *bumped, "registry")
    subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m",
         "chore(version): bump %d versioned file(s) at push boundary\n\n"
         "Auto-applied by version_gate.py. A commit is a checkpoint; a version is a\n"
         "published identity, so the version is made true at the publish boundary\n"
         "rather than at every commit. Use [minor]/[major] to escalate or\n"
         "[no-version] to skip." % len(bumped)],
        capture_output=True, text=True, timeout=25,
    )

    # Commit the mirrored halves in THEIR repos too. Not pushed from here — that repo
    # gets pushed on its own schedule — but committing keeps the twin from sitting
    # dirty and getting swept into an unrelated commit by whoever pushes it next.
    for other_repo, files in mirrored.items():
        git(other_repo, "add", "--", *files, "registry")
        subprocess.run(
            ["git", "-C", other_repo, "commit", "-q", "-m",
             "chore(version): mirror %d version bump(s) from the paired layer\n\n"
             "Auto-applied by version_gate.py. These files are byte-identical twins of\n"
             "the layer just pushed; bumping only one side would desync the mirror.\n"
             "[no-version]" % len(files)],
            capture_output=True, text=True, timeout=25,
        )

    beat("bump", ",".join(bumped))
    print(f"[version-gate] {len(bumped)} file(s) bumped, 0 blocked", file=sys.stderr)
    print("\n".join(report), file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # never cost anyone a push
