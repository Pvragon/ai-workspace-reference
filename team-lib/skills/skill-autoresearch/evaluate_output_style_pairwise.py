#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: Immutable pairwise evaluator for the output-style-v2 lineage. Runs the candidate style
#   over 17 prompts in a vanilla directory with read-only tools, then judges every candidate reply
#   against frozen Concise and ASD-STE100 references in BOTH orders (position-balanced). Metric is
#   the win fraction; a cluster bootstrap over packets prints its standard error and the keep
#   threshold. Deterministic prose tells act as guards, never as the objective.
# created: 2026-09-04
# last_updated: 2026-09-04
# maintainer: pvragon
# ---
"""
Usage
  evaluate_output_style_pairwise.py --style PATH --out DIR [--runs 2] [--jobs 3] [--refs Concise,ASD-STE100]
                                    [--model claude-opus-5] [--judge-model claude-opus-5] [--prompts id,id]

Summary block (grep the first line for the metric):
  ---
  score:            0.7188   win fraction over all ballots, higher is better
  score_se:         0.0410   cluster-bootstrap standard error over packets
  keep_threshold:   0.0820   2 x score_se; pass to autoresearch_ledger.py decide --threshold
  win_vs_Concise:   0.7500
  win_vs_ASD-STE100: 0.6875
  quality:          4.31     candidate mean of (correctness, completeness) across ballots, diagnostic
  readability:      4.58     candidate mean of the four readability criteria, diagnostic
  correctness_min:  4        guard: >= 3
  words:            281.3    guard: <= 1.5 x mean reference words
  emdash_per100:    0.04     guard: <= 0.10
  long_sentences:   0.04     guard: <= 0.10 (share of sentences over 25 words)
  closing_offers:   0.06     guard: <= 0.10 per reply
  narration:        0.00     guard: <= 0.10 per reply
  guards_ok:        1        1 = every guard passed; the program discards on 0 regardless of score
  guards_failed:    none     which guards failed, if any
Every run writes tells.json next to its ballots. From the second experiment on, pass the
baseline's file as --baseline-tells so a guard is "no worse than max(cap, 1.25 x baseline + 0.02)"
rather than an absolute cap the baseline itself might not meet.
  packets:          34
  ballots:          136
  crashed_runs:     0
  failed_judges:    0
Exit 2 if any candidate run or judge produced no output.
"""
import argparse, json, os, random, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent / "evaluators" / "output-style-v2"
Q = ["correctness", "completeness"]; R = ["directness", "plain_language", "economy", "length"]
NO_WRITE = "Write Edit MultiEdit NotebookEdit Bash EnterPlanMode ExitPlanMode WebFetch WebSearch Agent".split()
CLOSING = re.compile(r"(say the word|let me know if|want me to|happy to (draft|write|help|do)|i can (draft|write|implement|do that|set that up)|shall i)", re.I)
NARRATION = re.compile(r"(^|\n)\s*(i (read|checked|looked at|ran|wrote|did not run|didn't run|have written)\b|.*\b(plan file|plan mode|exitplanmode)\b|.*\btools? (is|are) (not )?available\b)", re.I)
GUARDS = dict(correctness_min=3, emdash_per100=0.10, long_sentences=0.10, closing_offers=0.10, narration=0.10, words_ratio=1.5)


def clean_env():
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}


def claude_p(prompt, extra, timeout=900):
    cmd = ["claude", "-p", prompt, "--setting-sources", "local", "--output-format", "json", "--permission-mode", "default",
           "--allowedTools", "Read", "Glob", "Grep", "--disallowedTools", *NO_WRITE, "--no-session-persistence", "--max-turns", "10", *extra]
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout, env=clean_env())
        if not p.stdout.strip(): return None, f"empty stdout rc={p.returncode} stderr={p.stderr[-300:]!r}"
        d = json.loads(p.stdout)
        return (None, d.get("result", "")[:300]) if d.get("is_error") else (d.get("result", ""), None)
    except subprocess.TimeoutExpired: return None, "timeout"
    except Exception as e: return None, f"{type(e).__name__}: {str(e)[:200]}"


