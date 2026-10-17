---
template: app-readme
version: 1.1.1
summary: "Sticky-note to-do list for a corner of a tiling desktop: one plain markdown file that you and your AI agents both write to, shown in a small themed terminal pane. Type or dictate to add, click to check off, free categories, colored due dates, word wrap, and a CLI for agents. README covers install, keys and the file format."
created: 2026-10-15
last_updated: 2026-10-16
maintainer: pvragon
---

# todo pane

A to-do list that lives in a small terminal window and works like a sticky note. Each item is one
short line, 44 characters at most, that you remember the meaning of. You add by typing or talking,
and you check things off with a click.

Everything is stored in one plain markdown file. You can read it, edit it by hand, keep it in git,
or let an AI agent add to it from the command line.

## What you get

- Add an item by typing, with no key to press first. Voice dictation works too, because the pane
  takes whatever your dictation tool types.
- Say or type a due date at the end, like "friday 10am", "due friday", "by the 20th" or "10/20",
  and it becomes the item's due date. A clock time stays in the text, drawn in orange.
- Check an item off with a click or the space bar. It strikes through, then moves to a done file
  the next morning. A closed view shows what you finished, and you can bring any of it back.
- Star the one to three items that matter most right now, the way you'd run a highlighter over
  a paper list. Click the ☆ at the left of a row, or press Ctrl+S, and the whole row is
  highlighted. The highlight goes away when you click the star again or close the item.
- Retire an item you won't do. It closes the same way, in grey instead of orange.
- Delete an item by clearing its text and pressing Enter. A copy goes to the done file, so a
  slip can be undone.
- Give items any category you like, with `#work` or by saying "category work". The list opens grouped
  by category (Ctrl+G or one click flattens it), and you can rename a category for every item in
  it at once. In grouped view,
  dragging an item into another group gives it that group's category.
- Nest one level of sub-items under an item with Tab. The parent shows a dot for each sub-item,
  filled in as they get done.
- Drag items to reorder them. Your order is kept, the way it would be on paper.
- Due dates are colored by urgency: grey when they're far off, brighter within three days, orange
  today, and bold orange once overdue.
- Long items wrap in a narrow window, and the list scrolls, with a marker for what's off screen.
- Copy, cut and paste work within a line and on whole items.
- On Omarchy, the pane uses your current theme and recolors itself when you switch themes.
  Elsewhere it uses neutral colors.

## Install

You need Python 3.11 or newer. Nothing else is required. For the clipboard keys on Wayland, install
`wl-clipboard`.

```
python3 ~/ai-workspace/team-lib/apps/todo-pane/todo_pane.py
```

Give it its own small terminal window. It works from about 36 columns wide; 60 by 20 or larger is
comfortable. It sets its window title to `todo`, so a window manager rule can place it.

Your list is `~/.config/todo-pane/todo.md`. To keep it somewhere else, set `TODO_FILE`, or make
`~/.config/todo-pane/todo.md` a symlink to the real file. The pane follows the link, so a list kept
in a synced or versioned folder stays where it is.

## Keys

| Key | Does |
|---|---|
| any letter | start a new item |
| Enter | new item below the current one |
| → or F2 | edit the current item |
| ↑ ↓ | move between items |
| space | check off or uncheck |
| Ctrl+S | star or unstar (highlight a priority) |
| Delete | retire (won't do) |
| clear the text, Enter | delete the item |
| Tab, Shift+Tab | indent or outdent |
| Shift+↑ ↓ | move an item (sub-items come along) |
| Ctrl+C, X, V | copy, cut, paste |
| Ctrl+G | grouped or flat (grouped is the default) |
| Ctrl+O | closed view |
| Ctrl+T | show created and closed dates |
| F1 | all keys |

While typing a line, ←→ move the cursor and Shift selects. Enter saves and opens the next line.
Esc stops. The footer counts characters against the 44 limit.

With the mouse, click a circle to check an item, click the ☆ to star it, and click its text to edit it. Click below the
list to add at the end, and drag a line to move it. In grouped view, click a category label to
rename that category. Shift+drag uses the terminal's own text selection.

## For AI agents

```
todo_pane.py add "Call the plumber" --due fri --cat home
todo_pane.py add "find the invoice" --under "Call the plumber"
todo_pane.py star "Call the plumber"          # --off removes the star
todo_pane.py list
```

`add` refuses text over 44 characters with exit code 2, so an agent has to shorten the item rather
than retry. When `TODO_PANE_AGENT` or `CLAUDECODE` is set, items an agent adds carry a small dot
in the pane, so you can tell them from your own. Write each one so it makes sense to you later,
since you didn't write it.

The pane and the CLI take a lock before every write and replace the file in one step, so they
never overwrite each other. The pane reloads when the file changes.

## The file

```
- [ ] Call the plumber  #home  ^261017  +261015
  - [x] find the invoice  +261013  ✓261014
- [-] new monitor arm  #desk  +261001  ✗261015
- [ ] renew domain  #work  +261015  ·r
```

| Mark | Meaning |
|---|---|
| `[ ]` `[x]` `[-]` | open, done, retired |
| `#word` | category |
| `^YYMMDD` | due date |
| `(was YYMMDD)` | first due date, if it moved |
| `+YYMMDD` | created |
| `✓` or `✗YYMMDD` | closed, written by the pane |
| `↻N` | times reopened |
| `·r` | added by an agent |
| `★` | starred: a highlighted priority, cleared when the item closes |

Fields are read only at the end of a line, so an item like "#1 thing" stays text. Closed items move
to `todo-done.md` beside the list the morning after you close them.

Category colors are optional. Copy `categories.example.txt` to `~/.config/todo-pane/categories.txt`
and give each label a theme color name or a hex color.

## Platform support

| Platform | Status |
|---|---|
| Omarchy | Everything, including live theme colors. |
| Other Linux on Wayland | Everything, with neutral colors. |
| Linux on X11 | Everything except the clipboard keys. |
| macOS | Should work, untested. No clipboard keys. |
| Windows | Not supported. |

Only Omarchy with the foot terminal has been tested.

## Tests

```
python3 test_todo_pane.py
```

The tests use a temporary file and never touch your list.

## Security

Item text, pasted text, category names and agent input are all treated as untrusted. Control
characters are stripped before anything reaches the terminal, so text can't inject escape
sequences. Writes go to a temporary file in the same folder and replace the list in one step, under
a lock. The clipboard tools are called with the text passed as an argument, never through a shell.

## License

MIT. See [LICENSE](LICENSE).
