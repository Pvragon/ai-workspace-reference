# Dual-stack architecture — shadcn (Nextbase) + Untitled UI, one brand

Decision doc for how `build-brand-site` reconciles two component systems without
forcing a choice. Written for the ONE Mahjong / Pvragon context (v4 Nextbase line);
generalizes to any brand. Share the "For JP" section below with the lead engineer.

## The problem
- We want to base products on **Nextbase** (paid, v4), which ships **shadcn / Radix**
  (moving toward **Base UI** — see Watch below) + lucide + magicui.
- Our lead engineer (JP) is committed to **Untitled UI** (react-aria) and will reach for
  it on anything he builds — and we already shipped ONE Mahjong's marketing site on it.

## The resolution: tokens are the contract, the kit is per-surface
Both shadcn and Untitled UI are the same *kind* of thing — copy-in (you own the code),
Tailwind-based, token-driven component sets. They differ only in the primitive layer,
the token names, and the variant engine:

| | shadcn (Nextbase) | Untitled UI (JP / marketing) |
|---|---|---|
| Primitives | Radix → Base UI | react-aria |
| Theme tokens | `--primary` `--background` `--border` `--ring` `--radius` | `@theme --color-brand-*` + semantic |
| Variant engine | cva | tailwind-variants |

Put the brand in **one `brand-tokens.json`** (from `create-brand-guidelines`). A single
generator emits **both** theme targets from it, so a shadcn button and an Untitled UI
button render the *same brand* — identical color, type, radius:

```
brand-tokens.json  (single source of truth)
        │
        ├──►  shadcn theme    (:root { --primary … --ring … })      → Nextbase app surfaces
        └──►  Untitled UI @theme (--color-brand-* … semantic)        → marketing / brand surfaces
```

This is the `brand-site-scaffold` generator (`build-brand-theme.mjs`) extended to a second
output target. Brand fidelity is guaranteed at the token layer regardless of which kit a
given screen uses.

## The convention that keeps it coherent (split by surface)
Nextbase is a Turborepo (multiple apps/packages). Use each kit where it is strongest:
- **shadcn → SaaS app surfaces** (auth, dashboard, billing, data tables, command menu) —
  inherit Ultimate's machinery for free; that's the point of paying for it.
- **Untitled UI → marketing / landing / brand surfaces** — where design distinctiveness
  matters most, where JP works, and where ONE Mahjong already lives.

**Hard rule: one kit per *page*.** Don't mix a Radix/Base-UI widget and a react-aria widget
in the same view — different primitive stacks. Split at the app / route-group boundary,
which the monorepo already encourages. Both sides read the same tokens, so the seam is
invisible to the user.

## Why this is best-of-both, not a compromise
- JP gets Untitled UI on everything he touches; no framework-fighting.
- Products sit on Nextbase/shadcn + the paid Ultimate + the landing/component kits.
- The brand looks identical across both because tokens are the contract.
- The `build-brand-site` skill suite survives intact — it just gains a shadcn adapter in
  `brand-site-scaffold` / `brand-site-components`; methodology, gates, and gotchas hold.

## Cost / risk
Two component systems = more surface area; the generator emits two targets. Mitigated by
the one-kit-per-page rule + the shared token contract. Keep the marketing/app split clean
and the maintenance stays bounded.

## The seam — DECIDED 2026-07-23
**Untitled UI = marketing / brand / landing surfaces. shadcn/Base UI = app surfaces**
(auth, dashboard, billing, tables, settings, command menu). One kit per page; both consume
the same `brand-tokens.json`. This is the default line, chosen so JP owns Untitled UI where
design distinctiveness matters (and where ONE Mahjong already lives) while the product
inherits Nextbase's app machinery. Revisit only if a specific app surface needs UUI — move
that route-group's boundary, don't mix kits within a page.

## Watch: shadcn → Base UI
Nextbase's newest `nextbase-component-kit` HEAD is "rebuild Base UI component catalog" —
they're migrating the shadcn/Radix line onto **Base UI** (`@base-ui-components`, the
Radix successor). The dual-adapter model is unaffected (still `:root` CSS-var tokens); just
target the current Nextbase primitive when generating the shadcn-side components.

## Nextbase repo sync (Pvragon copies are NOT forks)
`Pvragon/*` Nextbase repos are independent copies (no shared history with `imbhargav5/*`),
so there's no `gh repo sync`. To refresh from upstream:
```
gh repo clone imbhargav5/<repo> /tmp/<repo> -- --single-branch --branch main
cd /tmp/<repo> && git remote add pvragon https://github.com/Pvragon/<repo>.git
git push pvragon main:main            # empty/refreshable target
# repo with content to preserve: push to a NEW branch, or archive main first, then promote
```
Latest upstream as of 2026-07-22: component-kit, landing-kit (10 templates),
teams-only-ultimate, ai-starter — all synced to Pvragon. **`Pvragon/nextbase-ultimate-v4`**
(renamed from `-v4-alpha`; old name redirects) holds the mainline v4 Ultimate snapshot and is
the canonical base. `Pvragon/nextbase-ultimate` is archived (read-only, retired).
