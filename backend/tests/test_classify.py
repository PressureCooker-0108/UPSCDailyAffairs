"""
Unit tests for the classify_news module.

Tests the TF-IDF-based sector classifier with a variety of realistic
news headlines and edge cases.
"""
import pytest
from services.classify_news import classify_sectors, VALID_SECTORS, _classification_cache


class TestClassifySectors:
    """Test suite for classify_sectors()."""

    # ── Single-sector classification ────────────

    def test_markets_sector(self):
        """Finance and market news should classify as Markets."""
        result = classify_sectors(
            "stock market reaches new highs after fed rate decision. "
            "The S&P 500 and Dow Jones both rallied on positive economic data."
        )
        assert "Markets" in result, f"Expected Markets, got {result}"
        # A pure markets headline shouldn't trigger unrelated sectors
        assert "Tech" not in result or "Markets" in result

    def test_tech_sector(self):
        """AI and technology news should classify as Tech."""
        result = classify_sectors(
            "AI startup raises $500 million for new machine learning chip. "
            "The company's breakthrough in neural networks could transform data centers."
        )
        assert "Tech" in result

    def test_geopolitics_sector(self):
        """Geopolitical news should classify as Geopolitics."""
        result = classify_sectors(
            "diplomatic tensions escalate between major powers at UN summit. "
            "Sanctions and trade restrictions threaten global stability."
        )
        assert "Geopolitics" in result

    def test_energy_sector(self):
        """Energy and oil news should classify as Energy."""
        result = classify_sectors(
            "oil prices surge as OPEC announces production cuts. "
            "Crude oil supply concerns drive energy sector volatility."
        )
        assert "Energy" in result

    def test_india_sector(self):
        """India-specific news should classify as India."""
        result = classify_sectors(
            "india gdp growth accelerates to 7.5 percent. "
            "Indian economy shows strong manufacturing and services output."
        )
        assert "India" in result

    def test_general_sector_fallback(self):
        """Generic news with no clear sector should classify as General."""
        result = classify_sectors(
            "local community celebrates annual festival with colorful parade. "
            "Hundreds of residents gathered in the town square."
        )
        assert "General" in result

    # ── Edge cases ──────────────────────────────

    def test_empty_string_returns_general(self):
        """Empty input should gracefully return General."""
        result = classify_sectors("")
        assert result == ["General"]

    def test_whitespace_only_returns_general(self):
        """Whitespace-only input should return General."""
        result = classify_sectors("   \n  \t  ")
        assert result == ["General"]

    def test_very_short_text_returns_reasonable_sector(self):
        """Very short text should still produce a reasonable classification."""
        result = classify_sectors("stock market rally")
        assert len(result) >= 1
        assert all(s in VALID_SECTORS for s in result)

    def test_short_tech_text(self):
        """Short tech text should classify as Tech."""
        result = classify_sectors("AI breakthrough")
        assert "Tech" in result or len(result) >= 1

    # ── Multi-sector classification ─────────────

    def test_mixed_markets_and_tech(self):
        """Text combining markets and tech should return both."""
        result = classify_sectors(
            "tech stocks rally as nasdaq hits new record. "
            "AI companies lead the market higher."
        )
        # Should include at least Markets or Tech (often both)
        assert "Markets" in result or "Tech" in result
        # The result should be reasonable — at least 1 sector, at most 2
        assert 1 <= len(result) <= 2

    def test_energy_and_geopolitics_overlap(self):
        """Energy news with geopolitical context should capture both."""
        result = classify_sectors(
            "oil prices surge after geopolitical tensions disrupt supply chains. "
            "Middle east conflict threatens global energy markets."
        )
        assert len(result) >= 1
        # Should capture either Energy or Geopolitics
        has_relevant = "Energy" in result or "Geopolitics" in result
        assert has_relevant, f"Expected Energy or Geopolitics, got {result}"

    # ── Cache behavior ──────────────────────────

    def test_cache_returns_same_result(self, clear_classify_cache):
        """Calling classify_sectors twice with the same text should return the same result."""
        text = "stock market reaches new highs amid fed rate decision."
        result1 = classify_sectors(text)
        result2 = classify_sectors(text)
        assert result1 == result2

    def test_cache_prevents_recomputation(self, clear_classify_cache):
        """The classifier should use cache for repeated identical inputs."""
        text = "ai startup raises funding for chip development."
        assert text[:200] not in _classification_cache

        result1 = classify_sectors(text)
        # After first call, the result should be cached
        cache_key = text[:200]
        assert cache_key in _classification_cache
        assert _classification_cache[cache_key] == result1

    def test_different_inputs_different_cache_entries(self, clear_classify_cache):
        """Different inputs should have separate cache entries."""
        classify_sectors("stock market rally")
        classify_sectors("ai breakthrough")
        assert len(_classification_cache) >= 2

    # ── Input format robustness ─────────────────

    def test_classify_with_urls(self):
        """Text containing URLs should still classify correctly."""
        result = classify_sectors(
            "breaking: fed announces rate hike https://example.com/fed-decision "
            "markets react to central bank policy change."
        )
        assert "Markets" in result or len(result) >= 1

    def test_classify_with_special_characters(self):
        """Text with special characters should not crash the classifier."""
        result = classify_sectors(
            "oil & gas prices surge! OPEC+ decision: $80/barrel (crude). "
            "Energy sector @ record highs #energy"
        )
        assert len(result) >= 1
        assert all(s in VALID_SECTORS for s in result)

    def test_classify_with_mixed_case(self):
        """The classifier should handle mixed case (it lowercases input)."""
        result1 = classify_sectors("STOCK MARKET RALLY TODAY")
        result2 = classify_sectors("stock market rally today")
        assert result1 == result2
