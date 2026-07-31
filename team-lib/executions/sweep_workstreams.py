#!/usr/bin/env python3
"""sweep_workstreams.py — detect closed / aged-out T2 workstreams for the debrief.

Two pathways, run over EVERY project_*.md at each debrief (any thread, any time):

  Pathway 1 — objective close detection.
    Each open T2 may carry a `close_signal:` list of machine-checkable triggers.
    We evaluate them against LIVE sources, so a close that happened in a totally
    different thread weeks ago is still detected here:
      - clickup:<taskId>            -> GET /api/v2/task; closed if status.type in {closed,done}
      - pr:<owner>/<repo>#<num>     -> `gh pr view`; closed if state MERGED or CLOSED
      - file:<abs-path>             -> path exists
      - grep:<abs-path>::<regex>    -> regex found in file
    OR-semantics: any satisfied signal closes the workstream.

  Pathway 2 — age-out floor.
    Any still-open item (pathway 1 didn't close it) whose `last_touched` is older
    than --age-days becomes a formal backlog item. Guarantees current-state stays
    bounded regardless of whether a close was ever detectable.

Read-only by default (emits JSON). With --apply it mutates the T2 files:
flips `status` -> archived|backlog, stamps last_touched, appends a note, and for
age-outs writes a backlog stub. It NEVER edits current-state.md — the debrief's
current-state regen is the single writer and drops any item now archived/backlog.
"""
import argparse, json, os, re, subprocess, sys, datetime, pathlib
import sys
from pathlib import Path

# --- portable path resolution (team-lib) -------------------------------------
# Scripts here are invoked by absolute path from hooks and cron, so the sibling
# module is not importable from cwd. Add our own directory to sys.path first.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import (  # noqa: E402
    memory_dir, meditations_dir, lenses_dir, journal_dir, shortterm_dir,
    state_dir, exec_dir, backlog_dir, agent_home, workspace, TOPIC_PREFIXES,
)
# -----------------------------------------------------------------------------

MEM = memory_dir()
# Optional: absent on a fresh install, in which case age-out is skipped.
BACKLOG = backlog_dir() or (agent_home() / "backlog")
SECRETS_ENV = workspace() / "personal/secrets/.env"
OPEN_STATUSES = {"in-flight", "handed-off", "follow-on"}

# ---------- frontmatter ----------
def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    fm_raw = m.group(1)
    fm = {}
    key = None
    def _scalar(v):
        """Quoted values are verbatim; only unquoted ones get comment-stripping.

        `#` inside quotes is DATA (PR/issue refs in close_signal, resolves_when),
        not a YAML comment. Stripping before unquoting silently truncated such
        values. See backlog/bug-regen-current-state-hash-truncation.md.
        """
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            return v[1:-1]
        return re.sub(r"\s+#.*$", "", v).strip()
    for line in fm_raw.splitlines():
        if re.match(r"^\s*-\s", line) and key:            # yaml list item
            fm.setdefault(key, [])
            if isinstance(fm[key], list):
                fm[key].append(_scalar(line.strip()[1:].strip()))
            continue
        mm = re.match(r"^\s*(\w[\w_]*):\s*(.*)$", line)   # any indent -> nested metadata: blocks read too
        if mm:
            key, val = mm.group(1), _scalar(mm.group(2).strip())
            if val == "":
                fm[key] = []          # maybe a block list follows
            else:
                fm[key] = val.strip('"\'')
    return fm, text

# ---------- signal evaluators ----------
def load_clickup_token():
    tok = os.environ.get("CLICKUP_API_TOKEN")
    if tok:
        return tok
    if SECRETS_ENV.exists():
        for line in SECRETS_ENV.read_text().splitlines():
            m = re.match(r"\s*CLICKUP_API_TOKEN\s*=\s*(.+)\s*$", line)
            if m:
                return m.group(1).strip().strip('"\'')
    return None

def check_clickup(task_id, cache):
    if task_id in cache:
        return cache[task_id]
    tok = load_clickup_token()
    if not tok:
        return ("error", "no CLICKUP_API_TOKEN")
    try:
        import urllib.request
        req = urllib.request.Request(
            f"https://api.clickup.com/api/v2/task/{task_id}",
            headers={"Authorization": tok})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        stype = (data.get("status") or {}).get("type", "").lower()
        sname = (data.get("status") or {}).get("status", "")
        res = ("closed", f"status={sname}") if stype in {"closed", "done"} else ("open", f"status={sname}")
    except Exception as e:  # noqa
        res = ("error", f"{type(e).__name__}: {e}")
    cache[task_id] = res
    return res

