---
template: integration
version: 1.0.0
type: cli
summary: "Namecheap CLI — full-coverage (59/59 methods) CLI + Python client for the Namecheap API: domains, DNS, SSL, transfers, privacy, users. Public repo at github.com/Pvragon/namecheap-cli. Zero dependencies; billable/destructive ops are confirmation-gated; dns add/rm wrap the all-or-nothing setHosts safely. Restish does NOT fit (XML RPC, no OpenAPI) — same call as waystar-cli."
created: 2026-07-17
last_updated: 2026-07-17
maintainer: pvragon
---

# Namecheap CLI (`namecheap`)

Full-coverage CLI and importable Python client for the
[Namecheap API](https://www.namecheap.com/support/api/intro/). Covers all 59
documented API methods across domains, DNS, child nameservers, transfers,
SSL, users, address book, and domain privacy — plus a raw `api` passthrough
for anything Namecheap adds later.

**Public repo:** <https://github.com/Pvragon/namecheap-cli> (MIT). Docs:
[README](https://github.com/Pvragon/namecheap-cli#readme) ·
[full command reference](https://github.com/Pvragon/namecheap-cli/blob/main/docs/commands.md).

## Why a custom CLI (and not Restish)

Same verdict as `waystar-cli`: the Namecheap API is XML-over-HTTP RPC
(`Command=namecheap.domains.getList`), has no OpenAPI description, and
returns XML — none of which Restish handles. The CLI is generated from a
declarative spec (`src/namecheap_cli/spec.py`) with a coverage-gate test
that fails if the surface ever drifts from Namecheap's documented method
inventory.

## Prerequisites

1. **Python 3.10+** — no runtime dependencies.
2. **API access enabled** on the Namecheap account (Profile → Tools →
   Business & Dev Tools → Namecheap API Access) and the calling machine's
   public IPv4 **whitelisted** (max 10 IPs; check with `curl https://api.ipify.org`).
3. **Credentials** at `~/.config/namecheap/.env` (chmod 600):

   ```
   NAMECHEAP_API_USER=<login username — NOT the email address>
   NAMECHEAP_API_KEY=<production key>
   NAMECHEAP_SANDBOX_API_USER=<sandbox username>
   NAMECHEAP_SANDBOX_API_KEY=<sandbox key>
   ```

   On this workspace the canonical copies live in
   `~/ai-workspace/personal/secrets/.env` (`NAMECHEAP_*` keys); re-sync with:
   `grep -E '^NAMECHEAP_' ~/ai-workspace/personal/secrets/.env > ~/.config/namecheap/.env && chmod 600 ~/.config/namecheap/.env`

## Setup

```bash
pipx install git+https://github.com/Pvragon/namecheap-cli
# or in a project venv:
pip install git+https://github.com/Pvragon/namecheap-cli
namecheap config          # verify credential resolution (never prints keys)
```

## Common commands

```bash
namecheap domains list
namecheap domains check coolidea.com,coolidea.io
namecheap domains info pvra.gon
namecheap dns get-hosts example.com
namecheap dns add example.com --type TXT --name @ --value "v=spf1 -all"
namecheap dns rm  example.com --name www --type CNAME
namecheap dns export example.com -o zone.json
namecheap users balances
namecheap api namecheap.users.getPricing ProductType=DOMAIN ProductName=COM ActionName=REGISTER
namecheap --sandbox domains create <domain> ... --yes   # test purchases: sandbox only
namecheap commands        # list all 59 methods
```

## Safety model (IMPORTANT for agents)

- **Billable** ops (register/renew/reactivate/transfer/SSL purchase/add
  funds/privacy renew) and **destructive** ops (setHosts, setContacts,
  lock changes, deletes) prompt for confirmation; non-TTY contexts must
  pass `--yes` explicitly. Treat production `--yes` on billable commands
  like a production write: only with the operator's explicit, same-conversation
  direction.
- `dns add`/`rm`/`import` are read-modify-write with a diff preview —
  always prefer them over raw `dns set-hosts`, which **replaces the whole
  zone** in one call.
- `dns rm` refuses to empty a zone entirely.
- Reads are always safe. Sandbox (`--sandbox`) uses play money.

## Library use

```python
from namecheap_cli import NamecheapClient
client = NamecheapClient()                      # or sandbox=True
result = client.call("namecheap.domains.getList", {"PageSize": 100})
```

## Gotchas learned in verification (2026-07-17)

- `ApiUser` must be the **account username**, not the account email —
  email yields `1011102 API Key is invalid`.
- IP-whitelist and auth failures both surface as numbered `ApiError`s; the
  CLI exits 1 with the code+message.
- Glue-record (`ns create`) IPs are validated server-side; RFC-reserved
  ranges (10.x, 203.0.113.x) are rejected with `3024278`.
- Rate limits: 50/min, 700/hour, 8000/day per key.

## Consumers

- the operator's Namecheap account (`your-username`) — all Pvragon domains.
- Sandbox account for write testing (`pvragon-cli-test-260717.com` lives
  there from the verification run).
