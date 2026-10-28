import json

import httpx
import pytest

from packages.config.settings import Settings
from services.news_intelligence.classification import build_target_prompt, parse_output
from services.news_intelligence.providers.gemini import (
    MAX_RESPONSE_BYTES,
    GeminiAdapter,
    GeminiError,
    decode_completion,
    response_schema,
)
from tests.decision.test_classification import SOURCE_ID, assessment, source

KEY = "unit-test-only-nonfunctional-key"


def settings(**changes):
    return Settings(
        **(
            {
                "gemini_enabled": True,
                "gemini_api_key": KEY,
                "gemini_model": "gemini-test",
                "_env_file": None,
            }
            | changes
        )
    )


def prompt():
    return build_target_prompt(
        [source()],
        {
            "event_id": SOURCE_ID,
            "source_ids": [SOURCE_ID],
            "symbol": "EXAMPLE",
            "asset_class": "stock",
        },
    )


def envelope(**changes):
    return {
        "modelVersion": "gemini-test-001",
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"role": "model", "parts": [{"text": json.dumps(assessment())}]},
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 20,
            "candidatesTokenCount": 30,
            "totalTokenCount": 50,
        },
    } | changes


def adapter(handler, **changes):
    return GeminiAdapter(
        settings(**changes), transport=httpx.MockTransport(handler), sleep=lambda _: None
    )


def test_request_fixed_host_header_structured_schema_no_tools_and_usage():
    seen = []

    def handler(request):
        seen.append(request)
        assert (
            str(request.url)
            == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
        )
        assert not request.url.query and request.headers["x-goog-api-key"] == KEY
        body = json.loads(request.content)
        assert KEY not in request.content.decode()
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["generationConfig"]["maxOutputTokens"] == 4096
        assert body["generationConfig"]["candidateCount"] == 1
        assert "tools" not in body and "toolConfig" not in body
        schema = body["generationConfig"]["responseJsonSchema"]
        assert schema["properties"]["symbol"]["enum"] == ["EXAMPLE"]
        assert schema["properties"]["event_id"]["enum"] == [SOURCE_ID]
        document = json.loads(body["contents"][0]["parts"][0]["text"])
        assert document["target"]["symbol"] == "EXAMPLE"
        assert document["sources"][0]["source_id"] == SOURCE_ID
        return httpx.Response(200, json=envelope())

    result = adapter(handler).complete(prompt())
    assert len(seen) == 1
    assert result.model_version == "gemini-test-001" and result.usage["totalTokenCount"] == 50
    assert parse_output(result.text).symbol == "EXAMPLE"


def test_subset_schema_keeps_fields_and_enum_but_local_constraints_remain():
    original = prompt()["response_schema"]
    converted = response_schema(original)
    assert original["properties"]["schema_version"]["const"] == "1.0"
    assert converted["properties"]["schema_version"]["enum"] == ["1.0"]
    assert "pattern" not in converted["properties"]["symbol"]
    assert "maxLength" not in converted["properties"]["symbol"]
    assert converted["additionalProperties"] is False
    assert converted["required"] == original["required"]
    assert converted["properties"]["confidence"]["maximum"] == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_transient_http_retry_is_bounded(status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text="secret error body " + KEY)

    with pytest.raises(GeminiError) as error:
        adapter(handler).complete(prompt())
    assert len(requests) == 2
    assert KEY not in str(error.value)
    assert error.value.code in ("GEMINI_RATE_LIMITED", "GEMINI_UNAVAILABLE")


def test_transient_then_success_and_connect_retry():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError(KEY, request=request)
        return httpx.Response(200, json=envelope())

    assert adapter(handler).complete(prompt()).model_version == "gemini-test-001"
    assert len(attempts) == 2


