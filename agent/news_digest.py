#!/usr/bin/env python3
"""
AI/Tech News Digest Agent
--------------------------
Called by the backend scheduler on Railway. Crawls preferred outlets
(RSS-first, HTML fallback), then asks a cheap LLM (no web_search tools)
to pick and rewrite 2–5 stories into digests/data.json.

If Claude fails twice, falls back to OpenAI gpt-5-nano for up to two
more attempts. The backend handles git add/commit/push — this script
only touches the JSON file.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

# Allow `python3 agent/news_digest.py` from repo root (Railway / local).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_sources import crawl_preferred_sources, filter_against_recent

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "data.json"
SOURCES_PATH = Path(__file__).parent / "sources.json"
CLAUDE_MODEL = "claude-haiku-4-5"
# Cheap refine model — no search tools; cost stays near one short completion
OPENAI_MODEL = os.getenv("OPENAI_DIGEST_MODEL", "gpt-5-nano")
MAX_ENTRIES = 300  # cap file size; oldest entries drop off the end
MIN_BULLETS = 2
MAX_CLAUDE_ATTEMPTS = 2
MAX_OPENAI_ATTEMPTS = 2
# How many prior digests to treat as "already covered" (dedupe window)
RECENT_LOOKBACK = 2
# Reject a digest if this many bullets look like repeats of recent days
MAX_DUPLICATE_BULLETS = 1


def load_sources() -> dict:
    if not SOURCES_PATH.exists():
        return {"preferred": [], "avoid": []}
    try:
        return json.loads(SOURCES_PATH.read_text())
    except json.JSONDecodeError:
        print("[digest] WARNING — corrupt sources.json, ignoring", file=sys.stderr)
        return {"preferred": [], "avoid": []}


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def significant_tokens(text: str) -> set[str]:
    stop = {
        "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "as",
        "at", "by", "from", "is", "are", "be", "its", "it", "this", "that", "new",
        "ai", "tech", "says", "after", "over", "into", "amid",
    }
    return {t for t in normalize_text(text).split() if len(t) > 2 and t not in stop}


def titles_similar(a: str, b: str, threshold: float = 0.55) -> bool:
    """True if two titles look like the same story (token overlap / containment)."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = significant_tokens(a), significant_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return overlap >= threshold


def collect_recent_coverage(entries: list, lookback: int = RECENT_LOOKBACK) -> list[dict]:
    """Headlines + bullet titles from the last N digests (for prompt + validation)."""
    covered: list[dict] = []
    for entry in entries[:lookback]:
        if entry.get("headline"):
            covered.append({"type": "headline", "text": entry["headline"]})
        for bullet in entry.get("bullets") or []:
            title = bullet.get("title") or ""
            if title:
                covered.append(
                    {
                        "type": "bullet",
                        "text": title,
                        "source": bullet.get("source") or "",
                    }
                )
    return covered


def build_prompt(candidates: list[dict], recent_coverage: list[dict], avoid: list) -> str:
    avoid_lines = "\n".join(f"- {name}" for name in avoid) or "- (none)"

    if recent_coverage:
        covered_lines = "\n".join(f"- {item['text']}" for item in recent_coverage[:40])
        covered_block = f"""
ALREADY COVERED (last {RECENT_LOOKBACK} digest(s) — DO NOT repeat these stories or near-duplicates):
{covered_lines}

Only include a story if it is genuinely NEW information (a material update, not a rewrite).
"""
    else:
        covered_block = ""

    candidate_lines = []
    for i, item in enumerate(candidates, start=1):
        published = item.get("published_at") or "unknown date"
        snippet = (item.get("summary") or "").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        line = (
            f"{i}. [{item.get('source')}] {item.get('title')}\n"
            f"   date: {published}\n"
            f"   url: {item.get('url')}"
        )
        if snippet:
            line += f"\n   snippet: {snippet}"
        candidate_lines.append(line)

    candidates_block = "\n".join(candidate_lines)

    return f"""You are editing a daily AI/tech news digest. Candidates below were already
crawled from preferred outlets — do NOT invent stories and do NOT claim you
searched the web. Pick the 2–5 most notable items from this list only.

Prefer concrete announcements, product launches, funding, regulation, research
breakthroughs, and major company moves. Cite the source name exactly as shown
in each candidate.

AVOID citing as primary source (skip these if they appear):
{avoid_lines}
{covered_block}
CANDIDATES:
{candidates_block}

Respond with ONLY a raw JSON object (no markdown fences, no commentary)
matching exactly this schema:

{{
  "headline": "one-line summary of the most important story",
  "bullets": [
    {{"title": "story title", "summary": "1-2 sentence summary", "source": "source name"}}
  ]
}}

Include 2–5 bullets. Use only stories from CANDIDATES. Your FINAL message must
be ONLY the raw JSON object — no preamble, no markdown fences, no commentary."""


