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

import itertools
import json
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Gemini API configuration
_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash-lite"]
_GEMINI_RETRY_DELAY = 3.0  # seconds to wait before retrying a 429'd model
_GEMINI_FALLBACK_DELAY = 1.0  # seconds to wait before trying the next fallback
_GEMINI_MAX_RETRIES = 2  # max retries per model on 429
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_TEMPERATURE = 0.2
_GEMINI_MAX_TOKENS = 500
_GEMINI_TIMEOUT_SECONDS = 30.0

# Threshold — only process stories with relevance >= this
GEMINI_RELEVANCE_THRESHOLD = 0.5


# Module-level round-robin key state
_api_key_cycle: itertools.cycle | None = None


def _load_api_keys() -> list[str]:
    """Load all Gemini API keys from environment variables.

    Resolution order:
      1. GEMINI_API_KEY (your existing/primary key)
      2. GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... (additional keys)

    GEMINI_API_KEY is always checked first so existing users don't
    need to rename their env var when adding extra keys.
    Numbered keys do NOT need to be sequential — _2 and _3 will be
    picked up even if _1 is missing.
    """
    keys = []

    # Always include GEMINI_API_KEY first (if set)
    primary = os.environ.get("GEMINI_API_KEY")
    if primary:
        keys.append(primary)

    # Scan numbered keys — no gap requirement, up to 20
    for i in range(1, 21):
        key = os.environ.get(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key)

    return keys


def _get_next_key() -> str | None:
    """Get the next API key via round-robin across all configured keys."""
    global _api_key_cycle
    if _api_key_cycle is None:
        all_keys = _load_api_keys()
        if not all_keys:
            return None
        _api_key_cycle = itertools.cycle(all_keys)
        if len(all_keys) > 1:
            logger.info(f"Loaded {len(all_keys)} Gemini API keys, using round-robin rotation")
    return next(_api_key_cycle)  # type: ignore[arg-type]


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

    api_key = _get_next_key()
    if not api_key:
        logger.warning("No GEMINI_API_KEY set — skipping Gemini analysis")
        return None

    subtopics = subtopics or []

    try:
        prompt = _build_upsc_prompt(
            gs_paper=gs_paper,
            subtopics=subtopics,
            matched_criteria=matched_criteria,
            headline=headline,
            summary=summary,
            why_it_matters=why_it_matters,
        )

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": _GEMINI_TEMPERATURE,
                "maxOutputTokens": _GEMINI_MAX_TOKENS,
            },
        }

        models_to_try = [_GEMINI_MODEL] + _GEMINI_FALLBACK_MODELS
        last_error = None
        model_used = None

        for model in models_to_try:
            url = f"{_GEMINI_BASE_URL}/{model}:generateContent?key={api_key}"

            retries = 0
            while retries <= _GEMINI_MAX_RETRIES:
                if retries > 0:
                    logger.warning(
                        f"[GEMINI] Retrying {model} "
                        f"(attempt {retries + 1}/{_GEMINI_MAX_RETRIES + 1})..."
                    )

                try:
                    with httpx.Client(timeout=_GEMINI_TIMEOUT_SECONDS) as client:
                        response = client.post(url, json=payload)

                    if response.status_code == 429:
                        # Rate limited — wait and retry same model
                        last_error = f"429 - {response.text[:200]}"
                        retries += 1
                        if retries <= _GEMINI_MAX_RETRIES:
                            logger.warning(
                                f"[GEMINI] Model {model} rate limited, "
                                f"sleeping {_GEMINI_RETRY_DELAY}s before retry..."
                            )
                            time.sleep(_GEMINI_RETRY_DELAY)
                            continue
                        else:
                            break

                    if response.status_code != 200:
                        last_error = f"{response.status_code} - {response.text[:200]}"
                        break  # Non-retryable error, try next model

                    try:
                        data = response.json()
                    except Exception as e:
                        last_error = f"invalid JSON: {e}"
                        break

                    # Extract text from Gemini response
                    candidates = data.get("candidates", [])
                    if not candidates:
                        last_error = "no candidates"
                        break

                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        last_error = "no content parts"
                        break

                    response_text = parts[0].get("text", "")
                    model_used = model
                    break  # Success!

                except httpx.TimeoutException:
                    last_error = "timeout"
                    break
                except httpx.RequestError as e:
                    last_error = str(e)
                    break
                except Exception as e:
                    last_error = str(e)
                    break

            # If model succeeded, exit the outer loop
            if model_used is not None:
                break

            # Log failure and wait before trying next model
            if model != models_to_try[-1]:
                logger.warning(
                    f"[GEMINI] Model {model} failed, "
                    f"trying next in {_GEMINI_FALLBACK_DELAY}s..."
                )
                time.sleep(_GEMINI_FALLBACK_DELAY)

        if model_used is None:
            logger.error(f"[GEMINI] All models failed. Last error: {last_error}")
            return None

        # Parse structured JSON
        playbook = _parse_gemini_response(response_text)
        if playbook is None:
            return None

        # Override with our pre-computed values
        playbook["gs_paper"] = gs_paper or playbook.get("gs_paper", "Unknown")
        playbook["subtopics"] = subtopics or playbook.get("subtopics", [])
        playbook["relevance_score"] = relevance_score

        if model_used != _GEMINI_MODEL:
            logger.warning(f"[GEMINI] Used fallback model {model_used} for: {headline[:60]}...")

        logger.info(
            f"Generated exam playbook for: {headline[:60]}... "
            f"(model: {model_used}, GS: {gs_paper})"
        )

        return playbook

    except Exception as e:
        logger.error(f"[GEMINI] Unexpected error generating playbook for '{headline[:60]}...': {e}")
        return None
