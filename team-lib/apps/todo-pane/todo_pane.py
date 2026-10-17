#!/usr/bin/env python3
# ---
# template: app
# version: 1.7.1
# summary: Sticky-note to-do pane for a tiling desktop. One plain markdown file that you and your agents write to; a compact themed terminal view with click or space to check off (strike-through), retire, free categories, MM/DD due dates colored by urgency, computed close dates, next-morning roll-off and a Keep-style closed view. Also a CLI for agents.
# created: 2026-10-15
# last_updated: 2026-10-16
# maintainer: pvragon
# ---
"""To-do pane: a sticky note that lives on the wall.

The data is one markdown file, one item per line, readable and editable by hand. It lives at
$TODO_FILE, else ~/.config/todo-pane/todo.md (a symlink there is followed, so the list can
live in a synced or versioned folder):

    - [ ] Call the plumber  #home  ^261017  +261015
      - [x] find the invoice  +261013  ✓261014
    - [-] new monitor arm  #desk  +261001  ✗261015
    - [ ] renew domain  #work  +261015  ·r

  [ ] open   [x] done   [-] retired (won't do)
  #cat  one free category      ^YYMMDD  due (shown as MM/DD)    (was YYMMDD)  first due
  +YYMMDD created              ✓/✗YYMMDD  closed (written by the pane)
  ·r  added by an agent (CLI)  ↻N  times reopened
Fields are only recognized at the END of a line, so "#1 thing" stays text.

Closed items stay on the wall, struck through, until the next morning; then they move
to todo-done.md. `c` shows recent closed items (newest first); space there reopens one.

Add by just typing (or talking: voxtype types into the pane). Click below the list for a
new line at the end; Enter saves and opens the next line; Tab / Shift+Tab indent it.
Click a circle (or space) to check; Delete retires; click the text (or Enter) to edit.
Drag a line to move it (Alt+↑↓ too). Click "group" or "closed" in the header (Ctrl+G, Ctrl+O).
Ctrl+T shows created and closed dates. F1 lists all of this.
Adding understands typed fields (#cat ^fri ^10/20) and plain ones at the end:
"... friday 10am", "due friday", "by the 20th", "category home". A time stays in the text.

CLI (for agents; marks items ·r when TODO_PANE_AGENT or CLAUDECODE is set):
    todo_pane.py add "text" [--due fri] [--cat work] [--under "parent text"]
    todo_pane.py list
Every write takes a lock and replaces the file atomically; the pane reloads on change.
"""
import calendar
import datetime as dt
import fcntl
import os
import re
import sys
import time
import tomllib
import unicodedata
from contextlib import contextmanager
from pathlib import Path

# Resolve symlinks up front: writes replace the file atomically, which would otherwise swap
# a symlink for a plain file and cut the link to wherever the list really lives.
TODO_FILE = Path(os.path.realpath(os.environ.get("TODO_FILE") or Path.home() / ".config/todo-pane/todo.md"))
DONE_FILE = TODO_FILE.with_name(TODO_FILE.stem + "-done.md")
LOCK_FILE = TODO_FILE.with_name("." + TODO_FILE.name + ".lock")
CAT_COLORS = Path.home() / ".config/todo-pane/categories.txt"   # optional: "<label> <theme-key|#hex>"
THEME = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
MAX_TEXT = 44   # an item's text is at most 44 characters, spaces included: a sticky note, not a ticket
HEADER = "# To-do. Managed by todo_pane.py; edit freely, one item per line.\n"

# ── Theme: Omarchy colors when present, neutral fallback elsewhere ──
DEFAULTS = {"background": "#16181d", "foreground": "#c8ccd4", "light_foreground": "#e6e9ef",
            "accent": "#5fa8d3", "selection": "#2c3e50", "muted": "#6b7280", "orange": "#f08a4b",
            "yellow": "#e6bb3f"}
C = dict(DEFAULTS)
_theme_mtime = None


def refresh_palette():
    global _theme_mtime
    try:
        mtime = THEME.stat().st_mtime
    except OSError:
        mtime = None
    if mtime == _theme_mtime:
        return
    _theme_mtime = mtime
    C.clear()
    C.update(DEFAULTS)
    try:
        C.update({k: v for k, v in tomllib.loads(THEME.read_text(encoding="utf-8", errors="replace")).items()
                  if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)})
    except (OSError, ValueError):
        pass


def fg(color, text, bold=False, strike=False):
    r, g, b = (int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    sgr = f"38;2;{r};{g};{b}" + (";1" if bold else "") + (";9" if strike else "")
    return f"\033[{sgr}m{text}\033[0m"


CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]")


