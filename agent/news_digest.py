#!/usr/bin/env python3
"""
AI/Tech News Digest Agent
--------------------------
Called by the backend scheduler on Railway. Asks Claude to find and
summarize recent AI/tech news via web search, and appends the result as a
structured entry to digests/data.json (newest entry first).

The backend server handles git add/commit/push — this script only
touches the JSON file.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
MODEL = "claude-haiku-4-5"
MAX_ENTRIES = 300  # cap file size; oldest entries drop off the end

PROMPT = """Search the web (at most 1 search) and find the most notable
AI / tech news from the last few hours. If nothing genuinely new has happened
since typical news cycles, it's fine to return fewer bullets rather than
padding with old or speculative stories.

Respond with ONLY a raw JSON object (no markdown fences, no commentary)
matching exactly this schema:

{
  "headline": "one-line summary of the most important story",
  "bullets": [
    {"title": "story title", "summary": "1-2 sentence summary", "source": "source name"}
  ]
}

Include 2-5 bullets. Do not include anything outside the JSON object."""


def call_claude() -> tuple[dict, dict | None]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 1}],
        messages=[{"role": "user", "content": PROMPT}],
    )

    usage = None
    if response.usage:
        # Fed to Zanshin's telemetry cost prediction (via the TELEMETRY_USAGE stdout line
        # below) — kept out of the public digest entry in data.json, since that file is
        # served as-is to the news site.
        usage = {
            "model": response.model,
            "inputTokens": response.usage.input_tokens,
            "cachedInputTokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            "outputTokens": response.usage.output_tokens,
        }

    text_blocks = [b.text for b in response.content if b.type == "text"]
    raw = text_blocks[-1].strip() if text_blocks else "{}"
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from Claude: {exc}") from exc

    return parsed, usage


def load_existing() -> list:
    if not DATA_PATH.exists():
        return []

    try:
        return json.loads(DATA_PATH.read_text())
    except json.JSONDecodeError:
        print(f"[digest] WARNING — corrupt data.json, starting fresh", file=sys.stderr)
        return []


def save(entries: list):
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(entries, indent=2))


def already_ran_today(entries: list, now: datetime) -> bool:
    """True if the newest digest entry is from today's UTC date."""
    if not entries:
        return False
    latest = entries[0].get("timestamp", "")
    try:
        dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        return dt.date() == now.date()
    except ValueError:
        return False


def main():
    now = datetime.now(timezone.utc)
    force = os.getenv("FORCE_DIGEST", "").lower() in ("1", "true", "yes")

    print(f"[{now.isoformat()}] Running digest agent...")

    entries = load_existing()
    if not force and already_ran_today(entries, now):
        print(f"[{now.isoformat()}] Digest already exists for today (UTC) — skipping")
        return

    try:
        parsed, usage = call_claude()
    except Exception as e:
        print(f"[{now.isoformat()}] Failed to get/parse digest: {e}")
        sys.exit(1)

    entry = {
        "timestamp": now.isoformat(),
        "headline": parsed.get("headline", ""),
        "bullets": parsed.get("bullets", []),
    }

    entries.insert(0, entry)
    entries = entries[:MAX_ENTRIES]

    save(entries)
    print(f"[{now.isoformat()}] Saved entry. Total entries: {len(entries)}")

    # Parsed back out of stdout by runDigest.js and attached to the telemetry.succeeded()
    # call — see backend/src/jobs/runDigest.js.
    if usage:
        print(f"TELEMETRY_USAGE={json.dumps(usage)}")


if __name__ == "__main__":
    main()
