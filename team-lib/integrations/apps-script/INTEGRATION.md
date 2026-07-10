---
template: integration
version: 1.0.0
summary: "Google Apps Script remote execution interface via clasp CLI. Enables creating and running Apps Script functions from the workspace — covers capabilities the Google Docs/Sheets/Slides REST APIs cannot reach (page numbers, first-page headers, auto-text, Forms API, etc.)."
type: remote-execution
created: 2026-03-20
last_updated: 2026-03-20
maintainer: pvragon
---

# Apps Script Integration

## What This Is

A remote execution interface for Google Apps Script. You write `.gs` functions locally, deploy them to Google's servers via `clasp push`, and execute them via `clasp run-function`. This gives the workspace access to the full Apps Script API surface — `DocumentApp`, `SpreadsheetApp`, `DriveApp`, `GmailApp`, `CalendarApp`, `SlidesApp`, `FormApp`, and more.

## Why It Exists

The Google Workspace REST APIs have structural gaps that have been open for 10+ years with no resolution. Apps Script can do things the REST API cannot:

| Capability | REST API | Apps Script |
|---|---|---|
| Auto-updating page numbers in docs | No (`insertAutoText` doesn't exist) | `footer.appendPageNumber()` |
| "Different first page" header creation | No (only `DEFAULT` type) | `doc.setHeaderFirstPageDifferent(true)` |
| Google Forms creation | No REST API exists | `FormApp.create()` |
| Advanced Slides layout | Limited | Full `SlidesApp` access |
| Sheets data validation rules | Limited | Full `SpreadsheetApp` access |

## Prerequisites (per developer, one-time setup)

1. **Install clasp:** `npm install -g @google/clasp`
2. **Enable Apps Script API:** Visit https://script.google.com/home/usersettings and toggle on
3. **Enable Apps Script API on GCP project:** Visit https://console.cloud.google.com/apis/library/script.googleapis.com?project=your-gcp-project and click Enable
4. **Login (management):** `clasp login --creds ~/.config/gws/client_secret.json`
5. **Login (execution):** `clasp login --creds ~/.config/gws/client_secret.json --use-project-scopes --user run`
6. **Link GCP project:** In the Apps Script editor (Project Settings → GCP Project → Change project → paste project number `YOUR_PROJECT_NUMBER`)
7. **Deploy as API Executable:** In the Apps Script editor (Deploy → New deployment → API Executable → access: Anyone)

## Available Scopes

The project is authorized for:
- `documents` — Google Docs
- `drive` — Google Drive
- `spreadsheets` — Google Sheets
- `calendar` — Google Calendar
- `gmail.modify` / `gmail.send` — Gmail
- `presentations` — Google Slides
- `forms` — Google Forms
- `groups` — Google Groups
- `script.external_request` — External HTTP calls

## Usage

From the `apps-script/` directory:

```bash
# Push local changes to Google
clasp push -f

# Run a function
clasp run-function functionName --user run

# Run with parameters
clasp run-function functionName --user run --params '["arg1", "arg2"]'
```

## Project Details

- **Script ID:** `YOUR_SCRIPT_ID`
- **GCP Project:** `your-gcp-project` (project number: `YOUR_PROJECT_NUMBER`)
- **OAuth Client:** Desktop App via `~/.config/gws/client_secret.json`
- **Editor URL:** https://script.google.com/d/YOUR_SCRIPT_ID/edit

## Adding New Functions

1. Write your function in `Code.gs` (or add a new `.gs` file)
2. `clasp push -f` to deploy
3. `clasp run-function yourFunction --user run` to test
4. If new OAuth scopes are needed, add to `appsscript.json` and re-authorize the `run` user
