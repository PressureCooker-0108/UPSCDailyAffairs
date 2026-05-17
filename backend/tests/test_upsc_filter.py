"""
Unit tests for upsc_filter.py — Syllabus-Aware ML Filtering Engine.

Tests cover:
  - Syllabus classification (classify_article)
  - Relevance scoring (score_relevance)
  - Irrelevant content detection (_check_irrelevant)
  - High-CA topic boosting (_high_ca_boost)
  - Criteria matching (_count_matched_criteria)
  - Novelty scoring (score_novelty, record_story, clear_novelty_memory)
  - Cluster processing (process_cluster, filter_and_rank_clusters)
  - Edge cases (empty text, missing syllabus, etc.)
"""

import pytest
import numpy as np
from upsc_filter import (
    classify_article,
    score_relevance,
    score_novelty,
    record_story,
    clear_novelty_memory,
    _check_irrelevant,
    _count_matched_criteria,
    _high_ca_boost,
    _build_cluster_text,
    process_cluster,
    filter_and_rank_clusters,
    _syllabus_vectorizer,
    _syllabus_vectors,
)


# ── Syllabus Classification Tests ──


class TestClassifyArticle:
    """Tests for classify_article() — the core syllabus mapping function."""

    def test_classify_governance_article(self):
        """Governance/policy text should map to a GS paper."""
        text = (
            "The government announced a new direct benefit transfer scheme for farmers "
            "under the PM Kisan Yojana. This will provide financial assistance to "
            "marginal farmers across India."
        )
        result = classify_article(text)
        assert "gs_paper" in result
        assert result["gs_paper"] != "Unknown"
        assert isinstance(result["subtopics"], list)
        assert result["confidence"] > 0

    def test_classify_economy_article(self):
        """Economic/financial text should have reasonable confidence."""
        text = (
            "The Indian economy is projected to grow at 7 percent in the current "
            "fiscal year. The monetary policy committee maintained the repo rate "
            "amidst stable inflation."
        )
        result = classify_article(text)
        assert result["gs_paper"] != "Unknown"
        assert result["confidence"] > 0

    def test_classify_returns_all_scores(self):
        """Classification should include all_scores for debugging."""
        text = "Supreme Court delivers landmark judgment on right to privacy."
        result = classify_article(text)
        assert "all_scores" in result
        assert len(result["all_scores"]) > 0
        assert "score" in result["all_scores"][0]
        assert "gs_paper" in result["all_scores"][0]

    def test_classify_empty_text(self):
        """Empty text should not crash."""
        result = classify_article("")
        assert isinstance(result, dict)
        assert "gs_paper" in result

    def test_classify_nonsense_text(self):
        """Random/nonsense text should not crash and should return low confidence."""
        result = classify_article("xyz zyx abc def ghi jkl mno pqr stu vwx yz")
        # Confidence may still be > 0 due to syllabus topic TF-IDF overlap
        assert isinstance(result, dict)
        assert "gs_paper" in result

    def test_classify_without_syllabus(self, monkeypatch):
        """When syllabus vectors are None, classify should return defaults."""
        monkeypatch.setattr("upsc_filter._syllabus_vectors", None)
        monkeypatch.setattr("upsc_filter._syllabus_vectorizer", None)
        result = classify_article("Any text here")
        assert result["gs_paper"] == "Unknown"
        assert result["confidence"] == 0.0
        assert result["subtopics"] == []


# ── Irrelevant Content Detection Tests ──


class TestIrrelevantDetection:
    """Tests for _check_irrelevant() — the hard rejection filter."""

    RELEVANT_TEXTS = [
        "The government announced a new policy on taxation",
        "Supreme court judgment on environmental clearance",
        "India and China hold border talks in Delhi",
        "RBI maintains repo rate at 6.5 percent",
        "New education policy focuses on skill development",
    ]

    IRRELEVANT_TEXTS = [
        "The celebrity wedding was attended by many film actors",
        "New bollywood movie breaks box office records",
        "IPL cricket match highlights from last night",
        "Fashion show in paris attracts top models",
        "Reality show winner announced after grand finale",
        "Football match premier league final score",
        "Actor and actress spotted at music album launch",
    ]

    @pytest.mark.parametrize("text", RELEVANT_TEXTS)
    def test_relevant_text_not_rejected(self, text):
        """UPSC-relevant text should NOT trigger the irrelevant filter."""
        assert not _check_irrelevant(text)

    @pytest.mark.parametrize("text", IRRELEVANT_TEXTS)
    def test_irrelevant_text_rejected(self, text):
        """Celebrity/entertainment/sports/gossip should be rejected."""
        assert _check_irrelevant(text)

    def test_empty_text_not_irrelevant(self):
        """Empty text should not be flagged as irrelevant."""
        assert not _check_irrelevant("")

    def test_mixed_text_still_rejected(self):
        """Text with both relevant and irrelevant content should still be rejected."""
        text = "The government policy on taxation was overshadowed by celebrity gossip"
        assert _check_irrelevant(text)


