"""Customer quote-approval links: public token-scoped reads and decisions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import secrets
from typing import Iterator
from uuid import UUID

from django.db import DatabaseError, connection, transaction
from psycopg import sql

from authentication.rls import tx_aborted
from documents.artifacts import SupabaseDocumentStorage, generate_artifact
from documents.brand import effective_brand_color
from documents.renderers import finish_label, frozen_glass_specs
from documents.repository import (
    DocumentaryError,
    decoded,
    documentary_backend,
    one,
    rows,
    write,
)
from mail.service import _frontend_origin
from rut import rut_mod11_valid

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32
_APPROVAL_TTL_DAYS = 30


@contextmanager
def portal_backend() -> Iterator[None]:
    """Switch to the portal role — the share token is the only capability.

    No JWT exists on public requests, so org scoping happens in the queries:
    every row is joined back to the approval's own ``org_id``/ids.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('role')")
        previous = str(cursor.fetchone()[0])
        if previous == "none":
            previous = "authenticated"
        cursor.execute("SET LOCAL ROLE portal_backend")
    try:
        yield
    except DatabaseError:
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous))
                )
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous))
                )


def share_quote(
    *, org_id: UUID, project_id: UUID, actor_id: UUID, role: str
) -> dict[str, object]:
    """Mint a fresh approval link for the project's latest sealed version."""
    with documentary_backend():
        project = one(
            "SELECT id,status FROM public.projects WHERE id=%s AND org_id=%s",
            [project_id, org_id],
            "project_not_found",
        )
        if str(project["status"]) not in ("QUOTED", "APPROVED"):
            raise DocumentaryError("quote_share_requires_quoted")
        versions = rows(
            "SELECT id FROM public.project_versions "
            "WHERE project_id=%s AND org_id=%s ORDER BY emitted_at DESC LIMIT 1",
            [project_id, org_id],
        )
        if not versions:
            raise DocumentaryError("version_not_found")
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(days=_APPROVAL_TTL_DAYS)
    minted_ids: list[UUID] = []
    with transaction.atomic(), documentary_backend():
        # A fresh share supersedes every outstanding EMAIL/FOLLOW link for
        # this revision — otherwise pending tokens accumulate and stay
        # concurrently valid. DOCUMENT-channel approvals survive: the QR
        # sealed inside the stored DOC-01 names that token, and the PDF is
        # immutable evidence that must keep resolving. CHANGES_REQUESTED
        # counts as outstanding: re-sharing answers the client's request
        # with a fresh live link.
        rows(
            "UPDATE public.customer_approvals SET status='REVOKED',revoked_at=%s,"
            "revoked_by=%s WHERE org_id=%s AND project_id=%s "
            "AND project_version_id=%s AND status IN ('PENDING','CHANGES_REQUESTED') "
            "AND channel IN ('EMAIL','FOLLOW') "
            "RETURNING id",
            [
                datetime.now(timezone.utc),
                str(actor_id),
                str(org_id),
                str(project_id),
                str(versions[0]["id"]),
            ],
        )
        minted = one(
            "INSERT INTO public.customer_approvals "
            "(org_id,project_id,project_version_id,token_hash,expires_at,created_by) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            [
                str(org_id),
                str(project_id),
                str(versions[0]["id"]),
                hashlib.sha256(token.encode()).hexdigest(),
                expires_at,
                str(actor_id),
            ],
        )
        minted_ids.append(minted["id"])
        # The document's acceptance QR needs a link that outlives re-shares:
        # an EMAIL token dies on the next share, so the sealed PDF embeds a
        # DOCUMENT-channel approval minted the first time its artifact is
        # produced. The slot is immutable — when the PDF already exists we
        # mint nothing (its QR, if any, belongs to the original share).
        slot_taken = rows(
            "SELECT id FROM public.document_artifacts "
            "WHERE org_id=%s AND project_version_id=%s "
            "AND artifact_scope='PROJECT_REVISION' AND artifact_scope_id=%s "
            "AND document_type='DOC-01' AND format='PDF'",
            [org_id, versions[0]["id"], versions[0]["id"]],
        )
        if not slot_taken:
            document_token = secrets.token_urlsafe(_TOKEN_BYTES)
            document_approval = one(
                "INSERT INTO public.customer_approvals "
                "(org_id,project_id,project_version_id,token_hash,expires_at,"
                "created_by,channel) VALUES (%s,%s,%s,%s,%s,%s,'DOCUMENT') "
                "RETURNING id",
                [
                    str(org_id),
                    str(project_id),
                    str(versions[0]["id"]),
                    hashlib.sha256(document_token.encode()).hexdigest(),
                    expires_at,
                    str(actor_id),
                ],
            )
            minted_ids.append(document_approval["id"])
    # DOC-01 generates AFTER minting so the acceptance block can carry the
    # document link (QR + URL). A render failure revokes every approval
    # minted above — no stranded token whose document nobody can produce.
    if not slot_taken:
        try:
            generate_artifact(
                org_id=org_id,
                actor_id=actor_id,
                role=role,
                project_version_id=versions[0]["id"],
                order_id=None,
                document_type="DOC-01",
                file_format="PDF",
                render_context={
                    "approval_url": (
                        f"{_frontend_origin()}/cotizacion/{document_token}"
                    )
                },
            )
        except Exception:
            with documentary_backend():
                rows(
                    "UPDATE public.customer_approvals SET status='REVOKED',"
                    "revoked_at=%s,revoked_by=%s WHERE id = ANY(%s::uuid[]) "
                    "AND status='PENDING'",
                    [datetime.now(timezone.utc), str(actor_id), minted_ids],
                )
            raise
    with documentary_backend():
        # P25: enlace de cotización al cliente por correo — el handler renderiza
        # white-label con la marca del org y registra mail_messages vía outbox.
        from automations.service import emit

        emit(
            "mail.quote_sent",
            org_id=org_id,
            actor_id=actor_id,
            idempotency_key=f"mail:quote-sent:{minted_ids[0]}",
            project_id=str(project_id),
            token=token,
        )
    return {"token": token, "expires_at": expires_at}


