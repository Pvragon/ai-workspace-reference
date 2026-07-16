---
template: onboarding-guide
version: 2.0.0
summary: "macOS Phase 1 for ONBOARDING.md: Xcode CLT + Homebrew + package installs (setup_system.sh is Debian/Ubuntu-only and will not run on a Mac). Rejoin ONBOARDING.md at Phase 2."
created: 2026-02-18
last_updated: 2026-07-16
maintainer: pvragon
---

# Onboarding, Phase 1 (macOS)

This file replaces **only Phase 1** of [ONBOARDING.md](./ONBOARDING.md) for Mac users — macOS is already Unix, so there's no WSL to install, but the system-setup script won't help you either: `_admin/setup_system.sh` is **Debian/Ubuntu-only** (it uses `apt-get` and exits immediately on macOS). Install its package list with Homebrew instead, below.

## 1. Xcode Command Line Tools

Open **Terminal** (Cmd+Space → "Terminal") and run:

```bash
xcode-select --install
```

Click **Install** in the popup and wait for it to finish.

## 2. Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen instructions at the end to add `brew` to your PATH (it prints two commands to copy-paste). Verify with `brew --version`.

## 3. Install the toolchain packages

This is the macOS equivalent of `setup_system.sh` — same tools, brew names:

```bash
brew install git gh python@3.12 node jq ripgrep sqlite tree wget bash
```

Notes:
- **No `sudo`** — Homebrew refuses to run as root.
- **`bash` matters:** macOS ships bash 3.2 (2007); the setup scripts use features that need bash 4+. Homebrew's bash installs alongside the system one and wins via PATH. Verify: `bash --version` shows 5.x.

## 4. Verify

```bash
git --version && gh --version && python3 --version && node --version && jq --version
```

All five print versions → **✓ Checkpoint passed.**

---

## Continue in ONBOARDING.md

Rejoin **[ONBOARDING.md at Phase 2](./ONBOARDING.md#phase-2-connect-your-terminal-to-github)** (Connect Your Terminal to GitHub) and follow it to the end. Two Mac adjustments as you go:

- **Phase 3 step 2:** skip `sudo ./temp-setup/team-lib/_admin/setup_system.sh` entirely — you just did its job with brew.
- **Phase 5 step 4:** your workspace file is at `~/ai-workspace/pvragon-workspace.code-workspace` (no `\\wsl$` path, no WSL extension needed).
