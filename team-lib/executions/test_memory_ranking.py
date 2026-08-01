#!/usr/bin/env python3
# ---
# template: execution
# version: 1.0.1
# summary: "Regression tests for the memory ranking pipeline (rerank_memory_index.py + update_memory_access.py), run against a SYNTHETIC fixture corpus in a temp dir — never the live corpus. Pins the invariants the design actually claims: determinism, total tie-break ordering, budget caps, curated summaries surviving regeneration (including rows sitting in the archive), nothing lost, born-visible, the spacing gate, malformed frontmatter degrading to defaults, and pin/superseded overriding score. Runs under pytest or standalone."
# created: 2026-07-30
# last_updated: 2026-08-01
# maintainer: the-operator
# ---
"""
test_memory_ranking.py — property tests for the memory ranking pipeline.

Run:  pytest executions/test_memory_ranking.py -q
  or: python3 executions/test_memory_ranking.py

Every test builds a fresh synthetic corpus in a temp dir and points
PVRAGON_AGENT_HOME at it, so the live memory corpus is never touched or read.
That isolation is the point: this suite exists to make the ranking code safe to
change, and a test that reads live state cannot do that.

WHY THIS EXISTS
  memory_self_check.py tests corpus CONTENT. verify_memory_install.py tests the
  WIRING. Neither tests whether the ranking is still CORRECT — and the reranker
  is the one component that can destroy data, by regenerating an index whose
  hand-curated summaries exist nowhere else.
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# MEMORY_EXEC_DIR points the suite at a DIFFERENT copy of the scripts. That exists so the
# tests can be run against a previous revision to confirm they actually fail on the bug they
# claim to catch — a suite that has only ever passed is evidence of nothing.
EXEC_DIR = Path(os.environ.get("MEMORY_EXEC_DIR") or Path(__file__).resolve().parent)
RERANK = EXEC_DIR / "rerank_memory_index.py"
ACCESS = EXEC_DIR / "update_memory_access.py"


# --------------------------------------------------------------------------
# fixture construction
# --------------------------------------------------------------------------

def iso(days_ago: float) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def day(days_ago: float) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


def mem(name, *, summary="", description="", access=0, last=30.0, stability=14.0,
        created=None, pin=None, status=None, importance=None, body="body text"):
    """Render one synthetic memory file."""
    fm = [f"name: {name}"]
    if description:
        fm.append(f'description: "{description}"')
    if summary:
        fm.append(f'summary: "{summary}"')
    fm.append(f"access_count: {access}")
    fm.append(f"last_accessed: {iso(last)}")
    fm.append(f"stability: {stability}")
    if created is not None:
        fm.append(f"created: {day(created)}")
    if pin is not None:
        fm.append(f"pin: {str(pin).lower()}")
    if status is not None:
        fm.append(f"status: {status}")
    if importance is not None:
        fm.append(f"importance: {importance}")
    return "---\n" + "\n".join(fm) + "\n---\n\n" + body + "\n"


class Corpus:
    """A throwaway agent home with a memory dir, plus helpers to run the tools."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.mem = self.home / "memory"
        self.mem.mkdir()
        (self.home / "identity.md").write_text("name: fixture\n")
        (self.mem / "short-term").mkdir()

    def add(self, filename, content):
        (self.mem / filename).write_text(content, encoding="utf-8")
        return self

    def env(self):
        e = dict(os.environ)
        e["PVRAGON_AGENT_HOME"] = str(self.home)
        e.pop("PVRAGON_AGENT", None)
        return e

    def rerank(self):
        r = subprocess.run([sys.executable, str(RERANK)], capture_output=True,
                           text=True, env=self.env())
        assert r.returncode == 0, f"rerank failed: {r.stderr}"
        return r.stdout

    def read_index(self):
        return (self.mem / "MEMORY.md").read_text(encoding="utf-8")

    def read_archive(self):
        return (self.mem / "MEMORY-archive.md").read_text(encoding="utf-8")

    def touch(self, filename, tool="Read"):
        """Simulate the PreToolUse hook firing on a Read of this memory."""
        payload = {"tool_name": tool,
                   "tool_input": {"file_path": str(self.mem / filename)}}
        subprocess.run([sys.executable, str(ACCESS)], input=json.dumps(payload),
                       capture_output=True, text=True, env=self.env())

    def bands(self):
        """filename -> band, parsed out of the generated index."""
        md, arch = self.read_index(), self.read_archive()
        inew, icold = md.find("## New ("), md.find("## Cold (")
        if inew == -1:
            inew = icold
        out = {}
        for band, text in (("hot", md[:inew]), ("new", md[inew:icold]),
                           ("cold", md[icold:]), ("archive", arch)):
            for m in re.finditer(r"^\| `([^`]+\.md)` \| (.*?) \|?\s*$", text, re.M):
                out.setdefault(m.group(1), (band, m.group(2)))
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()