def revoke_link(
    *, org_id: UUID, project_id: UUID, approval_id: UUID, actor_id: UUID
) -> dict[str, object]:
    """Kill a PENDING link. Decided links stay on the record — revocation is
    an off switch for an unanswered share, not a way to un-decide a client."""
    with documentary_backend():
        approval = one(
            "SELECT id,status FROM public.customer_approvals "
            "WHERE id=%s AND org_id=%s AND project_id=%s",
            [str(approval_id), str(org_id), str(project_id)],
            "approval_not_found",
        )
        if str(approval["status"]) == "REVOKED":
            return approval
        if str(approval["status"]) != "PENDING":
            raise DocumentaryError("approval_not_pending")
        return one(
            "UPDATE public.customer_approvals SET status='REVOKED',revoked_at=%s,"
            "revoked_by=%s WHERE id=%s AND status='PENDING' RETURNING id,status",
            [datetime.now(timezone.utc), str(actor_id), str(approval_id)],
        )


def update_link_expiry(
    *, org_id: UUID, project_id: UUID, approval_id: UUID, expires_at: datetime
) -> dict[str, object]:
    """Move a live link's expiry — never resurrects a dead one, never
    touches a decided one (the decision record keeps its timestamps)."""
    if expires_at <= datetime.now(timezone.utc):
        raise DocumentaryError("link_expiry_invalid")
    with documentary_backend():
        approval = one(
            "SELECT id,status FROM public.customer_approvals "
            "WHERE id=%s AND org_id=%s AND project_id=%s",
            [str(approval_id), str(org_id), str(project_id)],
            "approval_not_found",
        )
        if str(approval["status"]) not in ("PENDING", "CHANGES_REQUESTED"):
            raise DocumentaryError("approval_not_live")
        return one(
            "UPDATE public.customer_approvals SET expires_at=%s "
            "WHERE id=%s AND status IN ('PENDING','CHANGES_REQUESTED') "
            "RETURNING id,expires_at",
            [expires_at, str(approval_id)],
            "approval_not_found",
        )



def list_approvals(*, org_id: UUID, project_id: UUID) -> list[dict[str, object]]:
    """The org-side record of every link minted for a project: who it went
    to (the token stays opaque — the link URL is the capability), which
    revision it carried, and how the client answered."""
    with documentary_backend():
        one(
            "SELECT id FROM public.projects WHERE id=%s AND org_id=%s",
            [str(project_id), str(org_id)],
            "project_not_found",
        )
        return [
            {
                "id": str(row["id"]),
                "status": str(row["status"]),
                "channel": str(row["channel"]),
                "revision_code": str(row["revision_code"]),
                "decided_by": row["decided_by"],
                "decided_at": row["decided_at"].isoformat()
                if row["decided_at"]
                else None,
                "expires_at": row["expires_at"].isoformat(),
                "created_at": row["created_at"].isoformat(),
                "revoked_at": row["revoked_at"].isoformat()
                if row["revoked_at"]
                else None,
                "decided_note": row["decided_note"],
                # P10 — la evidencia completa de la última decisión: quién
                # firmó, su RUT, el texto aceptado, revisión y huella, IP y
                # agente. Sin evento (enlaces de antes de P10) queda null.
                "evidence": (
                    {
                        "decision": str(row["ev_decision"]),
                        "decided_by": row["ev_decided_by"],
                        "decided_rut": row["ev_decided_rut"],
                        "decided_note": row["ev_decided_note"],
                        "decision_ip": str(row["ev_ip"]) if row["ev_ip"] else None,
                        "decision_user_agent": row["ev_ua"],
                        "acceptance_text": row["ev_acceptance"],
                        "revision_code": row["ev_revision"],
                        "bom_hash": row["ev_bom"],
                        "positions": decoded(row["ev_positions"]) or [],
                        "created_at": row["ev_at"].isoformat(),
                    }
                    if row["ev_decision"] is not None
                    else None
                ),
                "view_count": int(row["view_count"] or 0),
                "first_viewed_at": row["first_viewed_at"].isoformat()
                if row["first_viewed_at"]
                else None,
                "last_viewed_at": row["last_viewed_at"].isoformat()
                if row["last_viewed_at"]
                else None,
            }
            for row in rows(
                "SELECT a.id,a.status,a.channel,a.decided_by,a.decided_at,a.decided_note,"
                "a.expires_at,a.created_at,a.revoked_at,a.view_count,"
                "a.first_viewed_at,a.last_viewed_at,"
                "v.revision_code,"
                "e.decision AS ev_decision,e.decided_by AS ev_decided_by,"
                "e.decided_rut AS ev_decided_rut,e.decided_note AS ev_decided_note,"
                "e.decision_ip AS ev_ip,e.decision_user_agent AS ev_ua,"
                "e.acceptance_text AS ev_acceptance,e.revision_code AS ev_revision,"
                "e.bom_hash AS ev_bom,e.positions AS ev_positions,e.created_at AS ev_at "
                "FROM public.customer_approvals a "
                "JOIN public.project_versions v "
                "ON v.id = a.project_version_id "
                "LEFT JOIN LATERAL ("
                "  SELECT * FROM public.customer_approval_events ev "
                "  WHERE ev.approval_id = a.id "
                "  ORDER BY ev.created_at DESC, ev.id DESC LIMIT 1"
                ") e ON true "
                "WHERE a.org_id=%s AND a.project_id=%s "
                "ORDER BY a.created_at DESC",
                [str(org_id), str(project_id)],
            )
        ]


