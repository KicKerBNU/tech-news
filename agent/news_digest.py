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
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from opentelemetry.trace import Status, StatusCode

from telemetry import get_tracer, init_telemetry, shutdown_telemetry

init_telemetry()
tracer = get_tracer()

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
MODEL = "claude-sonnet-4-6"
MAX_ENTRIES = 300  # cap file size; oldest entries drop off the end

PROMPT = """Search the web (at most 1-2 searches) and find the most notable
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


def call_claude() -> dict:
    with tracer.start_as_current_span("digest.call_claude") as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.request.model", MODEL)

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        start = time.monotonic()

        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1200,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
                messages=[{"role": "user", "content": PROMPT}],
            )
        except Exception as exc:
            span.set_attribute("exception.slug", "err-digest-claude-request")
            span.set_attribute("error", True)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise

        span.set_attribute("claude.duration_ms", (time.monotonic() - start) * 1000)
        span.set_attribute("gen_ai.response.model", response.model)
        if response.usage:
            span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)

        text_blocks = [b.text for b in response.content if b.type == "text"]
        raw = text_blocks[-1].strip() if text_blocks else "{}"
        raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            span.set_attribute("exception.slug", "err-digest-claude-json-parse")
            span.set_attribute("error", True)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "invalid JSON from Claude"))
            raise

        bullets = parsed.get("bullets", [])
        span.set_attribute("digest.bullet_count", len(bullets))
        span.set_attribute("digest.headline", (parsed.get("headline") or "")[:200])
        return parsed


def load_existing() -> list:
    with tracer.start_as_current_span("digest.load_entries") as span:
        if not DATA_PATH.exists():
            span.set_attribute("digest.file_exists", False)
            return []

        span.set_attribute("digest.file_exists", True)
        try:
            entries = json.loads(DATA_PATH.read_text())
        except json.JSONDecodeError as exc:
            span.set_attribute("exception.slug", "err-digest-load-json")
            span.set_attribute("error", True)
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, "corrupt data.json"))
            return []

        span.set_attribute("digest.entry_count", len(entries))
        return entries


def save(entries: list):
    with tracer.start_as_current_span("digest.save_entries") as span:
        span.set_attribute("digest.entry_count", len(entries))
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

    with tracer.start_as_current_span("digest.run") as span:
        span.set_attribute("digest.model", MODEL)
        span.set_attribute("digest.max_entries", MAX_ENTRIES)
        print(f"[{now.isoformat()}] Running digest agent...")

        entries = load_existing()
        if not force and already_ran_today(entries, now):
            print(f"[{now.isoformat()}] Digest already exists for today (UTC) — skipping")
            span.set_attribute("digest.skipped", True)
            return

        try:
            parsed = call_claude()
        except Exception as e:
            span.set_attribute("exception.slug", "err-digest-run-failed")
            span.set_attribute("error", True)
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
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
        span.set_attribute("digest.saved_entry_count", len(entries))
        span.set_attribute("digest.success", True)
        print(f"[{now.isoformat()}] Saved entry. Total entries: {len(entries)}")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown_telemetry()