def check_pr(spec):
    m = re.match(r"([^/]+/[^#]+)#(\d+)", spec)
    if not m:
        return ("error", "bad pr spec")
    repo, num = m.group(1), m.group(2)
    try:
        out = subprocess.run(["gh", "pr", "view", num, "--repo", repo, "--json", "state"],
                             capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return ("error", out.stderr.strip()[:80])
        state = json.loads(out.stdout).get("state", "").upper()
        if state == "MERGED":
            return ("closed", "state=MERGED")
        if state == "CLOSED":
            # CLOSED-unmerged is ABANDONED, not done — the opposite conclusion. Treating
            # the two alike silently archived a workstream whose own resolves_when said
            # "PR #382 MERGES": that PR was closed unmerged on 2026-07-21 and the §1b
            # swimlane work it was tracking is still outstanding. Surface it for a human
            # instead; an abandoned PR usually means the workstream needs a NEW signal,
            # which is precisely the judgment a sweep must not make on its own.
            return ("attention", "state=CLOSED unmerged — abandoned, needs a new signal")
        return ("open", f"state={state}")
    except Exception as e:  # noqa
        return ("error", f"{type(e).__name__}: {e}")

def check_file(path):
    return ("closed", "exists") if pathlib.Path(os.path.expanduser(path)).exists() else ("open", "absent")

def check_grep(spec):
    if "::" not in spec:
        return ("error", "grep needs path::regex")
    path, pat = spec.split("::", 1)
    p = pathlib.Path(os.path.expanduser(path))
    if not p.exists():
        return ("open", "file absent")
    try:
        return ("closed", "match") if re.search(pat, p.read_text()) else ("open", "no match")
    except Exception as e:  # noqa
        return ("error", f"{type(e).__name__}: {e}")

def eval_signal(sig, cu_cache):
    # Strip surrounding quotes before splitting. `close_signal: - "clickup:868…"` is
    # perfectly valid YAML, but the frontmatter is read line-wise rather than parsed, so
    # the quote stayed attached and the kind came through as '"clickup' — an unknown
    # signal, reported as an error and then ignored. The failure is silent in the worst
    # way: the workstream simply never auto-closes, forever, and nothing says why.
    # Found on project_trever-vesper-materials-handover.md, 2026-07-30.
    sig = sig.strip().strip('"').strip("'").strip()
    kind, _, arg = sig.partition(":")
    kind = kind.strip().lower()
    if kind == "clickup":
        return check_clickup(arg.strip(), cu_cache)
    if kind == "pr":
        return check_pr(arg.strip())
    if kind == "pr-any":
        # "resumed or closed" — some workstreams track whether a PR is still PENDING, not
        # whether it landed. For those, abandoning the PR genuinely resolves the item, so
        # any terminal state closes. Distinct from `pr:` on purpose: conflating the two is
        # the bug fixed above, and the caller must now say which meaning they intend.
        verdict, detail = check_pr(arg.strip())
        if verdict == "attention":
            return ("closed", "state=CLOSED unmerged (pr-any: terminal state accepted)")
        return (verdict, detail)
    if kind == "file":
        return check_file(arg.strip())
    if kind == "grep":
        return check_grep(arg.strip())
    if kind == "judgment":
        # Deliberately unmechanisable: the trigger is a human deciding, an off-system
        # event, or an observation ("no clobber across >=2 real debriefs") that no query
        # can answer. It NEVER closes — its whole job is to distinguish "triaged, and
        # genuinely not machine-checkable" from "nobody has looked at this yet". Without
        # it both look identical in no_close_signal, so the backfill can never be
        # finished: 55 untriaged and 55 correctly-triaged report the same number.
        return ("judgment", arg.strip() or "unspecified")
    return ("error", f"unknown signal kind '{kind}'")

# ---------- mutation ----------
def load_current_state_links():
    cs = MEM / "current-state.md"
    if not cs.exists():
        return set()
    return set(re.findall(r"\[\[(project_[a-z0-9_\-]+)\]\]", cs.read_text(), re.I))

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("project_", "")).strip("-")

