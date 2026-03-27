---
template: directive
version: 1.1.0
summary: "Governance rules for team-lib: naming conventions, graduation requirements, PR process, and quality standards. Required reading before any graduation to team-lib."
last_updated: 2026-02-18
maintainer: pvragon
---

# Directive: Team Library Governance

**Purpose:** Ensure `team-lib` remains a high-quality, standardized operating system for the entire team, preventing it from becoming a "junk drawer" of personal scripts.

---

## 1. Golden Rule: No Personal Code
*   **Concept:** `team-lib` is Shared Infrastructure.
*   **Rule:** If a script or resource is specific to a single user (e.g., hardcoded paths, user-specific APIs, "username-test"), it **MUST NOT** be in `team-lib`.
*   **Check:**
    *   No filenames with user prefixes (e.g., `username-scraper.py`).
    *   No hardcoded paths to `/home/<user>/...` (Use `$WORKSPACE_ROOT`).
    *   No personal secrets or tokens.

## 2. Naming Conventions (Strict)
Consistency reduces cognitive load.

| Type | Convention | Example |
|------|------------|---------|
| **Markdown Files** | `kebab-case.md` | `code-review-policy.md` |
| **Python Scripts** | `snake_case.py` | `web_scraper.py` |
| **Classes** | `PascalCase` | `class WebScraper:` |
| **Directories** | `kebab-case/` | `context/global/` |

**Prohibited:**
*   Spaces in filenames (`web scraper.py`)
*   Mixed case in filenames (`WebScraper.py` - unless strictly required by a specific framework)

## 3. The "Definition of Done" for Graduation
A file is not ready for `team-lib` until it meets these criteria:

### A. Documentation
*   **Markdown:** Must have YAML frontmatter with `version`, `maintainer`, and `summary` fields. See `context/indexed/progressive-disclosure-convention.md`.
*   **Scripts:** Must have a top-level docstring explaining Usage, Inputs, and Outputs.

### B. Quality Assurance
*   **Scripts:** For every `executions/script_name.py`, there should ideally be a `harnesses/test_script_name.py`.
*   **Scripts:** Must expose a `run()` entry point for importability, in addition to CLI invocation via `if __name__ == "__main__"`. See `context/indexed/execution-standard.md`.
*   **Safety:** Code must handle errors gracefully (no raw stack traces to user if avoidable).

## 4. Graduation Process (The "Librarian")
**POLICY:** Direct pushes to the `main` branch of `team-lib` are **FORBIDDEN**. All changes must go through a Pull Request.

1.  **Develop** in `my-lib`.
2.  **Graduate** using `python my-lib/executions/graduate_files.py`.
    *   *System validates naming, metadata, and genericness.*
3.  **Pull Request**:
    *   Create a branch in `team-lib`.
    *   Open a Pull Request.
    *   Review against this Governance Directive.
    *   Merge only when "Definition of Done" is met.

## 5. Versioning
*   **Semantic Versioning**: Use `Major.Minor.Patch` (1.0.0).
*   **Conflict Resolution**: If `team-lib` has v1.2.0 and you have v1.1.0, you **cannot** overwrite. You must pull, merge, and increment.

---

**Violations of this directive will result in rejected graduation attempts.**