def _validity_expired(value: object) -> bool:
    """Sealed ``quotation_valid_until`` — a malformed date is a data defect,
    not a crash: the public read must surface a contract error, not a 500."""
    if not value:
        return False
    try:
        return date.fromisoformat(str(value)) < datetime.now(timezone.utc).date()
    except ValueError:
        raise DocumentaryError("quotation_valid_until_invalid") from None


def _lookup_approval(token: str) -> dict[str, object]:
    """The token's row — the only unscoped portal query (hash → its own row).

    Never raises for dead-but-real links: revoked and expired tokens still
    resolve so their dedicated honest states render; mutations call
    ``_require_live`` to refuse them.
    """
    found = rows(
        "SELECT * FROM public.customer_approvals WHERE token_hash=%s",
        [hashlib.sha256(token.encode()).hexdigest()],
    )
    if len(found) != 1:
        raise DocumentaryError("quote_not_found")
    return found[0]


def _require_live(approval: dict[str, object]) -> None:
    if approval["status"] == "REVOKED":
        raise DocumentaryError("quote_revoked")
    if approval["expires_at"] < datetime.now(timezone.utc):
        raise DocumentaryError("quote_expired")


def _approval_for_token(token: str) -> dict[str, object]:
    approval = _lookup_approval(token)
    _require_live(approval)
    return approval


def _scope_org(org_id: object) -> None:
    """Bind the portal role to the approval's tenant for this transaction.

    Portal policies on every other table require ``org_id`` to equal the
    ``app.portal_org_id`` GUC — the token lookup is the only query that runs
    unscoped, and it only touches the token's own row by hash.
    """
    rows("SELECT set_config('app.portal_org_id', %s, true)", [str(org_id)])


def _bound_version(approval: dict[str, object]) -> dict[str, object]:
    return one(
        "SELECT revision_code,emitted_at,bom_hash,"
        "snapshot_json::text AS snapshot_json "
        "FROM public.project_versions "
        "WHERE id=%s AND org_id=%s AND project_id=%s",
        [approval["project_version_id"], approval["org_id"], approval["project_id"]],
        "version_not_found",
    )


def _sealed_project(version: dict[str, object]) -> dict[str, object]:
    """The immutable project payload captured when the revision was sealed."""
    snapshot = decoded(version["snapshot_json"])
    sealed = snapshot.get("project") if isinstance(snapshot, dict) else None
    return sealed if isinstance(sealed, dict) else {}


def _live_project(approval: dict[str, object], *, for_update: bool = False) -> dict[str, object]:
    return one(
        "SELECT status,current_revision FROM public.projects "
        "WHERE id=%s AND org_id=%s" + (" FOR UPDATE" if for_update else ""),
        [approval["project_id"], approval["org_id"]],
        "project_not_found",
    )


def _sealed_positions(version: dict[str, object]) -> list[dict[str, object]]:
    """The proposal's position cards — immutable snapshot rows, not live data."""
    snapshot = decoded(version["snapshot_json"])
    values = snapshot.get("positions") if isinstance(snapshot, dict) else None
    if not isinstance(values, list):
        return []
    positions = []
    for value in values:
        if not isinstance(value, dict):
            continue
        glass_specs: list[str] = []
        finish = ""
        try:
            glass_specs = frozen_glass_specs(value)
            finish = str(value.get("finish") or "") or finish_label(
                value.get("color_interior"), value.get("color_exterior"))
        except DocumentaryError:
            glass_specs = []
            finish = ""
        positions.append({
            "id": str(value.get("id") or ""),
            "position_index": value.get("position_index"),
            "quantity": value.get("quantity"),
            "typology": value.get("typology"),
            "location_tag": value.get("location_tag"),
            # P10 — alternativa sellada: fuera del total del trato.
            "is_option": bool(value.get("is_option")),
            "width_mm": str(value.get("width_mm") or ""),
            "height_mm": str(value.get("height_mm") or ""),
            "color_interior": value.get("color_interior"),
            "color_exterior": value.get("color_exterior"),
            # D05: sealed per-face finish detail — the portal paints the
            # declared render swatch, never an invented color.
            "color_interior_detail": value.get("color_interior_detail"),
            "color_exterior_detail": value.get("color_exterior_detail"),
            "glass_specs": glass_specs,
            "finish": finish or None,
            # Unpriced legacy lines stay null — a "$0" reads as free, never as
            # "not priced".
            "price_net": (
                str(value["price_net"]) if value.get("price_net") is not None else None
            ),
            "discount_pct": str(value.get("discount_pct") or "0"),
            "parametric_tree": value.get("parametric_tree"),
        })
    return positions


def _sealed_organization(version: dict[str, object]) -> dict[str, object]:
    """The issuer's white-label identity for the proposal page — commercial
    name, contact lines and a signed logo URL, all from the sealed snapshot
    so a later rebrand can't rewrite a live quote."""
    snapshot = decoded(version["snapshot_json"])
    org = snapshot.get("organization") if isinstance(snapshot, dict) else None
    if not isinstance(org, dict):
        return {}
    logo_url = None
    logo_key = org.get("brand_logo_key")
    if logo_key:
        try:
            logo_url = SupabaseDocumentStorage().signed_url(str(logo_key))
        except Exception:
            logo_url = None
    return {
        "name": org.get("name"),
        "tax_id": org.get("tax_id"),
        "commercial_name": org.get("commercial_name"),
        "brand_address": org.get("brand_address"),
        "brand_phone": org.get("brand_phone"),
        "brand_email": org.get("brand_email"),
        "brand_logo_url": logo_url,
        "brand_color": effective_brand_color(org.get("brand_color"))[0],
        # P10 — el pie «Generado con DEKOPEN» del portal obedece la misma
        # política sellada que los documentos (org.doc_dekopen_credit).
        "dekopen_credit": bool(org.get("doc_dekopen_credit", True)),
    }


