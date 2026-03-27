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

## Phase 2: Bootstrap (Choose Your Path)

You're already in a native Unix environment. Choose the path that matches your role.

### Option A: Standard User (I just want to use the tools)
*Best for: Users who will not be modifying the core Team Library code.*

1.  **Fetch the Setup Scripts**:
    Clone explicitly to a temporary folder to get the installer.
    ```bash
    cd ~
    git clone https://github.com/Pvragon/pvragon-ai-library.git temp-setup
    ```

2.  **Run System Setup (Admin)**:
    ```bash
    sudo ./temp-setup/_admin/setup_system.sh
    ```
    *Note: The script auto-detects macOS and uses `brew` instead of `apt-get`.*

3.  **Run Workspace Setup (User)**:
    ```bash
    ./temp-setup/_admin/setup_workspace.sh && rm -rf ~/temp-setup
    ```
    *Follow the prompts. When asked about `my-lib`, choose "Create new" or "Clone existing" as appropriate.*

---

### Option B: Contributor (I want to improve the Team Library)
*Best for: Developers who plan to submit Pull Requests to `team-lib`.*

1.  **Fork the Repository**:
    *   Go to [Pvragon/pvragon-ai-library](https://github.com/Pvragon/pvragon-ai-library).
    *   Click **Fork** (top right) → Select your username → Create Fork.

2.  **Clone YOUR Fork**:
    We clone *your* writeable copy directly to the final destination.
    ```bash
    mkdir -p ~/ai-workspace
    # REPLACE <YOUR-USERNAME> BELOW:
    git clone https://github.com/<YOUR-USERNAME>/pvragon-ai-library.git ~/ai-workspace/team-lib
    ```

3.  **Run Setup from Place**:
    ```bash
    ~/ai-workspace/team-lib/_admin/setup_workspace.sh
    ```
    *(The script will detect it's already cloned and skip the download step)*

4.  **Configure Upstream**:
    Link your repo back to the original so you can get updates.
    ```bash
    cd ~/ai-workspace/team-lib
    git remote add upstream https://github.com/Pvragon/pvragon-ai-library.git
    ```

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