def prose(text):
    p = re.sub(r"```.*?```", "", text, flags=re.S)
    return "\n".join(l for l in p.splitlines() if not l.strip().startswith("|"))


def tells(text):
    p = prose(text); words = re.findall(r"\b\w[\w'-]*\b", p); W = max(len(words), 1)
    sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", p) if s.strip()]; slen = [len(s.split()) for s in sents]
    return dict(words=W, emdash_per100=p.count("—") * 100 / W, long_sentences=sum(1 for n in slen if n > 25) / max(len(slen), 1),
                closing_offers=1 if CLOSING.search(p[-400:]) else 0, narration=1 if NARRATION.search(p) else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=2); ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--refs", default="Concise,ASD-STE100"); ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--judge-model", default="claude-opus-5"); ap.add_argument("--prompts", default="")
    ap.add_argument("--baseline-tells", default="", help="tells.json from the baseline run; guards then allow max(cap, 1.25 x baseline + 0.02)")
    a = ap.parse_args(); refs_wanted = a.refs.split(",")
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    body = re.sub(r"^---\n.*?\n---\n", "", Path(a.style).read_text(), count=1, flags=re.S).strip() + "\n"
    (out / "style_body.txt").write_text(body)
    prompts = json.loads((HERE / "prompts.json").read_text())
    if a.prompts: keep = set(a.prompts.split(",")); prompts = [p for p in prompts if p["id"] in keep]
    ptext = {p["id"]: p["prompt"] for p in prompts}
    brief = (HERE / "judge_brief_pairwise.md").read_text()
    refs = {}
    for f in (HERE / "reference").glob("*.json"):
        r = json.loads(f.read_text()); refs[(r["style"], r["prompt_id"], r["run"])] = r["text"]

    crashed = 0; cand = {}
    def run_cand(pid, run):
        t, err = claude_p(ptext[pid], ["--append-system-prompt-file", str(out / "style_body.txt"), "--model", a.model]); return pid, run, t, err
    with ThreadPoolExecutor(a.jobs) as ex:
        for f in as_completed([ex.submit(run_cand, p["id"], r) for p in prompts for r in range(1, a.runs + 1)]):
            pid, run, t, err = f.result()
            if t is None: crashed += 1; print(f"[crash] candidate {pid} r{run}: {err}", file=sys.stderr); continue
            cand[(pid, run)] = t
            (out / f"candidate__{pid}__r{run}.json").write_text(json.dumps({"prompt_id": pid, "run": run, "text": t}, indent=2))
            print(f"[cand] {pid} r{run} words={tells(t)['words']}", file=sys.stderr)

    ballots = []; failed = 0
    def judge(pid, run, ref, cand_first):
        rt = refs.get((ref, pid, run)) or refs.get((ref, pid, 1))
        if rt is None: return None, f"missing reference {ref} {pid}"
        A, B = (cand[(pid, run)], rt) if cand_first else (rt, cand[(pid, run)])
        packet = f"# Packet\n\n## The user's prompt\n\n```text\n{ptext[pid]}\n```\n\n## Response A\n\n{A.strip()}\n\n## Response B\n\n{B.strip()}\n"
        t, err = claude_p(brief + "\n\n" + packet, ["--model", a.judge_model])
        if t is None: return None, err
        try: v = json.loads(t[t.index("{"): t.rindex("}") + 1]); assert v["winner"] in ("A", "B")
        except Exception as e: return None, f"unparseable verdict: {str(e)[:100]}"
        cl = "A" if cand_first else "B"
        return {"pid": pid, "run": run, "ref": ref, "cand_label": cl, "won": v["winner"] == cl, "cand_scores": v["scores"][cl], "reason": v.get("reason", ""), "errors": v.get("errors_found", {})}, None
    jobs = [(pid, run, ref, cf) for (pid, run) in sorted(cand) for ref in refs_wanted for cf in (True, False)]
    with ThreadPoolExecutor(a.jobs) as ex:
        for f in as_completed([ex.submit(judge, *j) for j in jobs]):
            b, err = f.result()
            if b is None: failed += 1; print(f"[judge-fail] {err}", file=sys.stderr); continue
            ballots.append(b)
    (out / "ballots.json").write_text(json.dumps(ballots, indent=2))

    n = len(ballots); wins = sum(b["won"] for b in ballots); score = wins / n if n else 0.0
    # cluster bootstrap over packets (pid, run): ballots within a packet share the transcript
    by_packet = {}
    for b in ballots: by_packet.setdefault((b["pid"], b["run"]), []).append(b["won"])
    keys = list(by_packet); rng = random.Random(260904); boots = []
    for _ in range(1000):
        s = [w for k in rng.choices(keys, k=len(keys)) for w in by_packet[k]]
        boots.append(sum(s) / len(s))
    se = (sum((x - score) ** 2 for x in boots) / max(len(boots) - 1, 1)) ** 0.5 if keys else 0.0
    per_ref = {r: [b["won"] for b in ballots if b["ref"] == r] for r in refs_wanted}
    cs = [b["cand_scores"] for b in ballots]
    quality = sum(sum(c[k] for k in Q) / 2 for c in cs) / n if n else 0; readab = sum(sum(c[k] for k in R) / 4 for c in cs) / n if n else 0
    cmin = min((c["correctness"] for c in cs), default=0)
    tl = [tells(t) for t in cand.values()]; m = {k: sum(t[k] for t in tl) / max(len(tl), 1) for k in tl[0]} if tl else {}
    ref_words = [tells(refs[k])["words"] for k in refs if k[0] in refs_wanted and k[1] in ptext]
    words_cap = GUARDS["words_ratio"] * (sum(ref_words) / max(len(ref_words), 1))
    base = json.loads(Path(a.baseline_tells).read_text()) if a.baseline_tells else {}
    def cap(k):
        c = GUARDS[k]
        return max(c, 1.25 * base[k] + 0.02) if k in base else c
    m["correctness_min"] = cmin
    (out / "tells.json").write_text(json.dumps({**m, "words_cap": words_cap}, indent=2))
    failed_guards = [k for k in ("emdash_per100", "long_sentences", "closing_offers", "narration") if m[k] > cap(k)]
    if cmin < GUARDS["correctness_min"]: failed_guards.append("correctness_min")
    if m["words"] > max(words_cap, 1.25 * base.get("words", 0) + 0.02): failed_guards.append("words")
    guards_ok = int(bool(tl) and not failed_guards)
    print("---")
    print(f"score:            {score:.4f}"); print(f"score_se:         {se:.4f}"); print(f"keep_threshold:   {2*se:.4f}")
    for r in refs_wanted: print(f"win_vs_{r}: {sum(per_ref[r])/max(len(per_ref[r]),1):.4f}")
    print(f"quality:          {quality:.2f}"); print(f"readability:      {readab:.2f}"); print(f"correctness_min:  {cmin}")
    for k in ("words", "emdash_per100", "long_sentences", "closing_offers", "narration"):
        print(f"{k+':':18s}{m.get(k, 0):.2f}")
    print(f"words_cap:        {words_cap:.1f}"); print(f"guards_ok:        {guards_ok}"); print(f"guards_failed:    {','.join(failed_guards) or 'none'}")
    print(f"packets:          {len(cand)}"); print(f"ballots:          {n}"); print(f"crashed_runs:     {crashed}"); print(f"failed_judges:    {failed}")
    sys.exit(2 if (crashed or failed or not ballots) else 0)


if __name__ == "__main__":
    main()