def _sealed_doc_terms(version: dict[str, object]) -> dict[str, object]:
    """Condiciones comerciales selladas — las mismas que DOC-01 imprime."""
    snapshot = decoded(version["snapshot_json"])
    org = snapshot.get("organization") if isinstance(snapshot, dict) else None
    terms = org.get("doc_terms") if isinstance(org, dict) else None
    if not isinstance(terms, dict):
        return {}
    return {
        key: terms[key]
        for key in (
            "plazo_entrega",
            "instalacion",
            "exclusiones",
            "garantia",
            "jurisdiccion",
            "pago",
        )
        if terms.get(key)
    }


def _sealed_extras(version: dict[str, object]) -> list[dict[str, object]]:
    """Project-level charges sealed inside the applied pricing request —
    labeled net amounts the customer should see, never re-derived."""
    snapshot = decoded(version["snapshot_json"])
    pricing = snapshot.get("pricing") if isinstance(snapshot, dict) else None
    request = pricing.get("request") if isinstance(pricing, dict) else None
    items = request.get("extras") if isinstance(request, dict) else None
    if not isinstance(items, list):
        return []
    return [
        {"label": str(item.get("label") or ""), "amount": str(item.get("amount") or "0")}
        for item in items
        if isinstance(item, dict) and item.get("label")
    ]


def _payment_state(
    *,
    org_id: object,
    project_id: object,
    approval: dict[str, object],
    sealed: dict[str, object],
    superseded: bool,
    validity_expired: bool,
) -> dict[str, object]:
    """El estado de cobro que el portal puede prometer — nunca un botón
    engañoso.

    ``payable`` exige, en orden, todo lo que haría legítimo cobrar: la
    revisión sellada es la vigente, la propuesta sigue válida y está
    APROBADA, la moneda la cobra el proveedor (CLP), queda saldo y la org
    tiene un proveedor configurado (integración Flow o el simulador de
    sandbox). Si alguna condición falta, ``reason`` dice por qué y el
    frontend no dibuja el botón — el cobro oculto con razón, no un 422
    después del clic.
    """
    reason: str | None = None
    payable = False
    collected = Decimal("0")
    gross = Decimal(str(sealed.get("total_price_gross") or "0"))
    superseded_or_dead = superseded or str(approval["status"]) == "REVOKED"
    if not superseded_or_dead:
        payments = rows(
            "SELECT amount,voided_at FROM public.project_payments "
            "WHERE org_id=%s AND project_id=%s",
            [str(org_id), str(project_id)],
        )
        collected = sum(
            (Decimal(str(p["amount"])) for p in payments if p["voided_at"] is None),
            Decimal("0"),
        )
    balance = gross - collected
    if collected <= 0:
        status = "PENDING"
    elif balance > 0:
        status = "PARTIAL"
    else:
        status = "PAID"
    if superseded_or_dead:
        reason = "quote_not_current"
    elif validity_expired:
        reason = "quote_validity_expired"
    elif str(approval["status"]) != "APPROVED":
        reason = "not_approved"
    elif str(sealed.get("currency") or "CLP") != "CLP":
        reason = "unsupported_currency"
    elif balance <= 0:
        reason = "paid_in_full"
    else:
        if _provider_configured(org_id, approval):
            payable = True
        else:
            reason = "provider_not_configured"
    return {
        "status": status,
        "collected": str(collected),
        "balance": str(balance),
        "payable": payable,
        "reason": reason,
        # El simulador cobra solo en sandbox — el portal lo declara.
        "simulated": _simulated_payment(org_id, approval),
    }


def _claims_as_creator(approval: dict[str, object]) -> None:
    """Portal → claims del miembro que acuñó el enlace.

    Las policies de membresía (org_payment_integrations, el INSERT de
    customer_approvals/payment_links) resuelven la org vía auth.uid(); el
    portal no trae JWT, así que delega en el principal que el enlace ya
    acreditó al acuñarse — el mismo patrón de _transition_project_approved.
    """
    claims = json.dumps({"sub": str(approval["created_by"])})
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)", [claims]
        )


def _provider_configured(org_id: object, approval: dict[str, object]) -> bool:
    """¿La org puede cobrar online? Una integración Flow habilitada o el
    simulador de sandbox — leído con las credenciales del creador del
    enlace, que es quien firma el cobro si el cliente paga."""
    from billing.flow import mock_enabled

    _claims_as_creator(approval)
    with documentary_backend():
        found = rows(
            "SELECT org_id FROM public.org_payment_integrations "
            "WHERE org_id=%s AND provider='FLOW' AND enabled LIMIT 1",
            [str(org_id)],
        )
    return bool(found) or mock_enabled()


def _simulated_payment(org_id: object, approval: dict[str, object]) -> bool:
    from billing.flow import mock_enabled

    if not mock_enabled():
        return False
    _claims_as_creator(approval)
    with documentary_backend():
        found = rows(
            "SELECT org_id FROM public.org_payment_integrations "
            "WHERE org_id=%s AND provider='FLOW' AND enabled LIMIT 1",
            [str(org_id)],
        )
    return not found


def _latest_event(approval_id: object, org_id: object) -> dict[str, object] | None:
    """La evidencia pública de la decisión vigente — append-only.

    Los datos personales del firmante (nombre, RUT, IP, user agent, nota)
    viven en la tabla y los ve el estimador por list_approvals; al público
    solo le corresponde qué se decidió, cuándo y con qué texto."""
    events = rows(
        "SELECT decision,acceptance_text,revision_code,bom_hash,positions,"
        "created_at FROM public.customer_approval_events "
        "WHERE approval_id=%s AND org_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        [str(approval_id), str(org_id)],
    )
    if not events:
        return None
    event = events[0]
    return {
        "decision": str(event["decision"]),
        "acceptance_text": event["acceptance_text"],
        "revision_code": event["revision_code"],
        "positions": decoded(event["positions"]) or [],
        "created_at": event["created_at"].isoformat(),
    }


