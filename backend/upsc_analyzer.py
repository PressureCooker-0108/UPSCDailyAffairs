"""
upsc_analyzer.py — Gemini-Powered UPSC Exam Intelligence

SECONDARY intelligence layer. ONLY processes stories that have already been
pre-filtered by upsc_filter.py (relevance_score >= 0.5).

Gemini is ONLY:
  - a structured reasoning layer
  - a formatting layer
  - an exam framing layer

Gemini NEVER:
  - analyzes raw RSS feeds
  - determines primary relevance
  - processes noisy or low-relevance stories

Uses:
  - httpx (REST API, NOT Google SDK)
  - gemini-2.0-flash model
  - temperature = 0.2, maxOutputTokens = 500
"""

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Gemini API configuration
_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_TEMPERATURE = 0.2
_GEMINI_MAX_TOKENS = 500
_GEMINI_TIMEOUT_SECONDS = 30.0

# Threshold — only process stories with relevance >= this
GEMINI_RELEVANCE_THRESHOLD = 0.5


def _get_api_key() -> str | None:
    """Get Gemini API key from environment."""
    return os.environ.get("GEMINI_API_KEY")


def _build_upsc_prompt(
    gs_paper: str,
    subtopics: list[str],
    matched_criteria: int,
    headline: str,
    summary: str,
    why_it_matters: str,
) -> str:
    """Build the structured prompt for Gemini exam analysis.

    The prompt tells Gemini that a syllabus-aware ML engine has already
    classified the article — Gemini's only job is structured formatting
    and exam intelligence generation.
    """
    subtopics_str = ", ".join(subtopics) if subtopics else "General"

    prompt = f"""You are a UPSC current affairs analyst.

A syllabus-aware ML engine has already classified this article.

Use the provided classification and generate structured UPSC exam intelligence.

Return ONLY valid JSON.

OUTPUT SCHEMA:
{{
  "is_relevant": boolean,
  "relevance_score": float,
  "gs_paper": string,
  "subtopics": [string],
  "prelims_angle": string,
  "mains_angle": string,
  "probable_question": string,
  "static_connect": string,
  "key_terms": [string],
  "one_line_takeaway": string
}}

RULES:
- Be concise
- Use UPSC terminology
- Focus on analytical importance
- Avoid generic commentary
- Mention exact syllabus connections

PRE-CLASSIFIED DATA:
GS Paper: {gs_paper}
Subtopics: {subtopics_str}
Matched Criteria: {matched_criteria}

ARTICLE:
Headline: {headline}
Summary: {summary}
Why it matters: {why_it_matters}
"""
    return prompt


def _parse_gemini_response(response_text: str) -> dict[str, Any] | None:
    """Parse the Gemini API response, extracting the structured JSON.

    Handles markdown code fences and partial JSON extraction.
    """
    text = response_text.strip()

    # Try to extract JSON from markdown code fences
    if "```json" in text:
        json_start = text.index("```json") + 7
        json_end = text.index("```", json_start) if "```" in text[json_start:] else len(text)
        text = text[json_start:json_end].strip()
    elif "```" in text:
        # Try generic code fence
        json_start = text.index("```") + 3
        json_end = text.index("```", json_start) if "```" in text[json_start:] else len(text)
        text = text[json_start:json_end].strip()

    # Parse JSON
    try:
        result = json.loads(text)
        # Validate required fields
        required_fields = ["prelims_angle", "mains_angle", "probable_question",
                           "static_connect", "key_terms", "one_line_takeaway"]
        for field in required_fields:
            if field not in result:
                result[field] = result.get(field, "")

        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        logger.debug(f"Raw response: {response_text[:500]}")
        return None


def generate_exam_playbook(
    headline: str,
    summary: str,
    why_it_matters: str,
    gs_paper: str = "",
    subtopics: list[str] | None = None,
    matched_criteria: int = 0,
    relevance_score: float = 0.0,
) -> dict[str, Any] | None:
    """Generate a structured UPSC exam playbook for a pre-filtered story.

    Args:
      headline: Story headline / title
      summary: Extractive summary of the story
      why_it_matters: Context about why the story matters
      gs_paper: Pre-classified GS paper (from upsc_filter)
      subtopics: Pre-classified subtopics (from upsc_filter)
      matched_criteria: Number of relevance criteria matched
      relevance_score: UPSC relevance score (from upsc_filter)

    Returns:
      Structured exam playbook dict, or None if:
        - API key is missing
        - Relevance is below threshold
        - API call fails
        - Response parsing fails
    """
    # Hard requirement: pre-filtered high-relevance stories only
    if relevance_score < GEMINI_RELEVANCE_THRESHOLD:
        return None

    api_key = _get_api_key()
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping Gemini analysis")
        return None

    subtopics = subtopics or []

    prompt = _build_upsc_prompt(
        gs_paper=gs_paper,
        subtopics=subtopics,
        matched_criteria=matched_criteria,
        headline=headline,
        summary=summary,
        why_it_matters=why_it_matters,
    )

    url = f"{_GEMINI_BASE_URL}/{_GEMINI_MODEL}:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": _GEMINI_TEMPERATURE,
            "maxOutputTokens": _GEMINI_MAX_TOKENS,
        },
    }

    try:
        with httpx.Client(timeout=_GEMINI_TIMEOUT_SECONDS) as client:
            response = client.post(url, json=payload)

        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code} - {response.text[:200]}")
            return None

        data = response.json()

        # Extract text from Gemini response
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("Gemini returned no candidates")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            logger.warning("Gemini returned no content parts")
            return None

        response_text = parts[0].get("text", "")

        # Parse structured JSON
        playbook = _parse_gemini_response(response_text)
        if playbook is None:
            return None

        # Override with our pre-computed values
        playbook["gs_paper"] = gs_paper or playbook.get("gs_paper", "Unknown")
        playbook["subtopics"] = subtopics or playbook.get("subtopics", [])
        playbook["relevance_score"] = relevance_score

        logger.info(
            f"Generated exam playbook for: {headline[:60]}... "
            f"(GS: {gs_paper}, prelims: {str(playbook.get('prelims_angle', ''))[:40]}...)"
        )

        return playbook

    except httpx.TimeoutException:
        logger.error("Gemini API request timed out")
        return None
    except httpx.RequestError as e:
        logger.error(f"Gemini API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in Gemini analysis: {e}")
        return None
