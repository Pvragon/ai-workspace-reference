#!/usr/bin/env python3
# ---
# template: execution-script
# version: 1.3.1
# summary: >-
#   PreToolUse hook on `git push`. For every versioned file whose BODY changed in the outgoing
#   commits without its `version:` changing, it bumps the patch level, stamps `last_updated`,
#   regenerates the registry manifests and directory indexes, mirrors the bump to a
#   byte-identical twin, and commits so the push carries it. Never blocks;
#   [minor]/[major]/[no-version] override.
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
import difflib
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


def header_end(path, text):
    """End offset of the file's own metadata header; 0 when it has none.

    Version and date are read and stamped ONLY inside it. Searching the whole file stamped a
    template EXAMPLE in a body (`last_updated: [YYYY-MM-DD]` in a generated OPERATING-CORE,
    2026-10-21), which also made every regenerated core read as stale.
    """
    if path.endswith(".md"):
        if not text.startswith("---\n"):
            return 0
        end = text.find("\n---", 4)
        return end if end > 0 else 0
    lines = text.splitlines(keepends=True)[:40]  # a script's `# ---` header block lives at the top
    return sum(len(l) for l in lines)


def is_generated(header):
    """A file whose header says `generated_by:` is a build artifact: its source is versioned, it is not."""
    return re.search(r"^#?\s*generated_by:", header, re.M) is not None


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