def portal_quote(token: str, *, track: bool = True) -> dict[str, object]:
    """Public read: the sealed proposal — positions, issuer, totals, payment.

    Never a naked 410 for a real link: revoked, expired, superseded and
    decided quotes render their dedicated state with the issuer's identity
    so the client knows what happened and whom to call. Only an unknown or
    malformed token 404s.
    """
    with transaction.atomic(), portal_backend():
        approval = _lookup_approval(token)
        org_id = approval["org_id"]
        _scope_org(org_id)
        version = _bound_version(approval)
        now = datetime.now(timezone.utc)
        link_expired = approval["expires_at"] < now
        if track and approval["status"] not in ("REVOKED",) and not link_expired:
            # The client's open is the sales signal — record it on the link
            # so the estimator sees "opened N times · last today". Dead links
            # render their state page untracked: a view of "revocada" no es
            # interés en la propuesta.
            write(
                "UPDATE public.customer_approvals SET view_count=view_count+1,"
                "first_viewed_at=COALESCE(first_viewed_at, clock_timestamp()),"
                "last_viewed_at=clock_timestamp() WHERE id=%s AND org_id=%s",
                [approval["id"], org_id],
            )
        sealed = _sealed_project(version)
        project = _live_project(approval)
        superseded = str(project["current_revision"]) != str(version["revision_code"])
        validity_expired = _validity_expired(sealed.get("quotation_valid_until"))
        # El estado visible se deriva una vez y se nombra — cada página de
        # estado existe por una razón concreta, no por un if anidado.
        # "Reemplazada" gana a "revocada"/"vencida": la revisión sellada ya no
        # es la vigente (normalmente el enlace murió justo por eso) y la
        # página honesta es la que ofrece seguir a la cotización actual.
        if superseded:
            state = "superseded"
        elif str(approval["status"]) == "REVOKED":
            state = "revoked"
        elif link_expired:
            state = "link_expired"
        elif str(approval["status"]) == "APPROVED":
            state = "approved"
        elif str(approval["status"]) == "DECLINED":
            state = "declined"
        elif validity_expired:
            state = "validity_expired"
        else:
            state = "live" if str(approval["status"]) == "PENDING" else "changes_requested"
        # Reemplazada → la revisión vigente puede tener un link vivo al que
        # seguir (channel EMAIL/FOLLOW, no revocado ni expirado).
        follow_available = False
        if state == "superseded":
            live_link = rows(
                "SELECT a.id FROM public.customer_approvals a "
                "JOIN public.project_versions v ON v.id=a.project_version_id "
                "WHERE a.org_id=%s AND a.project_id=%s "
                "AND v.revision_code=%s AND a.channel IN ('EMAIL','FOLLOW') "
                "AND a.status IN ('PENDING','CHANGES_REQUESTED','APPROVED') "
                "AND a.expires_at > now() LIMIT 1",
                [org_id, approval["project_id"], str(project["current_revision"])],
            )
            follow_available = bool(live_link)
        artifacts = rows(
            "SELECT id,storage_object_key,created_at FROM public.document_artifacts "
            "WHERE org_id=%s AND project_version_id=%s "
            "AND document_type='DOC-01' AND format='PDF' "
            "ORDER BY created_at DESC LIMIT 1",
            [org_id, approval["project_version_id"]],
        )
        signed_url = (
            SupabaseDocumentStorage().signed_url(str(artifacts[0]["storage_object_key"]))
            if artifacts
            else None
        )
        # Totals absent from the sealed snapshot stay null — a $0 total on a
        # public proposal reads as a pricing error, never as "not priced".
        price_net = sealed.get("total_price_net")
        price_tax = sealed.get("total_price_tax")
        price_gross = sealed.get("total_price_gross")
        decision_event = (
            _latest_event(approval["id"], org_id)
            if str(approval["status"]) in ("APPROVED", "DECLINED", "CHANGES_REQUESTED")
            else None
        )
        return {
            "schema": "portal_quote_v2",
            "state": state,
            "organization": _sealed_organization(version),
            "project_code": sealed.get("code") or "",
            "project_name": sealed.get("name") or "",
            "client_name": sealed.get("client_name") or "",
            "revision_code": version["revision_code"],
            "current_revision": str(project["current_revision"]),
            "emitted_at": version["emitted_at"].isoformat(),
            "currency": sealed.get("currency") or "CLP",
            "payment_terms": sealed.get("payment_terms"),
            "doc_terms": _sealed_doc_terms(version),
            "notes_commercial": sealed.get("notes_commercial"),
            "total_price_net": str(price_net) if price_net is not None else None,
            "total_price_tax": str(price_tax) if price_tax is not None else None,
            "total_price_gross": str(price_gross) if price_gross is not None else None,
            "extras": _sealed_extras(version),
            "positions": _sealed_positions(version),
            "payment": _payment_state(
                org_id=org_id,
                project_id=approval["project_id"],
                approval=approval,
                sealed=sealed,
                superseded=superseded,
                validity_expired=validity_expired,
            ),
            "follow_available": follow_available,
            "acceptance_text": _acceptance_text(
                sealed=sealed,
                revision_code=version["revision_code"],
                gross=sealed.get("total_price_gross"),
                currency=sealed.get("currency") or "CLP",
            ),
            "decision_event": decision_event,
            "valid_until": sealed.get("quotation_valid_until"),
            "validity_expired": validity_expired,
            "superseded": superseded,
            "expires_at": approval["expires_at"].isoformat(),
            "approval_status": approval["status"],
            # The decider's name and decline note stay internal — a forwarded
            # link must not leak them to whoever holds the URL.
            "decided_by": None,
            "decided_at": (
                approval["decided_at"].isoformat() if approval["decided_at"] else None
            ),
            "decided_note": None,
            "quote_pdf_url": signed_url,
        }


