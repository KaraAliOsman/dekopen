"""Explicit supplier allocation and one confirmed batch per revision/order type."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import connection

from dekopen_engine.documentary_canonical import (
    DOCUMENTARY_CANONICAL_VERSION,
    documentary_canonical_json_v1,
    documentary_sha256_v1,
)

from documents.repository import DocumentaryError, decoded, documentary_backend, json_text, one, rows
from inventory.production_stock import coverage_for_version
from projects import org_branding


ORDER_TYPES = (
    "SUPPLIER_PROFILE_PO",
    "SUPPLIER_GLASS_PO",
    "SUPPLIER_HARDWARE_PO",
    "SUPPLIER_PANEL_PO",
)


def _public(value: object) -> object:
    return json.loads(json_text(value))


def _object(value: object, code: str) -> dict[str, object]:
    parsed = decoded(value)
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise DocumentaryError(code)
    return parsed


def _array(value: object, code: str) -> list[object]:
    parsed = decoded(value)
    if not isinstance(parsed, list):
        raise DocumentaryError(code)
    return parsed


def _version(version_id: UUID, org_id: UUID) -> dict[str, object]:
    version = one(
        "SELECT version.id,version.project_id,version.org_id,version.revision_code,"
        "version.authority_version,version.bom_hash,version.snapshot_sha256,"
        "version.production_allowed,version.documentary_complete,version.emitted_at,"
        "project.code AS project_code "
        "FROM public.project_versions version JOIN public.projects project "
        "ON project.id=version.project_id AND project.org_id=version.org_id "
        "WHERE version.id=%s AND version.org_id=%s",
        [version_id, org_id],
        "project_version_not_found",
    )
    if version["authority_version"] not in ("SHOT09_V1", "SHOT10_V1"):
        raise DocumentaryError("legacy_version_not_eligible")
    return version


def _line_snapshot(row: dict[str, object]) -> dict[str, object]:
    technical = _object(row["technical_identity"], "invalid_purchase_requirement")
    specification = _object(row["specification"], "invalid_purchase_requirement")
    source_trace = _array(row["source_trace"], "invalid_purchase_requirement")
    authority_ids = technical.get("authority_ids")
    technical_skus = technical.get("technical_skus")
    if not isinstance(authority_ids, list) or not all(isinstance(item, str) for item in authority_ids):
        raise DocumentaryError("invalid_purchase_requirement")
    if not isinstance(technical_skus, list) or not all(isinstance(item, str) for item in technical_skus):
        raise DocumentaryError("invalid_purchase_requirement")
    if not all(isinstance(item, str) for item in source_trace):
        raise DocumentaryError("invalid_purchase_requirement")
    quantity = Decimal(str(row["quantity"]))
    if quantity != quantity.to_integral_value():
        raise DocumentaryError("invalid_purchase_requirement")
    return {
        "id": str(row["id"]),
        "requirement_key": str(row["requirement_key"]),
        "order_type": str(row["order_type"]),
        "category": str(row["category"]),
        "authority_ids": authority_ids,
        "technical_skus": technical_skus,
        "purchasing_sku": str(row["purchasing_sku"]),
        "physical_stock_identity": (
            None if row["physical_stock_identity"] is None
            else str(row["physical_stock_identity"])
        ),
        "physical_stock_sku": (
            None if row.get("physical_stock_sku") is None
            else str(row["physical_stock_sku"])
        ),
        "physical_stock_name": (
            None if row.get("physical_stock_name") is None
            else str(row["physical_stock_name"])
        ),
        "unit": str(row["unit"]),
        "quantity": int(quantity),
        "specification": specification,
        "source_trace": source_trace,
    }


def _requirements(version_id: UUID, org_id: UUID,
                  order_type: str | None = None) -> list[dict[str, object]]:
    condition = "" if order_type is None else " AND order_type=%s"
    parameters: list[object] = [version_id, org_id]
    if order_type is not None:
        parameters.append(order_type)
    return rows(
        "SELECT line.id,line.requirement_key,line.project_id,line.project_version_id,"
        "line.org_id,line.order_type::text AS order_type,"
        "line.category,line.technical_identity::text,line.purchasing_sku,"
        "line.physical_stock_identity,line.unit,"
        "line.quantity,line.specification::text,line.source_trace::text,"
        "stock.sku AS physical_stock_sku,stock.name AS physical_stock_name "
        "FROM public.purchase_requirement_lines line "
        "LEFT JOIN public.inventory_stock stock "
        "ON stock.org_id = line.org_id "
        "AND stock.variant_key = line.physical_stock_identity::text "
        "WHERE line.project_version_id=%s AND line.org_id=%s"
        + condition
        + " ORDER BY line.order_type,line.category,line.purchasing_sku,line.requirement_key",
        parameters,
    )


def purchasing_state(org_id: UUID, version_id: UUID | None = None) -> dict[str, object]:
    with documentary_backend():
        if version_id is None:
            versions = rows(
                "SELECT version.id,version.project_id,version.revision_code,"
                "version.bom_hash,version.snapshot_sha256,version.documentary_complete,"
                "version.emitted_at,project.code AS project_code "
                "FROM public.project_versions version "
                "JOIN public.projects project "
                "ON project.id=version.project_id AND project.org_id=version.org_id "
                "WHERE version.org_id=%s "
                "AND version.authority_version IN ('SHOT09_V1','SHOT10_V1') "
                "ORDER BY version.emitted_at DESC,version.id",
                [org_id],
            )
            return {"versions": _public(versions)}
        version = _version(version_id, org_id)
        requirements = [_line_snapshot(item) for item in _requirements(version_id, org_id)]
        eligibilities = rows(
            "SELECT id,order_type::text,supplier_identity,supplier_name,supplier_details::text,"
            "eligible_requirement_keys::text,evidence::text,version,content_hash,created_at "
            "FROM public.supplier_eligibility_versions WHERE project_version_id=%s AND org_id=%s "
            "ORDER BY order_type,supplier_name,supplier_identity,version",
            [version_id, org_id],
        )
        allocations = rows(
            "SELECT allocation.id,allocation.requirement_line_id,allocation.supplier_eligibility_id,"
            "allocation.order_type::text,allocation.allocated_at "
            "FROM public.purchase_allocations allocation WHERE allocation.project_version_id=%s "
            "AND allocation.org_id=%s ORDER BY allocation.order_type,allocation.requirement_line_id",
            [version_id, org_id],
        )
        orders = rows(
            "SELECT o.id,o.order_code,o.order_type::text,o.status::text,o.supplier_identity,"
            "o.supplier_name,o.order_snapshot_hash,o.confirmed_at,o.sent_at,o.expected_at,"
            "l.line_count,l.total_qty,l.lines_preview::text AS lines_preview "
            "FROM public.orders o LEFT JOIN ("
            "SELECT order_id, COUNT(*) AS line_count, SUM(quantity) AS total_qty,"
            " jsonb_agg(jsonb_build_object('sku',line_snapshot->>'purchasing_sku',"
            " 'qty',quantity,'unit',line_snapshot->>'unit') ORDER BY id) AS lines_preview"
            " FROM public.order_requirement_lines WHERE org_id=%s GROUP BY order_id"
            ") l ON l.order_id=o.id "
            "WHERE o.project_version_id=%s AND o.org_id=%s "
            "ORDER BY o.order_type,o.supplier_name,o.id",
            [org_id, version_id, org_id],
        )
        artifacts = rows(
            "SELECT id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,file_sha256,"
            "byte_size,created_at FROM public.document_artifacts "
            "WHERE project_version_id=%s AND org_id=%s ORDER BY document_type,format,id",
            [version_id, org_id],
        )
        allocated = {str(item["requirement_line_id"]) for item in allocations}
        covered_keys = {
            (str(item["order_type"]), str(key))
            for item in eligibilities
            for key in _array(
                item["eligible_requirement_keys"], "invalid_supplier_eligibility"
            )
        }
        blockers = []
        for order_type in ORDER_TYPES:
            type_lines = [item for item in requirements if item["order_type"] == order_type]
            if not type_lines:
                continue
            uncovered = [
                item["requirement_key"] for item in type_lines
                if (order_type, item["requirement_key"]) not in covered_keys
            ]
            if uncovered:
                blockers.append({"order_type": order_type,
                                 "code": "SUPPLIER_ELIGIBILITY_REQUIRED",
                                 "requirement_keys": uncovered})
            missing = [item["requirement_key"] for item in type_lines if item["id"] not in allocated]
            if missing:
                blockers.append({"order_type": order_type, "code": "ALLOCATION_REQUIRED",
                                 "requirement_keys": missing})
        return {
            "version": _public(version),
            "requirements": requirements,
            "eligibilities": [
                {**item,
                 "id": str(item["id"]),
                 "supplier_details": _object(item["supplier_details"], "invalid_supplier_eligibility"),
                 "eligible_requirement_keys": _array(
                     item["eligible_requirement_keys"], "invalid_supplier_eligibility"
                 ),
                 "evidence": _object(item["evidence"], "invalid_supplier_eligibility")}
                for item in eligibilities
            ],
            "allocations": _public(allocations),
            "orders": [
                {
                    **_public(item),
                    "lines_preview": decoded(item["lines_preview"])
                    if item.get("lines_preview")
                    else [],
                }
                for item in orders
            ],
            "artifacts": _public(artifacts),
            "blockers": blockers,
            # §10 coverage: required vs on-hand/reserved/open-ordered vs the
            # remnant pool → shortage → recommended purchase, per line.
            "coverage": coverage_for_version(org_id, version_id),
        }


def create_eligibility(
    *, org_id: UUID, actor_id: UUID, version_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    if data.get("confirmed") is not True:
        raise DocumentaryError("supplier_eligibility_confirmation_required")
    valid_until = (data.get("evidence") or {}).get("valid_until")
    if valid_until is not None and valid_until < datetime.now(timezone.utc).date():
        raise DocumentaryError("supplier_eligibility_expired")
    order_type = str(data["order_type"])
    keys = data["eligible_requirement_keys"]
    if (
        not isinstance(keys, list)
        or not keys
        or not all(isinstance(item, str) for item in keys)
        or len(keys) != len(set(keys))
    ):
        raise DocumentaryError("invalid_supplier_eligibility")
    keys = sorted(keys)
    with documentary_backend():
        version = _version(version_id, org_id)
        requirement_rows = _requirements(version_id, org_id, order_type)
        available = {str(item["requirement_key"]) for item in requirement_rows}
        if not available or not set(keys).issubset(available):
            raise DocumentaryError("supplier_eligibility_requirement_mismatch")
        content = {
            "schema_version": 1,
            "project_id": version["project_id"],
            "project_version_id": version_id,
            "bom_hash": version["bom_hash"],
            "snapshot_sha256": version["snapshot_sha256"],
            "order_type": order_type,
            "supplier_identity": data["supplier_identity"],
            "supplier_name": data["supplier_name"],
            "supplier_details": data["supplier_details"],
            "eligible_requirement_keys": keys,
            "evidence": data["evidence"],
            "version": data["version"],
        }
        content_hash = documentary_sha256_v1(content)
        eligibility = one(
            "INSERT INTO public.supplier_eligibility_versions("
            "project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,"
            "supplier_identity,supplier_name,supplier_details,eligible_requirement_keys,evidence,"
            "version,content_hash,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s) "
            "RETURNING id,content_hash",
            [version["project_id"], version_id, org_id, version["bom_hash"],
             version["snapshot_sha256"], order_type, data["supplier_identity"],
             data["supplier_name"], json_text(data["supplier_details"]), json_text(keys),
             json_text(data["evidence"]), data["version"], content_hash, actor_id],
        )
        return {"id": str(eligibility["id"]), "content_hash": eligibility["content_hash"]}


def allocate_requirement(
    *, org_id: UUID, actor_id: UUID, requirement_id: UUID, eligibility_id: UUID
) -> dict[str, object]:
    with documentary_backend():
        requirement = one(
            "SELECT id,requirement_key,project_id,project_version_id,org_id,order_type::text "
            "FROM public.purchase_requirement_lines WHERE id=%s AND org_id=%s",
            [requirement_id, org_id],
            "purchase_requirement_not_found",
        )
        eligibility = one(
            "SELECT id,project_id,project_version_id,org_id,order_type::text,"
            "eligible_requirement_keys::text FROM public.supplier_eligibility_versions "
            "WHERE id=%s AND org_id=%s",
            [eligibility_id, org_id],
            "supplier_eligibility_not_found",
        )
        binding = ("project_id", "project_version_id", "org_id", "order_type")
        if any(str(requirement[key]) != str(eligibility[key]) for key in binding):
            raise DocumentaryError("supplier_eligibility_requirement_mismatch")
        eligible_keys = _array(
            eligibility["eligible_requirement_keys"], "invalid_supplier_eligibility"
        )
        if str(requirement["requirement_key"]) not in eligible_keys:
            raise DocumentaryError("supplier_eligibility_requirement_mismatch")
        allocation = one(
            "INSERT INTO public.purchase_allocations("
            "requirement_line_id,supplier_eligibility_id,project_id,project_version_id,"
            "org_id,order_type,allocated_by) VALUES(%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(requirement_line_id) DO UPDATE SET "
            "supplier_eligibility_id=EXCLUDED.supplier_eligibility_id,"
            "allocated_by=EXCLUDED.allocated_by,allocated_at=now() "
            "RETURNING id,requirement_line_id,supplier_eligibility_id",
            [requirement_id, eligibility_id, requirement["project_id"],
             requirement["project_version_id"], org_id, requirement["order_type"], actor_id],
        )
        return {key: str(value) for key, value in allocation.items()}


def confirm_order_type_batch(
    *, org_id: UUID, actor_id: UUID, version_id: UUID,
    order_type: str, confirmed: bool,
) -> tuple[list[dict[str, object]], bool]:
    if not confirmed:
        raise DocumentaryError("order_batch_confirmation_required")
    with documentary_backend():
        version = _version(version_id, org_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"{version_id}:{order_type}"],
            )
        existing_batch = rows(
            "SELECT id FROM public.order_allocation_batches "
            "WHERE project_version_id=%s AND org_id=%s AND order_type=%s",
            [version_id, org_id, order_type],
        )
        if existing_batch:
            existing_orders = rows(
                "SELECT id,order_code,order_type::text,status::text,supplier_name,order_snapshot_hash "
                "FROM public.orders WHERE allocation_batch_id=%s ORDER BY supplier_name,id",
                [existing_batch[0]["id"]],
            )
            return (
                [_public(item) for item in existing_orders],
                False,
            )
        requirement_rows = _requirements(version_id, org_id, order_type)
        if not requirement_rows:
            raise DocumentaryError("order_type_has_no_requirements")
        allocations = rows(
            "SELECT allocation.id,allocation.requirement_line_id,allocation.supplier_eligibility_id,"
            "eligibility.supplier_identity,eligibility.supplier_name,"
            "eligibility.supplier_details::text,eligibility.eligible_requirement_keys::text,"
            "eligibility.evidence::text,eligibility.version,eligibility.content_hash "
            "FROM public.purchase_allocations allocation "
            "JOIN public.supplier_eligibility_versions eligibility "
            "ON eligibility.id=allocation.supplier_eligibility_id "
            "AND eligibility.project_version_id=allocation.project_version_id "
            "AND eligibility.org_id=allocation.org_id AND eligibility.order_type=allocation.order_type "
            "WHERE allocation.project_version_id=%s AND allocation.org_id=%s "
            "AND allocation.order_type=%s ORDER BY allocation.requirement_line_id FOR UPDATE OF allocation",
            [version_id, org_id, order_type],
        )
        allocation_by_requirement = {
            str(item["requirement_line_id"]): item for item in allocations
        }
        if len(allocation_by_requirement) != len(requirement_rows) or any(
            str(item["id"]) not in allocation_by_requirement for item in requirement_rows
        ):
            raise DocumentaryError("order_type_allocation_incomplete")
        supplier_eligibility: dict[str, str] = {}
        grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
        allocation_preimage = []
        for requirement in requirement_rows:
            allocation = allocation_by_requirement[str(requirement["id"])]
            keys = _array(
                allocation["eligible_requirement_keys"], "invalid_supplier_eligibility"
            )
            if str(requirement["requirement_key"]) not in keys:
                raise DocumentaryError("supplier_eligibility_requirement_mismatch")
            evidence = _object(allocation["evidence"], "invalid_supplier_eligibility")
            expiry = evidence.get("valid_until")
            if expiry and str(expiry) < datetime.now(timezone.utc).date().isoformat():
                raise DocumentaryError("supplier_eligibility_expired")
            supplier_identity = str(allocation["supplier_identity"])
            eligibility_id = str(allocation["supplier_eligibility_id"])
            prior = supplier_eligibility.get(supplier_identity)
            if prior is not None and prior != eligibility_id:
                raise DocumentaryError("supplier_eligibility_fragmented")
            supplier_eligibility[supplier_identity] = eligibility_id
            grouped[eligibility_id].append((requirement, allocation))
            allocation_preimage.append({
                "requirement_key": str(requirement["requirement_key"]),
                "supplier_eligibility_id": eligibility_id,
                "eligibility_content_hash": str(allocation["content_hash"]),
            })
        allocation_hash = documentary_sha256_v1({
            "schema_version": 1,
            "project_version_id": version_id,
            "order_type": order_type,
            "allocations": allocation_preimage,
        })
        confirmed_at = datetime.now(timezone.utc)
        batch = one(
            "INSERT INTO public.order_allocation_batches("
            "project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,"
            "allocation_hash,confirmed_by,confirmed_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id",
            [version["project_id"], version_id, org_id, version["bom_hash"],
             version["snapshot_sha256"], order_type, allocation_hash, actor_id, confirmed_at],
        )
        batch_id = UUID(str(batch["id"]))
        projection = one(
            "SELECT projection_hash FROM public.purchase_projections "
            "WHERE project_version_id=%s AND org_id=%s",
            [version_id, org_id],
            "purchase_projection_not_found",
        )
        outputs = []
        for eligibility_id in sorted(grouped):
            values = grouped[eligibility_id]
            eligibility = values[0][1]
            line_snapshots = [_line_snapshot(item) for item, _ in values]
            order_id = uuid5(
                NAMESPACE_URL,
                f"https://dekopen.local/order/{batch_id}/{eligibility_id}",
            )
            order_code = f"PO-{order_id.hex[:12].upper()}"
            allocation_identity = documentary_sha256_v1({
                "batch_allocation_hash": allocation_hash,
                "supplier_eligibility_id": eligibility_id,
                "requirement_keys": [item["requirement_key"] for item in line_snapshots],
            })
            eligibility_snapshot = {
                "id": eligibility_id,
                "version": int(eligibility["version"]),
                "content_hash": str(eligibility["content_hash"]),
                "supplier_identity": str(eligibility["supplier_identity"]),
                "supplier_name": str(eligibility["supplier_name"]),
                "supplier_details": _object(
                    eligibility["supplier_details"], "invalid_supplier_eligibility"
                ),
                "eligible_requirement_keys": _array(
                    eligibility["eligible_requirement_keys"], "invalid_supplier_eligibility"
                ),
                "evidence": _object(
                    eligibility["evidence"], "invalid_supplier_eligibility"
                ),
            }
            snapshot = {
                "schema_version": 1,
                "canonical_version": DOCUMENTARY_CANONICAL_VERSION,
                "order": {
                    "id": order_id,
                    "order_code": order_code,
                    "order_type": order_type,
                    "status": "DRAFT",
                    "project_code": version["project_code"],
                    "supplier_identity": eligibility["supplier_identity"],
                    "supplier_name": eligibility["supplier_name"],
                    "supplier_details": eligibility_snapshot["supplier_details"],
                    "confirmed_by": actor_id,
                    "confirmed_at": confirmed_at,
                },
                "revision": {
                    "project_id": version["project_id"],
                    "project_version_id": version_id,
                    "revision_code": version["revision_code"],
                    "bom_hash": version["bom_hash"],
                    "snapshot_sha256": version["snapshot_sha256"],
                    "purchase_projection_hash": projection["projection_hash"],
                },
                "allocation_batch_id": batch_id,
                "allocation_identity": allocation_identity,
                "supplier_eligibility": eligibility_snapshot,
                "lines": line_snapshots,
                # Issuer identity for the letterhead — sealed with the order so
                # re-renders keep the same branding.
                "organization": org_branding.branding_for_snapshot(org_id=org_id),
            }
            order_snapshot_hash = documentary_sha256_v1(snapshot)
            one(
                "INSERT INTO public.orders("
                "id,org_id,project_id,order_type,order_code,status,supplier_name,payload_json,"
                "project_version_id,allocation_batch_id,supplier_eligibility_id,bom_hash,"
                "revision_snapshot_sha256,purchase_projection_hash,allocation_identity,"
                "order_snapshot_hash,supplier_identity,supplier_details,confirmed_by,confirmed_at) "
                "VALUES(%s,%s,%s,%s,%s,'DRAFT',%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) "
                "RETURNING id",
                [order_id, org_id, version["project_id"], order_type, order_code,
                 eligibility["supplier_name"],
                 documentary_canonical_json_v1(snapshot).decode("utf-8"), version_id,
                 batch_id, UUID(eligibility_id), version["bom_hash"],
                 version["snapshot_sha256"], projection["projection_hash"],
                 allocation_identity, order_snapshot_hash, eligibility["supplier_identity"],
                 json_text(eligibility_snapshot["supplier_details"]), actor_id, confirmed_at],
            )
            for line, requirement in zip(line_snapshots, values, strict=True):
                requirement_row = requirement[0]
                line_hash = documentary_sha256_v1(line)
                one(
                    "INSERT INTO public.order_requirement_lines("
                    "order_id,requirement_line_id,project_id,project_version_id,org_id,order_type,"
                    "bom_hash,revision_snapshot_sha256,quantity,line_snapshot,line_hash) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id",
                    [order_id, requirement_row["id"], version["project_id"], version_id,
                     org_id, order_type, version["bom_hash"], version["snapshot_sha256"],
                     line["quantity"], documentary_canonical_json_v1(line).decode("utf-8"),
                     line_hash],
                )
            outputs.append({
                "id": str(order_id), "order_code": order_code, "order_type": order_type,
                "status": "DRAFT", "supplier_name": str(eligibility["supplier_name"]),
                "order_snapshot_hash": order_snapshot_hash,
            })
        return outputs, True


def send_order(
    *, org_id: UUID, actor_id: UUID, order_id: UUID, confirmed: bool,
    expected_at=None,
) -> dict[str, object]:
    if not confirmed:
        raise DocumentaryError("order_send_confirmation_required")
    with documentary_backend():
        order = one(
            "SELECT id,order_code,order_type::text,status::text,supplier_name,order_snapshot_hash "
            "FROM public.orders WHERE id=%s AND org_id=%s FOR UPDATE",
            [order_id, org_id],
            "order_not_found",
        )
        if order["order_type"] not in ORDER_TYPES:
            raise DocumentaryError("supplier_order_type_required")
        if order["status"] == "SENT":
            return {key: str(value) for key, value in order.items()}
        if order["status"] != "DRAFT":
            raise DocumentaryError("order_state_invalid")
        sent_at = datetime.now(timezone.utc)
        updated = one(
            "UPDATE public.orders SET status='SENT',sent_by=%s,sent_at=%s,"
            "expected_at=%s,updated_at=%s "
            "WHERE id=%s AND org_id=%s RETURNING id,order_code,order_type::text,status::text,"
            "supplier_name,order_snapshot_hash,expected_at",
            [actor_id, sent_at, expected_at, sent_at, order_id, org_id],
        )
        return _public(updated)


def cancel_order(
    *, org_id: UUID, actor_id: UUID, order_id: UUID, confirmed: bool
) -> dict[str, object]:
    """Cancel an order while no goods arrived. Cancellation is a human,
    consequential decision — it always requires the explicit attestation —
    and it is honest only for DRAFT/SENT orders: the moment a receipt exists
    the order is evidence of physical events and can never be cancelled."""
    if not confirmed:
        raise DocumentaryError("order_cancel_confirmation_required")
    with documentary_backend():
        order = one(
            "SELECT id,order_code,order_type::text,status::text,supplier_name,"
            "order_snapshot_hash,cancelled_by,cancelled_at,expected_at "
            "FROM public.orders WHERE id=%s AND org_id=%s FOR UPDATE",
            [order_id, org_id],
            "order_not_found",
        )
        if order["order_type"] not in ORDER_TYPES:
            raise DocumentaryError("supplier_order_type_required")
        if order["status"] == "CANCELLED":
            return _public(order)
        if order["status"] not in ("DRAFT", "SENT"):
            raise DocumentaryError("order_state_invalid")
        cancelled_at = datetime.now(timezone.utc)
        updated = one(
            "UPDATE public.orders SET status='CANCELLED',cancelled_by=%s,"
            "cancelled_at=%s,updated_at=%s "
            "WHERE id=%s AND org_id=%s RETURNING id,order_code,order_type::text,"
            "status::text,supplier_name,order_snapshot_hash,cancelled_by,"
            "cancelled_at,expected_at",
            [actor_id, cancelled_at, cancelled_at, order_id, org_id],
        )
        return _public(updated)
