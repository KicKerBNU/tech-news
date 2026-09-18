#!/usr/bin/env python3
"""
AI/Tech News Digest Agent
--------------------------
Called by the backend scheduler on Railway. Asks Claude to find and
summarize recent AI/tech news via web search, and appends the result as a
structured entry to digests/data.json (newest entry first).

If Claude fails twice, falls back to OpenAI gpt-5-nano (cheap) for up to
two more attempts. The backend server handles git add/commit/push — this
script only touches the JSON file.
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
CLAUDE_MODEL = "claude-haiku-4-5"
# Cheapest OpenAI model with Responses + web_search — keep digest cost << $0.10
OPENAI_MODEL = os.getenv("OPENAI_DIGEST_MODEL", "gpt-5-nano")
MAX_ENTRIES = 300  # cap file size; oldest entries drop off the end
MIN_BULLETS = 2
MAX_CLAUDE_ATTEMPTS = 2
MAX_OPENAI_ATTEMPTS = 2

PROMPT = """Search the web for the most notable AI / tech news from the last 24 hours
(not just the last couple of hours). Prefer concrete announcements, product launches,
funding, regulation, research breakthroughs, and major company moves.

You MUST find real stories. An empty digest is not acceptable — dig deeper with your
search if the first results look thin. Cover the full day cycle (US / EU / Asia), not
only overnight quiet hours.

Respond with ONLY a raw JSON object (no markdown fences, no commentary)
matching exactly this schema:

{
  "headline": "one-line summary of the most important story",
  "bullets": [
    {"title": "story title", "summary": "1-2 sentence summary", "source": "source name"}
  ]
}

Include 2-5 bullets with real sources. Do not invent stories. Do not return an empty
bullets array. Do not include anything outside the JSON object."""


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from model: {exc}") from exc


def call_claude() -> tuple[dict, dict | None]:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
        messages=[{"role": "user", "content": PROMPT}],
    )

    usage = None
    if response.usage:
        usage = {
            "model": response.model,
            "inputTokens": response.usage.input_tokens,
            "cachedInputTokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            "outputTokens": response.usage.output_tokens,
        }

    text_blocks = [b.text for b in response.content if b.type == "text"]
    raw = text_blocks[-1].strip() if text_blocks else "{}"
    return _parse_json_response(raw), usage


def call_openai() -> tuple[dict, dict | None]:
    """Cheap OpenAI fallback via Responses API + web_search."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=OPENAI_MODEL,
        tools=[{"type": "web_search"}],
        max_tool_calls=2,
        max_output_tokens=1200,
        input=PROMPT,
    )

    usage = None
    if getattr(response, "usage", None):
        usage = {
            "model": getattr(response, "model", OPENAI_MODEL),
            "inputTokens": getattr(response.usage, "input_tokens", 0) or 0,
            "cachedInputTokens": 0,
            "outputTokens": getattr(response.usage, "output_tokens", 0) or 0,
        }

    raw = (getattr(response, "output_text", None) or "").strip()
    if not raw:
        # Fallback: walk output items for message text
        chunks: list[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", None) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(text)
        raw = chunks[-1].strip() if chunks else "{}"

    return _parse_json_response(raw), usage


def validate_digest(parsed: dict) -> None:
    headline = (parsed.get("headline") or "").strip()
    bullets = parsed.get("bullets") or []

    if not headline:
        raise ValueError("digest missing headline")

    if not isinstance(bullets, list) or len(bullets) < MIN_BULLETS:
        raise ValueError(
            f"digest too thin ({len(bullets) if isinstance(bullets, list) else 0} bullets; need >= {MIN_BULLETS})"
        )

    empty_phrases = (
        "no major",
        "nothing new",
        "no significant",
        "no notable",
        "quiet day",
        "no announcements",
    )
    if any(p in headline.lower() for p in empty_phrases) and len(bullets) < 3:
        raise ValueError(f"digest looks empty/placeholder: {headline!r}")


def load_existing() -> list:
    if not DATA_PATH.exists():
        return []

    try:
        return json.loads(DATA_PATH.read_text())
    except json.JSONDecodeError:
        print("[digest] WARNING — corrupt data.json, starting fresh", file=sys.stderr)
        return []


def save(entries: list):
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(entries, indent=2))


def is_valid_entry(entry: dict) -> bool:
    bullets = entry.get("bullets") or []
    return isinstance(bullets, list) and len(bullets) >= MIN_BULLETS


def already_ran_today(entries: list, now: datetime) -> bool:
    """True if today's UTC digest exists and has enough bullets (empty digests can regenerate)."""
    if not entries:
        return False
    latest = entries[0]
    stamp = latest.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if dt.date() != now.date():
            return False
        return is_valid_entry(latest)
    except ValueError:
        return False


def generate_digest(now: datetime) -> tuple[dict, dict | None]:
    """Try Claude twice, then OpenAI twice. Raises on total failure."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_CLAUDE_ATTEMPTS + 1):
        try:
            parsed, usage = call_claude()
            validate_digest(parsed)
            print(f"[{now.isoformat()}] Digest from Claude ({CLAUDE_MODEL}) attempt {attempt}")
            return parsed, usage
        except Exception as e:
            last_error = e
            print(f"[{now.isoformat()}] Claude attempt {attempt}/{MAX_CLAUDE_ATTEMPTS} failed: {e}")

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            f"Claude failed {MAX_CLAUDE_ATTEMPTS}x and OPENAI_API_KEY is not set "
            f"(last error: {last_error})"
        )

    for attempt in range(1, MAX_OPENAI_ATTEMPTS + 1):
        try:
            parsed, usage = call_openai()
            validate_digest(parsed)
            print(f"[{now.isoformat()}] Digest from OpenAI ({OPENAI_MODEL}) attempt {attempt}")
            return parsed, usage
        except Exception as e:
            last_error = e
            print(f"[{now.isoformat()}] OpenAI attempt {attempt}/{MAX_OPENAI_ATTEMPTS} failed: {e}")

    raise RuntimeError(f"All Claude + OpenAI attempts failed (last error: {last_error})")


def main():
    now = datetime.now(timezone.utc)
    force = os.getenv("FORCE_DIGEST", "").lower() in ("1", "true", "yes")

    print(f"[{now.isoformat()}] Running digest agent...")

    entries = load_existing()
    if not force and already_ran_today(entries, now):
        print(f"[{now.isoformat()}] Digest already exists for today (UTC) — skipping")
        return

    # Replace a same-day empty/thin digest if we're regenerating.
    if entries:
        try:
            latest_dt = datetime.fromisoformat(entries[0].get("timestamp", "").replace("Z", "+00:00"))
            if latest_dt.date() == now.date() and not is_valid_entry(entries[0]):
                print(f"[{now.isoformat()}] Replacing thin/empty digest from earlier today")
                entries = entries[1:]
        except ValueError:
            pass

    try:
        parsed, usage = generate_digest(now)
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
