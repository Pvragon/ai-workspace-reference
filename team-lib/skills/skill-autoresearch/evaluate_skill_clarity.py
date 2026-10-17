#!/usr/bin/env python3
# ---
# template: execution
# version: 2.0.1
# summary: Immutable evaluator for the skill-clarity autoresearch program. Spins up a throwaway git
#   worktree of the target repo, runs one claude -p executor that follows the target skill against
#   a fixed test brief and reports per-step clarity as JSON, then prints a Karpathy-style summary
#   whose "clarity:" line is the metric. The report is also written outside the worktree so a lost
#   return never loses the iteration.
# created: 2026-09-04
# last_updated: 2026-09-04
# maintainer: pvragon
# ---
"""
Usage
  evaluate_skill_clarity.py --repo DIR --skill PATH/TO/SKILL.md --brief PATH --out DIR [--mode create] [--model claude-opus-5]

Prints, at the end:
  ---
  clarity:          8.4000   mean per-step clarity, 1-10, higher is better
  min_step:         7        lowest step clarity
  steps:            9
  completed:        1        1 = executor finished end to end, 0 = it did not
  blocking_steps:   0        steps scored below 7
  issues:           3        count of issues the executor listed
Extract the metric with:  grep "^clarity:" run.log
Exit code 2 if the executor produced no parseable report (a crash in Karpathy's sense).

The executor runs inside a fresh git worktree of --repo on a detached HEAD so nothing it creates
touches the working tree; the worktree is removed afterwards. The executor may read, write and
run scripts inside the worktree only.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from pathlib import Path

TEMPLATE = """You are a test executor for one iteration of an autoresearch loop. Follow the skill
procedure EXACTLY as written. Read every file fresh; do not assume you know its contents.

1. Read the skill at {skill}
2. Read any templates, scripts or reference files it points at.
3. Read the test brief at {brief}. It stands in for the user: it holds the source materials and
   says how to answer when the skill asks the user something.
4. Follow the procedure step by step in "{mode}" mode, through every step including validation
   and output generation. Work only inside {worktree}.

While you work, rate EACH step of the skill's procedure for clarity, 1 to 10: was the instruction
unambiguous, did you have to guess, did a template or script contradict it, did the skill say what
to do on a non-zero exit code.

MANDATORY FINAL STEP: write the report below to {report} (absolute path, outside your working
directory) BEFORE you finish. Then reply with the same JSON and nothing else.

{{
  "completed": true or false,
  "steps": [{{"step": 1, "title": "...", "clarity": 8, "issue": "one sentence, or empty"}}, ...],
  "issues": ["template issue ...", "script issue ...", "procedure gap ..."],
  "worked_well": ["..."],
  "suggestions": ["..."]
}}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True); ap.add_argument("--skill", required=True); ap.add_argument("--brief", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--mode", default="create"); ap.add_argument("--model", default="claude-opus-5")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    report = out / "executor_report.json"
    wt = Path(tempfile.mkdtemp(prefix="autoresearch-wt-", dir=str(out)))
    subprocess.run(["git", "-C", a.repo, "worktree", "add", "--detach", str(wt), "HEAD"], check=True, capture_output=True)
    try:
        skill = str(Path(a.skill).resolve()); brief = str(Path(a.brief).resolve())
        # the executor reads the skill from the worktree copy if the skill lives in the repo
        rel = os.path.relpath(skill, Path(a.repo).resolve())
        if not rel.startswith(".."):
            skill = str(wt / rel)
        prompt = TEMPLATE.format(skill=skill, brief=brief, mode=a.mode, worktree=wt, report=report)
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        # the brief and the report live outside the worktree; grant both directories explicitly
        extra_dirs = sorted({str(out), str(Path(brief).parent)})
        cmd = ["claude", "-p", prompt, "--setting-sources", "local", "--output-format", "json", "--permission-mode", "acceptEdits",
               "--no-session-persistence", "--max-turns", "80", "--model", a.model]
        for d in extra_dirs:
            cmd += ["--add-dir", d]
        p = subprocess.run(cmd, cwd=wt, capture_output=True, text=True, timeout=3600, env=env)
        (out / "executor_stdout.json").write_text(p.stdout)
        data = None
        if report.exists():
            try: data = json.loads(report.read_text())
            except json.JSONDecodeError: data = None
        if data is None:
            try:
                res = json.loads(p.stdout).get("result", "")
                data = json.loads(res[res.index("{"): res.rindex("}") + 1])
            except Exception:
                data = None
    finally:
        subprocess.run(["git", "-C", a.repo, "worktree", "remove", "--force", str(wt)], capture_output=True)
    print("---")
    if not data or not data.get("steps"):
        print("clarity:          0.0000"); print("completed:        0"); print("crash:            no parseable executor report"); sys.exit(2)
    sc = [int(s["clarity"]) for s in data["steps"]]
    print(f"clarity:          {sum(sc)/len(sc):.4f}")
    print(f"min_step:         {min(sc)}")
    print(f"steps:            {len(sc)}")
    print(f"completed:        {1 if data.get('completed') else 0}")
    print(f"blocking_steps:   {sum(1 for s in sc if s < 7)}")
    print(f"issues:           {len(data.get('issues') or [])}")


if __name__ == "__main__":
    main()
