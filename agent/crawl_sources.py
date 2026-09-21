"""
Crawl preferred outlets (RSS-first, HTML fallback) into a candidate story list.

Discovery lives here so the digest LLM never needs paid web_search.
"""

from __future__ import annotations

import html
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; SIGNAL-NewsDigest/1.0; "
    "+https://github.com/KicKerBNU/tech-news)"
)
REQUEST_TIMEOUT = 20.0
MAX_WORKERS = 8
RECENCY_HOURS = 36
MAX_CANDIDATES = 40
MAX_PER_SOURCE = 12
MAX_PER_SOURCE_FINAL = 4
MAX_HTML_LINKS = 20

# Soft-skip hard paywalls when crawl yields nothing (do not retry aggressively).
BRITTLE_SOURCES = {
    "Bloomberg",
    "Financial Times",
    "Wall Street Journal",
    "The Information",
    "Reuters",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (tuple, list)) and len(value) >= 6:
        try:
            # feedparser time.struct_time-like
            return datetime(*value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError, IndexError, OverflowError):
            pass
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    # Drop fragments / tracking noise for dedupe
    clean = parsed._replace(fragment="", query="").geturl()
    return clean.rstrip("/")


def _is_recent(published: datetime | None, cutoff: datetime) -> bool:
    # Keep undated items — listing pages often omit timestamps.
    if published is None:
        return True
    return published >= cutoff


def _fetch_text(client: httpx.Client, url: str) -> str:
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _candidate(
    *,
    title: str,
    url: str,
    source: str,
    summary: str = "",
    published_at: datetime | None = None,
) -> dict | None:
    title = _strip_html(title)
    url = _normalize_url(url)
    if not title or not url or not url.startswith("http"):
        return None
    if len(title) < 12:
        return None
    return {
        "title": title,
        "url": url,
        "source": source,
        "summary": _strip_html(summary)[:400],
        "published_at": published_at.isoformat() if published_at else None,
    }


def crawl_rss(client: httpx.Client, source: dict, cutoff: datetime) -> list[dict]:
    rss = (source.get("rss") or "").strip()
    name = source.get("name") or "Unknown"
    if not rss:
        return []

    raw = _fetch_text(client, rss)
    feed = feedparser.parse(raw)
    items: list[dict] = []

    for entry in feed.entries[: MAX_PER_SOURCE * 2]:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        summary = (
            getattr(entry, "summary", None)
            or getattr(entry, "description", None)
            or ""
        )
        published = None
        if getattr(entry, "published_parsed", None):
            published = _parse_datetime(entry.published_parsed)
        elif getattr(entry, "updated_parsed", None):
            published = _parse_datetime(entry.updated_parsed)
        elif getattr(entry, "published", None):
            published = _parse_datetime(entry.published)
        elif getattr(entry, "updated", None):
            published = _parse_datetime(entry.updated)

        if not _is_recent(published, cutoff):
            continue

        item = _candidate(
            title=title,
            url=link,
            source=name,
            summary=summary,
            published_at=published,
        )
        if item:
            items.append(item)
        if len(items) >= MAX_PER_SOURCE:
            break

    return items


def _looks_like_article_url(href: str, base_netloc: str) -> bool:
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc and parsed.netloc != base_netloc and not parsed.netloc.endswith(
        "." + base_netloc
    ):
        # Allow same registrable host loosely via endswith already handled above
        if base_netloc not in parsed.netloc:
            return False
    path = parsed.path or ""
    if path in ("", "/"):
        return False
    skip_parts = (
        "/tag/",
        "/tags/",
        "/category/",
        "/categories/",
        "/author/",
        "/search",
        "/login",
        "/subscribe",
        "/video/",
        "/podcast",
        "/newsletter",
        "#",
    )
    lower = href.lower()
    if any(p in lower for p in skip_parts):
        return False
    # Prefer paths that look like articles (date or long slug)
    if re.search(r"/20\d{2}/\d{2}/", path):
        return True
    slug = path.rstrip("/").split("/")[-1]
    return len(slug) >= 20 or "-" in slug


def crawl_html(client: httpx.Client, source: dict, cutoff: datetime) -> list[dict]:
    """Conservative listing-page scrape when RSS is missing or empty."""
    del cutoff  # HTML listings rarely expose reliable dates; keep undated
    page_url = (source.get("url") or "").strip()
    name = source.get("name") or "Unknown"
    if not page_url:
        return []

    raw = _fetch_text(client, page_url)
    soup = BeautifulSoup(raw, "html.parser")
    base_netloc = urlparse(page_url).netloc

    seen: set[str] = set()
    items: list[dict] = []

    # Prefer article cards / headline links; skip bare section labels
    link_nodes = soup.select("article a[href], h1 a[href], h2 a[href], h3 a[href], a[href]")
    for node in link_nodes:
        href = node.get("href") or ""
        abs_url = urljoin(page_url, href)
        abs_url = _normalize_url(abs_url)
        if abs_url in seen:
            continue
        if not _looks_like_article_url(abs_url, base_netloc):
            continue

        title = node.get_text(" ", strip=True) or node.get("title") or ""
        if not title or len(title) < 28:
            parent = node.find_parent(["h1", "h2", "h3", "h4"])
            if parent:
                title = parent.get_text(" ", strip=True)
        # Drop nav / section labels ("Artificial intelligence", "Climate & energy")
        if not title or len(title) < 28 or " " not in title.strip():
            continue
        item = _candidate(title=title, url=abs_url, source=name, summary="")
        if not item:
            continue
        seen.add(abs_url)
        items.append(item)
        if len(items) >= MAX_HTML_LINKS:
            break

    return items[:MAX_PER_SOURCE]


