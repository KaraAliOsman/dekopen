"""§10: production stock loop.

From a sealed work-order plan DEKOPEN determines what stock the plan consumes,
reserves it on the append-only inventory ledger, and consumes the reservation
at the routing step where the material is physically used — so required →
reserved → consumed → remaining is one traceable chain. Concurrent work
orders cannot reserve the same stock: each item row is locked FOR UPDATE
inside the transaction before balances are recomputed, so a second order can
only ever see the stock the first one left behind.
"""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from uuid import UUID


from documents.repository import one, rows
from inventory.service import stock_variant_key


def _dec(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _identity_identities(org_id: UUID, authority_ids: set[str]) -> dict[str, dict[str, str | None]]:
    """stock_authority_id → purchasing identity (commercial sku + physical
    stock identity), resolved across the two BAR stock authorities."""
    if not authority_ids:
        return {}
    listed = sorted(authority_ids)
    # Both authority tables carry global rows (org_id IS NULL) — the cutting
    # repository's effective scope accepts them, so reservation lookup must
    # too, or globally-mapped bars reserve against an empty variant key.
    profile = rows(
        """
        SELECT id::text AS authority_id, commercial_sku,
               physical_stock_identity::text AS physical_stock_identity
        FROM public.profile_purchase_mappings
        WHERE (org_id = %s OR org_id IS NULL) AND id = ANY(%s::uuid[])
        """,
        [str(org_id), listed],
    )
    reinforce = rows(
        """
        SELECT id::text AS authority_id, commercial_sku,
               physical_stock_identity::text AS physical_stock_identity
        FROM public.reinforcement_articles
        WHERE (org_id = %s OR org_id IS NULL) AND id = ANY(%s::uuid[])
        """,
        [str(org_id), listed],
    )
    merged: dict[str, dict[str, str | None]] = {}
    for row in [*profile, *reinforce]:
        merged[str(row["authority_id"])] = {
            "purchasing_sku": str(row["commercial_sku"]),
            "physical_stock_identity": row.get("physical_stock_identity"),
        }
    return merged


def _balances(item_id: str) -> tuple[Decimal, Decimal]:
    row = one(
        """
        SELECT
            COALESCE(SUM(CASE
                WHEN movement_type IN ('RECEIPT', 'RETURN', 'ADJUSTMENT') THEN quantity
                WHEN movement_type IN ('CONSUMPTION', 'SCRAP') THEN -quantity
                ELSE 0 END), 0) AS on_hand,
            COALESCE(SUM(CASE
                WHEN movement_type = 'RESERVATION' THEN quantity
                WHEN movement_type IN ('RELEASE', 'CONSUMPTION') THEN -quantity
                ELSE 0 END), 0) AS reserved
        FROM public.inventory_movements WHERE item_id = %s
        """,
        [item_id],
        "inventory_item_missing",
    )
    return _dec(row["on_hand"]), _dec(row["reserved"])


def _upsert_item(
    *,
    org_id: UUID,
    sku: str,
    name: str,
    category: str,
    unit: str,
    variant_key: str,
) -> dict[str, object]:
    """Upsert the item and keep the row locked until commit — the upsert's
    row lock is what serializes concurrent reservations on the same stock."""
    return one(
        """
        INSERT INTO public.inventory_items(
            org_id, sku, name, category, unit, variant_key, attributes)
        VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb)
        ON CONFLICT (org_id, sku, variant_key)
        DO UPDATE SET sku = EXCLUDED.sku
        RETURNING id
        """,
        [str(org_id), sku, name, category, unit, variant_key],
        "inventory_item_missing",
    )


def reserve_for_order(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    needs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reserve ``needs`` (a stock need per planned material) for a work order.

    Each need is ``{kind, sku, variant_key, name, category, unit, needed}``.
    The reservation caps at the stock actually available — shortfall is
    reported, never fabricated. Movement rows carry the order id so the hold
    is attributable and releasable.

    Must run inside the caller's transaction (``optimize_work_order`` already
    holds the order row FOR UPDATE)."""
    report: list[dict[str, Any]] = []
    for need in needs:
        needed = _dec(need["needed"])
        if needed <= 0:
            continue
        item = _upsert_item(
            org_id=org_id,
            sku=str(need["sku"]),
            name=str(need.get("name") or need["sku"]),
            category=str(need.get("category") or need["kind"]),
            unit=str(need.get("unit") or "EA"),
            variant_key=str(need.get("variant_key") or ""),
        )
        on_hand, reserved = _balances(str(item["id"]))
        available = on_hand - reserved
        grant = min(needed, max(available, Decimal("0")))
        if grant > 0:
            rows(
                """
                INSERT INTO public.inventory_movements(
                    org_id, item_id, movement_type, quantity, order_id,
                    note, actor_id)
                VALUES (%s, %s, 'RESERVATION', %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    str(org_id),
                    str(item["id"]),
                    grant,
                    str(order_id),
                    f"wo-reserve:{need['kind']}",
                    str(actor_id) if actor_id else None,
                ],
            )
        report.append({
            "kind": need["kind"],
            "sku": need["sku"],
            "variant_key": str(need.get("variant_key") or ""),
            "name": str(need.get("name") or need["sku"]),
            "unit": str(need.get("unit") or "EA"),
            "needed": str(needed),
            "on_hand": str(on_hand),
            "reserved": str(grant),
            "short": str(needed - grant),
            "consumed_at": None,
        })
    return report


