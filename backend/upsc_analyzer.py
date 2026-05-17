"""
upsc_analyzer.py - OpenRouter-powered UPSC exam intelligence.

This is a SECONDARY intelligence layer. It only processes stories that have
already been pre-filtered by upsc_filter.py.

OpenRouter/Owl Alpha is ONLY:
  - a structured reasoning layer
  - a formatting layer
  - an exam framing layer

It NEVER:
  - analyzes raw RSS feeds
  - determines primary relevance
  - processes noisy or low-relevance stories
"""

import json
import os
import time
from typing import Any

import httpx
from loguru import logger


OPENROUTER_MODEL = "openrouter/owl-alpha"
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_TIMEOUT_SECONDS = 30.0
OPENROUTER_DEFAULT_TEMPERATURE = 0.2
OPENROUTER_DEFAULT_MAX_TOKENS = 700
OPENROUTER_DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 3.5
OPENROUTER_DEFAULT_MAX_RETRIES = 2
OPENROUTER_DEFAULT_FREE_TIER_RUN_CAP = 20
OPENROUTER_DEFAULT_FREE_TIER_DAILY_CAP = 50
OPENROUTER_DEFAULT_PAID_FREE_MODEL_DAILY_CAP = 1000
OPENROUTER_RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
AI_RELEVANCE_THRESHOLD = 0.50

_ai_state: dict[str, Any] = {
    "last_request_at": 0.0,
    "budget_exhausted": False,
    "run_cap": None,
    "daily_cap_assumed": None,
    "ai_calls_used": 0,
    "last_result": "not_started",
    "key_info": None,
    "is_free_tier": None,
    "api_keys": [],
    "key_index": 0,
    "key_usage": {},        # key_used_hash → call_count
    "review_calls_used": 0,
    "review_failures": 0,
}


def _get_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning(f"[AI] Invalid float for {name}: {value!r}; using default {default}")
        return default


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(f"[AI] Invalid int for {name}: {value!r}; using default {default}")
        return default


def _base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL).rstrip("/")


def _timeout_seconds() -> float:
    return _get_float_env("AI_TIMEOUT_SECONDS", OPENROUTER_DEFAULT_TIMEOUT_SECONDS)


def _temperature() -> float:
    return _get_float_env("AI_TEMPERATURE", OPENROUTER_DEFAULT_TEMPERATURE)


def _max_completion_tokens() -> int:
    return _get_int_env("AI_MAX_COMPLETION_TOKENS", OPENROUTER_DEFAULT_MAX_TOKENS)


def _min_request_interval_seconds() -> float:
    return _get_float_env(
        "AI_MIN_REQUEST_INTERVAL_SECONDS",
        OPENROUTER_DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
    )


def _max_retries() -> int:
    return _get_int_env("AI_MAX_RETRIES", OPENROUTER_DEFAULT_MAX_RETRIES)


def _free_tier_run_cap() -> int:
    return _get_int_env("AI_FREE_TIER_RUN_CAP", OPENROUTER_DEFAULT_FREE_TIER_RUN_CAP)


def _free_tier_daily_cap() -> int:
    return _get_int_env("AI_FREE_TIER_DAILY_CAP", OPENROUTER_DEFAULT_FREE_TIER_DAILY_CAP)


def _paid_free_model_daily_cap() -> int:
    return _get_int_env(
        "AI_PAID_FREE_MODEL_DAILY_CAP",
        OPENROUTER_DEFAULT_PAID_FREE_MODEL_DAILY_CAP,
    )


def _load_api_keys() -> list[str]:
    """Load all available OpenRouter API keys.

    Reads OPENROUTER_API_KEYS (comma-separated list) first, then
    falls back to OPENROUTER_API_KEY for backward compatibility.
    Returns an empty list if no keys are found.
    """
    keys_str = os.environ.get("OPENROUTER_API_KEYS")
    if keys_str:
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if keys:
            return keys
    single = os.environ.get("OPENROUTER_API_KEY")
    if single:
        return [single]
    return []