def registry_gate(repo, report, apply=True):
    """Make the repo's DERIVABLE manifests and directory indexes true at the publish boundary.

    Returns the LIST of repo-relative paths written (falsy when nothing was) — not a bool.
    ⚑ It returned a bool until 2026-08-08, and both callers staged the literal path "registry".
    That was correct while manifests were the only thing this wrote; adding index.md generation
    below would have written files in `skills/`, `executions/`, `directives/`, `personas/` and
    `context/indexed/` that NOTHING staged, so the push would carry the manifest and leave the
    index dirty in the working tree — a gate that half-fires and reports success. The caller can
    only stage what the gate tells it about, so the gate names every file it touched.

    `apply=False` measures and reports without writing — which is how the nightly tick inspects
    PROJECT repos. Those have live branches and worktrees belonging to other sessions, so a
    scheduled job that rewrote a manifest there would be editing someone else's checkout at 3am.
    Detection everywhere, mutation only in the layers this tool owns.

    Same rule this hook already enforces for versions, one level up: a commit is a private
    checkpoint, but an index becomes a promise to someone else the moment it is pushed. Versions
    were being kept honest here while the manifest carrying them drifted freely — `sync_registry`
    only corrects the version field of an entry that already exists, so a NEW file got no entry, a
    DELETED file kept one, and a rewritten `summary:` never reached the index at all.

    Opt-in by configuration, deliberately: a repo declares its manifests generated by having a
    `config/registry-map.yaml`. A repo without one is only PARSE-checked, never rewritten — because
    the manifests that have no map are the ones whose entries encode a human's grouping judgement
    (sections, buckets, exclusion reasons), and regenerating those destroys the thing they exist
    to hold. See the registry-conformance skill for that split.

    Never blocks and never raises: a registry that could not be rebuilt defers to the nightly
    --reconcile, exactly as an unresolvable push target does.
    """
    import pathlib
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    repo_p = pathlib.Path(repo)
    wrote = []

    # 1. PARSE, always — a manifest that does not load is a harder failure than a stale one, and
    #    every consumer of it gets an exception instead of an index, silently.
    reg_dir = repo_p / "registry"
    if reg_dir.is_dir():
        import yaml as _yaml
        for man in sorted(reg_dir.glob("*.yaml")):
            try:
                _yaml.safe_load(man.read_text(encoding="utf-8"))
            except Exception as exc:
                report.append(f"  ⚑ registry/{man.name} DOES NOT PARSE — {exc}")
                report.append(f"    every consumer gets an exception instead of an index")

    # 2. REGENERATE, only where a map says the manifest is derivable.
    cfg_path = repo_p / "config" / "registry-map.yaml"
    if not cfg_path.exists():
        return wrote
    try:
        import yaml as _yaml
        import build_registry as BR
        cfg = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        budget = int(cfg.get("summary_budget_words", 60))
        for name, spec in (cfg.get("registries") or {}).items():
            r = BR.build(repo_p, name, spec, budget)
            if r["raw"] == r["rendered"]:
                continue
            if r["comments_below"]:
                # PyYAML cannot round-trip comments; refusing is the correct outcome, and saying
                # so is what keeps it from looking like the gate simply did nothing.
                report.append(f"  registry/{name}: drift NOT applied — manifest carries comments "
                              f"below its header block and they would be discarded")
                continue
            rep = r["report"]
            detail = ", ".join(f"{k}:{len(v)}" for k, v in rep.items() if v) or "reformat"
            report.append(f"  registry/{spec['file'].split('/')[-1]}")
            if not apply:
                nlines = sum(1 for x in difflib.unified_diff(
                    r["raw"].splitlines(), r["rendered"].splitlines(), lineterm="", n=0)
                    if x[:1] in "+-" and x[:3] not in ("---", "+++"))
                report.append(f"    DRIFT: {nlines} line(s) differ from a rebuild ({detail})")
                continue
            r["path"].write_text(r["rendered"], encoding="utf-8")
            report.append(f"    regenerated from frontmatter at the push boundary ({detail})")
            wrote.append(str(r["path"].relative_to(repo_p)))
    except Exception as exc:
        report.append(f"  registry rebuild deferred to --reconcile ({exc.__class__.__name__})")

    # 3. The directory INDEXES, from the same map. A manifest and an index.md are two renderings
    #    of one fact, so publishing one true and the other stale just moves the drift. Wrapped
    #    separately from step 2 on purpose: an index failure must not cost the repo its manifest
    #    rebuild, and the two are independent artifacts.
    try:
        import build_index as BI
        for name, spec in (cfg.get("registries") or {}).items():
            r = BI.build_one(repo_p, name, spec, budget)
            if r["error"]:
                report.append(f"  index/{name}: no index target — {r['error']}")
                continue
            if r["path"] is None or r["raw"] == r["rendered"]:
                continue
            if r["refused"]:
                # Same refusal as the manifest's comments-below case, and for the same reason:
                # `## Contents` holds something a person wrote, and a 3am job is the worst
                # possible place to decide it was disposable. --force is a human's to type.
                report.append(f"  {r['path'].relative_to(repo_p)}: drift NOT applied — "
                              f"`## Contents` holds {len(r['refused'])} hand-authored line(s)")
                continue
            rel = str(r["path"].relative_to(repo_p))
            report.append(f"  {rel}")
            if not apply:
                nlines = sum(1 for x in difflib.unified_diff(
                    r["raw"].splitlines(), r["rendered"].splitlines(), lineterm="", n=0)
                    if x[:1] in "+-" and x[:3] not in ("---", "+++"))
                report.append(f"    DRIFT: {nlines} line(s) differ from a rebuild")
                continue
            r["path"].parent.mkdir(parents=True, exist_ok=True)
            r["path"].write_text(r["rendered"], encoding="utf-8")
            report.append("    `## Contents` regenerated from sibling summaries")
            wrote.append(rel)
    except Exception as exc:
        report.append(f"  index rebuild deferred to --reconcile ({exc.__class__.__name__})")
    return wrote


