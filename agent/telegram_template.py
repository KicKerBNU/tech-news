"""Telegram message template for the daily SIGNAL digest."""

from __future__ import annotations

import html
from datetime import datetime

TELEGRAM_MAX_LENGTH = 4096


def _format_stamp(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return timestamp


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def render_digest_telegram(entry: dict, *, site_url: str) -> str:
    stamp = _esc(_format_stamp(entry.get("timestamp", "")))
    headline = _esc(entry.get("headline", ""))
    site = _esc(site_url.rstrip("/"))

    lines = [
        "📡 <b>SIGNAL / AI &amp; TECH WIRE</b>",
        f"<i>{stamp}</i>",
        "",
        f"<b>{headline}</b>",
        "",
    ]

    for bullet in entry.get("bullets", []):
        title = _esc(bullet.get("title", ""))
        summary = _esc(bullet.get("summary", ""))
        source = _esc(bullet.get("source", ""))
        lines.append(f"• <b>{title}</b> — {summary} [{source}]")

    lines.extend(["", f'<a href="{site}">Read full feed →</a>'])

    message = "\n".join(lines)
    if len(message) <= TELEGRAM_MAX_LENGTH:
        return message

    # Trim bullets from the end until it fits
    trimmed = lines[:5]  # header block through headline
    trimmed.append("")
    for bullet_line in lines[5:-2]:
        candidate = "\n".join([*trimmed, bullet_line, "", lines[-1]])
        if len(candidate) > TELEGRAM_MAX_LENGTH - 20:
            trimmed.append("…")
            break
        trimmed.append(bullet_line)

    trimmed.extend(["", lines[-1]])
    return "\n".join(trimmed)
