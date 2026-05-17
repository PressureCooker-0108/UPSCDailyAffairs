"""
Shared test fixtures for the News Dashboard backend.

Pytest auto-discovers this file and makes fixtures available to all tests.
"""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure the backend directory is on sys.path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Pytest configuration ─────────────────────

def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "smoke: Tests that make real HTTP requests (RSS feeds). Use -m 'not smoke' to skip.",
    )


# ── Fixtures ─────────────────────────────────


@pytest.fixture
def sample_articles() -> list[dict]:
    """A list of realistic article dicts for use in integration/smoke tests."""
    return [
        {
            "id": "abc123",
            "title": "stock market reaches new highs amid fed rate decision",
            "url": "https://example.com/market-news",
            "source": "Test Source",
            "published_at": "2025-01-15T10:00:00+00:00",
            "content_snippet": "The stock market rallied today as the Federal Reserve announced its latest rate decision. Investors reacted positively to the news.",
        },
        {
            "id": "def456",
            "title": "ai startup raises $500 million for new chip development",
            "url": "https://example.com/tech-news",
            "source": "Tech Blog",
            "published_at": "2025-01-15T11:00:00+00:00",
            "content_snippet": "A promising AI startup has secured $500 million in funding to develop next-generation chips for machine learning applications.",
        },
        {
            "id": "ghi789",
            "title": "india gdp growth accelerates to 7.5 percent",
            "url": "https://example.com/india-news",
            "source": "Times of India",
            "published_at": "2025-01-14T08:00:00+00:00",
            "content_snippet": "India's economy grew at 7.5% in the latest quarter, driven by strong manufacturing and services sectors.",
        },
        {
            "id": "jkl012",
            "title": "oil prices surge after geopolitical tensions in middle east",
            "url": "https://example.com/energy-news",
            "source": "Reuters",
            "published_at": "2025-01-15T06:00:00+00:00",
            "content_snippet": "Oil prices jumped 5% following increased tensions in the Middle East, raising concerns about supply disruptions.",
        },
        {
            "id": "mno345",
            "title": "new climate report warns of rising sea levels by 2030",
            "url": "https://example.com/climate-news",
            "source": "BBC",
            "published_at": "2025-01-13T14:00:00+00:00",
            "content_snippet": "A new UN climate report warns that sea levels could rise significantly by 2030 if emissions are not reduced.",
        },
    ]


@pytest.fixture
def app():
    """Create a test FastAPI app with SQLite, skipping the lifespan scheduler."""
    # Set test environment to prevent the app lifespan from starting the
    # real scheduler and background pipeline (which makes real HTTP requests).
    os.environ["DATABASE_URL"] = "sqlite:///test_news.db"
    os.environ["_TESTING"] = "1"

    # Import here so the test DB URL is picked up
    from models.database import init_db
    init_db()

    from main import app as _app
    yield _app

    # Cleanup test database
    cleanup_test_db()


@pytest.fixture
def client(app):
    """FastAPI TestClient for integration tests."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def clear_classify_cache():
    """Clear the classify module's in-memory cache before each test."""
    from services.classify_news import _classification_cache
    _classification_cache.clear()
    return _classification_cache


# ── Helpers ──────────────────────────────────

def cleanup_test_db():
    """Remove test database files created during test runs."""
    import glob
    for f in glob.glob("test_news.db*"):
        try:
            os.remove(f)
        except (PermissionError, FileNotFoundError):
            pass