def basic_corpus(n=12):
    c = Corpus()
    for i in range(n):
        c.add(f"feedback_f{i:02d}.md",
              mem(f"f{i:02d}", description=f"desc for f{i:02d}",
                  access=i, last=10.0 + i, created=200))
    return c


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

def test_determinism_byte_identical():
    """Two runs over an unchanged corpus emit identical bytes.

    This is the concurrency guarantee ('parallel regenerations converge'), which
    was previously assumed rather than checked.
    """
    with basic_corpus() as c:
        c.rerank()
        first, first_arch = c.read_index(), c.read_archive()
        c.rerank()
        assert c.read_index() == first
        assert c.read_archive() == first_arch


def test_tie_break_is_total_and_order_independent():
    """Most of the corpus shares a score, so ties are the COMMON case.

    Files are created in one order and re-created in reverse; the emitted index
    must be identical. Guards the implicit dependence on glob() order.
    """
    files = [(f"feedback_tie{i:02d}.md",
              mem(f"tie{i:02d}", description=f"d{i}", access=3, last=5.0, created=200))
             for i in range(10)]
    with Corpus() as a, Corpus() as b:
        for n, t in files:
            a.add(n, t)
        for n, t in reversed(files):
            b.add(n, t)
        a.rerank()
        b.rerank()
        assert a.read_index() == b.read_index()


def test_nothing_is_lost():
    """Every file on disk appears in exactly one band."""
    with basic_corpus(40) as c:
        c.rerank()
        bands = c.bands()
        on_disk = {p.name for p in c.mem.glob("*.md")
                   if p.name.startswith(("feedback_", "project_", "reference_"))}
        assert on_disk == set(bands), f"missing: {on_disk - set(bands)}"


def test_summary_comes_from_the_file():
    """`summary:` in frontmatter is the displayed text, and beats `description:`."""
    with basic_corpus(5) as c:
        c.add("feedback_src.md",
              mem("src", description="the description", summary="THE SUMMARY WINS",
                  access=2, last=1.0, created=200))
        c.rerank()
        _, text = c.bands()["feedback_src.md"]
        assert "THE SUMMARY WINS" in text, text


def test_index_is_derived_hand_edits_are_discarded():
    """The index is a pure function of the corpus.

    This REPLACES the old contract, under which a hand-edited row was carried
    forward. That carry-forward is what made the index stateful and gave it a
    destructive failure mode. An edit here must now be discarded — the summary is
    edited in the FILE.
    """
    with basic_corpus(5) as c:
        c.rerank()
        md = c.read_index().replace("desc for f00", "HAND EDITED IN THE INDEX")
        (c.mem / "MEMORY.md").write_text(md, encoding="utf-8")
        c.rerank()
        assert "HAND EDITED IN THE INDEX" not in c.read_index(), \
            "a hand-edited index row survived — the index is reading its own output again"
        assert "desc for f00" in c.read_index() + c.read_archive()


def test_editing_the_file_changes_the_index():
    """The replacement escape hatch: edit the file, rerank, and the index follows."""
    with basic_corpus(5) as c:
        c.rerank()
        p = c.mem / "feedback_f00.md"
        p.write_text(p.read_text().replace('description: "desc for f00"',
                                           'summary: "EDITED IN THE FILE"'), encoding="utf-8")
        c.rerank()
        assert "EDITED IN THE FILE" in c.read_index() + c.read_archive()


def test_archived_rows_do_not_resurrect_as_ghosts():
    """A file rolled off to the archive must not come back as a ⚠ missing-file row.

    The tombstone path reads the archive; if it cannot tell a rolled-off row from a
    deleted file, every archived memory grows a duplicate ghost entry.
    """
    c = Corpus()
    for i in range(120):  # enough to overflow Hot+Cold into the archive
        c.add(f"feedback_g{i:03d}.md",
              mem(f"g{i:03d}", description="x" * 200, access=0, last=400.0, created=300))
    with c:
        c.rerank()
        c.rerank()
        assert "⚠ file missing" not in c.read_archive(), \
            "rolled-off rows were mistaken for deleted files"
        bands = c.bands()
        assert len(bands) == 120, f"expected 120 rows, got {len(bands)}"


def test_deleted_file_keeps_a_tombstone():
    """Never delete: a row whose file is gone is preserved and marked."""
    with basic_corpus(5) as c:
        c.rerank()
        (c.mem / "feedback_f00.md").unlink()
        c.rerank()
        assert "feedback_f00.md" in c.read_index() + c.read_archive()
        assert "⚠ file missing" in c.read_index() + c.read_archive()


