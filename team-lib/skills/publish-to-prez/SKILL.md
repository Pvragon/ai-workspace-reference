---
template: skill-definition
version: 1.0.0
summary: "Publish an agentically-created, self-contained HTML artifact (or a branded deck) to prez.prgn.ai — the Pvragon presentations host. Covers file placement + naming, embedding diagrams (mermaid→Excalidraw), the password/protected-path mechanism, deploy-by-push, and the 401→200 verification. This is the standard home for agent-generated HTML, not a one-off."
created: 2026-07-21
last_updated: 2026-07-21
maintainer: pvragon
---

# Skill: Publish to prez.prgn.ai

## What prez is

`prez.prgn.ai` (alias `prez.pvragon.com`) is Pvragon's host for **agentically-created HTML** —
self-contained pages and branded decks. It is the standard, permanent, team-owned home for
HTML artifacts you'd otherwise leave in a throwaway Claude Artifact or a local file.

- **Repo:** `Pvragon/presentations` (cloned at `~/ai-workspace/projects/presentations`).
- **Hosting:** Vercel, **auto-deploys on push to `main`**. No build step (`vercel.json` →
  `buildCommand: ""`, `outputDirectory: "."`, `cleanUrls: true`).
- **`cleanUrls`:** `northwind/foo.html` is served at `/northwind/foo` (drop the `.html` in shared links).
- **Auth:** per-path password gating via `middleware.js` (see §Passwords).

**Git = source of truth; the deployed page is a rendered view.** Never treat a live URL as the
only copy — the committed file in this repo is the record. (This is the lesson that motivated the
skill: a Claude Artifact is Anthropic-hosted, unversioned, and not ours; prez is all three.)

## When to use

- You generated a **self-contained HTML artifact** (report, handoff page, dashboard, one-pager,
  interactive explainer) and want a permanent, shareable, optionally password-gated URL on our
  own domain. **← the primary use.**
- You produced a **branded slide deck** from markdown and want it in the category browser.

