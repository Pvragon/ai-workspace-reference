#!/usr/bin/env python3
# ---
# template: execution
# version: 1.1.0
# summary: Repair frontmatter blocks that are PRESENT but unparseable, by re-emitting them through
#          a YAML emitter so quoting is correct. Refuses anything it cannot round-trip verify.
#          Dry-run by default; --apply writes.
# created: 2026-08-08
# last_updated: 2026-08-08
# maintainer: pvragon
# known_limitations: >-
#   The WHOLE-BLOCK rewrite handles the flat `key: value` shape only; a block with top-level lists, nested
#   mappings or block scalars is REFUSED rather than rewritten — those need a human, and a
#   rewriter that guesses at structure would silently reshape meaning.
# ---
"""A broken frontmatter block is invisible, not loud, which is why they accumulate.

Measured in acme-health-main on 2026-08-08: 22 documents whose frontmatter no YAML parser can read.
Every one of them LOOKED fine — the block is there, the keys are there, `summary:` is there — and
the repo's own census counted all 22 as compliant because it matched the literal string `summary:`
rather than parsing. To any consumer doing yaml.safe_load, those files have no metadata at all.

Every instance was the same defect: **an unquoted plain scalar containing `: `**. YAML reads the
second colon as a nested mapping and gives up.

    summary: Aetna audit closed at 1,947 attributed. Next: run the classifier.
                                                          ^^^^^^ mapping values are not allowed here

The fix is not to hand-edit 22 files — it is to stop hand-writing the quoting. This reads the
block, reconstructs each key's value with plain-scalar folding semantics (continuation lines join
with a single space, which is what YAML would have done had it parsed), and re-emits through the
emitter, which quotes correctly by construction.

THE GUARANTEE, and why you can run this on documents you have not read:

  1. it only ever touches a block that does NOT currently parse — a healthy file is never rewritten
  2. it refuses any block it cannot reason about (top-level lists, nested maps, block scalars)
  3. the rewritten block must re-parse, and parse to exactly the dict that was reconstructed
  4. every original key must survive, in the original order
  5. each value must be preserved up to whitespace — compared with all whitespace removed, so a
     re-wrap is allowed and a dropped clause is not
  6. the document BODY below the frontmatter is copied byte-for-byte and never touched

Any file failing 2-6 is reported and skipped, never written. Dry-run is the default.

    python3 repair_frontmatter.py --repo DIR [path ...] [--apply] [--verbose]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_registry import read_frontmatter          # noqa: E402  one reader, not two

FM_BLOCK = re.compile(r"\A(---\r?\n)(.*?)(\r?\n---[ \t]*\r?\n?)", re.S)
# Scripts carry the same metadata as a `# ---` comment block, usually under a shebang. Same
# defect, same repair — and skipping them was not a decision, just an unexamined `.md` filter.
# Found when version_gate.py's OWN frontmatter turned out to be unparseable for exactly the
# reason this tool exists, and the tool could not reach it.
FM_BLOCK_PY = re.compile(r"\A((?:#![^\n]*\r?\n)?#[ \t]*---[ \t]*\r?\n)(.*?)"
                         r"(\r?\n#[ \t]*---[ \t]*\r?\n?)", re.S)
KEY_LINE = re.compile(r"^([A-Za-z_][\w.\-]*):(?:[ \t]+(.*))?$")

SKIP_DIRS = (".git", "archive", "node_modules", "_archive", "__pycache__")
SUFFIXES = (".md", ".py", ".sh")


def _block_of(path: Path, text: str):
    """(match, is_comment_form) for whichever frontmatter shape this file uses, or (None, False)."""
    if path.suffix in (".py", ".sh"):
        return FM_BLOCK_PY.match(text), True
    return FM_BLOCK.match(text), False


def _decomment(block: str) -> str | None:
    """Strip the leading `# ` from each line. None if a line is not commented at all."""
    out = []
    for ln in block.splitlines():
        if not ln.strip():
            out.append("")
            continue
        if not ln.lstrip().startswith("#"):
            return None
        out.append(re.sub(r"^#[ \t]?", "", ln, count=1))
    return "\n".join(out)


def _files_under(root: Path) -> list[Path]:
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        out += [Path(dp) / fn for fn in fns if fn.endswith(SUFFIXES)]
    return sorted(out)


_md_under = _files_under          # kept: the old name is used by callers/tests


def reconstruct(block: str) -> tuple[dict | None, str]:
    """(ordered {key: value}, reason-if-refused) from a block that does not parse.

    Plain-scalar folding: a continuation line belongs to the preceding key and joins with a single
    space. That is precisely what YAML does for a multi-line plain scalar, so reconstructing this
    way preserves the meaning the author intended — the block failed only because a `: ` inside
    the value made the parser read structure where there was prose.
    """
    entries: dict[str, str] = {}
    order: list[str] = []
    current: str | None = None
    # ⚑ A key with NO inline value followed by indented content is a nested mapping or a list, and
    # folding its children into a string would silently turn structure into prose. The first
    # version of this function did exactly that to `meta:\n  inner: a: b` and called it repaired;
    # its own self-check caught it. Track the shape rather than inferring from the folded result,
    # because after folding a flattened mapping is indistinguishable from a legitimate scalar.
    awaiting_value: str | None = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue                                  # blank lines carry no value in this shape
        stripped = line.lstrip()
        indented = line != stripped
        if not indented:
            if stripped.startswith("- "):
                return None, "top-level list — needs a human, not a rewriter"
            if stripped.startswith("#"):
                return None, "comment inside the block — a rewriter would drop it"
            m = KEY_LINE.match(line)
            if m:
                key, val = m.group(1), (m.group(2) or "")
                if val.strip() in (">", ">-", "|", "|-", ">+", "|+"):
                    return None, f"block scalar at `{key}:` — already explicit, leave it alone"
                if key in entries:
                    return None, f"duplicate key `{key}`"
                entries[key] = val.strip()
                order.append(key)
                current = key
                awaiting_value = None if val.strip() else key
                continue
            if current is None:
                return None, "content before the first key"
            if awaiting_value:
                return None, (f"`{awaiting_value}:` has no inline value and is followed by more "
                              f"content — a nested mapping or list, not a scalar")
            # an unindented continuation is legal for a plain scalar; keep folding
            entries[current] = (entries[current] + " " + stripped).strip()
            continue
        if current is None:
            return None, "indented content before the first key"
        if awaiting_value:
            return None, (f"`{awaiting_value}:` has no inline value and is followed by indented "
                          f"content — a nested mapping or list, not a scalar")
        # NOTE: an indented `- item` under a key that HAS an inline value is not a list — YAML
        # folds it into the scalar (`tags: something\n  - one` parses as `tags: "something - one"`).
        # A guard against it lived here briefly and was wrong twice over: unreachable in isolation,
        # and it would have refused a case where folding is the correct reading. Removed rather
        # than given a test, because a branch that cannot fire is worse than no branch.
        entries[current] = (entries[current] + " " + stripped).strip()
    if not entries:
        return None, "no keys found"
    if any(not v for v in entries.values()):
        empty = [k for k, v in entries.items() if not v]
        return None, f"empty value(s) for {empty} — likely a nested mapping, not a flat block"
    return {k: _value(entries[k]) for k in order}, ""


def _value(raw: str):
    """The value a healthy parser would have produced for this scalar, not its raw text.

    ⚑ A block usually breaks on ONE line; the others are already well-formed and must be read as
    YAML, not as text. Treating them as text corrupted two things, both caught by spot-checking
    five files before a bulk apply rather than by any assertion:

      * an ALREADY-QUOTED scalar — `summary: "Oklahoma rules (covers all states): (1) DISPATCH…"`
        was fine, the file broke on a later `status:` line. Reading it as text made the double
        quotes part of the content, so the repaired value literally began with a `"`.
      * a TYPED scalar — `created: 2026-05-06` is a date to YAML. Reading it as text and
        re-emitting would have quoted it into a string, silently changing its type.

    `verify()` cannot catch either: the damage happens during reconstruction, so the round-trip
    agrees with itself. Parse each value, and fall back to raw text only when parsing fails —
    which is precisely the `: `-in-a-plain-scalar case this tool exists to repair.
    """
    try:
        parsed = yaml.safe_load(f"__k__: {raw}")
    except yaml.YAMLError:
        return raw                                   # the defect being repaired: keep it literal
    if not isinstance(parsed, dict) or "__k__" not in parsed:
        return raw
    val = parsed["__k__"]
    # A FLOW container on the value line (`tags: [a, b]`, `meta: {x: y}`) is a value, not
    # structure, and preserving it as a list/dict is the faithful reading — demoting it to a
    # string was a third type change, found the same way as the other two. The dangerous shape,
    # multi-line BLOCK structure, never reaches here: `awaiting_value` refuses it upstream.
    return raw if val is None else val


def _norm(s: str) -> str:
    """Whitespace-insensitive content, so a re-wrap passes and a dropped clause does not."""
    return "".join(str(s).split())


def repair(path: Path) -> tuple[str, str]:
    """(status, detail). status in: ok-already, repaired, refused, no-frontmatter."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m, commented = _block_of(path, text)
    if not m:
        return "no-frontmatter", ""
    if isinstance(read_frontmatter(path), dict):
        return "ok-already", ""

    open_d, block, close_d = m.group(1), m.group(2), m.group(3)
    body = text[m.end():]

    if commented:
        block = _decomment(block)
        if block is None:
            return "refused", "comment block contains an uncommented line"

    data, why = reconstruct(block)
    if data is None:
        return "refused", why

    plain_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=96,
                                 default_flow_style=False).rstrip("\n")
    new_block = plain_block
    if commented:
        new_block = "\n".join(("# " + ln) if ln else "#" for ln in plain_block.split("\n"))
    candidate = open_d + new_block + close_d + body

    # verify against the PLAIN block — the commented form is not YAML, and handing it to the
    # verifier would make every script file fail the "does not parse" check for the wrong reason
    why = verify(data, plain_block, candidate, body)
    if why:
        return "refused", why
    return "repaired", candidate