def _get_next_api_key() -> str | None:
    """Return the next API key in round-robin order."""
    keys = _ai_state.get("api_keys", [])
    if not keys:
        return None
    idx = _ai_state.get("key_index", 0) % len(keys)
    _ai_state["key_index"] = idx + 1
    return keys[idx]


def _build_headers(api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    referer = os.environ.get("OPENROUTER_HTTP_REFERER")
    app_name = os.environ.get("OPENROUTER_APP_NAME")
    if referer:
        headers["HTTP-Referer"] = referer
    if app_name:
        headers["X-Title"] = app_name
    return headers


def _set_last_result(result: str) -> None:
    _ai_state["last_result"] = result


def _mark_budget_exhausted(result: str) -> None:
    _ai_state["budget_exhausted"] = True
    _set_last_result(result)


def _should_skip_for_budget() -> bool:
    run_cap = _ai_state.get("run_cap")
    if _ai_state.get("budget_exhausted"):
        _set_last_result("skipped_budget")
        return True
    if isinstance(run_cap, int) and _ai_state.get("ai_calls_used", 0) >= run_cap:
        _mark_budget_exhausted("skipped_budget")
        return True
    return False


def _wait_for_request_slot() -> None:
    min_interval = _min_request_interval_seconds()
    if min_interval <= 0:
        return

    now = time.monotonic()
    last_request_at = float(_ai_state.get("last_request_at") or 0.0)
    elapsed = now - last_request_at
    if last_request_at > 0 and elapsed < min_interval:
        sleep_for = min_interval - elapsed
        logger.info(f"[AI] Pacing OpenRouter requests; sleeping {sleep_for:.2f}s")
        time.sleep(sleep_for)

    _ai_state["last_request_at"] = time.monotonic()


def _parse_retry_after(response: httpx.Response) -> float | None:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        seconds = float(retry_after)
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return seconds


def _build_system_prompt() -> str:
    return """You are a UPSC current affairs analyst.

Return ONLY valid JSON that matches this schema:
{
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
}

CRITICAL RULES FOR one_line_takeaway:
- MUST be specific to THIS article's content — NOT generic
- MUST be different from the "Why it matters" field provided
- Do NOT use templates like "This development is significant for UPSC preparation"
- Do NOT reuse or rephrase the input "Why it matters" — generate NEW insight
- Do NOT say "reflects ongoing trends" without specifying WHICH trends
- Focus on the CONCRETE exam angle: "How would UPSC test THIS specific story?"
- Maximum 15 words
- Use UPSC terminology
- Mention exact syllabus connections when possible
- Examples of GOOD: "RBI repo rate hike tests monetary policy knowledge", "PM Modi bilateral visit signals India-Sweden strategic partnership"
- Examples of BAD: "This is significant for UPSC", "reflects ongoing trends", "important for preparation"

Do not wrap the JSON in markdown."""


def _build_upsc_prompt(
    gs_paper: str,
    subtopics: list[str],
    matched_criteria: int,
    headline: str,
    summary: str,
    why_it_matters: str,
) -> str:
    """Build the structured user prompt for UPSC exam analysis."""
    subtopics_str = ", ".join(subtopics) if subtopics else "General"

    return f"""A syllabus-aware ML engine has already classified this article.

Use the provided classification and generate structured UPSC exam intelligence.

PRE-CLASSIFIED DATA:
GS Paper: {gs_paper}
Subtopics: {subtopics_str}
Matched Criteria: {matched_criteria}

ARTICLE:
Headline: {headline}
Summary: {summary}
Why it matters: {why_it_matters}
"""


def _parse_ai_response(response_text: str) -> dict[str, Any] | None:
    """Parse model output, accepting raw JSON or fenced JSON."""
    text = response_text.strip()

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

    if not text.startswith("{"):
        brace_start = text.find("{")
        if brace_start != -1:
            text = text[brace_start:]
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[: i + 1]
                    break

    try:
        result = json.loads(text)
        required_fields = [
            "prelims_angle",
            "mains_angle",
            "probable_question",
            "static_connect",
            "key_terms",
            "one_line_takeaway",
        ]
        for field in required_fields:
            if field not in result or result[field] is None:
                result[field] = ""
        if not isinstance(result.get("key_terms"), list):
            result["key_terms"] = []
        return result
    except json.JSONDecodeError as e:
        logger.error(f"[AI] Failed to parse response as JSON: {e}")
        logger.debug(f"[AI] Raw response (first 500 chars): {response_text[:500]}")
        _set_last_result("parse_error")
        return None


def _extract_chat_response_text(data: dict[str, Any]) -> str | None:
    choices = data.get("choices", [])
    if not choices:
        return None

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        joined = "".join(parts).strip()
        return joined or None
    return None


def fetch_openrouter_key_info(api_key: str | None = None) -> dict[str, Any] | None:
    """Fetch OpenRouter key metadata for budgeting and diagnostics."""
    if not api_key:
        keys = _ai_state.get("api_keys", []) or _load_api_keys()
        if not keys:
            return None
        api_key = keys[0]  # Use first key for budget metadata

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{_base_url()}/key",
                headers=_build_headers(api_key),
            )
        if response.status_code != 200:
            logger.warning(
                f"[AI] Failed to fetch OpenRouter key info: {response.status_code} {response.text[:200]}"
            )
            return None
        return response.json()
    except Exception as e:
        logger.warning(f"[AI] Failed to fetch OpenRouter key info: {e}")
        return None





