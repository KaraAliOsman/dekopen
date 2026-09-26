"""Customer quote-approval links: public token-scoped reads and decisions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import secrets
from typing import Iterator
from uuid import UUID

from django.db import DatabaseError, connection, transaction
from psycopg import sql

from documents.artifacts import SupabaseDocumentStorage, generate_artifact
from documents.renderers import finish_label, frozen_glass_specs
from documents.repository import (
    DocumentaryError,
    decoded,
    documentary_backend,
    one,
    rows,
)

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
        if not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(previous))
                )
        raise
    else:
        if not connection.needs_rollback:
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
    # The client-facing quotation is DOC-01 (the commercial offer). Generate it
    # before minting: generation is slot-idempotent, and a failure must not
    # strand an approval whose token nobody ever saw.
    generate_artifact(
        org_id=org_id,
        actor_id=actor_id,
        role=role,
        project_version_id=versions[0]["id"],
        order_id=None,
        document_type="DOC-01",
        file_format="PDF",
    )
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(days=_APPROVAL_TTL_DAYS)
    with transaction.atomic(), documentary_backend():
        # A fresh share supersedes every outstanding link for this revision —
        # otherwise pending tokens accumulate and stay concurrently valid.
        rows(
            "UPDATE public.customer_approvals SET status='REVOKED',revoked_at=%s,"
            "revoked_by=%s WHERE org_id=%s AND project_id=%s "
            "AND project_version_id=%s AND status='PENDING' RETURNING id",
            [
                datetime.now(timezone.utc),
                str(actor_id),
                str(org_id),
                str(project_id),
                str(versions[0]["id"]),
            ],
        )
        one(
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
            }
            for row in rows(
                "SELECT a.id,a.status,a.decided_by,a.decided_at,a.decided_note,"
                "a.expires_at,a.created_at,a.revoked_at,v.revision_code "
                "FROM public.customer_approvals a "
                "JOIN public.project_versions v "
                "ON v.id = a.project_version_id "
                "WHERE a.org_id=%s AND a.project_id=%s "
                "ORDER BY a.created_at DESC",
                [str(org_id), str(project_id)],
            )
        ]


def _approval_for_token(token: str) -> dict[str, object]:
    found = rows(
        "SELECT * FROM public.customer_approvals WHERE token_hash=%s",
        [hashlib.sha256(token.encode()).hexdigest()],
    )
    if len(found) != 1:
        raise DocumentaryError("quote_not_found")
    approval = found[0]
    if approval["status"] == "REVOKED":
        raise DocumentaryError("quote_revoked")
    if approval["expires_at"] < datetime.now(timezone.utc):
        raise DocumentaryError("quote_expired")
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
        "SELECT revision_code,emitted_at,snapshot_json::text AS snapshot_json "
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
            finish = finish_label(value.get("color_interior"), value.get("color_exterior"))
        except DocumentaryError:
            glass_specs = []
            finish = ""
        positions.append({
            "id": str(value.get("id") or ""),
            "position_index": value.get("position_index"),
            "quantity": value.get("quantity"),
            "typology": value.get("typology"),
            "location_tag": value.get("location_tag"),
            "width_mm": str(value.get("width_mm") or ""),
            "height_mm": str(value.get("height_mm") or ""),
            "color_interior": value.get("color_interior"),
            "color_exterior": value.get("color_exterior"),
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
    }


def _payment_state(
    *, org_id: object, project_id: object, gross: Decimal, superseded: bool
) -> dict[str, object] | None:
    """The customer's own payment state on the proposal link."""
    # A superseded link's sealed gross belongs to a dead revision — mixing it
    # with live payments shows crossed-era numbers under the banner.
    if superseded:
        return None
    payments = rows(
        "SELECT amount,voided_at FROM public.project_payments "
        "WHERE org_id=%s AND project_id=%s",
        [str(org_id), str(project_id)],
    )
    if not payments:
        return None
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
    return {
        "status": status,
        "collected": str(collected),
        "balance": str(balance),
    }


