#!/usr/bin/env python3
# ---
# template: execution
# version: 2.0.0
# summary: Deterministic helpers for the autoresearch loop's bookkeeping — results.tsv (Karpathy's
#   5-column ledger), the keep/discard decision with an optional noise threshold, and the safe
#   revert of a discarded experiment commit. The agent still runs the loop; this keeps the ledger
#   well-formed and the git reset from ever eating a non-experiment commit.
# created: 2026-09-04
# last_updated: 2026-09-04
# maintainer: pvragon
# ---
"""
Usage
  autoresearch_ledger.py init   --ledger PATH --metric NAME [--aux NAME]
  autoresearch_ledger.py record --ledger PATH --repo DIR --metric VALUE --aux VALUE --status keep|discard|crash --note "text"
  autoresearch_ledger.py best   --ledger PATH --direction lower|higher      -> prints the best kept metric so far
  autoresearch_ledger.py decide --ledger PATH --direction lower|higher --metric VALUE [--threshold 0.0] [--simpler]
                                 -> prints keep or discard (exit 0 = keep, 1 = discard)
  autoresearch_ledger.py revert --repo DIR   -> git reset --hard HEAD~1, only if HEAD is an "autoresearch:" commit

Ledger format is Karpathy's, verbatim: tab-separated, header row, 5 columns
  commit<TAB><metric><TAB><aux><TAB>status<TAB>description
The metric column is named for the program's metric (val_bpb in the original); aux is the
soft-constraint column (memory_gb in the original). Descriptions may contain anything but tabs.
"""
import argparse, subprocess, sys
from pathlib import Path


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def read(ledger):
    rows = []
    lines = Path(ledger).read_text().splitlines()
    header = lines[0].split("\t") if lines else []
    for line in lines[1:]:
        if line.strip():
            parts = line.split("\t")
            rows.append(dict(zip(header, parts)))
    return header, rows


def cmd_init(a):
    p = Path(a.ledger)
    if p.exists():
        sys.exit(f"refusing to overwrite existing ledger {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"commit\t{a.metric}\t{a.aux}\tstatus\tdescription\n")
    print(f"initialised {p}")


def cmd_record(a):
    if a.status not in ("keep", "discard", "crash"):
        sys.exit("status must be keep, discard or crash")
    if "\t" in a.note:
        sys.exit("description must not contain tabs")
    commit = git(a.repo, "rev-parse", "--short=7", "HEAD").stdout.strip() or "0000000"
    with open(a.ledger, "a") as f:
        f.write(f"{commit}\t{a.metric}\t{a.aux}\t{a.status}\t{a.note}\n")
    print(f"recorded {commit} {a.metric} {a.status}")


def best_kept(ledger, direction):
    header, rows = read(ledger)
    kept = [float(r[header[1]]) for r in rows if r.get("status") == "keep"]
    if not kept:
        return None
    return min(kept) if direction == "lower" else max(kept)


def cmd_best(a):
    b = best_kept(a.ledger, a.direction)
    print("none" if b is None else f"{b:.6f}")


def cmd_decide(a):
    b = best_kept(a.ledger, a.direction)
    m = float(a.metric)
    if b is None:
        print("keep (baseline)"); return 0
    delta = (b - m) if a.direction == "lower" else (m - b)
    # Karpathy: keep only if strictly improved. Our addition: an improvement smaller than the
    # measured noise floor is not an improvement; --simpler lets an equal-or-better result that
    # removed complexity through (his simplicity criterion).
    if delta > a.threshold or (a.simpler and delta >= 0):
        print(f"keep (delta {delta:+.6f} vs best {b:.6f})"); return 0
    print(f"discard (delta {delta:+.6f} vs best {b:.6f}, threshold {a.threshold})"); return 1


def cmd_revert(a):
    subject = git(a.repo, "log", "-1", "--format=%s").stdout.strip()
    if not subject.startswith("autoresearch:"):
        sys.exit(f"refusing: HEAD commit is not an experiment commit: {subject!r}")
    if git(a.repo, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        sys.exit("refusing: working tree has uncommitted changes")
    r = git(a.repo, "reset", "--hard", "HEAD~1")
    print(r.stdout.strip() or r.stderr.strip())


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("--ledger", required=True); s.add_argument("--metric", required=True); s.add_argument("--aux", default="aux")
    s = sub.add_parser("record"); s.add_argument("--ledger", required=True); s.add_argument("--repo", required=True); s.add_argument("--metric", required=True); s.add_argument("--aux", default="0.0"); s.add_argument("--status", required=True); s.add_argument("--note", required=True)
    s = sub.add_parser("best"); s.add_argument("--ledger", required=True); s.add_argument("--direction", choices=["lower", "higher"], required=True)
    s = sub.add_parser("decide"); s.add_argument("--ledger", required=True); s.add_argument("--direction", choices=["lower", "higher"], required=True); s.add_argument("--metric", required=True); s.add_argument("--threshold", type=float, default=0.0); s.add_argument("--simpler", action="store_true")
    s = sub.add_parser("revert"); s.add_argument("--repo", required=True)
    a = ap.parse_args()
    rc = {"init": cmd_init, "record": cmd_record, "best": cmd_best, "decide": cmd_decide, "revert": cmd_revert}[a.cmd](a)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
