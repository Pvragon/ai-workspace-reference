#!/usr/bin/env python3
# ---
# template: execution
# version: 1.2.0
# summary: "Checks a draft team post (ClickUp comment, channel post, PR comment) against the team-post skill: rendered length cap, first line is an outcome, paragraphs of at most three sentences, a sentence limit per post, no bare identifiers, no em dashes, no headings, few bold labels, no self-narration. Exit 1 on any hard failure. --judge adds one claude -p turn with the humanizer skill and supplement loaded."
# created: 2026-09-22
# last_updated: 2026-10-02
# maintainer: pvragon
# ---
"""
Check a draft team post before it is posted.

CLI:
    python3 check_team_post.py draft.md --kind comment
    python3 check_team_post.py draft.md --kind channel --judge
    echo "text" | python3 check_team_post.py - --kind comment --json

Import:
    from check_team_post import run
    result = run(text, kind="comment")          # dict: ok, fails, warns, stats
    result = run(text, kind="channel", judge=True)

Hard rules (FAIL, exit 1):
    length      rendered text over the cap for the kind (comment 600, channel 900)
    paragraph   a paragraph (blank-line separated block, list blocks excluded) over 3 sentences
    sentences   more than 6 sentences outside lists (comment) or 9 (channel); a list has
                at most 6 items
    first-line  first line is empty, a heading, a label ending in ":", a greeting only,
                a mention list only, or an opening sentence over 220 characters
    identifier  a ticket id, commit hash, PR number, path or code name in a sentence
                with fewer than five other words
    em-dash     any em dash
    heading     any markdown heading
    bold-labels more than two lines opening with a bold label
    table       any markdown table

Soft rules (WARN, still exit 0):
    narration   phrases about the writer's own process
    lines       more than 10 lines (comment) or 14 (channel)
    sentence    a sentence over 30 words

Rendering: mentions become "@Name", links and images become their visible text, code marks and
emphasis marks are removed. Length and every rule are measured on that rendered text.
"""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

CAPS = {"comment": 600, "channel": 900}
SENTENCES_MAX = {"comment": 6, "channel": 9}
PARAGRAPH_SENTENCES_MAX = 3
LIST_ITEMS_MAX = 6
LINE_SOFT = {"comment": 10, "channel": 14}
FIRST_LINE_MAX = 220
SENTENCE_WORDS_MAX = 30

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]            # team-lib/skills/team-post/scripts -> ai-workspace
HUMANIZER_SKILL = WORKSPACE / "team-lib/skills/_external/blader-humanizer/SKILL.md"
SUPPLEMENT = WORKSPACE / "team-lib/skills/humanizer-supplement/SKILL.md"
SKILL = HERE.parent / "SKILL.md"

GREETING = re.compile(r"^(hey|hi|hello|good (morning|afternoon|evening)|team|folks|all)\b[\w\s,@.!]*$", re.I)
IDENT_PATTERNS = [
    re.compile(r"\b868[a-z0-9]{6}\b"),                    # ClickUp task id
    re.compile(r"\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"),   # git hash
    re.compile(r"(?<![\w/])#\d{2,5}\b"),                   # PR / issue number
    re.compile(r"\b[\w.-]+/[\w.-]+\.(?:ts|tsx|js|py|sql|md|json)\b"),        # file path
    re.compile(r"\b[a-z][A-Za-z0-9]+\(\)"),                # function call name
    re.compile(r"\b[a-z]+_[a-z_]+\b"),                     # snake_case column / table
]
NARRATION = [
    r"\bI (read|checked|pulled|ran|re-ran|went through|verified|investigated|traced|looked at)\b",
    r"\bstatic code read\b",
    r"\bnot an incident reconstruction\b",
    r"\bthis is a (text )?write-?up\b",
    r"\bcan'?t be exported\b",
    r"\bfor context,",
    r"\bas requested\b",
    r"\bhere'?s? (is )?(a|an|the|my) (quick )?(update|summary|breakdown|rundown|report)\b",
    r"\bquick (update|note)\b",
    r"\bstatus check by\b",
    r"\bjust wanted to\b",
    r"\bworth noting\b",
    r"\bto be clear\b",
    r"[—–-]\s*🤖",
]