def verify(data: dict, new_block: str, candidate: str, body: str) -> str:
    """The guarantee, as its own function so it can be tested WITHOUT a cooperating emitter.

    ⚑ These checks are a backstop against a rewrite that loses content — which means in normal
    operation they never fire, which means a test that only exercises the happy path cannot tell
    them from checks that were deleted. Measured: disabling the content and key-order checks left
    the suite fully green. They are called with hand-built mismatched inputs in --self-check now.
    Returns a reason, or "" when the rewrite is safe to write.
    """
    try:
        parsed = yaml.safe_load(new_block)
    except yaml.YAMLError as exc:
        return f"rewritten block still does not parse ({exc.__class__.__name__})"
    if not isinstance(parsed, dict):
        return "rewritten block is not a mapping"
    if list(parsed.keys()) != list(data.keys()):
        return "key set or order changed in the rewrite"
    for k in data:
        if _norm(parsed[k]) != _norm(data[k]):
            return f"value for `{k}` changed in the rewrite"
    if not candidate.endswith(body):
        return "document body would not be preserved"
    return ""


def repair_targeted(path: Path, max_fixes: int = 12) -> tuple[str, str]:
    """Fix ONLY the lines YAML actually chokes on, leaving every other byte alone.

    The whole-block rewrite above refuses any frontmatter it cannot model as a flat mapping —
    correctly, because folding a nested structure into prose destroys it. But that leaves the
    commonest real case unserved: a block with a legitimate nested `metadata:` mapping AND one
    broken flat line, which describes 17 of this agent's memory files.

    So this does the opposite of a rewrite. It asks the parser where it failed, converts THAT line
    from a plain scalar to a folded one (`key: >-` + the value indented beneath), and asks again.
    Nothing else is touched, which makes the guarantee much stronger than the rewrite's: every
    line except the ones named in the report is byte-identical, and the block parses at the end.

    Returns (status, new_text_or_reason) with status in: ok-already, repaired, refused.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    m, commented = _block_of(path, text)
    if not m:
        return "no-frontmatter", ""
    if isinstance(read_frontmatter(path), dict):
        return "ok-already", ""

    open_d, close_d, body = m.group(1), m.group(3), text[m.end():]
    lines = m.group(2).split("\n")
    pre = "# " if commented else ""
    fixed = []

    for _ in range(max_fixes):
        probe = "\n".join(_decomment("\n".join(lines)) .split("\n")) if commented \
            else "\n".join(lines)
        if probe is None:
            return "refused", "comment block contains an uncommented line"
        try:
            parsed = yaml.safe_load(probe)
            if isinstance(parsed, dict):
                new_block = "\n".join(lines)
                return "repaired", (open_d + new_block + close_d + body)
            return "refused", "frontmatter is not a mapping even after repair"
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            if mark is None or not (0 <= mark.line < len(lines)):
                return "refused", f"parser gave no line to act on ({getattr(exc,'problem',exc)})"
            i = mark.line
            # walk back to the key line owning this scalar
            while i >= 0:
                bare = re.sub(r"^#[ \t]?", "", lines[i]) if commented else lines[i]
                km = KEY_LINE.match(bare)
                if km and (km.group(2) or "").strip():
                    break
                i -= 1
            if i < 0 or i in fixed:
                return "refused", "could not localise the broken line"
            bare = re.sub(r"^#[ \t]?", "", lines[i]) if commented else lines[i]
            km = KEY_LINE.match(bare)
            key, val = km.group(1), (km.group(2) or "").strip()
            if val in (">", ">-", "|", "|-"):
                return "refused", f"`{key}:` is already a block scalar"
            lines[i] = f"{pre}{key}: >-"
            lines.insert(i + 1, f"{pre}  {val}")
            fixed.append(i)
    return "refused", f"still unparseable after {max_fixes} targeted fixes"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Repair unparseable frontmatter blocks.")
    ap.add_argument("paths", nargs="*", help="files to repair; default: every .md under --repo")
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()

    repo = Path(a.repo).resolve()
    targets = [Path(p) for p in a.paths] if a.paths else _md_under(repo)

    repaired, refused, seen = [], [], 0
    for p in targets:
        status, detail = repair(p)
        if status in ("ok-already", "no-frontmatter"):
            continue
        seen += 1
        rel = os.path.relpath(p, repo)
        if status == "refused":
            refused.append((rel, detail))
            continue
        repaired.append((rel, detail))
        if a.apply:
            p.write_text(detail, encoding="utf-8")

    print(f"{seen} file(s) with unparseable frontmatter")
    print(f"  {len(repaired):>4}  {'REPAIRED' if a.apply else 'repairable (dry run)'}")
    print(f"  {len(refused):>4}  refused — a rewriter must not guess at these")
    for rel, _ in repaired if a.verbose or not a.apply else []:
        print(f"      + {rel}")
    for rel, why in refused:
        print(f"      ! {rel}\n          {why}")
    if repaired and not a.apply:
        print("\n  re-run with --apply to write.")
    return 0 if not refused else 1


def self_check() -> int:
    """Two-sided: the defect class must be repaired, and every unsafe shape must be REFUSED."""
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)

        def mk(name: str, fm: str, body: str = "\n# Title\n\nprose here\n") -> Path:
            p = d / name
            p.write_text(f"---\n{fm}\n---\n{body}", encoding="utf-8")
            return p

        # 1. the real defect class: `: ` inside an unquoted scalar
        p = mk("colon.md", "template: doc\nversion: 1.0.0\n"
                           "summary: Closed at 1,947. Next: run the classifier.")
        status, out = repair(p)
        if status != "repaired":
            print(f"FAIL: the `: ` defect was not repaired ({status}: {out})"); ok = False
        else:
            p.write_text(out, encoding="utf-8")
            fm = read_frontmatter(p)
            if not isinstance(fm, dict):
                print("FAIL: repaired file still does not parse"); ok = False
            elif fm.get("summary") != "Closed at 1,947. Next: run the classifier.":
                print(f"FAIL: value not preserved: {fm.get('summary')!r}"); ok = False
            elif "# Title" not in p.read_text():
                print("FAIL: document body was lost"); ok = False

        # 2. multi-line plain scalar folds with single spaces, content intact
        p = mk("multi.md", "summary: First part here\n  and a continuation: with a colon\n"
                           "version: 2.0.0")
        status, out = repair(p)
        if status != "repaired":
            print(f"FAIL: multi-line scalar not repaired ({status}: {out})"); ok = False
        else:
            got = yaml.safe_load(FM_BLOCK.match(out).group(2))
            if got.get("summary") != "First part here and a continuation: with a colon":
                print(f"FAIL: folding wrong: {got.get('summary')!r}"); ok = False
            if list(got) != ["summary", "version"]:
                print(f"FAIL: key order not preserved: {list(got)}"); ok = False

        # 2b. an already-quoted scalar must keep its CONTENT, not gain its quote characters, and a
        #     typed scalar must keep its type. The block below breaks only on `status:`.
        p = mk("quoted.md", 'summary: "Rules (all states): (1) DISPATCH"\n'
                            "created: 2026-05-06\n"
                            "status: active — open item: mileage")
        status, out = repair(p)
        if status != "repaired":
            print(f"FAIL: mixed quoted/typed block not repaired ({status}: {out})"); ok = False
        else:
            got = yaml.safe_load(FM_BLOCK.match(out).group(2))
            if got.get("summary") != "Rules (all states): (1) DISPATCH":
                print(f"FAIL: quoted scalar corrupted: {got.get('summary')!r}"); ok = False
            if str(got.get("created")) != "2026-05-06":
                print(f"FAIL: typed scalar not preserved: {got.get('created')!r}"); ok = False
            if got.get("status") != "active — open item: mileage":
                print(f"FAIL: the broken scalar was not repaired: {got.get('status')!r}"); ok = False

        # 2c. a FLOW list on the value line stays a list
        p = mk("flow.md", "tags: [alpha, beta]\nstatus: active — open item: mileage")
        status, out = repair(p)
        if status != "repaired":
            print(f"FAIL: flow-list block not repaired ({status}: {out})"); ok = False
        else:
            got = yaml.safe_load(FM_BLOCK.match(out).group(2))
            if got.get("tags") != ["alpha", "beta"]:
                print(f"FAIL: flow list not preserved as a list: {got.get('tags')!r}"); ok = False

        # 2d. the `# ---` script form: same defect, same repair, and the file must stay valid
        #     Python. version_gate.py's own frontmatter was broken this way, and this tool could
        #     not reach it because the walk filtered to .md.
        py = d / "script.py"
        py.write_text("#!/usr/bin/env python3\n# ---\n# template: execution\n# version: 1.0.0\n"
                      "# summary: Does a thing. Next: another thing.\n# ---\n"
                      'import os\nprint("body")\n', encoding="utf-8")
        status, out = repair(py)
        if status != "repaired":
            print(f"FAIL: script-form frontmatter not repaired ({status}: {out})"); ok = False
        else:
            py.write_text(out, encoding="utf-8")
            fm = read_frontmatter(py)
            if not isinstance(fm, dict):
                print(f"FAIL: repaired script still does not parse ({fm})"); ok = False
            elif fm.get("summary") != "Does a thing. Next: another thing.":
                print(f"FAIL: script summary not preserved: {fm.get('summary')!r}"); ok = False
            else:
                import ast as _ast
                try:
                    _ast.parse(py.read_text(encoding="utf-8"))
                except SyntaxError as exc:
                    print(f"FAIL: repaired script is not valid Python ({exc})"); ok = False
                if 'print("body")' not in py.read_text(encoding="utf-8"):
                    print("FAIL: script body was lost"); ok = False

        # 3. a HEALTHY file must never be touched
        p = mk("fine.md", "template: doc\nsummary: nothing wrong here\nversion: 1.0.0")
        before = p.read_text()
        status, _ = repair(p)
        if status != "ok-already":
            print(f"FAIL: a healthy file was not left alone ({status})"); ok = False
        if p.read_text() != before:
            print("FAIL: a healthy file was modified"); ok = False

        # 4-6. shapes a rewriter must REFUSE rather than guess at
        for name, fm, label in [
            ("list.md", "tags:\n  - one: two\n  - three", "list value"),
            ("toplist.md", "- one: two\n- three: four", "top-level list"),
            ("block.md", "summary: >\n  folded: text\nbad: a: b", "block scalar"),
            ("nested.md", "meta:\n  inner: a: b", "nested mapping"),
            # a duplicate key silently drops the first value, and verify() cannot see it: the loss
            # happens during reconstruction, so `data` is already missing it and the round-trip
            # agrees with itself. This refusal is the ONLY thing guarding it.
            ("dup.md", "summary: Next: colon\nsummary: a second one", "duplicate key"),
        ]:
            p = mk(name, fm)
            if isinstance(read_frontmatter(p), dict):
                continue                     # it parsed after all; not a case for this tool
            status, why = repair(p)
            if status != "refused":
                print(f"FAIL: {label} was not refused (got {status})"); ok = False

        # 7. a list AFTER a valid key — only the list guard can catch this one. Without it the
        #    item folds into the preceding scalar and the file is "repaired" into prose.
        p = mk("listafter.md", "summary: text here\n- item: two")
        if not isinstance(read_frontmatter(p), dict):
            status, why = repair(p)
            if status != "refused":
                print(f"FAIL: a list after a key was not refused (got {status})"); ok = False

        # 8-10. THE GUARANTEE ITSELF, called with mismatched inputs. These branches never fire on
        #    a cooperating emitter, so without this the checks could be deleted with the suite
        #    staying green — which is exactly what mutation testing showed on 2026-08-08.
        if verify({"a": "one"}, "a: one", "---\na: one\n---\nbody", "body"):
            print("FAIL: verify() rejected a sound rewrite"); ok = False
        if not verify({"a": "one"}, "a: DIFFERENT", "---\na: DIFFERENT\n---\nbody", "body"):
            print("FAIL: verify() accepted a rewrite that changed a value"); ok = False
        if not verify({"a": "one", "b": "two"}, "b: two\na: one",
                      "---\nb: two\na: one\n---\nbody", "body"):
            print("FAIL: verify() accepted a rewrite that reordered keys"); ok = False
        if not verify({"a": "one"}, "a: one", "---\na: one\n---\nTRUNCATED", "body"):
            print("FAIL: verify() accepted a rewrite that dropped the body"); ok = False
        if not verify({"a": "one"}, "a: [unclosed", "x", "body"):
            print("FAIL: verify() accepted a block that does not parse"); ok = False
    print("self-check: PASS" if ok else "self-check: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
