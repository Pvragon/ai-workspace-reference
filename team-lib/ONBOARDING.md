---
template: onboarding-guide
version: 2.0.0
summary: "The single linear onboarding path: blank computer → fully functioning named agent. Assumes nothing — no accounts, no auth, no tools. Each phase ends with a checkpoint. Supersedes GETTING_STARTED.md as the canonical guide."
created: 2026-07-16
last_updated: 2026-07-16
maintainer: pvragon
---

# Onboarding: Blank Computer → Your Own Named Agent

This is the only document you need. Follow it top to bottom — every phase ends with a **✓ Checkpoint** so you know it worked before moving on. Nothing here assumes you've used this workspace (or any of these tools) before.

**What you'll have at the end:** a complete AI workspace on your machine, the standard toolchain installed and authenticated, and a personal AI agent — with a name it chose itself — that knows the workspace conventions and is ready to work.

**Time:** roughly 60–90 minutes, most of it waiting on installs.

> **macOS users:** Phase 1 differs (no WSL needed). Do [GETTING_STARTED_MAC.md](./GETTING_STARTED_MAC.md) Phase 1, then rejoin this document at **Phase 2**.

## Before you start — prerequisites checklist

- [ ] A computer you have **admin rights** on (Windows 10/11, or macOS)
- [ ] A **GitHub account** ([github.com/signup](https://github.com/signup)) — and, if your team runs a private library repo, an accepted invite to it
- [ ] **Claude access** — a Claude account login *or* an API key (you'll use it in Phase 6)
- [ ] Any team-provided tokens for optional integrations (see Phase 4 — you can proceed without them)

You will also create, during setup: your own **private personal AI library repo** (`<you>-ai-library`) on GitHub — the setup script creates it for you in Phase 3; nothing to prepare.

---

## Phase 1: Machine Prep (Windows → Linux)

We work inside Linux. On Windows, that means **WSL 2** (Windows Subsystem for Linux).

1. Right-click the Start button → **Terminal (Admin)**.
2. Run:
   ```powershell
   wsl --install
   ```
3. **Restart your computer.** (WSL does not work until you reboot.)
4. After reboot, an Ubuntu terminal opens automatically to finish installing. If it doesn't, launch the **Ubuntu** app from the Start menu.
5. Create your **UNIX username and password** when prompted. Keep it simple; you'll type this password for every `sudo` command.

**✓ Checkpoint:** you have an Ubuntu terminal open, and `pwd` prints `/home/<your-username>`.

> **Rule from here on:** every command in this guide is typed into this Ubuntu (Linux) terminal, not PowerShell. And we never work under `/mnt/c/...` — always under `/home/`.

---

## Phase 2: Connect Your Terminal to GitHub

Your terminal needs to prove who you are before it can create your private library (and clone your team's repo, if it's private). Do this once, now.

1. **Install git and the GitHub CLI:**
   ```bash
   sudo apt-get update && sudo apt-get install -y git gh
   ```
2. **Log in to GitHub from the terminal:**
   ```bash
   gh auth login
   ```
   Answer: **GitHub.com** → **HTTPS** → **Yes** (authenticate Git) → **Login with a web browser**, then paste the one-time code into the browser page it opens.
3. **Verify:**
   ```bash
   gh auth status
   ```

**✓ Checkpoint:** `gh auth status` shows `✓ Logged in to github.com as <your-handle>`.

---

## Phase 3: Bootstrap the Workspace

Two scripts do the heavy lifting: one installs system packages (needs `sudo`), one builds your workspace (never `sudo`).

1. **Fetch the installer:**
   ```bash
   cd ~
   gh repo clone Pvragon/ai-workspace-reference temp-setup
   ```
   *(Working from your own team's library instead? Clone that repo here and export `TEAM_REPO_URL=<its-url>` before step 3.)*
2. **System setup** (installs Python, Node, and friends):
   ```bash
   sudo ./temp-setup/team-lib/_admin/setup_system.sh
   ```
   Wait for `✨ System setup complete!`.
3. **Workspace setup** (builds `~/ai-workspace`, sets up the team library, provisions tools):
   ```bash
   ./temp-setup/team-lib/_admin/setup_workspace.sh
   ```
   This script asks questions. Here's what to answer:
   - **Git identity** (name/email) — your real name and email; this labels your git commits.
   - **Private Library (my-lib) Setup** → choose **2) Create new local repository**. Everyone has their own **private personal AI library** — it's your laboratory, and it lives in a private repo under *your* GitHub account. Option 1 (clone) is only for re-installing on a second machine.
   - **Create a private GitHub repo as its remote?** → **Y**, accept the suggested name. Your library is backed up from day one. *(If it fails or you answer N: `gh repo create <name> --private --source=. --push` from inside `~/ai-workspace/my-lib` later.)*
   - **Which AI clients do you use?** (MCP configuration) → **1** (Claude Code). Re-run later for other clients.
4. **Clean up the installer:**
   ```bash
   rm -rf ~/temp-setup
   ```
   > If setup failed partway: fix the reported problem, then re-run from the permanent location — `bash ~/ai-workspace/team-lib/_admin/setup_workspace.sh`. It's idempotent.

**✓ Checkpoint:** the script ended with `=== Setup complete! ===`, and `ls ~/ai-workspace` shows `agents  my-lib  personal  projects  team-lib` (plus a `.code-workspace` file).

---

## Phase 4: Keys & Tool Logins

1. **Secrets file.** Setup created `~/ai-workspace/personal/secrets/.env` from a template. Open it and fill in what you have:
   ```bash
   nano ~/ai-workspace/personal/secrets/.env
   ```
   The template groups keys into **team-shared** (ask your team lead), **per-user** (generate your own from each service's settings page), and **project-specific** (only when a project needs them — never copy someone else's values). **Never** commit this file or paste its values into chat.
2. **Google Workspace CLI** (optional — skip if your team doesn't use it):
   ```bash
   gws auth login
   ```
   On WSL the browser may not auto-launch — copy the printed URL into your Windows browser.
3. **Health check:**
   ```bash
   bash ~/ai-workspace/team-lib/_admin/validate.sh
   ```

**✓ Checkpoint:** validate.sh ends green — `✨ All checks passed!` or structure-valid with only warnings you understand (each warning line says how to clear it).

---

## Phase 5: Your Editor

> **Prefer a desktop chat app over an editor + terminal?** Once Phases 1–4 are done, you can drive the
> workspace from the **Claude Code desktop app** instead — see [DESKTOP_APP_SETUP.md](./DESKTOP_APP_SETUP.md)
> (and [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md) for the absolute-beginner version). It's an
> optional alternative; the editor path below stays the default.

1. Install your editor of choice (VS Code, Cursor, or similar).
2. In the editor, install the **WSL extension** (Extensions sidebar → search "WSL"). *(Mac: skip.)*
3. `F1` (or `Ctrl+Shift+P`) → **WSL: Connect to WSL** → confirm the bottom-left badge says **WSL: Ubuntu**.
4. **File → Open Workspace from File...** → `\\wsl$\Ubuntu\home\<your-username>\ai-workspace\pvragon-workspace.code-workspace` *(Mac: `~/ai-workspace/pvragon-workspace.code-workspace`)*

**✓ Checkpoint:** the sidebar shows four numbered roots: `0 📝 /personal`, `1 📚 /team-lib`, `2 🔧 /my-lib`, `3 🚀 /projects`.

---

## Phase 6: First Agent Session

Claude Code was installed during Phase 3 (it's part of the standard toolchain).

1. **Open a fresh terminal** (or run `source ~/.bashrc`) — Phase 3 added the tool directory to your PATH, and only new shells pick it up. Then:
   ```bash
   cd ~/ai-workspace/my-lib
   claude
   ```
   (If `claude` isn't found: `npm install -g @anthropic-ai/claude-code`, then retry.)
2. Complete the login it offers (`/login`) — Claude account or API key.
3. **Confirm the agent loaded its instructions.** Ask it:
   > What are your artifact mirroring rules?

   It should answer about mirroring deliverables to `my-lib/runtime/deliverables/` and intermediates to `my-lib/runtime/.tmp/` — that means it read your `AGENTS.md`, the operating manual setup installed for it.

**✓ Checkpoint:** the agent answers correctly from its instructions, without searching for files first.

---

## Phase 7: Name Your Agent 🎉

Your agent chooses its own name — once, at the start of its life. Don't skip this; it's the point.

1. In the same Claude Code session, say:
   > Please read ~/ai-workspace/team-lib/skills/choose-name/SKILL.md and follow it.
2. The ceremony walks the agent through choosing a name and pronouns, writing its identity into its global config, and scaffolding its identity home at `~/ai-workspace/agents/<its-name>/`. The `agents/example-agent/` directory in this repo shows the full pattern — including memory-file format and the vendor **adapter** (`adapters/claude/link.sh`) that connects the agent's canonical memory into Claude Code's per-project memory system; copy what's useful.
3. **Version it:**
   ```bash
   cd ~/ai-workspace/agents/<its-name> && git init && git add -A && git commit -m "Agent genesis"
   ```
   The agent's memory is worth backing up from day one.
4. Introduce yourself back. Seriously — it sets the tone.

**✓ Checkpoint:** `ls ~/ai-workspace/agents/` shows your agent's directory, and a **brand-new** session (`/exit`, then `claude` again) greets you already knowing its name.

---

## Phase 8: First Real Task & What's Next

Give the agent a small real task to exercise the full loop — for example:

> Look through team-lib/registry/skills.yaml and give me a one-paragraph tour of three skills you think I'll use most.

Then, at your own pace:

- **Read the operating manual:** `team-lib/context/indexed/workspace-reference.md` — the definitive guide to layers, modes, and rules.
- **The mental model in one breath:** `personal/` is your sandbox (no team repo), `team-lib/` is the shared standard library (don't edit directly), `my-lib/` is your laboratory (most work starts here), `projects/` is where app development happens.
- **The graduation workflow:** build and iterate in `my-lib` → when something is stable and team-useful, propose it into `team-lib` via a Pull Request.
- **Contributing back / fork flow:** see the appendix in [GETTING_STARTED.md](GETTING_STARTED.md).

---

**That's it. You have a workspace, a toolchain, and a colleague with a name.** Welcome aboard. 🚀