def render(text):
    """Reduce ClickUp / markdown markup to the words a reader sees."""
    s = text.replace("\r\n", "\n")
    s = re.sub(r"\[@([^\]]+)\]\(#[^)]*\)", r"@\1", s)               # ClickUp mention
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                       # image
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)                   # link -> text
    s = re.sub(r"<[^>]+>", " ", s)                                   # html tags
    s = re.sub(r"`([^`]*)`", r"\1", s)                               # code marks
    s = s.replace("\\.", ".").replace("\\*", "*").replace("\\[", "[").replace("\\]", "]")
    lines = []
    for ln in s.split("\n"):
        ln = ln.strip()
        if ln in ("* * *", "---", "***"):
            continue
        if ln == "" and (not lines or lines[-1] == ""):
            continue                                                 # collapse blank runs
        lines.append(ln)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


LIST_ITEM = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")


def blocks(rendered):
    """Blocks as (kind, lines): kind is 'list' or 'para'. A blank line ends a block, and so does
    the switch between list-item lines and prose lines, so an intro line directly above a list
    is its own paragraph."""
    out, cur, cur_kind = [], [], None
    for ln in rendered.split("\n") + [""]:
        kind = None if ln == "" else ("list" if LIST_ITEM.match(ln) else "para")
        if kind != cur_kind and cur:
            out.append((cur_kind, cur)); cur = []
        if kind is not None:
            cur.append(ln)
        cur_kind = kind
    return out


def strip_marks(line):
    line = re.sub(r"^\s*#{1,6}\s*", "", line)
    line = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", line)
    line = re.sub(r"\*\*|__", "", line)
    line = re.sub(r"(?<!\w)[*_](?!\s)|(?<!\s)[*_](?!\w)", "", line)
    return line.strip()


def sentences(text):
    plain = "\n".join(strip_marks(l) for l in text.split("\n"))
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", plain) if x.strip()]


# The agent signature required by identity.md ("— Sent by Your Agent 🤖" in the
# operator's voice, "— Your Agent 🤖" in the agent's own). Exempt from the em-dash and
# flourish checks when it is the final line (the operator's ruling, 2026-10-02).
SIGNATURE = re.compile(r"\n?[ \t]*— (Sent by )?[\w .'-]+ 🤖[ \t]*\s*\Z")


