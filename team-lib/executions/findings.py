#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "The findings inbox: a pull-only queue of audit observations, each in a lane (auto,
#   ask, hands-off) from config/findings-lanes.yaml, with an ambient statusline segment that
#   counts only the `ask` lane and escalates on AGE. The nightly findings_resolver.py works the
#   auto lane; the operator sees only what needs him."
# created: 2026-07-30
# last_updated: 2026-10-20
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

Two flags for sources the last_seen clock cannot describe (added 2026-09-25):

  --once  The source records once and never re-detects (a meditation, a debrief). Under the
          last_seen clock it would close as "resolved" on day three with nothing decided and
          nothing changed. Instead it stays open ONCE_ICE_DAYS, then goes on ice ("dormant",
          reason "iced"). Recording the same key again revives it: ice means "wait until the
          topic comes back", not "answered".
  --hold  Waiting has a cost that keeps growing (money, a person waiting, a deadline, something
          breaking). Never auto-closes and is always in `escalations`. Closes only by a human
          answer: `dismiss <id> --note "..."`. Use it rarely; if it is common, triage is wrong.

Measured before the change: all 9 dream-sourced findings read "resolved" and none of their
conditions had changed. Four were questions for the operator that never reached him.

Lanes (added 2026-10-20, approved design). Every finding is in one of three lanes:

  auto       Your Agent's to resolve. The nightly findings_resolver.py re-checks these and closes
             the stale ones (and, in live mode, applies whitelisted fixes).
  ask        A decision that is the owner's: money, people, outward messages, authorship, a
             choice between options, or a question a reflective wake filed with --hold.
  hands-off  An open workstream or a live session owns it. Recorded, never acted on.

The lane is decided by the first matching rule in config/findings-lanes.yaml (plus the personal
overlay my-lib/config/findings-lanes.yaml), so it is data, not code. It is stamped on the row
at record time with lane_by "rules", and re-derived while lane_by stays "rules", so a rule edit
reaches existing rows. A lane set by the resolver or by hand (`lane <id> <lane>`) sticks.
Rows written before lanes existed have no lane field and are classified the same way.

