"""Explicit supplier allocation and one confirmed batch per revision/order type."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import connection, transaction

from dekopen_engine.documentary_canonical import (
    DOCUMENTARY_CANONICAL_VERSION,
    documentary_canonical_json_v1,
    documentary_sha256_v1,
)

from documents.renderers import _piece_labels
from documents.repository import DocumentaryError, decoded, documentary_backend, json_text, next_human_code, one, rows, write
from inventory.production_stock import coverage_for_version
from inventory.service import stock_variant_key
from mail import service as mail_service
from projects import org_branding

logger = logging.getLogger(__name__)


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


def _trace_labels(version_id: UUID, org_id: UUID) -> dict[str, str]:
    """Human-facing codes for trace ids (M-01 members, V-01 bays, I-01 glass) so
    a purchaser reads where each requirement comes from instead of raw hashes.
    Same sequential codes the workshop documents print — one identity space."""
    row = one(
        "SELECT snapshot_json::text AS snapshot_json FROM public.project_versions "
        "WHERE id=%s AND org_id=%s",
        [version_id, org_id],
        "project_version_not_found",
    )
    snapshot = _object(row["snapshot_json"], "invalid_frozen_revision_snapshot")
    merged: dict[str, str] = {}
    for kind_map in _piece_labels(snapshot).values():
        for key, label in kind_map.items():
            if key is not None:
                merged.setdefault(str(key), label)
    return merged


def _line_snapshot(row: dict[str, object],
                   labels: dict[str, str] | None = None,
                   quantity_override=None,
                   unit_price=None) -> dict[str, object]:
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
    if quantity_override is not None:
        quantity = Decimal(str(quantity_override))
    else:
        quantity = Decimal(str(row["quantity"]))
    if quantity != quantity.to_integral_value() or quantity <= 0:
        raise DocumentaryError("invalid_purchase_requirement")
    snapshot = {
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
        "source_trace_labels": [
            labels.get(entry) if labels is not None else None
            for entry in source_trace
        ],
    }
    # El precio acordado con el proveedor se sella dentro de la línea — la OC
    # es un documento y su monto no se deriva después, vive en la evidencia.
    if unit_price is not None:
        snapshot["unit_price"] = str(Decimal(str(unit_price)))
    return snapshot


def _requirements(version_id: UUID, org_id: UUID,
                  order_type: str | None = None) -> list[dict[str, object]]:
    condition = "" if order_type is None else " AND order_type=%s"
    parameters: list[object] = [version_id, org_id]
    if order_type is not None:
        parameters.append(order_type)
    result = rows(
        "SELECT line.id,line.requirement_key,line.project_id,line.project_version_id,"
        "line.org_id,line.order_type::text AS order_type,"
        "line.category,line.technical_identity::text,line.purchasing_sku,"
        "line.physical_stock_identity,line.unit,"
        "line.quantity,line.specification::text,line.source_trace::text "
        "FROM public.purchase_requirement_lines line "
        "WHERE line.project_version_id=%s AND line.org_id=%s"
        + condition
        + " ORDER BY line.order_type,line.category,line.purchasing_sku,line.requirement_key",
        parameters,
    )
    # Stock display identity resolves the same bucket the receiver writes
    # (psi, else the spec hash for made-to-measure glass) — a SQL join on psi
    # alone can never reach a spec-keyed row.
    stock_names = {
        (str(item["sku"]), str(item["variant_key"])): item
        for item in rows(
            "SELECT sku, name, variant_key FROM public.inventory_stock "
            "WHERE org_id = %s",
            [org_id],
        )
    }
    for line in result:
        specification = line.get("specification")
        variant = stock_variant_key(
            line.get("physical_stock_identity"),
            json.loads(str(specification)) if specification else None,
            line.get("category"),
        )
        item = stock_names.get((str(line["purchasing_sku"]), variant))
        line["physical_stock_sku"] = item["sku"] if item else None
        line["physical_stock_name"] = item["name"] if item else None
    return result


def _unclaimed_requirements(version_id: UUID, org_id: UUID,
                            order_type: str) -> list[dict[str, object]]:
    """Requirement lines not fully covered by order lines. Coverage is
    quantity-aware: each order line covers `quantity - released_qty`, so a
    cancellation releases the unreceived remainder (a partially-received
    line keeps covering only what physically arrived) and the requirement
    comes back here carrying its open quantity — never the full amount
    again, which would re-order already-received goods."""
    covered = {
        str(row["requirement_line_id"]): Decimal(str(row["covered_qty"]))
        for row in rows(
            "SELECT requirement_line_id, SUM(quantity - released_qty) AS covered_qty "
            "FROM public.order_requirement_lines "
            "WHERE project_version_id=%s AND org_id=%s "
            "GROUP BY requirement_line_id",
            [version_id, org_id],
        )
    }
    result = []
    for item in _requirements(version_id, org_id, order_type):
        open_qty = (
            Decimal(str(item["quantity"]))
            - covered.get(str(item["id"]), Decimal(0))
        )
        if open_qty > 0:
            item["open_qty"] = open_qty
            result.append(item)
    return result


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
        labels = _trace_labels(version_id, org_id)
        requirements = [
            _line_snapshot(item, labels) for item in _requirements(version_id, org_id)
        ]
        eligibilities = rows(
            "SELECT id,order_type::text,supplier_identity,supplier_name,supplier_details::text,"
            "eligible_requirement_keys::text,evidence::text,version,content_hash,created_at "
            "FROM public.supplier_eligibility_versions WHERE project_version_id=%s AND org_id=%s "
            "ORDER BY order_type,supplier_name,supplier_identity,version",
            [version_id, org_id],
        )
        today = datetime.now(timezone.utc).date().isoformat()
        for eligibility in eligibilities:
            expiry = _object(
                eligibility["evidence"], "invalid_supplier_eligibility"
            ).get("valid_until")
            eligibility["expired"] = bool(expiry) and str(expiry) < today
        allocations = rows(
            "SELECT allocation.id,allocation.requirement_line_id,allocation.supplier_eligibility_id,"
            "allocation.order_type::text,allocation.allocated_at,allocation.unit_price "
            "FROM public.purchase_allocations allocation WHERE allocation.project_version_id=%s "
            "AND allocation.org_id=%s ORDER BY allocation.order_type,allocation.requirement_line_id",
            [version_id, org_id],
        )
        orders = rows(
            "SELECT o.id,o.order_code,o.order_type::text,o.status::text,o.supplier_identity,"
            "o.supplier_name,o.order_snapshot_hash,o.confirmed_at,o.sent_at,o.expected_at,"
            "o.sent_to,o.cancelled_at,o.supplier_details::text AS supplier_details,"
            "l.line_count,l.total_qty,l.released_qty,l.lines_preview::text AS lines_preview,"
            "l.priced_amount,l.unpriced_lines,"
            "r.damaged_qty,r.receipt_count "
            "FROM public.orders o LEFT JOIN ("
            "SELECT order_id, COUNT(*) AS line_count, SUM(quantity) AS total_qty,"
            " SUM(COALESCE(released_qty, 0)) AS released_qty,"
            " jsonb_agg(jsonb_build_object('sku',line_snapshot->>'purchasing_sku',"
            " 'qty',quantity,'unit',line_snapshot->>'unit',"
            " 'unit_price',line_snapshot->>'unit_price') ORDER BY id) AS lines_preview,"
            " SUM(quantity * (line_snapshot->>'unit_price')::numeric) "
            " FILTER (WHERE line_snapshot->>'unit_price' IS NOT NULL) AS priced_amount,"
            " COUNT(*) FILTER (WHERE line_snapshot->>'unit_price' IS NULL) AS unpriced_lines"
            " FROM public.order_requirement_lines WHERE org_id=%s GROUP BY order_id"
            ") l ON l.order_id=o.id "
            "LEFT JOIN ("
            "SELECT rc.order_id, SUM(rl.damaged_qty) AS damaged_qty,"
            " COUNT(DISTINCT rc.id) AS receipt_count "
            "FROM public.order_receipts rc "
            "JOIN public.order_receipt_lines rl ON rl.receipt_id=rc.id "
            "WHERE rc.org_id=%s GROUP BY rc.order_id"
            ") r ON r.order_id=o.id "
            "WHERE o.project_version_id=%s AND o.org_id=%s "
            "ORDER BY o.order_type,o.supplier_name,o.id",
            [org_id, org_id, version_id, org_id],
        )
        artifacts = rows(
            "SELECT id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,file_sha256,"
            "byte_size,created_at FROM public.document_artifacts "
            "WHERE project_version_id=%s AND org_id=%s ORDER BY document_type,format,id",
            [version_id, org_id],
        )
        allocated = {str(item["requirement_line_id"]) for item in allocations}
        coverage = {
            str(row["requirement_line_id"]): Decimal(str(row["covered_qty"]))
            for row in rows(
                "SELECT requirement_line_id, SUM(quantity - released_qty) AS covered_qty "
                "FROM public.order_requirement_lines "
                "WHERE project_version_id=%s AND org_id=%s "
                "GROUP BY requirement_line_id",
                [version_id, org_id],
            )
        }
        for item in requirements:
            covered_qty = coverage.get(str(item["id"]), Decimal(0))
            open_qty = Decimal(str(item["quantity"])) - covered_qty
            item["claimed"] = open_qty <= 0
            item["open_qty"] = int(open_qty) if open_qty > 0 else 0
        for item in orders:
            item["total_amount"] = item.pop("priced_amount", None)
            item["unpriced_lines"] = int(item.get("unpriced_lines") or 0)
        covered_keys = {
            (str(item["order_type"]), str(key))
            for item in eligibilities
            if not item["expired"]
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
                    "supplier_details": _object(
                        item["supplier_details"] or {}, "invalid_order_snapshot"
                    ),
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
        _upsert_supplier(
            org_id=org_id, actor_id=actor_id,
            tax_id=str(data["supplier_identity"]),
            name=str(data["supplier_name"]),
            details=data.get("supplier_details") or {},
        )
        return {"id": str(eligibility["id"]), "content_hash": eligibility["content_hash"]}


def allocate_requirement(
    *, org_id: UUID, actor_id: UUID, requirement_id: UUID, eligibility_id: UUID,
    unit_price: object = None,
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
            "eligible_requirement_keys::text,evidence::text FROM public.supplier_eligibility_versions "
            "WHERE id=%s AND org_id=%s",
            [eligibility_id, org_id],
            "supplier_eligibility_not_found",
        )
        expiry = _object(eligibility["evidence"], "invalid_supplier_eligibility").get(
            "valid_until"
        )
        if expiry and str(expiry) < datetime.now(timezone.utc).date().isoformat():
            raise DocumentaryError("supplier_eligibility_expired")
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
            "org_id,order_type,allocated_by,unit_price) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(requirement_line_id) DO UPDATE SET "
            "supplier_eligibility_id=EXCLUDED.supplier_eligibility_id,"
            "allocated_by=EXCLUDED.allocated_by,allocated_at=now(),"
            "unit_price=EXCLUDED.unit_price "
            "RETURNING id,requirement_line_id,supplier_eligibility_id,unit_price",
            [requirement_id, eligibility_id, requirement["project_id"],
             requirement["project_version_id"], org_id, requirement["order_type"], actor_id,
             unit_price],
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
        labels = _trace_labels(version_id, org_id)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"{version_id}:{order_type}"],
            )
        existing_batch = rows(
            "SELECT id,attempt FROM public.order_allocation_batches "
            "WHERE project_version_id=%s AND org_id=%s AND order_type=%s "
            "ORDER BY attempt DESC",
            [version_id, org_id, order_type],
        )
        # Requirements already claimed by a live order line stay claimed — a
        # re-confirm only covers lines released by a cancellation.
        requirement_rows = _unclaimed_requirements(version_id, org_id, order_type)
        attempt = 1
        if existing_batch:
            # Idempotent while the batch covers the type and nothing was
            # released. When cancelled orders released requirement lines, the
            # buyer confirms a new attempt — a fresh batch, never a mutation
            # of the cancelled one. The response lists every live order of the
            # type, across attempts.
            if not requirement_rows:
                return (
                    [
                        _public(item) for item in rows(
                            "SELECT id,order_code,order_type::text,status::text,supplier_name,order_snapshot_hash "
                            "FROM public.orders "
                            "WHERE project_version_id=%s AND org_id=%s AND order_type=%s "
                            "AND status <> 'CANCELLED' ORDER BY supplier_name,id",
                            [version_id, org_id, order_type],
                        )
                    ],
                    False,
                )
            attempt = int(existing_batch[0]["attempt"]) + 1
        elif not requirement_rows:
            raise DocumentaryError("order_type_has_no_requirements")
        allocations = rows(
            "SELECT allocation.id,allocation.requirement_line_id,allocation.supplier_eligibility_id,"
            "allocation.unit_price,"
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
        # Allocations persist for requirements a partially-received cancel
        # left covered — this batch only needs one per UNCLAIMED line.
        if any(
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
            "attempt": attempt,
            "allocations": allocation_preimage,
        })
        confirmed_at = datetime.now(timezone.utc)
        batch = one(
            "INSERT INTO public.order_allocation_batches("
            "project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,"
            "allocation_hash,attempt,confirmed_by,confirmed_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
            "RETURNING id",
            [version["project_id"], version_id, org_id, version["bom_hash"],
             version["snapshot_sha256"], order_type, allocation_hash, attempt,
             actor_id, confirmed_at],
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
            line_snapshots = [
                _line_snapshot(
                    item, labels,
                    quantity_override=item.get("open_qty"),
                    unit_price=alloc["unit_price"],
                )
                for item, alloc in values
            ]
            order_id = uuid5(
                NAMESPACE_URL,
                f"https://dekopen.local/order/{batch_id}/{eligibility_id}",
            )
            # Folio humano OC- por org — private.next_human_code serializa
            # con advisory lock, así que órdenes concurrentes del mismo
            # batch obtienen folios consecutivos. Las órdenes ya emitidas
            # conservan su folio PO-… sellado (order_snapshot_hash).
            order_code = next_human_code(org_id, "orders")
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


# Tipo de documento de la OC por tipo de compra — el envío emite el PDF
# en el mismo clic humano que encola el correo (DOC-02 vidrios, DOC-04
# perfiles, DOC-08 herrajes y paneles).
_ORDER_DOC_TYPES = {
    "SUPPLIER_GLASS_PO": "DOC-02",
    "SUPPLIER_PROFILE_PO": "DOC-04",
    "SUPPLIER_HARDWARE_PO": "DOC-08",
    "SUPPLIER_PANEL_PO": "DOC-08",
}


def send_order(
    *, org_id: UUID, actor_id: UUID, order_id: UUID, confirmed: bool,
    expected_at=None, sent_to=None, role: str | None = None,
) -> dict[str, object]:
    if not confirmed:
        raise DocumentaryError("order_send_confirmation_required")
    with documentary_backend():
        order = one(
            "SELECT id,order_code,order_type::text,status::text,supplier_name,order_snapshot_hash,"
            "project_version_id "
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
        if sent_to is not None:
            sent_to = str(sent_to).strip() or None
        updated = one(
            "UPDATE public.orders SET status='SENT',sent_by=%s,sent_at=%s,"
            "expected_at=%s,sent_to=%s,updated_at=%s "
            "WHERE id=%s AND org_id=%s RETURNING id,order_code,order_type::text,status::text,"
            "supplier_name,order_snapshot_hash,expected_at,sent_to",
            [actor_id, sent_at, expected_at, sent_to, sent_at, order_id, org_id],
        )
        # Aviso al proveedor por el outbox: la fila mail_messages es la
        # evidencia del envío (sandbox entrega simulada; SMTP real se activa
        # por ACTIVACION.md). Un proveedor sin correo declarado queda SKIPPED.
        output = _public(updated)
        try:
            # Savepoint: si el outbox falla, sólo se deshace la fila de
            # correo — un except a pelo dejaría la transacción abortada y el
            # commit del SENT caería con ella.
            with transaction.atomic():
                output["mail"] = mail_service.deliver_order_sent(
                    org_id=org_id, order_id=order_id,
                    sent_to=str(sent_to or ""),
                )
        except Exception:  # el correo nunca tira la transición de la OC
            logger.exception("order mail enqueue failed for %s", order_id)
            output["mail"] = None
    # El PDF de la OC se emite en el mismo clic: job_runs es service-owned,
    # así que el enqueue pide el cambio de rol explícito (fuera del bloque
    # documentary_backend que ya cerró). Si falla, la OC ya quedó SENT y el
    # PDF se puede emitir manual desde la lista de documentos de la orden.
    doc_type = _ORDER_DOC_TYPES.get(str(order["order_type"]))
    if doc_type is not None and order.get("project_version_id") is not None and role is not None:
        try:
            from jobs.service import enqueue as enqueue_job, job_backend

            # job_backend fuera, savepoint dentro: primero se deshace el
            # INSERT fallido y luego se restaura el rol (si el savepoint va
            # fuera, el restore del rol quedaría bloqueado por la tx abortada).
            with job_backend(), transaction.atomic():
                job, _created = enqueue_job(
                    org_id=org_id,
                    job_type="document.artifact.generate",
                    payload={
                        "document_type": doc_type,
                        "format": "PDF",
                        "project_version_id": str(order["project_version_id"]),
                        "order_id": str(order_id),
                    },
                    idempotency_key=f"{doc_type.lower()}:pdf:{order_id}",
                    created_by=actor_id,
                    role=role,
                )
            output["document_job"] = {"id": str(job["id"]), "document_type": doc_type}
        except Exception:
            logger.exception("order PDF job enqueue failed for %s", order_id)
            output["document_job"] = None
    return output


def cancel_order(
    *, org_id: UUID, actor_id: UUID, order_id: UUID, confirmed: bool
) -> dict[str, object]:
    """Cancel an order. Cancellation is a human, consequential decision —
    it always requires the explicit attestation. For DRAFT/SENT the whole
    order releases; for PARTIALLY_RECEIVED the received (usable) quantities
    remain covered by the received goods and only the unreceived remainder
    returns to open demand. FULFILLED orders can never be cancelled — every
    line is already evidence of physical events."""
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
        if order["status"] not in ("DRAFT", "SENT", "PARTIALLY_RECEIVED"):
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
        # Release the line claims so the same requirements can be ordered
        # again. The release is quantity-aware: each line releases only what
        # was never received as usable goods (received - damaged keeps
        # covering the requirement — that material physically arrived and is
        # evidence, never re-ordered). The cancelled order's rows remain as
        # evidence, stamped released_at.
        write(
            "UPDATE public.order_requirement_lines l SET released_at=%s,"
            " released_qty = GREATEST(0, l.quantity - COALESCE(("
            " SELECT SUM(g.received_qty - g.damaged_qty)"
            " FROM public.order_receipt_lines g WHERE g.order_line_id = l.id"
            " ),0)) "
            "WHERE l.order_id=%s AND l.org_id=%s AND l.released_at IS NULL",
            [cancelled_at, order_id, org_id],
        )
        return _public(updated)


def orders_index(org_id: UUID, status: str | None = None) -> dict[str, object]:
    """Org-wide purchase-order index — the purchaser's day view: every order
    with its project, revision, expected date, and how much is still to arrive."""
    params: list[object] = [org_id]
    status_filter = ""
    if status:
        status_filter = " AND o.status=%s"
        params.append(status)
    with documentary_backend():
        orders = rows(
            "SELECT o.id,o.order_code,o.order_type::text,o.status::text,o.supplier_identity,"
            "o.supplier_name,o.expected_at,o.sent_at,o.sent_to,o.created_at,"
            "v.revision_code,v.id AS project_version_id,"
            "p.id AS project_id,p.code AS project_code,"
            "COALESCE(l.line_count,0) AS line_count,l.total_qty,l.released_qty,"
            "l.priced_amount,l.unpriced_lines,"
            "COALESCE(r.good_qty,0) AS good_qty,COALESCE(r.damaged_qty,0) AS damaged_qty,"
            "COALESCE(r.receipt_count,0) AS receipt_count "
            "FROM public.orders o "
            "LEFT JOIN public.project_versions v "
            "ON v.id=o.project_version_id AND v.org_id=o.org_id "
            "LEFT JOIN public.projects p ON p.id=o.project_id AND p.org_id=o.org_id "
            "LEFT JOIN ("
            "SELECT order_id, COUNT(*) AS line_count, SUM(quantity) AS total_qty,"
            " SUM(COALESCE(released_qty, 0)) AS released_qty,"
            " SUM(quantity * (line_snapshot->>'unit_price')::numeric) "
            " FILTER (WHERE line_snapshot->>'unit_price' IS NOT NULL) AS priced_amount,"
            " COUNT(*) FILTER (WHERE line_snapshot->>'unit_price' IS NULL) AS unpriced_lines"
            " FROM public.order_requirement_lines WHERE org_id=%s GROUP BY order_id"
            ") l ON l.order_id=o.id "
            "LEFT JOIN ("
            "SELECT rc.order_id,"
            " SUM(rl.received_qty - rl.damaged_qty) AS good_qty,"
            " SUM(rl.damaged_qty) AS damaged_qty,"
            " COUNT(DISTINCT rc.id) AS receipt_count "
            "FROM public.order_receipts rc "
            "JOIN public.order_receipt_lines rl ON rl.receipt_id=rc.id "
            "WHERE rc.org_id=%s GROUP BY rc.order_id"
            ") r ON r.order_id=o.id "
            # Purchasing index lists supplier purchase orders only — WORKSHOP_OT
            # rows are production work orders sharing the orders table.
            "WHERE o.org_id=%s AND o.order_type<>'WORKSHOP_OT'" + status_filter + " "
            "ORDER BY CASE WHEN o.expected_at IS NULL THEN 1 ELSE 0 END,"
            "o.expected_at,o.created_at DESC,o.id",
            [org_id, org_id] + params,
        )
        result = []
        for item in orders:
            item = dict(item)
            total = Decimal(str(item.get("total_qty") or 0))
            good = Decimal(str(item.get("good_qty") or 0))
            item["outstanding_qty"] = total - good
            item["total_amount"] = item.pop("priced_amount", None)
            item["unpriced_lines"] = int(item.get("unpriced_lines") or 0)
            result.append(_public(item))
        return {"orders": result}



def _upsert_supplier(
    *, org_id: UUID, actor_id: UUID, tax_id: str, name: str, details: object
) -> dict[str, object]:
    tax_id = tax_id.strip()
    name = name.strip()
    if not tax_id or not name:
        raise DocumentaryError("invalid_supplier")
    if not isinstance(details, dict):
        raise DocumentaryError("invalid_supplier")
    row = one(
        "INSERT INTO public.suppliers(org_id,tax_id,name,details,created_by) "
        "VALUES(%s,%s,%s,%s::jsonb,%s) "
        "ON CONFLICT(org_id,tax_id) DO UPDATE SET "
        "name=EXCLUDED.name,details=EXCLUDED.details,updated_at=now() "
        "RETURNING id,tax_id,name,details::text AS details,updated_at",
        [org_id, tax_id, name, json_text(details), actor_id],
    )
    return {
        "id": str(row["id"]),
        "tax_id": str(row["tax_id"]),
        "name": str(row["name"]),
        "details": _object(row["details"], "invalid_supplier"),
        "updated_at": str(row["updated_at"]),
    }


def create_supplier(*, org_id: UUID, actor_id: UUID, data: dict[str, object]) -> dict[str, object]:
    if data.get("confirmed") is not True:
        raise DocumentaryError("supplier_confirmation_required")
    with documentary_backend():
        return _upsert_supplier(
            org_id=org_id, actor_id=actor_id,
            tax_id=str(data.get("tax_id") or ""),
            name=str(data.get("name") or ""),
            details=data.get("details") or {},
        )


def suppliers_index(org_id: UUID) -> dict[str, object]:
    with documentary_backend():
        entries = rows(
            "SELECT id,tax_id,name,details::text AS details,updated_at "
            "FROM public.suppliers WHERE org_id=%s ORDER BY name,tax_id",
            [org_id],
        )
        return {
            "suppliers": [
                {**_public(item), "details": _object(item["details"], "invalid_supplier")}
                for item in entries
            ]
        }
