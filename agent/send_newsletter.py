#!/usr/bin/env python3
"""
Send the latest digest entry to all active newsletter subscribers via Resend.
Subscribers are stored as Resend Contacts (no database required).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from email_template import render_digest_email

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
BATCH_SIZE = 100
RESEND_API = "https://api.resend.com"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"[newsletter] Skipping — {name} is not set")
        sys.exit(0)
    return value


def resend_request(api_key: str, path: str, *, method: str = "GET", body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{RESEND_API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def sign_email(email: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), email.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def fetch_active_subscribers(api_key: str) -> list[str]:
    emails: list[str] = []
    cursor = None

    while True:
        query = urllib.parse.urlencode({"limit": 100, **({"after": cursor} if cursor else {})})
        payload = resend_request(api_key, f"/contacts?{query}")
        for contact in payload.get("data", []):
            if not contact.get("unsubscribed"):
                emails.append(contact["email"])

        if not payload.get("has_more"):
            break
        cursor = payload.get("next")

    return emails


def load_latest_entry() -> dict | None:
    if not DATA_PATH.exists():
        return None
    entries = json.loads(DATA_PATH.read_text())
    return entries[0] if entries else None


def send_batch(api_key: str, messages: list[dict]) -> None:
    payload = json.dumps(messages).encode()
    req = urllib.request.Request(
        f"{RESEND_API}/emails/batch",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        json.load(resp)


def main() -> None:
    resend_key = _require_env("RESEND_API_KEY")
    from_email = _require_env("RESEND_FROM_EMAIL")
    unsubscribe_secret = _require_env("UNSUBSCRIBE_SECRET")
    site_url = os.getenv("SITE_URL", "https://signal-news-agent.netlify.app")

    entry = load_latest_entry()
    if not entry:
        print("[newsletter] No digest entry found — nothing to send")
        return

    subscribers = fetch_active_subscribers(resend_key)
    if not subscribers:
        print("[newsletter] No active subscribers")
        return

    subject = f"SIGNAL — {entry.get('headline', 'Daily digest')[:120]}"
    messages = []

    for email in subscribers:
        sig = sign_email(email, unsubscribe_secret)
        query = urllib.parse.urlencode({"email": email, "sig": sig})
        unsubscribe_url = f"{site_url.rstrip('/')}/unsubscribe?{query}"
        html_body = render_digest_email(entry, site_url=site_url, unsubscribe_url=unsubscribe_url)
        messages.append(
            {
                "from": from_email,
                "to": [email],
                "subject": subject,
                "html": html_body,
            }
        )

    sent = 0
    for i in range(0, len(messages), BATCH_SIZE):
        batch = messages[i : i + BATCH_SIZE]
        send_batch(resend_key, batch)
        sent += len(batch)

    print(f"[newsletter] Sent digest to {sent} subscriber(s)")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"[newsletter] HTTP error ({exc.code}): {body}")
        raise SystemExit(1)
