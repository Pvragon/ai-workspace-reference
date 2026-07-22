---
template: onboarding-guide
version: 0.1.0
summary: "DRAFT. The step-zero card for a total newbie: get Claude Max, open the desktop app's Code tab, paste one prompt pointing at the repo, and let the agent do the rest. The absolute minimum a non-technical person needs to start; hands off to DESKTOP_APP_SETUP.md (which the agent reads)."
status: draft
created: 2026-07-21
last_updated: 2026-07-21
maintainer: pvragon
---

# Start Here (Step Zero) — Your Own AI Agent, No Experience Needed

You don't need to understand any of this. Do these steps in order, then your agent takes over and
walks you through everything else.

*Who this is for: anyone adopting the public Pvragon reference workspace. (If you're a Pvragon team
member with a GitHub org invite, you follow the internal library path instead — your onboarding note
covers it — not this public copy.)*

## The five steps

1. **Get a Claude subscription.** Go to [claude.com](https://claude.com/pricing) and subscribe to
   **Claude Max** (the cheaper **Pro** plan also works; Max just gives you more room to work).

2. **Install the Claude desktop app** and open it:
   - **Windows:** [download here](https://claude.ai/api/desktop/win32/x64/setup/latest/redirect)
   - **Mac:** [download here](https://claude.ai/api/desktop/darwin/universal/dmg/latest/redirect)

   Run the installer, open **Claude**, and sign in with the account from step 1.

3. **Click the "Code" tab** at the top of the app.

4. **Start a session** (if it asks for a folder, pick any folder for now, like your Documents), then
   **paste this exactly** into the chat box and send it:

   > I want to set up the Pvragon AI workspace on this computer. I'm not technical. Please read the
   > guide at https://github.com/Pvragon/ai-workspace-reference — start with `team-lib/ONBOARDING.md`
   > and `team-lib/START_HERE_DESKTOP.md` / `team-lib/DESKTOP_APP_SETUP.md` — and walk me through the
   > whole setup one step at a time. Run whatever you safely can for me. Whenever I need to do
   > something myself, tell me exactly what to click or type and where, and wait for me to say "done"
   > before moving to the next step.

5. **Follow what your agent tells you.** It reads the setup guide and leads from here. The one-time
   setup has several short hands-on moments — you'll paste a handful of commands into a terminal it
   points you to, click through a couple of sign-ins, and restart the computer once for the Linux
   system. The agent tells you *exactly* what to do each time and waits. Say **"done"** after each
   step. Once setup is finished, it takes over fully and you rarely touch the terminal again.

That's the whole card. Everything past this point, your agent walks you through.

---

### What to expect (so nothing surprises you)
- **Time:** about an hour the first time, most of it just waiting for downloads.
- **You'll make a free GitHub account** partway through — the agent walks you through it.
- **One restart** of your computer during setup (for the Linux system). Normal. Reopen the app after.
- **At the end** you'll have your own AI agent — with a name it picks itself — that knows how to work
  the way this workspace does.

*If your agent ever seems stuck or unsure, tell it: "re-read `team-lib/DESKTOP_APP_SETUP.md` and let's
pick up where we left off." That guide is written for it to follow.*
