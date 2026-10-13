#!/usr/bin/env python3
"""
SIGNAL Work-Disruption Digest
-----------------------------
Daily brief on AI and the job market (layoffs, role changes, automation
backlash, slowdowns, workplace regulation). Crawl-first, cheap LLM refine
with no web_search. Writes digests/work.json only (API distribution).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 agent/work_digest.py` from repo root (Railway / local).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawl_sources import crawl_preferred_sources, filter_against_recent
import news_digest as nd

REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "digests" / "work.json"
SOURCES_PATH = Path(__file__).parent / "sources.work.json"
MAX_ENTRIES = 300
MIN_BULLETS = nd.MIN_BULLETS
RECENT_LOOKBACK = nd.RECENT_LOOKBACK

# Soft topic gate before the LLM — titles/snippets must look job/labor related.
WORK_KEYWORDS = (
    "job",
    "jobs",
    "layoff",
    "laid off",
    "hiring",
    "hire",
    "workforce",
    "worker",
    "workers",
    "employee",
    "employees",
    "employment",
    "unemployment",
    "labor",
    "labour",
    "union",
    "strike",
    "automation",
    "automate",
    "replace",
    "replacing",
    "displacement",
    "reskill",
    "upskill",
    "retrain",
    "workplace",
    "white-collar",
    "blue-collar",
    "gig",
    "payroll",
    "headcount",
    "redundan",
    "firing",
    "fired",
    "cut jobs",
    "job cut",
    "job cuts",
    "hiring freeze",
    "slow down",
    "slowdown",
    "pause ai",
    "ban ai",
    "regulate",
    "regulation",
    "regulator",
    "robot",
    "robots",
    "human in the loop",
    "deskilling",
    "productivity",
    "wage",
    "wages",
    "salary",
    "salaries",
    "career",
    "careers",
    "profession",
    "call center",
    "customer service",
    "office work",
)


def load_sources() -> dict:
    if not SOURCES_PATH.exists():
        return {"preferred": [], "avoid": []}
    try:
        return json.loads(SOURCES_PATH.read_text())
    except json.JSONDecodeError:
        print("[work] WARNING — corrupt sources.work.json, ignoring", file=sys.stderr)
        return {"preferred": [], "avoid": []}


def load_existing() -> list:
    if not DATA_PATH.exists():
        return []
    try:
        return json.loads(DATA_PATH.read_text())
    except json.JSONDecodeError:
        print("[work] WARNING — corrupt work.json, starting fresh", file=sys.stderr)
        return []


def save(entries: list) -> None:
    DATA_PATH.parent.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(entries, indent=2) + "\n")


def looks_like_work_story(item: dict) -> bool:
    blob = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
    return any(keyword in blob for keyword in WORK_KEYWORDS)


def filter_work_candidates(candidates: list[dict]) -> list[dict]:
    return [c for c in candidates if looks_like_work_story(c)]


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

    return f"""You write SIGNAL Work — a daily brief on how AI is changing jobs and work
life, for busy NON-TECHNICAL readers. Candidates below were already crawled —
do NOT invent stories and do NOT claim you searched the web. Pick 2–5 items
from this list only.

TOPIC (strict)
Only stories about the job market and work disruption:
- Layoffs, hiring freezes, headcount cuts tied to AI/automation
- Roles redesigned, tasks automated, “AI replacing workers”
- Unions, protests, worker pushback, calls to slow or pause AI at work
- Regulation of workplace AI, bans, safety rules that protect jobs
- Reskilling / upskilling waves, wage pressure, career uncertainty
- Public criticism of robots/AI taking human work

Skip: product launches, model release notes, chip deals, funding rounds —
unless there is a clear jobs / labor / workplace angle.

AUDIENCE & VOICE
- No engineering jargon. Plain language a non-technical person can share.
- Sharp newsletter tone. Short, concrete, human. Easy to say out loud.
- First sentence = what happened. Second = why it matters for people’s work
  or livelihoods. Invite a reaction without asking a question or using hype.