def test_budgets_never_exceeded():
    """A row that would straddle a budget boundary is pushed down, never truncated."""
    sys.path.insert(0, str(EXEC_DIR))
    import rerank_memory_index as R
    c = Corpus()
    for i in range(60):
        c.add(f"feedback_h{i:03d}.md",
              mem(f"h{i:03d}", description="y" * 300, access=60 - i, last=1.0, created=300))
    with c:
        c.rerank()
        md = c.read_index()
        inew, icold = md.find("## New ("), md.find("## Cold (")
        if inew == -1:  # pre-v2.1.0 layout has no New band
            inew = icold
        hot_rows = re.findall(r"^\| `[^`]+\.md` \| .*$", md[:inew], re.M)
        cold_rows = re.findall(r"^\| `[^`]+\.md` \| .*$", md[icold:], re.M)
        assert sum(len(r) + 1 for r in hot_rows) <= R.HOT_CHAR_BUDGET
        assert sum(len(r) + 1 for r in cold_rows) <= R.COLD_CHAR_BUDGET
        for r in hot_rows + cold_rows:
            assert "y" * 300 in r, "a row was truncated instead of pushed down"


def test_pin_forces_hot_regardless_of_score():
    with basic_corpus(30) as c:
        c.add("feedback_pinned.md",
              mem("pinned", description="pinned row", access=0, last=9999.0,
                  created=500, pin=True))
        c.rerank()
        assert c.bands()["feedback_pinned.md"][0] == "hot"


def test_superseded_forced_out_of_active_index():
    with basic_corpus(5) as c:
        c.add("feedback_old.md",
              mem("old", description="superseded row", access=999, last=0.0,
                  created=500, status="superseded-by-lens"))
        c.rerank()
        assert c.bands()["feedback_old.md"][0] == "archive", \
            "a superseded file outranked live memories"


def test_malformed_frontmatter_degrades_not_crashes():
    """A broken file must fall back to defaults, not kill the run or vanish."""
    with basic_corpus(5) as c:
        c.add("feedback_broken.md", "---\nname: broken\ndescription: a: b: c\n[[[\n---\nbody\n")
        c.add("feedback_nofm.md", "no frontmatter at all\n")
        c.rerank()
        bands = c.bands()
        assert "feedback_broken.md" in bands
        assert "feedback_nofm.md" in bands


def test_newborn_is_visible_in_the_autoloaded_index():
    """THE regression that motivated this suite.

    A memory created today scores 1.00 and lost to 124 older files, landing in
    the archive: never indexed, so never read, so never reinforced. This test
    would have caught it the day the Cold budget was halved.
    """
    c = Corpus()
    # Descriptions must be REALISTICALLY long (~300 chars, as in the live corpus). With short
    # rows the whole tail fits inside the 12K Hot budget, the newborn is never crowded out, and
    # this test passes against the very bug it exists to catch. It did exactly that on first
    # write — verified by running it against the pre-fix reranker.
    for i in range(200):  # a long tail that all outranks a newborn AND overflows Hot+Cold
        c.add(f"feedback_old{i:03d}.md",
              mem(f"old{i:03d}", description=f"established memory {i} " + "z" * 300,
                  access=5, last=2.0, created=300))
    c.add("feedback_newborn.md",
          mem("newborn", description="written moments ago " + "w" * 300,
              access=0, last=0.0, created=0))
    with c:
        c.rerank()
        band = c.bands()["feedback_newborn.md"][0]
        assert band in ("hot", "new"), \
            f"a memory written today landed in '{band}' — it can never be read, so it can never be reinforced"


def test_newborn_grace_expires():
    """Grace is a window, not a permanent pin — otherwise New grows without bound."""
    with basic_corpus(5) as c:
        c.add("feedback_stale.md",
              mem("stale", description="born long ago", access=0, last=200.0, created=200))
        c.rerank()
        assert c.bands()["feedback_stale.md"][0] != "new"


def test_missing_created_is_not_treated_as_newborn():
    """Fail closed. mtime is last-touch, not birth, so absence must not mean 'new'."""
    with basic_corpus(5) as c:
        c.add("feedback_nocreated.md",
              mem("nocreated", description="no created field", access=0, last=200.0))
        c.rerank()
        assert c.bands()["feedback_nocreated.md"][0] != "new"


# --------------------------------------------------------------------------
# frontmatter scalar parsing
#
# These matter because the summary is moving INTO the file. While the index
# carried it, a mis-parsed frontmatter value was merely a fallback nobody saw;
# once the file is the source of truth, a parser that takes only the first line
# silently truncates every multi-line summary in the corpus.
# --------------------------------------------------------------------------

def _pf(fm_body):
    sys.path.insert(0, str(EXEC_DIR))
    import rerank_memory_index as R
    return R.parse_frontmatter("---\n" + fm_body + "\n---\n\nbody\n")


def test_parse_plain_scalar():
    assert _pf("summary: just text here")["summary"] == "just text here"


