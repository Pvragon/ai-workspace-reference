#!/usr/bin/env python3
# ---
# template: execution
# version: 2.0.1
# summary: >-
#   Immutable evaluator for the output-style autoresearch program. Runs a candidate style
#   over a fixed prompt set in a vanilla directory (no CLAUDE.md), builds blinded packets against
#   frozen reference transcripts, judges them with claude -p under a fixed rubric, and prints a
#   Karpathy-style summary block whose "score:" line is the metric. Everything it reads is frozen:
#   prompts, fixture, reference transcripts, judge brief. Do not edit inside a run.
# created: 2026-09-04
# last_updated: 2026-10-07
# maintainer: pvragon
# ---
"""
Usage
  evaluate_output_style.py --style PATH --out DIR [--runs 2] [--judges 2] [--jobs 3] [--model claude-opus-5]
                           [--prompts id,id] [--judge-model claude-opus-5]

Prints, at the end, a block like:
  ---
  score:            4.4321      mean composite (0.5 quality + 0.5 readability), 1-5, higher is better
  win_rate:         0.6250      share of ballots ranking the candidate first of four
  quality:          4.2500
  readability:      4.6100
  correctness_min:  4           lowest correctness score any judge gave the candidate
  words:            281.3       mean prose words per reply (soft constraint, like VRAM)
  emdash_per100:    0.04
  long_sentences:   0.04        share of sentences over 25 words
  packets:          16
  ballots:          32
  crashed_runs:     0
Extract the metric with:  grep "^score:" run.log
Exit code is 2 if any candidate run or judge failed to produce output, so a crash is detectable.

Design notes
- Candidate runs use --setting-sources local (drops every CLAUDE.md; verified 2026-09-03) and
  --append-system-prompt-file, which is the same system-prompt layer an output style with
  keep-coding-instructions: true occupies. --bare is not used: it skips the subscription login.
- Tools are restricted to Read/Glob/Grep so no arm can dodge a prompt by writing a plan file
  (the plan-mode artifact that cost two arms a packet each on 2026-09-04).
- Reference arms are FROZEN transcripts (Default, Concise, ASD-STE100; 8 prompts x 2 runs,
  captured 2026-09-03 on claude-opus-5). The candidate is judged against the same references
  every experiment, which is what makes experiments comparable.
- Judges are claude -p sessions given the brief and a shuffled 4-response packet, replying with
  JSON. Label->style keys never leave this process.
"""
import argparse, json, os, random, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent / "evaluators" / "output-style"
REFS = ["Default", "Concise", "ASD-STE100"]
Q = ["correctness", "completeness"]; R = ["directness", "plain_language", "economy", "length"]
NO_WRITE = "Write Edit MultiEdit NotebookEdit Bash EnterPlanMode ExitPlanMode WebFetch WebSearch Agent"


def clean_env():
    return {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}


def claude_p(prompt, cwd, extra, timeout=900):
    cmd = ["claude", "-p", prompt, "--setting-sources", "local", "--output-format", "json",
           "--permission-mode", "default", "--allowedTools", "Read", "Glob", "Grep",
           "--disallowedTools", *NO_WRITE.split(), "--no-session-persistence", "--max-turns", "10", *extra]
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=clean_env())
        if not p.stdout.strip():
            return None, f"empty stdout rc={p.returncode} stderr={p.stderr[-400:]!r}"
        d = json.loads(p.stdout)
        if d.get("is_error"):
            return None, d.get("result", "")[:500]
        return d.get("result", ""), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (json.JSONDecodeError, Exception) as e:
        return None, f"{type(e).__name__}: {str(e)[:300]}"


