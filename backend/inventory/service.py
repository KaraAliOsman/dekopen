"""Inventory orchestration: derived stock, order receiving, stock corrections.

Stock is derived exclusively from the append-only inventory_movements ledger.
Receiving a supplier order records what physically arrived
(order_receipts/order_receipt_lines) and writes one RECEIPT movement per good
quantity; order status advances through PARTIALLY_RECEIVED / FULFILLED."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID

from django.db import transaction

from documents.repository import DocumentaryError, documentary_backend, one, rows
from pricing.repository import json_text


def _decode_snapshot(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else json.loads(str(value))


def _line_item_identity(line_snapshot: dict[str, object]) -> dict[str, str]:
    sku = str(line_snapshot.get("purchasing_sku") or "")
    if not sku:
        raise DocumentaryError("receipt_line_sku_missing")
    specification = line_snapshot.get("specification")
    name = sku
    if isinstance(specification, dict):
        name = str(specification.get("name") or specification.get("title") or sku)
    return {
        "sku": sku,
        "name": name,
        "category": str(line_snapshot.get("category") or "UNSPECIFIED"),
        "unit": str(line_snapshot.get("unit") or "unit"),
        "variant_key": str(line_snapshot.get("physical_stock_identity") or ""),
    }


def list_stock(*, org_id: UUID) -> dict[str, object]:
    items = rows(
        """
        SELECT inventory_stock.item_id, sku, name, category, unit, variant_key,
               on_hand_qty, reserved_qty, (on_hand_qty - reserved_qty) AS available_qty,
               COALESCE(inc.incoming_qty, 0) AS incoming_qty,
               loc.racks
        FROM public.inventory_stock
        LEFT JOIN (
            SELECT item_id,
                   STRING_AGG(DISTINCT rack_location, ', ' ORDER BY rack_location) AS racks
            FROM public.inventory_movements
            WHERE org_id = %s
              AND rack_location IS NOT NULL
              AND rack_location <> ''
            GROUP BY item_id
        ) loc ON loc.item_id = public.inventory_stock.item_id
        LEFT JOIN (
            SELECT stock.item_id,
                   SUM(l.quantity - COALESCE(r.received_qty, 0)) AS incoming_qty
            FROM public.order_requirement_lines l
            JOIN public.orders o
                ON o.id = l.order_id AND o.org_id = l.org_id
                AND o.status IN ('SENT', 'PARTIALLY_RECEIVED')
            LEFT JOIN (
                SELECT order_line_id, SUM(received_qty) AS received_qty
                FROM public.order_receipt_lines
                GROUP BY order_line_id
            ) r ON r.order_line_id = l.id
            JOIN public.inventory_stock stock
                ON stock.org_id = l.org_id
                AND stock.variant_key = l.line_snapshot->>'physical_stock_identity'
            WHERE l.org_id = %s
            GROUP BY stock.item_id
        ) inc ON inc.item_id = public.inventory_stock.item_id
        WHERE inventory_stock.org_id = %s
        ORDER BY sku, variant_key
        """,
        [str(org_id), str(org_id), str(org_id)],
    )
    return {"items": items}


def list_movements(*, org_id: UUID, item_id: UUID | None, limit: int) -> dict[str, object]:
    clauses = ["m.org_id = %s"]
    parameters: list[object] = [str(org_id)]
    if item_id is not None:
        clauses.append("m.item_id = %s")
        parameters.append(str(item_id))
    parameters.append(limit)
    items = rows(
        f"""
        SELECT m.id, m.item_id, m.movement_type::text, m.quantity, m.order_id,
               m.order_line_id, m.lot_code, m.rack_location, m.note,
               m.actor_id, m.actor_label, m.created_at
        FROM public.inventory_movements m
        WHERE {' AND '.join(clauses)}
        ORDER BY m.created_at DESC
        LIMIT %s
        """,
        parameters,
    )
    return {"movements": items}


def order_receiving(*, org_id: UUID, order_id: UUID) -> dict[str, object]:
    with documentary_backend():
        order = one(
            """
            SELECT id, order_code, order_type::text, status::text, supplier_name
            FROM public.orders WHERE id = %s AND org_id = %s
            """,
            [str(order_id), str(org_id)],
            "order_not_found",
        )
        lines = rows(
            """
            SELECT l.id, l.quantity, l.line_snapshot,
                   COALESCE(r.received_qty, 0) AS received_qty,
                   COALESCE(r.damaged_qty, 0) AS damaged_qty
            FROM public.order_requirement_lines l
            LEFT JOIN (
                SELECT order_line_id, SUM(received_qty) AS received_qty,
                       SUM(damaged_qty) AS damaged_qty
                FROM public.order_receipt_lines
                GROUP BY order_line_id
            ) r ON r.order_line_id = l.id
            WHERE l.order_id = %s AND l.org_id = %s
            ORDER BY l.id
            """,
            [str(order_id), str(org_id)],
        )
        receipts = rows(
            """
            SELECT id, receipt_key, note, received_by, created_at
            FROM public.order_receipts
            WHERE order_id = %s AND org_id = %s
            ORDER BY created_at
            """,
            [str(order_id), str(org_id)],
        )
    public_lines = []
    for line in lines:
        snapshot = _decode_snapshot(line["line_snapshot"])
        # Damaged units are not fulfilment — the buyer still owes the line
        # their replacement, so outstanding counts usable receipts only.
        outstanding = max(
            line["quantity"] - (line["received_qty"] - line["damaged_qty"]),
            type(line["quantity"])(0),
        )
        public_lines.append(
            {
                "id": str(line["id"]),
                "ordered_qty": line["quantity"],
                "received_qty": line["received_qty"],
                "damaged_qty": line["damaged_qty"],
                "outstanding_qty": outstanding,
                "purchasing_sku": snapshot.get("purchasing_sku"),
                "category": snapshot.get("category"),
                "unit": snapshot.get("unit"),
                "physical_stock_identity": snapshot.get("physical_stock_identity"),
                "specification": snapshot.get("specification"),
            }
        )
    return {
        "order": {k: str(v) for k, v in order.items()},
        "lines": public_lines,
        "receipts": [
            {k: str(v) if v is not None else None for k, v in receipt.items()}
            for receipt in receipts
        ],
    }


def _next_order_status(*, org_id: UUID, order_id: UUID) -> str:
    # Fulfilment is per line: an over-receipt on one line must not hide a
    # shortage on another.
    totals = one(
        """
        SELECT COALESCE(bool_and(complete), FALSE) AS fulfilled
        FROM (
            SELECT COALESCE(r.received_qty, 0) - COALESCE(r.damaged_qty, 0)
                   >= l.quantity AS complete
            FROM public.order_requirement_lines l
            LEFT JOIN (
                SELECT order_line_id, SUM(received_qty) AS received_qty,
                       SUM(damaged_qty) AS damaged_qty
                FROM public.order_receipt_lines
                GROUP BY order_line_id
            ) r ON r.order_line_id = l.id
            WHERE l.order_id = %s AND l.org_id = %s
        ) per_line
        """,
        [str(order_id), str(org_id)],
        "order_lines_missing",
    )
    if totals["fulfilled"]:
        return "FULFILLED"
    return "PARTIALLY_RECEIVED"


def receive_order(
    *,
    org_id: UUID,
    actor_id: UUID,
    order_id: UUID,
    receipt_key: str,
    note: str | None,
    lines: list[dict[str, Any]],
    actor_label: str | None = None,
) -> tuple[dict[str, object], bool]:
    """Record a physical receipt against a SENT/partial order. Idempotent per
    (org, receipt_key): a replayed key returns the existing receipt."""
    with transaction.atomic(), documentary_backend():
        # Serialize retries on the same (org, receipt_key) pair so a concurrent
        # replay waits for the first transaction instead of racing the insert.
        rows(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"{org_id}:{receipt_key}"],
        )
        existing = rows(
            "SELECT id, receipt_key, order_id FROM public.order_receipts WHERE org_id = %s AND receipt_key = %s",
            [str(org_id), receipt_key],
        )
        if existing:
            if str(existing[0]["order_id"]) != str(order_id):
                raise DocumentaryError("receipt_key_reused")
            return order_receiving(org_id=org_id, order_id=order_id), False

        order = one(
            """
            SELECT id, status::text FROM public.orders
            WHERE id = %s AND org_id = %s FOR UPDATE
            """,
            [str(order_id), str(org_id)],
            "order_not_found",
        )
        status = str(order["status"])
        if status == "DRAFT":
            raise DocumentaryError("order_not_sent")
        if status in ("FULFILLED", "CANCELLED"):
            raise DocumentaryError("order_state_invalid")

        order_lines = {
            str(row["id"]): row
            for row in rows(
                "SELECT id, quantity, line_snapshot FROM public.order_requirement_lines "
                "WHERE order_id = %s AND org_id = %s",
                [str(order_id), str(org_id)],
            )
        }
        receipt = one(
            """
            INSERT INTO public.order_receipts(org_id, order_id, receipt_key, note, received_by)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            [str(org_id), str(order_id), receipt_key, note, str(actor_id)],
        )
        receipt_id = receipt["id"]
        for entry in lines:
            order_line_id = str(entry["order_line_id"])
            line = order_lines.get(order_line_id)
            if line is None:
                raise DocumentaryError("receipt_line_unknown")
            received_qty = entry["received_qty"]
            damaged_qty = entry["damaged_qty"]
            if damaged_qty > received_qty:
                raise DocumentaryError("receipt_damage_exceeds_received")
            receipt_line = one(
                """
                INSERT INTO public.order_receipt_lines(
                    receipt_id, order_line_id, received_qty, damaged_qty,
                    lot_code, rack_location, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                [
                    str(receipt_id),
                    order_line_id,
                    received_qty,
                    damaged_qty,
                    entry.get("lot_code"),
                    entry.get("rack_location"),
                    entry.get("note"),
                ],
            )
            good_qty = received_qty - damaged_qty
            if good_qty <= 0:
                continue
            snapshot = _decode_snapshot(line["line_snapshot"])
            identity = _line_item_identity(snapshot)
            item = one(
                """
                INSERT INTO public.inventory_items(
                    org_id, sku, name, category, unit, variant_key, attributes)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (org_id, sku, variant_key)
                DO UPDATE SET sku = EXCLUDED.sku
                RETURNING id
                """,
                [
                    str(org_id),
                    identity["sku"],
                    identity["name"],
                    identity["category"],
                    identity["unit"],
                    identity["variant_key"],
                    json_text(snapshot.get("specification") or {}),
                ],
            )
            one(
                """
                INSERT INTO public.inventory_movements(
                    org_id, item_id, movement_type, quantity, order_id,
                    order_line_id, receipt_line_id, lot_code, rack_location,
                    note, actor_id, actor_label)
                VALUES (%s, %s, 'RECEIPT', %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    str(org_id),
                    str(item["id"]),
                    good_qty,
                    str(order_id),
                    order_line_id,
                    str(receipt_line["id"]),
                    entry.get("lot_code"),
                    entry.get("rack_location"),
                    entry.get("note"),
                    str(actor_id),
                    actor_label,
                ],
            )
        new_status = _next_order_status(org_id=org_id, order_id=order_id)
        one(
            "UPDATE public.orders SET status = %s, updated_at = %s WHERE id = %s AND org_id = %s RETURNING id",
            [new_status, datetime.now(timezone.utc), str(order_id), str(org_id)],
        )
        return order_receiving(org_id=org_id, order_id=order_id), True


