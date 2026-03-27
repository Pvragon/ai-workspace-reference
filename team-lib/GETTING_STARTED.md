---
template: onboarding-guide
version: 1.0.0
summary: "Step-by-step onboarding guide from blank Windows machine to fully configured agentic workspace. Covers WSL setup, IDE connection, bootstrap scripts, and workflow basics."
created: 2026-01-15
last_updated: 2026-02-18
maintainer: pvragon
---

# Getting Started: From Zero to Agentic

Welcome to the **Pvragon AI Workspace**. This guide will take you from a blank Windows machine to a fully configured, agentic development environment.

> [!NOTE]
> **macOS users:** See [GETTING_STARTED_MAC.md](./GETTING_STARTED_MAC.md) for Mac-specific instructions.

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

### 2. Install Google Antigravity
1.  Download and install **Google Antigravity**.
    *   *Note: If you prefer to use VS Code, Cursor, or another editor, you are welcome to do so. However, these instructions assume you are using Antigravity.*
2.  Open Antigravity.
3.  Install the **WSL Extension** (if not already installed).
    *   Go to Extensions (sidebar block icon) -> Search "WSL" -> Install.

---

## Phase 2: Enter the Matrix (Connecting to Linux)

**CRITICAL RULE:** We do not work in the Windows filesystem (`C:\Users\...`). We work inside the Linux filesystem (`/home/yourname/...`).

1.  Open Antigravity.
2.  Press `F1` (or `Ctrl+Shift+P`) to open the Command Palette.
3.  Type and select: **`WSL: Connect to WSL`**.
4.  A new window will open. Look at the bottom left corner: it should say **WSL: Ubuntu**.
5.  Open your Linux Home terminal:
    *   Press `Ctrl + ~` (tilde) to open the Integrated Terminal.
    *   Type `pwd`. It should show `/home/<your-username>`.
    *   *If it shows `/mnt/c/...`, you are in the wrong place. Type `cd ~` to go home.*

---

## Phase 3: Bootstrap (Choose Your Path)

You are now in Linux, but you don't have our tools yet. Choose the path that matches your role.

### Option A: Standard User (I just want to use the tools)
*Best for: Users who will not be modifying the core Team Library code.*

1.  **Install Git**:
    ```bash
    sudo apt-get update && sudo apt-get install -y git
    ```
2.  **Fetch the Setup Scripts**:
    Clone explicitly to a temporary folder to get the installer.
    ```bash
    cd ~
    git clone https://github.com/Pvragon/pvragon-ai-library.git temp-setup
    ```
3.  **Run System Setup (Admin)**:
    ```bash
    sudo ./temp-setup/_admin/setup_system.sh
    ```
4.  **Run Workspace Setup (User)**:
    ```bash
    ./temp-setup/_admin/setup_workspace.sh && rm -rf ~/temp-setup
    ```
    *Follow the prompts. When asked about `my-lib`, choose "Create new" or "Clone existing" as appropriate.*

---

### Option B: Contributor (I want to improve the Team Library)
*Best for: Developers who plan to submit Pull Requests to `team-lib`.*

1.  **Fork the Repository**:
    *   Go to [Pvragon/pvragon-ai-library](https://github.com/Pvragon/pvragon-ai-library).
    *   Click **Fork** (top right) -> Select your username -> Create Fork.

2.  **Install Git**:
    ```bash
    sudo apt-get update && sudo apt-get install -y git
    ```

3.  **Clone YOUR Fork**:
    We clone *your* writeable copy directly to the final destination.
    ```bash
    mkdir -p ~/ai-workspace
    # REPLACE <YOUR-USERNAME> BELOW:
    git clone https://github.com/<YOUR-USERNAME>/pvragon-ai-library.git ~/ai-workspace/team-lib
    ```

4.  **Run Setup from Place**:
    ```bash
    ~/ai-workspace/team-lib/_admin/setup_workspace.sh
    ```
    *(The script will detect it's already cloned and skip the download step)*

5.  **Configure Upstream**:
    Link your repo back to the original so you can get updates.
    ```bash
    cd ~/ai-workspace/team-lib
    git remote add upstream https://github.com/Pvragon/pvragon-ai-library.git
    ```

---

## Phase 4: Start

1.  **Restart your Terminal**
    *   Close the terminal window and open a new one. This loads the new configuration.

2.  **Open your Workspace (RECOMMENDED):**
    *   **This is the default way to load the workspace.**
    *   In Antigravity: **File -> Open Workspace from File...**
    *   Select: `\\wsl$\Ubuntu\home\<username>\ai-workspace\pvragon-workspace.code-workspace`


## Phase 5: Workflow Basics

Understanding where to work is critical to keeping the workspace clean and effective.

### How to Think About This Workspace (Mental Model)

The `/ai-workspace` has four sub-directories, each with a specific role:

1.  **/personal** — **The Sandbox.**
    *   This is not linked to any repo and it's your place to do whatever you want.
    *   It's entirely local and can link to an obsidian vault or do other "second brain" tasks.

2.  **/my-lib** — **Your Laboratory.**
    *   This is where you work on DOE automations of your own. You use this workspace to make skills, directives, harnesses, executions, etc.
    *   **This is where you will work the majority of the time.**
    *   This directory is attached to your **personal repo** (e.g., `private-ai-library`).
    *   **Rule:** This is where you should push your code while you're working on it.

3.  **/team-lib** — **The Showroom.**
    *   This is an exact replica of `my-lib`, BUT it's designed to be shared by the team.
    *   It contains 'approved' skills and automations that we've developed as a team over time and released for others on the team to use.
    *   This is the folder that is attached to the **`pvragon-ai-library`** repo.

4.  **/projects** — **The Factory.**
    *   This is where agentic development on apps happens.
    *   It has some different rules that apply to building apps agentically.

### The "Graduation" Workflow

How does code get from your lab (`my-lib`) to the team (`team-lib`)?

1.  **Develop in `my-lib`**: Work out all the kinks, test your automations, and iterate privately.
2.  **Graduate to `team-lib`**: Once something is stable and useful for the team, move it to `team-lib`.
    *   *Option A*: Use the graduation skill (if available).
    *   *Option B*: Manually copy the folder (like `saas-usage-audit`) and drop the pieces into their appropriate `/team-lib` locations.
3.  **Pull Request**: Create a Pull Request against the `team-lib` repo (`pvragon-ai-library`) for review.

---

## 🤝 How to Contribute (For Option B Users)

Because you are working on a **Fork**, you cannot break the main team updates. Here is the workflow:

### 1. Update your code
Before starting work, make sure you have the latest team updates.
*   **GitHub UI**: Go to your fork on GitHub. Click **"Sync fork"**.
*   **Terminal**: `git pull upstream main`

### 2. Make your changes
Create a branch, write code, commit, and push to *your* fork.
```bash
git checkout -b feature/my-cool-feature
# ... work ...
git push origin feature/my-cool-feature
```

### 3. Open a Pull Request
*   Go to your fork on GitHub.
*   Click **"Compare & pull request"**.
*   Base: `Pvragon/pvragon-ai-library` provided by `main`.
*   Head: `<Your-Username>/pvragon-ai-library` provided by `feature/my-cool-feature`.


### 🎉 Congratulations!
You are now ready.
- **Global Context** is in `team-lib`.
- **Your Work** goes in `projects`.
- **Your Private Config** is in `my-lib`.

**Next Step:** Open `team-lib/context/indexed/workspace-reference.md` to read the Operating Manual.
