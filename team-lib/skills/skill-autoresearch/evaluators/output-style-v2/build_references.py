#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.0
# summary: Generate and freeze the reference transcripts for the output-style-v2 lineage — Concise
#   (built-in, via outputStyle) and ASD-STE100 (via appended style body) over every prompt in
#   prompts.json, N runs each, under the same read-only tool policy the evaluator uses. Run once;
#   the outputs are then part of the immutable evaluator.
# created: 2026-09-04
# last_updated: 2026-09-04
# maintainer: pvragon
# ---
import json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
HERE = Path(__file__).resolve().parent; SKILL = HERE.parent.parent
NO_WRITE = "Write Edit MultiEdit NotebookEdit Bash EnterPlanMode ExitPlanMode WebFetch WebSearch Agent".split()
STE_BODY = HERE / "ste_body.txt"


def run(prompt, extra, model):
    cmd = ["claude", "-p", prompt, "--setting-sources", "local", "--output-format", "json", "--permission-mode", "default",
           "--allowedTools", "Read", "Glob", "Grep", "--disallowedTools", *NO_WRITE, "--no-session-persistence", "--max-turns", "10", "--model", model, *extra]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=900, env=env)
    if not p.stdout.strip(): return None
    d = json.loads(p.stdout); return None if d.get("is_error") else d.get("result", "")


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 2; jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 3; model = "claude-opus-5"
    prompts = json.loads((HERE / "prompts.json").read_text())
    ste = Path.home() / "ai-workspace/my-lib/runtime/.tmp/260903-output-style-test/styles/asd-ste100.md"
    STE_BODY.write_text(re.sub(r"^---\n.*?\n---\n", "", ste.read_text(), count=1, flags=re.S).strip() + "\n")
    styles = {"Concise": ["--settings", json.dumps({"outputStyle": "Concise"})], "ASD-STE100": ["--append-system-prompt-file", str(STE_BODY)]}
    jobs_list = [(s, p, r) for s in styles for p in prompts for r in range(1, runs + 1) if not (HERE / "reference" / f"{s}__{p['id']}__r{r}.json").exists()]
    print(f"{len(jobs_list)} reference runs to do", flush=True)
    def one(s, p, r):
        return s, p["id"], r, run(p["prompt"], styles[s], model)
    fails = 0
    with ThreadPoolExecutor(jobs) as ex:
        for f in as_completed([ex.submit(one, *j) for j in jobs_list]):
            s, pid, r, text = f.result()
            if text is None: fails += 1; print(f"[fail] {s} {pid} r{r}", flush=True); continue
            (HERE / "reference" / f"{s}__{pid}__r{r}.json").write_text(json.dumps({"style": s, "prompt_id": pid, "run": r, "text": text}, indent=2))
            print(f"[done] {s} {pid} r{r}", flush=True)
    print(f"finished, {fails} failures", flush=True); sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