def set_status(text, status, today):
    m = re.match(r"^(---\n.*?\n---\n)(.*)$", text, re.DOTALL)
    fm, body = m.group(1), m.group(2)
    if re.search(r"^(\s*)status:.*$", fm, re.M):
        fm = re.sub(r"^(\s*)status:.*$", rf"\1status: {status}", fm, count=1, flags=re.M)
    else:
        fm = fm.replace("---\n", f"---\nstatus: {status}\n", 1)
    if re.search(r"^(\s*)last_touched:.*$", fm, re.M):
        fm = re.sub(r"^(\s*)last_touched:.*$", rf"\1last_touched: {today}", fm, count=1, flags=re.M)
    else:
        fm = re.sub(r"^(\s*status: .*)$", rf"\1\nlast_touched: {today}", fm, count=1, flags=re.M)
    return fm + body

def clear_cs(text):
    # drop cs_section/cs_headline so the regen no longer renders a closed item
    return re.sub(r"^\s*cs_(section|headline):.*\n", "", text, flags=re.M)

def apply_archive(path, today, reason):
    t = clear_cs(set_status(path.read_text(), "archived", today))
    note = (f"\n## Archived {today}\n\nAuto-closed by sweep_workstreams: {reason}. "
            "Objective close-signal fired; `resolves_when` retained.\n")
    if f"## Archived {today}" not in t:
        t = t.rstrip() + "\n" + note
    path.write_text(t)