def _reset_ai_state() -> None:
    """Reset run-level AI state before each pipeline execution."""
    _ai_state.update({
        "last_request_at": 0.0,
        "budget_exhausted": False,
        "run_cap": None,
        "daily_cap_assumed": None,
        "ai_calls_used": 0,
        "last_result": "not_started",
        "key_info": None,
        "is_free_tier": None,
        "api_keys": [],
        "key_index": 0,
        "key_usage": {},
        "review_calls_used": 0,
        "review_failures": 0,
    })


def prepare_ai_run() -> dict[str, Any]:
    """Reset state and prepare a conservative request budget for this run.

    Loads all available API keys (round-robin pool) and checks each one's
    metadata for accurate budgeting. Total daily cap = num_keys * per_key_cap.
    """
    _reset_ai_state()
    keys = _load_api_keys()
    _ai_state["api_keys"] = keys
    _ai_state["key_count"] = len(keys)

    if not keys:
        logger.warning("[AI] No OPENROUTER_API_KEY(S) set — AI analysis disabled")
        _ai_state["run_cap"] = 0
        _ai_state["daily_cap_assumed"] = 0
        _ai_state["is_free_tier"] = None
        _set_last_result("no_key")
        return get_ai_runtime_status()

    # Check the first key's metadata for free-tier detection
    first_key_info = fetch_openrouter_key_info(keys[0])
    is_free_tier = True
    if first_key_info and isinstance(first_key_info.get("data"), dict):
        is_free_tier = bool(first_key_info["data"].get("is_free_tier", True))

    per_key_daily = _free_tier_daily_cap() if is_free_tier else _paid_free_model_daily_cap()
    total_daily = per_key_daily * len(keys)
    per_key_run = _free_tier_run_cap() if is_free_tier else per_key_daily
    total_run_cap = per_key_run * len(keys)

    _ai_state["key_info"] = first_key_info
    _ai_state["is_free_tier"] = is_free_tier
    _ai_state["daily_cap_assumed"] = total_daily
    _ai_state["run_cap"] = max(0, int(total_run_cap))
    _ai_state["per_key_daily_cap"] = per_key_daily

    logger.info(
        f"[AI] Budget: {len(keys)} key(s), free_tier={is_free_tier}, "
        f"per_key_daily={per_key_daily}, total_run_cap={total_run_cap}, "
        f"total_daily={total_daily}"
    )

    return get_ai_runtime_status()