def clean(text):
    """Untrusted text made safe to draw: no control or invisible format characters, one line."""
    text = CONTROL.sub("", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return re.sub(r"\s+", " ", text).strip()


def width(s):
    return sum(0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in s)


def clip(s, n):
    if width(s) <= n:
        return s
    out = ""
    for ch in s:
        if width(out + ch) > n - 1:
            break
        out += ch
    return out + "…"


# ── Model ───────────────────────────────────────────────────────────────────
def today():
    return dt.date.today()


def ymd(d):
    return d.strftime("%y%m%d")


def parse_ymd(s):
    try:
        return dt.datetime.strptime(s, "%y%m%d").date()
    except (TypeError, ValueError):
        return None


class Item:
    def __init__(self, text="", state=" ", cat="", due="", was="", created="", closed="",
                 by_agent=False, reopened=0, star=False):
        self.text, self.state, self.cat, self.due, self.was = text, state, cat, due, was
        self.star = star      # a priority for now: the row is highlighted while it stays open
        self.created, self.closed, self.by_agent, self.reopened = created, closed, by_agent, reopened
        self.removed = ""     # "cut" or "deleted": how it left the list (done file only)
        self.children = []
        self.parent = None

    @property
    def is_open(self):
        return self.state == " "

    def key(self):
        return (self.text, self.created)

    def line(self, indent=0):
        parts = [f"{'  ' * indent}- [{self.state}] {self.text}"]
        if self.cat:
            parts.append(f"#{self.cat}")
        if self.due:
            parts.append(f"^{self.due}")
        if self.was and self.was != self.due:
            parts.append(f"(was {self.was})")
        if self.star:
            parts.append("★")
        if self.created:
            parts.append(f"+{self.created}")
        if self.closed:
            parts.append(("✓" if self.state == "x" else "✗") + self.closed)
        if self.reopened:
            parts.append(f"↻{self.reopened}")
        if self.removed:
            parts.append(f"({self.removed})")
        if self.by_agent:
            parts.append("·r")
        return "  ".join(parts)


LINE = re.compile(r"^(\s*)- \[([ xX\-])\] ?(.*)$")
TOKENS = [
    (re.compile(r"\s+#([\w.\-]+)$"), "cat"),
    (re.compile(r"\s+\^(\d{6})$"), "due"),
    (re.compile(r"\s+\(was (\d{6})\)$"), "was"),
    (re.compile(r"\s+\+(\d{6})$"), "created"),
    (re.compile(r"\s+[✓✗](\d{6})$"), "closed"),
    (re.compile(r"\s+↻(\d{1,4})$"), "reopened"),
    (re.compile(r"\s+\((cut|deleted)\)$"), "removed"),
    (re.compile(r"\s+(·r)$"), "by_agent"),
    (re.compile(r"\s+(★)$"), "star"),
]


def parse_line(raw):
    m = LINE.match(raw.rstrip())
    if not m:
        return None, 0
    indent, state, rest = m.groups()
    it = Item(state=state.lower())
    rest = " " + rest
    changed = True
    while changed:
        changed = False
        for rx, field in TOKENS:
            t = rx.search(rest)
            if t:
                val = t.group(1)
                if field == "reopened":
                    it.reopened = int(val)
                elif field == "by_agent":
                    it.by_agent = True
                elif field == "star":
                    it.star = True
                else:
                    setattr(it, field, val)
                rest = rest[:t.start()]
                changed = True
    it.text = clean(rest)
    return it, (1 if len(indent.expandtabs(4)) >= 2 else 0)


class ItemList(list):
    """Top-level items, plus every line of the file that is not an item (notes, other list
    styles, blank lines), kept verbatim with its position, so a save never drops them.
    raw: [(n, line)] where n is how many top-level items came before the line."""
    def __init__(self, *a):
        super().__init__(*a)
        self.raw = []


def read(path):
    """File text as UTF-8 (bad bytes replaced). A missing file is "" ; any other read error
    raises, because treating an unreadable list as empty would let the next save wipe it."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def load(path=TODO_FILE):
    items = ItemList()
    for raw in read(path).splitlines():
        it, depth = parse_line(raw)
        if not it:
            if raw.strip() != HEADER.strip():
                items.raw.append((len(items), raw))
            continue
        if depth and items:
            it.parent = items[-1]
            items[-1].children.append(it)
        else:
            items.append(it)
    return items


def dump(items):
    raw = list(getattr(items, "raw", []))
    out = [HEADER]

    def flush(n):
        while raw and raw[0][0] <= n:
            out.append(raw.pop(0)[1] + "\n")
    for i, it in enumerate(items):
        flush(i)
        out.append(it.line() + "\n")
        out += [c.line(1) + "\n" for c in it.children]
    flush(len(items) + len(raw) + 1)
    return "".join(out)


@contextmanager
def locked():
    TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def atomic_write(path, text):
    """Replace a file in one step: a fresh private temp file in the same folder, flushed to
    disk, given the old file's permissions, then renamed over it. Symlinks are followed to
    the real file, so a linked list stays linked."""
    import tempfile
    real = Path(os.path.realpath(path))
    fd, tmp = tempfile.mkstemp(dir=real.parent, prefix=f".{real.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, os.stat(real).st_mode & 0o777)
        except FileNotFoundError:
            pass                               # a new file keeps mkstemp's private 0600
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mutate(fn):
    """Lock, reload from disk, apply fn(items), write back. Agents and the pane both use this,
    so a write never clobbers another writer's change."""
    with locked():
        items = load()
        result = fn(items)
        atomic_write(TODO_FILE, dump(items))
    return result


def find(items, key):
    for it in items:
        if it.key() == key:
            return it
        for c in it.children:
            if c.key() == key:
                return c
    return None


def siblings(items, it):
    return it.parent.children if it.parent else items


# ── Closing, reopening, roll-off ────────────────────────────────────────────
def close(it, state):
    it.state, it.closed = state, ymd(today())
    it.star = False       # a finished priority stops being one


def reopen(it):
    it.state, it.closed = " ", ""
    it.reopened += 1
    if it.parent and not it.parent.is_open:
        reopen(it.parent)


DONE_HEADER = "# Closed to-do items, newest at the end.\n"


def archive_line(it, removed=""):
    """One done-file line. A removed (cut/deleted) item is recorded as retired today."""
    text = f"{it.parent.text} › {it.text}" if it.parent else it.text
    copy = Item(text, it.state, it.cat or (it.parent.cat if it.parent else ""), it.due, it.was,
                it.created, it.closed, it.by_agent, it.reopened)
    if removed:
        copy.state, copy.closed, copy.removed = "-", copy.closed or ymd(today()), removed
    return copy.line()


def append_done(lines):
    """Add lines to the done file (call under the lock)."""
    if lines:
        atomic_write(DONE_FILE, (read(DONE_FILE) or DONE_HEADER) + "".join(l + "\n" for l in lines))


def roll_off(items):
    """Move items closed before today to the done file. Returns how many moved."""
    t = ymd(today())
    moved = []
    for it in list(items):
        # Closed sub-items go first. A closed parent goes only once nothing under it is
        # still open: an open sub-item must never leave the wall.
        for c in list(it.children):
            if not c.is_open and c.closed and c.closed < t:
                moved.append(archive_line(c))
                it.children.remove(c)
        if not it.is_open and it.closed and it.closed < t and not it.children:
            moved.append(archive_line(it))
            items.remove(it)
    append_done(moved)
    return len(moved)


def closed_recent(items, limit=60):
    """Closed items, newest first: today's from the wall, then the done file."""
    rows = []
    for it in items:
        for x in [it] + it.children:
            if not x.is_open:
                rows.append(("wall", x))
    try:
        for raw in read(DONE_FILE).splitlines():
            x, _ = parse_line(raw)
            if x:
                rows.append(("done", x))
    except OSError:
        pass
    rows.sort(key=lambda r: r[1].closed or "", reverse=True)
    return rows[:limit]


def restore_from_done(key):
    """Reopen an archived item: drop it from the done file and put it back at the end of the wall."""
    with locked():
        lines = read(DONE_FILE).splitlines(keepends=True)
        for i, raw in enumerate(lines):
            x, _ = parse_line(raw)
            if x and x.key() == key:
                items = load()
                x.state, x.closed, x.removed, x.reopened = " ", "", "", x.reopened + 1
                items.append(x)
                atomic_write(TODO_FILE, dump(items))      # list first: a duplicate beats a loss
                del lines[i]
                atomic_write(DONE_FILE, "".join(lines))
                return True
    return False


# ── Quick-add parsing (typed and spoken) ────────────────────────────────────
WEEKDAYS = {d.lower(): i for i, d in enumerate(calendar.day_name)}
WEEKDAYS.update({d.lower(): i for i, d in enumerate(calendar.day_abbr)})
WEEKDAYS.update({"tues": 1, "thur": 3, "thurs": 3})
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
NUMWORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
            "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def parse_due(s, base=None):
    """'fri', 'friday', 'next friday', 'tomorrow', 'today', '10/20', '20th', 'the 20th',
    'oct 20', 'october 20th' -> date, or None."""
    base = base or today()
    s = s.lower().strip(" .,!").removeprefix("the ").strip()
    if s in ("today", "tod", "tonight"):
        return base
    if s in ("tomorrow", "tom", "tmrw"):
        return base + dt.timedelta(days=1)
    nxt = s.startswith("next ")
    s2 = s.removeprefix("next ").strip()
    if s2 in WEEKDAYS:
        ahead = (WEEKDAYS[s2] - base.weekday()) % 7 or 7
        return base + dt.timedelta(days=ahead + (7 if nxt and ahead < 7 else 0))
    if s2 in ("week", "wk"):
        return base + dt.timedelta(days=7)

    def pick(month, day):
        for year in (base.year, base.year + 1):
            try:
                d = dt.date(year, month, day)
            except ValueError:
                return None
            if d >= base - dt.timedelta(days=60):   # a recent past date stays this year
                return d
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", s)
    if m:
        return pick(int(m[1]), int(m[2]))
    m = re.fullmatch(r"([a-z]+)\.? (\d{1,2})(st|nd|rd|th)?", s)
    if m and m[1] in MONTHS:
        return pick(MONTHS[m[1]], int(m[2]))
    m = re.fullmatch(r"(\d{1,2})(st|nd|rd|th)?", s)
    if m:
        day = int(m[1])
        d = pick(base.month, day)
        if d and d < base:
            month = base.month % 12 + 1
            d = pick(month, day)
        return d
    return None


_DAYWORD = (r"(?:next\s+)?(?:today|tonight|tomorrow|tmrw|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun|"
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)")
_DATE = (_DAYWORD + r"|\d{1,2}/\d{1,2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?")
_TIME = r"(?:\s*,?\s+(?:at\s+)?(\d{1,2}(?::\d\d)?\s*(?:am|pm|a\.m\.|p\.m\.)|noon))"
# "... due friday", "... by the 20th 3pm" (keyword), or a bare "... Friday 10am" / "... 10/20" at the end.
# A time has no field of its own: it stays in the text.
SPOKEN_DUE = re.compile(r"(?<![\s,])[\s,]+(?:(?:due|by|on)\s+(" + _DATE + r"|(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?)|(" + _DATE + r"))"
                        + _TIME + r"?[.!]?$", re.I)
SPOKEN_CAT = re.compile(r"(?<![\s,])[\s,]+(?:category|cat|tag)\s+([\w\s\-]{1,30}?)[.!]?$", re.I)
TYPED_CAT = re.compile(r"\s+#([\w.\-]+)$")
TYPED_DUE = re.compile(r"\s+\^([\w/]+)$")


def norm_cat(spoken, known):
    words = [NUMWORDS.get(w, w) for w in spoken.lower().split()]
    flat = re.sub(r"[^\w]", "", "".join(words))
    for k in known:
        if re.sub(r"[^\w]", "", k.lower()) == flat:
            return k
    return re.sub(r"[^\w.\-]", "", "-".join(words))[:24]


def parse_entry(raw, known_cats=()):
    """Free text from the add line -> (text, cat, due YYMMDD). Fields come off the end, any order."""
    # Bounded: an item is 44 characters plus a few fields. Longer input (a huge paste, a long
    # agent argument) is cut first, so the end-anchored regexes stay fast.
    text = " " + clean(raw)[:300]
    cat = due = ""
    for _ in range(4):
        m = TYPED_CAT.search(text)
        if m:
            cat, text = m[1], text[:m.start()]
            continue
        m = TYPED_DUE.search(text)
        if m and parse_due(m[1]):
            due, text = ymd(parse_due(m[1])), text[:m.start()]
            continue
        m = SPOKEN_CAT.search(text)
        if m:
            cat, text = norm_cat(m[1], known_cats), text[:m.start()]
            continue
        m = SPOKEN_DUE.search(text)
        if m and parse_due(m[1] or m[2]):
            due = ymd(parse_due(m[1] or m[2]))
            text = text[:m.start()] + (" " + m[3].replace(" ", "") if m[3] else "")
            continue
        break
    return clean(text).rstrip("."), cat, due


def known_categories(items):
    seen = []
    for it in items:
        for x in [it] + it.children:
            if x.cat and x.cat not in seen:
                seen.append(x.cat)
    return seen


def add_item(text, cat="", due="", under=None, by_agent=False, after=None):
    """Add under the lock. under/after are item keys. Returns the new item's key."""
    def op(items):
        it = Item(text, " ", cat, due, due, ymd(today()), "", by_agent)
        parent = find(items, under) if under else None
        if parent and parent.parent:
            parent = parent.parent
        if parent:
            it.parent = parent
            it.cat = it.cat if it.cat != parent.cat else ""
            anchor = find(items, after) if after else None
            kids = parent.children
            kids.insert(kids.index(anchor) + 1 if anchor in kids else len(kids), it)
        else:
            anchor = find(items, after) if after else None
            if anchor and anchor.parent:
                anchor = anchor.parent
            pos = items.index(anchor) + 1 if anchor in items else len(items)
            items.insert(pos, it)
        return it.key()
    return mutate(op)


# ── Pane ────────────────────────────────────────────────────────────────────
def cat_colors():
    out = {}
    try:
        for raw in CAT_COLORS.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = raw.split()
            if len(parts) == 2 and not raw.startswith("#"):
                out[parts[0].lower()] = parts[1]
    except OSError:
        pass
    return out


def color_for(spec):
    if spec in C:
        return C[spec]
    return spec if re.fullmatch(r"#[0-9a-fA-F]{6}", spec or "") else C["muted"]


def due_style(due):
    d = parse_ymd(due)
    if not d:
        return None, False
    days = (d - today()).days
    if days < 0:
        return C["orange"], True
    if days == 0:
        return C["orange"], False
    if days <= 3:
        return C["light_foreground"], False
    return C["muted"], False


class Pane:
    FLASH = 0.35

    def __init__(self):
        self.items, self.mtime = [], None
        self.sel = -1         # index into self.rows; -1 = nothing selected
        self.top = 0
        self.group = True     # grouped by category is the default view; ctrl+g flattens
        self.detail = False
        self.view = "wall"    # wall | closed | help
        self.draft = None     # the line being typed: {text, parent, after, edit}
        self.confirm = None   # (key, state) waiting for y/n
        self.flash = {}       # key -> time checked
        self.note, self.note_until = "", 0.0
        self.rows = []        # (kind, payload, depth) as drawn
        self.row_y = {}       # screen row -> index in self.rows
        self.list_end_y = 0   # first screen row below the list
        self.header_hits = {} # name -> (x0, x1) of clickable header words
        self.press = None     # mouse press: {idx, y, moved, drop}
        self.draft_x0, self.draft_off = None, 0   # where the typed line starts on screen
        self.row_first = set()                    # screen rows where a list row begins
        self.last_day = today()
        self.reload(force=True)

    # data
    def reload(self, force=False):
        try:
            mtime = TODO_FILE.stat().st_mtime
        except OSError:
            mtime = None
        new_day = self.last_day != today()
        if force or new_day or mtime != self.mtime:
            try:
                if (force or new_day) and TODO_FILE.exists():
                    self.last_day = today()
                    mutate(roll_off)        # yesterday's closed items go to the done file
                self.items = load()
                self.mtime = mtime          # stamped before the read, so a later write is seen
            except OSError as e:
                self.say(f"can't read the list: {clean(e.strerror or e)}", 5)
                self.mtime = mtime

    def apply(self, fn):
        try:
            r = mutate(fn)
        except OSError as e:
            self.say(f"not saved: {clean(e.strerror or e)}", 5)    # the list on disk is untouched
            return None
        self.mtime = None
        self.reload()
        return r

    def say(self, text, secs=2.5):
        self.note, self.note_until = text, time.time() + secs

    # rows
    def base_rows(self):
        if self.view == "closed":
            return [("closed", x, src) for src, x in closed_recent(self.items)]
        rows = []
        order = self.items
        if self.group:
            cats = known_categories(self.items)
            order = sorted(self.items, key=lambda it: cats.index(it.cat) + 1 if it.cat in cats else 0)
        last_cat = object()
        for it in order:
            if self.group and it.cat != last_cat:
                if rows:
                    rows.append(("gap", None, 0))
                if it.cat:
                    rows.append(("rule", it.cat, 0))
                last_cat = it.cat
            rows.append(("item", it, 0))
            rows += [("item", c, 1) for c in it.children]
        return rows

    def visible(self):
        rows = self.base_rows()
        d = self.draft
        if not d or self.view != "wall":
            return rows
        if d.get("rename") is not None:
            for i, r in enumerate(rows):
                if r[0] == "rule" and r[1] == d["rename"]:
                    rows[i] = ("draft", d, 0)
                    return rows
            self.draft = None
            return rows
        if d["edit"]:
            for i, r in enumerate(rows):
                if r[0] == "item" and r[1].key() == d["edit"]:
                    rows[i] = ("draft", d, r[2])
                    return rows
            self.draft = None        # the item went away under us
            return rows
        depth = 1 if d["parent"] else 0
        pos = len(rows)
        if d["parent"]:
            anchor = d["after"] or d["parent"]
            for i, r in enumerate(rows):
                if r[0] == "item" and r[1].key() == anchor:
                    pos = i + 1
                    if not d["after"]:    # first child: after the parent's existing children
                        while pos < len(rows) and rows[pos][0] == "item" and rows[pos][2] == 1:
                            pos += 1
                    break
        elif d["after"]:
            for i, r in enumerate(rows):
                if r[0] == "item" and r[1].key() == d["after"]:
                    pos = i + 1
                    while pos < len(rows) and rows[pos][0] == "item" and rows[pos][2] == 1:
                        pos += 1
                    break
        rows.insert(pos, ("draft", d, depth))
        return rows

    def selectable(self):
        return [i for i, r in enumerate(self.rows) if r[0] in ("item", "closed")]

    def current(self):
        if 0 <= self.sel < len(self.rows) and self.rows[self.sel][0] in ("item", "closed"):
            return self.rows[self.sel][1]
        return None

    def select_key(self, key):
        for i, r in enumerate(self.rows):
            if r[0] == "item" and r[1].key() == key:
                self.sel = i
                return

    def move_sel(self, step):
        sel = self.selectable()
        if not sel:
            return
        if self.sel not in sel:
            self.sel = sel[0] if step > 0 else sel[-1]
            return
        i = max(0, min(len(sel) - 1, sel.index(self.sel) + step))
        self.sel = sel[i]

    # drafting
    def start_draft(self, text="", at_end=False):
        """A new line, typed in place: after the selected item, at its level."""
        self.view = "wall"
        cur = None if at_end else self.current()
        if cur is not None and not isinstance(cur, Item):
            cur = None
        self.draft = self.new_line_after(cur, text)

    def new_line_after(self, cur, text=""):
        """A draft right after `cur`, at its level. In grouped view it joins cur's group."""
        if cur is None:
            return {"text": text, "parent": None, "after": None, "edit": None, "cat": ""}
        top = cur.parent or cur
        cat = top.cat if self.group else ""
        if cur.parent:
            return {"text": text, "parent": cur.parent.key(), "after": cur.key(), "edit": None, "cat": cat}
        return {"text": text, "parent": None, "after": cur.key(), "edit": None, "cat": cat}

    def draft_anchor(self):
        """The item the typed line sits on (edit) or just after; the key to move from."""
        d = self.draft
        return d["edit"] or d["after"] or d["parent"]

    def start_edit(self, it):
        due = parse_ymd(it.due)
        text = it.text + (f" #{it.cat}" if it.cat else "") + (f" ^{due:%m/%d}" if due else "")
        self.draft = {"text": text, "parent": None, "after": None, "edit": it.key(), "cat": ""}

    def draft_indent(self, out):
        d = self.draft
        if d["edit"]:
            self.indent(out, d["edit"])
            return
        if out and d["parent"]:
            d["after"], d["parent"] = d["parent"], None
        elif not out and not d["parent"]:
            # the new line goes under the top-level item just above it
            above = None
            if d["after"]:
                above = find(self.items, d["after"])
            elif self.items:
                above = self.items[-1]
            if above:
                d["parent"] = above.key()
                d["after"] = above.children[-1].key() if above.children else None

    def submit(self, keep_going=True):
        """Save the typed line. keep_going: open the next line below (Enter); False for ↑↓."""
        d, self.draft = self.draft, None
        if d and d["edit"] and d.get("rename") is None and not clean(d["text"]):
            it = find(self.items, d["edit"])
            if it and it.children:
                n = len(it.children)
                self.confirm = ("delete", d["edit"])
                self.say(f"delete it and its {n} sub-item{'s' if n > 1 else ''}? y to delete, any key keeps", 30)
            elif it:
                self.delete_item(d["edit"])
            return False
        if d and d.get("rename") is not None:
            old = d["rename"]
            new = re.sub(r"[^\w.\-]", "", clean(d["text"]).lstrip("#").replace(" ", "-"))[:24]
            if new != old:
                def op(items):
                    for it in items:
                        if it.cat == old:
                            it.cat = new            # sub-items inherit through their parent
                        for c in it.children:
                            if c.cat == old:
                                c.cat = "" if (it.cat == new or not new) else new
                self.apply(op)
                self.say(f"renamed to {new}" if new else "category cleared")
            return False
        if not d or not clean(d["text"]):
            return False
        body, cat, due = parse_entry(d["text"], known_categories(self.items))
        if d["edit"]:
            key = d["edit"]

            def op(items):
                it = find(items, key)
                if not it:
                    return
                it.text = body or it.text
                if cat:
                    it.cat = cat
                new_due, old = due, parse_ymd(it.due)
                if new_due and old and parse_ymd(new_due).strftime("%m%d") == old.strftime("%m%d"):
                    new_due = it.due    # same MM/DD as shown in the edit: keep the stored year
                if new_due and new_due != it.due:
                    it.was = it.was or it.due or new_due
                    it.due = new_due
            self.apply(op)
            new_key = (body or key[0], key[1])
            if keep_going:
                self.draft = self.new_line_after(find(self.items, new_key))   # Enter goes on to a new line
            self.rows = self.visible()
            self.select_key(new_key)
            return True
        body = body[:MAX_TEXT].rstrip()             # the cap holds even for a half-typed field
        if not body:
            return False
        if not cat and not d["parent"]:
            cat = d.get("cat", "")                   # typed inside a group: it belongs there
        key = add_item(body, cat, due, under=d["parent"], after=d["after"])
        self.reload()
        # Enter keeps you writing: a fresh line right below, at the same level.
        if keep_going:
            self.draft = self.new_line_after(find(self.items, key))
        self.rows = self.visible()
        self.select_key(key)
        return True

    # actions
    def toggle(self, state, it=None):
        cur = it or self.current()
        if cur is None:
            return
        key = cur.key()
        if self.view == "closed":
            src = self.rows[self.sel][2] if 0 <= self.sel < len(self.rows) else "wall"
            if src == "done":
                restore_from_done(key)
            else:
                self.apply(lambda items: find(items, key) and reopen(find(items, key)))
            self.reload()
            self.say("back on the wall")
            return
        if cur.is_open and state == "x" and any(c.is_open for c in cur.children):
            n = sum(c.is_open for c in cur.children)
            self.confirm = (key, state)
            self.say(f"also close {n} sub-item{'s' if n > 1 else ''}? y/n", 30)
            return
        self._toggle(key, state)

    def toggle_star(self, it=None):
        cur = it or self.current()
        if not isinstance(cur, Item) or self.view != "wall" or not cur.is_open:
            return
        key = cur.key()

        def op(items):
            x = find(items, key)
            if x and x.is_open:
                x.star = not x.star
                return x.star
            return None
        r = self.apply(op)
        if r is not None:
            self.say("starred" if r else "star off")

    def _toggle(self, key, state):
        def op(items):
            it = find(items, key)
            if not it:
                return None
            if it.is_open:
                close(it, state)
                for c in it.children:
                    if c.is_open:
                        close(c, state)
                return "closed"
            if it.state == state:
                reopen(it)
                return "opened"
            close(it, state)
            return "closed"
        r = self.apply(op)
        if r == "closed" and state == "x":
            self.flash[key] = time.time()

    def move(self, step):
        cur = self.current()
        if not isinstance(cur, Item) or self.view != "wall":
            return
        key = cur.key()
        # Top-level items move past the neighbour on screen, which in grouped view is the
        # next item of the same group, or the edge item of the next group (it joins that group).
        shown = [r[1].key() for r in self.base_rows() if r[0] == "item" and r[2] == 0]

        def op(items):
            it = find(items, key)
            if not it:
                return
            if it.parent:
                sib = it.parent.children
                i = sib.index(it)
                j = i + step
                if 0 <= j < len(sib):
                    sib[i], sib[j] = sib[j], sib[i]
                return
            i = shown.index(key) if key in shown else -1
            j = i + step
            if i < 0 or not 0 <= j < len(shown):
                return
            other = find(items, shown[j])
            if not other:
                return
            items.remove(it)
            items.insert(items.index(other) + (1 if step > 0 else 0), it)
            if self.group:
                it.cat = other.cat
        self.apply(op)
        self.rows = self.visible()
        self.select_key(key)

    def drop(self, key, target_key, below, group_cat=None):
        """Drag and drop: put `key` above or below `target_key` (None = end of the list).
        An item with sub-items always stays top level, so nesting never goes past two.
        group_cat (grouped view): the category of the group it was dropped into."""
        def op(items):
            it = find(items, key)
            if not it:
                return
            tgt = find(items, target_key) if target_key else None
            if tgt is it:
                return
            siblings(items, it).remove(it)
            was_parent = it.parent
            if tgt is None:
                it.parent = None
                items.append(it)
            elif tgt.parent and not it.children:
                kids = tgt.parent.children
                it.parent = tgt.parent
                kids.insert(kids.index(tgt) + (1 if below else 0), it)
            else:
                top = tgt.parent or tgt
                it.parent = None
                items.insert(items.index(top) + (1 if below else 0), it)
            if was_parent and not it.parent:
                it.cat = it.cat or was_parent.cat
            if group_cat is not None and not it.parent:
                it.cat = group_cat
            if it.parent and it.cat == it.parent.cat:
                it.cat = ""
        self.apply(op)
        self.rows = self.visible()
        self.select_key(key)

    def indent(self, out, key=None):
        if key is None:
            cur = self.current()
            if not isinstance(cur, Item) or self.view != "wall":
                return
            key = cur.key()

        def op(items):
            it = find(items, key)
            if not it:
                return
            if out and it.parent:
                p = it.parent
                p.children.remove(it)
                it.parent = None
                it.cat = it.cat or p.cat
                items.insert(items.index(p) + 1, it)
            elif not out and not it.parent and not it.children:
                i = items.index(it)
                if i > 0:
                    p = items[i - 1]
                    items.remove(it)
                    it.parent = p
                    if it.cat == p.cat:
                        it.cat = ""
                    p.children.append(it)
        self.apply(op)
        self.rows = self.visible()
        self.select_key(key)

    # input
    def type_burst(self, text):
        """Several printable characters in one read: typing or dictation (voxtype), never commands."""
        if self.draft:
            self.insert(text)
        elif text.strip():
            self.start_draft(text.lstrip())

    # the line being typed: text plus a cursor position
    def cursor(self):
        d = self.draft
        d["pos"] = max(0, min(len(d["text"]), d.get("pos", len(d["text"]))))
        return d["pos"]

    def insert(self, text):
        self.cut_selection()
        d, i = self.draft, self.cursor()
        text = re.sub(r"\s*[\r\n]+\s*", " ", text)    # a line holds one line
        if d.get("rename") is None:
            # The 44-character cap: typing stops once the item's text is full. Fields typed or
            # spoken at the end (#cat, ^fri, "due friday") don't count, since saving strips them.
            room = max(0, MAX_TEXT - text_length(d["text"]))
            if text_length(d["text"][:i] + text + d["text"][i:]) > MAX_TEXT:
                text = text[:room] if not field_tail(d["text"][:i] + text) else text
                if not text:
                    self.say(f"{MAX_TEXT} characters is the limit")
                    return
        d["text"] = d["text"][:i] + text + d["text"][i:]
        d["pos"] = i + len(text)

    def selection(self):
        """(start, end) of the selected text in the typed line, or None."""
        d = self.draft
        a = d.get("anchor")
        if a is None or a == self.cursor():
            return None
        a = max(0, min(len(d["text"]), a))
        return (min(a, d["pos"]), max(a, d["pos"]))

    def cut_selection(self):
        """Remove the selected text; returns it ('' if nothing was selected)."""
        d, r = self.draft, self.selection()
        d["anchor"] = None
        if not r:
            return ""
        a, b = r
        gone = d["text"][a:b]
        d["text"], d["pos"] = d["text"][:a] + d["text"][b:], a
        return gone

    # Keys that edit the typed line. Shift extends a selection; plain moves clear it.
    MOVES = {"\x1b[D": "left", "\x1b[C": "right", "\x1b[1;5D": "wordleft", "\x1b[1;3D": "wordleft",
             "\x1b[1;5C": "wordright", "\x1b[1;3C": "wordright", "\x1b[H": "home", "\x1bOH": "home",
             "\x1b[1~": "home", "\x1b[F": "end", "\x1bOF": "end", "\x1b[4~": "end", "\x05": "end"}
    SHIFT_MOVES = {"\x1b[1;2D": "left", "\x1b[1;2C": "right", "\x1b[1;6D": "wordleft",
                   "\x1b[1;6C": "wordright", "\x1b[1;2H": "home", "\x1b[1;2F": "end"}

    def target(self, move):
        d, i = self.draft, self.cursor()
        t = d["text"]
        if move == "left":
            return max(0, i - 1)
        if move == "right":
            return min(len(t), i + 1)
        if move == "wordleft":
            return len(re.sub(r"\S*\s*$", "", t[:i]))
        if move == "wordright":
            return i + re.match(r"\s*\S*", t[i:]).end()
        return 0 if move == "home" else len(t)

    def line_key(self, key):
        d = self.draft
        if key in self.SHIFT_MOVES:
            if d.get("anchor") is None:
                d["anchor"] = self.cursor()
            d["pos"] = self.target(self.SHIFT_MOVES[key])
            return True
        if key in self.MOVES:
            r = self.selection()
            move = self.MOVES[key]
            if r and move in ("left", "right"):
                d["pos"] = r[0] if move == "left" else r[1]   # collapse to that edge
            else:
                d["pos"] = self.target(move)
            d["anchor"] = None
            return True
        if key == "\x01":                                  # ctrl+a: select the whole line
            d["anchor"], d["pos"] = 0, len(d["text"])
            return True
        if key == "\x03":                                  # ctrl+c: copy (the line if nothing selected)
            r = self.selection()
            clip_copy(d["text"][r[0]:r[1]] if r else d["text"])
            self.say("copied")
            return True
        if key == "\x18":                                  # ctrl+x: cut (the line if nothing selected)
            if not self.selection():
                d["anchor"], d["pos"] = 0, len(d["text"])
            clip_copy(self.cut_selection())
            self.say("cut")
            return True
        if key == "\x16":                                  # ctrl+v: paste
            self.insert(clip_paste())
            return True
        if key in ("\x7f", "\x08"):                        # backspace
            if not self.cut_selection():
                i = self.cursor()
                if i:
                    d["text"], d["pos"] = d["text"][:i - 1] + d["text"][i:], i - 1
            return True
        if key == "\x1b[3~":                               # delete
            if not self.cut_selection():
                i = self.cursor()
                d["text"] = d["text"][:i] + d["text"][i + 1:]
            return True
        if key == "\x15":                                  # ctrl+u: clear to the start
            d["anchor"] = None
            i = self.cursor()
            d["text"], d["pos"] = d["text"][i:], 0
            return True
        if key == "\x17":                                  # ctrl+w: word back
            d["anchor"] = None
            i = self.cursor()
            head = re.sub(r"\S*\s*$", "", d["text"][:i])
            d["text"], d["pos"] = head + d["text"][i:], len(head)
            return True
        return False

    def handle(self, key):
        if self.confirm:
            k, st = self.confirm
            self.confirm, self.note_until = None, 0
            if k == "delete":
                if key in ("y", "Y"):            # only a deliberate y deletes; Enter doesn't
                    self.delete_item(st)
            elif key in ("y", "Y", "\r"):
                self._toggle(k, st)
            return
        if self.draft:
            d = self.draft
            if key in ("\r", "\n"):
                self.submit()
            elif key in ("\x1b[A", "\x1b[B"):            # ↑↓ leave the line (saved) and move
                step = -1 if key == "\x1b[A" else 1
                if clean(d["text"]):
                    self.submit(keep_going=False)        # selects the saved line
                    self.move_sel(step)
                else:
                    anchor = self.draft_anchor()
                    self.draft = None
                    self.rows = self.visible()
                    if anchor:
                        self.select_key(anchor)
                    # an empty new line sits just below its anchor: ↑ lands on the anchor itself
                    if d["edit"] or step > 0 or not anchor:
                        self.move_sel(step)
            elif key == "\x1b":
                self.draft = None
            elif self.line_key(key):
                pass                                       # cursor, selection, clipboard
            elif key in ("\t", "\x1b[Z") and d.get("rename") is not None:
                pass                                       # a category label has no levels
            elif key == "\t":
                self.draft_indent(False)
            elif key == "\x1b[Z":
                self.draft_indent(True)
            elif len(key) == 1 and key.isprintable():
                self.insert(key)
            return
        if self.view == "help":
            self.view = "wall"
            return
        if key == "\x1b[A":
            self.move_sel(-1)
        elif key == "\x1b[B":
            self.move_sel(1)
        elif key == " ":
            self.toggle("x")
        elif key == "\x1b[3~" and self.view == "wall":
            self.toggle("-")
        elif key in ("\r", "\n") and self.view == "wall":
            self.start_draft()                       # Enter: a new line below the current one
        elif key in ("\x1b[C", "\x05", "\x1bOQ", "\x1b[12~") and self.view == "wall" \
                and isinstance(self.current(), Item):
            self.start_edit(self.current())          # → (step into the line), ctrl+e or F2: edit it
        elif key in ("\x1b[1;2A", "\x1b[1;3A", "\x1b\x1b[A"):    # shift/alt+↑ move up
            self.move(-1)
        elif key in ("\x1b[1;2B", "\x1b[1;3B", "\x1b\x1b[B"):    # shift/alt+↓ move down
            self.move(1)
        elif key == "\t":
            self.indent(False)
        elif key == "\x1b[Z":
            self.indent(True)
        elif key == "\x03" and isinstance(self.current(), Item):     # ctrl+c: copy the item
            clip_copy(item_lines(self.current()))
            self.say("copied")
        elif key == "\x18" and isinstance(self.current(), Item) and self.view == "wall":   # ctrl+x
            self.cut_item(self.current())
        elif key == "\x16" and self.view == "wall":                  # ctrl+v: paste as items
            self.paste_items(clip_paste())
        elif key == "\x13" and self.view == "wall":                  # ctrl+s: star / unstar
            self.toggle_star()
        elif key == "\x07":       # ctrl+g
            self.toggle_group()
        elif key == "\x0f":       # ctrl+o
            self.toggle_closed()
        elif key == "\x14":       # ctrl+t
            self.detail = not self.detail
        elif key in ("\x1bOP", "\x1b[11~"):   # F1
            self.view = "help"
        elif key == "\x1b":
            self.view, self.sel = "wall", -1
        elif len(key) == 1 and key.isprintable():
            self.start_draft(key)

    def cut_item(self, cur):
        """Copy an item (with its sub-items) to the clipboard and take it off the list.
        A copy also goes to the done file, marked cut, so nothing is ever lost."""
        if not clip_copy(item_lines(cur)):
            self.say("clipboard unavailable, item kept")
            return
        key = cur.key()
        # Land on whatever follows the cut item (and its sub-items), else the one before.
        mine = {cur.key()} | {c.key() for c in cur.children}
        rest = [r[1].key() for r in self.rows if r[0] == "item" and r[1].key() not in mine]
        order = [r[1].key() for r in self.rows if r[0] == "item"]
        i = order.index(key)
        after = [k for k in order[i + 1:] if k not in mine]
        land = after[0] if after else (rest[-1] if rest else None)

        self.remove_item(key, "cut")
        self.rows = self.visible()
        if land:
            self.select_key(land)
        self.say("cut")

    def remove_item(self, key, why):
        """Take an item (and its sub-items) off the list. A copy goes to the done file,
        marked with why ("cut", "deleted"), so a slip can always be recovered."""
        def op(items):
            it = find(items, key)
            if not it:
                return
            siblings(items, it).remove(it)
            append_done([archive_line(x, why) for x in [it] + it.children])   # copy first
        self.apply(op)

    def delete_item(self, key):
        """Delete an item whose text was cleared; land on the item that was below it."""
        order = [r[1].key() for r in self.base_rows() if r[0] == "item"]
        it = find(self.items, key)
        mine = {key} | ({c.key() for c in it.children} if it else set())
        after = [k for k in order[order.index(key) + 1:] if k not in mine] if key in order else []
        before = [k for k in order[:order.index(key)] if k not in mine] if key in order else []
        self.remove_item(key, "deleted")
        self.rows = self.visible()
        land = (after or before[-1:] or [None])[0]
        if land:
            self.select_key(land)
        self.say("deleted (a copy is in the done file)")

    def paste_items(self, text):
        """Each pasted line becomes an item after the current one; indented lines become sub-items."""
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return
        cur = self.current() if isinstance(self.current(), Item) else None
        after = cur.key() if cur else None
        parent = cur.parent.key() if cur and cur.parent else None
        top = None
        cats = known_categories(self.items)
        for raw in lines:
            sub = raw[:1] in (" ", "\t") and top is not None
            line = re.sub(r"^\s*(?:[-*•]\s*)?(?:\[[ xX\-]\]\s*)?", "", raw)
            body, cat, due = parse_entry(line, cats)
            if not body:
                continue
            if sub:
                add_item(body, cat, due, under=top)
            else:
                after = add_item(body, cat, due, under=parent, after=after)
                top = after if not parent else None
        self.reload()
        self.say(f"pasted {len(lines)} item{'s' if len(lines) > 1 else ''}")

    def paste(self, text):
        """Text pasted through the terminal: into the open line, or as new items."""
        if self.confirm:
            self.handle("\x00")
        elif self.draft:
            self.insert(text)
        elif self.view == "wall":
            self.paste_items(text)

    def toggle_group(self):
        self.group = not self.group
        self.say("grouped by category" if self.group else "your order")

    def toggle_closed(self):
        self.draft = None
        self.view = "wall" if self.view == "closed" else "closed"
        self.sel = -1

    def mouse(self, b, x, y, down):
        if b in (64, 65) and down:
            self.move_sel(-1 if b == 64 else 1)
            return
        if b == 0 and down and self.draft and self.view == "wall":
            idx = self.row_y.get(y)
            if idx is None or self.rows[idx][0] != "draft":
                # A press elsewhere ends the open line (saved if it has text), then acts normally.
                draft_idx = next((i for i, r in enumerate(self.rows) if r[0] == "draft"), None)
                new_line = not self.draft["edit"] and self.draft.get("rename") is None
                if clean(self.draft["text"]):
                    self.submit(keep_going=False)
                else:
                    self.draft = None
                self.rows = self.visible()
                if idx is not None and draft_idx is not None and new_line and idx > draft_idx:
                    idx -= 1                       # rows below the closed new line moved up one
                self.press = {"idx": idx, "y": y, "x": x, "moved": False, "drop": None}
                return
        if b == 0 and down:                       # press
            if y == 1:
                for name, (x0, x1) in self.header_hits.items():
                    if x0 <= x <= x1:
                        self.toggle_group() if name == "group" else self.toggle_closed()
                return
            self.press = {"idx": self.row_y.get(y), "y": y, "x": x, "moved": False, "drop": None}
            return
        if b == 32 and down and self.press:       # drag (motion with the button held)
            p = self.press
            if p["idx"] is not None and y != p["y"] and not self.draft and self.view == "wall":
                p["moved"] = True
                p["drop"] = y
            return
        if not down and self.press:               # release
            p, self.press = self.press, None
            if p["moved"]:
                self.finish_drag(p)
            else:
                self.click(p["x"], p["y"])

    def finish_drag(self, p):
        src = self.rows[p["idx"]] if p["idx"] is not None and p["idx"] < len(self.rows) else None
        if not src or src[0] != "item":
            return
        idx = self.row_y.get(p["drop"])
        below = p["drop"] > p["y"]
        if idx is None:
            if p["drop"] >= self.list_end_y:
                self.drop(src[1].key(), None, True)
            return
        tgt = self.rows[idx]
        if tgt[0] == "item":
            cat = (tgt[1].parent or tgt[1]).cat if self.group else None
            self.drop(src[1].key(), tgt[1].key(), below, cat)
        elif tgt[0] == "rule" and self.group:
            # dropped on a category label: to the top of that group
            first = next((r for r in self.rows[idx + 1:] if r[0] == "item"), None)
            if first:
                self.drop(src[1].key(), first[1].key(), False, tgt[1])

    def click(self, x, y):
        if self.confirm:
            return
        idx = self.row_y.get(y)
        if idx is None:
            if y >= self.list_end_y and self.view == "wall":
                if self.draft and clean(self.draft["text"]):
                    self.submit()
                    self.draft = None
                self.sel = -1
                self.start_draft(at_end=True)    # click below the list: a new line at the end
            return
        kind, it, depth = self.rows[idx]
        if kind == "draft":
            if self.draft_x0 is not None:              # click inside the line moves the cursor
                self.draft["pos"] = self.draft_off + max(0, x - self.draft_x0)
                self.cursor()
            return
        if self.draft:
            if clean(self.draft["text"]):
                self.submit()
            self.draft = None
            self.rows = self.visible()
            if isinstance(it, Item):
                self.select_key(it.key())
            return
        if kind == "rule" and self.group:
            self.draft = {"text": it, "pos": len(it), "parent": None, "after": None, "edit": None,
                          "cat": "", "rename": it}
            return
        if kind in ("rule", "gap"):
            return
        self.sel = idx
        circle_x = 5 + (4 if (kind == "item" and depth) else 0)
        if x <= 2 and kind == "item" and y in self.row_first:
            self.toggle_star(it)               # the star column (and the pointer beside it)
        elif x <= circle_x + 1 and y in self.row_first:
            self.toggle("x", it)
        elif kind == "closed":
            self.toggle("x", it)
        else:
            self.start_edit(it)

    # drawing
    def draw(self, cols, rows_n):
        refresh_palette()
        w = max(24, cols)
        prev = self.current()
        self.rows = self.visible()
        if isinstance(prev, Item) and self.view == "wall":
            self.select_key(prev.key())     # selection follows the item when the view changes
        if self.sel >= len(self.rows):
            self.sel = -1
        open_n = sum(x.is_open for it in self.items for x in [it] + it.children)
        due_n = sum(1 for it in self.items for x in [it] + it.children
                    if x.is_open and parse_ymd(x.due) and parse_ymd(x.due) <= today())
        title = "closed" if self.view == "closed" else "todo"
        count = f"{open_n} open" + (f" · {due_n} due" if due_n else "")
        # The mark: the Nerd Font checkbox (nf-md-checkbox_marked_outline) in orange, the way
        # a single orange mark, quiet next to the title.
        mark = fg(C["orange"], "\U000f0856")
        g_txt = "grouped" if self.group else "group"
        c_txt = "← back" if self.view == "closed" else "closed"
        left_w = width(f" x {title}  {count}")
        right_w = width(f"{g_txt}  {c_txt}")
        pad = max(2, w - left_w - right_w - 1)
        x0 = left_w + pad + 1
        self.header_hits = {"group": (x0, x0 + width(g_txt) - 1),
                            "closed": (x0 + width(g_txt) + 2, x0 + width(g_txt) + 1 + width(c_txt))}
        gcol = C["accent"] if self.group else C["muted"]
        ccol = C["accent"] if self.view == "closed" else C["muted"]
        out = [f" {mark} {fg(C['light_foreground'], title)}  {fg(C['accent'], count)}"
               + " " * pad + fg(gcol, g_txt) + "  " + fg(ccol, c_txt), ""]
        if self.view == "help":
            for line in HELP.strip().splitlines():
                out.append(" " + fg(C["muted"], clip(line, w - 2)))
            out.append("")
            out.append(" " + fg(C["muted"], "any key to go back"))
            self.row_y, self.list_end_y = {}, rows_n
            return out
        footer_h = len(wrap_hints(self.footer_text(), w - 2))
        avail = max(1, rows_n - len(out) - footer_h)
        colors = cat_colors()
        now = time.time()
        drop_y = self.press["drop"] if self.press and self.press["moved"] else None
        # Rows can wrap onto several lines in a narrow tile, so scrolling works in lines.
        drawn = []
        for idx, (kind, it, depth) in enumerate(self.rows):
            selected = idx == self.sel and not self.draft     # while typing, only the new line is marked
            lines = self.draw_row(kind, it, depth, selected, w, colors, now)
            drawn.append(lines if isinstance(lines, list) else [lines])
        heights = [len(d) for d in drawn]
        focus = next((i for i, r in enumerate(self.rows) if r[0] == "draft"), self.sel)

        def fits(top):
            """Lines available for rows when the list starts at `top` (markers take a line each)."""
            room = avail - (1 if top > 0 else 0)
            used, last = 0, top
            for i in range(top, len(heights)):
                if used + heights[i] > room:
                    break
                used, last = used + heights[i], i + 1
            if last < len(heights):
                room -= 1                                  # the "more below" marker
                while last > top and sum(heights[top:last]) > room:
                    last -= 1
            return last

        if focus >= 0:
            self.top = min(self.top, focus)
            while self.top < focus and fits(self.top) <= focus:
                self.top += 1
        while self.top > 0 and fits(self.top - 1) >= len(heights):
            self.top -= 1                                  # no empty space at the bottom when scrolled
        self.top = max(0, min(self.top, max(0, len(self.rows) - 1)))
        end = fits(self.top)
        self.row_y, self.row_first = {}, set()
        if self.top > 0:
            out.append("  " + fg(C["muted"], f"↑ {self.top} more"))
        for idx in range(self.top, end):
            self.row_first.add(len(out) + 1)
            for k, line in enumerate(drawn[idx]):
                y = len(out) + 1
                self.row_y[y] = idx
                if k == 0 and y == drop_y and self.rows[idx][0] == "item":
                    line = self.draw_row(*self.rows[idx], False, w, colors, now, drop=True)
                    line = line[0] if isinstance(line, list) else line
                out.append(line)
        self.list_end_y = len(out) + 1
        if end < len(self.rows):
            out.append("  " + fg(C["muted"], f"↓ {len(self.rows) - end} more"))
        if not self.rows:
            msg = "nothing closed yet" if self.view == "closed" else "just start typing, or talk (ctrl+space)"
            out.append("  " + fg(C["muted"], msg))
        lines = wrap_hints(self.footer_text(), w - 2)
        out = out[:max(0, rows_n - len(lines))]
        while len(out) < rows_n - len(lines):
            out.append("")
        out += [" " + fg(C["muted"], l) for l in lines]      # always the last lines of the pane
        return out

    def footer_text(self):
        if time.time() < self.note_until:
            return self.note
        if self.press and self.press["moved"]:
            return "drop to move"
        if self.draft and self.draft.get("rename") is not None:
            return "⏎ rename the whole category  esc cancel  empty = no category"
        if self.draft:
            n = text_length(self.draft["text"])
            return f"{n}/{MAX_TEXT}  ⏎ next line  esc done  tab indent  “friday 10am”  #cat"
        if self.view == "closed":
            return "click or space reopen  esc back"
        return "type add  ⏎ new line  → edit  space done  ctrl+s star  del retire  tab indent  shift↑↓ move  F1 help"

    def draw_row(self, kind, it, depth, selected, w, colors, now, drop=False):
        if kind == "gap":
            return ""
        if kind == "rule":
            return "  " + fg(C["accent"], it) + " " + fg(C["selection"], "─" * max(0, w - width(it) - 5))
        if kind == "draft" and it.get("rename") is not None:
            text, pos = it["text"], self.cursor()
            self.draft_x0, self.draft_off = 3, 0
            shown = render_input(text, pos, self.selection(), C["accent"])
            return "  " + shown + " " + fg(C["selection"], "─" * max(0, w - width(text) - 6))
        if kind == "draft":
            indent = "    " if depth else ""
            room = max(8, w - 9 - len(indent))
            text, pos = it["text"], self.cursor()
            off = max(0, pos - room + 1) if pos >= room else 0     # keep the cursor in view
            shown = text[off:off + room]
            i = pos - off
            self.draft_x0, self.draft_off = 8 + len(indent), off
            r = self.selection()
            sel = (r[0] - off, r[1] - off) if r else None
            return (f"  {fg(C['orange'], '›')} {indent}{fg(C['accent'], '○')} "
                    + render_input(shown, i, sel, C["light_foreground"]))
        if kind == "closed":
            x = it
            d = parse_ymd(x.closed)
            stamp = d.strftime("%m/%d") if d else "     "
            glyph = "●" if x.state == "x" else "⊘"
            meta = x.cat[:8]
            text = clip(x.text, w - 18 - width(meta))
            line = f"  {fg(C['orange'], '›') if selected else ' '} {fg(C['muted'], glyph)} {fg(C['muted'], stamp)} {fg(C['muted'], text, strike=True)}"
            return line + " " * max(1, w - 11 - width(stamp) - width(text) - width(meta)) + fg(C["muted"], meta)
        flash = self.flash.get(it.key(), 0)
        flashing = now - flash < self.FLASH
        meta_parts = []
        if self.detail:
            c = parse_ymd(it.created)
            meta_parts.append(fg(C["muted"], "+" + c.strftime("%m/%d")) if c else "")
            cl = parse_ymd(it.closed)
            if cl:
                meta_parts.append(fg(C["muted"], ("✓" if it.state == "x" else "✗") + cl.strftime("%m/%d")))
        if it.cat and depth == 0 and not self.group:
            ccol = color_for(colors.get(it.cat.lower(), "muted"))
            meta_parts.append(fg(ccol, clip(it.cat, 8)))
        due_d = parse_ymd(it.due)
        # The date column is always reserved (6 cells: MM/DD plus a ↻ slot), so categories
        # line up in their own column whether or not an item has a date.
        if due_d:
            col, overdue = due_style(it.due) if it.is_open else (C["muted"], False)
            moved = fg(C["muted"], "↻") if it.was and it.was != it.due else " "
            meta_parts.append(fg(col, due_d.strftime("%m/%d"), bold=overdue) + moved)
        elif depth == 0 and (it.cat or it.by_agent) and not self.group:
            meta_parts.append(" " * 6)
        if it.by_agent:
            meta_parts.insert(0, fg(C["accent"], "·"))
        meta = " ".join(m for m in meta_parts if m)
        # Sub-item progress sits right after the text, as the same circles the items use,
        # so it can never be read as a date (the right edge holds only category and date).
        prog, prog_w = "", 0
        if it.children:
            done = sum(not c.is_open for c in it.children)
            n = len(it.children)
            # Full-size circles with a space between, so a finished one is clearly filled.
            k = min(done, 6)
            filled = " ".join(["●"] * k)
            empty = " ".join(["○"] * (min(n, 6) - k))
            prog = "  " + fg(C["accent"], filled) + (" " if filled and empty else "") + fg(C["muted"], empty)
            if n > 6:
                prog += fg(C["muted"], f" +{n - 6}")
            prog_w = width(re.sub(r"\033\[[0-9;]*m", "", prog))
        meta_w = width(re.sub(r"\033\[[0-9;]*m", "", meta))
        indent = "    " if depth else ""
        pointer = fg(C["orange"], "▸" if drop else "›") if (selected or drop) else " "
        if it.is_open:
            glyph = fg(C["accent"] if depth == 0 else C["muted"], "○")
            _, overdue = due_style(it.due) if due_d else (None, False)
            # Body text in the theme's foreground, sub-items a
            # step dimmer; near-white light_foreground on every line made the pane read grey.
            tcol = C["orange"] if overdue else (C["foreground"] if depth == 0 else C["dark_foreground"] if "dark_foreground" in C else C["muted"])
            if selected and not overdue:
                tcol = C["light_foreground"]     # the current line stands out by brightness
            strike = False
        elif it.state == "x":
            glyph = fg(C["orange"], "●") if flashing else fg(C["muted"], "●")
            tcol, strike = (C["orange"] if flashing else C["muted"]), not flashing or (now - flash) > self.FLASH / 2
        else:
            glyph = fg(C["muted"], "⊘")
            tcol, strike = C["muted"], True
        if self.press and self.press["moved"] and self.press["idx"] is not None \
                and self.rows[self.press["idx"]][1] is it:
            tcol = C["accent"]                 # the item being dragged
        room = max(6, w - 6 - len(indent) - meta_w - prog_w - 2)

        def paint(t):
            return fg(tcol, t, strike=strike) if strike or tcol == C["orange"] else with_times(t, tcol)
        parts = wrap_words(it.text, room, max(6, w - 7 - len(indent)))
        first = parts[0]
        gap = " " * max(1, w - 6 - len(indent) - width(first) - prog_w - meta_w - 1)
        lit = it.star and it.is_open
        star = fg(C["yellow"], "★") if lit else fg(C["selection"], "☆") if it.is_open else " "
        lines = [f"{star} {pointer} {indent}{glyph} {paint(first)}{prog}{gap}{meta}"]
        lead = " " * (6 + len(indent))                    # continuation lines align under the text
        lines += [lead + paint(part) for part in parts[1:]]
        if lit:
            lines = [highlight(l, w) for l in lines]
        return lines if len(lines) > 1 else lines[0]


def blend(a, b, t):
    """Hex color a mixed into b: t=0 is all b, t=1 all a."""
    ca, cb = ([int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in (a, b))
    return tuple(round(x * t + y * (1 - t)) for x, y in zip(ca, cb))


def highlight(line, w):
    """A starred row: a highlighter wash of the theme's yellow behind the whole line."""
    r, g, b = blend(C["yellow"], C["background"], 0.22)
    bg = f"\033[48;2;{r};{g};{b}m"
    vis = width(re.sub(r"\033\[[0-9;]*m", "", line))
    return bg + line.replace("\033[0m", "\033[0m" + bg) + " " * max(0, w - 1 - vis) + "\033[0m"


def render_input(text, pos, sel, color):
    """A typed line: selected text on the theme's selection teal, the cursor as an orange block."""
    def rgb(h, layer):
        return f"\033[{layer};2;{int(h[1:3], 16)};{int(h[3:5], 16)};{int(h[5:7], 16)}m"
    out, chars = "", list(text) + [" "]
    for i, ch in enumerate(chars):
        if i == pos:
            out += rgb(C["orange"], 48) + rgb(C["background"], 38) + ch + "\033[0m"
        elif sel and sel[0] <= i < sel[1]:
            out += rgb(C["selection"], 48) + rgb(C["bright_foreground"] if "bright_foreground" in C else C["light_foreground"], 38) + ch + "\033[0m"
        elif i < len(text):
            out += rgb(color, 38) + ch + "\033[0m"
    return out


# The whole rest of the line is a field: "#cat", "^fri", a keyword and its words
# ("due friday", "category home"), or a keyword still being typed ("du", "categ").
FIELD_START = re.compile(r"\s+(?:#\S*|\^\S*|(?:due|by|on|category|cat|tag)(?:\s.*)?|"
                         r"d|du|b|o|c|ca|cate|categ|catego|categor|t|ta)$", re.I)


def text_length(raw):
    """Length of an item's text once its trailing fields are taken off."""
    return len(parse_entry(raw)[0])


def field_tail(raw):
    """True while the end of a line is a field being typed (#cat, ^fri, due …, category …)."""
    # Find a space after which the rest reads as the start of a field, with the text before
    # it inside the cap: "…Plan due fr" is still a date being typed, not more text.
    for m in re.finditer(r"\s", raw):
        if FIELD_START.match(raw[m.start():]) and len(parse_entry(raw[:m.start()])[0]) <= MAX_TEXT:
            return True
    return False


def clip_copy(text):
    """System clipboard (Wayland), text on stdin. Returns False if it didn't take."""
    import subprocess
    try:
        return subprocess.run(["wl-copy"], input=text, text=True, timeout=2).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def clip_paste():
    import subprocess
    try:
        r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=2)
        if r.returncode != 0:
            return ""
        # Filter each line on its own: CONTROL also matches newlines, which must survive.
        return "\n".join(CONTROL.sub("", line.replace("\t", "  ")) for line in r.stdout.splitlines())
    except (OSError, subprocess.SubprocessError):
        return ""


def item_lines(it):
    """An item as plain text for the clipboard: the line, then its sub-items indented."""
    def one(x):
        due = parse_ymd(x.due)
        return x.text + (f" #{x.cat}" if x.cat else "") + (f" ^{due:%m/%d}" if due else "")
    return "\n".join([one(it)] + ["  " + one(c) for c in it.children])


TIME_IN_TEXT = re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)(?![a-z])|\bnoon\b|\bmidnight\b", re.I)