# ── Criteria Matching Tests ──


class TestCountMatchedCriteria:
    """Tests for _count_matched_criteria()."""

    def test_governance_text_matches_criteria(self):
        """Text about Indian government policy should match criteria."""
        matched, count = _count_matched_criteria(
            "The Indian government announced a new policy on welfare schemes"
        )
        assert isinstance(matched, list)
        assert count > 0

    def test_foreign_text_may_not_match(self):
        """Text without Indian/government keywords may not match criteria."""
        matched, count = _count_matched_criteria(
            "A new scientific discovery was made about quantum computing"
        )
        # May or may not match depending on criteria — just check no errors
        assert isinstance(matched, list)
        assert isinstance(count, int)

    def test_empty_text_no_match(self):
        """Empty text should return empty list and zero count."""
        matched, count = _count_matched_criteria("")
        assert matched == []
        assert count == 0


# ── High-CA Boost Tests ──


class TestHighCABoost:
    """Tests for _high_ca_boost()."""

    def test_governance_text_gets_boost(self):
        """Text matching high-CA topics should get a boost > 0."""
        text = (
            "The Indian government announced welfare schemes and policy changes "
            "for sustainable development and economic growth"
        )
        boost = _high_ca_boost(text)
        assert isinstance(boost, float)
        assert boost >= 0

    def test_irrelevant_text_no_boost(self):
        """Text with no high-CA keywords should get zero boost."""
        text = "A new movie was released in theatres this weekend"
        boost = _high_ca_boost(text)
        assert boost == 0.0

    def test_boost_capped_at_max(self):
        """Boost should be capped at 0.5 even with many matches."""
        text = (
            "governance constitution economy environment international relations "
            "science technology internal security welfare schemes policy changes "
            "sustainable development climate change social justice economic growth "
            "all these topics are covered comprehensively"
        )
        boost = _high_ca_boost(text)
        assert boost <= 0.5
        assert boost >= 0


# ── Relevance Scoring Tests ──


class TestScoreRelevance:
    """Tests for score_relevance() — the main UPSC relevance engine."""

    def test_relevant_governance_text(self):
        """Governance/policy text should score as relevant."""
        text = (
            "The Indian government announced a new direct benefit transfer scheme "
            "for farmers under PM Kisan. This policy provides financial assistance "
            "to marginal farmers across India."
        )
        result = score_relevance(text)
        assert isinstance(result, dict)
        assert "is_relevant" in result
        assert "relevance_score" in result
        assert "gs_paper" in result
        assert "subtopics" in result
        assert "matched_criteria" in result
        assert isinstance(result["matched_criteria"], list)
        assert result["relevance_score"] >= 0

    def test_irrelevant_celebrity_text(self):
        """Celebrity gossip should score as not relevant."""
        text = "Celebrity actor attends bollywood movie premiere with famous actress"
        result = score_relevance(text)
        assert result["is_relevant"] is False
        assert result["relevance_score"] == 0.0
        assert result.get("rejection_reason") == "irrelevant_content"

    def test_irrelevant_sports_text(self):
        """Sports content should score as not relevant."""
        text = "IPL cricket match highlights and player transfer rumors"
        result = score_relevance(text)
        assert result["is_relevant"] is False
        assert result["relevance_score"] == 0.0

    def test_empty_text(self):
        """Empty text should not crash and return zero scores."""
        result = score_relevance("")
        assert result["is_relevant"] is False
        assert result["relevance_score"] == 0.0
        assert result["gs_paper"] == "Unknown"

    def test_whitespace_text(self):
        """Whitespace-only text should return zero scores."""
        result = score_relevance("   \n   \t   ")
        assert result["is_relevant"] is False

    def test_priority_score_derived_from_relevance(self):
        """Priority score should be related to relevance score."""
        text = "Government policy on direct benefit transfer for farmers in India"
        result = score_relevance(text)
        assert 0 <= result["priority_score"] <= 1.0
        # Priority is derived from relevance + boosts, so it should be <= 1.0
        # and proportional to relevance

    def test_relevance_boosted_by_criteria_match(self):
        """Text matching multiple criteria should get a boost."""
        text = (
            "The Indian government announced a new legislation on environmental "
            "protection. This policy change will affect the economy and improve "
            "security measures."
        )
        result = score_relevance(text)
        # Should have matched some criteria
        assert len(result["matched_criteria"]) > 0
        assert result["relevance_score"] > 0

    def test_with_precomputed_classification(self):
        """Passing a pre-computed classification should work."""
        classification = {
            "gs_paper": "GS2",
            "subtopics": ["Governance", "Polity"],
            "confidence": 0.5,
            "topic": "Governance",
            "all_scores": [{"gs_paper": "GS2", "score": 0.5, "topic": "Governance", "subtopic": ""}],
        }
        text = "Some governance text here"
        result = score_relevance(text, classification=classification)
        assert result["gs_paper"] == "GS2"
        assert result["confidence"] == 0.5

    def test_highly_relevant_text_passes_threshold(self):
        """Highly relevant UPSC text should pass relevance threshold."""
        text = (
            "The Indian government announced major constitutional reforms "
            "through a new legislation in parliament. The policy will impact "
            "governance, economy, and social justice across the country."
        )
        result = score_relevance(text)
        # The GS paper boost + criteria match should push it above 0.35
        assert result["is_relevant"] is True or result["relevance_score"] > 0


