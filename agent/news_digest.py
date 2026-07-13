#!/usr/bin/env python3
"""
AI/Tech News Digest Agent
--------------------------
Called by the GitHub Actions workflow on a schedule. Asks Claude to find and
summarize recent AI/tech news via web search, and appends the result as a
structured entry to digests/data.json (newest entry first).

The GitHub Actions workflow handles git add/commit/push — this script only
touches the JSON file.
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime, timezone
import anthropic

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
MODEL = "claude-sonnet-4-6"
MAX_ENTRIES = 300  # cap file size; oldest entries drop off the end

PROMPT = """Search the web and find the most notable AI / tech news from the
last few hours. If nothing genuinely new has happened since typical news
cycles, it's fine to return fewer bullets rather than padding with old or
speculative stories.

Respond with ONLY a raw JSON object (no markdown fences, no commentary)
matching exactly this schema:

{
  "headline": "one-line summary of the most important story",
  "bullets": [
    {"title": "story title", "summary": "1-2 sentence summary", "source": "source name"}
  ]
}

Include 2-5 bullets. Do not include anything outside the JSON object."""


def call_claude() -> dict:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": PROMPT}],
    )

    # The final text block should be the JSON; strip stray code fences just in case.
    text_blocks = [b.text for b in response.content if b.type == "text"]
    raw = text_blocks[-1].strip() if text_blocks else "{}"
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

    return json.loads(raw)


def load_existing() -> list:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text())
        except json.JSONDecodeError:
            return []
    return []


def save(entries: list):
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(entries, indent=2))


def main():
    now = datetime.now(timezone.utc)
    print(f"[{now.isoformat()}] Running digest agent...")

    try:
        parsed = call_claude()
    except Exception as e:
        print(f"[{now.isoformat()}] Failed to get/parse digest: {e}")
        return  # skip this run rather than writing bad data

    entry = {
        "timestamp": now.isoformat(),
        "headline": parsed.get("headline", ""),
        "bullets": parsed.get("bullets", []),
    }

    entries = load_existing()
    entries.insert(0, entry)  # newest first
    entries = entries[:MAX_ENTRIES]

    save(entries)
    print(f"[{now.isoformat()}] Saved entry. Total entries: {len(entries)}")


if __name__ == "__main__":
    main()