def release_for_order(*, org_id: UUID, order_id: UUID, actor_id: UUID) -> int:
    """Release every still-open reservation a work order holds — called before
    a re-optimize so the new plan re-reserves atomically under one lock."""
    pending = rows(
        """
        SELECT item_id, SUM(CASE
            WHEN movement_type = 'RESERVATION' THEN quantity
            WHEN movement_type IN ('RELEASE', 'CONSUMPTION') THEN -quantity
            ELSE 0 END) AS outstanding
        FROM public.inventory_movements
        WHERE org_id = %s AND order_id = %s
        GROUP BY item_id
        """,
        [str(org_id), str(order_id)],
    )
    released = 0
    for row in pending:
        outstanding = _dec(row["outstanding"])
        if outstanding <= 0:
            continue
        rows(
            """
            INSERT INTO public.inventory_movements(
                org_id, item_id, movement_type, quantity, order_id,
                note, actor_id)
            VALUES (%s, %s, 'RELEASE', %s, %s, 'wo-replan-release', %s)
            RETURNING id
            """,
            [
                str(org_id),
                str(row["item_id"]),
                outstanding,
                str(order_id),
                str(actor_id) if actor_id else None,
            ],
        )
        released += 1
    return released


def consume_for_order(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    kinds: set[str],
    reservations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Consume the open reservations of the given ``kinds`` — written at the
    routing step where that material is physically used (bars at CUT, kits
    and fittings at ASSEMBLE, panels at GLAZE). Consumed quantity is exactly
    the held quantity: production can never consume stock it did not reserve.
    Returns the updated reservation report (``consumed_at`` stamped)."""
    now = rows(
        "SELECT now() AS at",
        [],
    )[0]["at"]
    held: dict[tuple[str, str], Decimal] = {}
    consumed: list[dict[str, Any]] = []
    for entry in reservations:
        if entry.get("kind") not in kinds or entry.get("consumed_at"):
            continue
        if _dec(entry["reserved"]) <= 0:
            continue
        key = (str(entry["sku"]), str(entry.get("variant_key") or ""))
        held[key] = held.get(key, Decimal("0")) + _dec(entry["reserved"])
        entry["consumed_at"] = str(now)
        consumed.append(entry)
    for (sku, variant_key), quantity in held.items():
        item = one(
            """
            SELECT id FROM public.inventory_items
            WHERE org_id = %s AND sku = %s AND variant_key = %s
            """,
            [str(org_id), sku, variant_key],
            "inventory_item_missing",
        )
        if quantity <= 0:
            continue
        rows(
            """
            INSERT INTO public.inventory_movements(
                org_id, item_id, movement_type, quantity, order_id,
                note, actor_id)
            VALUES (%s, %s, 'CONSUMPTION', %s, %s, 'wo-consume', %s)
            RETURNING id
            """,
            [
                str(org_id),
                str(item["id"]),
                quantity,
                str(order_id),
                str(actor_id) if actor_id else None,
            ],
        )
    return reservations


def bar_stock_needs(
    *,
    org_id: UUID,
    bars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fold the plan's NEW-source bars into inventory stock needs, keyed by
    the purchasing identity of each bar's stock authority."""
    ids = {
        str(bar.get("stock_authority_id"))
        for bar in bars
        if bar.get("source") == "NEW" and bar.get("stock_authority_id")
    }
    identities = _identity_identities(org_id, ids)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    missing: list[dict[str, Any]] = []
    for bar in bars:
        if bar.get("source") != "NEW":
            continue
        authority_id = bar.get("stock_authority_id")
        identity = identities.get(str(authority_id)) if authority_id else None
        if identity is None:
            # No authority row → the plan still works; the stock need is only
            # reported against the commercial sku so nothing is fabricated.
            missing.append({
                "kind": "BAR",
                "sku": str(bar.get("commercial_sku") or ""),
                "variant_key": "",
                "name": str(bar.get("commercial_sku") or ""),
                "category": "PROFILE",
                "unit": "BAR",
                "needed": Decimal("1"),
            })
            continue
        key = (identity["purchasing_sku"], str(identity.get("physical_stock_identity") or ""))
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "kind": "BAR",
                "sku": identity["purchasing_sku"],
                "variant_key": key[1],
                "name": identity["purchasing_sku"],
                "category": "PROFILE",
                "unit": "BAR",
                "needed": Decimal("1"),
            }
        else:
            entry["needed"] += Decimal("1")
    return [*grouped.values(), *missing]