def get_ai_runtime_status() -> dict[str, Any]:
    """Expose current AI runtime state for scheduler and diagnostics."""
    return {
        "model": OPENROUTER_MODEL,
        "base_url": _base_url(),
        "budget_exhausted": bool(_ai_state.get("budget_exhausted")),
        "run_cap": _ai_state.get("run_cap"),
        "daily_cap_assumed": _ai_state.get("daily_cap_assumed"),
        "ai_calls_used": int(_ai_state.get("ai_calls_used", 0)),
        "last_result": _ai_state.get("last_result"),
        "is_free_tier": _ai_state.get("is_free_tier"),
        "has_key_info": _ai_state.get("key_info") is not None,
        "key_info": _ai_state.get("key_info"),
        "key_count": len(_ai_state.get("api_keys", [])),
        "key_index": int(_ai_state.get("key_index", 0)),
        "key_usage": dict(_ai_state.get("key_usage", {})),
        "review_calls_used": int(_ai_state.get("review_calls_used", 0)),
        "review_failures": int(_ai_state.get("review_failures", 0)),
    }


def probe_openrouter(api_key: str | None = None) -> dict[str, Any]:
    """Run a tiny OpenRouter health check against all available keys.

    Returns a summary showing how many keys are reachable vs failing.
    """
    if api_key:
        # Single-key mode for backward compatibility
        return _probe_single_key(api_key)

    keys = _ai_state.get("api_keys", []) or _load_api_keys()
    if not keys:
        return {"status": "error", "message": "No OpenRouter API keys found"}

    results = []
    for i, key in enumerate(keys):
        result = _probe_single_key(key)
        masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "invalid"
        results.append({"key_index": i, "key_masked": masked, "status": result["status"]})

    ok_count = sum(1 for r in results if r["status"] == "ok")
    error_count = len(results) - ok_count

    return {
        "status": "ok" if ok_count > 0 else "error",
        "total_keys": len(keys),
        "reachable": ok_count,
        "failing": error_count,
        "key_results": results,
    }