def follow_quote(token: str) -> dict[str, object]:
    """Reemplazada → el cliente pide el link a la revisión vigente.

    Mints a FOLLOW-channel approval bound to the project's current sealed
    revision — a fresh token for the client who only holds the dead one.
    Reusa el link vivo si ya existe (cualquiera puede abrirlo igual).
    """
    with transaction.atomic(), portal_backend():
        approval = _lookup_approval(token)
        _scope_org(approval["org_id"])
        if str(approval["status"]) == "REVOKED":
            raise DocumentaryError("quote_revoked")
        project = _live_project(approval)
        live_version = one(
            "SELECT id,revision_code FROM public.project_versions v "
            "WHERE v.project_id=%s AND v.org_id=%s AND v.revision_code=%s",
            [approval["project_id"], approval["org_id"], str(project["current_revision"])],
            "version_not_found",
        )
        if str(approval["project_version_id"]) == str(live_version["id"]):
            # El link muerto ya apunta a la vigente — nada que seguir.
            raise DocumentaryError("quote_link_stale")
        # Cap duro: un cliente con el link muerto puede pedir el vigente,
        # no acuñar tokens sin límite. Cinco bastan para reenvíos honestos.
        minted = rows(
            "SELECT a.id FROM public.customer_approvals a "
            "WHERE a.org_id=%s AND a.project_id=%s AND a.project_version_id=%s "
            "AND a.channel='FOLLOW'",
            [approval["org_id"], approval["project_id"], live_version["id"]],
        )
        if len(minted) >= 5:
            raise DocumentaryError("follow_limit_reached")
    # Mint under documentary_backend: portal_write on customer_approvals is
    # UPDATE-only — el INSERT sigue el mismo camino que share_quote y lleva
    # las claims del creador del enlace para la policy de membresía.
    follow_token = secrets.token_urlsafe(_TOKEN_BYTES)
    with transaction.atomic():
        _claims_as_creator(approval)
        with documentary_backend():
            one(
                "INSERT INTO public.customer_approvals "
                "(org_id,project_id,project_version_id,token_hash,expires_at,"
                "created_by,channel) VALUES (%s,%s,%s,%s,%s,%s,'FOLLOW') "
                "RETURNING id",
                [
                    str(approval["org_id"]),
                    str(approval["project_id"]),
                    str(live_version["id"]),
                    hashlib.sha256(follow_token.encode()).hexdigest(),
                    datetime.now(timezone.utc) + timedelta(days=_APPROVAL_TTL_DAYS),
                    str(approval["created_by"]),
                ],
                "version_not_found",
            )
    return {"follow_token": follow_token}


def portal_pay(token: str, *, payer_email: str | None = None) -> dict[str, object]:
    """Cobrar desde la propuesta: minta o reusa el link de pago sellado.

    Las mismas compuertas del bloque `payment`: aprobada, vigente, no
    reemplazada, CLP, saldo > 0, proveedor configurado. El retorno queda
    sellado al portal — el pagador vuelve a ESTA cotización.
    """
    from projects import payment_links

    with transaction.atomic(), portal_backend():
        approval = _approval_for_token(token)
        _scope_org(approval["org_id"])
        version = _bound_version(approval)
        sealed = _sealed_project(version)
        project = _live_project(approval, for_update=True)
        superseded = str(project["current_revision"]) != str(version["revision_code"])
        payment = _payment_state(
            org_id=approval["org_id"],
            project_id=approval["project_id"],
            approval=approval,
            sealed=sealed,
            superseded=superseded,
            validity_expired=_validity_expired(sealed.get("quotation_valid_until")),
        )
        if not payment["payable"]:
            raise DocumentaryError("payment_not_payable")
        org_id = approval["org_id"]
        project_id = approval["project_id"]
        payer = (payer_email or "").strip() or str(
            sealed.get("client_email") or ""
        )
        if not payer:
            raise DocumentaryError("payer_email_required")
        return_url = f"{_frontend_origin()}/cotizacion/{token}"
        amount = Decimal(payment["balance"])
        # SALDO cobra todo el saldo vivo — semánticamente lo que el botón
        # promete («pagar lo que queda»), nunca una cuota inventada.
        kind = "SALDO"
        operation_key = f"portal:{approval['id']}:{secrets.token_hex(4)}"
    # create_link resuelve proveedor, slot de cobro y retorno — con las
    # claims del creador del enlace y rol documental desde el inicio: sus
    # lecturas de proyecto/deal corren antes de su propio role switch.
    with transaction.atomic():
        _claims_as_creator(approval)
        with documentary_backend():
            result = payment_links.create_link(
                org_id=UUID(str(org_id)),
                project_id=UUID(str(project_id)),
                actor_id=UUID(str(approval["created_by"])),
                data={
                    "operation_key": operation_key,
                    "kind": kind,
                    "amount": str(amount),
                    "payer_email": payer,
                    "subject": (
                        f"Cotización COT-{sealed.get('code')}-"
                        f"{version['revision_code']}"
                    ),
                    "return_url": return_url,
                },
            )
    link = result["link"]
    return {
        "payment_url": link.get("url"),
        "flow_token": link.get("flow_token"),
        "amount": link.get("amount"),
        "simulated": link.get("environment") == "MOCK",
    }


def payment_status(flow_token: str) -> dict[str, object]:
    """Estado público de un cobro — el retorno de Flow trae solo el token."""
    with transaction.atomic(), portal_backend():
        found = rows(
            "SELECT status,amount,kind,payer_return_url,project_id,org_id "
            "FROM public.project_payment_links WHERE flow_token=%s",
            [flow_token],
        )
        if len(found) != 1:
            raise DocumentaryError("quote_not_found")
        link = found[0]
        _scope_org(link["org_id"])
        return {
            "status": str(link["status"]),
            "amount": str(link["amount"]),
            "kind": str(link["kind"]),
            "payer_return_url": link["payer_return_url"],
            "project_id": str(link["project_id"]),
        }


