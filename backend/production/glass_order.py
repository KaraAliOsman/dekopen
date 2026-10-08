"""D02 glazier order — the supplier-facing cut list for one work order or a
batch of them (``?orders=``) of the same frozen version.

The document is always rendered from sealed evidence: the version
snapshot's manufacturing facts give the physical pieces (cut rect, infill
identity) and each work order's frozen payload gives the engine BOM
(composition, surcharge selections, safety findings). Nothing is
re-computed at print time — a later catalog edit can never drift an order
already released to the floor.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from html import escape
from uuid import UUID

from documents.renderers import (
    _CSS,
    _Raw,
    _cldate,
    _fmt_mm as _eng_fmt_mm,
    _piece_labels,
    _table,
    _url_fetcher,
)
from documents.repository import (
    DocumentaryError,
    decoded,
    documentary_backend,
    one,
    rows,
)

_ORDER_SQL = (
    "SELECT id,project_id,project_version_id,order_code,"
    "payload_json->>'position_id' AS position_id,"
    "payload_json::text AS payload_json FROM public.orders "
    "WHERE id=%s AND org_id=%s AND order_type='WORKSHOP_OT'"
)

_EDGE_ES = {
    "top": "superior",
    "right": "derecho",
    "bottom": "inferior",
    "left": "izquierdo",
}

_SAFETY_ES = {
    "TEMPERED": "templado",
    "LAMINATED": "laminado",
    "SAFETY_GLASS": "vidrio de seguridad",
    "SAFETY_CLASS_A": "seguridad clase A",
    "SAFETY_CLASS_B": "seguridad clase B",
    "SAFETY_CLASS_C": "seguridad clase C",
}


def _mm(value: object) -> Decimal:
    return Decimal(str(value))


def _fmt_mm(value: object) -> str:
    """Printed mm per §3.3 — thin-space grouping, comma decimal."""
    number = _mm(value).quantize(Decimal("0.01"))
    if number == number.to_integral_value():
        return _eng_fmt_mm(number.quantize(Decimal("1")))
    return _eng_fmt_mm(number.normalize())


def _csv_mm(value: object) -> str:
    """Machine-facing mm — the CSV feeds cutting software, so it keeps
    the canonical decimal form, not the §3.3 print glyph."""
    number = _mm(value).quantize(Decimal("0.01"))
    return format(number.normalize(), "f")


def _order_row(org_id: UUID, order_id: UUID) -> dict[str, object]:
    return one(
        _ORDER_SQL,
        [str(order_id), str(org_id)],
        "work_order_not_found",
    )


def _surcharge_text(selection: dict[str, object]) -> str:
    kind = str(selection.get("kind") or "")
    if kind == "EDGE_POLISH":
        edges = selection.get("edges") or []
        labels = ", ".join(_EDGE_ES.get(str(edge), str(edge)) for edge in edges)
        return f"Canto pulido ({labels})" if labels else "Canto pulido"
    if kind == "DRILL":
        count = int(selection.get("count") or 1)
        return f"Perforaciones ×{count}"
    if kind == "PALILLAJE":
        cols = selection.get("columns")
        rows_ = selection.get("rows")
        grid = f"{cols}×{rows_}" if cols is not None and rows_ is not None else "—"
        return f"Palillaje {grid}"
    if kind == "TEMPERED":
        return "Templado"
    return kind or "Recargo"


def _polishing_text(edges: object) -> str | None:
    if not isinstance(edges, list) or not edges:
        return None
    labels = ", ".join(_EDGE_ES.get(str(edge), str(edge)) for edge in edges)
    return f"Canto pulido ({labels})"


def _collect_orders(org_id: UUID, order_ids: list[UUID]) -> list[dict[str, object]]:
    orders = [_order_row(org_id, order_id) for order_id in order_ids]
    version_ids = {str(order["project_version_id"]) for order in orders}
    if len(version_ids) != 1:
        raise DocumentaryError(
            "glazier_order_mixed_versions",
            detail="Un pedido al vidriero solo agrupa órdenes de la misma versión congelada.",
        )
    return orders


def _glass_facts(
    org_id: UUID, orders: list[dict[str, object]]
) -> dict[str, object]:
    """Sealed pieces + enrichment, ready to render.

    Returns ``{"version": row, "snapshot": dict, "pieces": [...],
    "position_label": {pid: label}, "order_code": [codes]}`` where each
    piece is one physical unit of glass (facts expanded per repetition).
    """
    version_id = str(orders[0]["project_version_id"])
    version = one(
        "SELECT id,revision_code,emitted_at,snapshot_json::text "
        "FROM public.project_versions "
        "WHERE id=%s AND org_id=%s",
        [version_id, str(org_id)],
        "work_order_missing_version",
    )
    snapshot = decoded(version["snapshot_json"])
    if not isinstance(snapshot, dict):
        raise DocumentaryError("invalid_frozen_revision_snapshot")

    labels = _piece_labels(snapshot)
    infill_labels = labels.get("infill") or {}
    positions = {
        str(pos.get("id")): pos
        for pos in snapshot.get("positions") or []
        if isinstance(pos, dict) and pos.get("id")
    }

    # BOM enrichment: the work order payload carries the sealed engine BOM
    # for its position — composition dicts, surcharge selections, safety
    # findings — keyed by (position, bay, leaf) for the fact join.
    bom_by_key: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for order in orders:
        payload = decoded(order["payload_json"])
        materials = payload.get("materials") if isinstance(payload, dict) else None
        glasses = (materials or {}).get("glasses") or []
        position_id = str(payload.get("position_id") or "")
        for glass in glasses:
            if not isinstance(glass, dict):
                continue
            key = (
                position_id,
                str(glass.get("bay_id") or ""),
                str(glass.get("leaf_id") or ""),
            )
            bom_by_key.setdefault(key, []).append(glass)

    facts_units = [
        unit
        for unit in (snapshot.get("manufacturing") or [])
        if isinstance(unit, dict)
        and str(unit.get("position_id"))
        in {str(order["position_id"]) for order in orders}
    ]
    order_codes = {
        str(order["position_id"]): str(order["order_code"])
        for order in orders
    }

    # Enrichment catalogs: purchasing identity + structured product data,
    # scoped to the systems this batch actually uses.
    system_ids = sorted({
        str(pos.get("system_id"))
        for pos in positions.values()
        if pos.get("system_id")
    })
    purchase_rows = rows(
        "SELECT system_id::text, technical_sku, purchasing_sku, manufacturer_name,"
        " glass_spec FROM public.glass_purchase_mappings "
        "WHERE (org_id=%s OR org_id IS NULL)",
        [str(org_id)],
    ) if system_ids else []
    purchase_map = {
        (str(row["system_id"]), str(row["technical_sku"])): row
        for row in purchase_rows
    }
    product_rows = rows(
        "SELECT sku, commercial_name, notation, composition::text AS composition,"
        " safety_class, review_pending FROM public.glass_products "
        "WHERE is_active = TRUE AND (org_id=%s OR org_id IS NULL)",
        [str(org_id)],
    )
    product_map = {str(row["sku"]): row for row in product_rows}

    pieces: list[dict[str, object]] = []
    for unit in sorted(
        facts_units,
        key=lambda u: (
            int(u.get("position_index") or 0), int(u.get("repetition_index") or 0)
        ),
    ):
        position_id = str(unit.get("position_id") or "")
        position = positions.get(position_id) or {}
        index = unit.get("position_index")
        position_label = str(
            position.get("location_tag")
            or (f"P-{int(str(index)):02d}" if index is not None else "P-??")
        )
        system_id = str(position.get("system_id") or "")
        polishing_edges = {
            (str(item.get("bay_id") or ""), str(item.get("leaf_id") or "")): item.get("edges")
            for item in (position.get("glass_polishing") or [])
            if isinstance(item, dict)
        }
        for infill in unit.get("infills") or []:
            if not isinstance(infill, dict) or infill.get("kind") != "GLASS":
                continue
            bay_id = str(infill.get("bay_id") or "")
            leaf_id = str(infill.get("leaf_id") or "")
            rect = infill.get("rect") or {}
            technical_sku = str(infill.get("technical_sku") or "")
            bom_items = bom_by_key.get((position_id, bay_id, leaf_id)) or []
            bom = _match_bom_glass(
                bom_items, _mm(rect.get("width_mm") or 0), _mm(rect.get("height_mm") or 0)
            )
            surcharge_texts: list[str] = []
            if bom is not None:
                surcharge_texts += [
                    _surcharge_text(sel)
                    for sel in (bom.get("surcharge_selections") or [])
                    if isinstance(sel, dict)
                ]
                safety_findings = [
                    f for f in (bom.get("safety_findings") or [])
                    if isinstance(f, dict)
                ]
                composition = bom.get("composition")
            else:
                safety_findings = []
                composition = None
            legacy_polish = _polishing_text(
                polishing_edges.get((bay_id, leaf_id))
            )
            if legacy_polish and not any(
                "Canto pulido" in text for text in surcharge_texts
            ):
                surcharge_texts.append(legacy_polish)
            mapping = purchase_map.get((system_id, technical_sku))
            product = product_map.get(technical_sku)
            notation = _notation_for(
                product=product, composition=composition,
                fallback=str(infill.get("composition") or "Sin dato"),
            )
            infill_id = str(infill.get("infill_id") or "")
            pieces.append({
                "order_code": order_codes.get(position_id, "—"),
                "position_label": position_label,
                "piece_code": infill_labels.get(
                    infill_id, infill_id[:10] if infill_id else "—"
                ),
                "repetition": int(unit.get("repetition_index") or 0),
                "purchasing_sku": str(
                    (mapping or {}).get("purchasing_sku") or technical_sku
                ),
                "technical_sku": technical_sku,
                "manufacturer": str((mapping or {}).get("manufacturer_name") or "—"),
                "product_name": str((product or {}).get("commercial_name") or "—"),
                "notation": notation,
                "safety_class": str((product or {}).get("safety_class") or ""),
                "width_mm": _mm(rect.get("width_mm") or 0),
                "height_mm": _mm(rect.get("height_mm") or 0),
                "surcharges": list(dict.fromkeys(surcharge_texts)),
                "safety": sorted({
                    _SAFETY_ES.get(
                        str(f.get("required_safety") or ""),
                        str(f.get("required_safety") or ""),
                    )
                    for f in safety_findings
                    if str(f.get("severity") or "") == "MANDATORY"
                }) or sorted({
                    _SAFETY_ES.get(
                        str(f.get("required_safety") or ""),
                        str(f.get("required_safety") or ""),
                    )
                    for f in safety_findings
                }),
                "review_pending": bool((product or {}).get("review_pending")),
            })
    if not pieces:
        raise DocumentaryError(
            "glazier_order_no_glass",
            detail="La orden no contiene vidrios; el pedido al vidriero queda vacío.",
        )
    return {
        "version": version,
        "snapshot": snapshot,
        "pieces": pieces,
        "order_codes": [str(order["order_code"]) for order in orders],
    }


def _match_bom_glass(
    items: list[dict[str, object]], width_mm: Decimal, height_mm: Decimal
) -> dict[str, object] | None:
    """The fact piece and its BOM row share bay/leaf and cut dims — pick the
    first exact match; rotation is meaningful to a glazier, never merged."""
    for item in items:
        if (
            _mm(item.get("width_mm") or 0) == width_mm
            and _mm(item.get("height_mm") or 0) == height_mm
        ):
            return item
    return items[0] if items else None


def _notation_for(
    *, product: dict[str, object] | None,
    composition: object,
    fallback: str,
) -> str:
    if product is not None and product.get("notation"):
        return str(product["notation"])
    if isinstance(composition, dict):
        # Frozen BOM composition dicts carry the canonical notation under
        # "notation" when the engine serialized one.
        notation = composition.get("notation")
        if isinstance(notation, str) and notation:
            return notation
    return fallback


def _grouped_lines(pieces: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]], dict] = {}
    for piece in pieces:
        key = (
            piece["purchasing_sku"],
            piece["notation"],
            format(piece["width_mm"].quantize(Decimal("0.01")), "f"),
            format(piece["height_mm"].quantize(Decimal("0.01")), "f"),
            tuple(piece["surcharges"]),
            tuple(piece["safety"]),
        )
        group = groups.setdefault(
            key,
            {
                "purchasing_sku": piece["purchasing_sku"],
                "notation": piece["notation"],
                "width_mm": piece["width_mm"],
                "height_mm": piece["height_mm"],
                "surcharges": piece["surcharges"],
                "safety": piece["safety"],
                "qty": 0,
                "positions": [],
                "manufacturer": piece["manufacturer"],
            },
        )
        group["qty"] += 1
        label = piece["position_label"]
        if label not in group["positions"]:
            group["positions"].append(label)
    return sorted(
        groups.values(),
        key=lambda g: (g["purchasing_sku"], -g["width_mm"], -g["height_mm"]),
    )


_CSS_ORDER = """
@page { size: letter; margin: 12mm 12mm 16mm;
        @bottom-center { content: element(titleblock); } }
