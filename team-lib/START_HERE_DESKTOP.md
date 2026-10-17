---
template: onboarding-guide
version: 0.2.0
summary: "DRAFT. The step-zero card for a total newbie: get a Claude plan, open the desktop app's Code tab, paste one prompt pointing at the public reference repo, and let the agent do the rest. Works on your own or when joining a team that runs its own library; hands off to DESKTOP_APP_SETUP.md (which the agent reads)."
status: draft
created: 2026-07-21
last_updated: 2026-10-16
maintainer: pvragon
---

# Start Here (Step Zero): Your Own AI Agent, No Experience Needed

You don't need to understand any of this. Do these steps in order, then your agent takes over and
walks you through everything else.

*Who this is for: anyone setting up this AI workspace on their own computer. If you're joining a team
that already runs its own team library, ask your team's onboarding contact for that library's repo
URL before you start, and add it to the prompt in step 4 (there's a line for it).*

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

   > I want to set up the AI workspace from https://github.com/Pvragon/ai-workspace-reference on this
   > computer. I'm not technical. Please read its setup guide, starting with `team-lib/GETTING_STARTED.md`,
   > then `team-lib/START_HERE_DESKTOP.md` and `team-lib/DESKTOP_APP_SETUP.md`, and walk me through the
   > whole setup one step at a time. Run whatever you safely can for me. Whenever I need to do
   > something myself, tell me exactly what to click or type and where, and wait for me to say "done"
   > before moving to the next step.

   **Joining a team?** Add this line to the end of the prompt, with the URL your onboarding contact
   gave you:

   > I'm joining a team that runs its own team library at <team library repo URL>. Use the
   > "Joining a team" path in the guide.

5. **Follow what your agent tells you.** It reads the setup guide and leads from here. The one-time
   setup has several short hands-on moments: you'll paste a handful of commands into a terminal it
   points you to, click through a couple of sign-ins, and restart the computer once for the Linux
   system. The agent tells you *exactly* what to do each time and waits. Say **"done"** after each
   step. Once setup is finished, it takes over fully and you rarely touch the terminal again.

That's the whole card. Everything past this point, your agent walks you through.

---

### What to expect (so nothing surprises you)
- **Time:** about an hour the first time, most of it just waiting for downloads.
- **You'll make a free GitHub account** partway through, if you don't have one. The agent walks you
  through it.
- **One restart** of your computer during setup (for the Linux system). Normal. Reopen the app after.
- **Nothing else is required.** Connections to tools like Google Workspace or ClickUp are optional and
  can be added later, only if you use them.
- **At the end** you'll have your own AI agent, with a name it picks itself, that knows how to work
  the way this workspace does.

*If your agent ever seems stuck or unsure, tell it: "re-read `team-lib/DESKTOP_APP_SETUP.md` and let's
pick up where we left off." That guide is written for it to follow.*