def _transition_project_approved(
    *, approval: dict[str, object], version_id: str, now: datetime
) -> None:
    """Move the live project to APPROVED and queue its material forecast.

    Runs inside the caller's atomic block. The pricing trigger only allows
    pricing_backend and its project policy checks the caller's membership
    role, so the transition asserts the claims the approval delegated:
    created_by was verified as OWNER/ESTIMATOR when the approval was minted.
    The status guard makes the write atomic — a concurrent decision that
    commits first turns this into a no-op.
    """
    claims = json.dumps({"sub": str(approval["created_by"])})
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('request.jwt.claims', %s, true)", [claims]
        )
        cursor.execute("SET LOCAL ROLE pricing_backend")
    updated = rows(
        "UPDATE public.projects SET status='APPROVED',updated_at=%s "
        "WHERE id=%s AND org_id=%s AND status='QUOTED' RETURNING id",
        [now, approval["project_id"], approval["org_id"]],
    )
    if len(updated) != 1:
        # Under the FOR UPDATE lock the only way the guard misses is the
        # projects policy rejecting the claims principal — the link's
        # creator left the org. The customer's decision still seals; the
        # project stays QUOTED for staff to approve off-channel instead of
        # failing a customer click with a 500.
        logger.warning(
            "portal_approval_transition_denied",
            extra={
                "approval_id": str(approval["id"]),
                "created_by": str(approval["created_by"]),
            },
        )
        return
    # §08: an approved quote queues the material forecast for the version it
    # decided — the job carries the approval's minted actor as its principal.
    from automations.service import emit

    emit(
        "automation.prep_forecast",
        org_id=UUID(str(approval["org_id"])),
        actor_id=UUID(str(approval["created_by"])),
        idempotency_key=f"auto:prep:{version_id}",
        version_id=version_id,
    )


def approve_internal(
    *,
    org_id: UUID,
    project_id: UUID,
    actor_id: UUID,
    actor_label: str,
    note: str | None,
) -> dict[str, object]:
    """Staff records that the customer approved the quote off-channel.

    Mints an already-APPROVED approval row bound to the project's latest
    sealed version — the same audit shape a customer decision leaves — and
    runs the same project transition. Outstanding pending links for the
    revision are revoked: the deal is decided, so no token should stay live.
    """
    with documentary_backend():
        project = one(
            "SELECT id,status,current_revision FROM public.projects "
            "WHERE id=%s AND org_id=%s",
            [str(project_id), str(org_id)],
            "project_not_found",
        )
        live_status = str(project["status"])
        if live_status == "APPROVED":
            return {"project_status": "APPROVED"}
        if live_status != "QUOTED":
            raise DocumentaryError("quote_approve_requires_quoted")
        versions = rows(
            "SELECT id,revision_code FROM public.project_versions "
            "WHERE project_id=%s AND org_id=%s "
            "ORDER BY emitted_at DESC,id DESC LIMIT 1",
            [str(project_id), str(org_id)],
        )
        if not versions:
            raise DocumentaryError("version_not_found")
        if str(project["current_revision"]) != str(versions[0]["revision_code"]):
            raise DocumentaryError("quote_approve_revision_mismatch")

    now = datetime.now(timezone.utc)
    with transaction.atomic(), documentary_backend():
        write(
            "UPDATE public.customer_approvals SET status='REVOKED',revoked_at=%s,"
            "revoked_by=%s WHERE org_id=%s AND project_id=%s "
            "AND project_version_id=%s AND status IN ('PENDING','CHANGES_REQUESTED')",
            [now, str(actor_id), str(org_id), str(project_id),
             str(versions[0]["id"])],
        )
        internal_token = secrets.token_urlsafe(_TOKEN_BYTES)
        approval = one(
            "INSERT INTO public.customer_approvals "
            "(org_id,project_id,project_version_id,token_hash,status,decided_by,"
            "decided_at,decided_note,expires_at,created_by) "
            "VALUES (%s,%s,%s,%s,'APPROVED',%s,%s,%s,%s,%s) "
            "RETURNING id,org_id,project_id,created_by",
            [
                str(org_id),
                str(project_id),
                str(versions[0]["id"]),
                hashlib.sha256(internal_token.encode()).hexdigest(),
                actor_label,
                now,
                note or None,
                now + timedelta(days=_APPROVAL_TTL_DAYS),
                str(actor_id),
            ],
        )
        _transition_project_approved(
            approval=approval, version_id=str(versions[0]["id"]), now=now
        )
        # P25: aviso interno — el staff ve la aprobación sin abrir la app.
        from automations.service import emit

        emit(
            "mail.quote_approved",
            org_id=org_id,
            actor_id=actor_id,
            idempotency_key=f"mail:quote-approved:{approval['id']}",
            project_id=str(project_id),
            decided_by=actor_label,
        )
    return {"project_status": "APPROVED"}


def _acceptance_text(
    *, sealed: dict[str, object], revision_code: object, gross: object, currency: object
) -> str:
    """El literal que el cliente marcó — se construye en servidor desde las
    cifras selladas, nunca desde texto que venga en el request. CLP se
    formatea es-CL ($1.435.471); otra moneda viaja como monto + código."""
    try:
        amount = Decimal(str(gross))
    except Exception:
        amount = Decimal("0")
    money = (
        "$" + f"{int(amount):,}".replace(",", ".")
        if str(currency or "CLP") == "CLP"
        else f"{amount} {currency}"
    )
    return (
        f"Acepto la propuesta COT-{sealed.get('code')}-{revision_code} "
        f"por {money} IVA incluido y sus condiciones."
    )


