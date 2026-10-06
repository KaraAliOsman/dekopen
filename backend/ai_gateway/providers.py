"""Provider transports for the AI gateway.

Routes (capability → provider/model/cost) are operational config in ai_routes;
tenants only ever see the white-label public_name. Real providers are wired via
environment: AI_GATEWAY_{PROVIDER}_API_KEY and AI_GATEWAY_{PROVIDER}_BASE_URL.
MOCK is the deterministic default used by seeded routes and tests — it never
performs network I/O."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import logging
import os
import random
import re
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


MAX_BODY_BYTES = 1_048_576
# Above this size the base64 transport inflates the request more than a
# signed URL is worth — the image goes to the provider as a fetchable URL.
_IMAGE_WIRE_MAX_BYTES = 12 * 1024 * 1024
_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _image_mime(object_key: str) -> str:
    _, dot, ext = object_key.lower().rpartition(".")
    return _IMAGE_MIME.get(f".{ext}" if dot else "", "image/png")
# A configured base path may only contain plain ASCII segments — no
# encoded separators, dot segments, backslashes, or whitespace that could
# redirect the authenticated request on the approved host.
_BASE_PATH_RE = re.compile(r"/(?:[A-Za-z0-9._~-]+/)*[A-Za-z0-9._~-]*")


def _timeout_seconds(provider: str) -> float:
    """AI_GATEWAY_{P}_TIMEOUT_S — whole-request bound in seconds. Defaults to
    60; a malformed or out-of-range value refuses the provider outright so a
    deployment mistake fails visibly instead of silently changing latency
    guarantees."""
    raw = os.environ.get(f"AI_GATEWAY_{provider}_TIMEOUT_S", "")
    if not raw:
        return 60.0
    try:
        value = float(raw)
    except ValueError as error:
        raise ProviderError("ai_provider_unavailable") from error
    if not 1.0 <= value <= 600.0:
        raise ProviderError("ai_provider_unavailable")
    return value


# Transient retries: transport blips and 5xx answers deserve a bounded
# backoff retry, quota/auth/rejection do not. Route retry_max overrides the
# env default of 2; both are capped at 4 so a wedged endpoint cannot hold a
# worker loop hostage.
def _retries_max(provider: str) -> int:
    """AI_GATEWAY_{P}_RETRIES — retries after the first attempt on a
    transient failure. Default 2, range 0..4; malformed refuses the
    provider outright like a malformed timeout."""
    raw = os.environ.get(f"AI_GATEWAY_{provider}_RETRIES", "")
    if not raw:
        return 2
    try:
        value = int(raw)
    except ValueError as error:
        raise ProviderError("ai_provider_unavailable") from error
    if not 0 <= value <= 4:
        raise ProviderError("ai_provider_unavailable")
    return value


def _mock_enabled() -> bool:
    """Whether the deterministic MOCK provider may serve this deployment.
    Explicit AI_GATEWAY_MOCK_ENABLED wins either way — it is the only channel
    that can enable MOCK under ENVIRONMENT=production (the explicit "Modo de
    prueba" flag). Without it, MOCK serves development (DEBUG) and the test
    suite (PYTEST_CURRENT_TEST) only — DEBUG or a stray pytest process can
    never turn fabricated answers on in a production stack."""
    explicit = os.environ.get("AI_GATEWAY_MOCK_ENABLED", "").lower()
    if explicit in {"1", "true", "yes"}:
        return True
    if explicit in {"0", "false", "no"}:
        return False
    if os.environ.get("ENVIRONMENT", "") == "production":
        return False
    return os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"} or bool(
        os.environ.get("PYTEST_CURRENT_TEST")
    )


def _resolve_provider_hosts(hostname: str) -> list[str] | None:
    """Resolve the configured host once and return every validated global
    answer in resolver order, or None. Literal IPs are checked directly; a
    DNS name must resolve to global answers only — any non-global answer
    refuses the provider, and resolution failure refuses closed. Requests
    pin these exact addresses (Host header + SNI keep the configured name),
    so no second lookup exists for a rebinding attack to poison — while
    trying each answer preserves normal multi-address failover."""
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
        except (socket.gaierror, UnicodeError):
            return None
        resolved: list[str] = []
        for info in infos:
            if not info[4] or not info[4][0]:
                continue
            try:
                candidate = ipaddress.ip_address(info[4][0])
            except ValueError:
                return None
            if not candidate.is_global:
                return None
            resolved.append(info[4][0])
        return resolved or None
    return [str(address)] if address.is_global else None


def _retry_after_seconds(raw: str | None) -> float | None:
    """Parse a Retry-After header value in seconds (HTTP-date forms are
    ignored — capped at 30s so a hostile header can't park a worker)."""
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return min(max(value, 0.0), 30.0)


def _strict_json_options(options: dict) -> dict:
    """Drop tool calling and pin strict JSON output — the degraded contract
    a provider without tools support still satisfies: the model answers the
    same document shape the caller validates."""
    fallback = {
        key: value
        for key, value in options.items()
        if key not in ("tools", "tool_choice")
    }
    fallback["json_output"] = True
    return fallback


class ProviderError(Exception):
    """Sanitized provider failure — never carries credentials or payloads.

    ``transient`` marks a failure the caller may retry after a short backoff
    (timeouts, connect failures, 5xx/408/425, 429 with Retry-After). Quota,
    auth, rejection and mock-disabled errors are terminal — retrying them
    only burns time and can replay a billed call."""

    def __init__(
        self,
        code: str,
        *,
        transient: bool = False,
        retry_after: float | None = None,
    ):
        self.code = code
        self.transient = transient
        self.retry_after = retry_after
        super().__init__(code)


class HttpProvider:
    """Generic JSON invocation endpoint: POST {model, capability, input}."""

    def __init__(
        self,
        *,
        provider: str,
        timeout_s: float | None = None,
        retry_max: int | None = None,
    ):
        self.provider = provider
        self.api_key = os.environ.get(f"AI_GATEWAY_{provider}_API_KEY", "")
        self.base_url = os.environ.get(f"AI_GATEWAY_{provider}_BASE_URL", "").rstrip("/")
        if not self.api_key or not self.base_url:
            raise ProviderError("ai_provider_unavailable")
        # AI_GATEWAY_{P}_TIMEOUT_S bounds the whole HTTP exchange; the route's
        # timeout_s pins a per-capability bound on top. A malformed env value
        # is a deployment mistake — it fails visibly, never clamps silently.
        self.timeout = float(timeout_s) if timeout_s is not None else _timeout_seconds(provider)
        # Route retry_max (0..4, DB-checked) overrides the env default.
        self.retry_max = _retries_max(provider) if retry_max is None else int(retry_max)
        # Provider URLs are operator config, but a compromised value must not
        # turn the gateway into an authenticated proxy for internal services:
        # https-only, no userinfo/query/fragment, and the host must resolve
        # to global addresses only. Anything else refuses closed rather than
        # silently redirecting or dropping part of the configured endpoint.
        try:
            parsed = urlparse(self.base_url)
            hostname = parsed.hostname
            port = parsed.port or 443
        except ValueError as error:
            raise ProviderError("ai_provider_unavailable") from error
        if (
            parsed.scheme != "https"
            or not hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderError("ai_provider_unavailable")
        connect_ips = _resolve_provider_hosts(hostname)
        if connect_ips is None:
            raise ProviderError("ai_provider_unavailable")
        base_path = parsed.path.rstrip("/")
        if base_path and (
            not _BASE_PATH_RE.fullmatch(base_path)
            or any(segment in (".", "..") for segment in base_path.split("/"))
        ):
            raise ProviderError("ai_provider_unavailable")
        self._host = hostname
        self._port = port
        self._connect_ips = connect_ips
        self._base_path = base_path

    def _send(
        self,
        client: httpx.Client,
        connect_ip: str,
        *,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
        host_header: str,
        port_suffix: str,
        operation_key: str | None,
    ) -> bytes:
        """One pinned attempt: the URL carries the validated connect address
        while Host + SNI keep the configured name. The body streams in with
        a hard byte cap — an unbounded provider response cannot exhaust
        memory before it is rejected."""
        url_host = f"[{connect_ip}]" if ":" in connect_ip else connect_ip
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Host": host_header,
        }
        if operation_key:
            # The operation key doubles as the provider-level idempotency key
            # so a retry ambiguous to us can still dedupe provider-side.
            headers["Idempotency-Key"] = operation_key
        path, body = self._wire_request(route, capability, input_payload, provider_options)
        started = time.monotonic()
        with client.stream(
            "POST",
            f"https://{url_host}{port_suffix}{path}",
            headers=headers,
            extensions={"sni_hostname": self._host},
            json=body,
        ) as response:
            response.raise_for_status()
            content = bytearray()
            # iter_raw yields on every socket arrival — iter_bytes would
            # buffer to chunk size, letting a drip feed stall the deadline
            # check itself. Any wait still bounded by httpx's read timeout;
            # this check bounds the whole exchange's wall-clock. Already-
            # buffered responses (mock transports) yield everything at once.
            stream = response.iter_bytes(65536) if response.is_stream_consumed else response.iter_raw()
            for chunk in stream:
                if time.monotonic() - started > self.timeout:
                    raise ProviderError("ai_provider_timeout", transient=True)
                content += chunk
                if len(content) > MAX_BODY_BYTES:
                    raise ProviderError("ai_provider_output_too_large")
        return bytes(content)

    def _request(
        self,
        *,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
        client: httpx.Client | None = None,
        operation_key: str | None = None,
    ) -> bytes:
        """POST to the provider on each validated address until one connects.
        Connect-phase failures advance to the next pinned answer; any HTTP
        response (including errors) stops the loop — it is an answer, not a
        transport failure. Tests inject a MockTransport client so the real
        httpx request path (extensions, streaming) is exercised."""
        port_suffix = "" if self._port == 443 else f":{self._port}"
        header_host = f"[{self._host}]" if ":" in self._host else self._host
        host_header = header_host if self._port == 443 else f"{header_host}:{self._port}"
        if client is None:
            with httpx.Client(timeout=self.timeout) as owned:
                return self._attempts(
                    owned,
                    route,
                    capability,
                    input_payload,
                    provider_options,
                    host_header,
                    port_suffix,
                    operation_key,
                )
        return self._attempts(
            client,
            route,
            capability,
            input_payload,
            provider_options,
            host_header,
            port_suffix,
            operation_key,
        )

    def _attempts(
        self,
        client: httpx.Client,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
        host_header: str,
        port_suffix: str,
        operation_key: str | None,
    ) -> bytes:
        last_error: httpx.HTTPError | None = None
        for connect_ip in self._connect_ips:
            try:
                return self._send(
                    client,
                    connect_ip,
                    route=route,
                    capability=capability,
                    input_payload=input_payload,
                    provider_options=provider_options,
                    host_header=host_header,
                    port_suffix=port_suffix,
                    operation_key=operation_key,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as error:
                last_error = error
        # Every pinned answer refused the connection — a transient transport
        # failure the retry loop may re-attempt on a later tick.
        raise ProviderError("ai_provider_error", transient=True) from last_error

    def _request_retried(
        self,
        *,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
        client: httpx.Client | None,
        operation_key: str | None,
        requested_model: str,
    ) -> bytes:
        """The request with its transient-retry budget. Only transient
        failures retry — transport timeouts/connect errors and classified
        transient statuses. Quota, auth and rejection are terminal: a retry
        there wastes the caller's window and can replay a billed call."""
        attempt = 0
        while True:
            try:
                return self._request(
                    route=route,
                    capability=capability,
                    input_payload=input_payload,
                    provider_options=provider_options,
                    client=client,
                    operation_key=operation_key,
                )
            except httpx.HTTPStatusError as error:
                mapped = self._classify_status(error, capability, requested_model)
                if mapped.transient and attempt < self.retry_max:
                    self._sleep_retry(mapped, attempt, capability)
                    attempt += 1
                    continue
                raise mapped from error
            except ProviderError as error:
                if error.transient and attempt < self.retry_max:
                    self._sleep_retry(error, attempt, capability)
                    attempt += 1
                    continue
                raise
            except httpx.TransportError as error:
                if attempt < self.retry_max:
                    self._sleep_retry(
                        ProviderError("ai_provider_error", transient=True),
                        attempt,
                        capability,
                    )
                    attempt += 1
                    continue
                # Budget exhausted — the failure stays marked transient:
                # a transport blip is what it is; the bound was policy.
                raise ProviderError("ai_provider_error", transient=True) from error

    @staticmethod
    def _sleep_retry(error: "ProviderError", attempt: int, capability: str) -> None:
        delay = 0.4 * (2 ** attempt) + random.uniform(0, 0.1)
        if error.retry_after is not None:
            delay = max(delay, min(error.retry_after, 30.0))
        delay = min(delay, 30.0)
        logger.warning(
            "AI provider transient failure (capability=%s attempt=%s): %s"
            " — retrying in %.1fs",
            capability,
            attempt + 1,
            error.code,
            delay,
        )
        time.sleep(delay)

    _TRANSIENT_STATUSES = frozenset({408, 425, 500, 502, 503, 504})

    def _classify_status(
        self,
        error: httpx.HTTPStatusError,
        capability: str,
        requested_model: str,
    ) -> ProviderError:
        """Map an answered HTTP status to the sanitized contract. Transient
        statuses (5xx family, 408, 425) and a 429 that carries Retry-After
        are retryable; a bare 429 means quota exhausted — terminal."""
        response = error.response
        status = response.status_code
        retry_after = _retry_after_seconds(response.headers.get("retry-after"))
        # The provider answered — the status class is the diagnosis an
        # operator needs (bad key vs bad model vs spent quota), and the
        # effective model identifies which pin/override was actually sent.
        logger.warning(
            "AI provider %s answered %s (model=%s capability=%s)",
            self.provider,
            status,
            requested_model,
            capability,
        )
        if status in (401, 403):
            return ProviderError("ai_provider_auth")
        if status == 429:
            return ProviderError(
                "ai_provider_quota",
                transient=retry_after is not None,
                retry_after=retry_after,
            )
        if status in self._TRANSIENT_STATUSES:
            return ProviderError(
                "ai_provider_error", transient=True, retry_after=retry_after
            )
        if 400 <= status < 500:
            return ProviderError("ai_provider_rejected")
        return ProviderError("ai_provider_error")

    def invoke(
        self,
        *,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict | None = None,
        client: httpx.Client | None = None,
        operation_key: str | None = None,
        document_path: str | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        options = dict(provider_options or {})
        # The model must fit the provenance column BEFORE the paid call runs —
        # an env override longer than VARCHAR(120) would otherwise fail the
        # sealed audit after inference already happened.
        requested_model = self._requested_model(route)
        if not (0 < len(requested_model) <= 120):
            raise ProviderError("ai_provider_error")
        # Ephemeral fetch URLs are resolved at wire time, never carried in
        # input_payload: the audited input hash must stay identical across
        # retries even though a fresh signed URL is minted each attempt.
        # document_path arrives only from the service's org-scoped source
        # resolution — a request can name an owned document row but can
        # never choose the object key that gets signed.
        wire_input = dict(input_payload)
        if document_path:
            from documents.repository import DocumentaryError
            from documents.storage import SupabaseDocumentStorage

            try:
                wire_input["document_url"] = SupabaseDocumentStorage().signed_url(
                    document_path
                )
            except DocumentaryError as error:
                raise ProviderError("ai_provider_unavailable") from error
            if input_payload.get("kind") == "IMAGE":
                # True multimodal: the image bytes ride inside the request
                # as a data URI so the provider never has to fetch the
                # document itself. Larger files keep the signed URL, which
                # the wire layer still emits as an image_url part.
                try:
                    raw = SupabaseDocumentStorage().download_bounded(
                        document_path, _IMAGE_WIRE_MAX_BYTES
                    )
                    if raw is not None:
                        wire_input["_document_image"] = {
                            "mime": _image_mime(document_path),
                            "data": base64.b64encode(raw).decode("ascii"),
                        }
                except (DocumentaryError, httpx.HTTPError):
                    pass
        tools_fallback = False
        while True:
            try:
                content = self._request_retried(
                    route=route,
                    capability=capability,
                    input_payload=wire_input,
                    provider_options=options,
                    client=client,
                    operation_key=operation_key,
                    requested_model=requested_model,
                )
            except ProviderError as error:
                # A caller that asked for tool calling degrades once to strict
                # JSON when the endpoint rejects the tools parameter — the
                # model answers the same document contract and server-side
                # query steps still execute.
                if (
                    error.code == "ai_provider_rejected"
                    and options.get("tools")
                    and not tools_fallback
                ):
                    tools_fallback = True
                    logger.warning(
                        "AI provider %s rejected tool calling (capability=%s);"
                        " retrying without tools under strict JSON",
                        self.provider,
                        capability,
                    )
                    options = _strict_json_options(options)
                    continue
                raise
            try:
                parsed = self._parse_response(content)
                tokens_prompt = int(parsed["tokens_prompt"])
                tokens_completion = int(parsed["tokens_completion"])
                # Usage feeds an INT4 audit column — a malformed or impossible
                # count is a provider error, not an audit-time database
                # exception raised after the paid call already succeeded.
                if not (
                    0 <= tokens_prompt <= 2_147_483_647
                    and 0 <= tokens_completion <= 2_147_483_647
                ):
                    raise TypeError("provider token usage is outside the audit range")
            except (TypeError, ValueError, KeyError) as error:
                raise ProviderError("ai_provider_error") from error
            break
        response_model = parsed.get("model")
        result: dict[str, Any] = {
            "output": parsed["output"],
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "latency_ms": int((time.monotonic() - started) * 1000),
            # The model the request actually ran on — the response's own model
            # field wins when it is a sane string that fits the provenance
            # column; an overlong or absent value falls back to what we sent.
            # Sealed into audit provenance, which must never re-attribute.
            "model": (
                response_model
                if isinstance(response_model, str) and 0 < len(response_model) <= 120
                else requested_model
            ),
        }
        if parsed.get("tool_calls"):
            result["tool_calls"] = parsed["tool_calls"]
        if parsed.get("assistant_message") is not None:
            result["assistant_message"] = parsed["assistant_message"]
        if tools_fallback:
            result["tools_fallback"] = True
        return result
    def _requested_model(self, route: dict) -> str:
        """Model the request will run on; subclasses may override the route."""
        return str(route["provider_model"])

    def _wire_request(
        self,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
    ) -> tuple[str, dict]:
        """(path, json body) the subclass's protocol posts on the pinned host."""
        return f"{self._base_path}/invoke", {
            "model": route["provider_model"],
            "capability": capability,
            "input": input_payload,
        }

    def _parse_response(self, content: bytes) -> dict[str, Any]:
        """Generic envelope: {output|text, usage:{prompt_tokens,completion_tokens}}."""
        body = json.loads(content)
        if not isinstance(body, dict):
            raise TypeError("provider body is not an object")
        usage = body.get("usage") or {}
        if not isinstance(usage, dict):
            raise TypeError("provider usage is not an object")
        output = body.get("output") if "output" in body else body.get("text")
        if not isinstance(output, str):
            raise TypeError("provider output is not a string")
        return {
            "output": output,
            "tokens_prompt": int(usage.get("prompt_tokens") or 0),
            "tokens_completion": int(usage.get("completion_tokens") or 0),
            "model": body["model"] if isinstance(body.get("model"), str) else None,
        }


_DEFAULT_SYSTEM = (
    "You are the backend endpoint of a professional design tool. "
    "Respond with a single JSON document only — no prose, no markdown fences."
)


def _parse_tool_calls(raw: Any) -> list[dict]:
    """Normalize choices[0].message.tool_calls into {id, name, arguments}
    triples — arguments arrive as a JSON string on OpenAI-compatible
    endpoints; anything malformed is skipped, never crashes the round."""
    if not isinstance(raw, list) or not raw:
        return []
    calls: list[dict] = []
    for item in raw[:8]:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments)
            except ValueError:
                parsed_args = {"_raw": arguments}
        elif isinstance(arguments, dict):
            parsed_args = arguments
        else:
            parsed_args = {}
        calls.append(
            {
                "id": str(item.get("id") or f"call_{len(calls)}")[:80],
                "name": name.strip()[:120],
                "arguments": parsed_args,
            }
        )
    return calls


class OpenAICompatibleProvider(HttpProvider):
    """OpenAI-compatible chat-completions transport (Xiaomi MiMo, OpenAI,
    OpenRouter, …). Inherits the pinned-host request machinery; only the wire
    contract differs: POST {base}/chat/completions with {model, messages}.

    Configuration (all env, per provider name):
      AI_GATEWAY_{P}_API_KEY   — bearer token (required)
      AI_GATEWAY_{P}_BASE_URL  — https endpoint, e.g. https://api.xiaomimimo…/v1
      AI_GATEWAY_{P}_MODEL     — overrides the route's provider_model when set

    Server-side callers may steer the conversation through provider_options
    (never input_payload — that is client-supplied and audited verbatim, so
    honoring control keys inside it would let any authenticated caller replace
    the platform's system prompt and would pollute the replay hash):
      "system"      — system-prompt text (defaults to a JSON-only endpoint prompt)
      "json_output" — truthy requests response_format={"type": "json_object"}
    input_payload is serialized whole as the user message."""

    def __init__(
        self, *, provider: str, timeout_s=None, retry_max=None
    ):
        super().__init__(provider=provider, timeout_s=timeout_s, retry_max=retry_max)
        self._model = os.environ.get(f"AI_GATEWAY_{provider}_MODEL", "")

    def _wire_request(
        self,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict,
    ) -> tuple[str, dict]:
        # An operator may point BASE_URL straight at the completions path —
        # don't double-append it.
        path = (
            self._base_path
            if self._base_path.endswith("/chat/completions")
            else f"{self._base_path}/chat/completions"
        )
        # Wire-time artifacts (signed URL, inline image) are transport
        # details, not document facts — the text part never sees them.
        text_payload = {
            key: value
            for key, value in input_payload.items()
            if not key.startswith("_") and key != "document_url"
        }
        text_json = json.dumps(text_payload, ensure_ascii=False, default=str)
        image = input_payload.get("_document_image")
        image_url = input_payload.get("document_url")
        user_content: Any
        if (
            isinstance(image, dict)
            and isinstance(image.get("data"), str)
            and isinstance(image.get("mime"), str)
        ):
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image['mime']};base64,{image['data']}",
                    },
                },
                {"type": "text", "text": text_json},
            ]
        elif input_payload.get("kind") == "IMAGE" and isinstance(image_url, str):
            user_content = [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": text_json},
            ]
        else:
            clean_payload = {
                key: value
                for key, value in input_payload.items()
                if not key.startswith("_")
            }
            user_content = json.dumps(clean_payload, ensure_ascii=False, default=str)
        messages: list[dict] = [
            {
                "role": "system",
                "content": str(provider_options.get("system") or _DEFAULT_SYSTEM),
            }
        ]
        # Prior turns/tool transcripts the caller feeds forward — server-side
        # options only, never client input. Each must be a plain {role,
        # content[, tool_calls]} message dict.
        extra = provider_options.get("extra_messages")
        if isinstance(extra, list):
            messages.extend(
                message
                for message in extra
                if isinstance(message, dict) and isinstance(message.get("role"), str)
            )
        messages.append({"role": "user", "content": user_content})
        body: dict[str, Any] = {
            "model": self._requested_model(route),
            "messages": messages,
            "temperature": 0,
        }
        if provider_options.get("json_output"):
            body["response_format"] = {"type": "json_object"}
        # Native tool calling: callers pass OpenAI-shaped tool specs; the
        # model answers choices[0].message.tool_calls the server executes.
        tools = provider_options.get("tools")
        if isinstance(tools, list) and tools:
            body["tools"] = [
                tool for tool in tools if isinstance(tool, dict)
            ][:16]
            tool_choice = provider_options.get("tool_choice")
            if isinstance(tool_choice, str) and tool_choice in (
                "auto",
                "none",
                "required",
            ):
                body["tool_choice"] = tool_choice
        return path, body

    def _requested_model(self, route: dict) -> str:
        # AI_GATEWAY_{P}_MODEL is an operational override — the audit must
        # seal this effective model, not the route's, or provenance lies.
        if self._model:
            pinned = str(route["provider_model"])
            if self._model != pinned:
                logger.warning(
                    "AI_GATEWAY_%s_MODEL overrides the ai_routes pin: "
                    "env=%s route=%s capability=%s",
                    self.provider,
                    self._model,
                    pinned,
                    route.get("capability", "?"),
                )
            return self._model
        return str(route["provider_model"])

    def _parse_response(self, content: bytes) -> dict[str, Any]:
        """OpenAI envelope: choices[0].message.content + usage."""
        body = json.loads(content)
        if not isinstance(body, dict):
            raise TypeError("provider body is not an object")
        # Some compatible gateways answer 200 with an error envelope — that is
        # a provider answer, not a successful completion.
        if body.get("error"):
            raise TypeError("provider returned an error envelope")
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise TypeError("provider returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise TypeError("provider returned no message")
        output = message.get("content")
        tool_calls = _parse_tool_calls(message.get("tool_calls"))
        if not isinstance(output, str) and not tool_calls:
            raise TypeError("provider output is not a string")
        usage = body.get("usage") or {}
        if not isinstance(usage, dict):
            raise TypeError("provider usage is not an object")
        result: dict[str, Any] = {
            "output": output if isinstance(output, str) else "",
            "tokens_prompt": int(usage.get("prompt_tokens") or 0),
            "tokens_completion": int(usage.get("completion_tokens") or 0),
            "model": body["model"] if isinstance(body.get("model"), str) else None,
        }
        if tool_calls:
            result["tool_calls"] = tool_calls
            # The assistant message verbatim so a caller can echo it back
            # into a follow-up request's message list.
            result["assistant_message"] = {
                key: value
                for key, value in message.items()
                if key in ("role", "content", "tool_calls")
            }
        return result


_COUNT_RE = re.compile(r"(\d+)\s*(m[oó]dulos?|vanos?|unidades?|pa[nñ]os?)")
_WIDTH_RE = re.compile(
    r"(?:ancho\s+(?:total\s+)?(?:de\s+)?|medida\s+de\s+)(\d{3,5})(?:\s*mm)?"
    r"|(\d{3,5})\s*mm\s+de\s+ancho"
)
_HEIGHT_RE = re.compile(r"alto\s+(?:de\s+)?(\d{3,4})(?:\s*mm)?|(\d{3,4})\s*mm\s+de\s+alto")
_OPENING_KEYWORDS = (
    (re.compile(r"corred"), "SLIDING_2L"),
    (re.compile(r"puerta|door"), "DOOR_ENTRY"),
    (re.compile(r"proyectante|awning"), "AWNING"),
    (re.compile(r"oscil|batiente|tilt"), "TILT_TURN_LEFT"),
    (re.compile(r"fijo|fixed"), "FIXED"),
)


def _design_assist_output(input_payload: dict) -> dict:
    """Mock design intent → typed product ops. The contract the real provider
    must satisfy is exercised exactly: a JSON document of whitelisted ops plus
    a human note, deterministic per prompt so environments and tests agree.

    IA2 — el mock cubre el registro completo: split_bay con `parts` (N hojas
    iguales), refs de hoja posicionales post-split, ops de posición
    (set_system desde el catálogo real), vidrio sólo cuando el SKU existe, y
    el canal tipado `clarify` cuando la instrucción es ambigua."""
    prompt = str(input_payload.get("prompt") or "").lower()
    product = input_payload.get("product") or {}
    modules = product.get("modules") or []
    couplings = product.get("couplings") or []
    catalog = input_payload.get("catalog") or {}
    ops: list[dict] = []
    notes: list[str] = []
    clarify: dict | None = None

    # Reglas IA2 — van antes de las genéricas y marcan `handled` para que
    # el mismo prompt no dispare dos interpretaciones contradictorias.
    handled = False
    measure_mm = re.search(r"(\d+(?:[.,]\d+)?)\s*mm", prompt)
    measure_mm_loose = re.search(r"manilla[^\d]*?(\d{3,4})", prompt)

    if (
        re.search(r"manilla", prompt)
        and (measure_mm or measure_mm_loose)
        and re.search(r"instalaci[oó]n|elevaci[oó]n|altura\s+final|final\s+sobre", prompt)
    ):
        # La respuesta al clarify continúa el mismo pedido: la altura
        # queda zanjada y la manilla se fija a la medida declarada.
        ops.append(
            {
                "op": "set_handle_height",
                "mm": (measure_mm or measure_mm_loose).group(1).replace(",", "."),
            }
        )
        notes.append("manilla a la altura aclarada")
        handled = True
    elif re.search(r"manilla", prompt) and (measure_mm or measure_mm_loose):
        # "manilla a 1050 del piso" — ambigua: altura de instalación o
        # elevación objetivo. La respuesta correcta del contrato es una
        # aclaración tipada con opciones reales, no adivinar.
        mm = (measure_mm or measure_mm_loose).group(1)
        clarify = {
            "question": (
                f"¿{mm} mm es la altura de instalación "
                "o el punto donde debe quedar la manilla?"
            ),
            "options": [
                {"value": "instalacion", "label": "Altura de instalación"},
                {"value": "elevacion", "label": "Altura final sobre el piso"},
            ],
        }
        notes.append("aclaración sobre la altura de la manilla")
        handled = True
    elif re.search(r"manilla.*otro\s+lado|otro\s+lado|invertir|espej", prompt):
        # "pon la manilla al otro lado" — flip_handing espeja la hoja.
        ops.append({"op": "flip_handing"})
        notes.append("manilla al otro lado")
        handled = True
    if re.search(r"travesa[nñ]o", prompt):
        op: dict[str, object] = {"op": "split_bay", "axis": "H"}
        if measure_mm:
            op["offset_mm"] = measure_mm.group(1).replace(",", ".")
            op["from"] = (
                "START"
                if re.search(r"arriba|superior", prompt)
                else "END" if re.search(r"abajo|inferior", prompt) else "CENTER"
            )
        ops.append(op)
        notes.append("travesaño")
        handled = True
    if re.search(r"tres\s+hojas|en\s+tres\b", prompt):
        ops.append({"op": "split_bay", "axis": "V", "parts": 3})
        if re.search(r"fija\s+al\s+centro|centro\s+fij", prompt):
            # "fija al centro y abatibles a los lados" — refs posicionales
            # sobre el orden de hojas post-split (0,1,2).
            ops.append({"op": "set_opening", "bay": 0, "opening": "TURN_LEFT"})
            ops.append({"op": "set_opening", "bay": 2, "opening": "TURN_RIGHT"})
            notes.append("fija al centro, abatibles espejo")
        else:
            notes.append("tres hojas iguales")
        handled = True
    elif re.search(r"izquierda\s+fija.*oscil|fija.*(?:y|e)\s+.*oscil", prompt):
        # "la izquierda fija y la derecha oscilobatiente" — split + una
        # apertura por hoja, en orden de documento.
        ops.append({"op": "split_bay", "axis": "V"})
        ops.append({"op": "set_opening", "bay": 0, "opening": "FIXED"})
        ops.append({"op": "set_opening", "bay": 1, "opening": "TILT_TURN_LEFT"})
        notes.append("dos hojas: fija izquierda, oscilobatiente derecha")
        handled = True
    elif re.search(r"(?:en\s+dos|dos\s+hojas).*(?:oscil|batiente|tilt)", prompt):
        # "divide la hoja en dos oscilobatientes" — split + una apertura por
        # hoja en orden de documento (espejo: izquierda TILT_TURN_LEFT,
        # derecha TILT_TURN_RIGHT), mismo patrón que "fija + oscilobatiente".
        ops.append({"op": "split_bay", "axis": "V", "parts": 2})
        ops.append({"op": "set_opening", "bay": 0, "opening": "TILT_TURN_LEFT"})
        ops.append({"op": "set_opening", "bay": 1, "opening": "TILT_TURN_RIGHT"})
        notes.append("dos hojas oscilobatientes espejo")
        handled = True
    elif re.search(r"tercio|1/3|2/3", prompt):
        # «Proponer división 1/3–2/3» — un corte vertical al tercio del
        # ancho real del módulo (offset_mm es un número derivado de la
        # medida del contexto, lo que el contrato permite).
        total = sum(
            int(str(module.get("width_mm") or 0)) for module in modules
        )
        op: dict[str, object] = {"op": "split_bay", "axis": "V"}
        if total > 0:
            op["offset_mm"] = str(total // 3)
        ops.append(op)
        notes.append("división 1/3–2/3")
        handled = True
    elif re.search(r"dos\s+hojas|en\s+dos\b|a\s+la\s+mitad|por\s+la\s+mitad", prompt):
        ops.append({"op": "split_bay", "axis": "V", "parts": 2})
        notes.append("dos hojas iguales")
        handled = True
    if re.search(r"corred", prompt):
        # Sistema corredera: set_system con el id REAL del catálogo — la
        # op de posición existe, nunca un set_opening SLIDING_2L inventado.
        sliding = next(
            (
                item
                for item in catalog.get("systems") or []
                if isinstance(item, dict)
                and "SLIDING" in str(item.get("system_family") or "").upper()
            ),
            None,
        )
        if sliding is not None:
            ops.append({"op": "set_system", "system_id": str(sliding["id"])})
            notes.append(f"sistema {sliding.get('code') or 'corredero'}")
        handled = True
    if re.search(r"vidrio|termopanel|laminad", prompt):
        # Sólo SKUs reales del catálogo: si la composición pedida no existe,
        # se declara la no disponibilidad con las alternativas reales —
        # nunca un SKU inventado.
        wanted = re.search(r"(\d+[-+]\d+[-+]\d+|\d+\s*\+\s*\d+|laminad)", prompt)
        recipes = catalog.get("glass_recipes") or {}
        match = next(
            (
                sku
                for sku, spec in recipes.items()
                if wanted and str(wanted.group(1)).replace(" ", "") in str(spec).replace(" ", "")
            ),
            None,
        )
        if match:
            ops.append({"op": "set_glass", "sku": match})
            notes.append(f"vidrio {match}")
        else:
            options = ", ".join(
                f"{sku} ({spec})" for sku, spec in sorted(recipes.items())
            ) or "sin opciones registradas"
            notes.append(
                f"ese vidrio no está disponible en el catálogo; opciones: {options}"
            )
        handled = True
    if re.search(r"m[aá]s\s+ancha|m[aá]s\s+ancho", prompt):
        # "20 cm más ancha" — el número derivado lo calcula el motor
        # (declared + context), el mock lo emite como set_total_width.
        extra = re.search(r"(\d+(?:[.,]\d+)?)\s*(cm|mm|metros?)", prompt)
        if extra:
            value = float(extra.group(1).replace(",", "."))
            unit = extra.group(2)
            extra_mm = value * (1000 if unit.startswith("m") and unit != "mm" else 10 if unit == "cm" else 1)
            current = sum(
                float(str(module.get("width_mm") or 0)) for module in modules
            )
            if current > 0:
                ops.append(
                    {
                        "op": "set_total_width",
                        "width_mm": str(int(round(current + extra_mm))),
                    }
                )
                notes.append(f"ancho {int(round(current + extra_mm))} mm")
        handled = True
    meter_width = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:metros?|mts?)\s+de\s+ancho", prompt)
    if meter_width:
        ops.append(
            {
                "op": "set_total_width",
                "width_mm": str(int(float(meter_width.group(1).replace(",", ".")) * 1000)),
            }
        )
        notes.append(f"ancho total {meter_width.group(1)} m")
        handled = True
    bare_height = re.search(r"(\d{3,4})\s+de\s+alto", prompt)
    if bare_height:
        ops.append({"op": "set_height", "height_mm": int(bare_height.group(1))})
        notes.append(f"alto {bare_height.group(1)} mm")
        handled = True

    count = _COUNT_RE.search(prompt)
    if count and int(count.group(1)) > 0:
        ops.append({"op": "set_module_count", "count": int(count.group(1))})
        notes.append(f"{count.group(1)} módulos")
    width = _WIDTH_RE.search(prompt)
    if width:
        ops.append({"op": "set_total_width", "width_mm": int(width.group(1) or width.group(2))})
        notes.append(f"ancho total {width.group(1) or width.group(2)} mm")
    height = _HEIGHT_RE.search(prompt)
    if height:
        ops.append({"op": "set_height", "height_mm": int(height.group(1) or height.group(2))})
        notes.append(f"alto {height.group(1) or height.group(2)} mm")
    if re.search(r"igual|mismo\s+ancho|uniform", prompt):
        # "iguales" compone con conteo/ancho/sistema en la misma frase — no
        # es una petición alternativa, es una constraint más.
        ops.append({"op": "equalize_widths"})
        notes.append("anchos iguales")
    if re.search(r"arco|bow|proa", prompt) and couplings:
        for index, _ in enumerate(couplings):
            ops.append({"op": "set_coupling_angle", "coupling": index, "angle_deg": 22.5})
        notes.append("ángulos de arco 22.5°")
    if not handled:
        for pattern, opening in _OPENING_KEYWORDS:
            if pattern.search(prompt):
                target = 0 if opening == "DOOR_ENTRY" else None
                indices = [target] if target is not None else range(len(modules))
                for index in indices:
                    ops.append({"op": "set_opening", "module": index, "opening": opening})
                notes.append(f"apertura {opening}")
                break
    return {
        "ops": ops,
        "notes": (
            "; ".join(notes) if notes else "No reconocí una acción de diseño en la instrucción."
        ),
        **({"clarify": clarify} if clarify else {}),
    }


def _design_alternatives_output(input_payload: dict) -> dict:
    """Mock brief → intent-level candidate specs. Deterministic per brief:
    a sliding mention proposes a corredera first, a door mention a porte,
    otherwise the classic fixed/operable/sliding spread — every candidate
    is still built and engine-validated server-side before it ships."""
    brief = str(input_payload.get("brief") or "").lower()
    count = max(1, min(3, int(input_payload.get("count") or 2)))
    candidates: list[dict] = []
    if re.search(r"corred|sliding|riel", brief):
        candidates.append(
            {
                "label": "Corredera de dos hojas",
                "rationale": "Una hoja corre sobre la otra — sin barrido interior.",
                "openings": ["SLIDING_2L"],
            }
        )
    if re.search(r"puerta|door|porte", brief):
        # A door candidate is only buildable with a panel — pick from the
        # catalog the request supplied, so the engine refusal isn't fake.
        door: dict = {
            "label": "Puerta de acceso",
            "rationale": "Hoja de paso con apertura abatible.",
            "openings": ["DOOR_ENTRY"],
        }
        panel_skus = (input_payload.get("catalog") or {}).get("panel_skus") or []
        if panel_skus:
            door["panel_sku"] = sorted(panel_skus)[0]
        candidates.append(door)
    if re.search(r"arco|bow|proa", brief):
        candidates.append(
            {
                "label": "Bow de tres paños",
                "rationale": "Tres módulos en quiebre suave.",
                "openings": ["FIXED", "FIXED", "FIXED"],
                "angle_deg": 22.5,
            }
        )
    candidates.append(
        {
            "label": "Paño fijo",
            "rationale": "Máxima luz y la solución más simple.",
            "openings": ["FIXED"],
        }
    )
    candidates.append(
        {
            "label": "Abatible + fijo",
            "rationale": "Ventilación practicable junto a un paño fijo.",
            "openings": ["TURN_LEFT", "FIXED"],
        }
    )
    if "SLIDING_2L" not in {op for c in candidates for op in c["openings"]}:
        candidates.append(
            {
                "label": "Corredera",
                "rationale": "Alternativa sin barrido hacia el interior.",
                "openings": ["SLIDING_2L"],
            }
        )
    # Propose real catalog materials like a provider should: a glass SKU on
    # glazed candidates, a coupler SKU on multi-module ones — both picked
    # only from what the request's catalog supplied.
    catalog = input_payload.get("catalog") or {}
    glass_skus = sorted(catalog.get("glass_skus") or [])
    coupler_skus = sorted(catalog.get("coupler_skus") or [])
    for candidate in candidates:
        if glass_skus and any(op != "DOOR_ENTRY" for op in candidate["openings"]):
            candidate.setdefault("glass_sku", glass_skus[0])
        if coupler_skus and len(candidate["openings"]) > 1:
            candidate.setdefault("coupler_sku", coupler_skus[0])
    return {
        "alternatives": candidates[:count],
        "notes": f"{min(len(candidates), count)} alternativas para revisar.",
    }


def _context_assist_output(input_payload: dict) -> dict:
    """Mock contextual answer: the answer cites real values straight from the
    server-built context — never invented. Deterministic per surface so tests
    and every environment exercise the same response contract a real provider
    must satisfy."""
    surface = str(input_payload.get("surface") or "dashboard")
    context = input_payload.get("context") or {}
    org = context.get("organization") or {}
    parts = [f"Estás en la superficie '{surface}' de {org.get('name') or 'tu organización'}."]
    counts = context.get("counts")
    if isinstance(counts, dict):
        parts.append(
            f"La organización registra {counts.get('projects', 0)} proyectos y "
            f"{counts.get('work_orders_open', 0)} órdenes de producción abiertas."
        )
    if isinstance(context.get("projects"), list):
        parts.append(f"Veo {len(context['projects'])} proyectos recientes en la lista.")
    if isinstance(context.get("systems"), list):
        parts.append(f"El catálogo muestra {len(context['systems'])} sistemas de perfiles.")
    if isinstance(context.get("work_orders"), list):
        parts.append(f"Hay {len(context['work_orders'])} órdenes de producción.")
    if context.get("order_code"):
        parts.append(f"La orden {context['order_code']} está en estado {context.get('status')}.")
        if context.get("shortages"):
            parts.append(f"Registra {context['shortages']} línea(s) con escasez de material.")
    if context.get("code") and context.get("positions") is not None:
        parts.append(
            f"El proyecto {context['code']} tiene {len(context['positions'])} posiciones."
        )
    warnings: list[str] = []
    if context.get("shortages"):
        warnings.append("La orden tiene líneas de material sin reservar.")
    answer = " ".join(parts) + (
        " Para una respuesta generativa configura un proveedor real en la ruta 'context_assist'."
    )
    question = str(
        input_payload.get("question") or input_payload.get("prompt") or ""
    ).lower()
    if re.search(r"oscilobatiente|abatible|diferencia", question):
        # Pregunta de dominio (G02) — el glosario del contrato IA2, citado
        # literal para que el mock satisfaga el mismo piso editorial que el
        # proveedor real.
        answer = (
            "La diferencia: una hoja abatible gira sobre bisagras laterales "
            "y se abre completa (ventilación total); la oscilobatiente "
            "combina dos movimientos — abatible desde el costado y "
            "proyectante basculante desde arriba — así ventila de noche "
            "sin abrir del todo."
        )
    return {
        "answer": answer,
        "actions": [],
        "warnings": warnings,
    }


# Ops `_design_assist_output` can emit that are legal in a batch proposal —
# mirrors agent.BATCH_OPS minus the structural set_module_count (batch only
# accepts adjust ops). Providers must not import agent.py, so the subset
# lives here.
_MOCK_BATCH_OPS = {
    "set_opening",
    "set_total_width",
    "set_height",
    "equalize_widths",
    "set_coupling_angle",
}

# Surfaces whose projection needs no entity refs — the only ones the mock can
# query (the agent payload doesn't carry refs, so ref-requiring surfaces would
# just produce a rejected observation).
_QUERYABLE_WITHOUT_REFS = {
    "dashboard",
    "projects",
    "catalog",
    "production",
    "clients",
    "purchasing",
    "settings",
    "morning_brief",
    "purchase_plan",
    "production_plan",
    "catalog_compiler",
}


def _agent_output(input_payload: dict) -> dict:
    """Mock agent round: a contract-valid JSON document built only from the
    server-built context — so dev/CI can exercise the flagship agent loop
    (grounding, steps, states) without a real provider. On the first round
    it emits a plan + a claim so the work-visibility channels render; on
    later rounds (observations present) it closes without new queries."""
    context = input_payload.get("context") or {}
    org = context.get("organization") or {}
    goal = str(input_payload.get("goal") or "")
    observations = input_payload.get("observations") or []
    surface_name = str(input_payload.get("surface") or "dashboard")
    org_name = str(org.get("name") or "la organización")
    reply = (
        f"Revisé el contexto de {org_name} para “{goal[:120]}”. "
        "Respuesta determinista del proveedor de prueba."
    )
    evidence = re.findall(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        json.dumps(context, default=str),
    )[:2]
    document: dict = {
        "reply": reply,
        "steps": [],
        "warnings": [],
        "plan": [{"label": "Revisar el contexto del producto"}],
        "claims": (
            [{"text": f"La organización activa es {org_name}.", "evidence": evidence}]
            if evidence
            else []
        ),
        "questions": [],
    }
    if not observations and surface_name in _QUERYABLE_WITHOUT_REFS:
        # Round 1 asks for the same surface's data — the server executes it
        # and returns observations; round 2 settles with the grounded reply.
        # Ref-requiring surfaces can't be queried without entity ids (the
        # payload doesn't carry them), so they settle in one round.
        document["steps"] = [{"kind": "query", "surface": surface_name, "refs": {}}]
    # The service passes the position's product at input_payload top level
    # (not inside context) — the mock must read the same place the prompt does.
    product = context.get("product") or input_payload.get("product")
    goal_l = goal.lower()

    # IA2 §2 — los números salen de herramientas del motor: el paso
    # {"kind":"tool"} se ejecuta server-side y su salida vuelve como
    # observación la ronda siguiente, donde el mock la cita tal cual.
    if not observations:
        position_ref = context.get("id") if surface_name == "position" else None
        project_ref = (
            context.get("id")
            if surface_name == "project"
            else (context.get("project") or {}).get("id")
            if isinstance(context.get("project"), dict)
            else None
        )
        position_ref = str(position_ref) if position_ref else None
        project_ref = str(project_ref) if project_ref else None
        if position_ref and re.search(r"pesa|peso", goal_l):
            document["steps"].append(
                {
                    "kind": "tool",
                    "name": "calculate_position",
                    "args": {"position_id": position_ref},
                }
            )
        if position_ref and re.search(r"guardar|bloque|v[aá]lid|herraje|compatib", goal_l):
            document["steps"].append(
                {
                    "kind": "tool",
                    "name": "validate_position",
                    "args": {"position_id": position_ref},
                }
            )
        if project_ref and re.search(
            r"m[aá]s\s+car|mayor\s+costo|precio.*posici|posici[oó]n.*(precio|costo)", goal_l
        ):
            document["steps"].append(
                {
                    "kind": "tool",
                    "name": "price_project",
                    "args": {"project_id": project_ref},
                }
            )
        if project_ref and re.search(r"falta.*emitir|emitir|emiti|falta", goal_l):
            document["steps"].append(
                {
                    "kind": "tool",
                    "name": "get_blockers",
                    "args": {"project_id": project_ref},
                }
            )
        if project_ref and re.search(r"compar|rev-?[ab]|subi|encarec|delta", goal_l):
            document["steps"].append(
                {
                    "kind": "tool",
                    "name": "explain_price_delta",
                    "args": {"project_id": project_ref},
                }
            )
        if surface_name == "production" and re.search(
            r"bloquead|atrasad|detenid|pendiente", goal_l
        ):
            # ¿Qué OT están bloqueadas? — profundiza cada orden visible:
            # los ids vienen del contexto (refs observados).
            for order in (context.get("work_orders") or [])[:3]:
                if order.get("id"):
                    document["steps"].append(
                        {
                            "kind": "query",
                            "surface": "work_order",
                            "refs": {"work_order_id": str(order["id"])},
                        }
                    )
        if surface_name == "purchase_plan" and re.search(
            r"compra|falta|cobertura", goal_l
        ):
            # Plan de compras borrador — líneas sin cobertura y proveedores
            # del contexto, agrupados por order_type como el prompt exige.
            lines = context.get("uncovered_lines") or []
            suppliers = context.get("suppliers") or []
            if lines:
                groups: dict[str, list] = {}
                for line in lines:
                    groups.setdefault(
                        str(line.get("order_type") or "OTHER"), []
                    ).append(
                        {
                            "requirement_key": line.get("requirement_key"),
                            "sku": line.get("sku"),
                            "quantity": line.get("quantity"),
                            "unit": line.get("unit"),
                            "project_code": line.get("project_code"),
                        }
                    )
                document["steps"].append(
                    {
                        "kind": "artifact",
                        "artifact": {
                            "kind": "purchase_plan",
                            "title": "Plan de compras",
                            "payload": {
                                "groups": [
                                    {
                                        "order_type": key,
                                        "lines": value,
                                        "suppliers": [
                                            str(item.get("supplier"))
                                            for item in suppliers
                                            if item.get("order_type") == key
                                        ],
                                    }
                                    for key, value in groups.items()
                                ]
                            },
                        },
                        "references": [
                            str(line.get("id")) for line in lines if line.get("id")
                        ],
                    }
                )
                document["reply"] = (
                    f"Preparé el plan de compras: {len(lines)} líneas sin "
                    "cobertura agrupadas por tipo de pedido, con los "
                    "proveedores elegibles del contexto."
                )

    if not observations and surface_name == "position" and product:
        # A mutation-looking goal on the position surface produces a real
        # design-ops proposal — the ops card → apply → Guardar path stays
        # exercisable under mock. The service validates each op through the
        # same contract a live provider hits.
        design = _design_assist_output(
            {
                "prompt": goal,
                "product": product,
                "catalog": input_payload.get("catalog") or context.get("catalog") or {},
            }
        )
        if design["ops"]:
            document["steps"].append(
                {"kind": "ops", "ops": design["ops"], "label": design["notes"]}
            )
        if design.get("clarify"):
            document["clarify"] = design["clarify"]
    elif not observations and surface_name == "project" and context.get("editable"):
        # IA2 §1 — el agente del proyecto opera posiciones con las mismas
        # ops tipadas que la API: crear, duplicar y lote sobre producto.
        positions = context.get("positions") or []
        measure = re.search(r"(\d+)\s*[×x]\s*(\d+)", goal)
        if re.search(r"crea|crear|agrega|nueva\s+posici", goal_l) and measure:
            # system_id real del contexto: la familia corredera cuando la
            # meta la nombra, si no el primer sistema activo del taller —
            # default documentado, nunca un UUID inventado.
            catalog_systems = context.get("systems") or []
            sliding_system = next(
                (
                    item
                    for item in catalog_systems
                    if isinstance(item, dict)
                    and "SLIDING" in str(item.get("family") or "").upper()
                ),
                None,
            )
            wants_sliding = bool(re.search(r"corred", goal_l))
            system = (
                sliding_system
                if wants_sliding and sliding_system is not None
                else catalog_systems[0]
                if catalog_systems and isinstance(catalog_systems[0], dict)
                else None
            )
            ops: list[dict] = [
                {
                    "op": "add_position",
                    "width_mm": measure.group(1),
                    "height_mm": measure.group(2),
                    **(
                        {"system_id": str(system["id"])}
                        if system is not None and system.get("id")
                        else {}
                    ),
                    **(
                        {"opening": "SLIDING_2L"}
                        if wants_sliding
                        else {}
                    ),
                    **(
                        {"location": "Cocina"}
                        if re.search(r"cocina", goal_l)
                        else {}
                    ),
                }
            ]
            document["steps"].append(
                {"kind": "ops", "ops": ops, "label": "crear posición"}
            )
        elif re.search(r"duplica|duplicar|copia", goal_l) and positions:
            wanted_index = None
            index_match = re.search(r"posici[oó]n\s*(\d+)", goal_l)
            if index_match:
                wanted_index = int(index_match.group(1))
            target = next(
                (
                    item
                    for item in positions
                    if int(item.get("index") or 0) == wanted_index
                ),
                positions[wanted_index - 1]
                if wanted_index and 0 < wanted_index <= len(positions)
                else None,
            )
            count = None
            count_match = re.search(r"(cuatro|tres|dos|cinco|\d+)\s+veces", goal_l)
            if count_match:
                raw = count_match.group(1)
                count = {"cuatro": 4, "tres": 3, "dos": 2, "cinco": 5}.get(
                    raw, int(raw) if raw.isdigit() else 0
                )
            if isinstance(target, dict) and target.get("id"):
                op: dict[str, object] = {
                    "op": "duplicate_position",
                    "position_id": str(target["id"]),
                }
                if count:
                    op["count"] = count
                document["steps"].append(
                    {"kind": "ops", "ops": [op], "label": "duplicar posición"}
                )
        elif re.search(r"vidrio|glass|termopanel|low-?e|dvh", goal_l) and re.search(
            r"todas|segundo\s*piso|[2２]\s*[º°o]?\s*piso|piso\s*2|piso", goal_l
        ):
            # Lote por ubicación: position_ids explícitos del contexto —
            # los que dicen "segundo piso"/"2º piso" (o todas si no hay
            # filtro). «Termopanel Low-E» mapea al SKU real del catálogo
            # demo — la propuesta siempre apunta a un artículo existente.
            wants_low_e = bool(re.search(r"low-?e|lowe", goal_l))
            floor_re = re.compile(r"segundo\s*piso|[2２]\s*[º°o]?\s*piso|piso\s*2")
            wants_floor = bool(floor_re.search(goal_l))
            filtered = [
                item for item in positions
                if floor_re.search(str(item.get("location") or "").lower())
            ] if wants_floor else positions
            if wants_low_e:
                sku = "VIDRIO-LOWE-24"
            else:
                sku_match = re.search(r"vidrio\s+a\s+([A-Z0-9-]+)|a\s+([A-Z0-9-]+)$", goal, re.I)
                sku = next(
                    (
                        group for group in (sku_match.groups() if sku_match else [])
                        if group
                    ),
                    "VIDRIO-BASE",
                ).upper()
            ids = [str(item["id"]) for item in filtered if item.get("id")]
            if ids:
                document["steps"].append(
                    {
                        "kind": "batch_ops",
                        "targets": {"position_ids": ids},
                        "ops": [{"op": "set_glass", "sku": sku}],
                        "label": f"vidrio {sku} en {len(ids)} posición(es)",
                    }
                )
        elif re.search(r"descuento|baja.*precio|precio.*%|%\s*de\s*desc", goal_l):
            # Sin op de precio: lo honesto es derivar a la superficie real.
            pid = str(context.get("id"))
            document["steps"].append(
                {
                    "kind": "navigate",
                    "path": f"/projects/{pid}/pricing",
                    "label": "Precios del proyecto",
                }
            )
            document["reply"] = (
                "Los descuentos no se aplican desde el asistente — en Precios "
                "puedes emitir una revisión con la banda correspondiente."
            )
        elif re.search(r"emit", goal_l):
            pid = str(context.get("id"))
            document["steps"].append(
                {
                    "kind": "prepare",
                    "action": "emit_revision",
                    "path": f"/projects/{pid}/pricing",
                    "label": "Preparar emisión de la revisión",
                }
            )
        else:
            # Same exercise for the batch card: "todas las fijas a abatible" on a
            # project drafts one op set against the positions the context shows.
            # Batch ops never carry a positional module index — refs differ per
            # position, so module-bound ops use the "*" wildcard the server
            # expands against each position's real summary.
            design = _design_assist_output({"prompt": goal, "product": {}})
            batch_ops = [
                {**op, "module": "*"} if "module" in op else op
                for op in design["ops"]
                if op.get("op") in _MOCK_BATCH_OPS
            ]
            # No product lives in the batch payload — the opening-keyboard loop
            # iterates modules, so scan the goal for an opening keyword directly.
            if not batch_ops:
                for pattern, opening in _OPENING_KEYWORDS:
                    if pattern.search(goal_l):
                        batch_ops.append(
                            {"op": "set_opening", "module": "*", "opening": opening}
                        )
                        break
            if batch_ops and positions:
                document["steps"].append(
                    {
                        "kind": "batch_ops",
                        "targets": {"typology": "ALL"},
                        "ops": batch_ops,
                        "label": design["notes"],
                    }
                )

    # Ronda 2 — las observaciones de herramienta se citan tal cual: el mock
    # cumple la misma regla que el prompt exige al proveedor real.
    wo_observations = [
        item
        for item in (observations or [])
        if isinstance(item, dict)
        and item.get("surface") == "work_order"
        and isinstance(item.get("context"), dict)
    ]
    if wo_observations:
        lines: list[str] = []
        for obs in wo_observations:
            ctx = obs["context"]
            pending = [
                str(step.get("label") or step.get("code"))
                for step in (ctx.get("steps") or [])
                if step.get("status") == "PENDING"
            ]
            reason = " por material faltante" if ctx.get("shortages") else ""
            lines.append(
                f"La {ctx.get('order_code')} está {ctx.get('status')}{reason}"
                + (
                    f"; pendiente: {', '.join(pending)}."
                    if pending
                    else "."
                )
            )
        document["reply"] = " ".join(lines)
    elif surface_name == "work_order" and re.search(
        r"barras|marco|plan de corte", goal_l
    ):
        # F02 — la proyección no expone el plan de corte: la respuesta
        # honesta es admitir el dato faltante, no inventar un número.
        document["reply"] = (
            "La proyección de la orden no dispone del plan de corte — "
            "las barras de marco no constan aquí; el dato vive en el "
            "expediente CNC de la OT."
        )
    elif surface_name == "dashboard" and re.search(
        r"precio|cu[aá]nto|aproximad", goal_l
    ):
        # G01 — sin motor no hay precio honesto para una ventana suelta.
        document["reply"] = (
            "No dispone de un cálculo del motor para una ventana suelta — "
            "el precio solo es real si lo calcula el motor. Puedo crear "
            "un borrador de posición y calcularlo ahí si quieres."
        )

    tool_observations = [
        item
        for item in (observations or [])
        if isinstance(item, dict) and item.get("tool") and item.get("output")
    ]
    if tool_observations:
        parts: list[str] = []
        for obs in tool_observations:
            name = str(obs.get("tool"))
            output = obs.get("output") or {}
            if not isinstance(output, dict) or output.get("ok") is False:
                parts.append(
                    f"La herramienta {name} no pudo responder: "
                    f"{output.get('error') if isinstance(output, dict) else 'error'}."
                )
                continue
            if name == "calculate_position":
                weights = output.get("leaf_weights") or []
                if weights:
                    parts.append(
                        f"La hoja derecha pesa {weights[-1].get('total_weight_kg')} kg "
                        f"según el BOM persistido."
                    )
                else:
                    parts.append(
                        "La posición no tiene cálculo persistido todavía "
                        "(has_bom=false) — guárdala para que el motor calcule."
                    )
            elif name == "validate_position":
                blockers = output.get("blockers") or []
                if blockers:
                    parts.append(
                        "Bloqueos del motor: "
                        + ", ".join(
                            str(item.get("code") or item) for item in blockers
                        )
                        + "."
                    )
                else:
                    parts.append(
                        "El motor no reporta bloqueos para la posición — "
                        "la validación viene limpia."
                    )
            elif name == "price_project":
                lines = [
                    item
                    for item in (output.get("positions") or [])
                    if isinstance(item, dict) and item.get("ok")
                ]
                if lines:
                    top = max(
                        lines, key=lambda item: float(item.get("line_cost") or 0)
                    )
                    parts.append(
                        f"La posición más cara es la {top.get('index')} "
                        f"({top.get('location') or 'sin ubicación'}): "
                        f"${int(float(top.get('line_cost') or 0)):,} "
                        f"{output.get('currency') or ''}.".replace(",", ".")
                    )
            elif name == "price_position":
                parts.append(
                    f"La posición cuesta ${output.get('unit_cost')} "
                    f"{output.get('currency') or ''} "
                    f"(línea: ${output.get('line_cost')})."
                )
            elif name == "get_blockers":
                missing = output.get("missing") or []
                if missing:
                    parts.append("Falta para emitir: " + ", ".join(map(str, missing)) + ".")
                else:
                    parts.append("No falta nada para emitir según el motor.")
            elif name == "explain_price_delta":
                deltas = output.get("positions") or []
                parts.append(
                    f"El delta contra la autoridad aplicada cubre "
                    f"{len(deltas)} posición(es) "
                    f"(has_applied={output.get('has_applied')})."
                )
            else:
                parts.append(f"{name}: {json.dumps(output, default=str)[:160]}.")
        if parts:
            document["reply"] = " ".join(parts)
    return document


class MockProvider:
    """Deterministic provider — a real output a test can assert, never I/O."""

    def invoke(
        self,
        *,
        route: dict,
        capability: str,
        input_payload: dict,
        provider_options: dict | None = None,
        operation_key: str | None = None,
        # Mock performs no fetch — the parameter exists so the service passes
        # the resolved document path uniformly across providers.
        document_path: str | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        digest = hashlib.sha256(
            json.dumps(input_payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        if capability == "design_assist":
            output = json.dumps(_design_assist_output(input_payload), ensure_ascii=False)
        elif capability == "design_alternatives":
            output = json.dumps(
                _design_alternatives_output(input_payload), ensure_ascii=False
            )
        elif capability == "context_assist":
            output = json.dumps(
                _context_assist_output(input_payload), ensure_ascii=False
            )
        elif capability == "agent":
            output = json.dumps(
                _agent_output(input_payload), ensure_ascii=False
            )
        else:
            output = (
                f"{route['public_name']} [{capability}] respuesta determinista para {digest}"
            )
        serialized = json.dumps(input_payload, default=str)
        return {
            "output": output,
            "tokens_prompt": max(1, len(serialized) // 8),
            "tokens_completion": max(1, len(output) // 8),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }


# Providers that speak the OpenAI chat-completions protocol out of the box;
# AI_GATEWAY_{P}_PROTOCOL = openai|http overrides the registry either way.
_OPENAI_PROTOCOL_PROVIDERS = {"MIMO", "OPENAI", "OPENROUTER", "DEEPSEEK", "QWEN"}


def provider_for(route: dict):
    name = str(route["provider"]).upper()
    if name == "MOCK":
        if not _mock_enabled():
            raise ProviderError("ai_provider_mock_disabled")
        return MockProvider()
    # Per-capability transport options from ai_routes: NULL keeps the
    # provider's env/default bound.
    timeout_s = route.get("timeout_s")
    retry_max = route.get("retry_max")
    protocol = os.environ.get(f"AI_GATEWAY_{name}_PROTOCOL", "").lower()
    if protocol == "openai" or (not protocol and name in _OPENAI_PROTOCOL_PROVIDERS):
        return OpenAICompatibleProvider(
            provider=name, timeout_s=timeout_s, retry_max=retry_max
        )
    return HttpProvider(provider=name, timeout_s=timeout_s, retry_max=retry_max)
