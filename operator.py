"""
operator.py — Operator Agent: first autonomous SovereignClaw agent.

Telegram operator console. Handles system status, KIOS queries, and
CortexShell authorization confirmations.

Commands
--------
Read-only (no authorization required):
  /status           — CortexShell health + KIOS item count
  /stats            — KIOS tier distribution
  /recent [n]       — last n KIOS evaluations (default 5)
  /pending          — list CortexShell pending auth requests
  /help             — command list

Authorization management:
  /approve <id>     — approve a pending CortexShell action
  /deny <id>        — deny a pending CortexShell action

Governed actions (Operator requests CortexShell authorization first):
  /broadcast <msg>  — send a message to all registered channels

Usage
-----
  export OPERATOR_TELEGRAM_BOT_TOKEN=...
  export CORTEXSHELL_URL=http://localhost:8100
  export KIOS_DB_PATH=/home/matt/alte/kios/kios.db
  python operator.py
"""

import logging
import sqlite3
import time

import requests

from config import CORTEXSHELL_URL, KIOS_DB_PATH, TELEGRAM_BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

TG_API = "https://api.telegram.org/bot{token}/{method}"

HELP_TEXT = (
    "<b>Operator — Command Reference</b>\n\n"
    "<b>Status</b>\n"
    "  /status          — system health\n"
    "  /stats           — KIOS tier distribution\n"
    "  /recent [n]      — last n evaluations (default 5)\n\n"
    "<b>CortexShell</b>\n"
    "  /pending         — list pending auth requests\n"
    "  /approve &lt;id&gt;    — approve a pending action\n"
    "  /deny &lt;id&gt;       — deny a pending action\n\n"
    "<b>Governed actions</b>\n"
    "  /broadcast &lt;msg&gt; — send message to all channels\n"
    "                     (requires CortexShell authorization)\n"
)


# ── Telegram helpers ──────────────────────────────────────────────────────────

def tg(method: str, **kwargs) -> dict:
    url = TG_API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    resp = requests.post(url, json=kwargs, timeout=15)
    resp.raise_for_status()
    return resp.json()


def send(chat_id: int, text: str) -> None:
    tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
       disable_web_page_preview=True)


# ── CortexShell helpers ───────────────────────────────────────────────────────

