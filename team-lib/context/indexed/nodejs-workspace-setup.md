---
template: technical-context
version: 1.0.1
summary: "Node.js global npm setup: NODE_PATH configuration for global require() support, when to use global vs local install. Load when troubleshooting npm or setting up Node.js tooling."
created: 2026-01-26
last_updated: 2026-02-18
maintainer: pvragon
tags: [nodejs, npm, environment-setup, global-packages]
---

# Node.js Workspace Setup

## Global NPM Packages and NODE_PATH

When using globally installed npm packages (`npm install -g package-name`):

### Critical Issue

**Node.js `require()` does NOT automatically find global modules.**

Running `npm install -g docx` installs to:
```
/home/username/.nvm/versions/node/vXX.XX.X/lib/node_modules/docx
```

But `require('docx')` only searches:
1. Current directory's `node_modules/`
2. Parent directory's `node_modules/` (recursively up the tree)
3. **NOT** the global npm directory

### Solution: Set NODE_PATH

Add to `~/.bashrc` in **Section 3 (Global Environmental Variables)**:

```bash
# Add global npm modules to NODE_PATH for require() support
export NODE_PATH=$(npm root -g):$NODE_PATH
```

This tells Node.js to also search the global npm directory when resolving `require()` statements.

### Why This Matters

- **Anthropic skills** (docx, etc.) assume global installation with `npm install -g`
- Global install makes packages available system-wide (no duplication)
- Local install (`npm install docx` without `-g`) works for `require()` but duplicates dependencies in every project

### Verification

After adding NODE_PATH and sourcing bashrc:

```bash
source ~/.bashrc
echo $NODE_PATH  # Should show: /home/user/.nvm/versions/node/vX.X.X/lib/node_modules:

# Test require() works
node -e "const docx = require('docx'); console.log('✅ Success');"
```

### When to Use Global vs Local Install

**Global install (`npm install -g`):**
- CLI tools used across projects
- Libraries referenced by skills (e.g., docx for Anthropic skills)
- System-wide utilities

**Local install (`npm install`):**
- Project-specific dependencies
- When working in a directory with its own `package.json`
- Tightly version-controlled dependencies

### Already Configured

NODE_PATH is already configured in this workspace (added 2026-01-26). New terminals will automatically have access to global npm modules via `require()`.
