---
template: onboarding-guide
version: 2.0.0
summary: "Step-by-step onboarding guide from blank Windows machine to fully configured agentic workspace. Covers WSL setup, IDE connection, bootstrap scripts, agent creation, and workflow basics. v2.0.0: rewritten for the public ai-workspace-reference repo — single bootstrap path, reference-layout-aware setup, new agent-creation phase."
created: 2026-01-15
last_updated: 2026-07-09
maintainer: pvragon
---

# Getting Started: From Zero to Agentic

Welcome to the **Pvragon AI Workspace**. This guide will take you from a blank Windows machine to a fully configured, agentic development environment.

> [!NOTE]
> **macOS users:** See [GETTING_STARTED_MAC.md](./GETTING_STARTED_MAC.md) for Mac-specific instructions.

> [!IMPORTANT]
> **Using the public reference repo?** If you got here via [`Pvragon/ai-workspace-reference`](https://github.com/Pvragon/ai-workspace-reference), that repo **is your starting team library**. The setup script below knows how to bootstrap from it directly — no access to any private Pvragon repo is needed.

## Phase 1: The Foundation (Windows)

Before we can use our automation tools, we need a Linux kernel. We use **WSL 2** (Windows Subsystem for Linux) to get the power of Linux seamlessly inside Windows.

### 1. Install WSL
1.  Open **PowerShell** or **Command Prompt** as Administrator.
    *   *Right-click Start button -> Terminal (Admin)*
2.  Run the following command:
    ```powershell
    wsl --install
    ```
3.  **Restart your computer**.
    *   WSL will not work until you reboot.
4.  After reboot, a terminal window should open automatically to finish installing Ubuntu.
5.  Create your **UNIX Username** and **Password** when prompted.
    *   *Tip: Keep it simple. This does not need to match your Windows login.*

### 2. Install an Editor
1.  Install **VS Code** (or Google Antigravity, Cursor, or another VS Code-family editor — the instructions below work the same way).
2.  Open your editor.
3.  Install the **WSL Extension** (if not already installed).
    *   Go to Extensions (sidebar block icon) -> Search "WSL" -> Install.

---

## Phase 2: Enter the Matrix (Connecting to Linux)

**CRITICAL RULE:** We do not work in the Windows filesystem (`C:\Users\...`). We work inside the Linux filesystem (`/home/yourname/...`).

1.  Open your editor.
2.  Press `F1` (or `Ctrl+Shift+P`) to open the Command Palette.
3.  Type and select: **`WSL: Connect to WSL`**.
4.  A new window will open. Look at the bottom left corner: it should say **WSL: Ubuntu**.
5.  Open your Linux Home terminal:
    *   Press `Ctrl + ~` (tilde) to open the Integrated Terminal.
    *   Type `pwd`. It should show `/home/<your-username>`.
    *   *If it shows `/mnt/c/...`, you are in the wrong place. Type `cd ~` to go home.*

---

## Phase 3: Bootstrap

You are now in Linux, but you don't have the tools yet.

1.  **Install Git**:
    ```bash
    sudo apt-get update && sudo apt-get install -y git
    ```
2.  **Clone the reference repo** (keep it — it's useful reference material afterward):
    ```bash
    cd ~
    git clone https://github.com/Pvragon/ai-workspace-reference.git
    ```
3.  **Run System Setup (Admin)** — installs system-level dependencies (Node.js, Python, jq, etc.):
    ```bash
    sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh
    ```
4.  **Run Workspace Setup (User)** — scaffolds `~/ai-workspace`, extracts the team library, sets up your `my-lib`, Python venv, and toolchain:
    ```bash
    ~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh
    ```
    *Follow the prompts. When asked about `my-lib`, choose "Create new" (option 2) unless you already have a private library repo to clone.*

> [!NOTE]
> **Working with a team?** If your team maintains its own team-library repo, point the setup at it instead: `TEAM_REPO_URL=https://github.com/<your-org>/<your-team-lib>.git ~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh`

---

## Phase 4: Start

1.  **Restart your Terminal**
    *   Close the terminal window and open a new one. This loads the new configuration.

2.  **Open your Workspace (RECOMMENDED):**
    *   **This is the default way to load the workspace.**
    *   In your editor: **File -> Open Workspace from File...**
    *   Select: `\\wsl$\Ubuntu\home\<username>\ai-workspace\pvragon-workspace.code-workspace`

---

## Phase 5: Create Your Agent

Your workspace has a home for a persistent agent identity — name, memory, and preferences that survive across every session and every AI vendor.

1.  **Copy the example agent** (pick your agent's name — you can also let the agent choose its own):
    ```bash
    cp -r ~/ai-workspace-reference/agents/example-agent ~/ai-workspace/agents/<agent-name>
    ```
2.  **Personalize `identity.md`**: open `~/ai-workspace/agents/<agent-name>/identity.md` and fill in the name and defaults.
3.  **Link the memory adapter** (connects the agent's memory into Claude Code's per-project memory system):
    ```bash
    cd ~/ai-workspace/agents/<agent-name>/adapters/claude && ./link.sh
    ```
4.  **Point your instructions at the identity**: add a line like `READ ~/ai-workspace/agents/<agent-name>/identity.md` to the top of `~/.claude/CLAUDE.md` (create the file if needed).
5.  **Version it**: `cd ~/ai-workspace/agents/<agent-name> && git init && git add -A && git commit -m "Agent genesis"` — the agent's memory is worth backing up from day one.

The example memory files in `memory/` show the format: one fact per file, YAML frontmatter with a `metadata.type` of `user` / `feedback` / `project` / `reference`, and a one-line entry in `MEMORY.md` (the index the agent loads at every cold start).

---

## Phase 6: Workflow Basics

Understanding where to work is critical to keeping the workspace clean and effective.

### How to Think About This Workspace (Mental Model)

The `/ai-workspace` has four layer directories plus the cross-cutting `agents/`:

1.  **/personal** — **The Sandbox.**
    *   This is not linked to any shared repo and it's your place to do whatever you want.
    *   It's entirely local (optionally your own private repo, with `secrets/` gitignored) and can serve as an Obsidian vault or other "second brain."

2.  **/my-lib** — **Your Laboratory.**
    *   This is where you work on DOE automations of your own. You use this workspace to make skills, directives, harnesses, executions, etc.
    *   **This is where you will work the majority of the time.**
    *   Attach it to your own **private repo** when ready (e.g., `<you>/private-ai-library`).
    *   **Rule:** This is where you should push your code while you're working on it.

3.  **/team-lib** — **The Showroom.**
    *   Same shape as `my-lib`, BUT it's designed to be shared.
    *   It contains 'approved' skills and automations, released for everyone using the library.
    *   Bootstrapped from this reference repo; attach it to **your own team's repo** when you create one.

4.  **/projects** — **The Factory.**
    *   This is where agentic development on apps happens.
    *   It has some different rules that apply to building apps agentically (see `context/indexed/project-docs-standard.md`).

5.  **/agents** — **The Identity Layer (cross-cutting).**
    *   One folder per agent: `identity.md`, `memory/`, vendor `adapters/`.
    *   Git-backed so identity and memory survive machine changes and vendor switches.

### The "Graduation" Workflow

How does code get from your lab (`my-lib`) to the shared library (`team-lib`)?

1.  **Develop in `my-lib`**: Work out all the kinks, test your automations, and iterate privately.
2.  **Graduate to `team-lib`**: Once something is stable and useful for the team, move it to `team-lib`.
    *   *Option A*: Use the [`graduate-to-team-library`](../my-lib/directives/graduate-to-team-library.md) directive.
    *   *Option B*: Manually copy the folder and drop the pieces into their appropriate `/team-lib` locations (and register them in `registry/`).
3.  **Pull Request**: If your team-lib is a shared repo, open a Pull Request for review.

---

## 🤝 Contributing Back

Found a fix or improvement that belongs in the reference itself? PRs to [`Pvragon/ai-workspace-reference`](https://github.com/Pvragon/ai-workspace-reference) are welcome:

1.  Fork the repo on GitHub, clone your fork, create a branch.
2.  Make your change (keep it generic — no personal paths, names, or credentials).
3.  Push to your fork and open a Pull Request.

### 🎉 Congratulations!
You are now ready.
- **Global Context** is in `team-lib`.
- **Your Work** goes in `my-lib` (automations) and `projects` (apps).
- **Your Agent** lives in `agents/<agent-name>`.

**Next Step:** Open `team-lib/context/indexed/workspace-reference.md` to read the Operating Manual.
