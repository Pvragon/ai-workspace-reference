---
template: onboarding-guide
version: 0.2.0
summary: "DRAFT. An OPTIONAL alternative onboarding path (Claude Code Desktop / Codex) for anyone deploying this workspace, on their own or on a team, who would rather use a desktop app than VS Code + a terminal. Additive: the VS Code + terminal path in GETTING_STARTED.md stays the default; this forks in at Phase 5 for those who want it."
status: draft
created: 2026-07-21
last_updated: 2026-10-16
maintainer: pvragon
---

# Using Your Workspace in a Desktop App (Claude Code / Codex)

> **Brand-new and non-technical?** Start with [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md): five
> steps to get an agent running, which then walks you through the rest using *this* guide. The
> document below is the detailed reference that agent (or a self-driver) follows.

**This is an optional path.** The standard onboarding ([GETTING_STARTED.md](./GETTING_STARTED.md)) sets you up
in VS Code with a terminal, and that stays the default. Nothing here removes it. This guide is just a
*second* on-ramp for people who'd rather drive the workspace from a friendly desktop chat app. Pick
whichever fits you, or use both; the desktop app and VS Code coexist happily on the same workspace.

**Who this is for:** anyone setting up this AI workspace, whether on their own (from the public
reference repo) or as part of a team that runs its own team library, who would rather work in a GUI
chat app than live in an editor and a terminal.

**The one honest thing to know up front:** the desktop app is an alternative *cockpit*. It gives you a
chat GUI over the workspace, but it doesn't do the *one-time setup* for you. Your workspace has to
physically exist inside Linux (WSL) before any desktop app can point at it, and getting it there is a
terminal task. So expect one setup session in a terminal (almost all of it is scripted); after that
you can live in the app, with VS Code and the terminal there for the moments you want them.

---

## The core idea: let the agent walk you through it

The most effective way people have onboarded so far isn't reading a manual. It's this: **open an
agent, point it at the repo, tell it what you want, and follow its instructions.** The agent reads
the setup guide itself and walks you through it conversationally, running what it can and telling you
exactly what to type when it can't. You are the hands; it is the guide.

**The whole flow, in four moves:**

