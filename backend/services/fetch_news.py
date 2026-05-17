import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import feedparser

from config import RSS_SOURCES

logger = logging.getLogger(__name__)

# Regex to extract first <img> src from HTML snippets (fallback for feeds without media tags)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


# ── Helper ───────────────────────────────────

def _extract_image_url(entry) -> str | None:
    """Extract the best available image URL from an RSS entry.

    Checks multiple sources in order of reliability:
      1. media_thumbnail (BBC, Guardian, etc.)
      2. media_content (NYT, etc.)
      3. First <img> tag in summary HTML (fallback for feeds without media tags)

    Returns:
        Image URL string, or None if no image is found.
    """
    # Check media_thumbnail (most common standard — BBC, Guardian, WaPo)
    thumbnails = entry.get("media_thumbnail", [])
    if thumbnails and isinstance(thumbnails, list):
        # Prefer the largest thumbnail by width
        best = max(thumbnails, key=lambda t: int(t.get("width", 0) or 0))
        url = best.get("url", "")
        if url:
            return url

    # Check media_content (NYT, some others)
    media = entry.get("media_content", [])
    if media and isinstance(media, list):
        for m in media:
            if m.get("medium") == "image" and m.get("url"):
                return m["url"]
        # Fallback: first media item with a url even without medium type
        if media[0].get("url"):
            return media[0]["url"]

    # Fallback: try to extract from summary HTML (TechCrunch, Al Jazeera, etc.)
    summary = entry.get("summary", "")
    if summary:
        match = _IMG_SRC_RE.search(summary)
        if match:
            return match.group(1)

    # Fallback: check entry.content for embedded images (some feeds put
    # full HTML content here instead of summary)
    content_list = entry.get("content", [])
    if content_list and isinstance(content_list, list):
        for content_item in content_list:
            value = content_item.get("value", "")
            if value:
                match = _IMG_SRC_RE.search(value)
                if match:
                    return match.group(1)

    # Fallback: check links for enclosure-type images (podcasts, ESPN, etc.)
    links = entry.get("links", [])
    if links and isinstance(links, list):
        for link in links:
            rel = link.get("rel", "")
            href = link.get("href", "")
            media_type = link.get("type", "")
            if rel == "enclosure" and href and media_type.startswith("image/"):
                return href

    return None


def _fetch_single_source(source: dict) -> list[dict]:
    """Fetch and normalize articles from a single RSS source.

    Runs in a worker thread. Returns a list of article dicts.
    Includes the source's sector tags and image URL so downstream
    classification can use them.
    """
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        source_sectors = source.get("sectors", [])

        for entry in feed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue

            # Normalize published date
            published_at = datetime.now(timezone.utc).isoformat()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()

            # Create unique ID from URL
            article_id = hashlib.md5(link.encode("utf-8")).hexdigest()

            articles.append({
                "id": article_id,
                "title": title.lower(),
                "url": link,
                "source": source["name"],
                "published_at": published_at,
                "content_snippet": entry.get("summary", ""),
                "source_sectors": source_sectors,  # Tags inherited from RSS source
                "image_url": _extract_image_url(entry),  # Image from RSS media tags
            })

        logger.info(f"  {source['name']}: {len(articles)} articles")
        return articles

    except Exception as e:
        logger.error(f"  {source['name']}: Error — {e}")
        return []


# ── Main Fetcher ─────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Fetch and normalize articles from multiple RSS sources in parallel.

    Uses a thread pool (8 workers) for I/O-bound HTTP requests.
    Deduplicates by URL across all sources.
    """
    seen_urls: set[str] = set()
    all_articles: list[dict] = []

    logger.info(f"Fetching {len(RSS_SOURCES)} RSS feeds in parallel (8 workers)...")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_single_source, src): src for src in RSS_SOURCES}

        for future in as_completed(futures):
            source = futures[future]
            source_articles = future.result()

            # Deduplicate against seen URLs (main thread, so no race condition)
            for article in source_articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    all_articles.append(article)

    logger.info(f"Fetched {len(all_articles)} unique articles across all sources.")
    return all_articles
