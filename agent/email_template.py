"""HTML email template for the daily SIGNAL digest newsletter."""

from __future__ import annotations

import html
from datetime import datetime


def _format_stamp(timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return timestamp


def render_digest_email(
    entry: dict,
    *,
    site_url: str,
    unsubscribe_url: str,
) -> str:
    headline = html.escape(entry.get("headline", ""))
    stamp = html.escape(_format_stamp(entry.get("timestamp", "")))
    site_url = html.escape(site_url.rstrip("/"))
    unsubscribe_url = html.escape(unsubscribe_url)

    bullet_rows = []
    for bullet in entry.get("bullets", []):
        title = html.escape(bullet.get("title", ""))
        summary = html.escape(bullet.get("summary", ""))
        source = html.escape(bullet.get("source", ""))
        bullet_rows.append(
            f"""
            <tr>
              <td style="padding:0 0 16px 0;font-family:'IBM Plex Sans',Arial,sans-serif;font-size:14px;line-height:1.55;color:#e7ecf3;">
                <strong style="color:#ffb84d;">{title}</strong><br />
                <span style="color:#7e8aa0;">{summary}</span>
                <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#ffb84d;"> [{source}]</span>
              </td>
            </tr>
            """
        )

    bullets_html = "".join(bullet_rows) or "<tr><td style='color:#7e8aa0;'>No stories in this transmission.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SIGNAL — {headline}</title>
  </head>
  <body style="margin:0;padding:0;background:#0b0e14;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b0e14;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#131826;border:1px solid #232b3d;">
            <tr>
              <td style="padding:24px 28px;border-bottom:1px solid #232b3d;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:0.08em;color:#4ade80;">
                ● SIGNAL / AI &amp; TECH WIRE
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                <p style="margin:0 0 8px 0;font-family:'IBM Plex Mono',monospace;font-size:11px;color:#7e8aa0;">{stamp}</p>
                <h1 style="margin:0 0 24px 0;font-family:'IBM Plex Mono',monospace;font-size:22px;line-height:1.35;color:#e7ecf3;">{headline}</h1>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                  {bullets_html}
                </table>
                <p style="margin:28px 0 0 0;">
                  <a href="{site_url}" style="font-family:'IBM Plex Mono',monospace;font-size:12px;color:#ffb84d;text-decoration:none;">Read full feed →</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:18px 28px;border-top:1px solid #232b3d;font-family:'IBM Plex Mono',monospace;font-size:11px;line-height:1.6;color:#7e8aa0;">
                Daily digest · 08:00 UTC<br />
                <a href="{unsubscribe_url}" style="color:#7e8aa0;">Unsubscribe</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
