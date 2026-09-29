"""AI gateway invoke: one transaction binding entitlement, provider call,
immutable audit and wallet debit (PRD-13 pre/post-invocation hooks).

The org row lock (reconcile → FOR UPDATE) serializes AI spend per tenant —
but only around its own mutations: the balance check runs BEFORE any
provider HTTP so a broke wallet cancels the call before the request exists,
the provider call itself runs outside the lock, and audit + debit re-enter
it (debit re-checks the balance under the lock, so two concurrent invokes
still can't overspend). Tenants only ever see public_name — provider and
model stay sealed in the audit row."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from authentication.errors import contract_error
from ai_gateway.providers import ProviderError, provider_for
from billing import wallet
from documents.repository import DocumentaryError, rows
from documents.storage import readable_storage_key

RETENTION_DAYS = 90
MAX_OUTPUT_CHARS = 256_000

# input_payload is client-supplied and audited verbatim — server-only keys can
# never arrive through it. A provider call that needs a document names an owned
# source row via "source"; the service resolves that row under the active org
# and signs only the canonical stored object (never a client-chosen path).
_RESERVED_INPUT_KEYS = frozenset({"storage_path", "document_url"})
_SOURCE_TABLES = {
    "document_import": ("public.document_imports", "imports"),
    "catalog_import": ("public.catalog_imports", "catalog-imports"),
}


def _source_document_path(org_id: UUID, source: object) -> str | None:
    """Resolve a declared source reference to its canonical storage object key.

    The row must belong to the active org and the stored key must live under
    that org's canonical prefix — a corrupted row can never mint a URL for a
    foreign object, and no client input ever reaches the signer."""
    if source is None:
        return None
    # The source contract is exactly {kind, id} — an extra key (e.g. a nested
    # storage_path smuggle) makes the whole reference invalid rather than
    # being silently ignored in the audited input.
    if not isinstance(source, dict) or set(source) != {"kind", "id"}:
        raise contract_error(
            400,
            "ai_source_invalid",
            "La referencia de documento no es válida.",
        )
    table_prefix = _SOURCE_TABLES.get(str(source.get("kind")))
    try:
        source_id = UUID(str(source.get("id")))
    except (ValueError, AttributeError, TypeError):
        source_id = None
    if table_prefix is None or source_id is None:
        raise contract_error(
            400,
            "ai_source_invalid",
            "La referencia de documento no es válida.",
        )
    table, prefix = table_prefix
    found = rows(
        f"SELECT storage_path FROM {table} WHERE id=%s AND org_id=%s",
        [str(source_id), str(org_id)],
    )
    if not found:
        raise contract_error(
            404,
            "ai_source_not_found",
            "El documento de origen no existe o no pertenece a tu organización.",
        )
    path = str(found[0]["storage_path"])
    if not path.startswith(f"{prefix}/{org_id}/"):
        # Server-side data corruption — the stored object key must live under
        # the org's canonical prefix; refuse rather than sign a foreign object.
        raise ProviderError("ai_source_unreadable")
    try:
        # Read-path rule: a '%' written through the upload path stays
        # readable — anything that could escape the bucket still refuses.
        readable_storage_key(path)
    except DocumentaryError:
        raise ProviderError("ai_source_unreadable") from None
    return path


def _route(capability: str) -> dict | None:
    found = rows(
        "SELECT * FROM public.ai_routes WHERE capability=%s AND enabled",
        [capability],
    )
    return found[0] if found else None


def _input_hash(input_payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(input_payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _response(*, audit: dict, capability: str, route: dict, result: dict) -> dict:
    """The white-label invoke envelope — replayed verbatim on idempotent retries."""
    return {
        "audit_id": str(audit["id"]),
        "capability": capability,
        "model": route["public_name"],
        "output": result["output"],
        "tokens_prompt": int(result["tokens_prompt"]),
        "tokens_completion": int(result["tokens_completion"]),
        "latency_ms": int(result["latency_ms"]),
        "credits_debited": int(route["credits_cost"]),
    }


def _replay(
    *,
    org_id: UUID,
    operation_key: str,
    capability: str,
    tool_name: str | None,
    input_hash: str,
) -> dict | None:
    """The stored response of a completed operation, or None when no audit won
    this key. The org row lock (reconcile FOR UPDATE) makes the winner's commit
    visible here before any provider work is spent."""
    found = rows(
        "SELECT id, tool_name, state_hash_before, output_payload "
        "FROM public.ai_audit_logs WHERE org_id=%s AND operation_key=%s",
        [str(org_id), operation_key],
    )
    if not found:
        return None
    audit = found[0]
    envelope = audit["output_payload"] or {}
    if isinstance(envelope, str):
        envelope = json.loads(envelope)
    if (
        envelope.get("capability") != capability
        or audit["state_hash_before"] != input_hash
        or (audit["tool_name"] or capability) != (tool_name or capability)
    ):
        raise contract_error(
            409,
            "ai_operation_conflict",
            "La clave de operación ya fue usada con una solicitud distinta.",
        )
    return {"audit_id": str(audit["id"]), **envelope}


def _audit(
    *,
    org_id: UUID,
    user_id: UUID,
    route: dict,
    tool_name: str,
    operation_key: str,
    input_payload: dict,
    result: dict,
    response: dict,
) -> dict | None:
    inserted = rows(
        "INSERT INTO public.ai_audit_logs("
        "org_id, user_id, tool_name, model_used, prompt_version, retention_until,"
        " input_payload, output_payload, points_debited,"
        " tokens_prompt, tokens_completion, latency_ms, state_hash_before,"
        " operation_key, route_id)"
        " VALUES(%s,%s,%s,%s,%s, now() + %s * interval '1 day',%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        " ON CONFLICT (org_id, operation_key) WHERE operation_key IS NOT NULL DO NOTHING"
        " RETURNING *",
        [
            str(org_id),
            str(user_id),
            tool_name,
            # Audit rows are tenant-readable — model_used stores the white-label
            # name. Provider provenance lives behind route_id, an opaque FK only
            # the backend role can join to the sealed provider/model internals.
            str(route["public_name"]),
            str(route["prompt_version"]),
            RETENTION_DAYS,
            json.dumps(input_payload, default=str),
            json.dumps(response, default=str),
            int(route["credits_cost"]),
            int(result["tokens_prompt"]),
            int(result["tokens_completion"]),
            int(result["latency_ms"]),
            _input_hash(input_payload),
            operation_key,
            str(route["id"]),
        ],
    )
    if inserted:
        # Seal the exact provider/model/prompt at invocation time — route_id
        # alone would re-attribute history after a route edit. Provenance is
        # backend-only (billing_backend), the same role writing here.
        rows(
            "INSERT INTO public.ai_audit_provenance("
            "audit_id, provider, provider_model, prompt_version)"
            " VALUES(%s,%s,%s,%s) RETURNING audit_id",
            [
                str(inserted[0]["id"]),
                str(route["provider"]),
                # The model the request actually ran on (provider-reported or
                # its configured override) — never the route's label when the
                # transport selected another model behind it.
                str(result.get("model") or route["provider_model"]),
                str(route["prompt_version"]),
            ],
        )
    return inserted[0] if inserted else None


def invoke(
    *,
    org_id: UUID,
    user_id: UUID,
    capability: str,
    operation_key: str,
    input_payload: dict,
    tool_name: str | None = None,
    provider_options: dict | None = None,
) -> dict[str, Any]:
    # provider_options is server-side transport config (system prompt, output
    # mode). It is deliberately NOT part of input_payload: that hash covers the
    # client's request semantics so a prompt-version change can never break
    # replay, and the generic invoke endpoint can never smuggle in control keys.
    if _RESERVED_INPUT_KEYS.intersection(input_payload):
        raise contract_error(
            400,
            "ai_input_rejected",
            "La entrada contiene claves reservadas del servidor.",
        )
    input_hash = _input_hash(input_payload)
    with wallet.financial_transaction(org_id):
        organization = wallet.reconcile(org_id)
        # Idempotency: a retry of a completed operation replays its stored
        # response — no second provider call, no second debit.
        replay = _replay(
            org_id=org_id,
            operation_key=operation_key,
            capability=capability,
            tool_name=tool_name,
            input_hash=input_hash,
        )
        if replay is not None:
            return replay
        if (
            organization["subscription_tier"] == "STARTER"
            or not organization["subscription_active"]
        ):
            raise contract_error(
                409,
                "ai_entitlement_required",
                "Tu plan conserva todas las funciones manuales.",
            )
        route = _route(capability)
        if route is None:
            raise contract_error(
                404,
                "ai_capability_unknown",
                "La capacidad de IA solicitada no está disponible.",
            )
        credits = int(route["credits_cost"])
        # Pre-invocation hook: balance is checked while the org row is locked,
        # before any provider request exists — never debit after the fact.
        if int(organization["credits_balance"]) < credits:
            raise contract_error(
                409,
                "insufficient_credits",
                "No quedan créditos suficientes para esta operación de IA.",
            )
        # A declared source resolves to its canonical object key under the
        # active org; the provider signs exactly that path at wire time —
        # never a path the request supplied.
        document_path = _source_document_path(org_id, input_payload.get("source"))
    # The provider call runs OUTSIDE the wallet lock — holding the org row
    # FOR UPDATE across a network call would serialize every tenant request
    # behind provider latency (and a hung provider behind its full timeout).
    result = provider_for(route).invoke(
        route=route,
        capability=capability,
        input_payload=input_payload,
        provider_options=provider_options,
        document_path=document_path,
        # The wire key is org-namespaced: a real provider dedupes on the
        # header globally, so the raw org-scoped key alone would collide
        # across tenants sharing a capability-level key prefix.
        operation_key=f"{org_id}:{operation_key}",
    )
    if len(str(result["output"])) > MAX_OUTPUT_CHARS:
        raise ProviderError("ai_provider_output_too_large")
    with wallet.financial_transaction(org_id):
        wallet.reconcile(org_id)
        # A concurrent invoke may have committed while the provider ran —
        # replay must be re-checked under the lock before spending again.
        replay = _replay(
            org_id=org_id,
            operation_key=operation_key,
            capability=capability,
            tool_name=tool_name,
            input_hash=input_hash,
        )
        if replay is not None:
            return replay
        audit = _audit(
            org_id=org_id,
            user_id=user_id,
            route=route,
            tool_name=tool_name or capability,
            operation_key=operation_key,
            input_payload=input_payload,
            result=result,
            response={
                "capability": capability,
                "model": route["public_name"],
                "output": result["output"],
                "tokens_prompt": int(result["tokens_prompt"]),
                "tokens_completion": int(result["tokens_completion"]),
                "latency_ms": int(result["latency_ms"]),
                "credits_debited": credits,
            },
        )
        if audit is None:
            # The loser of a concurrent same-key invoke replays the winner's
            # stored response instead of double-debiting.
            return _replay(
                org_id=org_id,
                operation_key=operation_key,
                capability=capability,
                tool_name=tool_name,
                input_hash=input_hash,
            )
        wallet.debit(org_id, credits, audit["id"])
        return _response(audit=audit, capability=capability, route=route, result=result)


__all__ = ["ProviderError", "invoke"]