def _extract_json_object(raw: str) -> str:
    """Pull a JSON object out of model text that may include prose or fences."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty model response")

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    if raw.startswith("{") and raw.endswith("}"):
        return raw

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1].strip()

    raise ValueError("no JSON object found in model response")


def _strip_cite_markup(text: str) -> str:
    text = re.sub(r"</?cite[^>]*>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _clean_digest(parsed: dict) -> dict:
    """Normalize fields after parse (strip citation markup, whitespace)."""
    headline = _strip_cite_markup(parsed.get("headline") or "")
    bullets = []
    for bullet in parsed.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        bullets.append(
            {
                "title": _strip_cite_markup(bullet.get("title") or ""),
                "summary": _strip_cite_markup(bullet.get("summary") or ""),
                "source": _strip_cite_markup(bullet.get("source") or ""),
            }
        )
    return {"headline": headline, "bullets": bullets}


def _parse_json_response(raw: str) -> dict:
    try:
        extracted = _extract_json_object(raw)
        return _clean_digest(json.loads(extracted))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from model: {exc}") from exc


def call_claude(prompt: str) -> tuple[dict, dict | None]:
    """Refine crawled candidates — no web_search tools."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = None
    if response.usage:
        usage = {
            "model": response.model,
            "inputTokens": response.usage.input_tokens,
            "cachedInputTokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            "outputTokens": response.usage.output_tokens,
        }

    text_blocks = [b.text for b in response.content if b.type == "text" and b.text]
    candidates = [t for t in reversed(text_blocks) if "{" in t] or text_blocks
    raw = candidates[0].strip() if candidates else ""
    return _parse_json_response(raw), usage


def call_openai(prompt: str) -> tuple[dict, dict | None]:
    """Cheap OpenAI fallback — plain completion, no web_search."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=OPENAI_MODEL,
        max_output_tokens=1200,
        input=prompt,
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
        chunks: list[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", None) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(text)
        raw = chunks[-1].strip() if chunks else ""

    return _parse_json_response(raw), usage


def validate_digest(parsed: dict, recent_coverage: list[dict]) -> None:
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
        "insufficient",
        "unable to find",
        "no verified",
    )
    if any(p in headline.lower() for p in empty_phrases) and len(bullets) < 3:
        raise ValueError(f"digest looks empty/placeholder: {headline!r}")

    recent_texts = [item["text"] for item in recent_coverage]
    duplicate_titles: list[str] = []
    for bullet in bullets:
        title = (bullet.get("title") or "").strip()
        if not title:
            continue
        if any(titles_similar(title, prev) for prev in recent_texts):
            duplicate_titles.append(title)

    if len(duplicate_titles) > MAX_DUPLICATE_BULLETS:
        raise ValueError(
            "digest rehashes recent coverage: " + "; ".join(duplicate_titles[:3])
        )

    if any(titles_similar(headline, prev) for prev in recent_texts):
        # Headline alone matching yesterday is a strong smell — reject unless bullets are fresh
        if len(duplicate_titles) >= 1:
            raise ValueError(f"headline overlaps recent coverage: {headline!r}")


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


def generate_digest(now: datetime, prompt: str, recent_coverage: list[dict]) -> tuple[dict, dict | None]:
    """Try Claude twice, then OpenAI twice. Raises on total failure."""
    last_error: Exception | None = None

    for attempt in range(1, MAX_CLAUDE_ATTEMPTS + 1):
        try:
            parsed, usage = call_claude(prompt)
            validate_digest(parsed, recent_coverage)
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
            parsed, usage = call_openai(prompt)
            validate_digest(parsed, recent_coverage)
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
    working = list(entries)
    if working:
        try:
            latest_dt = datetime.fromisoformat(working[0].get("timestamp", "").replace("Z", "+00:00"))
            if latest_dt.date() == now.date() and not is_valid_entry(working[0]):
                print(f"[{now.isoformat()}] Replacing thin/empty digest from earlier today")
                working = working[1:]
        except ValueError:
            pass

    recent_coverage = collect_recent_coverage(working, RECENT_LOOKBACK)
    sources = load_sources()
    print(
        f"[{now.isoformat()}] Dedupe window: {len(recent_coverage)} prior items; "
        f"preferred sources: {len(sources.get('preferred') or [])}"
    )

    candidates, stats = crawl_preferred_sources(sources)
    recent_texts = [item["text"] for item in recent_coverage]
    candidates = filter_against_recent(candidates, recent_texts)
    stats["candidates"] = len(candidates)

    print(
        f"[{now.isoformat()}] crawled={stats['crawled']} candidates={stats['candidates']} "
        f"sources_ok={stats['sources_ok']} sources_failed={stats['sources_failed']}"
    )

    if len(candidates) < MIN_BULLETS:
        print(
            f"[{now.isoformat()}] Failed: not enough crawled candidates "
            f"({len(candidates)}; need >= {MIN_BULLETS})"
        )
        sys.exit(1)

    prompt = build_prompt(candidates, recent_coverage, sources.get("avoid") or [])

    try:
        parsed, usage = generate_digest(now, prompt, recent_coverage)
    except Exception as e:
        print(f"[{now.isoformat()}] Failed to get/parse digest: {e}")
        sys.exit(1)

    entry = {
        "timestamp": now.isoformat(),
        "headline": parsed.get("headline", ""),
        "bullets": parsed.get("bullets", []),
    }

    working.insert(0, entry)
    working = working[:MAX_ENTRIES]

    save(working)
    print(f"[{now.isoformat()}] Saved entry. Total entries: {len(working)}")

    # Parsed back out of stdout by runDigest.js and attached to the telemetry.succeeded()
    # call — see backend/src/jobs/runDigest.js.
    if usage:
        print(f"TELEMETRY_USAGE={json.dumps(usage)}")


if __name__ == "__main__":
    main()
