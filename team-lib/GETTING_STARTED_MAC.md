# Getting Started: From Zero to Agentic (macOS)

Welcome to the **Pvragon AI Workspace**. This guide will take you from a fresh Mac to a fully configured, agentic development environment.

> [!NOTE]
> This guide is for **macOS** users. If you are on Windows, see [GETTING_STARTED.md](./GETTING_STARTED.md).

---

## Phase 1: The Foundation (macOS)

Unlike Windows, macOS is already Unix-based—no need to install a Linux subsystem. You just need a few developer tools.

### 1. Install Xcode Command Line Tools

This provides Git and other essential build tools.

1.  Open **Terminal** (Cmd + Space → type "Terminal").
2.  Run:
    ```bash
    xcode-select --install
    ```
3.  Click **Install** in the popup and wait for completion.

### 2. Install Homebrew (Recommended)

Homebrew is the standard package manager for macOS.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After installation, follow the on-screen instructions to add Homebrew to your PATH.

### 3. Install Google Antigravity

1.  Download and install **Google Antigravity**.
    *   *Note: If you prefer to use VS Code, Cursor, or another editor, you are welcome to do so. However, these instructions assume you are using Antigravity.*
2.  Open Antigravity.

---

## Phase 2: Bootstrap

You're already in a native Unix environment.

1.  **Clone the reference repo** (keep it — it's useful reference material afterward):
    ```bash
    cd ~
    git clone https://github.com/Pvragon/ai-workspace-reference.git
    ```

2.  **Run System Setup (Admin)**:
    ```bash
    sudo ~/ai-workspace-reference/team-lib/_admin/setup_system.sh
    ```
    *Note: The script auto-detects macOS and uses `brew` instead of `apt-get`.*

3.  **Run Workspace Setup (User)** — scaffolds `~/ai-workspace`, extracts the team library, sets up your `my-lib`, Python venv, and toolchain:
    ```bash
    ~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh
    ```
    *Follow the prompts. When asked about `my-lib`, choose "Create new" (option 2) unless you already have a private library repo to clone.*

> [!NOTE]
> **Working with a team?** If your team maintains its own team-library repo, point the setup at it instead: `TEAM_REPO_URL=https://github.com/<your-org>/<your-team-lib>.git ~/ai-workspace-reference/team-lib/_admin/setup_workspace.sh`

---

## Phase 3: Start

1.  **Restart your Terminal**
    *   Close the terminal window and open a new one. This loads the new configuration.

2.  **Open your Workspace (RECOMMENDED):**
    *   **This is the default way to load the workspace.**
    *   In Antigravity: **File → Open Workspace from File...**
    *   Navigate to: `~/ai-workspace/pvragon-workspace.code-workspace`

---

## Phase 4: Workflow Basics

Understanding where to work is critical to keeping the workspace clean and effective.

### How to Think About This Workspace (Mental Model)

The `/ai-workspace` has four sub-directories, each with a specific role:

1.  **/personal** — **The Sandbox.**
    *   This is not linked to any repo and it's your place to do whatever you want.
    *   It's entirely local and can link to an Obsidian vault or do other "second brain" tasks.

2.  **/my-lib** — **Your Laboratory.**
    *   This is where you work on DOE automations of your own. You use this workspace to make skills, directives, harnesses, executions, etc.
    *   **This is where you will work the majority of the time.**
    *   This directory is attached to your **personal repo** (e.g., `private-ai-library`).
    *   **Rule:** This is where you should push your code while you're working on it.

3.  **/team-lib** — **The Showroom.**
    *   Same shape as `my-lib`, BUT it's designed to be shared.
    *   It contains 'approved' skills and automations, released for everyone using the library.
    *   Bootstrapped from this reference repo; attach it to **your own team's repo** when you create one.

4.  **/projects** — **The Factory.**
    *   This is where agentic development on apps happens.
    *   It has some different rules that apply to building apps agentically.

### The "Graduation" Workflow

How does code get from your lab (`my-lib`) to the team (`team-lib`)?

1.  **Develop in `my-lib`**: Work out all the kinks, test your automations, and iterate privately.
2.  **Graduate to `team-lib`**: Once something is stable and useful for the team, move it to `team-lib`.
    *   *Option A*: Use the graduation skill (if available).
    *   *Option B*: Manually copy the folder (like `saas-usage-audit`) and drop the pieces into their appropriate `/team-lib` locations.
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
- **Your Work** goes in `projects`.
- **Your Private Config** is in `my-lib`.

**Next Step:** Open `team-lib/context/indexed/workspace-reference.md` to read the Operating Manual.
