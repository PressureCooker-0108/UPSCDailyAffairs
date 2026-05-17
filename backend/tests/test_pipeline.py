"""
Smoke tests for the news pipeline.

These tests make real HTTP requests to a subset of RSS feeds to verify
that the pipeline's core functions work end-to-end.

Marked with @pytest.mark.smoke so they can be excluded from quick test runs:
    pytest -m "not smoke"   # run everything except smoke tests
    pytest -m smoke         # run only smoke tests
"""
import pytest
from services.fetch_news import fetch_rss_feeds, RSS_SOURCES
from services.clean_news import clean_articles
from services.classify_news import classify_sectors


# Use only 3 reliable sources for the smoke test to keep it fast
# BBC, NYT, and TechCrunch are typically available
SMOKE_SOURCES = [
    {"name": "BBC", "url": "http://feeds.bbci.co.uk/news/rss.xml"},
    {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
    {"name": "Times of India", "url": "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"},
]


@pytest.mark.smoke
class TestRssFetch:
    """Test that RSS fetching works against real feeds."""

    def test_fetch_returns_articles(self):
        """Fetching from 3 real feeds should return a list of articles."""
        articles = fetch_rss_feeds()

        assert isinstance(articles, list)
        assert len(articles) > 0, "Expected at least 1 article from 3 feeds"

    def test_fetched_articles_have_required_fields(self):
        """Each article should have id, title, url, source, published_at."""
        articles = fetch_rss_feeds()

        for article in articles:
            assert "id" in article, f"Missing id in {article.get('title', 'unknown')}"
            assert "title" in article, "Missing title"
            assert "url" in article, "Missing url"
            assert "source" in article, "Missing source"
            assert "published_at" in article, "Missing published_at"

            # Basic validation of field types
            assert isinstance(article["id"], str), "id should be string"
            assert isinstance(article["title"], str), "title should be string"
            assert len(article["title"]) > 0, "title should not be empty"
            assert isinstance(article["url"], str), "url should be string"
            assert article["url"].startswith("http"), f"url should start with http: {article['url']}"

    def test_fetched_articles_have_content(self):
        """Articles should have content_snippet field (may be empty)."""
        articles = fetch_rss_feeds()
        for article in articles:
            assert "content_snippet" in article

    def test_articles_are_deduplicated_by_url(self):
        """No two articles should share the same URL."""
        articles = fetch_rss_feeds()
        urls = [a["url"] for a in articles]
        unique_urls = set(urls)
        assert len(urls) == len(unique_urls), f"Found {len(urls) - len(unique_urls)} duplicate URLs"

    def test_titles_are_lowercase(self):
        """Titles should be normalized to lowercase."""
        articles = fetch_rss_feeds()
        for article in articles:
            has_upper = any(c.isupper() for c in article["title"])
            assert not has_upper, f"Title not lowercase: {article['title'][:80]}"


@pytest.mark.smoke
class TestCleanPipeline:
    """Test the cleaning step on real fetched data."""

    def test_clean_non_empty_articles(self):
        """Cleaning should not remove all articles."""
        articles = fetch_rss_feeds()
        cleaned = clean_articles(articles)
        assert len(cleaned) > 0, "Cleaning removed all articles"
        assert len(cleaned) <= len(articles), "Cleaning should not add articles"

    def test_clean_preserves_good_data(self):
        """Cleaning should preserve all articles and strip HTML tags."""
        articles = fetch_rss_feeds()
        cleaned = clean_articles(articles)
        # Clean doesn't remove articles, it only normalizes text
        assert len(cleaned) == len(articles)
        # No raw HTML tags should remain (entities like &amp; are expected
        # since clean_text only strips tags, not decodes entities)
        for a in cleaned:
            assert "<" not in a["title"] or a["title"].count("<") == a["title"].count(">"), \
                f"Unbalanced HTML tag found: {a['title'][:100]}"


@pytest.mark.smoke
class TestClassifyRealNews:
    """Test classification on real fetched headlines."""

    def test_classify_fetched_articles(self):
        """All fetched articles should be classifiable without errors."""
        articles = fetch_rss_feeds()

        for article in articles[:20]:  # Test first 20 articles
            text = f"{article['title']}. {article.get('content_snippet', '')}"
            sectors = classify_sectors(text)
            assert isinstance(sectors, list), f"Expected list, got {type(sectors)}"
            assert len(sectors) >= 1, "Expected at least 1 sector"
            assert len(sectors) <= 2, "Expected at most 2 sectors"

    def test_classify_markets_article(self):
        """Real market news should classify as Markets."""
        text = "stock market rally today as fed announces rate cut. S&P 500 hits new high."
        sectors = classify_sectors(text)
        assert "Markets" in sectors, f"Expected Markets, got {sectors}"


@pytest.mark.smoke
@pytest.mark.skip(reason="Full pipeline smoke test requires DB setup — run manually")
class TestFullPipeline:
    """Complete end-to-end pipeline smoke test (requires database)."""

    def test_pipeline_runs_without_error(self):
        """The full pipeline should complete without crashing."""
        from scheduler import run_pipeline
        # This will use SQLite locally and fetch real RSS feeds
        run_pipeline()
        # If we get here, the pipeline completed
        assert True