1. **Install the desktop app and sign in** (see *A1* below; it's a two-minute step).
2. **Open a Code session.** Any folder works for now; the agent just needs somewhere to talk to you
   from. (If you have nothing set up yet, point it at any folder, such as your Documents.)
3. **Say what you want.** Paste something like:
   > I want to set up the AI workspace from https://github.com/Pvragon/ai-workspace-reference on this
   > machine. Please read its onboarding guide (start with `team-lib/GETTING_STARTED.md`) and walk
   > me through it one step at a time. Generate and explain each command, tell me exactly where to run
   > it, and wait for me to confirm each step worked before the next.

   If you're joining a team, add: "I'm joining a team whose team library is at <team library repo
   URL>; use the Joining a team path."
4. **Follow along.** Do the steps it hands you, confirm each one, and let it lead.

That's the experience to aim for. The sections below are the **reference** the agent follows, and
your fallback if you'd rather do a step yourself or the agent gets stuck.

### What "the agent walks you through it" honestly means

The one-time setup, **GETTING_STARTED.md Phases 1 to 4** (installing Linux through WSL, connecting
GitHub, running the two bootstrap scripts, and adding any keys you need), happens with **your hands on a terminal
and the agent as your guide.** It writes out each command, explains what it does, tells you which window
to paste it into, and reads the result to catch errors. A few steps are irreducibly yours: installing
WSL needs a Windows **admin** terminal plus one **reboot**, and the GitHub sign-in (plus any optional
sign-ins, such as Google) needs your clicks.

So "the agent does it for you" means *you never have to figure out **what** to type or **why***, not
that it runs unattended while you watch. That distinction matters: **the desktop app can't run Linux
commands or provision WSL for you *before* a Linux workspace exists.** That's a chicken-and-egg only a
terminal can break. Once WSL exists and `validate.sh` passes, you switch the app to **WSL mode** (*A3*),
and from then on the agent genuinely drives.

> **Bottom line:** setup is a guided terminal session (about an hour, mostly waiting on downloads).
> Daily work afterward is the app in WSL mode. The steps below assume Phases 1 to 4 are done and
> `~/ai-workspace` validates.

---

## Path A: Claude Code Desktop (recommended)

This is the smoother of the two. It runs the *same engine* as the command-line Claude Code and
**shares all of your workspace's configuration**: your `CLAUDE.md`/`AGENTS.md` instructions, MCP
servers, hooks, skills, and settings all just work. It signs in with your **Claude Pro/Max
subscription** (no API key, no per-use billing).

> **Screenshots:** the app's UI shifts between releases, so rather than freeze stale images here, see
> the official [desktop quickstart](https://code.claude.com/docs/en/desktop-quickstart) and
> [desktop-in-WSL](https://code.claude.com/docs/en/desktop-wsl) pages for current visuals of the Code
> tab and the environment picker. *(Maintainer: capture fresh screenshots of A2 and A3 during the live
> verification run and drop them in beside each step.)*

### A1. Install and sign in
1. Download the app:
   - **Windows (most people):** <https://claude.ai/api/desktop/win32/x64/setup/latest/redirect>
     (Windows on ARM: the ARM64 installer, linked from the [desktop quickstart](https://code.claude.com/docs/en/desktop-quickstart))
   - **macOS:** <https://claude.ai/api/desktop/darwin/universal/dmg/latest/redirect>
2. Run the installer and launch **Claude** (Start menu or Applications).
3. **Sign in with your Anthropic account.** You need a paid plan (Pro or Max).

**✓ Checkpoint:** the app opens and you're signed in.

### A2. Open the Code tab
Click the **Code** tab at the top center. (If it asks you to upgrade, you're not on a paid plan
yet. If it asks you to sign in online, do it and restart the app.)

**✓ Checkpoint:** the Code tab is open.

### A3. Point it at your workspace (WSL mode)
Because your workspace lives inside Linux, you use **WSL mode**, not "Local."
1. Start a new session and open the **environment picker**.
2. Under the **WSL** section, pick your distribution (for example **Ubuntu**).
3. In the **folder picker**, browse (you'll see Linux paths like `/home/<your-username>/...`) and choose
   **`/home/<your-username>/ai-workspace/my-lib`**. (`my-lib` is your personal lab; it's where most work starts.)
4. When the **workspace trust** dialog appears, trust the folder.

> The first session in a distribution takes a minute while Claude sets itself up inside Linux.

> **Coming from the setup session?** This WSL-mode session is **brand new**. It has none of the
> conversation history from the terminal-setup chat that got you here (and if you just rebooted, that
> chat is gone). That's fine. To pick up cleanly, paste:
> > Re-read `team-lib/DESKTOP_APP_SETUP.md` and `team-lib/GETTING_STARTED.md`, check where my setup got to
> > (run `validate.sh` if unsure), and tell me the next step.

**✓ Checkpoint:** a session is open, pointed at `my-lib`, with no error about a missing distribution.

### A4. Confirm the agent loaded its instructions
In the chat, ask:
> What are your artifact mirroring rules?

It should answer about mirroring deliverables to `my-lib/runtime/deliverables/` and intermediates to
`my-lib/runtime/.tmp/`. That's proof it read your `AGENTS.md` (the operating manual) from inside WSL.

**✓ Checkpoint:** it answers from its instructions without searching for files first.

### A5. Name your agent 🎉
Same ceremony as GETTING_STARTED.md Phase 7, done right here in the desktop chat:
> Please read ~/ai-workspace/team-lib/skills/choose-name/SKILL.md and follow it.

Then start a **new** session and confirm it greets you already knowing its name.

**✓ Checkpoint:** `agents/<its-name>/` exists and a fresh session knows who it is.

### What you get, and what isn't in WSL mode yet
**You get:** the full harness Linux-side (skills via `/`, hooks, memory, MCP, subagents), a real
chat GUI, **visual diff review** (approve each change), and parallel sessions, all on your own
subscription.

**Not available in WSL sessions today** (per the current docs; recheck as the app updates):
- **No in-app terminal.** For occasional shell commands, open your Ubuntu terminal alongside the app.
- **No in-app file browser.** "Open in editor" opens the file in VS Code (connected to WSL). Diffs
  still show inside the app.
- Connectors and plugins installed *through the app's GUI* aren't available in WSL mode. (MCP servers
  configured in your workspace still load. **VERIFY on first run.**)

---

## Path B: Codex Desktop (honest expectations)

Codex can run this workspace, but the fit is looser and some things have to be *wired* rather than
inherited. It's closer to Claude Code than it used to be (Codex has added MCP, a Skills system, and a
hooks engine), so plan for adaptation, not absence.

**What comes along well:**
- **`AGENTS.md`:** Codex reads it natively (note the roughly 32 KiB default cap), so the core operating
  rules, layers, and conventions are intact. This is the whole reason the workspace mirrors its
  instructions across `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md`.
- **Directives:** the SOPs in `directives/` work as read-and-follow instructions.
- **MCP servers:** supported. You configure them separately; the workspace's toolchain installer
  doesn't write a Codex MCP config yet (**manual step, VERIFY**).
- **Skills:** Codex has a Skills system now, and this workspace's `SKILL.md` files are plain markdown
  plus optional scripts (the most portable primitive going), so many carry over. Invocation and
  discovery differ from Claude Code's `/` commands, so expect some adaptation. **VERIFY per skill.**

**What has to be wired, not inherited:**
- **Persistent memory and self-annealing.** Native Codex forgets between sessions, and `AGENTS.md`
  alone is static. The workspace's auto-loading memory framework is specific to Claude Code. On Codex
  you get the same effect by wiring a memory layer through its **hooks engine plus an MCP memory
  server** (the Hindsight / Mem0 / OpenViking pattern). Doable, not automatic, and if it isn't wired,
  corrections won't stick across sessions.
- **Hooks.** Codex has a hooks engine, but with fewer lifecycle points than Claude Code's, and the
  workspace's hook scripts are written for Claude Code, so they won't run as-is. Re-express the ones
  you need.
- **Subagents and parallel agents.** Confirm Codex's current story here separately; don't assume the
  workspace's fan-out patterns port unchanged.
- **Reaching WSL-installed tools.** Depending on how the Windows Codex app is running, its sandbox may
  not see CLIs installed inside WSL (`gws`, the `executions/` scripts). This is the known
  Windows-app-can't-see-the-WSL-workspace boundary; budget time to bridge it.

**Bottom line:** Codex plus `AGENTS.md`, directives, and MCP delivers a real chunk of the workspace out
of the box, and with a memory layer wired it can self-anneal too. The friction is less about missing
primitives than about the desktop app reaching the WSL workspace, so if that reach matters to you,
Path A (Claude Code desktop, WSL mode) is the lower-effort route today.

---

## When you finish here, go back for memory

This document stops at the naming ceremony. That is **not** the end of setup.

Return to [GETTING_STARTED.md](./GETTING_STARTED.md) and do **Phase 7.5** (give your agent
memory) and **Phase 8** (first real task). Without Phase 7.5 your agent has a name and a home
and no memory at all: it starts every session from nothing, and nothing about a working
install looks unfinished. One command:

```bash
bash ~/ai-workspace/team-lib/_admin/install_memory.sh
```

---

## Still to do before this ships (maintainer notes)
- [ ] **Live verification pass (the blocker to `status: active`):** run Path A end-to-end on a real
      Windows machine and confirm every UI label and checkpoint. Open unknowns: (a) can a **Local-mode**
      Windows Code session run the pre-WSL setup commands directly (for example via `wsl.exe`), or must
      the human paste them into a separate terminal? This determines how hands-off setup really is.
      (b) Do workspace-configured MCP servers load in WSL mode? (c) What is the exact Codex desktop
      environment-selection flow for a WSL folder? Capture fresh A2 and A3 screenshots during this run.
- [x] Placed in canonical `team-lib/` beside `GETTING_STARTED.md` (draft status).
- [x] Gap fixes applied (setup manual/agent boundary, WSL-session resume step, honest step counts,
      audience line, corrected Codex capabilities).
- [x] Pointer added from `GETTING_STARTED.md` Phase 5.
- [x] Mirrored to the public `ai-workspace-reference` repo.
- [ ] Lift `status: draft` to active once the live verification pass is done.
