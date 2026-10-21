---
template: business-context
version: 1.0.0
summary: "The house style for small terminal panes on the Omarchy desktop (to-do pane, music pane, and the everpresent Your Agent dashboard): live theme colors, one orange signal, the header and section grammar, glyphs, motion, input handling, and how a pane lays out from a 68-column tile up to fullscreen. Read before building or restyling any pane."
created: 2026-10-19
last_updated: 2026-10-19
maintainer: your-agent
entity_type: design-standard
tags: [omarchy, terminal, tui, design, theming, todo-pane, music-pane, everpresent]
status: active
---

# Terminal pane house style

This is the visual and behavioral style shared by the small terminal panes on the operator's desktop. It is written down from what the panes already do, so the code is the evidence:

- `team-lib/apps/todo-pane/todo_pane.py`, the to-do pane.
- `team-lib/apps/music-pane/music_pane.py`, the music pane.

The everpresent Your Agent dashboard follows it too (plan: `my-lib/runtime/deliverables/261019-everpresent-pane-interface/`). When a pane and this document disagree, check the pane's code, then fix whichever one is wrong.

## 1. The one rule

**Teal is structure, orange is signal.** That's the Omarchy theme's own rule (`~/.config/omarchy/themes/your-theme/colors.toml`). Structure means labels, rules, counts and the active state, and it's drawn in the accent and selection colors. Signal is orange, and it marks the one thing on screen that asks for the viewer. A pane where several things are orange has no signal.

## 2. Color

### 2.1 Load the theme live

Read the current theme from `~/.local/state/omarchy/current/theme/colors.toml`. Keep only the keys whose values are `#rrggbb` strings. Re-read the file when its modification time changes, so a theme switch recolors the pane within a second or two with no restart. On a machine without Omarchy, fall back to neutral defaults. Both panes use these:

```python
DEFAULTS = {"background": "#16181d", "foreground": "#c8ccd4", "light_foreground": "#e6e9ef",
            "accent": "#5fa8d3", "selection": "#2c3e50", "muted": "#6b7280", "orange": "#f08a4b",
            "yellow": "#e6bb3f"}
```

Colors are 24-bit SGR (`\033[38;2;r;g;bm`), wrapped by one small `fg(color, text)` helper. Never hard-code a theme's hex values in a pane. Use the key names below.

### 2.2 Roles

| Role | Key | Pvragon value |
|---|---|---|
| Structure | accent | #4DA4C2 |
| Signal | orange | #E7511F |
| Rules, quiet structure | selection | #1E4958 |
| Body text | foreground | #CBD8DE |
| Titles, emphasis | light_foreground | #DEEAEF |
| Meta, hints, done | muted | #5E767D |
| Stars only | yellow | #E6BB3F |

- **Orange is for:** the header mark, the selected-row pointer `›`, something due or overdue, a failure, the text cursor, and anything waiting on the operator. Nothing else.
- **Green and red:** neither pane uses them. A good result is a muted `✓`, and a failure is an orange `✗`.
- **Selection** (`selection`) colors rules and quiet structure, and it's the background of selected text in a text field.
- **Starred rows** get a wash of `yellow` behind the whole line, the way a highlighter would mark it (`todo_pane.py`, the starred-row renderer).

## 3. Layout grammar

### 3.1 No boxes

Panes don't draw borders around themselves. The tile edge is the border. Structure comes from a header, section labels and rules, and alignment.

### 3.2 Header

The header is one line at the top. It has four parts:

- **A quiet motif in structure colors.** The music pane draws an equalizer, `▁▂` in selection, `▃▅▆` in accent, then `▄▂` in selection.
- **One orange mark.** The music pane uses `♫` and the to-do pane uses a Nerd Font glyph.
- **The pane's name** in light foreground, lowercase.
- **Context** in muted, such as where you are or a count. Right-align it when there's room.

### 3.3 Sections

A section label is lowercase accent text, then an optional count in light foreground, then a selection-colored rule `─` running to the right edge. The to-do pane's category rules are the reference.

### 3.4 Rows

- Indent rows two spaces.
- Next comes a one-column pointer slot: an orange `›` on the selected row, blank otherwise.
- Then a glyph, then the text.
- Metadata (dates, counts, sources) is right-aligned in muted, one column in from the edge.
- Overflow shows as a muted `↑ N more` or `↓ N more` line, never a scrollbar.