def test_parse_quoted_scalar_with_colon_and_backtick():
    got = _pf('summary: "BUG-001: see `foo.py` — resolved"')["summary"]
    assert got == "BUG-001: see `foo.py` — resolved"


def test_parse_escaped_quotes_are_unescaped():
    got = _pf('summary: "\\"100%\\" means every record"')["summary"]
    assert got == '"100%" means every record', got


def test_parse_multiline_quoted_scalar_is_not_truncated():
    """216 live files already have a multi-line summary. First-line-only loses them."""
    got = _pf('summary: "first line continues\n  onto a second line\n  and a third."')["summary"]
    assert "third" in got, f"multi-line summary truncated: {got!r}"


def test_parse_folded_block_scalar():
    got = _pf("summary: >-\n  folded line one\n  folded line two")["summary"]
    assert got == "folded line one folded line two", got


def test_parse_stops_at_next_key():
    fm = 'summary: "the summary"\naccess_count: 7\nstability: 20.0'
    got = _pf(fm)
    assert got["summary"] == "the summary"
    assert got["access_count"] == "7"


def test_parse_nested_metadata_block_still_found():
    """Real corpus files nest type/node_type under `metadata:`; keys sit at any indent."""
    fm = 'description: "top level"\nmetadata:\n  node_type: memory\n  type: feedback\naccess_count: 3'
    got = _pf(fm)
    assert got["description"] == "top level"
    assert got["access_count"] == "3"


# --------------------------------------------------------------------------
# spacing gate (update_memory_access.py)
# --------------------------------------------------------------------------

def _fields(path):
    t = path.read_text(encoding="utf-8")
    def g(k, cast):
        m = re.search(rf"^{k}:\s*(.+)$", t, re.M)
        return cast(m.group(1).strip()) if m else None
    return g("access_count", int), g("stability", float)


def test_spacing_gate_blocks_massed_reads():
    """Cramming refreshes recency but must NOT inflate storage strength."""
    with basic_corpus(1) as c:
        f = "feedback_f00.md"
        (c.mem / f).write_text(mem("f00", description="d", access=1, last=0.0,
                                   stability=14.0, created=100), encoding="utf-8")
        (c.mem / f).write_text((c.mem / f).read_text() .replace(
            "stability: 14.0", f"stability: 14.0\nlast_reinforced: {iso(0.01)}"))
        before = _fields(c.mem / f)
        for _ in range(5):
            c.touch(f)
        assert _fields(c.mem / f) == before, "massed re-reads inflated access_count/stability"


def test_spaced_read_reinforces_with_capped_growth():
    """A read after the gap counts: access_count+1 and stability *= 1.6, capped 365."""
    with basic_corpus(1) as c:
        f = "feedback_f00.md"
        (c.mem / f).write_text(mem("f00", description="d", access=1, last=5.0,
                                   stability=14.0, created=100), encoding="utf-8")
        (c.mem / f).write_text((c.mem / f).read_text().replace(
            "stability: 14.0", f"stability: 14.0\nlast_reinforced: {iso(5)}"))
        c.touch(f)
        count, stab = _fields(c.mem / f)
        assert count == 2, f"expected access_count 2, got {count}"
        assert abs(stab - 22.4) < 0.01, f"expected stability 14*1.6=22.4, got {stab}"


def test_stability_cap():
    with basic_corpus(1) as c:
        f = "feedback_f00.md"
        (c.mem / f).write_text(mem("f00", description="d", access=9, last=5.0,
                                   stability=300.0, created=100), encoding="utf-8")
        (c.mem / f).write_text((c.mem / f).read_text().replace(
            "stability: 300.0", f"stability: 300.0\nlast_reinforced: {iso(5)}"))
        c.touch(f)
        _, stab = _fields(c.mem / f)
        assert stab <= 365.0, f"stability exceeded the 365 cap: {stab}"


def test_curation_reinforces_too():
    """Edit/Write count as reinforcement, not just Read (my-lib 1199c39)."""
    with basic_corpus(1) as c:
        f = "feedback_f00.md"
        (c.mem / f).write_text(mem("f00", description="d", access=1, last=5.0,
                                   stability=14.0, created=100), encoding="utf-8")
        (c.mem / f).write_text((c.mem / f).read_text().replace(
            "stability: 14.0", f"stability: 14.0\nlast_reinforced: {iso(5)}"))
        c.touch(f, tool="Edit")
        count, _ = _fields(c.mem / f)
        assert count == 2, "Edit did not reinforce"


# --------------------------------------------------------------------------

def _standalone():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append(name)
            print(f"  FAIL  {name}\n          {str(e)[:200]}")
        except Exception as e:                      # noqa: BLE001
            failed.append(name)
            print(f"  ERROR {name}: {type(e).__name__}: {str(e)[:200]}")
    print(f"\n{len(fns) - len(failed)}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_standalone())
