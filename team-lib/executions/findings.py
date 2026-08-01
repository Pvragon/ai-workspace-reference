#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: "The findings inbox: a pull-only queue of audit observations, with an ambient
#   statusline segment that escalates on AGE. Decouples the cheap frequent write (nightly
#   audits) from the gated read (when the operator has space), so findings stop being
#   announced at the two worst moments — session close and session start."
# created: 2026-07-30
# last_updated: 2026-08-01
# maintainer: pvragon
# ---
"""findings.py — observations wait here until there is time to work them.

The problem this solves is TIMING, not content. Audit findings are legitimate and were
being surfaced at session close, which is the moment of lowest available attention and
highest context — the equivalent of answering "I need to go" with "wait, also this."
Session start is no better: you arrive with a goal and get derailed before touching it.

So this queue is never announced. It has exactly three ways out:

  1. AMBIENT  — a statusline segment showing count + age of the oldest. Costs no attention
                and creates no obligation. Absent entirely when empty: a counter that only
                grows is a guilt meter, and you learn to ignore it in a week.
  2. PULL     — `findings.py list`, run when there is space. The operator picks the moment.
  3. ESCAPE   — past ESCALATE_DAYS the segment stops being enough and the finding earns one
                mention in conversation. Escalation inside ONE channel has a ceiling: red
                in a fixed position becomes wallpaper just like grey. A rare channel change
                buys more than any amount of colour.

Two clocks, deliberately different:

  first_seen  drives ESCALATION — how long you have had this, i.e. how long it has been
              ignored. This is what the statusline colours on.
  last_seen   drives RESOLUTION — a finding the audit stops re-detecting has gone away on
              its own, so it closes silently. No human action, no queue debt.

That split is what keeps the inbox honest. A persistent real problem refreshes last_seen
nightly and keeps ageing on first_seen until it escapes the statusline entirely. A
transient one disappears without ever costing anyone a decision.
"""
import argparse, datetime, hashlib, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import state_dir  # noqa: E402

STORE = state_dir() / "findings.json"
# The statusline renders on nearly every keystroke-ish event; paying python startup there
# to read a file that changes once a day is waste. Every mutation writes the rendered
# segment here and the statusline just cats it. Age granularity is DAYS and the nightly
# tick mutates daily, so a write-time cache is exactly as fresh as the data it shows.
SEGMENT_CACHE = state_dir() / "findings-statusline.txt"

RESOLVE_AFTER_DAYS = 3     # not re-detected this long -> the condition went away
ESCALATE_DAYS = 21         # past this, one mention in conversation (the channel escape)
LANDFILL_DAYS = 60         # never actioned this long -> park it; the queue is not a museum

RESET, YELLOW, RED, DIM = "\033[0m", "\033[33m", "\033[31m", "\033[2m"


def _load():
    if not STORE.exists():
        return {"findings": []}
    try:
        return json.loads(STORE.read_text())
    except Exception:
        return {"findings": []}


def _save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, indent=2) + "\n")
    os.replace(tmp, STORE)
    try:
        SEGMENT_CACHE.write_text(_segment(d, datetime.date.today()))
    except Exception:
        pass


def _key(source, key, text):
    """Stable identity for dedupe. The nightly tick re-detects the same conditions every
    night; without this the inbox would grow by the full audit surface daily."""
    basis = f"{source}::{key or text}"
    return hashlib.sha1(basis.encode()).hexdigest()[:10]


def _days(iso, today):
    try:
        return (today - datetime.date.fromisoformat(iso[:10])).days
    except Exception:
        return 0


def cmd_record(a, today):
    d = _load()
    fid = _key(a.source, a.key, a.text)
    for f in d["findings"]:
        if f["id"] == fid and f["status"] in ("open", "escalated"):
            f["last_seen"] = today.isoformat()
            f["text"] = a.text                     # refresh wording/counts
            f["severity"] = a.severity
            _save(d)
            print(json.dumps({"updated": fid}))
            return 0
    d["findings"].append({
        "id": fid, "source": a.source, "key": a.key or "", "text": a.text,
        "severity": a.severity, "status": "open",
        "first_seen": today.isoformat(), "last_seen": today.isoformat(),
    })
    _save(d)
    print(json.dumps({"created": fid}))
    return 0


def cmd_sweep(a, today):
    """Resolve what is gone, park what has rotted. Run by the nightly tick AFTER recording."""
    d = _load()
    resolved, parked = [], []
    for f in d["findings"]:
        if f["status"] not in ("open", "escalated"):
            continue
        if _days(f["last_seen"], today) >= RESOLVE_AFTER_DAYS:
            f["status"] = "resolved"
            f["closed"] = today.isoformat()
            resolved.append(f["id"])
        elif _days(f["first_seen"], today) >= LANDFILL_DAYS:
            # Not a failure of the finding — a decision, made by not making it for two
            # months. Parked rather than deleted, and re-recording revives it.
            f["status"] = "dormant"
            f["closed"] = today.isoformat()
            parked.append(f["id"])
    _save(d)
    print(json.dumps({"resolved": resolved, "parked": parked}))
    return 0