@pytest.mark.parametrize("status", [301, 307, 400, 401, 403, 404])
def test_non_retryable_errors_and_redirects_do_not_forward_the_key(status, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, text=KEY, headers={"Location": "https://attacker.example/steal"}
        )

    with pytest.raises(GeminiError, match="GEMINI_UPSTREAM_REJECTED"):
        adapter(handler).complete(prompt())
    assert len(calls) == 1 and KEY not in caplog.text


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.ReadTimeout, "GEMINI_TIMEOUT_AMBIGUOUS"),
        (httpx.ReadError, "GEMINI_TRANSPORT_AMBIGUOUS"),
    ],
)
def test_ambiguous_delivery_is_not_automatically_retried(exception, code):
    calls = []

    def handler(request):
        calls.append(request)
        raise exception(KEY, request=request)

    with pytest.raises(GeminiError) as error:
        adapter(handler).complete(prompt())
    assert error.value.code == code and len(calls) == 1
    assert KEY not in str(error.value)


@pytest.mark.parametrize(
    "case",
    [
        "blocked",
        "truncated",
        "no_candidates",
        "two_candidates",
        "tool",
        "thought",
        "missing_version",
        "usage",
        "invalid_json",
        "wrong_role",
        "duplicates",
    ],
)
def test_incomplete_unsafe_or_malformed_response_rejected_without_retry(case):
    body = envelope()
    candidate = body["candidates"][0]
    if case == "blocked":
        body["promptFeedback"] = {"blockReason": "SAFETY"}
    elif case == "truncated":
        candidate["finishReason"] = "MAX_TOKENS"
    elif case == "no_candidates":
        body["candidates"] = []
    elif case == "two_candidates":
        body["candidates"].append(candidate.copy())
    elif case == "tool":
        candidate["content"]["parts"] = [{"functionCall": {"name": "place_order"}}]
    elif case == "thought":
        candidate["content"]["parts"][0]["thought"] = True
    elif case == "missing_version":
        del body["modelVersion"]
    elif case == "usage":
        body["usageMetadata"]["totalTokenCount"] = "50"
    elif case == "wrong_role":
        candidate["content"]["role"] = "user"
    raw = json.dumps(body)
    if case == "invalid_json":
        raw = "not json " + KEY
    elif case == "duplicates":
        raw = raw[:-1] + ',"modelVersion":"gemini-other"}'
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text=raw)

    with pytest.raises(GeminiError, match="GEMINI_RESPONSE_REJECTED"):
        adapter(handler).complete(prompt())
    assert len(calls) == 1


def test_opaque_signature_is_not_interpreted_as_tool_or_reasoning():
    body = envelope()
    body["candidates"][0]["content"]["parts"][0]["thoughtSignature"] = "opaque-provider-signature"
    assert decode_completion(json.dumps(body).encode()).text == json.dumps(assessment())


def test_input_and_response_sizes_are_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))

    instance = adapter(handler)
    with pytest.raises(GeminiError, match="GEMINI_INPUT_TOO_LARGE"):
        instance.complete(prompt() | {"document_json": "x" * 65537})
    assert calls == []
    with pytest.raises(GeminiError, match="GEMINI_RESPONSE_TOO_LARGE"):
        instance.complete(prompt())
    assert calls == [1]


def test_optional_configuration_secret_repr_and_path_injection_rejected():
    with pytest.raises(GeminiError, match="GEMINI_DISABLED"):
        GeminiAdapter(settings(gemini_enabled=False))
    for changes in ({"gemini_api_key": ""}, {"gemini_model": ""}):
        with pytest.raises(GeminiError, match="GEMINI_NOT_CONFIGURED"):
            GeminiAdapter(settings(**changes))
    assert KEY not in repr(settings()) and KEY not in settings().model_dump_json()
    for model in [
        "../models/gemini-test",
        "https://attacker.example",
        "gemini-test:invoke",
        "gemini-test/other",
    ]:
        with pytest.raises(ValueError):
            settings(gemini_model=model)


def test_long_retry_after_fails_without_a_second_request_or_sleep():
    calls, sleeps = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    instance = GeminiAdapter(
        settings(), transport=httpx.MockTransport(handler), sleep=sleeps.append
    )
    with pytest.raises(GeminiError, match="GEMINI_RATE_LIMITED"):
        instance.complete(prompt())
    assert len(calls) == 1 and sleeps == []
