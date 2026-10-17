#!/usr/bin/env python3
# ---
# template: app-test
# version: 1.1.1
# summary: Tests for todo_pane.py against a temporary list file (never the real one). Covers date and field parsing, the file round trip, close/reopen/roll-off, restore from the done file, the 44-character cap, word wrap, clock times and the agent CLI. Run with python3 test_todo_pane.py.
# created: 2026-10-15
# last_updated: 2026-10-16
# maintainer: pvragon
# ---
"""Run: python3 test_todo_pane.py   (exit 0 = all pass)"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="todo-pane-test-")
os.environ["TODO_FILE"] = str(Path(TMP) / "todo.md")      # set before import: the module reads it once
os.environ.pop("CLAUDECODE", None)
os.environ.pop("TODO_PANE_AGENT", None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import todo_pane as t  # noqa: E402

BASE = dt.date(2026, 10, 15)          # a Thursday
t.today = lambda: BASE
failures = []


def check(cond, name):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# dates
for phrase, want in [("fri", (2026, 10, 16)), ("thursday", (2026, 10, 22)), ("next friday", (2026, 10, 23)),
                     ("tomorrow", (2026, 10, 16)), ("10/20", (2026, 10, 20)), ("1/5", (2027, 1, 5)),
                     ("the 20th", (2026, 10, 20)), ("3rd", (2026, 11, 3)), ("oct 20", (2026, 10, 20)),
                     ("October 20th", (2026, 10, 20))]:
    check(t.parse_due(phrase, BASE) == dt.date(*want), f"due '{phrase}'")
check(t.parse_due("13/45", BASE) is None, "impossible date is ignored")

# fields at the end of a line
check(t.parse_entry("Etsy shipping Friday 10am") == ("Etsy shipping 10am", "", "261016"), "bare date, time kept")
check(t.parse_entry("call mom due friday.") == ("call mom", "", "261016"), "spoken due date")
check(t.parse_entry("#1 thing #work ^10/20") == ("#1 thing", "work", "261020"), "leading # stays text")
check(t.parse_entry("send the list category team one", ["team1"])[1] == "team1", "spoken category matches")
check(t.parse_line("- [ ] bad date  ^999999")[0] is not None, "malformed date token doesn't crash")

# file round trip and nesting
k1 = t.add_item("Call the plumber", "home", "261017")
k2 = t.add_item("find the invoice", under=k1)
k3 = t.add_item("book a time", under=k1)
t.add_item("#1 thing", by_agent=True)
items = t.load()
check(len(items) == 2 and len(items[0].children) == 2, "nesting round-trips")
check(items[1].text == "#1 thing" and items[1].by_agent, "agent marker kept")
check(t.dump(t.load()) == Path(os.environ["TODO_FILE"]).read_text(), "dump(load) is stable")

# close, reopen, roll-off, restore
t.mutate(lambda its: t.close(t.find(its, k3), "x"))
check(t.find(t.load(), k3).closed == "261015", "close stamps today")
t.mutate(lambda its: t.reopen(t.find(its, k3)))
x = t.find(t.load(), k3)
check(x.is_open and not x.closed and x.reopened == 1, "reopen clears the stamp and counts")
t.mutate(lambda its: t.close(t.find(its, k3), "x"))
t.today = lambda: BASE + dt.timedelta(days=1)
check(t.mutate(t.roll_off) == 1, "next morning, the closed item rolls off")
rows = t.closed_recent(t.load())
check(rows and rows[0][1].text == "Call the plumber › book a time", "closed view names the parent")
check(t.restore_from_done(rows[0][1].key()), "restore from the done file")
check(t.load()[-1].is_open, "restored item is open")
t.today = lambda: BASE

# the 44-character cap
pane = t.Pane()
pane.start_draft()
for ch in "Updated proposal for David R + Staffing Plan and more":
    pane.handle(ch)
check(t.text_length(pane.draft["text"]) <= 46, "typing stops near 44 (a field may be starting)")
pane.submit(keep_going=False)
check(max(len(i.text) for i in t.load()) <= 44, "saved text never exceeds 44")
for ch in " due friday":
    pane.handle(ch)
check(t.parse_entry(pane.draft["text"])[2] == "261016", "a due date still fits after 44")
pane.draft = None
pane = t.Pane()
victim = t.add_item("delete me")
pane.mtime = None
pane.reload()
pane.rows = pane.visible()
pane.start_edit(t.find(pane.items, victim))
pane.draft["text"] = ""
pane.submit()
check(t.find(t.load(), victim) is None, "emptied edit + enter deletes")
check("delete me" in t.DONE_FILE.read_text() and "(deleted)" in t.DONE_FILE.read_text(), "deleted copy kept")
check(t.cli(["add", "x" * 45]) == 2, "CLI refuses 45 characters")
check(t.cli(["add", "short one", "--due", "fri"]) == 0, "CLI adds a short item")

# wrap and times
check(t.wrap_words("DR confirmations", 6, 30) == ["DR", "confirmations"], "wrap keeps words whole")
check(t.wrap_words("a" * 25, 10, 12) == ["a" * 10, "a" * 12, "a" * 3], "an overlong word splits")
check([m.group() for m in t.TIME_IN_TEXT.finditer("call 3:30pm, lunch at noon, room 101")] == ["3:30pm", "noon"],
      "clock times found, numbers ignored")

# untrusted text never carries control characters
check(t.clean("a\x1b[31mb‮c") == "a[31mbc", "escape and bidi characters stripped")


# ── security review fixes (each was a way to lose or garble items) ──
import stat
import time
F = Path(os.environ["TODO_FILE"])
F.write_text("# my notes\n- buy milk\n- [ ] real item  +261015\n* [ ] other style\n", encoding="utf-8")
t.add_item("added later")
body = F.read_text(encoding="utf-8")
check(all(x in body for x in ("# my notes", "- buy milk", "* [ ] other style", "added later")),
      "lines that aren't items survive a save")
os.chmod(F, 0)
try:
    t.add_item("should not land")
    wiped = True
except OSError:
    wiped = False
os.chmod(F, stat.S_IRUSR | stat.S_IWUSR)
check(not wiped and "real item" in F.read_text(encoding="utf-8"), "an unreadable list is never overwritten")
F.write_text("- [x] parent  +261010  ✓261012\n  - [ ] still open child  +261010\n", encoding="utf-8")
t.mutate(t.roll_off)
check("still open child" in F.read_text(encoding="utf-8"), "roll-off keeps an open sub-item on the wall")
F.write_text("- [ ] summer thing  ^260801  +260701\n", encoding="utf-8")
p2 = t.Pane()
p2.rows = p2.visible()
p2.start_edit(p2.items[0])
p2.draft["text"] = p2.draft["text"].replace("summer thing", "summer things")
p2.submit(keep_going=False)
check(t.load()[0].due == "260801" and not t.load()[0].was, "editing keeps the due date's year")
F.write_bytes(b"- [ ] bad bytes \xff\xfe here  +261015\n- [ ] count  \xe2\x86\xbb" + b"9" * 5000 + b"\n")
check(len(t.load()) == 2, "bad bytes and a huge reopen count don't crash")
t0 = time.time()
t.parse_entry("a" + ", " * 5000 + "x")
check(time.time() - t0 < 0.5, "pathological input parses fast")
F.write_text("- [ ] parent  +261015\n  - [ ] kid  +261015\n", encoding="utf-8")
p3 = t.Pane()
p3.rows = p3.visible()
p3.start_edit(p3.items[0])
p3.draft["text"] = ""
p3.submit()
p3.handle("\r")
check(len(t.load()) == 1, "Enter does not confirm a delete")
p3.start_edit(t.load()[0]) if False else None
line = t.archive_line(t.Item("gone", " ", "home", "261017", "261017", "261015"), "cut")
x, _ = t.parse_line(line)
check(x.text == "gone" and x.cat == "home" and x.state == "-" and x.closed and x.removed == "cut",
      "a cut copy in the done file parses back cleanly")
check(t.split_input("\x1b[200~a\rb\x1b[201~") == [("paste", "a\rb")], "terminal paste arrives as text")

# grouped view: dropping into another group takes that group's category
F.write_text("- [ ] loose  +261015\n- [ ] chores  #home  +261015\n", encoding="utf-8")
pg = t.Pane()
pg.group = True
pg.rows = pg.visible()
pg.drop(t.load()[0].key(), t.load()[1].key(), True, "home")
check(t.load()[1].text == "loose" and t.load()[1].cat == "home", "grouped drop adopts the group's category")

# star: a highlighted priority that clears when the item closes
F.write_text("- [ ] call bank  #home  ^261017  ★  +261015\n- [ ] plain  +261015\n", encoding="utf-8")
s0 = t.load()
check(s0[0].star and s0[0].cat == "home" and s0[0].due == "261017" and not s0[1].star,
      "a starred line parses with its other fields")
check(t.parse_line(s0[0].line())[0].star, "a star survives the round trip")
ps = t.Pane()
ps.rows = ps.visible()
ps.toggle_star(t.load()[1])
check(t.load()[1].star, "toggle_star stars an item")
row = ps.draw_row("item", t.load()[1], 0, False, 40, {}, 0)
check("\033[48;2;" in row and "★" in row, "a starred row is drawn highlighted")
ps.toggle_star(t.load()[1])
check(not t.load()[1].star, "toggle_star again removes the star")
plain = ps.draw_row("item", t.load()[1], 0, False, 40, {}, 0)
check("\033[48;2;" not in plain and "☆" in plain, "an unstarred row is not highlighted")
ps._toggle(t.load()[0].key(), "x")
check(not t.load()[0].star, "completing an item clears its star")
check(t.cli(["star", "plain"]) == 0 and t.load()[1].star, "CLI stars an item")
check(t.cli(["star", "plain", "--off"]) == 0 and not t.load()[1].star, "CLI removes a star")
check(t.cli(["star", "no such item"]) == 2, "CLI star on a missing item exits 2")
F.write_text("- [ ] retire me  ★  +261015\n", encoding="utf-8")
pr = t.Pane()
pr.rows = pr.visible()
pr._toggle(t.load()[0].key(), "-")
check(not t.load()[0].star, "retiring an item clears its star")

check(t.Pane().group, "grouped by category is the default view")

print(f"\n{len(failures)} failed" if failures else "\nall passed")
sys.exit(1 if failures else 0)