def prose_metrics(text):
    p = re.sub(r"```.*?```", "", text, flags=re.S)
    p = "\n".join(l for l in p.splitlines() if not l.strip().startswith("|"))
    words = re.findall(r"\b\w[\w'-]*\b", p); W = max(len(words), 1)
    sents = [s for s in re.split(r"(?<=[.!?])\s+|\n+", p) if len(s.split()) >= 1]
    slen = [len(s.split()) for s in sents]
    return dict(words=W, emdash_per100=p.count("—") * 100 / W, long=sum(1 for n in slen if n > 25) / max(len(slen), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=2); ap.add_argument("--judges", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=3); ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--judge-model", default="claude-opus-5"); ap.add_argument("--prompts", default="")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    body = re.sub(r"^---\n.*?\n---\n", "", Path(a.style).read_text(), count=1, flags=re.S).strip() + "\n"
    (out / "style_body.txt").write_text(body)
    prompts = json.loads((HERE / "prompts.json").read_text())
    if a.prompts:
        keep = set(a.prompts.split(",")); prompts = [p for p in prompts if p["id"] in keep]
    brief = (HERE / "judge_brief.md").read_text()
    refs = {}
    for f in (HERE / "reference").glob("*.json"):
        r = json.loads(f.read_text()); refs[(r["style"], r["prompt_id"], r["run"])] = r["text"]

    # 1. candidate runs
    crashed = 0; cand = {}
    def run_cand(pid, prompt, run):
        text, err = claude_p(prompt, HERE, ["--append-system-prompt-file", str(out / "style_body.txt"), "--model", a.model])
        return pid, run, text, err
    with ThreadPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(run_cand, p["id"], p["prompt"], r) for p in prompts for r in range(1, a.runs + 1)]
        for f in as_completed(futs):
            pid, run, text, err = f.result()
            if text is None:
                crashed += 1; print(f"[crash] candidate {pid} r{run}: {err}", file=sys.stderr); continue
            cand[(pid, run)] = text
            (out / f"candidate__{pid}__r{run}.json").write_text(json.dumps({"prompt_id": pid, "run": run, "text": text}, indent=2))
            print(f"[cand] {pid} r{run} words={prose_metrics(text)['words']}", file=sys.stderr)

    # 2. packets + judging
    rng = random.Random(int(time.time()))
    ballots = []; failed_judges = 0
    def judge(pid, run, j):
        arms = {"candidate": cand[(pid, run)]}
        for s in REFS:
            t = refs.get((s, pid, run)) or refs.get((s, pid, 1))
            if t is None:
                return None, f"missing reference {s} {pid}"
            arms[s] = t
        order = list(arms); rng.shuffle(order); labels = "ABCD"; key = dict(zip(labels, order))
        prompt_text = next(p["prompt"] for p in prompts if p["id"] == pid)
        packet = [f"# Packet {pid}\n", "## The user's prompt\n", "```text\n" + prompt_text + "\n```\n"]
        for lab in labels: packet += [f"\n## Response {lab}\n", arms[key[lab]].strip(), "\n"]
        text, err = claude_p(brief + "\n\n" + "\n".join(packet), HERE, ["--model", a.judge_model])
        if text is None: return None, err
        try:
            v = json.loads(text[text.index("{"): text.rindex("}") + 1])
        except Exception as e:
            return None, f"unparseable verdict: {str(e)[:100]}"
        return {"pid": pid, "run": run, "judge": j, "key": key, "verdict": v}, None
    with ThreadPoolExecutor(a.jobs) as ex:
        futs = [ex.submit(judge, pid, run, j) for (pid, run) in sorted(cand) for j in range(1, a.judges + 1)]
        for f in as_completed(futs):
            b, err = f.result()
            if b is None:
                failed_judges += 1; print(f"[judge-fail] {err}", file=sys.stderr); continue
            ballots.append(b)
    (out / "ballots.json").write_text(json.dumps(ballots, indent=2))

    # 3. score the candidate
    comps = []; quals = []; reads = []; firsts = 0; cmin = 5
    for b in ballots:
        inv = {v: k for k, v in b["key"].items()}; lab = inv["candidate"]; sc = b["verdict"]["scores"][lab]
        q = sum(sc[c] for c in Q) / 2; r = sum(sc[c] for c in R) / 4
        comps.append(0.5 * q + 0.5 * r); quals.append(q); reads.append(r); cmin = min(cmin, sc["correctness"])
        firsts += (b["verdict"]["ranking"][0] == lab)
    pm = [prose_metrics(t) for t in cand.values()]
    n = max(len(ballots), 1)
    print("---")
    print(f"score:            {sum(comps)/n:.4f}")
    print(f"win_rate:         {firsts/n:.4f}")
    print(f"quality:          {sum(quals)/n:.4f}")
    print(f"readability:      {sum(reads)/n:.4f}")
    print(f"correctness_min:  {cmin}")
    print(f"words:            {sum(m['words'] for m in pm)/max(len(pm),1):.1f}")
    print(f"emdash_per100:    {sum(m['emdash_per100'] for m in pm)/max(len(pm),1):.2f}")
    print(f"long_sentences:   {sum(m['long'] for m in pm)/max(len(pm),1):.2f}")
    print(f"packets:          {len(cand)}")
    print(f"ballots:          {len(ballots)}")
    print(f"crashed_runs:     {crashed}")
    print(f"failed_judges:    {failed_judges}")
    sys.exit(2 if (crashed or failed_judges or not ballots) else 0)


if __name__ == "__main__":
    main()