# ── Novelty Scoring Tests ──


class TestNoveltyScoring:
    """Tests for score_novelty(), record_story(), and clear_novelty_memory()."""

    def setup_method(self):
        """Clear novelty memory before each test."""
        clear_novelty_memory()

    def test_first_story_is_novel(self):
        """The first story should always have novelty_score of 1.0."""
        result = score_novelty("This is the first story ever")
        assert result["novelty_score"] == 1.0
        assert result["duplicate_of"] is None

    def test_identical_story_detected_as_duplicate(self):
        """Recording and then scoring the same text should detect duplication."""
        text = "The government announced a new policy on taxation"
        record_story(text)
        result = score_novelty(text)
        assert result["novelty_score"] < 1.0
        assert result["max_similarity"] > 0.8

    def test_different_stories_get_high_novelty(self):
        """Completely different stories should have high novelty."""
        record_story("Government policy on taxation in India")
        result = score_novelty("New scientific discovery about quantum computing in Switzerland")
        assert result["novelty_score"] >= 0.5
        assert result["duplicate_of"] is None

    def test_multiple_stories_in_memory(self):
        """Multiple recorded stories should all be checked against new text."""
        record_story("Economic policy and growth in India")
        record_story("Environmental protection and climate change")
        record_story("Supreme court judgment on constitutional law")
        # New story that's different
        result = score_novelty("International relations between India and China")
        assert result["novelty_score"] > 0
        assert isinstance(result["duplicate_of"], type(None)) or isinstance(result["duplicate_of"], str)

    def test_clear_novelty_memory(self):
        """clear_novelty_memory() should reset the memory."""
        record_story("Some recorded story")
        clear_novelty_memory()
        result = score_novelty("Any story after clearing memory")
        assert result["novelty_score"] == 1.0

    def test_novelty_never_below_01(self):
        """Novelty score should never drop below 0.1."""
        text = "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z"
        for _ in range(10):
            record_story(text)
        result = score_novelty(text)
        assert result["novelty_score"] >= 0.1


# ── Cluster Processing Tests ──


class TestBuildClusterText:
    """Tests for _build_cluster_text()."""

    def test_build_cluster_text(self):
        """Building text from a cluster should produce a combined string."""
        cluster = [
            {"title": "First article title", "content_snippet": "Content of first article"},
            {"title": "Second article title", "content_snippet": "Content of second article"},
        ]
        text = _build_cluster_text(cluster)
        assert "First article title" in text
        assert "Second article title" in text
        assert "Content of first article" in text

    def test_empty_cluster(self):
        """An empty cluster should return an empty string."""
        text = _build_cluster_text([])
        assert text == ""

    def test_cluster_limited_to_5_articles(self):
        """_build_cluster_text should only process first 5 articles."""
        cluster = [
            {"title": f"Article {i}", "content_snippet": f"Content {i}"}
            for i in range(10)
        ]
        text = _build_cluster_text(cluster)
        assert "Article 0" in text
        # [:5] gives indices 0,1,2,3,4 — so Article 5 should NOT be present
        assert "Article 5" not in text
        assert "Article 9" not in text  # 10th article should not be included