def crawl_one_source(source: dict, cutoff: datetime) -> tuple[str, list[dict], str | None]:
    name = source.get("name") or "Unknown"
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=headers) as client:
            items: list[dict] = []
            rss = (source.get("rss") or "").strip()
            if rss:
                try:
                    items = crawl_rss(client, source, cutoff)
                except Exception as exc:
                    print(
                        f"[crawl] {name}: RSS failed ({exc}); trying HTML",
                        file=sys.stderr,
                    )

            if not items:
                if name in BRITTLE_SOURCES and not rss:
                    return name, [], "skipped brittle (no rss)"
                try:
                    items = crawl_html(client, source, cutoff)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in (401, 403, 404):
                        return name, [], f"html blocked ({exc.response.status_code})"
                    raise

            if not items and name in BRITTLE_SOURCES:
                return name, [], "skipped brittle (empty)"

            return name, items, None
    except Exception as exc:
        return name, [], str(exc)


def _normalize_title(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_tokens(text: str) -> set[str]:
    stop = {
        "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "as",
        "at", "by", "from", "is", "are", "be", "its", "it", "this", "that", "new",
        "ai", "tech", "says", "after", "over", "into", "amid",
    }
    return {t for t in _normalize_title(text).split() if len(t) > 2 and t not in stop}


def titles_overlap(a: str, b: str, threshold: float = 0.55) -> bool:
    na, nb = _normalize_title(a), _normalize_title(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / max(1, min(len(ta), len(tb))) >= threshold


def dedupe_candidates(items: list[dict]) -> list[dict]:
    """Drop exact URL duplicates and near-identical titles within the batch."""
    out: list[dict] = []
    seen_urls: set[str] = set()

    for item in items:
        url = item.get("url") or ""
        if url in seen_urls:
            continue
        title = item.get("title") or ""
        if any(titles_overlap(title, prev.get("title") or "") for prev in out):
            continue
        seen_urls.add(url)
        out.append(item)
    return out


TECH_HINTS = {
    "ai", "artificial intelligence", "llm", "chatgpt", "claude", "openai", "anthropic",
    "google", "microsoft", "nvidia", "semiconductor", "chip", "startup", "saas",
    "cyber", "security", "software", "cloud", "robot", "autonomous", "tech",
    "machine learning", "gpu", "data center", "encryption", "privacy", "app store",
}


def _tech_score(item: dict) -> int:
    blob = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
    return sum(1 for hint in TECH_HINTS if hint in blob)


def _sort_key(item: dict) -> tuple:
    published = _parse_datetime(item.get("published_at"))
    # Undated listing-page items: treat as current so they can compete
    ts = published or _now()
    return (_tech_score(item), ts)


def diversify_candidates(items: list[dict], limit: int = MAX_CANDIDATES) -> list[dict]:
    """Keep ranking order but cap how many stories any single outlet can claim."""
    counts: dict[str, int] = {}
    out: list[dict] = []
    for item in items:
        source = item.get("source") or "Unknown"
        if counts.get(source, 0) >= MAX_PER_SOURCE_FINAL:
            continue
        counts[source] = counts.get(source, 0) + 1
        out.append(item)
        if len(out) >= limit:
            break
    return out


def crawl_preferred_sources(sources: dict) -> tuple[list[dict], dict]:
    """
    Crawl all preferred outlets. Returns (candidates, stats).

    stats: { crawled, candidates, sources_ok, sources_failed, failures }
    """
    preferred = sources.get("preferred") or []
    cutoff = _now() - timedelta(hours=RECENCY_HOURS)
    collected: list[dict] = []
    failures: list[str] = []
    sources_ok = 0

    if not preferred:
        return [], {
            "crawled": 0,
            "candidates": 0,
            "sources_ok": 0,
            "sources_failed": 0,
            "failures": [],
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(crawl_one_source, source, cutoff): source for source in preferred
        }
        for future in as_completed(futures):
            name, items, error = future.result()
            if error and not items:
                failures.append(f"{name}: {error}")
                if error.startswith("skipped"):
                    print(f"[crawl] {name}: {error}", file=sys.stderr)
                else:
                    print(f"[crawl] {name}: failed — {error}", file=sys.stderr)
                continue
            if not items:
                failures.append(f"{name}: empty")
                print(f"[crawl] {name}: no items", file=sys.stderr)
                continue
            sources_ok += 1
            collected.extend(items)
            print(f"[crawl] {name}: {len(items)} item(s)")

    collected.sort(key=_sort_key, reverse=True)
    crawled_count = len(collected)
    candidates = diversify_candidates(dedupe_candidates(collected), MAX_CANDIDATES)

    stats = {
        "crawled": crawled_count,
        "candidates": len(candidates),
        "sources_ok": sources_ok,
        "sources_failed": len(preferred) - sources_ok,
        "failures": failures[:20],
    }
    return candidates, stats


def filter_against_recent(candidates: list[dict], recent_texts: list[str]) -> list[dict]:
    """Drop candidates that look like already-covered digest stories."""
    if not recent_texts:
        return candidates
    kept: list[dict] = []
    for item in candidates:
        title = item.get("title") or ""
        if any(titles_overlap(title, prev) for prev in recent_texts):
            continue
        kept.append(item)
    return kept
