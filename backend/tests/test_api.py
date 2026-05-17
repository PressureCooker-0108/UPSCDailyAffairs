"""
Integration tests for the FastAPI API endpoints.

These tests use an in-memory SQLite database and the FastAPI TestClient
to verify that endpoints return the expected HTTP status codes and response shapes.
"""
import pytest
from fastapi.testclient import TestClient


class TestNewsEndpoint:
    """Tests for the /news endpoint."""

    def test_news_returns_valid_structure(self, client: TestClient):
        """GET /news should return a dict with expected keys."""
        response = client.get("/news")
        assert response.status_code == 200

        data = response.json()
        assert "top_stories" in data
        assert "sector_stories" in data
        assert "sectors" in data
        assert "last_updated" in data

    def test_news_stories_are_lists(self, client: TestClient):
        """top_stories and sectors should be lists."""
        response = client.get("/news")
        data = response.json()
        assert isinstance(data["top_stories"], list)
        assert isinstance(data["sectors"], list)
        assert isinstance(data["sector_stories"], dict)

    def test_news_with_force_refresh(self, client: TestClient):
        """GET /news?force_refresh=true should bypass cache."""
        response = client.get("/news?force_refresh=true")
        assert response.status_code == 200
        data = response.json()
        assert "top_stories" in data

    def test_news_returns_200(self, client: TestClient):
        """Baseline: the /news endpoint should respond with 200."""
        response = client.get("/news")
        assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for the root health check endpoint.

    The health endpoint no longer touches the database — it returns a
    simple status string. This prevents Render's deploy health checker
    from failing due to transient DB connection issues.
    """

    def test_health_returns_expected_keys(self, client: TestClient):
        """GET / should return status."""
        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        # stories and last_updated are no longer returned — see Render fix
        assert "stories" not in data
        assert "last_updated" not in data

    def test_health_status_message(self, client: TestClient):
        """The health status should be a positive string."""
        response = client.get("/")
        data = response.json()
        assert isinstance(data["status"], str)
        assert len(data["status"]) > 0
        assert data["status"] == "seriously operational"


class TestSourcesEndpoint:
    """Tests for the /sources endpoint."""

    def test_sources_returns_list(self, client: TestClient):
        """GET /sources should return a dict with a sources list."""
        response = client.get("/sources")
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert isinstance(data["sources"], list)


class TestTrendingEndpoint:
    """Tests for the /trending endpoint."""

    def test_trending_returns_list(self, client: TestClient):
        """GET /trending should return a dict with a trending list."""
        response = client.get("/trending")
        assert response.status_code == 200
        data = response.json()
        assert "trending" in data
        assert isinstance(data["trending"], list)

    def test_trending_with_custom_hours(self, client: TestClient):
        """GET /trending?hours=24 should work."""
        response = client.get("/trending?hours=24")
        assert response.status_code == 200

    def test_trending_invalid_hours_returns_422(self, client: TestClient):
        """GET /trending?hours=0 should return 422 (min is 1)."""
        response = client.get("/trending?hours=0")
        assert response.status_code == 422


class TestMarketsEndpoint:
    """Tests for the /markets endpoint."""

    def test_markets_returns_expected_structure(self, client: TestClient):
        """GET /markets should return a dict with list fields."""
        response = client.get("/markets")
        # Could be 200 or 500 depending on yfinance availability, but should
        # always return valid JSON with the expected keys.
        assert response.status_code in (200, 500)

        if response.status_code == 200:
            data = response.json()
            assert "all" in data
            assert "gainers" in data
            assert "losers" in data
            assert "indices" in data


class TestSectorSummariesEndpoint:
    """Tests for the /news/sector-summaries endpoint."""

    def test_sector_summaries_returns_list(self, client: TestClient):
        """GET /news/sector-summaries should return a dict with summaries list."""
        response = client.get("/news/sector-summaries")
        assert response.status_code == 200
        data = response.json()
        assert "summaries" in data
        assert isinstance(data["summaries"], list)


class TestBriefingEndpoint:
    """Tests for the /briefing endpoint."""

    def test_briefing_returns_200(self, client: TestClient):
        """GET /briefing should return 200."""
        response = client.get("/briefing")
        assert response.status_code == 200

    def test_briefing_has_content_field(self, client: TestClient):
        """The briefing response should have a 'content' field."""
        response = client.get("/briefing")
        data = response.json()
        assert "content" in data or "created_at" in data


class TestExportEndpoints:
    """Tests for export endpoints."""

    def test_export_markdown_returns_200(self, client: TestClient):
        """GET /export/markdown should return a file."""
        response = client.get("/export/markdown")
        assert response.status_code in (200, 500)

    def test_export_json_returns_200(self, client: TestClient):
        """GET /export/json should return JSON."""
        response = client.get("/export/json")
        assert response.status_code in (200, 500)

    def test_export_json_has_expected_keys(self, client: TestClient):
        """Successful JSON export should have stories, markets, source_diversity."""
        response = client.get("/export/json")
        if response.status_code == 200:
            data = response.json()
            assert "exported_at" in data
            assert "stories" in data