HOW TO WRITE EACH BULLET
- title: plain-language hook (rewrite technical outlet headlines)
- summary: 1–2 simple sentences with human stakes
- source: cite the outlet name exactly as shown in the candidate

Cite only sources from CANDIDATES. Prefer primary outlets over aggregators.

AVOID citing as primary source (skip these if they appear):
{avoid_lines}
{covered_block}
CANDIDATES:
{candidates_block}

Respond with ONLY a raw JSON object (no markdown fences, no commentary)
matching exactly this schema:

{{
  "headline": "one plain-language line that captures the day’s jobs/AI idea",
  "bullets": [
    {{"title": "plain-language title", "summary": "1-2 simple sentences with stakes", "source": "source name"}}
  ]
}}

Include 2–5 bullets. Use only stories from CANDIDATES. Your FINAL message must
be ONLY the raw JSON object — no preamble, no markdown fences, no commentary."""


def main() -> None:
    now = datetime.now(timezone.utc)
    force = os.getenv("FORCE_DIGEST", "").lower() in ("1", "true", "yes")

    print(f"[{now.isoformat()}] Running work-disruption digest agent...")

    entries = load_existing()
    if not force and nd.already_ran_today(entries, now):
        print(f"[{now.isoformat()}] Work digest already exists for today (UTC) — skipping")
        return

    working = list(entries)
    if working:
        try:
            latest_dt = datetime.fromisoformat(
                working[0].get("timestamp", "").replace("Z", "+00:00")
            )
            if latest_dt.date() == now.date() and (force or not nd.is_valid_entry(working[0])):
                reason = "force regenerate" if force else "thin/empty digest from earlier today"
                print(f"[{now.isoformat()}] Replacing today's work digest ({reason})")
                working = working[1:]
        except ValueError:
            pass

    recent_coverage = nd.collect_recent_coverage(working, RECENT_LOOKBACK)
    sources = load_sources()
    print(
        f"[{now.isoformat()}] Dedupe window: {len(recent_coverage)} prior items; "
        f"preferred sources: {len(sources.get('preferred') or [])}"
    )

    # Labor / policy outlets publish less often than tech blogs — use a 14-day window.
    # Filter for work topics BEFORE diversify/cap so job stories aren't crowded out.
    candidates, stats = crawl_preferred_sources(
        sources,
        recency_hours=24 * 14,
        item_filter=looks_like_work_story,
    )
    recent_texts = [item["text"] for item in recent_coverage]
    before_dedupe = len(candidates)
    candidates = filter_against_recent(candidates, recent_texts)
    stats["candidates"] = len(candidates)

    print(
        f"[{now.isoformat()}] crawled={stats['crawled']} work_candidates={before_dedupe}->{stats['candidates']} "
        f"sources_ok={stats['sources_ok']} sources_failed={stats['sources_failed']}"
    )

    if len(candidates) < MIN_BULLETS:
        print(
            f"[{now.isoformat()}] Failed: not enough work-related candidates "
            f"({len(candidates)}; need >= {MIN_BULLETS})"
        )
        sys.exit(1)

    prompt = build_prompt(candidates, recent_coverage, sources.get("avoid") or [])

    try:
        parsed, usage = nd.generate_digest(now, prompt, recent_coverage)
    except Exception as e:
        print(f"[{now.isoformat()}] Failed to get/parse work digest: {e}")
        sys.exit(1)

    entry = {
        "timestamp": now.isoformat(),
        "headline": parsed.get("headline", ""),
        "bullets": parsed.get("bullets", []),
    }

    working.insert(0, entry)
    working = working[:MAX_ENTRIES]
    save(working)
    print(f"[{now.isoformat()}] Saved work entry. Total entries: {len(working)}")

    if usage:
        print(f"TELEMETRY_USAGE={json.dumps(usage)}")


if __name__ == "__main__":
    main()
