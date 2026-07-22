---
template: onboarding-guide
version: 0.1.0
summary: "DRAFT. An OPTIONAL alternative onboarding path (Claude Code Desktop / Codex) for people using the public ai-workspace-reference library who'd prefer a desktop app over VS Code + a terminal. Additive — the VS Code + terminal path in ONBOARDING.md stays the default; this forks in at Phase 5 for those who want it."
status: draft
created: 2026-07-21
last_updated: 2026-07-21
maintainer: pvragon
---

# Using Your Workspace in a Desktop App (Claude Code / Codex)

> **Brand-new and non-technical?** Start with [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md) — five
> steps to get an agent running, which then walks you through the rest using *this* guide. The
> document below is the detailed reference that agent (or a self-driver) follows.

**This is an optional path.** The standard onboarding ([ONBOARDING.md](./ONBOARDING.md)) sets you up
in VS Code with a terminal, and that stays the default. Nothing here removes it. This guide is just a
*second* on-ramp for people who'd rather drive the workspace from a friendly desktop chat app. Pick
whichever fits you, or use both; the desktop app and VS Code coexist happily on the same workspace.

**Who this is for:** someone who has (or is getting) the Pvragon AI workspace and would rather work in
a GUI chat app than live in an editor and a terminal.

**The one honest thing to know up front:** the desktop app is an alternative *cockpit*. It gives you a
chat GUI over the workspace, but it doesn't do the *one-time setup* for you. Your workspace has to
physically exist inside Linux (WSL) before any desktop app can point at it, and getting it there is a
terminal task. So expect one setup session in a terminal (we've scripted almost all of it); after that
you can live in the app, with VS Code and the terminal there for the moments you want them.

---

## The core idea: let the agent walk you through it

The most effective way people have onboarded so far isn't reading a manual. It's this: **open an
agent, point it at the repo, tell it what you want, and follow its instructions.** The agent reads
the setup guide itself and walks you through it conversationally, running what it can and telling you
exactly what to type when it can't. You are the hands; it is the guide.

**The whole flow, in four moves:**

1. **Install the desktop app and sign in** (see *A1* below — it's a two-minute step).
2. **Open a Code session.** Any folder works for now — the agent just needs somewhere to talk to you
   from. (If you have nothing set up yet, point it at any folder, e.g. your Documents.)
3. **Say what you want.** Paste something like:
   > I want to set up the Pvragon AI workspace on this machine. Please read the onboarding guide at
   > https://github.com/Pvragon/ai-workspace-reference (start with `team-lib/ONBOARDING.md`) and walk
   > me through it one step at a time. Generate and explain each command, tell me exactly where to run
   > it, and wait for me to confirm each step worked before the next.
4. **Follow along.** Do the steps it hands you, confirm each one, and let it lead.

That's the experience to aim for. The sections below are the **reference** the agent follows — and
your fallback if you'd rather do a step yourself or the agent gets stuck.

### What "the agent walks you through it" honestly means

The one-time setup — installing Linux (WSL), connecting GitHub, running the two bootstrap scripts,
adding your keys (**ONBOARDING Phases 1–4**) — happens with **your hands on a terminal and the agent
as your guide.** It writes out each command, explains what it does, tells you which window to paste it
into, and reads the result to catch errors. A few steps are irreducibly yours: installing WSL needs a
Windows **admin** terminal plus one **reboot**, and the GitHub / Google sign-ins need your clicks.

So "the agent does it for you" means *you never have to figure out **what** to type or **why*** — not
that it runs unattended while you watch. That distinction matters: **the desktop app can't run Linux
commands or provision WSL for you *before* a Linux workspace exists** — a chicken-and-egg only a
terminal can break. Once WSL exists and `validate.sh` passes, you switch the app to **WSL mode** (*A3*),
and from then on the agent genuinely drives.

> **Bottom line:** setup = guided terminal session (≈1 hour, mostly waiting on downloads). Daily work
> afterward = the app in WSL mode. The steps below assume Phases 1–4 are done and `~/ai-workspace`
> validates.

---

## Path A — Claude Code Desktop (recommended)

This is the smoother of the two. It runs the *same engine* as the command-line Claude Code and
**shares all of your workspace's configuration**: your `CLAUDE.md`/`AGENTS.md` instructions, MCP
servers, hooks, skills, and settings all just work. It signs in with your **Claude Pro/Max
subscription** (no API key, no per-use billing).

> **Screenshots:** the app's UI shifts between releases, so rather than freeze stale images here, see
> the official [desktop quickstart](https://code.claude.com/docs/en/desktop-quickstart) and
> [desktop-in-WSL](https://code.claude.com/docs/en/desktop-wsl) pages for current visuals of the Code
> tab and the environment picker. *(Maintainer: capture fresh screenshots of A2–A3 during the live
> verification run and drop them in beside each step.)*

### A1. Install and sign in
1. Download the app:
   - **Windows (most people):** <https://claude.ai/api/desktop/win32/x64/setup/latest/redirect>
     (Windows on ARM: the ARM64 installer, linked from the [desktop quickstart](https://code.claude.com/docs/en/desktop-quickstart))
   - **macOS:** <https://claude.ai/api/desktop/darwin/universal/dmg/latest/redirect>
2. Run the installer and launch **Claude** (Start menu / Applications).
3. **Sign in with your Anthropic account.** You need a paid plan (Pro or Max).

**✓ Checkpoint:** the app opens and you're signed in.

### A2. Open the Code tab
Click the **Code** tab at the top center. (If it asks you to upgrade, you're not on a paid plan
yet. If it asks you to sign in online, do it and restart the app.)

**✓ Checkpoint:** the Code tab is open.

### A3. Point it at your workspace (WSL mode)
Because your workspace lives inside Linux, you use **WSL mode** — not "Local."
1. Start a new session and open the **environment picker**.
2. Under the **WSL** section, pick your distribution (e.g. **Ubuntu**).
3. In the **folder picker**, browse — you'll see Linux paths like `/home/<you>/...` — and choose
   **`/home/<you>/ai-workspace/my-lib`**. (`my-lib` is your personal lab; it's where most work starts.)
4. When the **workspace trust** dialog appears, trust the folder.

> The first session in a distribution takes a minute while Claude sets itself up inside Linux.

> **Coming from the setup session?** This WSL-mode session is **brand new** — it has none of the
> conversation history from the terminal-setup chat that got you here (and if you just rebooted, that
> chat is gone). That's fine. To pick up cleanly, paste:
> > Re-read `team-lib/DESKTOP_APP_SETUP.md` and `team-lib/ONBOARDING.md`, check where my setup got to
> > (run `validate.sh` if unsure), and tell me the next step.

**✓ Checkpoint:** a session is open, pointed at `my-lib`, with no error about a missing distribution.

### A4. Confirm the agent loaded its instructions
In the chat, ask:
> What are your artifact mirroring rules?

It should answer about mirroring deliverables to `my-lib/runtime/deliverables/` and intermediates to
`my-lib/runtime/.tmp/` — proof it read your `AGENTS.md` (the operating manual) from inside WSL.

**✓ Checkpoint:** it answers from its instructions without searching for files first.

### A5. Name your agent 🎉
Same ceremony as ONBOARDING Phase 7, done right here in the desktop chat:
> Please read ~/ai-workspace/team-lib/skills/choose-name/SKILL.md and follow it.

Then start a **new** session and confirm it greets you already knowing its name.

**✓ Checkpoint:** `agents/<its-name>/` exists and a fresh session knows who it is.

### What you get — and what isn't in WSL mode yet
**You get:** the full harness Linux-side (skills via `/`, hooks, memory, MCP, subagents), a real
chat GUI, **visual diff review** (approve each change), and parallel sessions, all on your own
subscription.

**Not available in WSL sessions today** (per the current docs — recheck as the app updates):
- **No in-app terminal.** For occasional shell commands, open your Ubuntu terminal alongside the app.
- **No in-app file browser.** "Open in editor" opens the file in VS Code (connected to WSL). Diffs
  still show inside the app.
- Connectors/plugins installed *through the app's GUI* aren't available in WSL mode. (MCP servers
  configured in your workspace still load — **VERIFY on first run.**)

---

## Path B — Codex Desktop (honest expectations)

Codex can run this workspace, but the fit is looser and some things have to be *wired* rather than
inherited. It's closer to Claude Code than it used to be — Codex has added MCP, a Skills system, and a
hooks engine — so plan for adaptation, not absence.

**What comes along well:**
- **`AGENTS.md`** — Codex reads it natively (note the ~32 KiB default cap), so the core operating
  rules, layers, and conventions are intact. This is the whole reason we mirror instructions across
  `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`.
- **Directives** — the SOPs in `directives/` work as read-and-follow instructions.
- **MCP servers** — supported. You configure them separately; the workspace's toolchain installer
  doesn't write a Codex MCP config yet (**manual step, VERIFY**).
- **Skills** — Codex has a Skills system now, and our `SKILL.md` files are plain markdown + optional
  scripts (the most portable primitive going), so many carry over. Invocation and discovery differ
  from Claude Code's `/`-commands, so expect some adaptation — **VERIFY per skill.**

**What has to be wired, not inherited:**
- **Persistent memory / self-annealing.** Native Codex forgets between sessions; `AGENTS.md` alone is
  static. Our auto-loading memory framework is Claude-Code-specific. On Codex you get the same effect
  by wiring a memory layer through its **hooks engine + an MCP memory server** (the Hindsight / Mem0 /
  OpenViking pattern). Doable, not automatic — and if it isn't wired, corrections won't stick across
  sessions.
- **Hooks.** Codex has a hooks engine, but with fewer lifecycle points than Claude Code's, and our
  hook scripts are written for Claude Code — they won't run as-is. Re-express the ones you need.
- **Subagents / parallel agents.** Confirm Codex's current story here separately; don't assume our
  fan-out patterns port unchanged.
- **Reaching WSL-installed tools.** Depending on how the Windows Codex app is running, its sandbox may
  not see CLIs installed inside WSL (`gws`, the `executions/` scripts). This is the known
  Windows-app-can't-see-the-WSL-workspace boundary; budget time to bridge it.

**Bottom line:** Codex + `AGENTS.md` + directives + MCP delivers a real chunk of the taste out of the
box, and with a memory layer wired it can self-anneal too. The friction is less about missing
primitives than about the desktop app reaching the WSL workspace — so if that reach matters to you,
Path A (Claude Code desktop, WSL mode) is the lower-effort route today.

---

## Still to do before this ships (maintainer notes)
- [ ] **Live verification pass (the blocker to `status: active`):** run Path A end-to-end on a real
      Windows machine and confirm every UI label and checkpoint. Open unknowns: (a) can a **Local-mode**
      Windows Code session run the pre-WSL setup commands directly (e.g. via `wsl.exe`), or must the
      human paste them into a separate terminal? — this determines how hands-off setup really is;
      (b) do workspace-configured MCP servers load in WSL mode; (c) exact Codex desktop
      environment-selection flow for a WSL folder. Capture fresh A2–A3 screenshots during this run.
- [x] Placed in canonical `team-lib/` beside `ONBOARDING.md` (draft status).
- [x] Gap fixes applied (setup manual/agent boundary, WSL-session resume step, honest step counts,
      audience line, corrected Codex capabilities).
- [x] Pointer added from `ONBOARDING.md` Phase 5.
- [x] Mirrored to the public `ai-workspace-reference` repo.
- [ ] Lift `status: draft` → active once the live verification pass is done.
