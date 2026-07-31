---
template: integration
version: 1.0.0
type: onboarding-guide
summary: "OAuth setup walkthrough for the gws CLI — covers Pvragon Workspace accounts (contact Farhan), personal Google accounts (full DIY), and how to run both side-by-side. Includes the 7-day refresh-token gotcha and how to recover from it."
created: 2026-05-09
last_updated: 2026-05-09
maintainer: pvragon
---

# gws CLI — OAuth Setup Guide

The `gws` CLI needs an OAuth client (developer credentials) and an authenticated user (you) to talk to Google APIs. There are two normal paths through this depending on which Google account you're connecting:

| Path | Use when | Effort | Who configures GCP |
|---|---|---|---|
| **A — Pvragon Workspace** (`@pvragon.com`) | Default for team members doing Pvragon work | ~5 min | Farhan |
| **B — Personal Google account** (consumer `@gmail.com` etc.) | Personal automation, side projects, anything outside Pvragon | ~15 min | You |

Both paths can coexist on the same machine — see [Running both side-by-side](#running-both-side-by-side) at the bottom.

---

## Path A — Pvragon Workspace account

**Contact Farhan.** He maintains the dedicated `pvragon-ai-workspace` GCP project that hosts the OAuth client used by everyone on the team. He'll provide:

1. The `client_secret.json` for the team Desktop OAuth client.
2. Your `@pvragon.com` email added to the project's allowed audience (if relevant).
3. Confirmation that the consent screen is in **Production** status (so your refresh tokens don't expire — see [the 7-day gotcha](#the-7-day-refresh-token-gotcha) below).

### Once Farhan gives you the file

```bash
mkdir -p ~/.config/gws
cp /path/to/client_secret.json ~/.config/gws/client_secret.json
chmod 600 ~/.config/gws/client_secret.json
gws auth login
# → opens browser, sign in as your @pvragon.com account, click through scopes
gws auth status   # verify
```

That's it. **Do not create your own GCP project for Pvragon work** — using one shared project keeps audit trails coherent and means Farhan can rotate / revoke credentials centrally if needed.

---

## Path B — Personal Google account (DIY)

Used when you want gws to operate against your own consumer Gmail / Drive / etc., separate from any Workspace org. You'll create your own GCP project (free, no billing required) and configure its OAuth consent screen.

> **The order of operations matters.** If you skip ahead to creating credentials before publishing to Production, every refresh token you mint will expire after 7 days and you'll be re-auth'ing weekly with no obvious explanation. See [the 7-day gotcha](#the-7-day-refresh-token-gotcha) for what's happening and how to recover.

### B1. Create a GCP project

1. Go to [console.cloud.google.com](https://console.cloud.google.com) signed in as your personal Google account.
2. Project picker → **New Project**.
3. Name: anything sensible like `<your-handle>-personal-cli`. Skip organization (consumer accounts don't have one).

No billing account needed. The Gmail/Drive/etc. APIs we'll use have generous free tiers.

### B2. Enable the APIs you'll need

Open each link in a new tab (project picker should show the project you just made), then click **Enable** on each page:

- [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
- [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
- [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
- [Google Docs API](https://console.cloud.google.com/apis/library/docs.googleapis.com)
- [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
- [Google Slides API](https://console.cloud.google.com/apis/library/slides.googleapis.com)
- [Google Tasks API](https://console.cloud.google.com/apis/library/tasks.googleapis.com)
- [People API](https://console.cloud.google.com/apis/library/people.googleapis.com) *(optional — for contacts)*

API library scopes don't show up in the consent-screen picker until the corresponding API is enabled.

### B3. Configure the OAuth consent screen — **Branding tab**

Left nav: **APIs & Services → OAuth consent screen** (a.k.a. "Google Auth Platform").

| Field | Value |
|---|---|
| User type | **External** (consumer Gmail can't use Internal) |
| App name | Anything descriptive — you'll see this on the unverified-app warning |
| User support email | Your personal Google address |
| Developer contact | Your personal Google address |
| App domain / Authorized domains | Leave blank |

### B4. **Data Access tab — add scopes**

Click **Add or remove scopes** and pick the set you actually need. Recommended baseline (mirrors what Pvragon's gws config uses):

```
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
https://www.googleapis.com/auth/calendar
https://www.googleapis.com/auth/documents
https://www.googleapis.com/auth/spreadsheets
https://www.googleapis.com/auth/presentations
https://www.googleapis.com/auth/tasks
https://www.googleapis.com/auth/contacts
https://www.googleapis.com/auth/drive
https://www.googleapis.com/auth/gmail.modify
```

`drive` and `gmail.modify` are *restricted* scopes (red warnings). Ignore the warnings — they affect the unverified-app screen wording, not whether things work.

**What I'd leave off unless you specifically need it:**
- `gmail.send` — lets the CLI (and any agent using it) send mail as you. Higher blast radius.
- `gmail.settings.*` — lets the CLI change forwarding rules, vacation responder, signatures.
- `drive.scripts` — lets the CLI manage Apps Script.

These can be added later (~2 min — re-edit Data Access, re-run `gws auth login`). Adding scopes after the fact does *not* re-trigger the 7-day clock as long as the app is in Production.

### B5. **Audience tab — Publish to Production** (this is the critical step)

| What you should see | What to do |
|---|---|
| Publishing status: **Testing** | Click **Publish app** → confirm "Push to production" → ignore any "Submit for verification" prompt. |
| Publishing status: **In production** | You're done — proceed. |

For single-user personal apps you do **not** need verification. The "Google hasn't verified this app" warning on first auth is the only practical consequence — you click "Advanced → Go to (unsafe)" once, grant scopes, and never see it again on that machine.

### B6. **Clients tab — create the OAuth client** (do this *after* B5, not before)

1. **Create credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Name: anything memorable (e.g. `gws-personal-cli`)
4. **Download JSON** from the success modal.

> If you already created the OAuth client *before* publishing to Production: don't worry, just delete it and create a new one now. Credentials issued in Testing carry the 7-day clock; ones issued in Production don't. See the gotcha below.

### B7. Wire it up locally

```bash
mkdir -p ~/.config/gws-personal
mv ~/Downloads/client_secret_*.json ~/.config/gws-personal/client_secret.json
chmod 600 ~/.config/gws-personal/client_secret.json
GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-personal" gws auth login
# → opens browser, pick your personal account, click through unverified-app warning,
#   grant scopes, browser redirects to localhost — done.
```

Add a permanent alias so you don't have to type the env var every time:

```bash
echo 'alias gws-personal="GOOGLE_WORKSPACE_CLI_CONFIG_DIR=$HOME/.config/gws-personal gws"' >> ~/.bashrc
source ~/.bashrc
gws-personal gmail users getProfile --params '{"userId": "me"}'   # smoke test
```

You should see your email + message/thread totals come back. Done.

---

## The 7-day refresh-token gotcha

This is the one trap that catches people, so it gets its own section.

### What happens

You set up your OAuth consent screen, create credentials right away, run `gws auth login`, everything seems fine. **A week later**, every `gws` call starts failing with `invalid_grant: Token has been expired or revoked` and you can't figure out why nothing changed.

### Why

Google's policy: while your OAuth app's consent screen is in **Testing** status, every refresh token issued to a user authenticating against any **sensitive** or **restricted** scope expires **7 days** after consent. This is intentional — Testing is meant for short-lived development, not real use.

`gmail.modify`, `drive`, and `userinfo.email` are all sensitive/restricted, so they all trigger this. You can't avoid it by picking different scopes if you want any real Gmail or Drive access.

### Why "publish to Production" alone isn't always enough to fix it

Here's the second-order trap. Even after you flip the consent screen to "In production":

> **Refresh tokens that were *issued* while the app was in Testing keep the 7-day clock forever.**

Publishing to Production only changes the behavior of *new* tokens minted after the publish. Any existing token still expires on its original schedule.

### How to recover (if you're stuck on the 7-day cycle)

1. **Verify** publishing status: APIs & Services → OAuth consent screen → Audience tab. It must say **In production**. If it says Testing, click **Publish app** first.
2. **Delete the existing OAuth client**: APIs & Services → Credentials → click the client → **Delete**.
3. **Create a fresh OAuth client** (same way as before — Desktop app type). Download the new JSON.
4. **Replace the local credentials**:
   ```bash
   rm ~/.config/gws/credentials.* ~/.config/gws/token_cache.json 2>/dev/null
   cp /path/to/new-client_secret.json ~/.config/gws/client_secret.json
   chmod 600 ~/.config/gws/client_secret.json
   gws auth login
   ```
5. The new refresh token will persist indefinitely.

### How to verify you're past it

After re-auth, run `gws auth status` and confirm `"token_valid": true`. Then leave it alone for >7 days and try a `gws` call. If it works, you're past the gotcha for good.

### One-line preventive

**Order of operations: Publish to Production *before* creating OAuth credentials, every time.** This guide puts B5 before B6 for exactly this reason.

---

## Running both side-by-side

If you do Pvragon work on the same machine where you also use a personal account, run both with separate config dirs:

```bash
# Pvragon (default — uses ~/.config/gws/)
gws gmail users getProfile --params '{"userId": "me"}'
# → returns your @pvragon.com profile

# Personal (uses ~/.config/gws-personal/)
gws-personal gmail users getProfile --params '{"userId": "me"}'
# → returns your @gmail.com profile
```

The `gws` CLI honors the `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` env var; the `gws-personal` alias just sets that var pointing at a parallel config dir. No interference between the two.

You can extend the same pattern for additional accounts (e.g. a client's Workspace) — pick a config dir, point an alias at it, run `gws auth login` once.

---

## Verification & troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Authentication successful` but later calls fail with `403 Delegation denied` | Calling Gmail with a `userId` that isn't the authenticated account, e.g. trying `userId: your-username@gmail.com` from a `@pvragon.com`-authed token | Use `userId: "me"` — it always means the authenticated account. Or auth as the right user in the right config dir. |
| `invalid_grant: Token has been expired or revoked` after exactly 7 days | Refresh token was issued while consent screen was in Testing | See [How to recover](#how-to-recover-if-youre-stuck-on-the-7-day-cycle) above |
| `Auth error` / `Token has been expired or revoked` after months of working | Token revoked at [myaccount.google.com/permissions](https://myaccount.google.com/permissions), or password changed, or account inactive >6 months | Re-run `gws auth login` |
| `gcloud CLI not found` when running `gws auth setup` | `auth setup` requires gcloud; you don't actually need `auth setup` if you already have `client_secret.json` in place | Skip `auth setup`. Just run `gws auth login` directly. |
| Scopes you expected aren't in the consent screen picker | The corresponding API isn't enabled in your GCP project | Go to APIs & Services → Library → Enable the missing API → reload the consent screen |
| Browser opens but never redirects back to localhost | WSL2 networking edge case, or some browsers block `localhost` redirects | Try a different browser (Chrome usually works); or copy the auth code manually from the URL after `?code=` and paste into the terminal prompt if `gws` falls back to manual mode |

---

## Related docs

- [`INTEGRATION.md`](./INTEGRATION.md) — gws CLI command reference and skill integration patterns
- `team-lib/GETTING_STARTED.md` — broader workspace onboarding (this doc is referenced from there for the gws step)