The statusline counts ONLY the ask lane: a number there means "needs the owner". Its format is
unchanged. If the lane config cannot be read, every row counts as ask, which is exactly the
pre-lane behaviour, so a broken config fails loud rather than silent.
"""
import argparse, datetime, hashlib, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_paths import state_dir, workspace  # noqa: E402

LANES = ("auto", "ask", "hands-off")
LANES_CONFIG = Path(__file__).resolve().parent.parent / "config" / "findings-lanes.yaml"
# Personal overlay: client names, internal domains, team repos — never in the published file.
LANES_OVERLAY = workspace() / "my-lib" / "config" / "findings-lanes.yaml"

STORE = state_dir() / "findings.json"
# The statusline renders on nearly every keystroke-ish event; paying python startup there
# to read a file that changes once a day is waste. Every mutation writes the rendered
# segment here and the statusline just cats it. Age granularity is DAYS and the nightly
# tick mutates daily, so a write-time cache is exactly as fresh as the data it shows.
SEGMENT_CACHE = state_dir() / "findings-statusline.txt"

RESOLVE_AFTER_DAYS = 3     # not re-detected this long -> the condition went away
ESCALATE_DAYS = 21         # past this, one mention in conversation (the channel escape)
LANDFILL_DAYS = 60         # never actioned this long -> park it; the queue is not a museum
ONCE_ICE_DAYS = 14         # a --once finding stays visible this long, then goes on ice

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


_LANE_CFG = None


def lane_config() -> dict:
    """team-lib's lane config with the personal overlay merged in. Lists append, scalars override.

    Returns {} when the config cannot be read; callers treat that as "every row is ask", the
    pre-lane behaviour. Cached per process: the statusline cache is written on every mutation.
    """
    global _LANE_CFG
    if _LANE_CFG is not None:
        return _LANE_CFG
    cfg = {}
    try:
        import yaml
        cfg = yaml.safe_load(LANES_CONFIG.read_text()) or {}
        if LANES_OVERLAY.exists():
            over = yaml.safe_load(LANES_OVERLAY.read_text()) or {}
            for k, v in over.items():
                if isinstance(v, list) and isinstance(cfg.get(k), list):
                    cfg[k] = cfg[k] + v
                else:
                    cfg[k] = v
    except Exception:
        cfg = {}
    _LANE_CFG = cfg
    return cfg


def _any(patterns, hay) -> bool:
    for p in patterns or ():
        try:
            if re.search(p, hay, re.I):
                return True
        except re.error:
            continue
    return False


def _rule_hits(match: dict, f: dict, cfg: dict) -> bool:
    for field, want in (match or {}).items():
        if field == "source":
            if not re.fullmatch(want, f.get("source", "")):
                return False
        elif field in ("key", "text"):
            hay = f.get(field, "") or ""
            if isinstance(want, str) and want.startswith("@"):
                # A reference to a pattern list; searched in key + text together.
                if not _any(cfg.get(want[1:]), f"{f.get('key', '')} {f.get('text', '')}"):
                    return False
            elif not re.search(want, hay, re.I):
                return False
        elif field in ("hold", "once"):
            if bool(f.get(field)) != bool(want):
                return False
        elif field == "severity":
            if f.get("severity", "normal") != want:
                return False
        else:
            return False                           # an unknown field never matches
    return True


def classify(f: dict) -> tuple:
    """(lane, kind) for a finding from the rules table alone, ignoring any stored lane."""
    cfg = lane_config()
    if not cfg:
        return "ask", "unclassified"
    for rule in cfg.get("rules") or ():
        if _rule_hits(rule.get("match") or {}, f, cfg):
            return rule.get("lane", "ask"), rule.get("kind", "freeform")
    d = cfg.get("default") or {}
    return d.get("lane", "ask"), d.get("kind", "freeform")


def lane_of(f: dict) -> str:
    """The lane that counts: a lane set by the resolver or by hand sticks; otherwise the rules."""
    if f.get("lane") in LANES and f.get("lane_by") in ("resolver", "human"):
        return f["lane"]
    return classify(f)[0]


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


def _stamp_lane(f, a):
    """Write the lane onto the row. --lane is the recorder saying so (sticks like a hand-set
    lane); otherwise the rules decide, unless the resolver or a human already moved it."""
    if getattr(a, "lane", None):
        f["lane"], f["lane_by"] = a.lane, "human"
    elif f.get("lane_by") not in ("resolver", "human"):
        f["lane"], f["lane_by"] = classify(f)[0], "rules"


def cmd_record(a, today):
    d = _load()
    fid = _key(a.source, a.key, a.text)
    for f in d["findings"]:
        if f["id"] == fid and f["status"] in ("open", "escalated"):
            f["last_seen"] = today.isoformat()
            f["text"] = a.text                     # refresh wording/counts
            f["severity"] = a.severity
            if a.once: f["once"] = True
            if a.hold: f["hold"] = True
            _stamp_lane(f, a)
            _save(d)
            print(json.dumps({"updated": fid}))
            return 0
    for f in d["findings"]:
        # Revival. Ice means "until the topic comes back"; this is it coming back. Without
        # this branch a re-record appended a SECOND row with the same id.
        if f["id"] == fid and f["status"] == "dormant":
            f.update(status="open", last_seen=today.isoformat(), text=a.text,
                     severity=a.severity, revived=today.isoformat())
            f.pop("closed", None); f.pop("reason", None)
            if a.once: f["once"] = True
            if a.hold: f["hold"] = True
            _stamp_lane(f, a)
            _save(d)
            print(json.dumps({"revived": fid}))
            return 0
    row = {
        "id": fid, "source": a.source, "key": a.key or "", "text": a.text,
        "severity": a.severity, "status": "open",
        "first_seen": today.isoformat(), "last_seen": today.isoformat(),
    }
    if a.once: row["once"] = True
    if a.hold: row["hold"] = True
    _stamp_lane(row, a)
    d["findings"].append(row)
    _save(d)
    print(json.dumps({"created": fid}))
    return 0


def cmd_sweep(a, today):
    """Resolve what is gone, park what has rotted. Run by the nightly tick AFTER recording."""
    d = _load()
    resolved, parked, iced = [], [], []
    for f in d["findings"]:
        if f["status"] not in ("open", "escalated"):
            continue
        if f.get("hold"):
            continue                               # only a human answer closes a hold
        if f.get("once"):
            # No re-detection will ever come, so last_seen says nothing. Never "resolved".
            if _days(f["first_seen"], today) >= ONCE_ICE_DAYS:
                f["status"] = "dormant"; f["reason"] = "iced"
                f["closed"] = today.isoformat()
                iced.append(f["id"])
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
    print(json.dumps({"resolved": resolved, "parked": parked, "iced": iced}))
    return 0


def _open_findings(d, today):
    out = [f for f in d["findings"] if f["status"] in ("open", "escalated")]
    out.sort(key=lambda f: f["first_seen"])
    return out


def cmd_list(a, today):
    d = _load()
    rows = _open_findings(d, today)
    if getattr(a, "lane", None):
        rows = [f for f in rows if lane_of(f) == a.lane]
    if a.json:
        # Additive: every row gains its effective lane and resolver kind; nothing is removed.
        out = [dict(f, lane=lane_of(f), kind=classify(f)[1]) for f in rows]
        print(json.dumps({"open": out}, indent=2)); return 0
    if not rows:
        print("Findings inbox is empty."); return 0
    print(f"{len(rows)} open finding(s), oldest {_days(rows[0]['first_seen'], today)}d:\n")
    for f in rows:
        age = _days(f["first_seen"], today)
        mark = "🔴" if age >= ESCALATE_DAYS else ("🟡" if age >= 7 else "  ")
        sev = " [CRITICAL]" if f["severity"] == "critical" else ""
        sev += " [HOLD]" if f.get("hold") else ""
        sev += f" [{lane_of(f)}]"
        print(f"{mark} {f['id']}  {age:>3}d  {f['source']}{sev}")
        print(f"      {f['text']}")
    print(f"\nDismiss with: findings.py dismiss <id> [--note \"what was decided\"]")
    return 0


def cmd_dismiss(a, today):
    d = _load()
    hit = False
    for f in d["findings"]:
        if f["id"] == a.id and f["status"] in ("open", "escalated"):
            f["status"] = "dismissed"; f["closed"] = today.isoformat(); hit = True
            if a.note: f["note"] = a.note
    _save(d)
    print(json.dumps({"dismissed": a.id} if hit else {"error": f"no open finding {a.id}"}))
    return 0 if hit else 1


def set_lane(d: dict, fid: str, lane: str, by: str, note: str = "") -> bool:
    """Move an open finding to a lane. Used by `lane` (by=human) and the resolver (by=resolver)."""
    hit = False
    for f in d["findings"]:
        if f["id"] == fid and f["status"] in ("open", "escalated"):
            f["lane"], f["lane_by"] = lane, by
            if note:
                f["lane_note"] = note
            hit = True
    return hit


def cmd_lane(a, today):
    d = _load()
    hit = set_lane(d, a.id, a.lane, "human", a.note)
    if hit:
        _save(d)
    print(json.dumps({"lane": a.lane, "id": a.id} if hit else {"error": f"no open finding {a.id}"}))
    return 0 if hit else 1


def _segment(d, today):
    """The rendered statusline segment, or empty when the inbox is empty.

    ONE implementation, used by both the write-time cache and the `statusline` subcommand —
    two renderers would drift, and the cached one is the one actually seen.
    """
    # Only the ask lane: a number here means "needs the owner". auto is the resolver's,
    # hands-off belongs to a workstream; both stay in `list` and the morning readout.
    rows = [f for f in _open_findings(d, today) if lane_of(f) == "ask"]
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
    # hands-off rows never escalate: their owner is the workstream, not this channel.
    rows = [f for f in _open_findings(_load(), today)
            if (_days(f["first_seen"], today) >= ESCALATE_DAYS or f["severity"] == "critical"
                or f.get("hold")) and lane_of(f) != "hands-off"]
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
    r.add_argument("--once", action="store_true", help="source never re-detects; ice, never auto-resolve")
    r.add_argument("--hold", action="store_true", help="cost grows while waiting; open until a human answers")
    r.add_argument("--lane", choices=LANES, default=None,
                   help="override the rules table (config/findings-lanes.yaml) for this finding")
    r.set_defaults(fn=cmd_record)

    l = sub.add_parser("list", parents=[common]); l.add_argument("--json", action="store_true")
    l.add_argument("--lane", choices=LANES, default=None, help="only this lane")
    l.set_defaults(fn=cmd_list)
    ln = sub.add_parser("lane", parents=[common], help="move an open finding to a lane (sticks)")
    ln.add_argument("id"); ln.add_argument("lane", choices=LANES); ln.add_argument("--note", default="")
    ln.set_defaults(fn=cmd_lane)
    s = sub.add_parser("sweep", parents=[common]); s.set_defaults(fn=cmd_sweep)
    dm = sub.add_parser("dismiss", parents=[common]); dm.add_argument("id"); dm.add_argument("--note", default="")
    dm.set_defaults(fn=cmd_dismiss)
    st = sub.add_parser("statusline", parents=[common]); st.set_defaults(fn=cmd_statusline)
    e = sub.add_parser("escalations", parents=[common]); e.add_argument("--json", action="store_true"); e.set_defaults(fn=cmd_escalations)

    a = ap.parse_args()
    return a.fn(a, datetime.date.fromisoformat(a.today))


def run() -> int:
    return main()


if __name__ == "__main__":
    sys.exit(main())