def resolve_pushed_repo(cmd, cwd_hint, note=lambda *a: None):
    """Which repo does this command actually push? Shared by every push-boundary hook.

    A hook sees command TEXT, never the expanded shell, so the target has to be
    inferred. Two forms have already bitten us, both by silently falling through to
    the session cwd — which is whatever directory the PREVIOUS command left behind:

      `git -C $VAR push`        -> literal "$VAR"          (2026-07-31, half-fixed)
      `cd <repo> && git push`   -> the cd is invisible     (2026-08-01)
      `(cd <repo> && git push)` -> matched by nothing      (2026-08-01, adversarial)
      `pushd <repo> && git push`-> matched by nothing      (2026-08-01, adversarial)

    The second made version_gate version the generated public repo while the source
    layer shipped unversioned. The 2026-07-31 entry was recorded as fixed and was not:
    only the `cd` branch returned None, while `-C` went on falling through to the
    session cwd for another day, under a docstring that said otherwise. An adversarial
    probe drove a `git -C $VAR push` of team-lib into a version bump of my-lib.

    ALL of these now return None. A target we cannot resolve is not the same fact as
    no target at all, and only one of those is safe to guess at; --reconcile is the
    floor that catches whatever this skips.

    `note` is an optional logging callback (event, detail).
    """
    repo = None

    m = re.search(r"git\s+-C\s+(\S+)", cmd)
    if m:
        cand = os.path.expanduser(m.group(1))
        if os.path.isdir(cand):
            repo = cand
        else:
            # Same rule as the cd branch below, and it was missing here — which is how a
            # `git -C $VAR push` of team-lib got evaluated against my-lib and reported
            # success. The docstring claimed this form was fixed; only half of it was.
            note("unexpanded-C", m.group(1)[:40])
            return None

    if repo is None:
        # `(cd repo && git push)` and `pushd repo && git push` were matched by nothing, so
        # they fell through to the session cwd too. Both confirmed live.
        cd = re.search(r"(?:^|&&|;|\||\(|\{)\s*(?:cd|pushd)\s+(\S+)", cmd)
        if cd:
            cand = os.path.expanduser(cd.group(1).strip("'\""))
            if os.path.isdir(cand):
                repo = cand
            else:
                # The command NAMES a target we cannot resolve (an unexpanded $VAR, a
                # worktree path built in the shell). Falling through to the session cwd
                # would evaluate a DIFFERENT repo and report success about it — measured
                # 2026-08-01, a worktree push of team-lib was evaluated against my-lib and
                # logged "nothing: no versioned file changed without a bump".
                #
                # "I cannot tell which repo" is not the same fact as "no repo was named",
                # and only one of them is safe to guess at. Skip instead; --reconcile is
                # the floor that catches whatever this misses.
                note("unexpanded-cd", cd.group(1)[:40])
                return None

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


def _scope_asserts():
    """The header-scoping rules, on the two shapes that broke on 2026-10-21."""
    core = ("---\ntemplate: operating-core\nversion: 2.20.0\ngenerated_by: x.py\n---\n"
            "body\n```yaml\nversion: 1.0.0\nlast_updated: [YYYY-MM-DD]\n```\n")
    assert is_generated(core[:header_end("a.md", core)])
    assert MD_UPDATED.search(core, 0, header_end("a.md", core)) is None  # the body example is out of reach
    doc = ("---\nversion: 1.2.0\nlast_updated: 2026-10-01\n---\n"
           "example:\nlast_updated: [YYYY-MM-DD]\n")
    h = header_end("a.md", doc)
    assert not is_generated(doc[:h])
    assert MD_UPDATED.search(doc, 0, h).group(2) == "2026-10-01"
    assert MD_VERSION.search("no frontmatter\nversion: 1.0.0\n", 0, header_end("b.md", "no frontmatter\n")) is None
    sh = "#!/usr/bin/env python3\n# ---\n# version: 1.0.0\n# generated_by: y\n# ---\n"
    assert is_generated(sh[:header_end("c.py", sh)])


def self_check():
    """Report whether the gate is actually reaching pushes. Exit 1 if it looks dead."""
    _scope_asserts()
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


