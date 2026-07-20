#!/usr/bin/env python3
"""
Post the latest digest to a Telegram group via Bot API.
Called by GitHub Actions after a successful digest run.

Setup:
  1. Message @BotFather → /newbot → copy token
  2. Add the bot to your group (make it admin if the group is restricted)
  3. Get chat id: post in the group, then open
     https://api.telegram.org/bot<TOKEN>/getUpdates
     and copy message.chat.id (negative number for groups)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from telegram_template import render_digest_telegram

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
TELEGRAM_API = "https://api.telegram.org"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"[telegram] ERROR — {name} is not set")
        sys.exit(1)
    return value


def load_latest_entry() -> dict | None:
    if not DATA_PATH.exists():
        return None
    entries = json.loads(DATA_PATH.read_text())
    return entries[0] if entries else None


def send_message(token: str, chat_id: str, text: str, *, thread_id: str | None = None) -> dict:
    payload: dict = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if thread_id:
        payload["message_thread_id"] = int(thread_id)

    data = urllib.parse.urlencode(payload).encode()
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    token = _require_env("TELEGRAM_BOT_TOKEN")
    chat_id = _require_env("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID")
    site_url = os.getenv("SITE_URL", "https://signal-news-agent.netlify.app")

    entry = load_latest_entry()
    if not entry:
        print("[telegram] No digest entry found — nothing to post")
        return

    text = render_digest_telegram(entry, site_url=site_url)
    result = send_message(token, chat_id, text, thread_id=thread_id)

    if not result.get("ok"):
        print(f"[telegram] API returned error: {result}")
        raise SystemExit(1)

    print(f"[telegram] Posted digest to chat {chat_id}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[telegram] HTTP error ({exc.code}): {body}")
        raise SystemExit(1)