def check(text, kind="comment"):
    fails, warns = [], []
    text = SIGNATURE.sub("", text)
    rendered = render(text)
    lines = [l for l in rendered.split("\n") if l != ""] if rendered else []
    plain_lines = [strip_marks(l) for l in lines]
    plain = "\n".join(plain_lines)
    n = len(plain)
    cap = CAPS[kind]
    blks = blocks(rendered)
    prose_sentences = [x for k, ls in blks if k == "para" for x in sentences("\n".join(ls))]
    list_items = sum(len(ls) for k, ls in blks if k == "list")
    stats = {"kind": kind, "chars": n, "cap": cap, "lines": len(lines), "paragraphs": sum(1 for k, _ in blks if k == "para"),
             "sentences": len(prose_sentences), "list_items": list_items}

    if n > cap:
        fails.append(f"length: {n} rendered characters, cap for a {kind} is {cap}. "
                     f"Move the detail to the ticket body, a doc or the PR and link it.")

    for k, ls in blks:
        if k == "para":
            c = len(sentences("\n".join(ls)))
            if c > PARAGRAPH_SENTENCES_MAX:
                fails.append(f"paragraph: {c} sentences in one paragraph, max {PARAGRAPH_SENTENCES_MAX}: "
                             f"{strip_marks(ls[0])[:70]!r}... Break it, or make the parallel items a list.")
        elif len(ls) > LIST_ITEMS_MAX:
            fails.append(f"list: {len(ls)} items, max {LIST_ITEMS_MAX}. The rest belongs in the linked place.")
    if len(prose_sentences) > SENTENCES_MAX[kind]:
        fails.append(f"sentences: {len(prose_sentences)} sentences outside lists, max {SENTENCES_MAX[kind]} for a {kind}.")

    first = plain_lines[0] if plain_lines else ""
    raw_first = lines[0] if lines else ""
    if not first:
        fails.append("first-line: the post is empty.")
    else:
        if re.match(r"^\s*#{1,6}\s", raw_first):
            fails.append(f"first-line: opens with a heading: {first[:80]!r}. The first line is the outcome.")
        elif first.endswith(":"):
            fails.append(f"first-line: ends with a colon, so it introduces a list instead of stating the outcome: {first[:80]!r}.")
        elif GREETING.match(first) and not re.search(r"[.!?]\s+\S", first):
            fails.append(f"first-line: greeting only: {first[:80]!r}. Greet if you like, then put the outcome on the same line.")
        elif re.fullmatch(r"(@[\w .'-]+[,\s]*)+(and\s+)?", first):
            fails.append("first-line: mentions only. Put the outcome on the first line with them.")
        else:
            first_sentence = sentences(first)[0] if sentences(first) else first
            if len(first_sentence) > FIRST_LINE_MAX:
                fails.append(f"first-line: the opening sentence is {len(first_sentence)} characters. "
                             f"One outcome sentence, under {FIRST_LINE_MAX}.")

    if "—" in rendered:
        fails.append(f"em-dash: {rendered.count('—')} em dash(es). Use a comma, a period or a colon.")

    heads = [l for l in lines if re.match(r"^\s*#{1,6}\s", l)]
    if heads:
        fails.append(f"heading: {len(heads)} markdown heading(s). A post has no sections; a thing with sections is a document.")

    bold_labels = [l for l in lines if re.match(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?\*\*[^*]{1,60}\*\*", l)]
    if len(bold_labels) > 2:
        fails.append(f"bold-labels: {len(bold_labels)} lines open with a bold label. Write sentences.")

    if any(re.match(r"^\s*\|.*\|\s*$", l) for l in lines):
        fails.append("table: markdown table in a post. Put it in the ticket body or a doc and link it.")

    # bare identifiers: an identifier in a sentence with fewer than five other words
    seen = set()
    for s in sentences(rendered):
        idents = []
        for pat in IDENT_PATTERNS:
            idents += pat.findall(s)
        if not idents:
            continue
        rest = s
        for i in idents:
            rest = rest.replace(i, " ")
        words = [w for w in re.findall(r"[A-Za-z]{2,}", rest)]
        if len(words) < 5:
            key = s[:60]
            if key not in seen:
                seen.add(key)
                fails.append(f"identifier: {', '.join(dict.fromkeys(idents))} with no words around it: {s[:90]!r}. Say what it is.")

    for pat in NARRATION:
        m = re.search(pat, rendered, re.I)
        if m:
            warns.append(f"narration: {m.group(0)!r}. Say what is true and what to do, not how you got there.")

    if len(lines) > LINE_SOFT[kind]:
        warns.append(f"lines: {len(lines)} lines; a {kind} rarely needs more than {LINE_SOFT[kind]}.")
    for s in sentences(rendered):
        w = len(s.split())
        if w > SENTENCE_WORDS_MAX:
            warns.append(f"sentence: {w} words: {s[:70]!r}...")

    return {"ok": not fails, "fails": fails, "warns": warns, "stats": stats, "rendered": rendered}


JUDGE_SYSTEM = ("You are a copy reviewer for a short message a teammate will read. You read reference material "
                "and one draft, and you answer with STRICT JSON only, no prose, no markdown fences.")
JUDGE_INSTRUCTION = """
=== YOUR TASK ===

Above are three references and one DRAFT. Check every sentence of the DRAFT against:
  (a) the humanizer skill: vocabulary and construction tells of machine writing;
  (b) the supplement: is the sentence about the subject, or about the document or the writer's process;
  (c) the team-post rules: first line is the outcome; every identifier named at first use; nothing
      about the writer's own process; a caveat only where it changes what the reader does.

Flag only real instances you can quote verbatim from the DRAFT. Do not flag style preferences.
Return exactly: {"findings":[{"quote":"<verbatim>","rule":"humanizer:<pattern>|stance:<S1-S3>|post:<rule>","why":"<one line>","rewrite":"<replacement or empty string to cut>"}]}
If the draft is clean return {"findings":[]}.
"""


def judge(text, model="sonnet", timeout=180):
    for p in (HUMANIZER_SKILL, SUPPLEMENT, SKILL):
        if not p.exists():
            return {"error": f"missing reference {p}"}
    prompt = (f"=== REFERENCE 1: HUMANIZER SKILL ===\n{HUMANIZER_SKILL.read_text()}\n\n"
              f"=== REFERENCE 2: HUMANIZER SUPPLEMENT ===\n{SUPPLEMENT.read_text()}\n\n"
              f"=== REFERENCE 3: TEAM-POST RULES ===\n{SKILL.read_text()}\n\n"
              f"=== DRAFT ===\n{render(text)}\n\n{JUDGE_INSTRUCTION}")
    cmd = ["claude", "-p", "--output-format", "json", "--model", model,
           "--tools", "", "--setting-sources", "", "--system-prompt", JUDGE_SYSTEM]
    t0 = datetime.datetime.now()
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"error": "`claude` is not on PATH"}
    except subprocess.TimeoutExpired:
        return {"error": f"judge timed out after {timeout}s"}
    secs = (datetime.datetime.now() - t0).total_seconds()
    if r.returncode != 0:
        return {"error": f"claude exited {r.returncode}: {(r.stderr or r.stdout)[:400]}"}
    try:
        body = json.loads(r.stdout)["result"]
        m = re.search(r"\{.*\}", body, re.S)
        findings = json.loads(m.group(0)).get("findings", []) if m else []
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not parse judge output: {e}: {r.stdout[:400]}"}
    return {"findings": findings, "seconds": round(secs, 1), "model": model}


def run(text, kind="comment", judge_draft=False, model="sonnet"):
    result = check(text, kind)
    if judge_draft:
        j = judge(text, model)
        result["judge"] = j
        if "error" in j:
            result["ok"] = False
            result["fails"].append(f"judge: could not run ({j['error']}). A check that silently passes measures nothing.")
        elif j["findings"]:
            result["ok"] = False
            for f in j["findings"]:
                result["fails"].append(f"judge {f.get('rule','')}: {f.get('quote','')[:90]!r}. {f.get('why','')}"
                                       + (f" Rewrite: {f['rewrite']!r}" if f.get("rewrite") else " Cut it."))
    return result


def main():
    ap = argparse.ArgumentParser(description="Check a draft team post against the team-post skill.")
    ap.add_argument("draft", help="path to the draft, or - for stdin")
    ap.add_argument("--kind", choices=CAPS, default="comment")
    ap.add_argument("--judge", action="store_true", help="also run one claude -p turn with the humanizer references")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = sys.stdin.read() if a.draft == "-" else pathlib.Path(a.draft).read_text()
    res = run(text, a.kind, a.judge, a.model)
    if a.json:
        print(json.dumps({k: v for k, v in res.items() if k != "rendered"}, indent=2))
    else:
        st = res["stats"]
        print(f"{'PASS' if res['ok'] else 'FAIL'}  {st['kind']}  {st['chars']}/{st['cap']} chars  "
              f"{st['paragraphs']} paragraphs  {st['sentences']} sentences  {st['list_items']} list items")
        for f in res["fails"]:
            print(f"  FAIL  {f}")
        for w in res["warns"]:
            print(f"  warn  {w}")
        if res.get("judge", {}).get("seconds") is not None:
            print(f"  judge ran in {res['judge']['seconds']}s on {res['judge']['model']}")
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