def reconcile(repo, apply=True):
    """Bump any versioned file whose body changed since its version last changed.

    The floor under the push hook. The hook only fires on pushes made through this
    harness; a push from a plain terminal, another machine, or another agent skips
    versioning entirely — and unlike publication it cannot be fixed from the
    outgoing range afterwards, because once pushed `@{u}..HEAD` is empty and the
    evidence of what should have bumped is gone.

    So this asks git instead, which is still authoritative: for each versioned
    file, find the last commit that changed its `version:` line, then check whether
    any later commit touched the file. Deliberately NO cached hash state — a
    checker that reads its own previous output is the anti-pattern that produced
    two separate bugs in this workspace, and git cannot silently rot.

    Returns a list of (path, old, new). Commits, never pushes.
    """
    out = []
    tracked = git(repo, "ls-files").splitlines()
    for rel in tracked:
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
        hend = header_end(rel, text)
        if is_generated(text[:hend]):
            continue  # a generated artifact; its source carries the version
        vm = ver_re.search(text, 0, hend)
        if not vm:
            continue  # unversioned file — not in scope

        # Only the MOST RECENT commit touching the file matters, which keeps this
        # to two git calls per file instead of walking its whole history — the
        # difference between a nightly pass that finishes and one that times out.
        #
        # It is exact for the commit patterns here, not merely a heuristic: the
        # gate writes version bumps as their own `chore(version)` commit, so the
        # newest commit touching a file either changed its version line (the
        # version is current with the body) or did not (the body moved after the
        # version last did). A hand-edit that changes both in one commit still
        # shows `+version:` and is correctly read as current.
        last = git(repo, "log", "-1", "--format=%H", "--", rel)
        if not last:
            continue  # untracked or never committed
        if re.search(r"^\+\s*#?\s*version:", git(repo, "show", last, "--", rel), re.M):
            continue  # version moved with the body

        old = (int(vm.group(2)), int(vm.group(3)), int(vm.group(4)))
        new_s = "%d.%d.%d" % bump(old, "patch")
        text = text[: vm.start()] + f"{vm.group(1)}{new_s}{vm.group(5)}" + text[vm.end():]
        today = git(repo, "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d") or ""
        um = upd_re.search(text, 0, header_end(rel, text))
        if um and today:
            text = text[: um.start()] + f"{um.group(1)}{today}{um.group(3)}" + text[um.end():]
        if apply:
            open(full, "w").write(text)
            sync_registry(repo, rel, new_s, [])
        out.append((rel, "%d.%d.%d" % old, new_s))

    if out and apply:
        git(repo, "add", "--", *[r for r, _, _ in out], "registry")
        subprocess.run(
            ["git", "-C", repo, "commit", "-q", "-m",
             # Deliberately NO [no-version] marker. That opt-out is scanned across
             # the WHOLE outgoing range, so a reconcile commit carrying it silently
             # disabled versioning for every unrelated change pushed alongside it —
             # observed immediately, on the very push that shipped this function.
             # The per-file "did the version line change in this range?" check
             # already protects these files precisely, which is the right scope.
             "chore(version): reconcile %d file(s) versioned outside the push gate\n\n"
             "Auto-applied by version_gate.py --reconcile from the nightly tick. These\n"
             "shipped with a body newer than their version because the push that\n"
             "carried them did not go through the harness hook. Not pushed."
             % len(out)],
            capture_output=True, text=True, timeout=25,
        )
    return out


