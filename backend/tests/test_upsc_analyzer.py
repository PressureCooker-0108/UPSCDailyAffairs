import json

import upsc_analyzer as analyzer


class FakeResponse:
    def __init__(self, status_code: int, json_data=None, text: str = "", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON payload")
        return self._json_data


class FakeClient:
    def __init__(self, factory):
        self.factory = factory

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        self.factory.get_calls += 1
        if not self.factory.get_responses:
            raise AssertionError(f"Unexpected GET request to {url}")
        return self.factory.get_responses.pop(0)

    def post(self, url, headers=None, json=None):
        self.factory.post_calls += 1
        self.factory.post_payloads.append(json)
        if not self.factory.post_responses:
            raise AssertionError(f"Unexpected POST request to {url}")
        return self.factory.post_responses.pop(0)


class FakeClientFactory:
    def __init__(self, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_calls = 0
        self.post_calls = 0
        self.post_payloads = []

    def __call__(self, *args, **kwargs):
        return FakeClient(self)


def _success_response(content: str) -> FakeResponse:
    return FakeResponse(
        200,
        json_data={"choices": [{"message": {"content": content}}]},
    )


def test_parse_ai_response_accepts_raw_json():
    result = analyzer._parse_ai_response(
        '{"prelims_angle":"A","mains_angle":"B","probable_question":"Q","static_connect":"S","key_terms":["x"],"one_line_takeaway":"T"}'
    )
    assert result is not None
    assert result["prelims_angle"] == "A"
    assert result["key_terms"] == ["x"]


def test_parse_ai_response_accepts_fenced_json():
    result = analyzer._parse_ai_response(
        '```json\n{"prelims_angle":"A","mains_angle":"B","probable_question":"Q","static_connect":"S","key_terms":["x"],"one_line_takeaway":"T"}\n```'
    )
    assert result is not None
    assert result["mains_angle"] == "B"


def test_parse_ai_response_rejects_malformed_json():
    result = analyzer._parse_ai_response("not valid json")
    assert result is None


def test_wait_for_request_slot_enforces_spacing(monkeypatch):
    analyzer._reset_ai_state()
    analyzer._ai_state["last_request_at"] = 10.0
    monkeypatch.setenv("AI_MIN_REQUEST_INTERVAL_SECONDS", "3.5")

    times = iter([12.0, 13.6])
    sleeps: list[float] = []
    monkeypatch.setattr(analyzer.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(analyzer.time, "sleep", lambda seconds: sleeps.append(seconds))

    analyzer._wait_for_request_slot()

    assert sleeps == [1.5]
    assert analyzer._ai_state["last_request_at"] == 13.6


def test_generate_exam_playbook_honors_retry_after(monkeypatch):
    analyzer._reset_ai_state()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_MIN_REQUEST_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AI_MAX_RETRIES", "2")

    factory = FakeClientFactory(
        get_responses=[FakeResponse(200, json_data={"data": {"is_free_tier": True}})],
        post_responses=[
            FakeResponse(429, text="rate limited", headers={"Retry-After": "7"}),
            _success_response(
                json.dumps({
                    "prelims_angle": "Prelims angle",
                    "mains_angle": "Mains angle",
                    "probable_question": "Question",
                    "static_connect": "Static",
                    "key_terms": ["term"],
                    "one_line_takeaway": "Takeaway",
                })
            ),
        ],
    )
    sleeps: list[float] = []
    monkeypatch.setattr(analyzer.httpx, "Client", factory)
    monkeypatch.setattr(analyzer.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = analyzer.generate_exam_playbook(
        headline="Policy update",
        summary="Important policy summary",
        why_it_matters="Relevant for governance",
        gs_paper="GS2",
        subtopics=["Governance"],
        matched_criteria=2,
        relevance_score=0.9,
    )

    assert result is not None
    assert result["gs_paper"] == "GS2"
    assert 7.0 in sleeps
    assert factory.post_calls == 2
    assert analyzer.get_ai_runtime_status()["ai_calls_used"] == 1


def test_generate_exam_playbook_stops_when_run_cap_is_reached(monkeypatch):
    analyzer._reset_ai_state()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_MIN_REQUEST_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("AI_FREE_TIER_RUN_CAP", "0")

    factory = FakeClientFactory(
        get_responses=[FakeResponse(200, json_data={"data": {"is_free_tier": True}})],
        post_responses=[],
    )
    monkeypatch.setattr(analyzer.httpx, "Client", factory)

    result = analyzer.generate_exam_playbook(
        headline="Policy update",
        summary="Important policy summary",
        why_it_matters="Relevant for governance",
        gs_paper="GS2",
        subtopics=["Governance"],
        matched_criteria=2,
        relevance_score=0.9,
    )

    assert result is None
    assert factory.get_calls == 1
    assert factory.post_calls == 0
    assert analyzer.get_ai_runtime_status()["last_result"] == "skipped_budget"


def test_prepare_ai_run_defaults_to_free_tier_budget_when_key_info_unavailable(monkeypatch):
    analyzer._reset_ai_state()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("AI_FREE_TIER_RUN_CAP", "20")
    monkeypatch.setenv("AI_FREE_TIER_DAILY_CAP", "50")

    factory = FakeClientFactory(
        get_responses=[FakeResponse(503, text="unavailable")],
        post_responses=[],
    )
    monkeypatch.setattr(analyzer.httpx, "Client", factory)

    status = analyzer.prepare_ai_run()

    assert status["is_free_tier"] is True
    assert status["run_cap"] == 20
    assert status["daily_cap_assumed"] == 50
    assert status["has_key_info"] is False
