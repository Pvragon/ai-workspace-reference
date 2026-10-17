---
template: integration
version: 1.1.0
type: onboarding-guide
summary: "OAuth setup walkthrough for the gws CLI: an organization's shared OAuth client (from your workspace admin), a personal Google account (full DIY), and how to run both side by side. Includes the 7-day refresh-token gotcha and how to recover from it."
created: 2026-05-09
last_updated: 2026-10-16
maintainer: pvragon
---

# gws CLI: OAuth Setup Guide

The `gws` CLI needs an OAuth client (developer credentials) and an authenticated user (you) to talk to Google APIs. There are two normal paths, depending on which Google account you're connecting and who manages the OAuth client:

| Path | Use when | Effort | Who configures Google Cloud |
|---|---|---|---|
| **A: Your organization's shared OAuth client** | Your account is in a Google Workspace organization whose admin already runs a shared OAuth client for this workspace | About 5 min | Your workspace admin |
| **B: Your own OAuth client** (personal `@gmail.com`, or any account with no shared client) | Personal automation, side projects, or a solo install | About 15 min | You |

Both paths can coexist on the same machine; see [Running both side by side](#running-both-side-by-side) at the bottom.

---

## Path A: Your organization's shared OAuth client

**Ask your Google Workspace admin.** If your organization runs a dedicated Google Cloud project that hosts a shared Desktop OAuth client for everyone using this workspace, the admin provides:

1. The `client_secret.json` for that shared Desktop OAuth client.
2. Your account added to the project's allowed audience, if the client is restricted.
3. Confirmation that the consent screen is in **Production** status, so your refresh tokens don't expire (see [the 7-day gotcha](#the-7-day-refresh-token-gotcha) below).

### Once you have the file

```bash
mkdir -p ~/.config/gws
cp /path/to/client_secret.json ~/.config/gws/client_secret.json
chmod 600 ~/.config/gws/client_secret.json
gws auth login
# opens a browser: sign in with your organization account and click through the scopes
gws auth status   # verify
```

That's it. **If your organization provides a shared client, don't create your own Google Cloud project for work accounts.** One shared project keeps audit trails coherent and lets the admin rotate or revoke credentials centrally.

If your organization has no shared client, use Path B with your work account instead (your admin may need to allow the app).

---

## Path B: Your own OAuth client (DIY)

Use this when you want gws to operate against your own Gmail, Drive, and so on, separate from any organization, or when no shared client exists for you. You'll create your own Google Cloud project (free, no billing required) and configure its OAuth consent screen.

> **The order of operations matters.** If you skip ahead to creating credentials before publishing to Production, every refresh token you mint will expire after 7 days, and you'll be re-authenticating weekly with no obvious explanation. See [the 7-day gotcha](#the-7-day-refresh-token-gotcha) for what's happening and how to recover.

### B1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com), signed in as the Google account you're connecting.
2. Project picker, then **New Project**.
3. Name: anything sensible, like `<your-handle>-personal-cli`. Skip organization (consumer accounts don't have one).

No billing account needed. The Gmail, Drive, and other APIs used here have generous free tiers.

### B2. Enable the APIs you'll need

Open each link in a new tab (the project picker should show the project you just made), then click **Enable** on each page:

- [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
- [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
- [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
- [Google Docs API](https://console.cloud.google.com/apis/library/docs.googleapis.com)
- [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
- [Google Slides API](https://console.cloud.google.com/apis/library/slides.googleapis.com)
- [Google Tasks API](https://console.cloud.google.com/apis/library/tasks.googleapis.com)
- [People API](https://console.cloud.google.com/apis/library/people.googleapis.com) *(optional, for contacts)*

An API's scopes don't show up in the consent-screen picker until that API is enabled.

### B3. Configure the OAuth consent screen: **Branding tab**

Left nav: **APIs & Services, then OAuth consent screen** (also called "Google Auth Platform").

| Field | Value |
|---|---|
| User type | **External** (consumer Gmail can't use Internal) |
| App name | Anything descriptive; you'll see this on the unverified-app warning |
| User support email | Your own Google address |
| Developer contact | Your own Google address |
| App domain / Authorized domains | Leave blank |

### B4. **Data Access tab: add scopes**

Click **Add or remove scopes** and pick the set you actually need. Recommended baseline (what this workspace's Google skills assume):

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

`drive` and `gmail.modify` are *restricted* scopes (red warnings). Ignore the warnings; they affect the unverified-app screen wording, not whether things work.

**Leave these off unless you specifically need them:**
- `gmail.send`: lets the CLI (and any agent using it) send mail as you. Higher blast radius.
- `gmail.settings.*`: lets the CLI change forwarding rules, the vacation responder, and signatures.
- `drive.scripts`: lets the CLI manage Apps Script.

These can be added later in about 2 minutes (re-edit Data Access, re-run `gws auth login`). Adding scopes after the fact does *not* restart the 7-day clock as long as the app is in Production.

### B5. **Audience tab: Publish to Production** (this is the critical step)

| What you should see | What to do |
|---|---|
| Publishing status: **Testing** | Click **Publish app**, confirm "Push to production," and ignore any "Submit for verification" prompt. |
| Publishing status: **In production** | You're done; proceed. |

For single-user personal apps you do **not** need verification. The "Google hasn't verified this app" warning on first sign-in is the only practical consequence: you click "Advanced," then "Go to (unsafe)" once, grant scopes, and never see it again on that machine.

### B6. **Clients tab: create the OAuth client** (do this *after* B5, not before)

1. **Create credentials, then OAuth client ID.**
2. Application type: **Desktop app**.
3. Name: anything memorable (for example `gws-personal-cli`).
4. **Download JSON** from the success dialog.

> If you already created the OAuth client *before* publishing to Production, don't worry: delete it and create a new one now. Credentials issued in Testing carry the 7-day clock; ones issued in Production don't. See the gotcha below.

### B7. Wire it up locally

If this is your only Google account for gws, put the file in the default config directory and log in:

```bash
mkdir -p ~/.config/gws
mv ~/Downloads/client_secret_*.json ~/.config/gws/client_secret.json
chmod 600 ~/.config/gws/client_secret.json
gws auth login
```

If you also use Path A on the same machine, give the personal account its own config directory instead:

```bash
mkdir -p ~/.config/gws-personal
mv ~/Downloads/client_secret_*.json ~/.config/gws-personal/client_secret.json
chmod 600 ~/.config/gws-personal/client_secret.json
GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-personal" gws auth login
# opens a browser: pick your personal account, click through the unverified-app warning,
# grant scopes, and the browser redirects to localhost. Done.
```

Add a permanent alias so you don't have to type the environment variable every time:

```bash
echo 'alias gws-personal="GOOGLE_WORKSPACE_CLI_CONFIG_DIR=$HOME/.config/gws-personal gws"' >> ~/.bashrc
source ~/.bashrc
gws-personal gmail users getProfile --params '{"userId": "me"}'   # smoke test
```

You should see your email address and message and thread totals come back. Done.

---

## The 7-day refresh-token gotcha

This is the one trap that catches people, so it gets its own section.

### What happens

You set up your OAuth consent screen, create credentials right away, run `gws auth login`, and everything seems fine. **A week later**, every `gws` call starts failing with `invalid_grant: Token has been expired or revoked`, and you can't figure out why, because nothing changed.

### Why

Google's policy: while your OAuth app's consent screen is in **Testing** status, every refresh token issued to a user who consents to any **sensitive** or **restricted** scope expires **7 days** after consent. This is intentional: Testing is meant for short-lived development, not real use.

`gmail.modify`, `drive`, and `userinfo.email` are all sensitive or restricted, so they all trigger this. You can't avoid it by picking different scopes if you want any real Gmail or Drive access.

### Why "publish to Production" alone isn't always enough to fix it

Here's the second-order trap. Even after you flip the consent screen to "In production":

> **Refresh tokens that were *issued* while the app was in Testing keep the 7-day clock forever.**

Publishing to Production only changes the behavior of *new* tokens minted after the publish. Any existing token still expires on its original schedule.

### How to recover (if you're stuck on the 7-day cycle)

1. **Verify** publishing status: APIs & Services, then OAuth consent screen, then the Audience tab. It must say **In production**. If it says Testing, click **Publish app** first.
2. **Delete the existing OAuth client:** APIs & Services, then Credentials, then click the client, then **Delete**.
3. **Create a fresh OAuth client** (same way as before, Desktop app type). Download the new JSON.
4. **Replace the local credentials:**
   ```bash
   rm ~/.config/gws/credentials.* ~/.config/gws/token_cache.json 2>/dev/null
   cp /path/to/new-client_secret.json ~/.config/gws/client_secret.json
   chmod 600 ~/.config/gws/client_secret.json
   gws auth login
   ```
5. The new refresh token will persist indefinitely.

If you're on Path A, the admin does steps 1 to 3 and gives you the new file; you do step 4.

### How to verify you're past it

After re-authenticating, run `gws auth status` and confirm `"token_valid": true`. Then leave it alone for more than 7 days and try a `gws` call. If it works, you're past the gotcha for good.

### One-line preventive

**Order of operations: publish to Production *before* creating OAuth credentials, every time.** This guide puts B5 before B6 for exactly this reason.

---

## Running both side by side

If you use an organization account and a personal account on the same machine, run each with its own config directory:

```bash
# Organization account (default: uses ~/.config/gws/)
gws gmail users getProfile --params '{"userId": "me"}'
# returns your organization profile

# Personal account (uses ~/.config/gws-personal/)
gws-personal gmail users getProfile --params '{"userId": "me"}'
# returns your @gmail.com profile
```

The `gws` CLI honors the `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` environment variable; the `gws-personal` alias just sets that variable to a parallel config directory. The two don't interfere.

You can extend the same pattern to additional accounts (for example, a client's Google Workspace): pick a config directory, point an alias at it, and run `gws auth login` once.

---

## Verification and troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Authentication successful`, but later calls fail with `403 Delegation denied` | Calling Gmail with a `userId` that isn't the authenticated account, for example passing `userId: someone@example.com` while authenticated as a different account | Use `userId: "me"`; it always means the authenticated account. Or authenticate as the right user in the right config directory. |
| `invalid_grant: Token has been expired or revoked` after exactly 7 days | The refresh token was issued while the consent screen was in Testing | See [How to recover](#how-to-recover-if-youre-stuck-on-the-7-day-cycle) above |
| `Auth error` / `Token has been expired or revoked` after months of working | Token revoked at [myaccount.google.com/permissions](https://myaccount.google.com/permissions), password changed, or account inactive for more than 6 months | Re-run `gws auth login` |
| `gcloud CLI not found` when running `gws auth setup` | `auth setup` requires gcloud; you don't need `auth setup` if `client_secret.json` is already in place | Skip `auth setup`. Run `gws auth login` directly. |
| Scopes you expected aren't in the consent-screen picker | The corresponding API isn't enabled in your Google Cloud project | Go to APIs & Services, then Library, enable the missing API, and reload the consent screen |
| Browser opens but never redirects back to localhost | A WSL2 networking edge case, or a browser that blocks `localhost` redirects | Try a different browser (Chrome usually works), or copy the auth code from the URL after `?code=` and paste it into the terminal prompt if `gws` falls back to manual mode |

---

## Related docs

- [`INTEGRATION.md`](./INTEGRATION.md): gws CLI command reference and skill integration patterns
- `team-lib/GETTING_STARTED.md`: broader workspace onboarding (Phase 4 points here for the gws step)