def _mapping_rows(org_id: UUID, system_id: str, query: str, skus: set[str]) -> dict[str, str]:
    """technical sku → purchasing sku across one authority table; unmapped
    technical skus simply absent — coverage reports them, nothing invented."""
    found: dict[str, str] = {}
    for row in rows(query, [system_id, sorted(skus), str(org_id)]):
        found[str(row["technical_sku"])] = str(row["purchasing_sku"])
    return found


def unit_stock_needs(
    *,
    org_id: UUID,
    system_id: str,
    quantity: int,
    hardware_items: list[dict[str, Any]],
    fittings: list[dict[str, Any]],
    panels: list[dict[str, Any]],
    sheet_purchases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Fold the sealed materials of one work order into inventory stock needs.

    Returns (needs, unmapped_skus) — unmapped technical skus have no declared
    purchasing authority, so they can never resolve to a stock item; they are
    reported, not silently dropped."""
    multiplier = Decimal(str(max(int(quantity), 1)))
    needs: list[dict[str, Any]] = []
    unmapped: list[str] = []

    kit_skus = {str(item["kit_sku"]) for item in hardware_items if item.get("kit_sku")}
    kit_map = _mapping_rows(
        org_id, system_id,
        """
        SELECT DISTINCT ON (kit.sku) kit.sku AS technical_sku,
               mapping.purchasing_sku
        FROM public.hardware_purchase_mappings mapping
        JOIN public.hardware_kits kit ON kit.id = mapping.hardware_kit_id
        WHERE kit.system_id = %s AND kit.sku = ANY(%s)
          AND (mapping.org_id IS NULL OR mapping.org_id = %s)
        ORDER BY kit.sku, mapping.org_id NULLS LAST
        """,
        kit_skus,
    ) if kit_skus else {}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    def _add(kind: str, sku: str, name: str, qty: Decimal, unit: str = "EA") -> None:
        key = (kind, sku)
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "kind": kind, "sku": sku, "variant_key": "",
                "name": name, "category": kind, "unit": unit,
                "needed": qty,
            }
        else:
            entry["needed"] += qty

    for item in hardware_items:
        kit_sku = str(item.get("kit_sku") or "")
        purchasing = kit_map.get(kit_sku)
        if purchasing is None:
            unmapped.append(kit_sku)
            continue
        _add("HARDWARE_KIT", purchasing, str(item.get("name") or kit_sku),
             _dec(item.get("qty") or 1) * multiplier, unit="KIT")

    fitting_skus = {str(p["sku"]) for p in fittings if p.get("sku")}
    fitting_map = _mapping_rows(
        org_id, system_id,
        """
        SELECT DISTINCT ON (technical_sku) technical_sku, purchasing_sku
        FROM public.fitting_purchase_mappings
        WHERE system_id = %s AND technical_sku = ANY(%s)
          AND (org_id IS NULL OR org_id = %s)
        ORDER BY technical_sku, org_id NULLS LAST
        """,
        fitting_skus,
    ) if fitting_skus else {}
    for piece in fittings:
        sku = str(piece.get("sku") or "")
        purchasing = fitting_map.get(sku)
        if purchasing is None:
            unmapped.append(sku)
            continue
        _add("FITTING", purchasing, sku, _dec(piece.get("qty") or 1) * multiplier)

    panel_skus = {str(p["sku"]) for p in panels if p.get("sku")}
    panel_map = _mapping_rows(
        org_id, system_id,
        """
        SELECT panel.sku AS technical_sku, authority.purchasing_sku
        FROM public.panel_purchase_authorities authority
        JOIN public.infill_articles panel ON panel.id = authority.infill_article_id
        WHERE panel.system_id = %s AND panel.sku = ANY(%s)
          AND (authority.org_id IS NULL OR authority.org_id = %s)
        """,
        panel_skus,
    ) if panel_skus else {}
    for piece in panels:
        sku = str(piece.get("sku") or "")
        purchasing = panel_map.get(sku)
        if purchasing is None:
            unmapped.append(sku)
            continue
        _add("PANEL", purchasing, str(piece.get("name") or sku), multiplier)

    for purchase in sheet_purchases:
        if str(purchase.get("group_kind") or "GLASS") != "GLASS":
            # Panel-group sheet purchases stay on the panel purchase-authority
            # path above (PANEL need at GLAZE; unmapped panels gate the step) —
            # reserving the sheet too would book the same physical good twice.
            continue
        # `SheetPurchase` carries `purchasing_sku` — the commercial identity
        # purchase orders and receiving book against — not `workshop_sku`.
        sku = str(
            purchase.get("purchasing_sku")
            or purchase.get("workshop_sku")
            or purchase.get("commercial_sku")
            or ""
        )
        if not sku:
            continue
        _add("SHEET", sku, sku, _dec(purchase.get("qty_sheets") or purchase.get("qty_bars") or 1))

    needs.extend(grouped.values())
    return needs, sorted(set(unmapped))


_BAR_UNITS = {"BAR"}


def coverage_for_version(org_id: UUID, version_id: UUID) -> dict[str, Any]:
    """§10 coverage: for a frozen production version, per requirement line —
    required, what physical stock exists, what is already held by other work,
    what open purchase orders cover, the reusable remnant pool, the resulting
    shortage and the recommended purchase quantity.

    Pure read: immutable requirement lines are never mutated; all quantities
    come from the ledger view and sealed order evidence."""
    lines = rows(
        """
        SELECT id::text, order_type::text, category, purchasing_sku,
               physical_stock_identity::text, unit::text, quantity,
               technical_identity::text, specification::text
        FROM public.purchase_requirement_lines
        WHERE project_version_id = %s AND org_id = %s
        ORDER BY order_type, category, purchasing_sku, requirement_key
        """,
        [str(version_id), str(org_id)],
    )
    if not lines:
        return {"version_id": str(version_id), "lines": [], "shortages": 0}
    line_ids = [line["id"] for line in lines]
    ordered = {
        str(row["requirement_line_id"]): _dec(row["qty"])
        for row in rows(
            """
            SELECT lines.requirement_line_id::text, SUM(lines.quantity) AS qty
            FROM public.order_requirement_lines lines
            JOIN public.orders o ON o.id = lines.order_id
            WHERE lines.org_id = %s AND lines.requirement_line_id = ANY(%s::uuid[])
              AND lines.released_at IS NULL
              -- Every live order is a decision already made: a DRAFT may not
              -- be sent yet, but it still means "do not buy this again" — and
              -- a CANCELLED order's lines are released, not counted.
              AND o.status <> 'CANCELLED'
            GROUP BY lines.requirement_line_id
            """,
            [str(org_id), line_ids],
        )
    }
    received = {
        str(row["requirement_line_id"]): _dec(row["qty"])
        for row in rows(
            """
            SELECT order_line.requirement_line_id::text,
                   SUM(receipt_line.received_qty - receipt_line.damaged_qty) AS qty
            FROM public.order_receipt_lines receipt_line
            JOIN public.order_receipts receipt
              ON receipt.id = receipt_line.receipt_id
            JOIN public.order_requirement_lines order_line
              ON order_line.id = receipt_line.order_line_id
            WHERE receipt.org_id = %s
              AND order_line.requirement_line_id = ANY(%s::uuid[])
            GROUP BY order_line.requirement_line_id
            """,
            [str(org_id), line_ids],
        )
    }
    stock = {
        (str(row["sku"]), str(row["variant_key"] or "")): row
        for row in rows(
            """
            SELECT sku, variant_key, on_hand_qty, reserved_qty
            FROM public.inventory_stock WHERE org_id = %s
            """,
            [str(org_id)],
        )
    }
    psi_values = [
        line["physical_stock_identity"] for line in lines
        if line.get("physical_stock_identity")
    ]
    bar_remnants: dict[str, dict[str, Any]] = {}
    if psi_values:
        for row in rows(
            """
            SELECT physical_stock_identity::text AS psi,
                   COUNT(*) AS count, SUM(length_mm) AS total_mm
            FROM public.inventory_remnants
            WHERE org_id = %s AND kind = 'BAR' AND status = 'AVAILABLE'
              AND physical_stock_identity = ANY(%s::uuid[])
            GROUP BY physical_stock_identity
            """,
            [str(org_id), psi_values],
        ):
            bar_remnants[str(row["psi"])] = {
                "count": int(row["count"]),
                "total_mm": str(_dec(row["total_mm"])),
            }
    sheet_remnants: dict[str, int] = {}
    sheet_skus = sorted({
        str(json.loads(line["technical_identity"]).get("workshop_sku") or "")
        for line in lines
        if line["unit"] == "EA"
        and isinstance(line.get("technical_identity"), str)
        and '"workshop_sku"' in line["technical_identity"]
    } - {""})
    if sheet_skus:
        for row in rows(
            """
            SELECT sheet_workshop_sku AS sku, COUNT(*) AS count
            FROM public.inventory_remnants
            WHERE org_id = %s AND kind = 'SHEET' AND status = 'AVAILABLE'
              AND sheet_workshop_sku = ANY(%s)
            GROUP BY sheet_workshop_sku
            """,
            [str(org_id), sheet_skus],
        ):
            sheet_remnants[str(row["sku"])] = int(row["count"])

    coverage: list[dict[str, Any]] = []
    shortages = 0
    # Stock is allocated against lines sequentially — two requirement lines
    # sharing a SKU must not both draw on the same on-hand units, or the
    # suggested purchase understates the real need (review PU3).
    allocated: dict[tuple[str, str], Decimal] = {}
    for line in lines:
        sku = str(line["purchasing_sku"])
        psi = line.get("physical_stock_identity") or ""
        # Same bucket identity the receiver assigns: psi, else the spec hash —
        # a cut-glass line must see its own stock row, not collide on "".
        spec = line.get("specification")
        variant = stock_variant_key(
            psi,
            json.loads(spec) if isinstance(spec, str) else spec,
            line.get("category"),
        )
        required = _dec(line["quantity"])
        stock_row = stock.get((sku, variant))
        on_hand = _dec(stock_row["on_hand_qty"]) if stock_row else Decimal("0")
        reserved = _dec(stock_row["reserved_qty"]) if stock_row else Decimal("0")
        pool = allocated.get((sku, variant))
        if pool is None:
            pool = max(on_hand - reserved, Decimal("0"))
        covered = min(required, max(pool, Decimal("0")))
        allocated[(sku, variant)] = pool - covered
        available = pool
        bought = ordered.get(str(line["id"]), Decimal("0"))
        arrived = received.get(str(line["id"]), Decimal("0"))
        open_ordered = max(bought - arrived, Decimal("0"))
        shortage = max(required - covered, Decimal("0"))
        # Recommended purchase covers what stock cannot, less what is already
        # on its way — ordering more would double-buy.
        recommended = max(shortage - open_ordered, Decimal("0"))
        # The headline counter answers the buyer's question — how many lines
        # still need purchasing action — not how many lack stock on hand.
        if recommended > 0:
            shortages += 1
        remnant: dict[str, Any] | None = None
        if str(line["unit"]) == "BAR" and psi:
            pool = bar_remnants.get(str(psi))
            if pool:
                remnant = {"kind": "BAR", **pool}
        else:
            identity = line.get("technical_identity")
            workshop_sku = ""
            if isinstance(identity, str):
                workshop_sku = str(
                    json.loads(identity).get("workshop_sku") or ""
                )
            count = sheet_remnants.get(workshop_sku or sku)
            if count:
                remnant = {"kind": "SHEET", "count": count}
        coverage.append({
            "requirement_line_id": str(line["id"]),
            "order_type": line["order_type"],
            "category": line["category"],
            "purchasing_sku": sku,
            "physical_stock_identity": str(psi) or None,
            "unit": line["unit"],
            "required": str(required),
            "on_hand": str(on_hand),
            "reserved": str(reserved),
            "available": str(available),
            "ordered": str(bought),
            "received": str(arrived),
            "open_ordered": str(open_ordered),
            "remnant_pool": remnant,
            "shortage": str(shortage),
            "recommended_purchase": str(recommended),
        })
    return {
        "version_id": str(version_id),
        "lines": coverage,
        "shortages": shortages,
    }