def _probe_single_key(api_key: str) -> dict[str, Any]:
    """Health-check a single OpenRouter key."""
    key_info = fetch_openrouter_key_info(api_key)
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Reply with exactly: OK"},
            {"role": "user", "content": "Ping"},
        ],
        "temperature": 0.0,
        "max_tokens": 10,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{_base_url()}/chat/completions",
                headers=_build_headers(api_key),
                json=payload,
            )
        if response.status_code != 200:
            return {"status": "error", "code": response.status_code, "detail": response.text[:200]}
        data = response.json()
        text = _extract_chat_response_text(data)
        return {"status": "ok" if text else "error", "response": text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


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

    Uses round-robin API key rotation across all available OpenRouter keys.
    Budget is tracked across the entire run, not per-key.
    """
    if relevance_score < AI_RELEVANCE_THRESHOLD:
        _set_last_result("below_threshold")
        return None

    api_key = _get_next_api_key()
    if not api_key:
        logger.warning("[AI] No OpenRouter API keys available - skipping AI analysis")
        _set_last_result("no_key")
        return None

    if _ai_state.get("run_cap") is None:
        # Budget not initialized — happens if prepare_ai_run() wasn't called
        prepare_ai_run()
        api_key = _get_next_api_key() or api_key

    if _should_skip_for_budget():
        logger.warning("[AI] Run budget exhausted - skipping remaining AI calls")
        return None

    subtopics = subtopics or []

    headline = headline.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()
    summary = summary.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()
    why_it_matters = why_it_matters.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt()},
            {
                "role": "user",
                "content": _build_upsc_prompt(
                    gs_paper=gs_paper,
                    subtopics=subtopics,
                    matched_criteria=matched_criteria,
                    headline=headline,
                    summary=summary,
                    why_it_matters=why_it_matters,
                ),
            },
        ],
        "temperature": _temperature(),
        "max_tokens": _max_completion_tokens(),
    }

    last_error = None
    for attempt in range(_max_retries() + 1):
        try:
            _wait_for_request_slot()
            with httpx.Client(timeout=_timeout_seconds()) as client:
                response = client.post(
                    f"{_base_url()}/chat/completions",
                    headers=_build_headers(api_key),
                    json=payload,
                )

            if response.status_code in {429, 503}:
                last_error = f"{response.status_code} - {response.text[:200]}"
                retry_after = _parse_retry_after(response)
                if attempt >= _max_retries():
                    _mark_budget_exhausted("rate_limited")
                    logger.warning(
                        f"[AI] OpenRouter rate limit persisted after retries; "
                        f"budget exhausted for this run ({last_error})"
                    )
                    return None
                backoff = retry_after if retry_after is not None else min(20.0, 4.0 * (2 ** attempt))
                logger.warning(
                    f"[AI] OpenRouter returned {response.status_code}; "
                    f"retrying in {backoff:.1f}s (attempt {attempt + 1}/{_max_retries() + 1})"
                )
                time.sleep(backoff)
                continue

            if response.status_code in {502, 504}:
                last_error = f"{response.status_code} - {response.text[:200]}"
                if attempt >= _max_retries():
                    _set_last_result("provider_error")
                    logger.error(f"[AI] OpenRouter request failed after retries: {last_error}")
                    return None
                backoff = min(20.0, 4.0 * (2 ** attempt))
                logger.warning(
                    f"[AI] Provider transient error {response.status_code}; "
                    f"retrying in {backoff:.1f}s (attempt {attempt + 1}/{_max_retries() + 1})"
                )
                time.sleep(backoff)
                continue

            if response.status_code == 401:
                _set_last_result("auth_error")
                logger.error("[AI] OpenRouter rejected the API key (401)")
                return None

            if response.status_code == 402:
                _mark_budget_exhausted("credits_error")
                logger.error("[AI] OpenRouter account has insufficient credits or negative balance (402)")
                return None

            if response.status_code != 200:
                _set_last_result("response_error")
                logger.error(f"[AI] OpenRouter request failed: {response.status_code} {response.text[:200]}")
                return None

            try:
                data = response.json()
            except Exception as e:
                _set_last_result("response_error")
                logger.error(f"[AI] OpenRouter returned invalid JSON: {e}")
                return None

            response_text = _extract_chat_response_text(data)
            if not response_text:
                _set_last_result("response_error")
                logger.error("[AI] OpenRouter returned no message content")
                return None

            playbook = _parse_ai_response(response_text)
            if playbook is None:
                return None

            playbook["gs_paper"] = gs_paper or playbook.get("gs_paper", "Unknown")
            playbook["subtopics"] = subtopics or playbook.get("subtopics", [])
            playbook["relevance_score"] = relevance_score

            # Track per-key usage
            key_short = api_key[:8] + "..." if len(api_key) > 8 else "invalid"
            usage = _ai_state.setdefault("key_usage", {})
            usage[key_short] = usage.get(key_short, 0) + 1

            _ai_state["ai_calls_used"] = int(_ai_state.get("ai_calls_used", 0)) + 1
            _set_last_result("success")
            logger.info(
                f"[AI] Generated exam playbook for: {headline[:60]}... "
                f"(model: {OPENROUTER_MODEL}, GS: {gs_paper}, key={key_short})"
            )
            return playbook

        except httpx.TimeoutException:
            last_error = "timeout"
            if attempt >= _max_retries():
                _set_last_result("request_error")
                logger.error("[AI] OpenRouter request timed out after retries")
                return None
            backoff = min(20.0, 4.0 * (2 ** attempt))
            logger.warning(
                f"[AI] OpenRouter request timed out; retrying in {backoff:.1f}s "
                f"(attempt {attempt + 1}/{_max_retries() + 1})"
            )
            time.sleep(backoff)
        except httpx.RequestError as e:
            last_error = str(e)
            if attempt >= _max_retries():
                _set_last_result("request_error")
                logger.error(f"[AI] OpenRouter network error after retries: {e}")
                return None
            backoff = min(20.0, 4.0 * (2 ** attempt))
            logger.warning(
                f"[AI] OpenRouter request error; retrying in {backoff:.1f}s "
                f"(attempt {attempt + 1}/{_max_retries() + 1})"
            )
            time.sleep(backoff)
        except Exception as e:
            _set_last_result("request_error")
            logger.error(f"[AI] Unexpected error generating playbook for '{headline[:60]}...': {e}")
            return None

    _set_last_result("request_error")
    logger.error(f"[AI] OpenRouter request failed. Last error: {last_error}")
    return None


# ──────────────────────────────────────────────
#  AI Review Verdict
# ──────────────────────────────────────────────

def _build_review_system_prompt() -> str:
    """System prompt for the AI review verdict.

    This is a lightweight classification call, NOT a full playbook.
    It validates whether a story genuinely belongs in UPSC prep.
    """
    return """You are a strict UPSC content reviewer. Your job is to validate whether a news article genuinely belongs in a UPSC current affairs prep app.

Return ONLY valid JSON matching this schema:
{
  "verdict": "PASS" | "FLAG" | "REJECT",
  "confidence": "high" | "medium" | "low",
  "reasoning": "Brief explanation for your verdict",
  "suggested_gs_paper": string | null,
  "issues": [string]
}

VERDICT RULES:
- PASS: The article is clearly UPSC-relevant (governance, policy, economy, IR, environment, etc.)
- FLAG: The article has some relevance but seems tangential, or the connection to UPSC is weak
- REJECT: The article does NOT belong (entertainment, sports, celebrity, corporate earnings, local crime, etc.)

CONFIDENCE RULES:
- high: You're very sure about the verdict
- medium: You're somewhat sure
- low: The article is ambiguous and could go either way

Be strict but fair. If an article genuinely connects to the UPSC syllabus, it should PASS.
Do not wrap the JSON in markdown."""


def _build_review_prompt(
    headline: str,
    full_text: str,
    gs_paper: str,
    subtopics: list[str],
    why_it_matters: str,
) -> str:
    """Build the user prompt for the AI review verdict."""
    subtopics_str = ", ".join(subtopics) if subtopics else "None assigned"
    return f"""Review this article for UPSC relevance.

HEADLINE: {headline}

FULL TEXT:
{full_text[:1500]}

PRE-CLASSIFIED BY TF-IDF SYLLABUS ENGINE:
GS Paper: {gs_paper}
Subtopics: {subtopics_str}
Why It Matters: {why_it_matters}

Give your verdict on whether this belongs in a UPSC current affairs app."""


def _parse_review_response(response_text: str) -> dict[str, Any] | None:
    """Parse the AI review verdict JSON response."""
    text = response_text.strip()

    # Handle fenced JSON
    if "```json" in text:
        json_start = text.index("```json") + 7
        rest = text[json_start:]
        json_end = rest.index("```") if "```" in rest else len(rest)
        text = rest[:json_end].strip()
    elif "```" in text and "{" in text:
        json_start = text.index("```") + 3
        rest = text[json_start:]
        json_end = rest.index("```") if "```" in rest else len(rest)
        text = rest[:json_end].strip()

    if not text.startswith("{"):
        brace_start = text.find("{")
        if brace_start != -1:
            text = text[brace_start:]
        depth = 0
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[: i + 1]
                    break

    try:
        result = json.loads(text)
        verdict = result.get("verdict", "FLAG")
        if verdict not in ("PASS", "FLAG", "REJECT"):
            verdict = "FLAG"
        return {
            "verdict": verdict,
            "confidence": result.get("confidence", "low"),
            "reasoning": result.get("reasoning", ""),
            "suggested_gs_paper": result.get("suggested_gs_paper"),
            "issues": result.get("issues", []),
        }
    except json.JSONDecodeError:
        logger.error(f"[AI Review] Failed to parse response: {response_text[:300]}")
        return None


def generate_review_verdict(
    headline: str,
    full_text: str,
    gs_paper: str = "",
    subtopics: list[str] | None = None,
    why_it_matters: str = "",
) -> dict[str, Any] | None:
    """Generate an AI review verdict for a story.

    This is a lightweight classification call that validates whether
    a story genuinely belongs in UPSC prep. It runs BEFORE the full
    exam playbook generation to save playbook calls on rejected stories.

    Uses round-robin key rotation.

    Returns a dict with:
      - verdict: "PASS" | "FLAG" | "REJECT"
      - confidence: "high" | "medium" | "low"
      - reasoning: str
      - suggested_gs_paper: str | None
      - issues: list[str]
    Returns None if the API call fails.
    """
    api_key = _get_next_api_key()
    if not api_key:
        logger.warning("[AI Review] No API keys available — skipping review")
        return None

    if _should_skip_for_budget():
        logger.warning("[AI Review] Budget exhausted — skipping review")
        return None

    subtopics = subtopics or []

    # Sanitize inputs
    headline = headline.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()[:200]
    full_text = full_text.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()[:1500]
    why_it_matters = why_it_matters.replace("\"", "'").replace("\n", " ").replace("\r", " ").strip()[:300]

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": _build_review_system_prompt()},
            {
                "role": "user",
                "content": _build_review_prompt(
                    headline=headline,
                    full_text=full_text,
                    gs_paper=gs_paper,
                    subtopics=subtopics,
                    why_it_matters=why_it_matters,
                ),
            },
        ],
        "temperature": 0.1,  # Low temperature for consistent classification
        "max_tokens": 300,   # Review needs fewer tokens than playbook
    }

    last_error = None
    for attempt in range(_max_retries() + 1):
        try:
            _wait_for_request_slot()
            with httpx.Client(timeout=_timeout_seconds()) as client:
                response = client.post(
                    f"{_base_url()}/chat/completions",
                    headers=_build_headers(api_key),
                    json=payload,
                )

            if response.status_code in {429, 503}:
                last_error = f"{response.status_code}"
                retry_after = _parse_retry_after(response)
                if attempt >= _max_retries():
                    _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                    logger.warning(f"[AI Review] Rate limit exhausted for this run")
                    return None
                backoff = retry_after if retry_after is not None else min(20.0, 4.0 * (2 ** attempt))
                logger.warning(f"[AI Review] Rate limited; retrying in {backoff:.1f}s")
                time.sleep(backoff)
                continue

            if response.status_code in {502, 504}:
                last_error = f"{response.status_code}"
                if attempt >= _max_retries():
                    _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                    logger.error(f"[AI Review] Provider error after retries: {last_error}")
                    return None
                backoff = min(20.0, 4.0 * (2 ** attempt))
                time.sleep(backoff)
                continue

            if response.status_code in (401, 402):
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                logger.error(f"[AI Review] Key error ({response.status_code}) — skipping")
                return None

            if response.status_code != 200:
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                logger.error(f"[AI Review] Request failed: {response.status_code}")
                return None

            data = response.json()
            response_text = _extract_chat_response_text(data)
            if not response_text:
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                logger.error("[AI Review] Empty response")
                return None

            verdict = _parse_review_response(response_text)
            if verdict is None:
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                return None

            # Track per-key usage
            key_short = api_key[:8] + "..." if len(api_key) > 8 else "invalid"
            usage = _ai_state.setdefault("key_usage", {})
            usage[key_short] = usage.get(key_short, 0) + 1

            _ai_state["review_calls_used"] = int(_ai_state.get("review_calls_used", 0)) + 1
            _ai_state["ai_calls_used"] = int(_ai_state.get("ai_calls_used", 0)) + 1

            logger.info(
                f"[AI Review] {verdict['verdict']} for: {headline[:60]}... "
                f"(confidence={verdict['confidence']}, key={key_short})"
            )
            return verdict

        except httpx.TimeoutException:
            last_error = "timeout"
            if attempt >= _max_retries():
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                logger.error("[AI Review] Timed out after retries")
                return None
            backoff = min(20.0, 4.0 * (2 ** attempt))
            logger.warning(f"[AI Review] Timeout; retrying in {backoff:.1f}s")
            time.sleep(backoff)
        except httpx.RequestError as e:
            last_error = str(e)
            if attempt >= _max_retries():
                _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
                logger.error(f"[AI Review] Network error after retries: {e}")
                return None
            backoff = min(20.0, 4.0 * (2 ** attempt))
            time.sleep(backoff)
        except Exception as e:
            _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
            logger.error(f"[AI Review] Unexpected error: {e}")
            return None

    _ai_state["review_failures"] = int(_ai_state.get("review_failures", 0)) + 1
    logger.error(f"[AI Review] Failed. Last error: {last_error}")
    return None