def decide_quote(
    *,
    token: str,
    decision: str,
    decided_by: str,
    note: str | None,
    decided_rut: str | None = None,
    accepted: bool = False,
    marked_position_ids: list[str] | None = None,
    decision_ip: str | None = None,
    decision_user_agent: str | None = None,
) -> dict[str, object]:
    """Approve, decline or request changes on the shared quote; replays
    return the sealed state. CHANGES_REQUESTED keeps the link alive — the
    client can still decide later, or the estimator re-shares and the link
    rotates.

    Aprobar sella una evidencia completa (customer_approval_events, tabla
    append-only): nombre + RUT validado, la frase literal aceptada, la
    revisión y su huella, las alternativas marcadas, la IP y el user agent.
    """
    if decision not in ("APPROVED", "DECLINED", "CHANGES_REQUESTED"):
        raise DocumentaryError("decision_invalid")
    if decision == "CHANGES_REQUESTED" and not note:
        raise DocumentaryError("changes_note_required")
    if decision == "APPROVED":
        # Quien acepta se identifica: la evidencia vale lo que identifica.
        if not decided_rut or not rut_mod11_valid(decided_rut):
            raise DocumentaryError("decided_rut_invalid")
        if not accepted:
            raise DocumentaryError("acceptance_required")
    if decided_rut is not None and not rut_mod11_valid(decided_rut):
        raise DocumentaryError("decided_rut_invalid")
    with transaction.atomic(), portal_backend():
        approval = _approval_for_token(token)
        _scope_org(approval["org_id"])
        if approval["status"] in ("PENDING", "CHANGES_REQUESTED"):
            version = _bound_version(approval)
            sealed = _sealed_project(version)
            valid_until = sealed.get("quotation_valid_until")
            if _validity_expired(valid_until):
                raise DocumentaryError("quote_validity_expired")
            project = _live_project(approval, for_update=True)
            live_status = str(project["status"])
            if str(project["current_revision"]) != str(version["revision_code"]):
                # A successor revision replaced the quote this link decided.
                raise DocumentaryError("quote_link_stale")
            if live_status != "QUOTED" and not (
                live_status == "APPROVED" and decision == "APPROVED"
            ):
                # The project already moved on — approved or rejected — so
                # this link no longer decides anything.
                raise DocumentaryError("quote_already_decided")
            # Alternativas marcadas: solo pueden venir ids sellados con
            # is_option — cualquier otro id es un request inventado.
            marked_positions: list[dict[str, object]] = []
            sealed_positions = _sealed_positions(version)
            option_by_id = {
                p["id"]: p for p in sealed_positions if p.get("is_option")
            }
            for position_id in marked_position_ids or []:
                option = option_by_id.get(str(position_id))
                if option is None:
                    raise DocumentaryError("decision_position_not_option")
                marked_positions.append(
                    {
                        "position_id": str(position_id),
                        "position_index": option["position_index"],
                    }
                )
            acceptance_text = (
                _acceptance_text(
                    sealed=sealed,
                    revision_code=version["revision_code"],
                    gross=sealed.get("total_price_gross"),
                    currency=sealed.get("currency") or "CLP",
                )
                if decision == "APPROVED"
                else None
            )
            now = datetime.now(timezone.utc)
            # The status guard makes the write atomic: a concurrent decision
            # that commits first turns this into a no-op, and the fresh read
            # below replays the sealed state instead of overwriting it.
            decided = rows(
                "UPDATE public.customer_approvals SET status=%s,decided_by=%s,"
                "decided_at=%s,decided_note=%s WHERE id=%s "
                "AND status IN ('PENDING','CHANGES_REQUESTED') "
                "RETURNING id",
                [
                    decision,
                    f"{decided_by} · {decided_rut}" if decided_rut else decided_by,
                    now,
                    note or None,
                    approval["id"],
                ],
            )
            if decided:
                # La evidencia es append-only: cada decisión efectiva deja
                # su fila completa y el trigger la vuelve inmutable.
                rows(
                    "INSERT INTO public.customer_approval_events "
                    "(org_id,approval_id,project_id,decision,decided_by,"
                    "decided_rut,decided_note,decision_ip,decision_user_agent,"
                    "acceptance_text,revision_code,bom_hash,positions) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s::inet,%s,%s,%s,%s,%s::jsonb) "
                    "RETURNING id",
                    [
                        str(approval["org_id"]),
                        approval["id"],
                        str(approval["project_id"]),
                        decision,
                        decided_by,
                        decided_rut,
                        note or None,
                        decision_ip or None,
                        decision_user_agent or None,
                        acceptance_text,
                        str(version["revision_code"]),
                        str(version.get("bom_hash") or "") or None,
                        json.dumps(marked_positions),
                    ],
                )
            if decided and decision == "APPROVED" and live_status == "QUOTED":
                _transition_project_approved(
                    approval=approval,
                    version_id=str(approval["project_version_id"]),
                    now=now,
                )
            if decided and decision == "APPROVED":
                # P25: aviso interno de aprobación — el actor del job es el
                # miembro que acuñó el enlace (created_by del approval).
                from automations.service import emit

                emit(
                    "mail.quote_approved",
                    org_id=UUID(str(approval["org_id"])),
                    actor_id=UUID(str(approval["created_by"])),
                    idempotency_key=f"mail:quote-approved:{approval['id']}",
                    project_id=str(approval["project_id"]),
                    decided_by=(
                        f"{decided_by} · {decided_rut}"
                        if decided_rut
                        else decided_by
                    ),
                )
            if decided and decision == "CHANGES_REQUESTED":
                # P08: pedido de ajustes — aviso interno al equipo; el
                # enlace sigue vivo para una decisión posterior.
                from automations.service import emit

                emit(
                    "mail.quote_changes_requested",
                    org_id=UUID(str(approval["org_id"])),
                    actor_id=UUID(str(approval["created_by"])),
                    idempotency_key=f"mail:quote-changes:{approval['id']}:{now.isoformat()}",
                    project_id=str(approval["project_id"]),
                    decided_by=(
                        f"{decided_by} · {decided_rut}"
                        if decided_rut
                        else decided_by
                    ),
                    note=note or "",
                )
    return portal_quote(token, track=False)
