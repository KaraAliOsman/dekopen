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


def _mock_enabled() -> bool:
    """Whether the deterministic MOCK provider may serve this deployment.
    Explicit AI_GATEWAY_MOCK_ENABLED wins either way; otherwise it serves
    only development (DEBUG) and the test suite (pytest sets
    PYTEST_CURRENT_TEST) — a production stack can never answer silently
    with fabricated content."""
    explicit = os.environ.get("AI_GATEWAY_MOCK_ENABLED", "").lower()
    if explicit in {"1", "true", "yes"}:
        return True
    if explicit in {"0", "false", "no"}:
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


class ProviderError(Exception):
    """Sanitized provider failure — never carries credentials or payloads."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class HttpProvider:
    """Generic JSON invocation endpoint: POST {model, capability, input}."""

    def __init__(self, *, provider: str):
        self.provider = provider
        self.api_key = os.environ.get(f"AI_GATEWAY_{provider}_API_KEY", "")
        self.base_url = os.environ.get(f"AI_GATEWAY_{provider}_BASE_URL", "").rstrip("/")
        if not self.api_key or not self.base_url:
            raise ProviderError("ai_provider_unavailable")
        # AI_GATEWAY_{P}_TIMEOUT_S bounds the whole HTTP exchange. A malformed
        # value is a deployment mistake — it fails visibly, never clamps
        # silently to an operator-surprising bound.
        self.timeout = _timeout_seconds(provider)
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
        with client.stream(
            "POST",
            f"https://{url_host}{port_suffix}{path}",
            headers=headers,
            extensions={"sni_hostname": self._host},
            json=body,
        ) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes(65536):
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
        raise ProviderError("ai_provider_error") from last_error

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
        options = provider_options or {}
        # The model must fit the provenance column BEFORE the paid call runs —
        # an env override longer than VARCHAR(120) would otherwise fail the
        # sealed audit after inference already happened.
        requested_model = self._requested_model(route)
        if not (0 < len(requested_model) <= 120):
            raise ProviderError("ai_provider_error")
        try:
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
            content = self._request(
                route=route,
                capability=capability,
                input_payload=wire_input,
                provider_options=options,
                client=client,
                operation_key=operation_key,
            )
            parsed = self._parse_response(content)
            tokens_prompt = int(parsed["tokens_prompt"])
            tokens_completion = int(parsed["tokens_completion"])
            # Usage feeds an INT4 audit column — a malformed or impossible count
            # is a provider error, not an audit-time database exception raised
            # after the paid call already succeeded.
            if not (
                0 <= tokens_prompt <= 2_147_483_647 and 0 <= tokens_completion <= 2_147_483_647
            ):
                raise TypeError("provider token usage is outside the audit range")
        except ProviderError:
            raise
        except httpx.HTTPStatusError as error:
            # The provider answered — the status class is the diagnosis an
            # operator needs (bad key vs bad model vs spent quota), and the
            # effective model identifies which pin/override was actually sent.
            status = error.response.status_code
            logger.warning(
                "AI provider %s answered %s (model=%s capability=%s)",
                self.provider,
                status,
                requested_model,
                capability,
            )
            if status in (401, 403):
                raise ProviderError("ai_provider_auth") from error
            if status == 429:
                raise ProviderError("ai_provider_quota") from error
            if 400 <= status < 500:
                raise ProviderError("ai_provider_rejected") from error
            raise ProviderError("ai_provider_error") from error
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise ProviderError("ai_provider_error") from error
        response_model = parsed.get("model")
        return {
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

    def __init__(self, *, provider: str):
        super().__init__(provider=provider)
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
        body: dict[str, Any] = {
            "model": self._requested_model(route),
            "messages": [
                {
                    "role": "system",
                    "content": str(provider_options.get("system") or _DEFAULT_SYSTEM),
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
        }
        if provider_options.get("json_output"):
            body["response_format"] = {"type": "json_object"}
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
        output = message.get("content") if isinstance(message, dict) else None
        if not isinstance(output, str):
            raise TypeError("provider output is not a string")
        usage = body.get("usage") or {}
        if not isinstance(usage, dict):
            raise TypeError("provider usage is not an object")
        return {
            "output": output,
            "tokens_prompt": int(usage.get("prompt_tokens") or 0),
            "tokens_completion": int(usage.get("completion_tokens") or 0),
            "model": body["model"] if isinstance(body.get("model"), str) else None,
        }


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
    a human note, deterministic per prompt so environments and tests agree."""
    prompt = str(input_payload.get("prompt") or "").lower()
    product = input_payload.get("product") or {}
    modules = product.get("modules") or []
    couplings = product.get("couplings") or []
    ops: list[dict] = []
    notes: list[str] = []
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
        ops.append({"op": "equalize_widths"})
        notes.append("anchos iguales")
    if re.search(r"arco|bow|proa", prompt) and couplings:
        for index, _ in enumerate(couplings):
            ops.append({"op": "set_coupling_angle", "coupling": index, "angle_deg": 22.5})
        notes.append("ángulos de arco 22.5°")
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
    return {
        "answer": " ".join(parts)
        + " Para una respuesta generativa configura un proveedor real en la ruta 'context_assist'.",
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
        "Respuesta determinista del proveedor MOCK."
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
    if not observations and surface_name == "position" and product:
        # A mutation-looking goal on the position surface produces a real
        # design-ops proposal — the ops card → apply → Guardar path stays
        # exercisable under mock. The service validates each op through the
        # same contract a live provider hits.
        design = _design_assist_output({"prompt": goal, "product": product})
        if design["ops"]:
            document["steps"].append(
                {"kind": "ops", "ops": design["ops"], "label": design["notes"]}
            )
    elif not observations and surface_name == "project" and context.get("editable"):
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
                if pattern.search(goal.lower()):
                    batch_ops.append(
                        {"op": "set_opening", "module": "*", "opening": opening}
                    )
                    break
        if batch_ops and context.get("positions"):
            document["steps"].append(
                {
                    "kind": "batch_ops",
                    "targets": {"typology": "ALL"},
                    "ops": batch_ops,
                    "label": design["notes"],
                }
            )
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
    protocol = os.environ.get(f"AI_GATEWAY_{name}_PROTOCOL", "").lower()
    if protocol == "openai" or (not protocol and name in _OPENAI_PROTOCOL_PROVIDERS):
        return OpenAICompatibleProvider(provider=name)
    return HttpProvider(provider=name)