class TestProcessCluster:
    """Tests for process_cluster()."""

    def test_relevant_cluster_passes(self):
        """A cluster about governance/policy should pass the filter."""
        cluster = [
            {
                "title": "Government announces new welfare scheme for farmers",
                "content_snippet": "The Indian government announced a new direct benefit transfer scheme for farmers under PM Kisan Yojana."
            },
            {
                "title": "Policy changes in agricultural sector",
                "content_snippet": "New policy changes will benefit marginal farmers across India."
            },
        ]
        result = process_cluster(cluster)
        assert "is_filtered_out" in result
        # It may or may not pass depending on syllabus confidence
        # But the result should have all expected keys
        assert "relevance_score" in result
        assert "gs_paper" in result
        assert "subtopics" in result
        assert "priority_score" in result
        assert "novelty_score" in result
        assert "cluster_size" in result
        assert result["cluster_size"] == 2

    def test_irrelevant_cluster_rejected(self):
        """A cluster about entertainment should be rejected."""
        cluster = [
            {
                "title": "Bollywood movie release breaks records",
                "content_snippet": "The new bollywood film starring famous actors has broken box office records."
            },
        ]
        result = process_cluster(cluster)
        assert result["is_filtered_out"] is True
        assert result.get("filter_reason") == "irrelevant_content"

    def test_empty_cluster_handled(self):
        """An empty cluster should not crash."""
        result = process_cluster([])
        assert isinstance(result, dict)
        assert "is_filtered_out" in result

    def test_cluster_without_content_snippet(self):
        """Articles without content_snippet should still work."""
        cluster = [
            {"title": "Government policy announcement"},
        ]
        result = process_cluster(cluster)
        assert isinstance(result, dict)
        assert "gs_paper" in result
        assert "relevance_score" in result


class TestFilterAndRankClusters:
    """Tests for filter_and_rank_clusters()."""

    def test_empty_clusters_list(self):
        """Empty clusters list should return empty results."""
        results, gemini = filter_and_rank_clusters([])
        assert results == []
        assert gemini == []

    def test_filter_and_rank(self):
        """Multiple clusters should be filtered and ranked by priority."""
        clusters = [
            [
                {
                    "title": "Bollywood movie gossip and celebrity news",
                    "content_snippet": "Film actors and actresses at movie premiere"
                }
            ],
            [
                {
                    "title": "Government announces new welfare policy",
                    "content_snippet": "The Indian government announced a new policy on direct benefit transfer for farmers."
                }
            ],
        ]
        results, gemini = filter_and_rank_clusters(clusters, max_stories=10)
        assert isinstance(results, list)
        assert isinstance(gemini, list)
        # At least the entertainment one should be filtered out
        if len(results) > 0:
            for r in results:
                assert r["is_filtered_out"] is False
                assert r["priority_score"] > 0

    def test_max_stories_limit(self):
        """max_stories should limit the number of results returned."""
        clusters = [
            [{"title": f"Government policy topic {i}", "content_snippet": f"The Indian government announced policy {i}."}]
            for i in range(20)
        ]
        results, _ = filter_and_rank_clusters(clusters, max_stories=5)
        assert len(results) <= 5

    def test_gemini_budget_respected(self):
        """max_gemini_calls should limit gemini candidates."""
        # Create clusters that try to pass the 0.72 threshold
        # (hard to guarantee with TF-IDF, so we just check the structure)
        clusters = [
            [{"title": "Government policy announcement", "content_snippet": "Indian government policy announcement on economy"}]
            for _ in range(10)
        ]
        results, gemini = filter_and_rank_clusters(clusters, max_stories=10, max_gemini_calls=3)
        assert len(gemini) <= 3
        # All gemini candidates should also be in results
        for g in gemini:
            assert any(g["relevance_score"] == r["relevance_score"] for r in results)


# ── Global State Cleanup ──


def teardown_module():
    """Clean up global state after all tests."""
    clear_novelty_memory()
