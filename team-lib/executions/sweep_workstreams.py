#!/usr/bin/env python3
"""sweep_workstreams.py — detect closed / aged-out T2 workstreams for the debrief.

Two pathways, run over EVERY project_*.md at each debrief (any thread, any time):

  Pathway 1 — objective close detection.
    Each open T2 may carry a `close_signal:` list of machine-checkable triggers.
    We evaluate them against LIVE sources, so a close that happened in a totally
    different thread weeks ago is still detected here:
      - clickup:<taskId>            -> closed if status.type == closed, or the status NAME
                                       is in DONE_STATUS_NAMES. Other done-type statuses
                                       are surfaced, not closed (done != shipped).
      - clickup-done:<taskId>       -> as above, but ANY done-type closes. Opt-in.
      - pr:<owner>/<repo>#<num>     -> closed only if MERGED. CLOSED-unmerged is ABANDONED
                                       and is surfaced for a human, not auto-closed.
      - pr-any:<owner>/<repo>#<num> -> any terminal state closes ("resumed or closed").
      - file:<abs-path>             -> path exists
      - grep:<abs-path>::<regex>    -> regex found in file
      - judgment:<reason>           -> NEVER closes; records that a human triaged this and
                                       found nothing machine-checkable.
    OR-semantics: any satisfied signal closes the workstream.

  Pathway 2 — dormancy.
    Any still-open item (pathway 1 didn't close it) whose `last_touched` is older
    than --age-days goes `dormant`: not finished, not queued, moved on from. This
    is a CLOSE, not a queue — no stub, no disposition step, no review. The T2 file
    and its MEMORY.md row stay exactly where they are, so ordinary recall still
    finds it; dormancy removes an item from ATTENTION, never from MEMORY.

    Applies corpus-wide, not just to current-state members. The old carve-out had
    it backwards: an item 83 days old AND absent from current-state is the most
    dormant object in the corpus, and it was the one guaranteed never to be acted
    on (26 such items on 2026-07-30).

  Pathway 3 — revival.
    A dormant item whose `last_touched` moves past its `dormant_since` returns to
    in-flight automatically. Working on it IS the revival signal — there is no
    command to remember, which is the point. Closing on a 20-day timer is only
    safe because coming back is free.

    The clock reads `last_touched` ONLY. `last_accessed`/`access_count` move
    whenever anything READS a memory file — including the index reranker — and
    watching those would let a dormant item resurrect itself the moment something
    glanced at it. The two fields look interchangeable and are not.

Any status outside OPEN_STATUSES | CLOSED_STATUSES is reported as `unknown_status`
rather than skipped in silence — a file the sweep declines to look at is
indistinguishable from one that does not exist. Fix with
normalize_workstream_status.py.

Read-only by default (emits JSON). With --apply it mutates the T2 files: flips
`status` -> archived (signal fired) or dormant (past the age threshold), and appends
a note. It NEVER edits current-state.md — the debrief's current-state regen is the
single writer and drops anything no longer open.
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
# Terminal, and legitimately skipped. Anything outside OPEN | CLOSED is a defect, not a
# state — see the unknown_status report key.
CLOSED_STATUSES = {"archived", "dormant", "backlog"}

# ClickUp done-type status NAMES that close a workstream (the operator, 2026-07-30). The work
# may not be shipped — "staged" explicitly is not — but for the purpose of clearing
# current-state, the team has moved on and it should stop occupying attention. Named
# explicitly rather than accepting all done-type, so a new done-type status someone
# invents later does not silently start closing workstreams.
DONE_STATUS_NAMES = {"staged", "qa-in-prod"}

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
        # done-type != shipped. In this ClickUp space "staged" is typed `done` but means
        # staged FOR release (the operator, 2026-07-30) — and ClickUp leaves date_closed null for
        # it, agreeing the task is not closed. Auto-archiving on done-type would have
        # retired BUG-011 while its ~3,731-row backfill was still unrun.
        #
        # Same shape as the merged-vs-closed PR bug: two states that read alike and mean
        # opposite things. Only `closed`-type auto-closes; `done`-type is surfaced for a
        # human. A workspace where done-type really does mean shipped can say so with an
        # explicit clickup-done: signal rather than by loosening this for everyone.
        if stype == "closed" or sname.strip().lower() in DONE_STATUS_NAMES:
            res = ("closed", f"status={sname}")
        elif stype == "done":
            res = ("attention", f"status={sname} (done-type, not closed — shipped?)")
        else:
            res = ("open", f"status={sname}")
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
    if kind == "clickup-done":
        # Opt-in: accept done-type as closed, for a list where done really does mean
        # shipped. Explicit per-signal, so no other workstream inherits the assumption.
        verdict, detail = check_clickup(arg.strip(), cu_cache)
        return ("closed", detail) if verdict == "attention" else (verdict, detail)
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

def apply_dormant(path, today, age):
    """Go dormant WITHOUT stamping last_touched.

    set_status() moves last_touched to today, which is right for an archive but fatal
    here: revival compares last_touched against dormant_since, so stamping both to the
    same date would mean no later edit could ever look newer, and touch-to-revive would
    silently never fire. Preserving the real last_touched also keeps the record of how
    long the item actually sat.
    """
    t = clear_cs(path.read_text())
    if re.search(r"^\s*status:.*$", t, re.M):
        t = re.sub(r"^(\s*)status:.*$", r"\1status: dormant", t, count=1, flags=re.M)
    else:
        t = t.replace("---\n", "---\nstatus: dormant\n", 1)
    if re.search(r"^\s*dormant_since:.*$", t, re.M):
        t = re.sub(r"^(\s*)dormant_since:.*$", rf"\1dormant_since: {today}", t, count=1, flags=re.M)
    else:
        t = re.sub(r"^(\s*status: dormant)$", rf"\1\ndormant_since: {today}", t, count=1, flags=re.M)
    note = (f"\n## Dormant {today}\n\nUntouched for {age} days. Not finished and not queued — "
            "moved on from. Nothing is required of anyone. Edit this file and the next sweep "
            "returns it to in-flight automatically.\n")
    if f"## Dormant {today}" not in t:
        t = t.rstrip() + "\n" + note
    path.write_text(t)

def apply_revive(path, today):
    t = path.read_text()
    t = re.sub(r"^(\s*)status:.*$", r"\1status: in-flight", t, count=1, flags=re.M)
    t = re.sub(r"^\s*dormant_since:.*\n", "", t, count=1, flags=re.M)
    note = (f"\n## Revived {today}\n\nEdited after going dormant, so the sweep returned it to "
            "in-flight.\n")
    if f"## Revived {today}" not in t:
        t = t.rstrip() + "\n" + note
    path.write_text(t)

# apply_backlog() removed 2026-07-30. Dormancy replaced the age-out->backlog pathway;
# keeping a second, unreachable closing mechanism around is how the two copies of a
# capability start drifting (AGENTS.md principle 15).

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    # 20 days, per the operator 2026-07-30: "a project that sits for four weeks is 'done' and has
    # been moved on from ... for now it's not even on the backburner any more. It's closed."
    ap.add_argument("--age-days", type=int, default=20)
    ap.add_argument("--revive", metavar="NAME",
                    help="force a dormant workstream back to in-flight (with --apply)")
    ap.add_argument("--apply", action="store_true", help="perform mutations (default: report only)")
    args = ap.parse_args()
    today = datetime.date.fromisoformat(args.today)

    if args.revive:
        name = args.revive if args.revive.startswith("project_") else "project_" + args.revive
        p = MEM / f"{name}.md"
        if not p.exists():
            print(json.dumps({"error": f"no such workstream: {name}"})); sys.exit(1)
        st = (parse_fm(p.read_text())[0].get("status") or "").strip()
        if st != "dormant":
            print(json.dumps({"error": f"{name} is '{st}', not dormant"})); sys.exit(1)
        if args.apply:
            apply_revive(p, args.today)
        print(json.dumps({"revived": name, "mode": "apply" if args.apply else "report"}))
        return

    cu_cache = {}
    cs_links = load_current_state_links()
    report = {"reference_date": args.today, "age_days": args.age_days, "mode": "apply" if args.apply else "report",
              "current_state_items": len(cs_links),
              "closed_by_signal": [], "went_dormant": [], "revived": [], "pinned_skipped": [],
              "judgment_only": [], "needs_attention": [], "unknown_status": [],
              "errors": [], "unresolved_open": []}
    scanned = 0
    with_signal = 0
    judgment_only = 0
    for path in sorted(MEM.glob("project_*.md")):
        text = path.read_text()
        fm, _ = parse_fm(text)
        status = (fm.get("status") or "").strip()
        if status == "dormant":
            # Pathway 3 — revival. A dormant item is not "open", so it is not scanned or
            # counted, but it must still be VISITED: touch-to-revive is the counterweight
            # that makes closing on a timer safe, and a counterweight that only works when
            # someone remembers to invoke it is not a counterweight.
            lt, ds = str(fm.get("last_touched", "")), str(fm.get("dormant_since", ""))
            if re.match(r"\d{4}-\d{2}-\d{2}", lt) and re.match(r"\d{4}-\d{2}-\d{2}", ds) \
                    and lt[:10] > ds[:10]:
                report["revived"].append({"name": path.stem, "last_touched": lt[:10],
                                          "dormant_since": ds[:10]})
                if args.apply:
                    apply_revive(path, args.today)
            continue
        if status not in OPEN_STATUSES:
            if status not in CLOSED_STATUSES:
                # An unrecognised or missing status is invisible to BOTH pathways: it can
                # neither close nor go dormant, and appears in no count. On 2026-07-30
                # that hid 66 files, one of which (v2-contract-billing-grain-and-rates)
                # was active work touched six days earlier. Never skip in silence again —
                # normalize with normalize_workstream_status.py.
                report["unknown_status"].append({"name": path.stem, "status": status or "(none)"})
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
        # Pathway 2 — dormancy. Corpus-wide; `pin: true` is the ONLY exemption.
        #
        # The current-state membership test that used to live here is deliberately gone.
        # It meant the stalest items in the corpus — open, months old, already invisible —
        # were the exact set nothing could ever act on.
        lt = fm.get("last_touched", "")
        age = None
        if re.match(r"\d{4}-\d{2}-\d{2}", str(lt)):
            age = (today - datetime.date.fromisoformat(lt[:10])).days
        pinned = str(fm.get("pin", "")).strip().lower() in {"true", "yes", "1"}
        in_cs = name in cs_links
        if age is not None and age >= args.age_days:
            if pinned:
                report["pinned_skipped"].append({"name": name, "age_days": age})
            else:
                report["went_dormant"].append({"name": name, "last_touched": lt, "age_days": age,
                                               "in_current_state": in_cs})
                if args.apply:
                    apply_dormant(path, args.today, age)
        else:
            report["unresolved_open"].append({"name": name, "status": status, "last_touched": lt,
                                              "age_days": age, "in_current_state": in_cs, "signals": len(signals)})
    report["scanned_open"] = scanned
    report["dormant_total"] = sum(
        1 for p in MEM.glob("project_*.md")
        if (parse_fm(p.read_text())[0].get("status") or "").strip() == "dormant")
    # Emit the denominator and the ratio EXPLICITLY rather than making every caller
    # derive them. On 2026-07-30 three different figures for this one measurement
    # appeared within hours — "55 of 97 / 43%", "55 of 67 / 18%", "55 of 66 / 83%" —
    # in two memory files and a subagent report, because each reader summed a
    # different combination of the arrays below. The numerator was never in dispute.
    # A number that must be computed by the reader will be computed differently by
    # each reader; publish it once, from the code that owns it.
    #
    # 2026-07-30 — that first fix published a number, but the WRONG number: 97, from
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
        "went_dormant": len(report["went_dormant"]),
        "revived": len(report["revived"]),
        "dormant_total": report["dormant_total"],
        "unknown_status": len(report["unknown_status"]),
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
