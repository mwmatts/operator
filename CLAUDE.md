# Operator Agent
# Claude Code Project File

## What Operator Is

Operator is the first autonomous SovereignClaw agent. It is the operator-level
Telegram console — system status, KIOS queries, and CortexShell authorization
management.

Operator is NOT a content evaluation bot. That is @KIOSClaw_bot (kios_bot.py).
Operator is the human-facing ops interface for the SovereignClaw infrastructure.

---

## Scope

Operator handles:
1. **System status** — health checks for CortexShell and KIOS DB
2. **KIOS queries** — read-only: stats, recent evaluations
3. **CortexShell confirmations** — approve/deny pending authorization requests
4. **Governed actions** — actions that require CortexShell authorization before
   execution (e.g. /broadcast)

Operator does NOT:
- Evaluate content (that is KIOS's job)
- Store state of its own (reads KIOS DB read-only)
- Run without CortexShell available for governed actions

---

## Files

| File | Purpose |
|---|---|
| operator.py | Main agent — Telegram poll loop + command dispatch |
| config.py | Token, CortexShell URL, KIOS DB path |
| requirements.txt | Dependencies (requests only) |
| Dockerfile | Container build |
| docker-compose.yml | Service definition |
| .env.example | Environment variable template |

---

## Environment Variables

OPERATOR_TELEGRAM_BOT_TOKEN  — Telegram bot token (@OperatorClaw_bot)
CORTEXSHELL_URL              — CortexShell base URL (default: http://localhost:8100)
KIOS_DB_PATH                 — Path to KIOS SQLite DB (default: ~/alte/kios/kios.db)

---

## CortexShell Integration

Operator calls CortexShell for governed actions:
  POST /authorize  — request human authorization
  POST /confirm/{id} — confirm/deny a pending action (via /approve, /deny commands)
  GET /pending     — list pending auth requests
  GET /health      — liveness check

Operator polls CortexShell for up to 5 minutes after a governed action request,
then times out with a message to the user.

---

## Docker Notes

- Shares the `kios_data` Docker volume with KIOS containers (read access to kios.db)
- Uses `network_mode: host` so it can reach CortexShell on localhost:8100
- `kios_data` volume is marked `external: true` — created by KIOS docker-compose

---

## Telegram Bot

@OperatorClaw_bot — create via @BotFather, add token to .env as OPERATOR_TELEGRAM_BOT_TOKEN
