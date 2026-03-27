---
template: agent-safety
version: 1.0.1
summary: "Workspace root safety gate. Prevents agents from working at the root level; redirects to a valid scope."
last_updated: 2026-02-18
maintainer: pvragon
---

# 🛑 STOP - WRONG DIRECTORY
You are at the **Workspace Root** (`~/ai-workspace`).
**NO WORK IS PERMITTED HERE.**

### Instructions
1. **Do not create files.**
2. **Do not run commands.**
3. **Do not make changes.**

**Action:** Ask the user to move to a scope: `personal/`, `team-lib/`, `my-lib/`, or `projects/`.

