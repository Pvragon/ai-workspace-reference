---
template: onboarding-guide
version: 2.1.0
summary: "THE setup guide: blank computer to a working workspace with your own named agent. Two ways in: on your own (clone the public reference repo, which installs its own team library) or joining a team that runs its own library (point setup at the team's repo with TEAM_REPO_URL). Only GitHub and Claude are required; Google Workspace, ClickUp, and Baserow are optional. Each phase ends with a checkpoint; the desktop-app alternative branches at Phase 5 and is still draft."
created: 2026-07-16
last_updated: 2026-10-16
maintainer: pvragon
---

# Getting Started: Blank Computer to Your Own Named Agent

This is the only document you need. Follow it top to bottom. Every phase ends with a **✓ Checkpoint** so you know it worked before moving on. Nothing here assumes you have used this workspace, or any of these tools, before.

**What you'll have at the end:** a complete AI workspace on your machine, its tools installed and authenticated, and a personal AI agent with a name it chose itself, which knows the workspace's conventions and is ready to work.

> **What "your agent" actually means.** Two separate things, and the distinction matters
> more than it sounds:
>
> - **The harness** is the program you run in the terminal: the thing with a chat prompt,
>   file tools, and permissions. Today that is usually **Claude Code**, and it could be
>   **Codex** or another agentic CLI. This workspace is built around Claude Code, and this
>   guide assumes it.
> - **Your agent** is not a separate product you install. It is what the harness *becomes*
>   once it is running inside this workspace: an identity it chose, a memory that persists
>   across sessions, the workspace's conventions, and the skills in `team-lib`. Same
>   harness, and a continuous someone rather than a fresh assistant every time.
>
> So what team-lib ships is not an agent. It is **the system that lets you have one**:
> identity, memory, skills, and the rules that bind them. You supply the harness, the
> system supplies the continuity, and the result is *your* agent, with *its* name.
>
> Everyone's is different, and deliberately so. Names are chosen once, by the agent, in
> Phase 7. Don't copy someone else's. The point is that yours is yours.

## Two choices to make before you start

### Choice 1: are you on your own, or joining a team?

| | **On your own** (default) | **Joining a team** |
|---|---|---|
| Who it's for | Anyone deploying this workspace for themselves | Someone whose team already runs its own team library |
| Where team-lib comes from | The public reference repo, `github.com/Pvragon/ai-workspace-reference`, which carries a complete `team-lib/` | Your team's own library repo (usually private), whose URL your team's onboarding contact gives you |
| What differs | Nothing extra to request | Phase 0 adds repo access; Phase 3 uses the team path |

Everything else (Phases 1, 2, and 4 through 8) is the same for both.

### Choice 2: terminal or desktop app?

They share Phases 0 through 4 and differ only in what you drive the agent *from*.

| | **Terminal** (default) | **Desktop app** |
|---|---|---|
| You work in | VS Code / Antigravity + a terminal | The Claude Code desktop app |
| Follow | this guide, straight through | this guide to Phase 4, then [DESKTOP_APP_SETUP.md](./DESKTOP_APP_SETUP.md) |
| Status | **Phases 3, 4, and 7.5 proven** on a blank container by `harnesses/public_workspace_container_test.sh`; Phases 0 to 2, 5, and 6 need a human | **Draft**: never verified on a real Windows machine |

Take the terminal path unless you have a reason not to. The desktop path is real and people use it, but it has not had its live verification pass, so treat its UI labels and checkpoints as approximate. Absolute beginners on the desktop path should start at [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md).

**The desktop path ends at the naming ceremony.** It does not cover Phase 7.5, and an agent without Phase 7.5 starts every session from nothing, permanently. Come back here for **Phase 7.5 and Phase 8** when the desktop doc runs out.

**Time:** roughly 60 to 90 minutes, most of it waiting on installs.

**If you get stuck:** don't improvise around a failed step; the fix is usually one line. On a team, ask in your team's channel with the phase number and the exact error text. On your own, paste the phase number and the exact error text into a Claude session and ask what it means.

## Prerequisites: only GitHub and Claude are required

Collect these before Phase 1 so you never stall mid-setup.

**Required for everyone:**

