import hashlib
from loguru import logger
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import feedparser
import httpx

from config import RSS_SOURCES, PRS_SCRAPER_CONFIG, get_source_metadata, get_source_weight


# Regex to extract first <img> src from HTML snippets (fallback for feeds without media tags)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

# ── PRS scraper regex patterns ───────────────
_PRS_TITLE_RE = re.compile(r'<h2[^>]*>\s*<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>\s*</h2>', re.IGNORECASE)
_PRS_TITLE_RE2 = re.compile(r'<h3[^>]*>\s*<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>\s*</h3>', re.IGNORECASE)
_PRS_SUMMARY_RE = re.compile(r'<p[^>]*class=["\'][^"\']*summary[^"\']*["\'][^>]*>([^<]+)</p>', re.IGNORECASE)
_PRS_SUMMARY_RE2 = re.compile(r'<div[^>]*class=["\'][^"\']*excerpt[^"\']*["\'][^>]*>\s*<p[^>]*>([^<]+)</p>', re.IGNORECASE)


# ── Helper ───────────────────────────────────

def _extract_image_url(entry) -> str | None:
    """Extract the best available image URL from an RSS entry."""
    thumbnails = entry.get("media_thumbnail", [])
    if thumbnails and isinstance(thumbnails, list):
        best = max(thumbnails, key=lambda t: int(t.get("width", 0) or 0))
        url = best.get("url", "")
        if url:
            return url

    media = entry.get("media_content", [])
    if media and isinstance(media, list):
        for m in media:
            if m.get("medium") == "image" and m.get("url"):
                return m["url"]
        if media[0].get("url"):
            return media[0]["url"]

    summary = entry.get("summary", "")
    if summary:
        match = _IMG_SRC_RE.search(summary)
        if match:
            return match.group(1)

    content_list = entry.get("content", [])
    if content_list and isinstance(content_list, list):
        for content_item in content_list:
            value = content_item.get("value", "")
            if value:
                match = _IMG_SRC_RE.search(value)
                if match:
                    return match.group(1)

    links = entry.get("links", [])
    if links and isinstance(links, list):
        for link in links:
            rel = link.get("rel", "")
            href = link.get("href", "")
            media_type = link.get("type", "")
            if rel == "enclosure" and href and media_type.startswith("image/"):
                return href

    return None


def _enrich_article(article: dict, source_name: str) -> dict:
    """Attach source metadata to an article dict from SOURCE_METADATA in config."""
    meta = get_source_metadata(source_name)
    article["source_type"] = meta["type"]
    article["authority_score"] = meta["authority_score"]
    article["source_priority"] = meta["upsc_priority"]
    article["source_weight"] = get_source_weight(source_name)
    return article


def _fetch_single_source(source: dict) -> list[dict]:
    """Fetch and normalize articles from a single RSS source."""
    try:
        feed = feedparser.parse(source["url"])
        articles = []
        source_sectors = source.get("sectors", [])
        source_name = source["name"]

        for entry in feed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not link or not title:
                continue

            published_at = datetime.now(timezone.utc).isoformat()
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()

            article_id = hashlib.md5(link.encode("utf-8")).hexdigest()

            article = {
                "id": article_id,
                "title": title.lower(),
                "url": link,
                "source": source_name,
                "published_at": published_at,
                "content_snippet": entry.get("summary", ""),
                "source_sectors": source_sectors,
                "image_url": _extract_image_url(entry),
            }
            _enrich_article(article, source_name)
            articles.append(article)

        logger.info(f"  {source_name}: {len(articles)} articles")
        return articles

    except Exception as e:
        logger.error(f"  {source['name']}: Error — {e}")
        return []


# ── PRS Scraper ─────────────────────────────

def _scrape_prs_page(client: httpx.Client, page_path: str) -> list[dict]:
    """Scrape a single PRS India page for article links and metadata.

    Uses regex-based HTML extraction to avoid adding BeautifulSoup dependency.
    """
    url = f"{PRS_SCRAPER_CONFIG['base_url']}{page_path}"
    try:
        resp = client.get(url, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning(f"  PRS: Failed to fetch {page_path} — {e}")
        return []

    articles = []
    now = datetime.now(timezone.utc).isoformat()
    seen_urls = set()

    # Extract title+link pairs from h2 and h3 tags
    matches = _PRS_TITLE_RE.findall(html) + _PRS_TITLE_RE2.findall(html)

    if not matches:
        logger.warning(f"  PRS {page_path}: no article links found (page structure may have changed)")

    for href, title_text in matches:
        href = href.strip()
        title_text = title_text.strip()
        if not href or not title_text:
            continue

        if href.startswith("/"):
            href = f"{PRS_SCRAPER_CONFIG['base_url']}{href}"

        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Extract summary from nearby HTML
        summary = ""
        summary_matches = _PRS_SUMMARY_RE.findall(html)
        if summary_matches:
            summary = summary_matches[0].strip()
        else:
            summary_matches2 = _PRS_SUMMARY_RE2.findall(html)
            if summary_matches2:
                summary = summary_matches2[0].strip()

        article_id = hashlib.md5(href.encode("utf-8")).hexdigest()

        article = {
            "id": article_id,
            "title": title_text.lower(),
            "url": href,
            "source": "PRS",
            "published_at": now,
            "content_snippet": summary or title_text,
            "source_sectors": ["India", "Governance"],
            "image_url": None,
        }
        _enrich_article(article, "PRS")
        articles.append(article)

    logger.info(f"  PRS {page_path}: {len(articles)} articles")
    return articles


def fetch_prs_articles() -> list[dict]:
    """Fetch articles from PRS Legislative Research using lightweight scraping.

    PRS does not offer RSS feeds, so we scrape key pages.
    Returns list of article dicts in the same format as RSS sources.
    """
    if not PRS_SCRAPER_CONFIG.get("enabled", True):
        return []

    all_articles = []
    seen_urls: set[str] = set()

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            for page_path in PRS_SCRAPER_CONFIG["pages"]:
                page_articles = _scrape_prs_page(client, page_path)
                for article in page_articles:
                    if article["url"] not in seen_urls:
                        seen_urls.add(article["url"])
                        all_articles.append(article)

                if len(all_articles) >= PRS_SCRAPER_CONFIG["max_articles"]:
                    all_articles = all_articles[:PRS_SCRAPER_CONFIG["max_articles"]]
                    break

        logger.info(f"PRS: {len(all_articles)} articles scraped")
    except Exception as e:
        logger.error(f"PRS scraper failed: {e}")

    return all_articles


# ── Main Fetcher ─────────────────────────────

def fetch_rss_feeds() -> list[dict]:
    """Fetch and normalize articles from multiple RSS sources in parallel.

    Uses a thread pool (8 workers) for I/O-bound HTTP requests.
    Deduplicates by URL across all sources.
    Also fetches PRS articles via lightweight scraper.
    """
    seen_urls: set[str] = set()
    all_articles: list[dict] = []

    logger.info(f"Fetching {len(RSS_SOURCES)} RSS feeds in parallel (8 workers)...")

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_single_source, src): src for src in RSS_SOURCES}

        for future in as_completed(futures):
            source = futures[future]
            source_articles = future.result()

            for article in source_articles:
                if article["url"] not in seen_urls:
                    seen_urls.add(article["url"])
                    all_articles.append(article)

    # Fetch PRS articles (not RSS, uses httpx scraper)
    prs_articles = fetch_prs_articles()
    for article in prs_articles:
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

    logger.info(f"Fetched {len(all_articles)} unique articles across all sources (incl. PRS).")
    return all_articles
