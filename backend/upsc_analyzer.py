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
AI_RELEVANCE_THRESHOLD = 0.65

_ai_state: dict[str, Any] = {
    "last_request_at": 0.0,
    "budget_exhausted": False,
    "run_cap": None,
    "daily_cap_assumed": None,
    "ai_calls_used": 0,
    "last_result": "not_started",
    "key_info": None,
    "is_free_tier": None,
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


def _load_api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY")


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

Rules:
- Be concise
- Use UPSC terminology
- Focus on analytical importance
- Avoid generic commentary
- Mention exact syllabus connections
- Do not wrap the JSON in markdown unless absolutely necessary"""


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
    api_key = api_key or _load_api_key()
    if not api_key:
        return None

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


def _initialize_run_budget(api_key: str | None = None) -> dict[str, Any]:
    """Initialize run-level AI budget state from OpenRouter key metadata."""
    api_key = api_key or _load_api_key()
    if not api_key:
        _ai_state["run_cap"] = 0
        _ai_state["daily_cap_assumed"] = 0
        _ai_state["is_free_tier"] = None
        _ai_state["key_info"] = None
        _set_last_result("no_key")
        return get_ai_runtime_status()

    key_info = fetch_openrouter_key_info(api_key)
    is_free_tier = True
    if key_info and isinstance(key_info.get("data"), dict):
        is_free_tier = bool(key_info["data"].get("is_free_tier", True))

    daily_cap_assumed = _free_tier_daily_cap() if is_free_tier else _paid_free_model_daily_cap()
    run_cap = min(_free_tier_run_cap(), daily_cap_assumed) if is_free_tier else daily_cap_assumed

    _ai_state["key_info"] = key_info
    _ai_state["is_free_tier"] = is_free_tier
    _ai_state["daily_cap_assumed"] = daily_cap_assumed
    _ai_state["run_cap"] = max(0, int(run_cap))
    return get_ai_runtime_status()


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
    })


def prepare_ai_run() -> dict[str, Any]:
    """Reset state and prepare a conservative request budget for this run."""
    _reset_ai_state()
    return _initialize_run_budget()


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
    }


def probe_openrouter(api_key: str | None = None) -> dict[str, Any]:
    """Run a tiny OpenRouter health check and return key metadata when possible."""
    api_key = api_key or _load_api_key()
    if not api_key:
        return {"status": "error", "message": "No OPENROUTER_API_KEY found in environment"}

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
            return {
                "status": "error",
                "model": OPENROUTER_MODEL,
                "key_info": key_info,
                "code": response.status_code,
                "detail": response.text[:300],
            }

        data = response.json()
        text = _extract_chat_response_text(data)
        if not text:
            return {
                "status": "error",
                "model": OPENROUTER_MODEL,
                "key_info": key_info,
                "detail": "No content in response",
            }

        return {
            "status": "ok",
            "model": OPENROUTER_MODEL,
            "response": text,
            "key_info": key_info,
        }
    except Exception as e:
        return {
            "status": "error",
            "model": OPENROUTER_MODEL,
            "key_info": key_info,
            "detail": str(e),
        }


def generate_exam_playbook(
    headline: str,
    summary: str,
    why_it_matters: str,
    gs_paper: str = "",
    subtopics: list[str] | None = None,
    matched_criteria: int = 0,
    relevance_score: float = 0.0,
) -> dict[str, Any] | None:
    """Generate a structured UPSC exam playbook for a pre-filtered story."""
    if relevance_score < AI_RELEVANCE_THRESHOLD:
        _set_last_result("below_threshold")
        return None

    api_key = _load_api_key()
    if not api_key:
        logger.warning("[AI] No OPENROUTER_API_KEY set - skipping AI analysis")
        _set_last_result("no_key")
        return None

    if _ai_state.get("run_cap") is None:
        _initialize_run_budget(api_key)

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

            _ai_state["ai_calls_used"] = int(_ai_state.get("ai_calls_used", 0)) + 1
            _set_last_result("success")
            logger.info(
                f"[AI] Generated exam playbook for: {headline[:60]}... "
                f"(model: {OPENROUTER_MODEL}, GS: {gs_paper})"
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