def cs_get(path: str) -> dict:
    resp = requests.get(f"{CORTEXSHELL_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def cs_post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{CORTEXSHELL_URL}{path}", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── KIOS DB helpers (read-only) ───────────────────────────────────────────────

def kios_stats() -> str:
    if not KIOS_DB_PATH.exists():
        return "KIOS DB not found at expected path."
    with sqlite3.connect(KIOS_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0]
        rows = conn.execute(
            "SELECT tier, COUNT(*) as n FROM content_items GROUP BY tier ORDER BY n DESC"
        ).fetchall()
        cost = conn.execute(
            "SELECT SUM(eval_cost_est) FROM content_items"
        ).fetchone()[0] or 0.0

    lines = [f"<b>KIOS Stats</b>  ({total} items evaluated)\n"]
    for r in rows:
        tier = r["tier"] or "unknown"
        lines.append(f"  {tier}: {r['n']}")
    lines.append(f"\nTotal cost: ${cost:.4f}")
    return "\n".join(lines)


def kios_recent(limit: int = 5) -> str:
    limit = min(max(limit, 1), 20)
    if not KIOS_DB_PATH.exists():
        return "KIOS DB not found at expected path."
    with sqlite3.connect(KIOS_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, channel, tier, summary, created_at "
            "FROM content_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    if not rows:
        return "No evaluations in DB yet."

    TIER_EMOJI = {
        "deep_watch": "🟢", "skim": "🟡", "summary_only": "🟠",
        "skip": "⚫", "DISCARD": "🔴",
    }
    lines = [f"<b>Recent {limit} evaluations</b>\n"]
    for r in rows:
        emoji = TIER_EMOJI.get(r["tier"], "⚪")
        title = r["title"] or "Unknown"
        channel = r["channel"] or "Unknown"
        summary = (r["summary"] or "—")[:120]
        date = (r["created_at"] or "")[:10]
        lines.append(
            f"{emoji} <b>{title}</b>\n"
            f"   {channel}  |  {date}\n"
            f"   {summary}"
        )
    return "\n\n".join(lines)


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_status(chat_id: int) -> None:
    lines = ["<b>Operator — System Status</b>\n"]

    # CortexShell
    try:
        data = cs_get("/health")
        lines.append(f"✅ CortexShell  <code>{data.get('time', '')[:19]}</code>")
    except Exception as exc:
        lines.append(f"❌ CortexShell  {exc}")

    # KIOS DB
    try:
        with sqlite3.connect(KIOS_DB_PATH) as conn:
            n = conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0]
        lines.append(f"✅ KIOS DB  {n} items")
    except Exception as exc:
        lines.append(f"❌ KIOS DB  {exc}")

    send(chat_id, "\n".join(lines))


def cmd_stats(chat_id: int) -> None:
    send(chat_id, kios_stats())


def cmd_recent(chat_id: int, args: str) -> None:
    try:
        limit = int(args.strip()) if args.strip() else 5
    except ValueError:
        limit = 5
    send(chat_id, kios_recent(limit))


def cmd_pending(chat_id: int) -> None:
    try:
        items = cs_get("/pending")
    except Exception as exc:
        send(chat_id, f"❌ CortexShell error: {exc}")
        return

    if not items:
        send(chat_id, "✅ No pending authorization requests.")
        return

    lines = [f"<b>Pending auth requests ({len(items)})</b>\n"]
    for item in items:
        lines.append(
            f"<code>{item['id']}</code>\n"
            f"  Agent: {item['agent']}  |  Action: {item['action']}\n"
            f"  {item.get('description', '')}\n"
            f"  Use /approve {item['id']} or /deny {item['id']}"
        )
    send(chat_id, "\n\n".join(lines))


def cmd_approve(chat_id: int, action_id: str) -> None:
    if not action_id:
        send(chat_id, "Usage: /approve &lt;action_id&gt;")
        return
    try:
        cs_post(f"/confirm/{action_id}", {"decision": "approved", "decided_by": "operator_telegram"})
        send(chat_id, f"✅ Approved: <code>{action_id}</code>")
        log.info("Approved action %s", action_id)
    except Exception as exc:
        send(chat_id, f"❌ Approve failed: {exc}")


def cmd_deny(chat_id: int, action_id: str) -> None:
    if not action_id:
        send(chat_id, "Usage: /deny &lt;action_id&gt;")
        return
    try:
        cs_post(f"/confirm/{action_id}", {"decision": "denied", "decided_by": "operator_telegram"})
        send(chat_id, f"❌ Denied: <code>{action_id}</code>")
        log.info("Denied action %s", action_id)
    except Exception as exc:
        send(chat_id, f"❌ Deny failed: {exc}")


def cmd_broadcast(chat_id: int, message: str) -> None:
    """
    Governed action: request CortexShell authorization before sending.
    Operator creates an auth request, then polls until approved/denied/expired.
    """
    if not message.strip():
        send(chat_id, "Usage: /broadcast &lt;message&gt;")
        return

    # Request authorization from CortexShell
    try:
        auth = cs_post("/authorize", {
            "agent": "operator",
            "action": "broadcast",
            "payload": {"message": message, "target": "all_channels"},
            "description": f"Broadcast to all channels: \"{message[:80]}\"",
        })
    except Exception as exc:
        send(chat_id, f"❌ CortexShell unreachable: {exc}")
        return

    action_id = auth["action_id"]
    send(
        chat_id,
        f"⏳ Authorization requested from CortexShell.\n"
        f"Action ID: <code>{action_id}</code>\n\n"
        f"Approve with: /approve {action_id}\n"
        f"Deny with:    /deny {action_id}",
    )
    log.info("Broadcast authorization requested: %s", action_id)

    # Poll CortexShell for decision (up to 5 minutes, 5s interval)
    for _ in range(60):
        time.sleep(5)
        try:
            status = cs_get(f"/pending/{action_id}")
        except Exception:
            continue

        decision = status.get("status")
        if decision == "approved":
            # Execute the broadcast
            send(chat_id, f"📢 <b>Broadcast</b>\n{message}")
            log.info("Broadcast executed: %s", action_id)
            return
        elif decision in ("denied", "expired"):
            send(chat_id, f"🚫 Broadcast {decision}: <code>{action_id}</code>")
            log.info("Broadcast %s: %s", decision, action_id)
            return
        # Still pending — keep polling

    send(chat_id, f"⏰ Broadcast timed out waiting for authorization: <code>{action_id}</code>")


# ── Dispatch ──────────────────────────────────────────────────────────────────

def dispatch(chat_id: int, text: str) -> None:
    text = text.strip()
    if not text.startswith("/"):
        send(chat_id, "Send /help to see available commands.")
        return

    parts = text.split(None, 1)
    cmd = parts[0].lower().split("@")[0]  # strip @botname suffix
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/help":
        send(chat_id, HELP_TEXT)
    elif cmd == "/status":
        cmd_status(chat_id)
    elif cmd == "/stats":
        cmd_stats(chat_id)
    elif cmd == "/recent":
        cmd_recent(chat_id, args)
    elif cmd == "/pending":
        cmd_pending(chat_id)
    elif cmd == "/approve":
        cmd_approve(chat_id, args.strip())
    elif cmd == "/deny":
        cmd_deny(chat_id, args.strip())
    elif cmd == "/broadcast":
        cmd_broadcast(chat_id, args)
    else:
        send(chat_id, f"Unknown command: {cmd}\nSend /help for the command list.")


# ── Poll loop ─────────────────────────────────────────────────────────────────

def poll() -> None:
    offset = None
    log.info("Operator agent started. Polling for messages...")

    while True:
        try:
            params: dict = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(
                TG_API.format(token=TELEGRAM_BOT_TOKEN, method="getUpdates"),
                params=params,
                timeout=40,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")
                if chat_id and text:
                    dispatch(chat_id, text)

        except KeyboardInterrupt:
            log.info("Operator stopped.")
            break
        except Exception as exc:
            log.error("Poll error: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    poll()