def with_times(text, color):
    """Item text with any clock time in it (10am, 3:30pm, noon) in brand orange."""
    out, i = "", 0
    for m in TIME_IN_TEXT.finditer(text):
        out += fg(color, text[i:m.start()]) + fg(C["orange"], m.group())
        i = m.end()
    return out + fg(color, text[i:])


def wrap_words(text, n, rest=None):
    """Wrap text at word boundaries: the first line holds n columns, later lines `rest`
    (default n). A word only splits when it is longer than a whole line."""
    rest = rest or n
    lines, cur = [], ""

    def limit():
        return n if not lines else rest
    for word in text.split(" "):
        trial = f"{cur} {word}" if cur else word
        if width(trial) <= limit():
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while width(word) > limit():                       # a word longer than a whole line
            lines.append(word[:limit()])
            word = word[len(lines[-1]):]
        cur = word
    lines.append(cur)
    return lines


def wrap_hints(text, n):
    """Split a hint line (double-space separated) into at most two lines."""
    if width(text) <= n:
        return [text]
    parts, lines, cur = text.split("  "), [], ""
    for part in parts:
        trial = f"{cur}  {part}" if cur else part
        if width(trial) > n and cur:
            lines.append(cur)
            cur = part
        else:
            cur = trial
    lines.append(cur)
    return lines[:1] + [clip("  ".join(lines[1:]), n)] if len(lines) > 1 else lines


