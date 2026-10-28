"""Gemini Developer API REST adapter. No tools, remote URLs or client-selected models."""

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from packages.config.settings import Settings

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RESPONSE_BYTES = 262144
MAX_PROMPT_BYTES = 65536
RETRYABLE = {429, 500, 502, 503, 504}


class GeminiError(RuntimeError):
    """Only fixed, non-sensitive error codes may cross the application boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Completion:
    text: str
    model_version: str
    usage: dict[str, int]


def response_schema(schema):
    """Google's documented JSON Schema subset; full constraints still run locally."""
    supported = {
        "$defs",
        "$ref",
        "type",
        "format",
        "title",
        "description",
        "enum",
        "items",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
        "anyOf",
        "oneOf",
        "properties",
        "additionalProperties",
        "required",
    }
    result = {}
    for key, value in schema.items():
        if key == "const":
            result["enum"] = [value]
        elif key in ("properties", "$defs"):
            result[key] = {name: response_schema(child) for name, child in value.items()}
        elif key in ("items", "additionalProperties") and isinstance(value, dict):
            result[key] = response_schema(value)
        elif key in ("anyOf", "oneOf"):
            result[key] = [response_schema(child) for child in value]
        elif key in supported:
            result[key] = value
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("Non-finite response number")


def decode_completion(content: bytes) -> Completion:
    try:
        data = json.loads(
            content, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        if not isinstance(data, dict) or data.get("promptFeedback", {}).get("blockReason"):
            raise ValueError("Blocked response")
        candidates = data["candidates"]
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise ValueError("Incomplete or ambiguous candidate")
        candidate = candidates[0]
        if any(rating.get("blocked", False) for rating in candidate.get("safetyRatings", [])):
            raise ValueError("Blocked candidate")
        if candidate["content"].get("role") != "model":
            raise ValueError("Expected model content")
        parts = candidate["content"]["parts"]
        if not parts or any(
            set(part) - {"text", "thoughtSignature", "thought"}
            or part.get("thought", False)
            or not isinstance(part.get("text"), str)
            for part in parts
        ):
            raise ValueError("Non-text or thought/tool output")
        text = "".join(part["text"] for part in parts)
        version = data["modelVersion"]
        if (
            not text.strip()
            or not isinstance(version, str)
            or len(version) > 200
            or not re.fullmatch(r"gemini-[A-Za-z0-9._-]+", version)
        ):
            raise ValueError("Missing content/model version")
        metadata = data.get("usageMetadata", {})
        usage = {
            key: metadata[key]
            for key in (
                "promptTokenCount",
                "candidatesTokenCount",
                "totalTokenCount",
                "thoughtsTokenCount",
            )
            if key in metadata
        }
        if any(type(count) is not int or count < 0 for count in usage.values()):
            raise ValueError("Invalid token count")
        return Completion(text, version, usage)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, RecursionError):
        raise GeminiError("GEMINI_RESPONSE_REJECTED") from None


class GeminiAdapter:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not settings.gemini_enabled:
            raise GeminiError("GEMINI_DISABLED")
        if not settings.gemini_api_key.get_secret_value() or not settings.gemini_model:
            raise GeminiError("GEMINI_NOT_CONFIGURED")
        self._settings = settings
        self._transport = transport
        self._sleep = sleep

    def generate(self, prompt: dict) -> str:
        return self.complete(prompt).text

    def complete(self, prompt: dict) -> Completion:
        document = prompt["document_json"]
        if len(document.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise GeminiError("GEMINI_INPUT_TOO_LARGE")
        body = {
            "systemInstruction": {"parts": [{"text": prompt["system"]}]},
            "contents": [{"role": "user", "parts": [{"text": document}]}],
            "generationConfig": {
                "temperature": 0,
                "candidateCount": 1,
                "maxOutputTokens": self._settings.gemini_max_output_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema(prompt["response_schema"]),
            },
        }
        url = f"{API_ROOT}/{self._settings.gemini_model}:generateContent"
        # Never put the key in the URL/body or propagate upstream bodies/exceptions.
        headers = {
            "x-goog-api-key": self._settings.gemini_api_key.get_secret_value(),
            "Content-Type": "application/json",
        }
        with httpx.Client(
            timeout=httpx.Timeout(self._settings.gemini_timeout_seconds),
            follow_redirects=False,
            verify=True,
            trust_env=True,
            transport=self._transport,
        ) as client:
            for attempt in range(2):
                try:
                    with client.stream("POST", url, headers=headers, json=body) as response:
                        if response.status_code in RETRYABLE:
                            if attempt == 0:
                                delay = 0.25
                                retry_after = response.headers.get("Retry-After")
                                if retry_after is not None:
                                    try:
                                        delay = float(retry_after)
                                    except ValueError:
                                        delay = math.inf
                                if math.isfinite(delay) and 0 <= delay <= 1:
                                    self._sleep(max(0.25, delay))
                                    continue
                            raise GeminiError(
                                "GEMINI_RATE_LIMITED"
                                if response.status_code == 429
                                else "GEMINI_UNAVAILABLE"
                            )
                        if response.status_code != 200:
                            raise GeminiError("GEMINI_UPSTREAM_REJECTED")
                        content = bytearray()
                        for chunk in response.iter_bytes():
                            content.extend(chunk)
                            if len(content) > MAX_RESPONSE_BYTES:
                                raise GeminiError("GEMINI_RESPONSE_TOO_LARGE")
                        return decode_completion(bytes(content))
                except (httpx.ConnectError, httpx.ConnectTimeout):
                    if attempt == 0:
                        self._sleep(0.25)
                        continue
                    raise GeminiError("GEMINI_UNAVAILABLE") from None
                except httpx.TimeoutException:
                    # Delivery may have succeeded: don't automatically pay for a second generation.
                    raise GeminiError("GEMINI_TIMEOUT_AMBIGUOUS") from None
                except httpx.HTTPError:
                    raise GeminiError("GEMINI_TRANSPORT_AMBIGUOUS") from None
        raise GeminiError("GEMINI_UNAVAILABLE")