### 3.5 Keys

The last line or two of the pane list the keys in muted text, for example `n new  space done  ↵ open  esc back`. They're always visible and always last.

## 4. Glyphs

| Glyph | Meaning |
|---|---|
| › | Selected row |
| ○ | Open item |
| ● | Done (muted) |
| ⊘ | Retired |
| ★ / ☆ | Starred / not |
| ↻ | Moved or recurring |
| ✓ / ✗ | Ran ok / failed |

New panes may add glyphs for their own concepts (the everpresent dashboard adds `▸` doing, `⧖` waiting, `⇄` agent and `◷` job or event). Each glyph means one thing in a pane. Meaning never rests on color alone: every colored element also has a glyph or a word.

Measure glyph width in display cells (`unicodedata.east_asian_width` W or F counts as 2, combining marks as 0), the way `todo_pane.py`'s `width()` does. Code-point length is wrong for emoji and for some symbols. A glyph that renders oddly in JetBrainsMono Nerd Font has to be checked in a real foot window, not assumed.

## 5. Motion

There's almost none. Nothing scrolls, slides or blinks on its own.

- **Flash on change:** when an item is checked off, it shows in orange for a moment before settling to muted with a strike-through (`todo_pane.py`, `FLASH`).
- **Live meters:** the music pane's audio waves and a progress fill are the only continuous motion, and only while something is actually happening.
- **No sound,** ever.

## 6. Input and behavior

- **Mouse and paste:** enable button-event mouse tracking with SGR coordinates (`\033[?1002h\033[?1006h`) and bracketed paste (`\033[?2004h`). Restore the terminal on every exit path.
- **Untrusted text:** strip control and bidirectional-override characters from anything that came from outside (titles, file contents, network data) before drawing it. Both panes use the same `CONTROL` pattern and a `clean()` helper.
- **Stdlib only.** No curses, no TUI framework, nothing to install beyond Python and the command-line tools a pane wraps (mpv and fzf for music). The panes draw whole frames with ANSI and `\033[K`.
- **One writer per file.** A pane's data file is written under an `fcntl` lock with an atomic replace. Agents change it through the pane's own CLI (`todo_pane.py add …`), never by editing the file.
- **A CLI for agents.** Every pane that holds data also has a command-line form, so an agent can read and write it without the screen.
- **Never steal focus.** A pane is launched unfocused (`no_initial_focus`) and never raises or moves windows. See memory `feedback_never-steal-focus-when-opening-windows`.

## 7. Sizes: from a tile to fullscreen

### 7.1 The panel is the unit

Design every view as a **panel 68 columns wide**, the width of a comms-wall tile (516 px at JetBrainsMono 9, measured 2026-10-19). A panel's height is flexible, and it truncates with a `↓ N more` line rather than overflowing.

Measure the terminal on every frame (`shutil.get_terminal_size`, as the music pane does). Lay out panels by how many fit:

| Terminal width | Layout |
|---|---|
| under 100 cols | One panel, tabs in the header |
| 100 to 139 | Two panels side by side |
| 140 and up | Two panels plus wider gutters, or three on a landscape screen |

Tall terminals stack panels in rows. When every view fits on screen at once, drop the tabs from the header.

### 7.2 Fullscreen on a comms wall

The comms monitors are portrait, 1080 x 1920. Super+F on a tile there gives roughly 142 x 105 cells. That's scaled from the tile's measured size and still needs checking in a real window. At that size a pane should look intentional rather than stretched:

- **Keep the 68-column grid.** Don't stretch rows across 142 columns, where right-aligned metadata ends up far from its text. Place two panels with a two-column gutter, which fills 138 columns.
- **Center the leftover margin** instead of hanging it on the right.
- **Re-read the size on every frame**, so toggling Super+F back and forth re-lays out immediately.

## 8. Checklist for a new pane

1. It loads the theme live, with the neutral fallback.
2. Exactly one thing is orange at rest (the header mark). Anything else orange means "needs you".
3. It has the header, sections and key line as described above, and no box.
4. Widths are measured in display cells, and each mockup has been checked in a real foot window.
5. It lays out at 68 columns and at fullscreen, re-measuring on every frame.
6. It has stdlib-only code, a lock around its data file, a CLI for agents, and sanitized outside text.
7. It never takes focus.