HELP = """
Add      just start typing, or talk (ctrl+space)
         enter on a line starts a new one below it
         click below the list for a new line at the end
         enter saves and opens the next line · esc stops
         ←→ move the cursor · home/end · ctrl+←→ by word
         tab / shift+tab indent the line · #cat ^fri or "due friday"
Check    click the circle, or space · del retires (won't do)
Star     click the ☆ at the left, or ctrl+s: highlights a priority
         the star clears when the item is done or retired
Edit     → steps into the line (cursor at the end) · click the text · F2
Delete   clear an item's text and press enter (a copy goes to the done file)
Move     drag a line · shift+↑↓ (sub-items come along) · tab / shift+tab indent
Views    click "group" or "closed" up top · ctrl+g · ctrl+o
         grouped: click a category label to rename it for every item in it
Copy     shift+←→ (ctrl for words, home/end) selects in a line · ctrl+a all
         ctrl+c copy · ctrl+x cut · ctrl+v paste (on an item: the whole item)
         pasted lines become items; indented lines become sub-items
         shift+drag selects anything on screen (the terminal's own selection)
Dates    ctrl+t shows created and closed dates
"""

MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"


def split_input(raw):
    """-> list of events: ("key", k) | ("text", s) | ("paste", s) | ("mouse", b, x, y, down).
    A run of two or more printable characters is a burst of typing or dictation."""
    events, i, buf = [], 0, ""

    def flush():
        nonlocal buf
        if len(buf) > 1:
            events.append(("text", buf))
        elif buf:
            events.append(("key", buf))
        buf = ""
    while i < len(raw):
        if raw.startswith(PASTE_START, i):                 # terminal paste: one text event
            flush()
            end = raw.find(PASTE_END, i)
            stop = end if end >= 0 else len(raw)
            events.append(("paste", raw[i + len(PASTE_START):stop]))
            i = stop + len(PASTE_END) if end >= 0 else len(raw)
            continue
        m = MOUSE.match(raw, i)
        if m:
            flush()
            events.append(("mouse", int(m[1]), int(m[2]), int(m[3]), m[4] == "M"))
            i = m.end()
            continue
        if raw[i] == "\x1b" and i + 1 < len(raw) and raw[i + 1] in "[O":
            flush()
            j = i + 2
            while j < len(raw) and not (raw[j].isalpha() or raw[j] == "~"):
                j += 1
            events.append(("key", raw[i:j + 1]))
            i = j + 1
            continue
        if raw[i] == "\x1b" and raw.startswith("\x1b\x1b[", i):
            flush()
            events.append(("key", raw[i:i + 4]))
            i += 4
            continue
        ch = raw[i]
        if ch.isprintable():
            buf += ch
        else:
            flush()
            events.append(("key", ch))
        i += 1
    flush()
    return events