def main():
    if "--self-check" in sys.argv:
        sys.exit(self_check())

    # Invoked directly by the nightly tick, not as a hook: no stdin to read.
    if "--reconcile" in sys.argv:
        i = sys.argv.index("--reconcile")
        repo = (sys.argv[i + 1] if len(sys.argv) > i + 1
                and not sys.argv[i + 1].startswith("-") else os.getcwd())
        apply = "--dry-run" not in sys.argv
        rows = reconcile(repo, apply=apply)
        # The registry backstop for everything the push path skipped: an unresolvable push
        # target, a commit-and-push in one command, a manifest edited straight on main. A gate
        # that only fires at the boundary measures nothing about what got around the boundary.
        reg_report = []
        reg_wrote = registry_gate(repo, reg_report, apply=apply)
        # ⚑ COMMIT what it wrote. reconcile() above commits only when a VERSION moved, staging
        # the blanket path "registry" — so a run that regenerated a manifest and bumped nothing
        # left the rebuild sitting dirty in the working tree, while dream_cycle logged
        # "regenerated and committed, not pushed". The claim was false for manifests already;
        # adding index.md generation would have spread it to five more files per layer, every
        # night. `apply` is False for project repos, so this can only ever touch the layers we own.
        if apply and reg_wrote:
            git(repo, "add", "--", *reg_wrote)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m",
                 "chore(registry): reconcile manifests and indexes from the nightly tick\n\n"
                 "Auto-applied by version_gate.py --reconcile. These drifted from the frontmatter\n"
                 "they index because the push that carried them did not go through the harness\n"
                 "hook. Regenerated and committed, not pushed."],
                capture_output=True, text=True, timeout=25)
            reg_report.append(f"  committed {len(reg_wrote)} regenerated file(s)")
        print(json.dumps({"status": "ok",
                          "bumped": [{"path": p, "from": a, "to": b} for p, a, b in rows],
                          "registry_rewritten": reg_wrote,
                          "registry_notes": reg_report}))
        sys.exit(0)

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
    if not repo:
        # Named a target we could not resolve. Deferring is correct and cheap: --reconcile
        # runs nightly on both layers and will bump whatever this skipped. Never block.
        beat("skip", "unresolvable push target — deferring to --reconcile")
        sys.exit(0)
    if not repo.startswith(WORKSPACE):
        beat("skip", f"outside workspace: {repo}")
        sys.exit(0)  # not ours to police

    # A GENERATED artifact must never be versioned here. The public reference repo
    # is produced by publish_public_reference.py from team-lib, so its versions are
    # team-lib's versions; bumping them in place makes the derived copy claim a
    # version its source never had, and the next publish silently reverts it.
    # Belt and braces with the cd/-C resolution above: that stops us ARRIVING here
    # by accident, this stops us acting even if we do.
    #
    # Compare the COMMON git dir, not the working tree. A worktree of the public repo has
    # its own toplevel, so the identity test missed it and versioned the generated artifact
    # in place — the "even if we do" the comment above promised to cover. Confirmed by
    # adversarial probe, 2026-08-01.
    def _repo_identity(path):
        common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        return os.path.realpath(common) if common else os.path.realpath(path)

    public_root = os.path.join(WORKSPACE, PUBLIC_LAYER)
    if (os.path.realpath(repo) == os.path.realpath(public_root)
            or (os.path.isdir(public_root) and _repo_identity(repo) == _repo_identity(public_root))):
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

    # Behind upstream? Then git is about to reject this push (non-fast-forward), and anything
    # written here is left behind as dirty files that block the very pull the operator needs
    # next. Write nothing; the push that lands after the pull is where versions get checked.
    # Found 2026-10-07 in bidscout (206 behind): bumps to teammates' files blocked the pull.
    behind = git(repo, "rev-list", "--count", "HEAD..@{u}")
    if behind and behind != "0":
        beat("behind", f"{behind} commit(s) behind upstream; push will be rejected; no writes")
        print(f"[version-gate] branch is {behind} commit(s) behind its upstream; git will reject "
              "this push. Pull first; versions are checked on the push that lands. Nothing written.",
              file=sys.stderr)
        sys.exit(0)

    msgs = git(repo, "log", "--format=%B", "@{u}..HEAD").lower()

    # A directive must be a TRAILER — its own line — not any occurrence of the
    # token anywhere in the prose. As a bare substring, merely WRITING about the
    # marker triggers it: the commit that fixed a [no-version] bug quoted the token
    # in its own message and silently opted its own push out of versioning, twice
    # in a row. A control token that any sentence can fire is not a control token.
    def directive(tag):
        return re.search(rf"^\s*\[{tag}\]\s*$", msgs, re.M) is not None

    if directive("no-version"):
        # ⚑ [no-version] is a statement about VERSIONS, not about the index, and treating it as
        # both is a bug this hook shipped with for exactly one push. The mirror commit carries
        # [no-version] by design, so the 2026-08-08 my-lib push opted out here while 11 mirrored
        # version bumps went to the remote with registry/skills.yaml still naming the old numbers.
        # A guard is a new boundary and a new boundary is a new unexercised path: the opt-out
        # predates the registry pass and silently acquired power over it.
        beat("optout", "[no-version] trailer in range — registry still made true")
        reg_report = []
        reg_wrote = registry_gate(repo, reg_report)
        if reg_wrote:
            git(repo, "add", "--", *reg_wrote)
            subprocess.run(
                ["git", "-C", repo, "commit", "-q", "-m",
                 "chore(registry): regenerate manifests and indexes at push boundary\n\n"
                 "Auto-applied by version_gate.py. [no-version] opted this push out of VERSION\n"
                 "bumps; the index is a separate promise and is still made true.\n[no-version]"],
                capture_output=True, text=True, timeout=25)
            print("[version-gate] registry regenerated ([no-version] applies to versions only)",
                  file=sys.stderr)
            print("\n".join(reg_report), file=sys.stderr)
        sys.exit(0)
    level = "major" if directive("major") else "minor" if directive("minor") else "patch"

    # THREE dots. For `git diff`, `A..B` compares the two TREES, so every file upstream changed
    # looks like a local change once the branch has diverged; `A...B` diffs from the merge-base,
    # which is the outgoing change only. (`rev-list`/`log` above use `..` correctly: there it
    # means commits.) Two dots here bumped teammates' files on 2026-10-07.
    changed = [f for f in git(repo, "diff", "--name-only", "@{u}...HEAD").splitlines() if f]
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
        hend = header_end(rel, text)
        if is_generated(text[:hend]):
            continue  # a generated artifact; its source carries the version
        vm = ver_re.search(text, 0, hend)
        if not vm:
            continue  # unversioned file — not in scope

        # Did the version line itself change in this range? If so, respect it.
        diff = git(repo, "diff", "-U0", "@{u}...HEAD", "--", rel)
        if re.search(r"^\+\s*#?\s*version:", diff, re.M):
            continue

        orig = text  # pre-bump content, for the mirror-equality test below
        old = (int(vm.group(2)), int(vm.group(3)), int(vm.group(4)))
        new = bump(old, level)
        new_s = "%d.%d.%d" % new
        text = text[: vm.start()] + f"{vm.group(1)}{new_s}{vm.group(5)}" + text[vm.end():]
        um = upd_re.search(text, 0, header_end(rel, text))
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

    # The index must be true at the same boundary the versions are. Run this AFTER the bumps so
    # the regenerated manifest carries the versions this run just stamped, not the previous ones.
    reg_wrote = registry_gate(repo, report)

    if not bumped and not reg_wrote:
        beat("nothing", "no versioned file changed without a bump; registry already true")
        if report:                       # parse failures / refusals still deserve to be seen
            print("[version-gate] registry notes:", file=sys.stderr)
            print("\n".join(report), file=sys.stderr)
        sys.exit(0)

    # Commit the bump BEFORE the push runs, so the push carries it. Without this
    # the version lands in the working tree and the pushed commits stay stale —
    # the exact drift this hook exists to stop.
    # Stage only paths that EXIST. A missing pathspec (most project repos have no registry/)
    # makes `git add` fail outright, nothing is staged, the commit fails too, and both errors
    # were swallowed: the push shipped the old version and left the bump dirty for some later,
    # unrelated commit to sweep up. Measured 2026-10-07: 23 of 26 repos have no registry/.
    def _existing(r, paths):
        return [x for x in paths if os.path.exists(os.path.join(r, x))]

    add = subprocess.run(["git", "-C", repo, "add", "--",
                          *_existing(repo, [*(bumped or []), "registry", *reg_wrote])],
                         capture_output=True, text=True, timeout=25)
    subject = ("chore(version): bump %d versioned file(s) at push boundary" % len(bumped)
               if bumped else "chore(registry): regenerate manifests at push boundary")
    done = subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m",
         "%s\n\n"
         "Auto-applied by version_gate.py. A commit is a checkpoint; a version — and the\n"
         "index that publishes it — is an identity other people rely on, so both are made\n"
         "true at the publish boundary rather than at every commit. Use [minor]/[major] to\n"
         "escalate or [no-version] to skip." % subject],
        capture_output=True, text=True, timeout=25,
    )
    if add.returncode != 0 or done.returncode != 0:
        why = (add.stderr or done.stderr or done.stdout or "").strip().splitlines()[:2]
        beat("commit-failed", " | ".join(why))
        print("[version-gate] ⚠ bumped but could NOT commit the bump, so this push carries the "
              "OLD versions and the bump is left uncommitted: " + " | ".join(why), file=sys.stderr)

    # Commit the mirrored halves in THEIR repos too. Not pushed from here — that repo
    # gets pushed on its own schedule — but committing keeps the twin from sitting
    # dirty and getting swept into an unrelated commit by whoever pushes it next.
    for other_repo, files in mirrored.items():
        git(other_repo, "add", "--", *_existing(other_repo, [*files, "registry"]))
        subprocess.run(
            ["git", "-C", other_repo, "commit", "-q", "-m",
             "chore(version): mirror %d version bump(s) from the paired layer\n\n"
             "Auto-applied by version_gate.py. These files are byte-identical twins of\n"
             "the layer just pushed; bumping only one side would desync the mirror.\n"
             "[no-version]" % len(files)],
            capture_output=True, text=True, timeout=25,
        )

    beat("bump", ",".join(bumped) + ("|registry" if reg_wrote else ""))
    print(f"[version-gate] {len(bumped)} file(s) bumped"
          f"{', registry regenerated' if reg_wrote else ''}, 0 blocked", file=sys.stderr)
    print("\n".join(report), file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # never cost anyone a push
