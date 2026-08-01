---
template: onboarding-guide
version: 2.0.1
summary: "The single linear onboarding path: blank computer → fully functioning named agent. Assumes nothing — no accounts, no auth, no tools. Each phase ends with a checkpoint. Supersedes GETTING_STARTED.md as the canonical guide."
created: 2026-07-16
last_updated: 2026-08-01
maintainer: pvragon
---

# Onboarding: Blank Computer → Your Own Named Agent

This is the only document you need. Follow it top to bottom — every phase ends with a **✓ Checkpoint** so you know it worked before moving on. Nothing here assumes you've used this workspace (or any of these tools) before.

**What you'll have at the end:** a complete AI workspace on your machine, every team tool installed and authenticated, and a personal AI agent — with a name it chose itself — that knows our conventions and is ready to work.

> **What "your agent" actually means.** Two separate things, and the distinction matters
> more than it sounds:
>
> - **The harness** is the program you run in the terminal — the thing with a chat prompt,
>   file tools, and permissions. Today that is usually **Claude Code**, and it could be
>   **Codex** or another agentic CLI. **We use Claude Code**, and this guide assumes it.
> - **Your agent** is not a separate product you install. It is what the harness *becomes*
>   once it is running inside this workspace: an identity it chose, a memory that persists
>   across sessions, our conventions, and the skills in `team-lib`. Same harness, and a
>   continuous someone rather than a fresh assistant every time.
>
> So what team-lib ships is not an agent. It is **the system that lets you have one** —
> identity, memory, skills, and the rules that bind them. You supply the harness; the
> system supplies the continuity; the result is *your* agent, with *its* name.
>
> Everyone's is different, and deliberately so. Names are chosen once, by the agent, in
> Phase 7. Don't copy someone else's — the point is that yours is yours.

**Time:** roughly 60–90 minutes, most of it waiting on installs.

**If you get stuck:** post in the team channel with the phase number and the exact error text. Don't improvise around a failed step — the fix is usually one line.

## Before you start — prerequisites checklist

Everything on this list is either something you have or something your **onboarding contact** provides. Collect it all before Phase 1 so you never stall mid-setup:

- [ ] A computer you have **admin rights** on (Windows 10/11, or macOS)
- [ ] A **GitHub account** + an accepted **Pvragon org invite** (Phase 0 walks through this)
- [ ] Your **Pvragon Google Workspace** login
- [ ] A **ClickUp** invite to the Pvragon workspace
- [ ] **Claude access** — a Claude Team/Pro account login *or* an API key (ask your onboarding contact which you're getting; you'll use it in Phase 6)
- [ ] A **Baserow token** (`BASEROW_MCP_TOKEN`) from your team lead (used in Phase 4; you can proceed without it and add it later)

You will also create, during setup: your own **private personal AI library repo** (`<you>-ai-library`) on GitHub — the setup script creates it for you in Phase 3; you don't need to prepare anything.

> **macOS users:** Phases 1–2 differ (no WSL needed). Do [GETTING_STARTED_MAC.md](./GETTING_STARTED_MAC.md) Phase 1, then rejoin this document at **Phase 2**.

---

## Phase 0: Accounts & Access (before touching the terminal)

You need three accounts, and Pvragon needs to grant you access to each. Do this first — some steps wait on a human.