**When NOT to use:** live apps with a backend (that's `play.prgn.ai` / a real Vercel app), or
anything that isn't a static, self-contained file.

## Two flows

| Flow | What | How |
|------|------|-----|
| **A — Artifact** | A single self-contained `.html` (embed all CSS/JS/assets) | Drop the file in a category folder, push. §Flow A. |
| **B — Branded deck** | Slide deck from a `.md` source | Use `markdown-to-branded-doc` + add an index card. See the repo `README.md`. |

Most agent output is **Flow A.** Flow B (decks with category index cards, topic groups, search
`data-search`) is fully documented in `~/ai-workspace/projects/presentations/README.md` — follow
that for decks; don't duplicate it here.

---

## Flow A — publish a self-contained artifact

### 1. Author the HTML self-contained
Everything inlined — CSS in a `<style>`, JS in `<script>`, images as `data:` URIs, fonts embedded.
No external CDN/webfont/script references (they may be blocked or rot). Make it a full standalone
doc (`<!doctype html><html><head>…</head><body>…`). Design both light and dark themes and keep it
responsive (wide content in its own `overflow-x:auto` container).

### 2. Diagrams — render, don't rely on a runtime
prez has **no client-side mermaid runtime.** If your artifact has a mermaid diagram, render it to
a static, inline SVG first — and upcycle it to the Excalidraw hand-drawn look while you're at it,
via the **`mermaid-to-excalidraw`** skill:

```bash
# lock the mermaid logic first, in a .mmd file
node ~/ai-workspace/team-lib/integrations/excalidraw-cli/bin/excalidraw.mjs mermaid \
  <name>.mmd -o <out>/ -f svg,png --scale 3
```

- **Gotcha:** the Excalidraw mermaid parser renders `<br/>` as **literal text**. Preprocess the
  `.mmd`, replacing `<br/>` / `<br>` with real newlines, before rendering.
- **Visually verify the PNG** (the skill mandates this) — labels present/legible, arrows correct.
- **Inline the `.svg`** into your page (it's self-contained: `viewBox` intact, font embedded as a
  data URI). Give it `style="width:100%;height:auto;display:block"`. This removes any runtime dep
  and stays crisp at any zoom.

### 3. Place + name the file
Put it in the right **category folder** (e.g. `northwind/` for Acme Health/Northwind work — Acme Health content
lives under `/northwind`). Name it `YYMMDD-descriptive-name.html` (date prefix, self-documenting):

```
~/ai-workspace/projects/presentations/northwind/260721-transport-status-pipeline-handoff.html
```

A file dropped under an existing category is served immediately at `/<category>/<name>` — you do
**not** need to add an index card unless you want it to appear in the category browser (that's the
Flow-B index-card step).

### 4. Decide access — public vs protected
If the content is internal or sensitive (financials, client data, anything non-public), it MUST
live under a **password-protected path**. See §Passwords. Existing categories that are already
protected (e.g. `/northwind`, `/one-mahjong`) protect **every file beneath them automatically** — no
extra step; just drop the file in that folder.

### 5. Deploy
```bash
cd ~/ai-workspace/projects/presentations
git add <category>/<file>.html
git commit -m "feat(<category>): <what> (prez artifact)"
git push origin main        # Vercel auto-deploys (needs the push go-ahead)
```

### 6. Verify (don't assume the deploy worked)
Wait ~20–60s, then confirm the route is live and (if protected) gated. Use a normal browser UA
(Vercel bot-challenges headless/unknown agents):

```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
URL="https://prez.prgn.ai/<category>/<name>"
curl -s -o /dev/null -w "%{http_code}\n" -A "$UA" "$URL"                         # protected → 401
curl -s -o /dev/null -w "%{http_code}\n" -A "$UA" \
  --cookie "prez_auth_<category>=<password>" "$URL"                              # → 200 + content
```
A `401` on the plain request (not `404`) confirms the route deployed and the gate is active; `200`
with the cookie confirms the real page serves. Grep the authed body for a known marker to be sure.

---

## Passwords & protected paths (mechanism)

Auth is enforced by `projects/presentations/middleware.js`. It is **password-per-path**, not
per-user. **The passwords themselves are NOT in this repo** — they are Vercel env vars on the
`presentations` project (scope `pvragon-dev`). To learn or rotate a value, use the Vercel CLI
(token in `personal/secrets/.env`) or ask the project owner.

**How it works:**
- `PROTECTED_PATHS` maps a path prefix → an env var, e.g. `'/northwind': 'PREZ_PW_NORTHWIND'`.
- The `config.matcher` array must also list the prefix (`'/northwind'`, `'/northwind/:path*'`).
- Any path at or under a protected prefix is gated (`path === prefix || path.startsWith(prefix+'/')`).
- On correct password (POST), middleware sets cookie `prez_auth_<prefix>` (slashes→underscores),
  value = the password, `Path` scoped to the prefix, `HttpOnly; Secure; SameSite=Lax`, **7-day**
  Max-Age. So one unlock lasts a week per browser.

**To protect a NEW category path:**
1. Add an entry to `PROTECTED_PATHS` in `middleware.js`: `'/newcat': 'PREZ_PW_NEWCAT'`.
2. Add `'/newcat'` and `'/newcat/:path*'` to the `config.matcher` array.
3. Create the env var (do NOT commit the password):
   ```bash
   printf "<password>" | npx vercel env add PREZ_PW_NEWCAT production \
     --scope pvragon-dev --token "$VERCEL_TOKEN"
   ```
4. Push (redeploys). Middleware reads env at request time; existing cookies stay valid to TTL.

**To find which paths are currently protected:** read `PROTECTED_PATHS` in `middleware.js` — it is
the live source of truth (memory/notes drift; new categories get added).

## Guardrails

1. **Self-contained only.** Inline everything. An external reference that rots = a broken artifact.
2. **Internal/sensitive content → protected path, always.** Never publish financials, client data,
   or PHI to an unprotected prefix. A prez link is world-reachable if the path isn't gated.
3. **Never commit a password** to `presentations` (or anywhere in git). Env vars only.
4. **Git is the record.** Commit the source file; the deployed page is derived.
5. **Verify after deploy** (§6). A green push ≠ a working page.

## Reference paths
- Repo: `~/ai-workspace/projects/presentations/` (`README.md` = deck/category flow, index cards).
- Auth: `projects/presentations/middleware.js` (`PROTECTED_PATHS`, matcher).
- Diagram render: `team-lib/skills/mermaid-to-excalidraw/SKILL.md` + `team-lib/integrations/excalidraw-cli/`.
- Deck template: `team-lib/context/indexed/companies/pvragon/brand/assets/templates/html-presentation.html`.
- Deck authoring: `team-lib/skills/markdown-to-branded-doc/SKILL.md`.
