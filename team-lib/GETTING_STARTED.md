---
template: onboarding-guide
version: 3.0.0
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
>
> Using the public reference repo? It **is** your starting team library — ONBOARDING.md's bootstrap knows how to extract it directly; no access to any private repo is needed.

---

## Appendix: Fork-Based Contributor Flow

Want to improve the reference (or your team's library) with the extra isolation of a fork — you literally cannot touch `main`? Use this flow.

1. **Fork the repository** on GitHub → your username.
2. **Point your clone at your fork:**
   ```bash
   cd <your-clone>
   git remote set-url origin https://github.com/<YOUR-USERNAME>/<repo>.git
   git remote add upstream https://github.com/Pvragon/ai-workspace-reference.git
   ```
3. **Stay current:** before starting work, `git pull upstream main` (or click **Sync fork** on GitHub).
4. **Work on a branch, push to your fork:**
   ```bash
   git checkout -b feature/my-cool-feature
   # ... work ...
   git push origin feature/my-cool-feature
   ```
5. **Open the Pull Request:** on GitHub, click **Compare & pull request**. The **base repository** is the upstream repo, base branch `main`; the **head** is your fork's feature branch.

Read [directives/team-library-governance.md](directives/team-library-governance.md) before your first PR.