def record_movement(
    *,
    org_id: UUID,
    actor_id: UUID,
    item_id: UUID,
    movement_type: str,
    quantity: Any,
    lot_code: str | None,
    note: str,
    rack_location: str | None = None,
    actor_label: str | None = None,
) -> dict[str, object]:
    """Manual stock corrections. Reservation/consumption stay reserved for
    production flows; here only RECEIPT-free adjustments are allowed."""
    if movement_type not in ("ADJUSTMENT", "RETURN", "SCRAP"):
        raise DocumentaryError("movement_type_not_allowed")
    with transaction.atomic(), documentary_backend():
        item = one(
            "SELECT id FROM public.inventory_items WHERE id = %s AND org_id = %s",
            [str(item_id), str(org_id)],
            "inventory_item_not_found",
        )
        movement = one(
            """
            INSERT INTO public.inventory_movements(
                org_id, item_id, movement_type, quantity, lot_code,
                rack_location, note, actor_id, actor_label)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, item_id, movement_type::text, quantity, order_id,
                      order_line_id, lot_code, rack_location, note,
                      actor_id, actor_label, created_at
            """,
            [
                str(org_id),
                str(item["id"]),
                movement_type,
                quantity,
                lot_code,
                rack_location,
                note,
                str(actor_id),
                actor_label,
            ],
        )
    return dict(movement)