def _open_findings(d, today):
    out = [f for f in d["findings"] if f["status"] in ("open", "escalated")]
    out.sort(key=lambda f: f["first_seen"])
    return out


def cmd_list(a, today):
    d = _load()
    rows = _open_findings(d, today)
    if a.json:
        print(json.dumps({"open": rows}, indent=2)); return 0
    if not rows:
        print("Findings inbox is empty."); return 0
    print(f"{len(rows)} open finding(s), oldest {_days(rows[0]['first_seen'], today)}d:\n")
    for f in rows:
        age = _days(f["first_seen"], today)
        mark = "🔴" if age >= ESCALATE_DAYS else ("🟡" if age >= 7 else "  ")
        sev = " [CRITICAL]" if f["severity"] == "critical" else ""
        print(f"{mark} {f['id']}  {age:>3}d  {f['source']}{sev}")
        print(f"      {f['text']}")
    print(f"\nDismiss with: findings.py dismiss <id>")
    return 0


def cmd_dismiss(a, today):
    d = _load()
    hit = False
    for f in d["findings"]:
        if f["id"] == a.id and f["status"] in ("open", "escalated"):
            f["status"] = "dismissed"; f["closed"] = today.isoformat(); hit = True
    _save(d)
    print(json.dumps({"dismissed": a.id} if hit else {"error": f"no open finding {a.id}"}))
    return 0 if hit else 1


def _segment(d, today):
    """The rendered statusline segment, or empty when the inbox is empty.

    ONE implementation, used by both the write-time cache and the `statusline` subcommand —
    two renderers would drift, and the cached one is the one actually seen.
    """
    rows = _open_findings(d, today)
    if not rows:
        return ""
    oldest = _days(rows[0]["first_seen"], today)
    n = len(rows)
    crit = sum(1 for f in rows if f["severity"] == "critical")
    if crit:
        seg = f"{RED}📥 {n} findings · {crit} CRITICAL{RESET}"
    elif oldest >= ESCALATE_DAYS:
        seg = f"{RED}📥 {n} findings · OLDEST {oldest}d{RESET}"
    elif oldest >= 14:
        seg = f"{RED}📥 {n} findings · oldest {oldest}d{RESET}"
    elif oldest >= 7:
        seg = f"{YELLOW}📥 {n} findings · oldest {oldest}d{RESET}"
    elif oldest >= 3:
        seg = f"📥 {n} findings · {oldest}d"
    else:
        seg = f"{DIM}◦ {n} findings{RESET}"
    return f"  │  {seg}"


def cmd_statusline(a, today):
    """One segment for the statusline, escalating on the age of the oldest.

    Prints NOTHING when the inbox is empty — the absence is the reward, and a segment that
    is always present is one that is never read.
    """
    seg = _segment(_load(), today)
    if seg:
        print(seg)
    return 0


def cmd_escalations(a, today):
    """Findings that have outgrown the statusline. The ONLY push channel, and it fires
    rarely by construction — if it fires often, the triage is wrong, not the threshold."""
    rows = [f for f in _open_findings(_load(), today)
            if _days(f["first_seen"], today) >= ESCALATE_DAYS or f["severity"] == "critical"]
    print(json.dumps({"escalations": rows}, indent=2) if a.json else
          "\n".join(f"{_days(f['first_seen'], today)}d  {f['source']}: {f['text']}" for f in rows))
    return 0


def main():
    # --today on a shared parent so it is accepted on EITHER side of the subcommand.
    # Parent-only placement is a trap in a tool meant to be scripted: `findings.py record
    # ... --today X` is the natural order and would have failed with an unhelpful usage dump.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--today", default=datetime.date.today().isoformat())
    ap = argparse.ArgumentParser(description="findings inbox", parents=[common])
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", parents=[common]); r.add_argument("--source", required=True)
    r.add_argument("--text", required=True); r.add_argument("--key", default="")
    r.add_argument("--severity", default="normal", choices=["normal", "critical"])
    r.set_defaults(fn=cmd_record)

    l = sub.add_parser("list", parents=[common]); l.add_argument("--json", action="store_true"); l.set_defaults(fn=cmd_list)
    s = sub.add_parser("sweep", parents=[common]); s.set_defaults(fn=cmd_sweep)
    dm = sub.add_parser("dismiss", parents=[common]); dm.add_argument("id"); dm.set_defaults(fn=cmd_dismiss)
    st = sub.add_parser("statusline", parents=[common]); st.set_defaults(fn=cmd_statusline)
    e = sub.add_parser("escalations", parents=[common]); e.add_argument("--json", action="store_true"); e.set_defaults(fn=cmd_escalations)

    a = ap.parse_args()
    return a.fn(a, datetime.date.fromisoformat(a.today))


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