1. **GitHub account.** If you don't have one: [github.com/signup](https://github.com/signup). A personal account is fine.
2. **Send your GitHub handle** to your onboarding contact and ask for a **Pvragon org invite**. Accept the invite from the email GitHub sends you (or [github.com/orgs/Pvragon/invitation](https://github.com/orgs/Pvragon/invitation)).
   - *Verify:* visit [github.com/Pvragon/pvragon-ai-library](https://github.com/Pvragon/pvragon-ai-library) — you should see the repo, not a 404.
3. **Google Workspace account** — your `@pvragon.com` (or client-domain) address, from your onboarding contact. You'll use it for `gws` (Drive/Docs/Gmail automation).
4. **ClickUp** — ask your onboarding contact for an invite to the Pvragon ClickUp workspace.
5. **Claude access** — ask your onboarding contact for a seat on the team Claude account (or an API key). You won't need it until Phase 6, but request it now so it's waiting.

**✓ Checkpoint:** you can open the `pvragon-ai-library` repo page on GitHub while logged in, and you can log in to Google and ClickUp.

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
5. Create your **UNIX username and password** when prompted. Keep it simple; it doesn't need to match your Windows login. You'll type this password for every `sudo` command.

**✓ Checkpoint:** you have an Ubuntu terminal open, and `pwd` prints `/home/<your-username>`.

> **Rule from here on:** every command in this guide is typed into this Ubuntu (Linux) terminal, not PowerShell. And we never work under `/mnt/c/...` — always under `/home/`.

---

## Phase 2: Connect Your Terminal to GitHub

The team library is a **private** repo — your terminal has to prove who you are before it can download anything. This is the step most setup pain traces back to, so do it now, once.

1. **Install git and the GitHub CLI:**
   ```bash
   sudo apt-get update && sudo apt-get install -y git gh
   ```
2. **Log in to GitHub from the terminal:**
   ```bash
   gh auth login
   ```
   Answer the prompts exactly like this:
   - *Where do you use GitHub?* → **GitHub.com**
   - *Preferred protocol?* → **HTTPS**
   - *Authenticate Git with your GitHub credentials?* → **Yes**
   - *How would you like to authenticate?* → **Login with a web browser**
   - Copy the one-time code it shows, press Enter, and paste the code into the browser page that opens (on Windows, open the URL in your normal browser if one doesn't launch).
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
   gh repo clone Pvragon/pvragon-ai-library temp-setup
   ```
2. **System setup** (installs Python, Node, and friends):
   ```bash
   sudo ./temp-setup/_admin/setup_system.sh
   ```
   Wait for `✨ System setup complete!`.
3. **Workspace setup** (builds `~/ai-workspace`, clones the team library, provisions tools):
   ```bash
   ./temp-setup/_admin/setup_workspace.sh
   ```
   This script asks questions. Here's what to answer:
   - **Git identity** (name/email) — your real name and work email; this labels your git commits.
   - **Private Library (my-lib) Setup** → choose **2) Create new local repository**. Everyone on the team has their own **private personal AI library** (`my-lib`) — it's your laboratory, and it lives in a private repo under *your* GitHub account. You're new, so you create one now; option 1 (clone) is only for people re-installing on a second machine.
   - **Create a private GitHub repo as its remote?** → **Y**, accept the suggested name (`<your-username>-ai-library`). The script creates the private repo under your account and pushes to it — your library is backed up from day one. *(If this step fails or you answer N, nothing is lost: back it up later with `gh repo create <name> --private --source=. --push` from inside `~/ai-workspace/my-lib`.)*
   - **Which AI clients do you use?** (MCP configuration) → **1** (Claude Code). You can re-run this later for other clients.
4. **Clean up the installer:**
   ```bash
   rm -rf ~/temp-setup
   ```
   > If setup failed partway: fix the reported problem, then re-run from the permanent location — `bash ~/ai-workspace/team-lib/_admin/setup_workspace.sh`. It's idempotent (safe to re-run; it never overwrites your files).

**✓ Checkpoint:** the script ended with `=== Setup complete! ===`, and `ls ~/ai-workspace` shows `agents  my-lib  personal  projects  team-lib` (plus a `.code-workspace` file).

> **`agents/` is empty on purpose, and your agent has no memory yet.** Setup wires the
> memory hooks but stops there, reporting `DEFERRED`. That is the intended sequence: naming
> is a christening — it happens *after* the workspace exists, and the agent chooses its own
> name rather than setup inventing one for it. Phase 7 is the ceremony; Phase 7.5 installs
> the memory into the home it creates. `validate.sh` will keep flagging the gap until then.

---

## Phase 4: Keys & Tool Logins

Your workspace exists; now wire up credentials so the tools actually work.

1. **Secrets file.** Setup created `~/ai-workspace/personal/secrets/.env` from a template. Open it and fill in what you have:
   ```bash
   nano ~/ai-workspace/personal/secrets/.env
   ```
   | Key | What it's for | Where to get it |
   |-----|---------------|-----------------|
   | `BASEROW_MCP_TOKEN` | Baserow database access (team MCP) | Ask your team lead |
   | `CLICKUP_WORKSPACE_ID`, `PULSE_CHANNEL_ID` | Shared team constants | Ask your team lead (same values for everyone) |
   | `GOOGLE_WORKSPACE_EMAIL` | Your own Pvragon address | You already have it |
   | `CLICKUP_API_TOKEN` | ClickUp scripting (optional now) | Generate your own: ClickUp → Settings → Apps → API Token |

   The template file groups keys into **team-shared** (ask your lead), **per-user** (generate your own), and **project-specific** (only when assigned to a project — never copy someone else's). **Never** commit this file or paste its values into chat.
2. **Google Workspace CLI:**
   ```bash
   gws auth login
   ```
   Log in with your Pvragon Google account. On WSL the browser may not auto-launch — copy the printed URL into your Windows browser.
3. **Health check:**
   ```bash
   bash ~/ai-workspace/team-lib/_admin/validate.sh
   ```

**✓ Checkpoint:** validate.sh ends green — either `✨ All checks passed!` or `✅ Structure valid` with only warnings you understand (each warning line says how to clear it).

---

## Phase 5: Your Editor

> **Prefer a desktop chat app over an editor + terminal?** Once Phases 1–4 are done, you can drive the
> workspace from the **Claude Code desktop app** instead — see [DESKTOP_APP_SETUP.md](./DESKTOP_APP_SETUP.md)
> (and [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md) for the absolute-beginner version). It's an
> optional alternative; the editor path below stays the default.

1. Install **Google Antigravity** (team default) — or VS Code / Cursor if you prefer; the steps are identical.
2. In the editor, install the **WSL extension** (Extensions sidebar → search "WSL").
3. `F1` (or `Ctrl+Shift+P`) → **WSL: Connect to WSL** → confirm the bottom-left badge says **WSL: Ubuntu**.
4. **File → Open Workspace from File...** → `\\wsl$\Ubuntu\home\<your-username>\ai-workspace\pvragon-workspace.code-workspace`

**✓ Checkpoint:** the sidebar shows four numbered roots: `0 📝 /personal`, `1 📚 /team-lib`, `2 🔧 /my-lib`, `3 🚀 /projects`.

---

## Phase 6: First Agent Session

Claude Code was installed during Phase 3 (it's part of the standard toolchain). Time to turn it on.

1. **Open a fresh terminal** (or run `source ~/.bashrc`) — Phase 3 added the tool directory to your PATH, and only new shells pick it up. Then:
   ```bash
   cd ~/ai-workspace/my-lib
   claude
   ```
   (If `claude` isn't found: `npm install -g @anthropic-ai/claude-code`, then retry.)
2. Complete the login it offers (`/login`) — use the Claude account or API key your onboarding contact set you up with.
3. **Confirm the agent loaded its instructions.** Ask it:
   > What are your artifact mirroring rules?

   It should answer about mirroring deliverables to `my-lib/runtime/deliverables/` and intermediates to `my-lib/runtime/.tmp/`. That means it read your `AGENTS.md` — the operating manual setup installed for it.

**✓ Checkpoint:** the agent answers the question correctly from its instructions, without searching for files first.

---

## Phase 7: Name Your Agent 🎉

Your agent chooses its own name — once, at the start of its life. This is the fun part; don't skip it.

1. In the same Claude Code session, say:
   > Please read ~/ai-workspace/team-lib/skills/choose-name/SKILL.md and follow it.
2. The ceremony walks the agent through choosing a name and pronouns, writing its identity into its global config (so every future session knows who it is), and scaffolding its identity home at `~/ai-workspace/agents/<its-name>/`.
3. Introduce yourself back. Seriously — it sets the tone.

**✓ Checkpoint:** `ls ~/ai-workspace/agents/` shows your agent's directory, and a **brand-new** session (`/exit`, then `claude` again) greets you already knowing its name.

---

## Phase 7.5: Give Your Agent Memory 🧠

Your agent now has a name and a home. It does not yet have a memory — every session
starts from nothing, and without this phase it always will. This is the part that turns
a harness into a someone: a ranked, decaying, self-maintaining memory built from markdown
files, no database.

This is the system, not the agent. What you install here is identical for everyone on the
team; what accumulates in it is not. After a few weeks your agent's memory is a record of
*your* work, and the same install on a colleague's machine has become a different
colleague. Nothing about the mechanism is personal — everything about the contents is.

Run it **after** Phase 7, because the install writes into the agent home the naming
ceremony just created.

```bash
bash ~/ai-workspace/team-lib/_admin/install_memory.sh
```

That is the whole install. It bootstraps the memory data (tier directories, frontmatter,
starter meditation library, first ranked index), registers the harness hooks, installs the
nightly dream-cycle cron, and then verifies the wiring actually fires. It is idempotent —
re-run it any time.

If the agent's naming ceremony already ran it, this is a no-op that re-verifies. If it
prints `DEFERRED`, no agent home exists yet: finish Phase 7 first.

Inspect before committing to it with `--dry-run`, and see `--help` for `--no-cron` (hosts
that schedule differently) and `--agent NAME` (non-interactive installs that skip the
ceremony).

**Re-run `python3 ~/ai-workspace/team-lib/executions/verify_memory_install.py` after any
change to hooks, paths, or settings.** A disconnected hook is otherwise invisible —
memories simply stop gaining strength and nothing ever complains.

**✓ Checkpoint:** the installer ends with `=== Memory system installed. ===`, and
`~/ai-workspace/agents/<your-agent>/memory/MEMORY.md` exists with a Hot band.

Then ask your agent:

> Read `team-lib/context/indexed/memory-system.md` and tell me, in your own words,
> what happens to something I tell you today if neither of us mentions it again for
> a month.

If it cannot answer that, it has not understood the tier model, and its memory will
silently become a junk drawer. The doc is the contract: tiers, the scoring formula,
every constant, the frontmatter schema, and the failure-mode table.

**Two things worth knowing on day one:**

- **`MEMORY.md` is generated.** It is regenerated from the corpus on every rerank, so
  hand-edits there are discarded. To change what an entry says, edit that memory
  file's `summary:` — never the index.
- **Nothing is ever deleted.** Low-relevance memories roll off into
  `MEMORY-archive.md`, still one `Read` away. Visibility shifts; files do not vanish.

---

## Phase 8: First Real Task & What's Next

Give the agent a small real task to exercise the full loop — for example:

> Look through team-lib/registry/skills.yaml and give me a one-paragraph tour of three skills you think I'll use most in my role.

Then, at your own pace:

- **Read the operating manual:** `team-lib/context/indexed/workspace-reference.md` — the definitive guide to layers, modes, and rules.
- **The mental model in one breath:** `personal/` is your sandbox (no repo), `team-lib/` is the shared standard library (don't edit directly), `my-lib/` is your laboratory (most of your work starts here), `projects/` is where app development happens.
- **The graduation workflow:** build and iterate in `my-lib` → when something is stable and team-useful, propose it into `team-lib` via a Pull Request.

### Contributing to team-lib (when you're ready)

Never push to `main` directly. The flow:

```bash
cd ~/ai-workspace/team-lib
git checkout -b feature/my-improvement
# ... make changes ...
git push origin feature/my-improvement
gh pr create --fill
```

On the PR page: the **base repository** is `Pvragon/pvragon-ai-library` with base branch `main`; your feature branch is the head. Read `directives/team-library-governance.md` before your first PR — it's the quality bar reviewers hold you to.

*(Prefer to work from a fork so you can't touch main at all? That flow is in the [contributor appendix of the old guide](GETTING_STARTED.md) — both are accepted.)*

---

**That's it. You have a workspace, a toolchain, and a colleague with a name.** Welcome aboard. 🚀