def apply_backlog(path, fm, today):
    name = path.stem
    slug = slugify(name)
    stub = BACKLOG / f"{today}-{slug}.md"
    if not stub.exists():
        stub.write_text(
            f"# {name} — aged out of current-state {today}\n\n"
            f"**Auto-created** by sweep_workstreams (open >age threshold, no close-signal fired).\n"
            f"**Source T2:** `memory/{name}.md`\n"
            f"**resolves_when:** {fm.get('resolves_when','(none)')}\n"
            f"**resume_via:** {fm.get('resume_via','(none)')}\n\n"
            "Disposition (close / re-activate / drop) happens at backlog review.\n")
    t = clear_cs(set_status(path.read_text(), "backlog", today))
    if "backlog:" not in t.split("---")[1]:
        t = re.sub(r"^(\s*status: .*)$", rf"\1\nbacklog: my-lib/backlog/{today}-{slug}.md",
                   t, count=1, flags=re.M)
    note = (f"\n## Aged out to backlog {today}\n\nOpen past the age threshold with no "
            f"close-signal; formalized at `my-lib/backlog/{today}-{slug}.md`.\n")
    if f"## Aged out to backlog {today}" not in t:
        t = t.rstrip() + "\n" + note
    path.write_text(t)
    try:
        return str(stub.relative_to(workspace()))
    except ValueError:
        return str(stub)

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--age-days", type=int, default=45)
    ap.add_argument("--apply", action="store_true", help="perform mutations (default: report only)")
    args = ap.parse_args()
    today = datetime.date.fromisoformat(args.today)

    cu_cache = {}
    cs_links = load_current_state_links()
    report = {"reference_date": args.today, "age_days": args.age_days, "mode": "apply" if args.apply else "report",
              "current_state_items": len(cs_links),
              "closed_by_signal": [], "aged_out": [], "stale_corpus_ignored": [], "pinned_skipped": [],
              "judgment_only": [], "needs_attention": [],
              "errors": [], "unresolved_open": []}
    scanned = 0
    with_signal = 0
    judgment_only = 0
    for path in sorted(MEM.glob("project_*.md")):
        text = path.read_text()
        fm, _ = parse_fm(text)
        status = (fm.get("status") or "").strip()
        if status not in OPEN_STATUSES:
            continue
        scanned += 1
        name = path.stem
        signals = fm.get("close_signal") or []
        if isinstance(signals, str):
            signals = [signals]
        if not signals:
            # A workstream with no close_signal can NEVER be auto-closed — pathway 1 has
            # nothing to evaluate, and the soft resolves_when grep only fires on a lucky
            # phrase match. Report it, because otherwise the sweep's silence about this
            # file is indistinguishable from "checked it, still open".
            #
            # Observed 2026-07-30: project_agent-memory-system met every clause of its own
            # resolves_when and neither pathway fired; a human had to read the prose to
            # notice the work was finished. Anything the sweep cannot see, it should say
            # it cannot see.
            report.setdefault("no_close_signal", []).append(name)
        closed = None
        judgment_reasons = []
        machine_signals = 0
        for sig in signals:
            verdict, detail = eval_signal(sig, cu_cache)
            if verdict == "judgment":
                judgment_reasons.append(detail); continue
            machine_signals += 1
            if verdict == "attention":
                report["needs_attention"].append({"name": name, "signal": sig, "detail": detail})
                continue
            if verdict == "closed":
                closed = (sig, detail); break
            if verdict == "error":
                report["errors"].append({"name": name, "signal": sig, "error": detail})
        if signals:
            # An item carrying BOTH a real signal and a judgment note still counts as
            # machine-checkable — the mechanism can fire. Only judgment-ONLY items are
            # parked, and they are parked visibly, never silently.
            if machine_signals:
                with_signal += 1
            else:
                judgment_only += 1
                report["judgment_only"].append({"name": name, "reason": "; ".join(judgment_reasons)})
        if closed:
            report["closed_by_signal"].append({"name": name, "signal": closed[0], "detail": closed[1]})
            if args.apply:
                apply_archive(path, args.today, f"{closed[0]} ({closed[1]})")
            continue
        # age-out (pathway 2) — scoped to current-state members, honors pin:
        lt = fm.get("last_touched", "")
        age = None
        if re.match(r"\d{4}-\d{2}-\d{2}", str(lt)):
            age = (today - datetime.date.fromisoformat(lt[:10])).days
        pinned = str(fm.get("pin", "")).strip().lower() in {"true", "yes", "1"}
        in_cs = name in cs_links
        if age is not None and age >= args.age_days:
            if pinned:
                report["pinned_skipped"].append({"name": name, "age_days": age})
            elif not in_cs:
                # old parked corpus note, not cluttering current-state -> leave alone
                report["stale_corpus_ignored"].append({"name": name, "age_days": age})
            else:
                entry = {"name": name, "last_touched": lt, "age_days": age, "resume_via": fm.get("resume_via", "")}
                if args.apply:
                    entry["backlog"] = apply_backlog(path, fm, args.today)
                report["aged_out"].append(entry)
        else:
            report["unresolved_open"].append({"name": name, "status": status, "last_touched": lt,
                                              "age_days": age, "in_current_state": in_cs, "signals": len(signals)})
    report["scanned_open"] = scanned
    # Emit the denominator and the ratio EXPLICITLY rather than making every caller
    # derive them. On 2026-07-30 three different figures for this one measurement
    # appeared within hours — "55 of 97 / 43%", "55 of 67 / 18%", "55 of 66 / 83%" —
    # in two memory files and a subagent report, because each reader summed a
    # different combination of the arrays below. The numerator was never in dispute.
    # A number that must be computed by the reader will be computed differently by
    # each reader; publish it once, from the code that owns it.
    #
    # 2026-07-31 — that first fix published a number, but the WRONG number: 97, from
    # summing `no_close_signal + unresolved_open + closed_by_signal`. Those arrays are
    # not a partition. `no_close_signal` is a property of an item; `unresolved_open` /
    # `aged_out` / `stale_corpus_ignored` / `pinned_skipped` are its disposition. An item
    # lacking a signal AND not yet aged out lands in BOTH — 31 items did, so the
    # denominator over-counted by 31 and coverage read 43% when it was 17%.
    #
    # The lesson is one layer deeper than "publish the number": DON'T DERIVE IT AT ALL.
    # `scanned` and `with_signal` are counted once each, in the loop, at the moment the
    # item is classified. The assert holds by construction — each open item increments
    # exactly one of the two branches — so it can only fire if a future refactor breaks
    # the partition, which is precisely when this went wrong the first time.
    assert with_signal + judgment_only + len(report["no_close_signal"]) == scanned, (
        f"partition broken: {with_signal} + {judgment_only} + "
        f"{len(report['no_close_signal'])} != {scanned}")
    report["summary"] = {
        "open_total": scanned,
        # Can auto-close: a mechanism will detect it with no human in the loop.
        "with_close_signal": with_signal,
        # Triaged and deliberately parked — a human read it and there is nothing to check.
        "judgment_only": judgment_only,
        # Nobody has looked yet. THIS is the backlog; the number that should reach zero.
        "without_close_signal": len(report["no_close_signal"]),
        "coverage_pct": round(100 * with_signal / scanned) if scanned else 0,
        "triaged_pct": round(100 * (with_signal + judgment_only) / scanned) if scanned else 0,
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
