"""§11 work-order traceability — assemble the sealed chain in both directions.

Forward: project → version → position → module/bay/leaf → article → cut
piece → stock source → plan → work order. Backward: any cut ``piece_id``
resolves to the work order, plan location and routing progress it lives in.

Everything returned here is read-only evidence: the chain is decoded from the
sealed ``orders.payload_json`` plan and the append-only step/movement ledgers
— nothing is recomputed or inferred. IDs are the stable identities the sealed
artifacts already carry (``piece_id`` hashes, position/bay/leaf uuids,
``stock_authority_id``, remnant and movement ids)."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from documents.repository import (
    DocumentaryError,
    documentary_backend,
    one,
    rows,
)
from documents.renderers import (
    _cut_key,
    _cut_member_map,
    _cut_spec_index,
    _infill_code_map,
    _infill_key,
    _infill_spec_index,
    _location,
    _piece_labels,
)

from dekopen_engine.cutting import CutBar
from dekopen_engine.manufacturing import ManufacturingFactsV1
from dekopen_engine.operations import (
    OperationKind,
    member_meta_map,
    operations_from_plan,
)


def _decoded(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _trace_piece(cut: dict[str, Any], code: str | None = None) -> dict[str, Any]:
    """The stable identity of one cut piece — everything needed to walk
    backward from the physical label to its origin member. ``code`` is the
    shop-facing code (M-xx/R-xx/I-xx) the printed packs carry, so screen and
    paper name the same piece identically."""
    return {
        "piece_id": cut.get("piece_id"),
        "code": code,
        "sequence": cut.get("sequence"),
        "role": cut.get("role"),
        "length_mm": cut.get("length_mm"),
        "width_mm": cut.get("width_mm"),
        "height_mm": cut.get("height_mm"),
        "angle_left": cut.get("angle_left"),
        "angle_right": cut.get("angle_right"),
        "sagitta_mm": cut.get("sagitta_mm"),
        "workshop_sku": cut.get("workshop_sku"),
        "source_kind": cut.get("source_kind"),
        "x_mm": cut.get("x_mm"),
        "y_mm": cut.get("y_mm"),
        "rotated": cut.get("rotated"),
        "source_position_id": cut.get("source_position_id"),
        "module_id": cut.get("module_id"),
        "bay_id": cut.get("bay_id"),
        "leaf_id": cut.get("leaf_id"),
        "unit_index": cut.get("unit_index"),
        "machining": cut.get("machining"),
    }


def _plan_bars(
    optimization: dict[str, Any],
    cut_map: dict[tuple[str, ...], str] | None = None,
) -> list[dict[str, Any]]:
    bars = (optimization.get("bars") or {}).get("workshop_cut_plan") or []
    plan = []
    for bar in bars:
        plan.append({
            "bar_index": bar.get("bar_index"),
            "commercial_sku": bar.get("commercial_sku"),
            "material": bar.get("material"),
            "color": bar.get("color"),
            "source": bar.get("source"),
            "stock_authority_id": bar.get("stock_authority_id"),
            "stock_length_mm": bar.get("stock_length_mm"),
            "remainder_mm": bar.get("remainder_mm"),
            "yield_pct": bar.get("yield_pct"),
            "cuts": [
                _trace_piece(cut, (cut_map or {}).get(_cut_key(cut)))
                for cut in bar.get("cuts") or []
            ],
        })
    return plan


def _plan_sheets(
    optimization: dict[str, Any],
    infill_map: dict[tuple[str, str, str], str] | None = None,
) -> list[dict[str, Any]]:
    sheets = optimization.get("sheets") or []
    plan = []
    for sheet in sheets:
        plan.append({
            "sheet_index": sheet.get("sheet_index"),
            "workshop_sku": sheet.get("workshop_sku"),
            "material": sheet.get("material"),
            "width_mm": sheet.get("sheet_width_mm"),
            "height_mm": sheet.get("sheet_height_mm"),
            "purchasing_sku": sheet.get("purchasing_sku"),
            "remnant_id": sheet.get("remnant_id"),
            "yield_pct": sheet.get("yield_pct"),
            "source": sheet.get("source"),
            "pieces": [
                _trace_piece(piece, (infill_map or {}).get(_infill_key(piece)))
                for piece in sheet.get("placements") or []
            ],
        })
    return plan


def trace_work_order(*, org_id: UUID, order_id: UUID) -> dict[str, Any]:
    """The full forward chain for one work order."""
    order = one(
        """
        SELECT id::text, order_code, status::text, project_id::text,
               project_version_id::text, order_type::text,
               payload_json::text, created_at, updated_at
        FROM public.orders WHERE id = %s AND org_id = %s
        """,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )
    payload = _decoded(order["payload_json"])
    optimization = _decoded(payload.get("optimization")) or {}

    project = None
    if order["project_id"]:
        project = one(
            """
            SELECT id::text, code, name, client_name, current_revision
            FROM public.projects WHERE id = %s AND org_id = %s
            """,
            [order["project_id"], str(org_id)],
            "work_order_not_found",
        )

    version = None
    version_snapshot: dict[str, Any] = {}
    if order["project_version_id"]:
        # The frozen snapshot (PII/pricing/BOM) is denied to the
        # authenticated role — the documentary authority resolves it
        # server-side and only a role-safe projection reaches the client.
        with documentary_backend():
            version = one(
                """
                SELECT id::text, revision_code, snapshot_sha256, bom_hash,
                       emitted_at, production_allowed, snapshot_json::text
                FROM public.project_versions WHERE id = %s AND org_id = %s
                """,
                [order["project_version_id"], str(org_id)],
                "work_order_not_found",
            )
        version_snapshot = _decoded(version.pop("snapshot_json", None))

    steps = rows(
        """
        SELECT step.id::text, step.sequence, step.code, step.label,
               step.status, step.work_center_id::text,
               work_center.code AS work_center_code,
               work_center.name AS work_center_name,
               step.started_at, step.finished_at, step.actor_id::text,
               step.note
        FROM public.production_steps step
        LEFT JOIN public.work_centers work_center
          ON work_center.id = step.work_center_id
        WHERE step.order_id = %s AND step.org_id = %s
        ORDER BY step.sequence
        """,
        [str(order_id), str(org_id)],
    )

    events = rows(
        """
        SELECT id::text, step_id::text, event, actor_id::text,
               payload::text, created_at
        FROM public.production_step_events
        WHERE order_id = %s AND org_id = %s
        ORDER BY created_at
        """,
        [str(order_id), str(org_id)],
    )
    for event in events:
        event["payload"] = _decoded(event["payload"])

    movements = rows(
        """
        SELECT movement.id::text, movement.movement_type::text,
               movement.quantity, movement.note,
               movement.created_at, movement.actor_id::text,
               item.id::text AS item_id, item.sku, item.variant_key,
               item.name AS item_name
        FROM public.inventory_movements movement
        JOIN public.inventory_items item ON item.id = movement.item_id
        WHERE movement.order_id = %s AND movement.org_id = %s
        ORDER BY movement.created_at
        """,
        [str(order_id), str(org_id)],
    )

    remnants = rows(
        """
        SELECT id::text, kind, status, material, color,
               stock_authority_id::text, sheet_workshop_sku,
               physical_stock_identity::text,
               length_mm, width_mm, height_mm, origin,
               origin_order_id::text, reserved_order_id::text,
               consumed_order_id::text, rack_location
        FROM public.inventory_remnants
        WHERE org_id = %s AND (
            origin_order_id = %s OR reserved_order_id = %s
            OR consumed_order_id = %s)
        ORDER BY created_at
        """,
        [str(org_id), str(order_id), str(order_id), str(order_id)],
    )

    position_id = payload.get("position_id")
    # Shop-facing piece/location codes (M-xx/R-xx/I-xx/V-xx/H-xx) — the same
    # codes the printed packs emit, so web and paper reconcile.
    piece_label_map: dict[str, str] = {}
    labels: dict[str, dict[object, str]] = {}
    cut_map: dict[tuple[str, ...], str] = {}
    infill_map: dict[tuple[str, str, str], str] = {}
    if version_snapshot:
        try:
            labels = _piece_labels(version_snapshot)
            for group in labels.values():
                for key, code in group.items():
                    piece_label_map[str(key)] = code
            cut_map = _cut_member_map(version_snapshot, labels)
            infill_map = _infill_code_map(version_snapshot, labels)
        except DocumentaryError:
            piece_label_map = {}
            cut_map = {}
            infill_map = {}
    return {
        "work_order": {
            "id": order["id"],
            "order_code": order["order_code"],
            "order_type": order["order_type"],
            "status": order["status"],
            "created_at": order["created_at"],
            "updated_at": order["updated_at"],
        },
        "project": project,
        "version": version,
        "position_id": position_id,
        "labels": piece_label_map,
        "plan": {
            "optimized_at": optimization.get("optimized_at"),
            "strategy": optimization.get("strategy"),
            "color": optimization.get("color"),
            "units": optimization.get("units"),
            "bars": _plan_bars(optimization, cut_map),
            "sheets": _plan_sheets(optimization, infill_map),
            "unnested": optimization.get("unnested") or [],
        },
        "stock": {
            "reservations": optimization.get("stock_reservations") or [],
            "unmapped_stock_skus": optimization.get("unmapped_stock_skus") or [],
            "movements": movements,
            "remnants": remnants,
        },
        "steps": steps,
        "events": events,
        "operations": _trace_operations(
            payload=payload,
            optimization=optimization,
            version_snapshot=version_snapshot,
            step_codes={str(step["code"]) for step in steps},
        ),
    }


def station_map_for(payload: dict[str, Any], kinds: list[str]) -> dict[str, str]:
    """The frozen process authority decides which station an op kind lands
    on — the UI groups by this declared map, never by a frontend guess.
    Orders frozen before the authority model keep the legacy routing the
    shop used: saw cuts at the saw, every other member op at machining."""
    authority_map = (payload.get("process_authority") or {}).get(
        "operation_station_map"
    )
    if authority_map:
        station_map = dict(authority_map)
        station_map.setdefault("SAW_CUT", "CUT")
        return station_map
    return {
        kind: ("CUT" if kind == "SAW_CUT" else "MACHINING") for kind in kinds
    }


def _trace_operations(
    *,
    payload: dict[str, Any],
    optimization: dict[str, Any],
    version_snapshot: dict[str, Any],
    step_codes: set[str] | None = None,
) -> dict[str, Any]:
    """The sealed plan's machining operations, reconstructed deterministically
    — the same derivation ``export_operations`` uses, computed at read time so
    the operator sees them without sealing an export. Empty when the order has
    not been optimized or the frozen snapshot carries no manufacturing facts."""
    raw_bars = (optimization.get("bars") or {}).get("workshop_cut_plan") or []
    raw_units = [
        unit
        for unit in (version_snapshot.get("manufacturing") or [])
        if not payload.get("position_id")
        or str(unit.get("position_id")) == str(payload["position_id"])
    ]
    if not raw_bars:
        return {"count": 0, "items": [], "unemitted_kinds": []}
    try:
        bars = [
            CutBar.model_validate_json(json.dumps(bar)) for bar in raw_bars
        ]
        fact_units = [
            ManufacturingFactsV1.model_validate_json(json.dumps(unit))
            for unit in raw_units
        ]
    except Exception:
        return {"count": 0, "items": [], "unemitted_kinds": [],
                "unavailable": "operations_underivable"}
    ops_issues: list[dict[str, object]] = []
    derived = operations_from_plan(
        bars=bars, fact_units=fact_units, issues=ops_issues
    )
    ops = [op.model_dump(mode="json") for op in derived]
    by_kind: dict[str, int] = {}
    for op in ops:
        by_kind[str(op["kind"])] = by_kind.get(str(op["kind"]), 0) + 1
    station_map = station_map_for(payload, list(by_kind))
    for op in ops:
        op["station"] = station_map.get(str(op["kind"]))
    # Ops mapped to a station the order never got are floor-invisible: no
    # card claims them and the order can complete with work undone. Name
    # them so the read surface — and the operator banner — can flag them.
    unclaimed: list[dict[str, Any]] = []
    if step_codes is not None:
        by_station: dict[str, list[str]] = {}
        for op in ops:
            station = op.get("station")
            if station and station not in step_codes:
                by_station.setdefault(str(station), []).append(
                    str(op["kind"])
                )
        unclaimed = [
            {
                "station": station,
                "operation_count": len(kinds),
                "kinds": sorted(set(kinds)),
            }
            for station, kinds in sorted(by_station.items())
        ]
    emitted = set(by_kind)
    unemitted = sorted(
        kind.value for kind in OperationKind if kind.value not in emitted
    )
    return {
        "count": len(ops),
        "by_kind": by_kind,
        "items": ops,
        "station_map": station_map,
        # Sealed member geometry the ops reference — the station card draws
        # the member strip and anchors each op on it without a snapshot read.
        "members": member_meta_map(fact_units),
        "unemitted_kinds": unemitted,
        "unclaimed": unclaimed,
        "issues": ops_issues,
        "plan_invalidated": bool(optimization.get("invalidated")),
        "process_authority": payload.get("process_authority") or {},
    }


def _piece_hits(
    order_row: dict[str, Any],
    piece_id: str,
    *,
    spec_keys: set[tuple[str, ...]] | None = None,
    infill_keys: set[tuple[str, str, str]] | None = None,
    bay_ids: set[str] | None = None,
    leaf_ids: set[str] | None = None,
    position_ids: set[str] | None = None,
    unit_index: int | None = None,
    cut_map: dict[tuple[str, ...], str] | None = None,
    infill_map: dict[tuple[str, str, str], str] | None = None,
) -> list[dict[str, Any]]:
    """Locate ``piece_id`` inside one order's sealed plan — directly by piece
    hash, or indirectly through a resolved printed code: ``spec_keys`` are the
    member/reinforcement spec tuples a scanned M-xx/R-xx resolves to,
    ``infill_keys`` the (position, bay, leaf) tuples an I-xx resolves to, and
    the plain id sets cover location (V-xx/H-xx/P-nn) and unit (-Unn) codes."""
    payload = _decoded(order_row["payload_json"])
    optimization = _decoded(payload.get("optimization")) or {}
    hits: list[dict[str, Any]] = []
    for bar in _plan_bars(optimization, cut_map):
        for cut in bar["cuts"]:
            matched = cut["piece_id"] == piece_id
            if not matched and spec_keys is not None:
                matched = _cut_key(cut) in spec_keys
            if not matched and bay_ids is not None:
                matched = str(cut.get("bay_id") or "") in bay_ids
            if not matched and leaf_ids is not None:
                matched = str(cut.get("leaf_id") or "") in leaf_ids
            if not matched and position_ids is not None:
                matched = str(cut.get("source_position_id") or "") in position_ids
            if not matched and unit_index is not None:
                matched = cut.get("unit_index") == unit_index
            if matched:
                hits.append({
                    "kind": "BAR",
                    "bar_index": bar["bar_index"],
                    "commercial_sku": bar["commercial_sku"],
                    "piece": cut,
                })
    for sheet in _plan_sheets(optimization, infill_map):
        for piece in sheet["pieces"]:
            matched = piece["piece_id"] == piece_id
            if not matched and infill_keys is not None:
                matched = _infill_key(piece) in infill_keys
            if not matched and bay_ids is not None:
                matched = str(piece.get("bay_id") or "") in bay_ids
            if not matched and leaf_ids is not None:
                matched = str(piece.get("leaf_id") or "") in leaf_ids
            if not matched and position_ids is not None:
                matched = str(piece.get("source_position_id") or "") in position_ids
            if not matched and unit_index is not None:
                matched = piece.get("unit_index") == unit_index
            if matched:
                hits.append({
                    "kind": "SHEET",
                    "sheet_index": sheet["sheet_index"],
                    "workshop_sku": sheet["workshop_sku"],
                    "piece": piece,
                })
    return hits


_CODE_RE = re.compile(r"^(MAN|M|R|I|V|H)-?(\d+)$|^P-?(\d+)$|^-?U(\d+)$", re.IGNORECASE)
# Scanned unit-label identities: the packing QR payload
# ``DEKOPEN|<order_code>|<label_code>|<pieces>`` and the printed label code
# ``<order_code>-U<nn>`` both end in the unit marker.
_QR_RE = re.compile(r"^DEKOPEN\|([^|]+)\|([^|]+)\|", re.IGNORECASE)
_UNIT_SUFFIX_RE = re.compile(r"-?U(\d+)$", re.IGNORECASE)
_UNIT_LABEL_RE = re.compile(r"^(.+)-U(\d+)$", re.IGNORECASE)


def _scan_order_hint(query: str) -> str | None:
    """The label itself says which order it belongs to — a QR payload
    (``DEKOPEN|<order>|<label>|…``) or a printed ``<order>-U<nn>`` code.
    Without this hint a unit scan floods every order that cut unit 1."""
    text = query.strip().upper()
    qr = _QR_RE.match(text)
    if qr:
        return qr.group(1)
    unit_label = _UNIT_LABEL_RE.match(text)
    if unit_label:
        return unit_label.group(1)
    return None


def _normalize_query(query: str) -> str:
    """Reduce a scanned QR payload or printed label code to the piece code
    grammar ``_CODE_RE`` understands — operators scan what the label carries,
    not the raw spec codes."""
    text = query.strip().upper()
    qr = _QR_RE.match(text)
    if qr:
        text = qr.group(2)
    unit = _UNIT_SUFFIX_RE.search(text)
    if unit and not _CODE_RE.match(text):
        return f"U{unit.group(1)}"
    return text


def _resolve_code(
    version_snapshot: dict[str, Any], query: str
) -> dict[str, Any]:
    """Resolve a printed code to the frozen identities it names — member,
    reinforcement, infill, bay, leaf and position ids — so a scanned
    M-03/I-02/-U01 hits the same pieces the paper label does. Returns the
    label maps plus the resolved id sets (empty dict when nothing resolves)."""
    match = _CODE_RE.match(_normalize_query(query))
    if not match:
        return {}
    try:
        labels = _piece_labels(version_snapshot)
    except DocumentaryError:
        return {}
    resolved: dict[str, Any] = {
        "spec_keys": set(),
        "infill_keys": set(),
        "bay_ids": set(),
        "leaf_ids": set(),
        "position_ids": set(),
        "unit_index": None,
        "cut_map": _cut_member_map(version_snapshot, labels),
        "infill_map": _infill_code_map(version_snapshot, labels),
    }
    prefix, member_digits, position_digits, unit_digits = match.groups()
    if unit_digits is not None:
        resolved["unit_index"] = int(unit_digits)
        return resolved
    if position_digits is not None:
        for position_id, code in labels["position"].items():
            if str(code) == f"P{position_digits}":
                resolved["position_ids"].add(str(position_id))
        return resolved
    group = {
        "M": "member",
        "R": "reinforcement",
        "I": "infill",
        "V": "bay",
        "H": "leaf",
        "MAN": "handle",
    }[prefix]
    canonical = f"{prefix}-{member_digits}"
    resolved_ids = {
        entity_id
        for entity_id, code in labels[group].items()
        if str(code) == canonical
    }
    if not resolved_ids:
        return {}
    if group in ("member", "reinforcement"):
        spec_index = _cut_spec_index(version_snapshot)
        kind_tag = "PROFILE" if group == "member" else "REINFORCEMENT"
        for key, ids in spec_index.items():
            if key[0] == kind_tag and any(entity_id in resolved_ids for entity_id in ids):
                resolved["spec_keys"].add(key)
    elif group == "infill":
        infill_index = _infill_spec_index(version_snapshot)
        for key, ids in infill_index.items():
            if any(entity_id in resolved_ids for entity_id in ids):
                resolved["infill_keys"].add(key)
    elif group == "bay":
        resolved["bay_ids"] = {str(entity_id) for entity_id in resolved_ids}
    elif group == "leaf":
        resolved["leaf_ids"] = {str(entity_id) for entity_id in resolved_ids}
    return resolved


def trace_piece(*, org_id: UUID, piece_id: str) -> dict[str, Any]:
    """Backward lookup: which work order(s) and plan location carry a
    physical piece — walk from the piece back to order → version → project."""
    if not piece_id or len(piece_id) > 256:
        raise DocumentaryError("work_order_piece_invalid")
    normalized = _normalize_query(piece_id)
    code_query = bool(_CODE_RE.match(normalized))
    # A printed code never appears inside payload_json, so the LIKE prefilter
    # only applies to raw piece_id scans — code lookups scan every order in
    # the org (bounded; an operator scan is a rare call). When the scanned
    # label carries its own order code (QR payload, printed -Unn code),
    # scope to that order instead of listing every order's unit 1.
    order_hint = _scan_order_hint(piece_id)
    params: list[Any] = [str(org_id)]
    extra = ""
    if order_hint:
        extra += " AND order_code = %s"
        params.append(order_hint)
    if not code_query:
        extra += " AND payload_json::text LIKE %s"
        params.append(f"%{piece_id}%")
    orders = rows(
        """
        SELECT id::text, order_code, status::text,
               project_id::text, project_version_id::text, payload_json::text
        FROM public.orders
        WHERE org_id = %s
        """
        + extra
        + " ORDER BY created_at",
        params,
    )
    matches: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}

    def _snapshot(version_id: str) -> dict[str, Any]:
        if version_id not in snapshots:
            with documentary_backend():
                snapshot_row = one(
                    """
                    SELECT snapshot_json::text
                    FROM public.project_versions
                    WHERE id = %s AND org_id = %s
                    """,
                    [version_id, str(org_id)],
                    "work_order_not_found",
                )
            snapshots[version_id] = _decoded(snapshot_row["snapshot_json"])
        return snapshots[version_id]

    for order in orders:
        resolved: dict[str, Any] = {}
        labels: dict[str, dict[Any, str]] = {}
        # A code lookup resolves against the sealed snapshot before the piece
        # scan; a raw piece_id scan only needs the snapshot once the order
        # actually carries a hit (saves one read per non-matching order).
        if order["project_version_id"] and code_query:
            resolved = _resolve_code(
                _snapshot(str(order["project_version_id"])), piece_id
            )
        hits = _piece_hits(
            order,
            piece_id,
            spec_keys=resolved.get("spec_keys") or None,
            infill_keys=resolved.get("infill_keys") or None,
            bay_ids=resolved.get("bay_ids") or None,
            leaf_ids=resolved.get("leaf_ids") or None,
            position_ids=resolved.get("position_ids") or None,
            unit_index=resolved.get("unit_index"),
            cut_map=resolved.get("cut_map"),
            infill_map=resolved.get("infill_map"),
        )
        if not hits:
            continue
        if order["project_version_id"]:
            try:
                labels = _piece_labels(
                    _snapshot(str(order["project_version_id"]))
                )
            except DocumentaryError:
                labels = {}
        # Stamp the human location on every hit: two pieces on the same bar
        # read identically until the position/unit/vano-hoja codes join them.
        for hit in hits:
            piece = hit.get("piece") or {}
            hit["position_code"] = labels.get("position", {}).get(
                piece.get("source_position_id")
            )
            hit["location_code"] = (
                _location(labels, piece.get("bay_id"), piece.get("leaf_id"))
                if labels
                else None
            )
        # The scan answers "what do I run on this stick": resolve the member
        # ids behind the matched pieces and attach each one's machining ops —
        # the same sealed derivation the ops export and the member diagram use.
        order_ops: dict[str, Any] | None = None
        spec_index: dict[tuple[str, ...], list[object]] | None = None
        for hit in hits:
            if hit.get("kind") != "BAR":
                hit["operations"] = []
                continue
            piece = hit.get("piece") or {}
            if order_ops is None:
                try:
                    snapshot = _snapshot(str(order["project_version_id"])) \
                        if order["project_version_id"] else {}
                    order_ops = _trace_operations(
                        payload=_decoded(order["payload_json"]),
                        optimization=_decoded(
                            _decoded(order["payload_json"]).get("optimization")
                        ) or {},
                        version_snapshot=snapshot,
                    )
                    spec_index = _cut_spec_index(snapshot)
                except DocumentaryError:
                    order_ops = {"items": []}
                    spec_index = {}
            member_ids: set[str] = set()
            key = _cut_key(piece)
            for spec_key, ids in (spec_index or {}).items():
                if spec_key == key:
                    member_ids = {str(mid) for mid in ids}
                    break
            host_ops = [
                {
                    **op,
                    "member_label": (labels.get("member", {}) or {}).get(
                        op.get("host")
                    )
                    or (labels.get("reinforcement", {}) or {}).get(
                        op.get("host")
                    ),
                }
                for op in (order_ops or {}).get("items", [])
                if op.get("host_kind") == "MEMBER" and str(op.get("host")) in member_ids
            ]
            hit["operations"] = host_ops
        steps = rows(
            """
            SELECT sequence, code, label, status
            FROM public.production_steps
            WHERE order_id = %s AND org_id = %s
            ORDER BY sequence
            """,
            [order["id"], str(org_id)],
        )
        project = None
        if order["project_id"]:
            # project_manual_read excludes floor roles — the scan must not die
            # on a lookup the operator is allowed to know (order code + name).
            with documentary_backend():
                project = one(
                    """
                    SELECT id::text, code, name FROM public.projects
                    WHERE id = %s AND org_id = %s
                    """,
                    [order["project_id"], str(org_id)],
                    "work_order_not_found",
                )
        for hit in hits:
            matches.append({
                "work_order": {
                    "id": order["id"],
                    "order_code": order["order_code"],
                    "status": order["status"],
                },
                "project": project,
                "project_version_id": order["project_version_id"],
                "location": hit,
                "steps": steps,
            })
    return {"piece_id": piece_id, "matches": matches}


def trace_version(*, org_id: UUID, version_id: UUID) -> dict[str, Any]:
    """Forward chain from a frozen version to every work order released
    from it — plus, per order, the positions and piece counts its plan cut."""
    version = one(
        """
        SELECT id::text, project_id::text, revision_code, snapshot_sha256,
               bom_hash, emitted_at, production_allowed
        FROM public.project_versions WHERE id = %s AND org_id = %s
        """,
        [str(version_id), str(org_id)],
        "version_not_found",
    )
    project = one(
        """
        SELECT id::text, code, name, client_name
        FROM public.projects WHERE id = %s AND org_id = %s
        """,
        [version["project_id"], str(org_id)],
        "version_not_found",
    )
    orders = rows(
        """
        SELECT id::text, order_code, status::text, order_type::text,
               payload_json::text, created_at
        FROM public.orders
        WHERE org_id = %s AND project_version_id = %s
        ORDER BY created_at
        """,
        [str(org_id), str(version_id)],
    )
    work_orders = []
    for order in orders:
        payload = _decoded(order["payload_json"])
        optimization = _decoded(payload.get("optimization")) or {}
        bars = _plan_bars(optimization)
        sheets = _plan_sheets(optimization)
        positions = sorted({
            str(cut["source_position_id"])
            for bar in bars for cut in bar["cuts"]
            if cut["source_position_id"]
        } | {
            str(piece["source_position_id"])
            for sheet in sheets for piece in sheet["pieces"]
            if piece["source_position_id"]
        })
        work_orders.append({
            "work_order": {
                "id": order["id"],
                "order_code": order["order_code"],
                "order_type": order["order_type"],
                "status": order["status"],
                "created_at": order["created_at"],
            },
            "position_id": payload.get("position_id"),
            "positions_cut": positions,
            "bars": len(bars),
            "sheets": len(sheets),
            "pieces": sum(len(bar["cuts"]) for bar in bars)
            + sum(len(sheet["pieces"]) for sheet in sheets),
        })
    return {
        "version": version,
        "project": project,
        "work_orders": work_orders,
    }
