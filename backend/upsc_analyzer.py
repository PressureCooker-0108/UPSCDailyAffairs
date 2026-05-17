"""
upsc_analyzer.py — Gemini-Powered UPSC Exam Intelligence

SECONDARY intelligence layer. ONLY processes stories that have already been
pre-filtered by upsc_filter.py (relevance_score >= 0.65).

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
  - gemini-2.0-flash model (primary)
  - gemini-2.0-flash-lite (fallback, same quota pool)
  - gemini-1.5-flash (second fallback, separate quota pool)
  - temperature = 0.2, maxOutputTokens = 1024
"""

import itertools
import json
from loguru import logger
import os
import time
from typing import Any

import httpx


# Gemini API configuration
_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash-lite", "gemini-1.5-flash"]
_GEMINI_FALLBACK_DELAY = 1.0  # seconds to wait before trying the next fallback
# Exponential backoff for 429 retries: 6s, 12s, 24s (3 retries max per model)
_GEMINI_BACKOFF_BASE = 6.0  # starting backoff in seconds
_GEMINI_MAX_RETRIES = 3  # max retries per model on 429
_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1/models"
_GEMINI_TEMPERATURE = 0.2
_GEMINI_MAX_TOKENS = 1024
_GEMINI_TIMEOUT_SECONDS = 30.0

# Threshold — only process stories with relevance >= this
GEMINI_RELEVANCE_THRESHOLD = 0.65


# Module-level round-robin key state
_api_key_cycle: itertools.cycle | None = None
_exhausted_keys: set[str] = set()  # keys that have hit daily quota exhaustion


def _reset_key_state() -> None:
    """Reset all key-related state. Called on each pipeline run to clear
    exhausted-key tracking that might be stale from a previous run."""
    global _api_key_cycle, _exhausted_keys
    _api_key_cycle = None
    _exhausted_keys = set()


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
    """Get the next API key via round-robin across all configured keys.

    Always rebuilds the cycle from currently active (non-exhausted) keys.
    Returns None if ALL keys are exhausted — no point retrying until
    daily quota reset or billing is enabled.
    """
    global _api_key_cycle, _exhausted_keys
    all_keys = _load_api_keys()
    if not all_keys:
        return None

    # Remove exhausted keys from the pool
    active_keys = [k for k in all_keys if k not in _exhausted_keys]
    if not active_keys:
        logger.error("[GEMINI] All API keys have exhausted their daily quota — skipping all Gemini calls")
        return None

    # Rebuild the cycle every time so exhausted keys are excluded immediately
    _api_key_cycle = itertools.cycle(active_keys)
    if len(active_keys) > 1:
        logger.info(f"Loaded {len(active_keys)} Gemini API keys, using round-robin rotation")
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

    Handles various response formats — raw JSON, markdown-wrapped JSON
    (```json ... ```), and orphaned JSON blocks.
    """
    text = response_text.strip()

    # Fallback 1: Extract JSON from ```json ... ``` fences
    if "```json" in text:
        json_start = text.index("```json") + 7
        rest = text[json_start:]
        json_end = rest.index("```") if "```" in rest else len(rest)
        text = rest[:json_end].strip()
    elif "```" in text:
        json_start = text.index("```") + 3
        rest = text[json_start:]
        json_end = rest.index("```") if "```" in rest else len(rest)
        text = rest[:json_end].strip()

    # Fallback 2: Try to find the first { ... } JSON block
    if not text.startswith("{"):
        brace_start = text.find("{")
        if brace_start != -1:
            text = text[brace_start:]
        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[:i+1]
                    break

    # Parse JSON
    try:
        result = json.loads(text)
        # Validate required fields, fill missing with defaults
        required_fields = ["prelims_angle", "mains_angle", "probable_question",
                           "static_connect", "key_terms", "one_line_takeaway"]
        for field in required_fields:
            if field not in result or result[field] is None:
                result[field] = ""
        if "key_terms" in result and not isinstance(result["key_terms"], list):
            result["key_terms"] = []

        return result
    except json.JSONDecodeError as e:
        logger.error(f"[GEMINI] Failed to parse response as JSON: {e}")
        logger.debug(f"[GEMINI] Raw response (first 500 chars): {response_text[:500]}")
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
        # Sanitize user content to prevent unescaped characters breaking JSON output
        headline = headline.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()
        summary = summary.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()
        why_it_matters = why_it_matters.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()

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
                        last_error = f"429 - {response.text[:200]}"
                        # Check if this is quota exhaustion vs rate limiting
                        # Quota exhaustion: "You exceeded your current quota"
                        # Rate limiting: "rate limit" or just 429 without quota message
                        error_body = response.text.lower()
                        is_quota_exhausted = "quota" in error_body or "billing" in error_body

                        if is_quota_exhausted:
                            logger.warning(
                                f"[GEMINI] Key quota exhausted for {model} — "
                                f"marking key as dead for this run"
                            )
                            _exhausted_keys.add(api_key)
                            break  # Don't retry, try next model

                        # Pure rate limiting — exponential backoff: 6s, 12s, 24s
                        retries += 1
                        if retries <= _GEMINI_MAX_RETRIES:
                            backoff = _GEMINI_BACKOFF_BASE * (2 ** (retries - 1))
                            logger.warning(
                                f"[GEMINI] Model {model} rate limited (attempt {retries}/"
                                f"{_GEMINI_MAX_RETRIES}), "
                                f"backing off {backoff}s before retry..."
                            )
                            time.sleep(backoff)
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