@page labels { size: 62mm 42mm; margin: 2mm; }
.labels-page { page: labels; }
.glass-label { border: 0.4pt solid #465158; border-radius: 1.5mm;
               display: inline-flex; gap: 2mm; padding: 1.6mm;
               width: 58mm; height: 38mm; overflow: hidden;
               vertical-align: top; }
.glass-label .qr { width: 17mm; height: 17mm; flex: none; }
.glass-label .qr svg { width: 17mm; height: 17mm; }
.glass-label .l-body { font-size: 6.4pt; line-height: 1.35;
                       font-family: 'IBM Plex Mono', monospace; }
.glass-label .l-code { font-size: 8pt; font-weight: 700; }
.warn { color: #B25E09; font-weight: 600; }
"""


def _order_html(context: dict[str, object]) -> str:
    import segno

    pieces = context["pieces"]
    lines = _grouped_lines(pieces)
    order_codes = ", ".join(context["order_codes"])
    version = context["version"]
    revision = str(version.get("revision_code") or "—")

    table_rows: list[list[object]] = []
    for line in lines:
        extras = "; ".join(line["surcharges"]) or "—"
        safety = "; ".join(line["safety"])
        safety_cell: object = (
            _Raw(f'<span class="warn">{escape(safety)}</span>') if safety else "—"
        )
        table_rows.append([
            line["purchasing_sku"],
            line["notation"],
            _fmt_mm(line["width_mm"]),
            _fmt_mm(line["height_mm"]),
            line["qty"],
            ", ".join(line["positions"]),
            extras,
            safety_cell,
        ])
    supplier_names = sorted({
        piece["manufacturer"] for piece in pieces if piece["manufacturer"] != "—"
    })
    supplier = ", ".join(supplier_names) or "Vidriería"
    labels_html = []
    for index, piece in enumerate(pieces):
        qr_payload = (
            f"DEKOPEN|{piece['order_code']}|{piece['piece_code']}|1"
        )
        qr_svg = segno.make(qr_payload, error="m").svg_inline(
            border=1, scale=3
        )
        labels_html.append(
            f'<div class="glass-label"><div class="qr">{qr_svg}</div>'
            f'<div class="l-body"><div class="l-code">'
            f"{escape(str(piece['piece_code']))}</div>"
            f"<div>{escape(str(piece['purchasing_sku']))}</div>"
            f"<div>{escape(piece['notation'])}</div>"
            f"<div>{_fmt_mm(piece['width_mm'])} × "
            f"{_fmt_mm(piece['height_mm'])} mm</div>"
            f"<div>OT {escape(str(piece['order_code']))} · "
            f"{escape(str(piece['position_label']))}</div>"
            "</div></div>"
        )
    emitted_raw = version.get("emitted_at")
    emitted = emitted_raw.isoformat() if hasattr(emitted_raw, "isoformat") else emitted_raw
    title_block = (
        '<div class="titleblock">'
        f'<div class="tb-cell tb-wide">Pedido al vidriero · '
        f"{escape(order_codes)}</div>"
        f'<div class="tb-cell">Rev. {escape(revision)} · '
        f"{_cldate(emitted)}</div>"
        "</div>"
    )
    pending = [p for p in pieces if p["review_pending"]]
    pending_note = (
        '<p class="warn">Hay productos con datos de proveedor pendientes de '
        'revisión técnica (provenance sintético/legado). Confirmar con el '
        'vidriero antes de confirmar el pedido.</p>'
        if pending
        else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>{_CSS}{_CSS_ORDER}</style></head><body>
{title_block}
<h1>Pedido al vidriero</h1>
<div class="meta">
 <div><strong>Proveedor</strong> {escape(supplier)}</div>
 <div><strong>Órdenes</strong> {escape(order_codes)}</div>
 <div><strong>Versión</strong> {escape(revision)}</div>
 <div><strong>Piezas</strong> {len(pieces)} en {len(lines)} líneas</div>
</div>
{pending_note}
<h2>Lista de corte</h2>
{_table(
    ["SKU", "Composición", "Ancho mm", "Alto mm", "Cant.", "Posición", "Recargos", "Seguridad"],
    table_rows,
    classes=["", "", "num", "num", "num", "", "", ""],
)}
<h2 class="labels-page">Etiquetas por pieza</h2>
<div class="labels-page">{''.join(labels_html)}</div>
</body></html>"""


def _order_csv(context: dict[str, object]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([
        "orden", "posicion", "codigo_pieza", "sku_compra", "sku_tecnico",
        "composicion", "ancho_mm", "alto_mm", "cantidad", "recargos",
        "seguridad", "proveedor",
    ])
    for piece in context["pieces"]:
        writer.writerow([
            piece["order_code"], piece["position_label"], piece["piece_code"],
            piece["purchasing_sku"], piece["technical_sku"], piece["notation"],
            _csv_mm(piece["width_mm"]), _csv_mm(piece["height_mm"]), 1,
            "; ".join(piece["surcharges"]), "; ".join(piece["safety"]),
            piece["manufacturer"],
        ])
    return output.getvalue().encode("utf-8-sig")


def _parse_order_ids(raw: object) -> list[UUID]:
    if not isinstance(raw, list):
        return []
    result: list[UUID] = []
    for value in raw:
        try:
            result.append(UUID(str(value)))
        except (ValueError, AttributeError):
            continue
    return result


def glazier_order(
    *, org_id: UUID, order_id: UUID, extra_order_ids: list[UUID] | None,
    output_format: str,
) -> tuple[bytes, str, str]:
    """Render the glazier order. ``output_format`` is ``pdf`` or ``csv``;
    returns ``(content, content_type, download_name)``."""
    order_ids = [order_id, *(extra_order_ids or [])]
    with documentary_backend():
        orders = _collect_orders(org_id, order_ids)
        context = _glass_facts(org_id, orders)
    revision = str(context["version"].get("revision_code") or "rev")
    stem = f"pedido-vidriero-{revision}"
    if output_format == "csv":
        return _order_csv(context), "text/csv", f"{stem}.csv"
    html = _order_html(context)
    from weasyprint import HTML

    pdf = HTML(string=html, url_fetcher=_url_fetcher).write_pdf()
    return pdf, "application/pdf", f"{stem}.pdf"