def portal_quote(token: str) -> dict[str, object]:
    """Public read: the sealed proposal — positions, issuer, totals, payment."""
    with transaction.atomic(), portal_backend():
        approval = _approval_for_token(token)
        org_id = approval["org_id"]
        _scope_org(org_id)
        version = _bound_version(approval)
        sealed = _sealed_project(version)
        project = _live_project(approval)
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
        gross = Decimal(str(sealed.get("total_price_gross") or "0"))
        superseded = str(project["current_revision"]) != str(version["revision_code"])
        # A live Flow link the estimator already minted is the proposal's next
        # step — only for CLP deals (the provider charges CLP).
        payment_url = None
        if str(sealed.get("currency") or "CLP") == "CLP":
            live_link = rows(
                "SELECT url FROM public.project_payment_links "
                "WHERE org_id=%s AND project_id=%s AND status='PENDING' AND url IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 1",
                [org_id, approval["project_id"]],
            )
            if live_link:
                payment_url = live_link[0]["url"]
        # Totals absent from the sealed snapshot stay null — a $0 total on a
        # public proposal reads as a pricing error, never as "not priced".
        price_net = sealed.get("total_price_net")
        price_tax = sealed.get("total_price_tax")
        price_gross = sealed.get("total_price_gross")
        return {
            "schema": "portal_quote_v1",
            "organization": _sealed_organization(version),
            "project_code": sealed.get("code") or "",
            "project_name": sealed.get("name") or "",
            "client_name": sealed.get("client_name") or "",
            "revision_code": version["revision_code"],
            "emitted_at": version["emitted_at"].isoformat(),
            "currency": sealed.get("currency") or "CLP",
            "payment_terms": sealed.get("payment_terms"),
            "notes_commercial": sealed.get("notes_commercial"),
            "total_price_net": str(price_net) if price_net is not None else None,
            "total_price_tax": str(price_tax) if price_tax is not None else None,
            "total_price_gross": str(price_gross) if price_gross is not None else None,
            "positions": _sealed_positions(version),
            "payment": _payment_state(
                org_id=org_id,
                project_id=approval["project_id"],
                gross=gross,
                superseded=superseded,
            ),
            "payment_url": payment_url,
            "valid_until": sealed.get("quotation_valid_until"),
            "validity_expired": bool(
                sealed.get("quotation_valid_until")
                and date.fromisoformat(str(sealed["quotation_valid_until"]))
                < datetime.now(timezone.utc).date()
            ),
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
        raise DocumentaryError("quote_link_stale")
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
        rows(
            "UPDATE public.customer_approvals SET status='REVOKED',revoked_at=%s,"
            "revoked_by=%s WHERE org_id=%s AND project_id=%s "
            "AND project_version_id=%s AND status='PENDING'",
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
    return {"project_status": "APPROVED"}


def decide_quote(
    *,
    token: str,
    decision: str,
    decided_by: str,
    note: str | None,
    decided_rut: str | None = None,
) -> dict[str, object]:
    """Approve or decline the shared quote; replays return the sealed state."""
    with transaction.atomic(), portal_backend():
        approval = _approval_for_token(token)
        _scope_org(approval["org_id"])
        if approval["status"] == "PENDING":
            version = _bound_version(approval)
            valid_until = _sealed_project(version).get("quotation_valid_until")
            if valid_until and date.fromisoformat(str(valid_until)) < datetime.now(
                timezone.utc
            ).date():
                raise DocumentaryError("quote_validity_expired")
            project = _live_project(approval, for_update=True)
            live_status = str(project["status"])
            if str(project["current_revision"]) != str(version["revision_code"]) or (
                live_status != "QUOTED"
                and not (live_status == "APPROVED" and decision == "APPROVED")
            ):
                # A successor revision reset the live project, or the quote
                # already moved on — the link no longer decides anything.
                raise DocumentaryError("quote_link_stale")
            now = datetime.now(timezone.utc)
            # The status guard makes the write atomic: a concurrent decision
            # that commits first turns this into a no-op, and the fresh read
            # below replays the sealed state instead of overwriting it.
            decided = rows(
                "UPDATE public.customer_approvals SET status=%s,decided_by=%s,"
                "decided_at=%s,decided_note=%s WHERE id=%s AND status='PENDING' "
                "RETURNING id",
                [
                    decision,
                    f"{decided_by} · {decided_rut}" if decided_rut else decided_by,
                    now,
                    note or None,
                    approval["id"],
                ],
            )
            if decided and decision == "APPROVED" and live_status == "QUOTED":
                _transition_project_approved(
                    approval=approval,
                    version_id=str(approval["project_version_id"]),
                    now=now,
                )
    return portal_quote(token)