DEBUG_FLAG = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "todo-pane-debug"


def debug_mouse(ev):
    """While the flag file $XDG_RUNTIME_DIR/todo-pane-debug exists, log raw mouse events
    beside it (todo-pane-debug.log). Diagnostics only: positions and buttons, no text."""
    if DEBUG_FLAG.exists():
        try:
            with open(str(DEBUG_FLAG) + ".log", "a", encoding="utf-8") as f:
                f.write(f"{time.time():.3f} {ev}\n")
        except OSError:
            pass


def compiles(path):
    """True if the file is complete, valid Python (an editor may be mid-save)."""
    try:
        compile(Path(path).read_text(encoding="utf-8"), str(path), "exec")
        return True
    except (OSError, SyntaxError, ValueError):
        return False


def run_pane():
    import codecs
    import select
    import shutil
    import termios
    import tty
    print("\033]2;todo\007", end="", flush=True)   # window title, so a window manager rule can find it
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IXON | termios.IXOFF)                  # ctrl+s / ctrl+q
    attrs[3] &= ~(termios.ISIG | termios.IEXTEN)                 # ctrl+c / ctrl+z / ctrl+v
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    dec = codecs.getincrementaldecoder("utf-8")(errors="ignore")
    # 1002: report presses, releases and drags; 1006: SGR coordinates
    sys.stdout.write("\033[?25l\033[?1002h\033[?1006h\033[?2004h")    # 2004: bracketed paste
    pane = Pane()
    me = Path(__file__).resolve()
    born = me.stat().st_mtime
    checked = time.time()
    pending = ""
    try:
        while True:
            # Hot reload: when this file changes, restart in place, but only between lines
            # (no typing in progress, no question pending), so an update never eats a draft.
            if time.time() - checked > 2:
                checked = time.time()
                try:
                    changed = me.stat().st_mtime != born
                except OSError:
                    changed = False
                if changed and not pane.draft and not pane.confirm and not pane.press and compiles(me):
                    termios.tcsetattr(fd, termios.TCSADRAIN, saved)
                    sys.stdout.write("\033[?1002l\033[?1006l\033[?2004l\033[?25h\033[0m")
                    sys.stdout.flush()
                    os.execv(sys.executable, [sys.executable, str(me)])
            ready, _, _ = select.select([fd], [], [], 1 / 20)
            if ready:
                pending += dec.decode(os.read(fd, 4096))
                if PASTE_START in pending and PASTE_END not in pending and len(pending) < 1 << 20:
                    continue                                # wait for the rest of the paste
                chunk, pending = pending, ""
                for ev in split_input(chunk):
                    if ev[0] == "key":
                        pane.handle(ev[1])
                    elif ev[0] == "text":
                        if pane.confirm:
                            pane.handle("\x00")          # typing or dictation never answers y/n
                        else:
                            pane.type_burst(ev[1])
                    elif ev[0] == "paste":
                        pane.paste(ev[1])
                    else:
                        debug_mouse(ev)
                        pane.mouse(*ev[1:])
            pane.reload()
            cols, rows = shutil.get_terminal_size((68, 25))
            frame = pane.draw(cols - 1, rows)
            sys.stdout.write("\033[H" + "".join(l + "\033[K\r\n" for l in frame[:-1]) + frame[-1] + "\033[K\033[J")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\033[?1002l\033[?1006l\033[?2004l\033[?25h\033[0m\n")


def cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="todo_pane.py", description="Sticky-note to-do pane and CLI.")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("add", help="add an item")
    a.add_argument("text")
    a.add_argument("--due", default="", help="fri, tomorrow, 10/20, oct 20 ...")
    a.add_argument("--cat", default="", help="free category label")
    a.add_argument("--under", default="", help="text of an open top-level item to nest under")
    sub.add_parser("list", help="print open items")
    st = sub.add_parser("star", help="star an open item (highlight it as a priority)")
    st.add_argument("text", help="the item's text, exactly")
    st.add_argument("--off", action="store_true", help="remove the star instead")
    args = ap.parse_args(argv)
    if args.cmd == "add":
        try:
            items = load()
        except OSError as e:
            print(f"Can't read the list: {clean(e.strerror or e)}", file=sys.stderr)
            return 1
        body, cat, due = parse_entry(args.text, known_categories(items))
        if args.due:
            d = parse_due(args.due)
            if not d:
                print(f"Could not read due date: {clean(args.due)}", file=sys.stderr)
                return 2
            due = ymd(d)
        if args.cat:
            cat = norm_cat(args.cat, known_categories(items))
        under = None
        if args.under:
            match = [it for it in items if it.is_open and it.text.lower() == args.under.lower()]
            if not match:
                print(f"No open item named: {clean(args.under)}", file=sys.stderr)
                return 2
            under = match[0].key()
        if len(body) > MAX_TEXT:
            print(f"Too long: {len(body)} characters; the limit is {MAX_TEXT} (spaces included). "
                  f"Shorten it: {body!r}", file=sys.stderr)
            return 2
        agent = bool(os.environ.get("TODO_PANE_AGENT") or os.environ.get("CLAUDECODE"))
        try:
            add_item(body, cat, due, under=under, by_agent=agent)
        except OSError as e:
            print(f"Not saved, the list is unchanged: {clean(e.strerror or e)}", file=sys.stderr)
            return 1
        d = parse_ymd(due)
        print(f"Added: {body}" + (f"  #{cat}" if cat else "") + (f"  due {d:%m/%d}" if d else ""))
        return 0
    if args.cmd == "star":
        want = not args.off

        def op(items):
            hits = [x for it in items for x in [it] + it.children
                    if x.is_open and x.text.lower() == args.text.lower()]
            for x in hits[:1]:
                x.star = want
            return bool(hits)
        try:
            found = mutate(op)
        except OSError as e:
            print(f"Not saved, the list is unchanged: {clean(e.strerror or e)}", file=sys.stderr)
            return 1
        if not found:
            print(f"No open item named: {clean(args.text)}", file=sys.stderr)
            return 2
        print(("Starred: " if want else "Unstarred: ") + clean(args.text))
        return 0
    if args.cmd == "list":
        for it in load():
            for x in [it] + it.children:
                if x.is_open:
                    d = parse_ymd(x.due)
                    print(("  - " if x.parent else "- ") + ("★ " if x.star else "") + x.text
                          + (f"  #{x.cat}" if x.cat else "")
                          + (f"  due {d:%m/%d}" if d else ""))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(cli(sys.argv[1:]) if len(sys.argv) > 1 else run_pane())
    except KeyboardInterrupt:
        sys.exit(0)