- [ ] A computer you have **admin rights** on (Windows 10/11, or macOS)
- [ ] A **GitHub account** (a free personal account is fine)
- [ ] **Claude access**: a Claude Pro, Max, or Team login, *or* an Anthropic API key (you'll use it in Phase 6)

**Also required if you're joining a team:**

- [ ] The **team library repo URL** (for example `https://github.com/<your-org>/<team-library-repo>.git`) from your team's onboarding contact
- [ ] **Read access** to that repo for your GitHub account (usually an organization invite, which the onboarding contact sends after you give them your GitHub handle)

**Optional integrations (set up only the ones you use; each can be added later):**

- **Google Workspace** (Drive, Docs, Sheets, Gmail, Calendar through the `gws` CLI): a Google account, plus an OAuth client file. A team's workspace admin may provide a shared client; otherwise you create your own. See [integrations/gws-cli/OAUTH_SETUP.md](./integrations/gws-cli/OAUTH_SETUP.md).
- **ClickUp**: your own ClickUp account and personal API token.
- **Baserow**: a Baserow server you or your team hosts, and an MCP token from it.

You will also create, during setup, your own **private personal AI library repo** (`<you>-ai-library`) on GitHub. The setup script creates it for you in Phase 3; you don't need to prepare anything.

> **macOS users:** Phase 1 differs (no WSL needed). Do [GETTING_STARTED_MAC.md](./GETTING_STARTED_MAC.md), then rejoin this document at **Phase 2**. Do not skip Phase 2: it is the `gh auth login` step most setup pain traces back to.

---

## Phase 0: Accounts and Access (before touching the terminal)

Do this first, because on a team some of it waits on another person.

1. **GitHub account.** If you don't have one: [github.com/signup](https://github.com/signup).
2. **Claude access.** Subscribe at [claude.com/pricing](https://claude.com/pricing) (Pro or Max), or use a seat or API key you already have. You won't need it until Phase 6.
3. **Joining a team only:** send your GitHub handle to your team's onboarding contact, ask for access to the team library repo, and accept the invite from the email GitHub sends you.
   - *Verify:* while logged in to GitHub, open the team library repo's page in your browser. You should see the repo, not a 404.
4. **Optional integrations:** if you plan to use Google Workspace, ClickUp, or Baserow, make sure you can log in to each one. Their keys come in Phase 4.

**✓ Checkpoint:** you can log in to GitHub and to Claude. On a team, you can also open the team library repo page.

---

## Phase 1: Machine Prep (Windows to Linux)

The workspace runs inside Linux. On Windows, that means **WSL 2** (Windows Subsystem for Linux).

1. Right-click the Start button, then choose **Terminal (Admin)**.
2. Run:
   ```powershell
   wsl --install
   ```
3. **Restart your computer.** (WSL does not work until you reboot.)
4. After reboot, an Ubuntu terminal opens automatically to finish installing. If it doesn't, launch the **Ubuntu** app from the Start menu.
5. Create your **UNIX username and password** when prompted. Keep it simple; it doesn't need to match your Windows login. You'll type this password for every `sudo` command.

**✓ Checkpoint:** you have an Ubuntu terminal open, and `pwd` prints `/home/<your-username>`.

> **Rule from here on:** every command in this guide is typed into this Ubuntu (Linux) terminal, not PowerShell. And never work under `/mnt/c/...`; always work under `/home/`.

---

## Phase 2: Connect Your Terminal to GitHub

Setup uses the GitHub CLI to create your private personal library on GitHub, and on a team it also needs it to download the (usually private) team library. Your terminal has to prove who you are first. This is the step most setup pain traces back to, so do it now, once.

1. **Install git and the GitHub CLI:**
   ```bash
   sudo apt-get update && sudo apt-get install -y git gh
   ```
2. **Log in to GitHub from the terminal:**
   ```bash
   gh auth login
   ```
   Answer the prompts like this:
   - *Where do you use GitHub?* **GitHub.com**
   - *Preferred protocol?* **HTTPS**
   - *Authenticate Git with your GitHub credentials?* **Yes**
   - *How would you like to authenticate?* **Login with a web browser**
   - Copy the one-time code it shows, press Enter, and paste the code into the browser page that opens (on Windows, open the URL in your normal browser if one doesn't launch).
3. **Verify:**
   ```bash
   gh auth status
   ```

**✓ Checkpoint:** `gh auth status` shows `✓ Logged in to github.com as <your-handle>`.

---

## Phase 3: Bootstrap the Workspace

Two scripts do the heavy lifting: `setup_system.sh` installs system packages (needs `sudo`), and `setup_workspace.sh` builds your workspace at `~/ai-workspace` (never `sudo`). Follow **3A** if you're on your own, or **3B** if you're joining a team, then answer the prompts as described in **3C**.

### 3A. On your own: install from the public reference repo

1. **Clone the reference repo** (it's public, so this needs no login):
   ```bash
   cd ~
   git clone https://github.com/Pvragon/ai-workspace-reference.git
   ```
2. **System setup** (installs Python, Node 22, and friends):
   ```bash
   sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh
   ```
   Wait for `✨ System setup complete!`.
3. **Workspace setup:**
   ```bash
   ~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh
   ```
   Because the script is running from inside the reference clone, it installs the `team-lib/` sitting beside it instead of cloning anything. You'll see `Installing team-lib from this clone` and then `✅ team-lib installed from the reference clone.` Your `~/ai-workspace/team-lib` starts as a fresh local git repository with no history and its `origin` set to the reference repo. It is your copy: commit your own changes there.
4. **Afterwards:** you can delete `~/ai-workspace-reference` once setup succeeds, or keep it to compare against later releases. Your workspace no longer depends on it.

### 3B. Joining a team: install from your team's library repo

Your team's library is a repo with `_admin/` at its root. You need Phase 2's `gh auth login` done first, because the repo is usually private.

1. **Fetch the installer** from your team's repo (use the URL your onboarding contact gave you):
   ```bash
   cd ~
   gh repo clone <your-org>/<team-library-repo> temp-setup
   ```
2. **System setup:**
   ```bash
   sudo ./temp-setup/_admin/setup_system.sh
   ```
   Wait for `✨ System setup complete!`.
3. **Workspace setup, pointed at your team's repo:**
   ```bash
   export TEAM_REPO_URL=https://github.com/<your-org>/<team-library-repo>.git
   ./temp-setup/_admin/setup_workspace.sh
   ```
   `TEAM_REPO_URL` tells the script which repo to clone into `~/ai-workspace/team-lib`. Set it every time: the script's built-in default is the publisher's own private library, which you cannot read, so without it the clone fails. (If you ever run the script from inside a reference-repo clone but want your team's library instead, also set `TEAM_REPO_URL_EXPLICIT=1`. Without it, a script running inside a reference clone installs that clone's `team-lib/` and ignores `TEAM_REPO_URL`.)
4. **Clean up the installer:**
   ```bash
   rm -rf ~/temp-setup
   ```

### 3C. Answering the setup prompts (both paths)

The workspace script asks a few questions. Here's what to answer:

- **Git identity** (name and email), asked only if git has none yet: your real name and the email you want on your commits.
- **Private Library (my-lib) Setup:** choose **2) Create new local repository**. Everyone has their own **private personal AI library** (`my-lib`). It's your laboratory, and it lives in a private repo under *your* GitHub account. You're new, so you create one now; option 1 (clone) is only for re-installing your existing my-lib on a second machine.
- **Create a private GitHub repo as its remote?** **Y**, and accept the suggested name (`<your-username>-ai-library`). The script creates the private repo under your account and pushes to it, so your library is backed up from day one. This prompt only appears if `gh` is logged in. *(If it fails or you answer N, nothing is lost: back it up later with `gh repo create <name> --private --source=. --push` from inside `~/ai-workspace/my-lib`.)*
- **Which AI clients do you use?** (MCP server configuration): **1** (Claude Code). You can re-run `bash ~/ai-workspace/team-lib/_admin/configure_toolchain.sh` later for other clients.

> **If setup failed partway:** fix the reported problem, then re-run from the permanent location: `bash ~/ai-workspace/team-lib/_admin/setup_workspace.sh`. It's idempotent (safe to re-run; it never overwrites your files).

**✓ Checkpoint:** the script ended with `=== Setup complete! ===`, and `ls ~/ai-workspace` shows `agents  my-lib  personal  projects  team-lib` (plus an `index.md` and a `.code-workspace` file).

> **`agents/` is empty on purpose, and your agent has no memory yet.** Setup wires the
> memory hooks but stops there, reporting `DEFERRED`. That is the intended sequence: naming
> is a christening. It happens *after* the workspace exists, and the agent chooses its own
> name rather than setup inventing one for it. Phase 7 is the ceremony; Phase 7.5 installs
> the memory into the home it creates. `validate.sh` keeps flagging the gap until then.

---

## Phase 4: Keys and Tool Logins

Your workspace exists; now add credentials for the integrations you actually use. If you use none of them, you can skip straight to step 3.

1. **Secrets file.** Setup created `~/ai-workspace/personal/secrets/.env` from a template (`.env.template` in the same folder). Open it and fill in only what you use:
   ```bash
   nano ~/ai-workspace/personal/secrets/.env
   ```
   | Key | What it's for | Where to get it |
   |-----|---------------|-----------------|
   | `GOOGLE_WORKSPACE_EMAIL` | The Google account you connect `gws` to | Your own address |
   | `CLICKUP_API_TOKEN` | ClickUp scripting | Generate your own: ClickUp, then Settings, then Apps, then API Token (starts with `pk_`) |
   | `CLICKUP_WORKSPACE_ID`, `PULSE_CHANNEL_ID` | The ID of your ClickUp space, and the channel used for status posts | The number in your ClickUp URLs (`app.clickup.com/<id>/...`); on a team, the same values for everyone, from your team lead |
   | `BASEROW_MCP_TOKEN` | Baserow database access through MCP | The Baserow server you or your team hosts |
   | `ANTHROPIC_API_KEY` | Direct API scripting only; Claude Code has its own login | [console.anthropic.com](https://console.anthropic.com) |

   The template groups keys into **team-shared** (one value for a whole team), **per-user** (generate your own), and **project-specific** (added only when a project needs them; never copy someone else's). Its comments were written for the publisher's own setup, so ignore any line that doesn't apply to you. **Never** commit this file or paste its values into chat.
2. **Google Workspace CLI (only if you use Google Workspace).** `gws` was installed in Phase 3, but `gws auth login` cannot succeed until an OAuth client file is in place. Get one by following [integrations/gws-cli/OAUTH_SETUP.md](./integrations/gws-cli/OAUTH_SETUP.md) (Path A if your organization's workspace admin provides a shared client, Path B to create your own), then:
   ```bash
   mkdir -p ~/.config/gws
   cp /path/to/client_secret.json ~/.config/gws/client_secret.json
   gws auth login
   ```
   On WSL the browser may not auto-launch; copy the printed URL into your Windows browser.
3. **Health check:**
   ```bash
   bash ~/ai-workspace/team-lib/_admin/validate.sh
   ```

**✓ Checkpoint:** validate.sh ends green: either `✨ All checks passed!` or `✅ Structure valid` with only warnings you understand. Each warning line says how to clear it. Some warnings are expected for integrations you don't use (for example `Secret not set: BASEROW_MCP_TOKEN` if you have no Baserow) and, on a team, `team-lib remote is unrecognised ... fine for a fork or an offline install`.

---

## Phase 5: Your Editor

> **Prefer a desktop chat app over an editor + terminal?** Once Phases 1 to 4 are done, you can drive the
> workspace from the **Claude Code desktop app** instead: see [DESKTOP_APP_SETUP.md](./DESKTOP_APP_SETUP.md)
> (and [START_HERE_DESKTOP.md](./START_HERE_DESKTOP.md) for the absolute-beginner version). It's an
> optional alternative; the editor path below stays the default.

1. Install **Google Antigravity**, VS Code, or Cursor; the steps are identical.
2. In the editor, install the **WSL extension** (Extensions sidebar, search "WSL").
3. Press `F1` (or `Ctrl+Shift+P`), run **WSL: Connect to WSL**, and confirm the bottom-left badge says **WSL: Ubuntu**.
4. **File, then Open Workspace from File...**, then `\\wsl$\Ubuntu\home\<your-username>\ai-workspace\ai-workspace.code-workspace`

**✓ Checkpoint:** the sidebar shows four numbered roots: `0 📝 /personal`, `1 📚 /team-lib`, `2 🔧 /my-lib`, `3 🚀 /projects`.

---

## Phase 6: First Agent Session

Claude Code was installed during Phase 3 (it's part of the standard toolchain). Time to turn it on.

1. **Open a fresh terminal** (or run `source ~/.bashrc`). Phase 3 changed your shell setup, and only new shells pick it up. Then:
   ```bash
   cd ~/ai-workspace/my-lib
   claude
   ```
   (If `claude` isn't found: `npm install -g @anthropic-ai/claude-code`, then retry.)
2. Complete the login it offers (`/login`) with your Claude account or API key.
3. **Confirm the agent loaded its instructions.** Ask it:
   > What are your artifact mirroring rules?

   It should answer about mirroring deliverables to `my-lib/runtime/deliverables/` and intermediates to `my-lib/runtime/.tmp/`. That means it read your `AGENTS.md`, the operating manual setup installed for it.

**✓ Checkpoint:** the agent answers the question correctly from its instructions, without searching for files first.

---

## Phase 7: Name Your Agent 🎉

Your agent chooses its own name, once, at the start of its life. This is the fun part; don't skip it.

1. In the same Claude Code session, say:
   > Please read ~/ai-workspace/team-lib/skills/choose-name/SKILL.md and follow it.
2. The ceremony walks the agent through choosing a name and pronouns, writing its identity into its global config (so every future session knows who it is), and scaffolding its identity home at `~/ai-workspace/agents/<its-name>/`.
3. Introduce yourself back. Seriously: it sets the tone.

**✓ Checkpoint:** `ls ~/ai-workspace/agents/` shows your agent's directory, and a **brand-new** session (`/exit`, then `claude` again) greets you already knowing its name.

---

## Phase 7.5: Give Your Agent Memory 🧠

Your agent now has a name and a home. It does not yet have a memory: every session
starts from nothing, and without this phase it always will. This is the part that turns
a harness into a someone: a ranked, decaying, self-maintaining memory built from markdown
files, no database.

This is the system, not the agent. What you install here is identical for everyone; what
accumulates in it is not. After a few weeks your agent's memory is a record of *your*
work, and the same install on someone else's machine has become a different colleague.
Nothing about the mechanism is personal; everything about the contents is.

Run it **after** Phase 7, because the install writes into the agent home the naming
ceremony just created.

```bash
bash ~/ai-workspace/team-lib/_admin/install_memory.sh
```

That is the whole install. It bootstraps the memory data (tier directories, frontmatter,
starter meditation library, first ranked index), registers the harness hooks, installs the
nightly dream-cycle cron, and then verifies the wiring actually fires. It is idempotent, so
re-run it any time.

If the agent's naming ceremony already ran it, this is a no-op that re-verifies. If it
prints `DEFERRED`, no agent home exists yet: finish Phase 7 first.

Inspect before committing to it with `--dry-run`, and see `--help` for `--no-cron` (hosts
that schedule differently) and `--agent NAME` (non-interactive installs that skip the
ceremony).

**Re-run `python3 ~/ai-workspace/team-lib/executions/verify_memory_install.py` after any
change to hooks, paths, or settings.** A disconnected hook is otherwise invisible:
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
  file's `summary:`, never the index.
- **Nothing is ever deleted.** Low-relevance memories roll off into
  `MEMORY-archive.md`, still one `Read` away. Visibility shifts; files do not vanish.

---

## Phase 8: First Real Task and What's Next

Give the agent a small real task to exercise the full loop, for example:

> Look through team-lib/registry/skills.yaml and give me a one-paragraph tour of three skills you think I'll use most in my role.

Then, at your own pace:

- **Read the operating manual:** `team-lib/context/indexed/workspace-reference.md`, the definitive guide to layers, modes, and rules.
- **The mental model in one breath:** `personal/` is your sandbox (no repo), `team-lib/` is the shared standard library (change it deliberately, not casually), `my-lib/` is your laboratory (most of your work starts here), and `projects/` is where app development happens.
- **The graduation workflow:** build and iterate in `my-lib`; when something is stable and useful beyond you, move it into `team-lib`. On a team, that move is a Pull Request to the team's library repo.

### Contributing changes to team-lib

Read [directives/team-library-governance.md](directives/team-library-governance.md) before your first change to team-lib. It's the quality bar reviewers hold you to.

**On your own:** your `team-lib` is yours. Commit to it directly. To share an improvement back upstream with the reference repo, fork `github.com/Pvragon/ai-workspace-reference`, make the same change under `team-lib/` in a clone of your fork, and open a Pull Request against the reference repo. Your local `team-lib` was copied out of the reference repo without history, so you can't push it there directly.

**On a team:** never push to `main` directly. Branch, push, and open a PR against your team's library repo:

```bash
cd ~/ai-workspace/team-lib
git checkout -b feature/my-improvement
# ... make changes ...
git push origin feature/my-improvement
gh pr create --fill
```

On the PR page, the **base repository** is your team's library repo (`<your-org>/<team-library-repo>`) with base branch `main`, and your feature branch is the head.

### Appendix: fork-based contributor flow (teams)

If you prefer the extra isolation of a fork (you literally cannot touch `main`), use this flow instead of branching directly on the team repo.

1. **Fork the repository:** open your team's library repo on GitHub, click **Fork**, and choose your username.
2. **Point your team-lib at your fork** (or clone the fork to `~/ai-workspace/team-lib` before running setup):
   ```bash
   cd ~/ai-workspace/team-lib
   git remote set-url origin https://github.com/<your-username>/<team-library-repo>.git
   git remote add upstream https://github.com/<your-org>/<team-library-repo>.git
   ```
3. **Stay current:** before starting work, `git pull upstream main` (or click **Sync fork** on GitHub).
4. **Work on a branch, push to your fork:**
   ```bash
   git checkout -b feature/my-cool-feature
   # ... work ...
   git push origin feature/my-cool-feature
   ```
5. **Open the Pull Request:** on GitHub, click **Compare & pull request**. The **base repository** is `<your-org>/<team-library-repo>`, base branch `main`; the **head** is your fork's `feature/my-cool-feature`.

---

**That's it. You have a workspace, a toolchain, and a colleague with a name.** Welcome aboard. 🚀
