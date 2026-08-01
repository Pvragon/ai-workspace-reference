---
template: onboarding-guide
version: 2.0.0
summary: "Redirect stub — ONBOARDING.md is the canonical setup guide. This file retains only the fork-based contributor appendix."
created: 2026-01-15
last_updated: 2026-07-16
maintainer: pvragon
---

# Getting Started

> **This guide has been replaced.**
>
> ## 👉 [ONBOARDING.md](./ONBOARDING.md) is the canonical setup guide.
>
> It takes you from a blank computer — no accounts, no auth, no tools — all the way to a fully functioning named agent, with a checkpoint after every phase. Windows and macOS both start there.

---

## Appendix: Fork-Based Contributor Flow

Most contributors branch directly on `Pvragon/pvragon-ai-library` (see ONBOARDING.md Phase 8). If you prefer the extra isolation of a fork — you literally cannot touch `main` — use this flow instead.

1. **Fork the repository:** go to [Pvragon/pvragon-ai-library](https://github.com/Pvragon/pvragon-ai-library) → **Fork** → your username.
2. **Point your team-lib at your fork** (or clone the fork to `~/ai-workspace/team-lib` before running setup):
   ```bash
   cd ~/ai-workspace/team-lib
   git remote set-url origin https://github.com/<YOUR-USERNAME>/pvragon-ai-library.git
   git remote add upstream https://github.com/Pvragon/pvragon-ai-library.git
   ```
3. **Stay current:** before starting work, `git pull upstream main` (or click **Sync fork** on GitHub).
4. **Work on a branch, push to your fork:**
   ```bash
   git checkout -b feature/my-cool-feature
   # ... work ...
   git push origin feature/my-cool-feature
   ```
5. **Open the Pull Request:** on GitHub, click **Compare & pull request**. The **base repository** is `Pvragon/pvragon-ai-library`, base branch `main`; the **head** is your fork's `feature/my-cool-feature`.

Read [directives/team-library-governance.md](directives/team-library-governance.md) before your first PR.
