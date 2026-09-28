"""§10-A complete production pack — one printable bundle per work order:
cut plan (bars + sheets), machining schedule, assembly maps, glazing
worksheet, QC sheet and unit labels. Everything derives from the live
optimization + the sealed snapshot — the pack re-renders on demand and a
re-optimization (``invalidated``) refuses print, so the bundle can never
drift from the plan the floor executes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from uuid import UUID

from dekopen_engine.cutting import CutBar
from dekopen_engine.manufacturing import ManufacturingFactsV1
from dekopen_engine.operations import OperationKind, operations_from_plan
from documents.renderers import (
    _CATEGORY_ES,
    _CSS,
    _ROLE_ES,
    _cldate,
    _cut_member_map,
    _cut_piece_ids,
    _infill_code_map,
    _infill_key,
    _location,
    _pct,
    _piece_labels,
    _role_name,
    _SLOT_ES,
    _table,
    _url_fetcher,
    _value,
)
from django.db import transaction

from documents.repository import DocumentaryError, decoded, documentary_backend, one

from production.cut_pack import (
    _claim_piece,
    _CSS_PACK,
    _fmt_mm,
    _piece_pools,
    _UNNEST_REASONS,
    _bar_svg,
    _mm,
    _sheet_svg,
)
from production.service import (
    _decoded,
    _optimization_fingerprint,
    _raw_fact_units,
)

_CSS_BUNDLE = """
.pack-section { break-before: page; }
.pack-section.first { break-before: auto; }
.pack-grid { display: flex; flex-wrap: wrap; gap: 5mm; }
.member-card { break-inside: avoid; width: 122mm; border: 0.4pt solid #161C1F;
               border-radius: 1.5mm; padding: 2.5mm 3mm; }
.member-card h4 { font-size: 8.5pt; margin: 0 0 1.5mm; }
.member-svg { width: 100%; height: auto; display: block; }
.unit-map { max-height: 120mm; display: block; margin: 0 auto; }
.unit-map-svg { width: auto; max-width: 100%; height: 118mm; display: block; }
.qc-check { display: inline-block; width: 3.4mm; height: 3.4mm;
            border: 0.5pt solid #161C1F; border-radius: 0.5mm; }
.op-table table { table-layout: fixed; width: 100% }
.op-table td, .op-table th { font-size: 7pt; overflow-wrap: break-word }
.op-table td:first-child { font-weight: 600; font-size: 7pt }
.op-table td:last-child { font-family: monospace; font-size: 7pt;
                         word-break: break-all }
.op-table td.mark { text-align: center; font-weight: 700 }
.label-grid { display: flex; flex-wrap: wrap; gap: 4mm; }
.unit-label { width: 100mm; height: 50mm; box-sizing: border-box;
              border: 0.6pt solid #161C1F; border-radius: 2mm;
              padding: 2.5mm 3mm; break-inside: avoid;
              display: flex; align-items: flex-start; gap: 3mm; }
.unit-label .qr { width: 26mm; height: 26mm; flex: none; }
.unit-label .qr svg { display: block; }
.unit-label .label-body { flex: 1; min-width: 0; }
.unit-label h4 { margin: 0 0 1mm; font-size: 13pt; letter-spacing: 0.02em;
                 word-break: break-all; }
.unit-label p { margin: 0; font-size: 7.5pt; line-height: 1.35; }
.cover-stats { display: flex; flex-wrap: wrap; gap: 4mm; margin: 3mm 0; }
.cover-stat { border-left: 0.8mm solid #0B7770; padding-left: 2.5mm; }
.cover-stat strong { display: block; font-size: 13pt; color: #161C1F; }
.cover-stat span { font-size: 7pt; text-transform: uppercase;
                   letter-spacing: 0.5pt; color: #465158; }
.warn-note { background: #FDF1E3; border-left: 1mm solid #B25E09;
             padding: 1.5mm 3mm; font-size: 8pt; }
"""


def _op_anchor(member: dict[str, object], op: dict[str, object]) -> Decimal | None:
    """Project an op's MEMBER_PLAN point onto the member's run axis —
    distance from the member start, so markers sit at the right spot on
    the strip regardless of member orientation."""
    start = member.get("start") or {}
    end = member.get("end") or {}
    try:
        sx, sy = _mm(start.get("x_mm")), _mm(start.get("y_mm"))
        ex, ey = _mm(end.get("x_mm")), _mm(end.get("y_mm"))
        dx, dy = ex - sx, ey - sy
        run = (dx * dx + dy * dy).sqrt()
        if run <= 0:
            return None
        ox = _mm(op.get("x_mm") or 0)
        oy = _mm(op.get("y_mm") or 0)
        along = ((ox - sx) * dx + (oy - sy) * dy) / run
        return max(Decimal("0"), min(along, run))
    except Exception:
        return None


def _member_svg(member: dict[str, object], ops: list[dict[str, object]]) -> str:
    """Member strip for the machining pack: the member's real cut length,
    op markers projected onto the run, sagitta note when arched."""
    length = _mm(member.get("cut_length_mm"))
    span = max(length, Decimal("1"))
    # Diagram strip, not a to-scale section: exaggerate thickness so the bar
    # reads ~8mm on paper regardless of the member's real proportions.
    height = span * Decimal("0.13")
    half = height / 2
    svg = [
        f'<svg class="member-svg" viewBox="0 0 {span} {height * Decimal("1.6")}" '
        'preserveAspectRatio="xMinYMid meet" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="{height}" width="{span}" height="{half}" '
        'fill="#E6F4F2" stroke="#075F5A" stroke-width="2"/>',
    ]
    if _mm(member.get("angle_left")) != Decimal("90"):
        svg.append(
            f'<line x1="0" y1="{height}" x2="{min(half, span * Decimal("0.08"))}" '
            f'y2="{height + half}" stroke="#E56A32" stroke-width="2"/>'
        )
    if _mm(member.get("angle_right")) != Decimal("90"):
        svg.append(
            f'<line x1="{span}" y1="{height}" '
            f'x2="{max(span - half, span * Decimal("0.92"))}" '
            f'y2="{height + half}" stroke="#E56A32" stroke-width="2"/>'
        )
    # Markers are numbered chips that cross-reference the op table (a "Marca"
    # column carries the same index) — WeasyPrint's SVG text support is too
    # limited for inline kind labels at strip scale.
    chip_r = height * Decimal("0.24")
    chip_font = chip_r * Decimal("1.15")
    digit_w = chip_font * Decimal("0.62")
    strip_mid = height + half / 2
    for index, op in enumerate(ops):
        anchor = _op_anchor(member, op)
        if anchor is None:
            continue
        x = anchor if length > 0 else Decimal("0")
        x = max(chip_r * Decimal("1.2"), min(x, span - chip_r * Decimal("1.2")))
        kind = str(op.get("kind") or "")
        color = "#E56A32" if kind == "HANDLE_PREP" else "#161C1F"
        num = str(index + 1)
        svg.append(
            f'<circle cx="{x}" cy="{strip_mid}" r="{chip_r}" '
            f'fill="{color}"/>'
            f'<text x="{x - digit_w * Decimal(len(num)) * Decimal("0.5")}" '
            f'y="{strip_mid + chip_font * Decimal("0.36")}" '
            f'fill="#FCFDFC" font-size="{chip_font}" font-weight="600">'
            f"{num}</text>"
        )
    svg.append("</svg>")
    return "".join(svg)


def _table_raw(headers, rows, classes=None):
    """Table body without the <table> opener — caller supplies it (colgroup)."""
    head = "<tr>" + "".join(f"<th>{escape(h)}</th>" for h in headers) + "</tr>"
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="{classes[i] if classes and i < len(classes) else ""}">'
            f"{escape(_value(cell))}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    return f"<thead>{head}</thead><tbody>{body}</tbody></table>"


_VIEW_LABELS = {
    "BUILDING_INTERIOR_LOOKING_OUTWARD": "Vista desde interior",
    "BUILDING_EXTERIOR_LOOKING_INWARD": "Vista desde exterior",
}

_VERTICAL_REFERENCE_LABELS = {
    "OUTER_TOP": "marco superior",
    "OUTER_BOTTOM": "marco inferior",
    "LEAF_TOP": "borde superior de la hoja",
    "LEAF_BOTTOM": "borde inferior de la hoja",
}

_OPENING_LABELS = {
    "FIXED": "Fijo",
    "TURN_LEFT": "Abatir izq.",
    "TURN_RIGHT": "Abatir der.",
    "TILT_TURN_LEFT": "Oscilobatiente izq.",
    "TILT_TURN_RIGHT": "Oscilobatiente der.",
    "SLIDING_2L": "Corredera 2 hojas",
    "SLIDING_3L": "Corredera 3 hojas",
    "SLIDING_4L": "Corredera 4 hojas",
    "SLIDING": "Corredera",
    "AWNING": "Proyectante",
    "DOOR_ENTRY": "Puerta",
    "DOOR_DOUBLE": "Puerta doble",
}

_ROLE_LABELS = {
    "FRAME": "Marco",
    "SASH": "Hoja",
    "MULLION_V": "Montante vert.",
    "MULLION_H": "Travesaño",
    "GLAZING_BEAD": "Vidriera",
    "COUPLER": "Acople",
    "THRESHOLD": "Umbral",
}

_INFILL_LABELS = {
    "GLASS": "Vidrio",
    "PANEL": "Panel",
    "GLASS_PANEL": "Vidrio + panel",
}

_OP_LABELS = {
    "SAW_CUT": "Corte sierra",
    "END_MILL": "Reto de extremo",
    "END_MACHINING": "Caja de extremo",
    "HANDLE_PREP": "Prep. herraje",
    "LOCK_PREP": "Prep. cerradura",
    "HINGE_PREP": "Prep. bisagra",
    "DRAINAGE": "Drenaje",
}

_TOOL_LABELS = {
    "saw": "Disco de corte",
    "end_mill": "Fresa de copia",
    "drill": "Broca",
    "mark": "Marcado",
}

_BASIS_LABELS = {
    "cut_plan.head_trim": "Plan de corte",
    "cut_plan.placement": "Plan de corte",
    "cut_plan.tail_trim": "Plan de corte",
    "member_end_overlap": "Solape de extremo",
}

_EDGE_LABELS = {"START": "Ext. A", "END": "Ext. B"}


def _op_reference(detail: dict[str, object]) -> str:
    """Human reference for where the op sits: cut edge (Ext. A/B) or the
    declared vertical reference — never raw enums."""
    edge = str(detail.get("edge") or "")
    if edge in _EDGE_LABELS:
        return _EDGE_LABELS[edge]
    vref = str(detail.get("vertical_reference") or "")
    if vref in _VERTICAL_REFERENCE_LABELS:
        return _VERTICAL_REFERENCE_LABELS[vref]
    return "—"


def _basis_label(basis: str) -> str:
    if basis in _BASIS_LABELS:
        return _BASIS_LABELS[basis]
    if basis.startswith("handle_requirement_policy:"):
        return f"Política herraje {basis.split(':', 1)[1]}"
    return basis


def _unit_map_svg(
    unit: ManufacturingFactsV1,
    labels: dict[str, dict[object, str]],
) -> str:
    """Per-unit plan map in member-plan space: infill rects, leaf outlines,
    member runs with their M-xx codes, handle markers — the assembly
    section's relationship view."""
    width = _mm(unit.nominal_width_mm)
    height = _mm(unit.nominal_height_mm)
    font = max(min(width, height) / Decimal("24"), Decimal("28"))
    pad = max(Decimal("80"), font * Decimal("1.4"))
    vb_w = width + pad * 2
    vb_h = height + pad * 2
    # WeasyPrint scales svgs from physical width/height attributes, not CSS.
    aspect = vb_w / vb_h
    box_h = min(Decimal("118"), Decimal("200") / aspect)
    box_w = box_h * aspect

    def _cx(cx: Decimal, text: str, size: Decimal) -> Decimal:
        """Left-aligned x that visually centers ``text`` on ``cx`` —
        text-anchor=middle is ignored by the renderer."""
        return cx - size * Decimal("0.6") * Decimal(len(text)) / 2

    small = font * Decimal("0.7")
    svg = [
        f'<svg width="{box_w}mm" height="{box_h}mm" '
        f'viewBox="{-pad} {-pad} {vb_w} {vb_h}" '
        'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="none" '
        'stroke="#161C1F" stroke-width="3"/>',
    ]
    for infill in unit.infills:
        rect = infill.rect
        code = labels["infill"].get(infill.infill_id, infill.semantic_infill_id)
        x, y = _mm(rect.x_mm), _mm(rect.y_mm)
        w, h = _mm(rect.width_mm), _mm(rect.height_mm)
        shape = infill.shape or []
        if shape:
            points = " ".join(f"{_mm(p.x_mm)},{_mm(p.y_mm)}" for p in shape)
            svg.append(
                f'<polygon points="{points}" fill="#8FB8CC" '
                'fill-opacity="0.25" stroke="#4A7E93" stroke-width="2" '
                'stroke-dasharray="10 6"/>'
            )
        else:
            svg.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                'fill="#8FB8CC" fill-opacity="0.25" stroke="#4A7E93" '
                'stroke-width="2" stroke-dasharray="10 6"/>'
            )
        svg.append(
            f'<text x="{_cx(x + w / 2, str(code), font)}" '
            f'y="{y + h / 2 + font * Decimal("0.35")}" '
            f'fill="#2C5667" font-size="{font}" font-weight="600">'
            f"{escape(code)}</text>"
        )
    for leaf in unit.leaves:
        rect = leaf.rect
        x, y = _mm(rect.x_mm), _mm(rect.y_mm)
        w, h = _mm(rect.width_mm), _mm(rect.height_mm)
        opening = _OPENING_LABELS.get(
            str(leaf.opening_type.value), str(leaf.opening_type.value)
        )
        svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" '
            'stroke="#0B7770" stroke-width="2.5" stroke-dasharray="4 4"/>'
            f'<text x="{_cx(x + w / 2, opening, small)}" '
            f'y="{y + h - small * Decimal("0.4")}" '
            f'fill="#0B4D49" font-size="{small}">'
            f"{escape(opening)}</text>"
        )
    for index, member in enumerate(unit.members):
        code = labels["member"].get(member.member_id, member.semantic_member_id)
        x1, y1 = _mm(member.start.x_mm), _mm(member.start.y_mm)
        x2, y2 = _mm(member.end.x_mm), _mm(member.end.y_mm)
        # Labels stagger along the run and alternate the perpendicular side
        # so clustered members (sash over frame) don't print their codes on
        # top of each other; mid-run collides with centered infill codes.
        dx, dy = x2 - x1, y2 - y1
        run = max((dx * dx + dy * dy).sqrt(), Decimal("1"))
        px, py = -dy / run, dx / run
        along = Decimal("0.10") + Decimal(index % 3) * Decimal("0.38")
        side = Decimal("0.9") if index % 2 == 0 else Decimal("-0.7")
        lx = (x1 + dx * along) + px * font * side
        ly = (y1 + dy * along) + py * font * side
        svg.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#161C1F" stroke-width="7" stroke-linecap="round"/>'
            f'<text x="{_cx(lx, str(code), font)}" '
            f'y="{ly + font * Decimal("0.3")}" '
            f'fill="#161C1F" font-size="{font}" font-weight="700">'
            f'{escape(code)}</text>'
        )
    for handle in unit.handles:
        code = labels["handle"].get(handle.handle_id, "MAN")
        x, y = _mm(handle.point.x_mm), _mm(handle.point.y_mm)
        r = font * Decimal("0.55")
        label = f"{code} · {_value(handle.requested_height_mm)} mm"
        # Right-hand default flips to left-of-mark when it would clip the
        # viewBox edge (handle near the right jamb).
        est = Decimal(len(label)) * small * Decimal("0.55")
        gap = r + font * Decimal("0.3")
        lx = x + gap
        if lx + est > width:
            lx = x - gap - est
        svg.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="#E56A32"/>'
            f'<text x="{lx}" '
            f'y="{y + small * Decimal("0.35")}" fill="#8A3A12" '
            f'font-size="{small}" font-weight="700">{escape(label)}</text>'
        )
    # overall dims on the margins
    w_text = _value(width)
    h_text = _value(height)
    svg.append(
        f'<text x="{_cx(width / 2, w_text, font)}" '
        f'y="{-pad * Decimal("0.35")}" '
        f'fill="#161C1F" font-size="{font}">{w_text}</text>'
        f'<text x="{width + pad * Decimal("0.35")}" '
        f'y="{_cx(height / 2, h_text, font)}" '
        f'fill="#161C1F" font-size="{font}" '
        f'transform="rotate(90 {width + pad * Decimal("0.35")} '
        f'{_cx(height / 2, h_text, font)})">{h_text}</text>'
    )
    svg.append("</svg>")
    return "".join(svg)


def _qc_rows(
    fact_units: list[ManufacturingFactsV1],
    labels: dict[str, dict[object, str]],
) -> list[list[object]]:
    """Designed measurement fields: expected values come from the sealed
    facts; actual/pass are blank for the operator and the verifier."""
    rows: list[list[object]] = []
    for unit in fact_units:
        for member in unit.members:
            code = labels["member"].get(member.member_id, member.semantic_member_id)
            angles = f"{_value(member.angle_left)}° / {_value(member.angle_right)}°"
            sag = (
                f" · sag. {_value(member.sagitta_mm)} mm"
                if member.sagitta_mm is not None
                else ""
            )
            rows.append(
                [
                    code,
                    f"largo {_value(member.cut_length_mm)} mm · {angles}{sag}",
                ]
            )
        for reinf in unit.reinforcements:
            code = labels["reinforcement"].get(reinf.reinforcement_id, "R")
            host = labels["member"].get(reinf.parent_member_id, "M")
            rows.append(
                [
                    code,
                    f"refuerzo de {host} · {_value(reinf.cut_length_mm)} mm",
                ]
            )
        for infill in unit.infills:
            code = labels["infill"].get(infill.infill_id, "I")
            rect = infill.rect
            shape = " · forma" if infill.shape else ""
            rows.append(
                [
                    code,
                    f"{_value(rect.width_mm)}×{_value(rect.height_mm)} mm · "
                    f"{infill.composition}{shape}",
                ]
            )
        for handle in unit.handles:
            code = labels["handle"].get(handle.handle_id, "MAN")
            rows.append(
                [
                    code,
                    "altura "
                    f"{_value(handle.requested_height_mm)} mm desde "
                    f"{_VERTICAL_REFERENCE_LABELS.get(str(handle.vertical_reference.value), handle.vertical_reference.value)}",
                ]
            )
    return rows


def _pack_html(
    *,
    order: dict[str, object],
    payload: dict[str, object],
    optimization: dict[str, object],
    snapshot: dict[str, object],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
    infills: dict[tuple[str, str, str], str],
    fact_units: list[ManufacturingFactsV1],
    fingerprint: str,
) -> str:
    import segno

    order_code = _value(order["order_code"])
    short_fp = fingerprint[:16]
    generated = _cldate(datetime.now(timezone.utc).isoformat())
    bars = [
        b
        for b in (optimization.get("bars") or {}).get("workshop_cut_plan") or []
        if isinstance(b, dict)
    ]
    sheets = [s for s in optimization.get("sheets") or [] if isinstance(s, dict)]
    unnested = [u for u in optimization.get("unnested") or [] if isinstance(u, dict)]
    metrics = (optimization.get("bars") or {}).get("metrics") or {}
    glasses = [
        g
        for g in ((payload.get("materials") or {}).get("glasses") or [])  # type: ignore[union-attr]
        if isinstance(g, dict)
    ]
    polishing = payload.get("glass_polishing") or []
    quantity = max(int(payload.get("quantity") or 1), 1)
    member_count = sum(len(unit.members) for unit in fact_units)
    ops = operations_from_plan(
        bars=[CutBar.model_validate_json(json.dumps(b)) for b in bars],
        fact_units=fact_units,
    )

    def titleblock(name: str) -> str:
        return (
            '<div class="titleblock">'
            f'<div class="tb-cell tb-wide"><span class="tb-label">Orden de trabajo</span>'
            f'<span class="tb-value">{escape(order_code)} · {escape(name)}</span></div>'
            f'<div class="tb-cell"><span class="tb-label">Huella del plan</span>'
            f'<span class="tb-value">{escape(short_fp)}</span></div>'
            f'<div class="tb-cell"><span class="tb-label">Emitido</span>'
            f'<span class="tb-value">{escape(generated)}</span></div>'
            '<div class="tb-cell"><span class="tb-label">Página</span>'
            '<span class="tb-value pg"></span></div></div>'
        )

    body = titleblock("Pack de producción")
    # ---- cover ----
    qr_payload = f"DEKOPEN|{order_code}|PACK|{short_fp}"
    qr_svg = segno.make(qr_payload, error="m").svg_inline(border=2, scale=6)
    body += (
        '<main class="workshop"><section class="pack-section first">'
        '<div class="masthead"><span class="brand">DEKOPEN'
        '<span class="mark"></span></span>'
        f'<div class="meta"><strong>{escape(order_code)}</strong><br/>'
        f'Pack de producción · {escape(short_fp)}</div></div>'
        '<div class="rule-stack"></div>'
        '<div class="cover-stats">'
        f'<div class="cover-stat"><strong>{quantity}</strong><span>unidades</span></div>'
        f'<div class="cover-stat"><strong>{len(bars)}</strong><span>barras</span></div>'
        f'<div class="cover-stat"><strong>{len(sheets)}</strong><span>láminas</span></div>'
        f'<div class="cover-stat"><strong>{member_count}</strong><span>miembros</span></div>'
        f'<div class="cover-stat"><strong>{len(ops)}</strong><span>operaciones</span></div>'
        f'<div class="cover-stat"><strong>{len(glasses)}</strong><span>vidrios</span></div>'
        "</div>"
        '<div class="pack-meta">'
        f'<span>Color: <strong>{escape(_value(optimization.get("color")))}</strong></span>'
        f'<span>Estrategia: <strong>{escape(_value(optimization.get("strategy")))}</strong></span>'
        f'<span>Optimizado: <strong>{escape(_cldate(optimization.get("optimized_at")))}</strong></span>'
        f'<span>Merma de proceso: <strong>{_value(metrics.get("process_waste_mm"))} mm</strong></span>'
        "</div>"
        '<div class="sign-row">'
        f'<div class="qr">{qr_svg}</div>'
        '<div class="sign-cell sign-date"><span class="sign-label">Fecha</span></div>'
        '<div class="sign-cell"><span class="sign-label">Responsable</span></div>'
        '<div class="sign-cell"><span class="sign-label">Recepción taller</span></div>'
        "</div></section>"
    )
    # ---- cut ----
    if bars:
        body += '<section class="pack-section">'
        first = True
        pools = _piece_pools(_cut_piece_ids(snapshot), labels)
        has_sagitta = any(
            cut.get("sagitta_mm") not in (None, "", "0", "0.00")
            for bar in bars
            for cut in (bar.get("cuts") or [])
            if isinstance(cut, dict)
        )
        headers = ["Sec.", "Pieza", "Posición", "Vano / hoja", "Función", "Corte mm", "Ángulos"]
        classes = ["", "", "", "", "", "dimension", ""]
        if has_sagitta:
            headers.append("Sagitta")
            classes.append("dimension")
        for bar in bars:
            source = str(bar.get("source") or "NEW")
            badge = (
                '<span class="badge badge-remnant">retazo '
                + escape(_value(bar.get("remnant_id"))[:8].upper())
                + "</span>"
                if source == "REMNANT"
                else '<span class="badge badge-new">barra nueva</span>'
            )
            bar_no = _value(bar.get("bar_index"))
            bar_sku = _value(bar.get("commercial_sku"))
            stock = _mm(bar.get("stock_length_mm"))
            kerf_total = _mm(bar.get("kerf_total_mm") or "0")
            head_trim = _mm(bar.get("head_trim_mm") or "0")
            tail_trim = _mm(bar.get("tail_trim_mm") or "0")
            remainder = _mm(bar.get("remainder_mm") or "0")
            cuts = [c for c in (bar.get("cuts") or []) if isinstance(c, dict)]
            pieces_mm = sum(
                (_mm(c.get("length_mm") or "0") for c in cuts), Decimal("0")
            )
            diff = stock - (
                pieces_mm + kerf_total + head_trim + tail_trim + remainder
            )
            remnant_line = ""
            if remainder > 0:
                if bar.get("remainder_reusable"):
                    remnant_line = (
                        f"Retazo {_fmt_mm(remainder)} mm recuperable — "
                        "etiquetar y devolver a stock."
                    )
                else:
                    remnant_line = (
                        f"Cola {_fmt_mm(remainder)} mm — desecho, no "
                        "retorna a stock."
                    )
            codes: list[str] = []
            table_rows: list[list[object]] = []
            for index, cut in enumerate(cuts):
                code, _entity = _claim_piece(cut, pools, labels, cut_map)
                codes.append(code)
                row: list[object] = [
                    cut.get("sequence") or index + 1,
                    code,
                    labels["position"].get(
                        cut.get("source_position_id"),
                        cut.get("source_position_id"),
                    ),
                    _location(labels, cut.get("bay_id"), cut.get("leaf_id")),
                    " · ".join(
                        part
                        for part in (
                            _CATEGORY_ES.get(
                                str(cut.get("source_kind")),
                                _value(cut.get("source_kind")),
                            ),
                            _ROLE_ES.get(
                                _role_name(cut.get("role")),
                                _value(cut.get("role")),
                            ),
                        )
                        if part
                    ) or "—",
                    _fmt_mm(cut.get("length_mm")),
                    f"{_fmt_mm(cut.get('angle_left'))}° / "
                    f"{_fmt_mm(cut.get('angle_right'))}°",
                ]
                if has_sagitta:
                    row.append(_value(cut.get("sagitta_mm")))
                table_rows.append(row)
            body += (
                '<div class="bar-block">'
                + ("<h2>Plan de barras</h2>" if first else "")
                + '<div class="bar-band">'
                + f"<h3>Barra {bar_no} · {escape(bar_sku)} · "
                f"{escape(_value(bar.get('material')))} · "
                f"{_value(bar.get('stock_length_mm'))} mm {badge} · "
                f"rendimiento {_pct(bar.get('yield_pct'))}%</h3>"
                + _bar_svg(bar, labels, cut_map, codes=codes)
                + "</div>"
                + _table(
                    headers,
                    table_rows,
                    classes,
                    thead_extra=(
                        f'<tr class="bar-cont"><th colspan="{len(headers)}">'
                        f"Tabla de cortes — Barra {escape(bar_no)} · "
                        f"{escape(bar_sku)}</th></tr>"
                    ),
                )
                + (
                    f'<div class="bar-balance {"ok" if diff == 0 else "diff"}">'
                    f"{_fmt_mm(stock)} mm = {_fmt_mm(pieces_mm)} mm piezas "
                    f"({len(cuts)}) + {_fmt_mm(kerf_total)} mm disco "
                    f"+ {_fmt_mm(head_trim + tail_trim)} mm despuntes "
                    f"+ {_fmt_mm(remainder)} mm remanente"
                    + (
                        " — cierra exacto"
                        if diff == 0
                        else f" — diferencia sin asignar {_fmt_mm(diff)} mm"
                    )
                    + "</div>"
                )
                + (
                    f'<div class="bar-remnant">{escape(remnant_line)}</div>'
                    if remnant_line
                    else ""
                )
                + "</div>"
            )
            first = False
        body += "</section>"
    if sheets:
        body += '<section class="pack-section">'
        first = True
        for sheet in sheets:
            body += (
                '<div class="bar-band">'
                + ("<h2>Plan de láminas</h2>" if first else "")
                + f"<h3>Lámina {_value(sheet.get('sheet_index'))} · "
                f"{escape(_value(sheet.get('purchasing_sku')))} · "
                f"{_value(sheet.get('sheet_width_mm'))}×"
                f"{_value(sheet.get('sheet_height_mm'))} mm · "
                f"rendimiento {_pct(sheet.get('yield_pct'))}%</h3>"
                + _sheet_svg(sheet, labels, infills)
                + "</div>"
            )
            first = False
        body += "</section>"
    if unnested:
        body += (
            '<section class="pack-section"><h2>Piezas no ubicadas</h2>'
            + _table(
                ["Pieza", "Grupo", "Medidas", "Motivo"],
                [
                    [
                        infills.get(
                            _infill_key(item),
                            str(item.get("kind") or ""),
                        )
                        + " · "
                        + _location(
                            labels, item.get("bay_id"), item.get("leaf_id")
                        ),
                        item.get("group"),
                        f"{_value(item.get('width_mm'))}×{_value(item.get('height_mm'))}"
                        if item.get("width_mm")
                        else _value(item.get("length_mm")),
                        _UNNEST_REASONS.get(
                            str(item.get("reason") or ""),
                            item.get("reason"),
                        ),
                    ]
                    for item in unnested
                ],
                ["", "", "dimension", ""],
            )
            + "</section>"
        )
    # ---- machining ----
    member_ops = [op for op in ops if op.host_kind == "MEMBER"]
    saw_ops = [op for op in ops if op.kind == OperationKind.SAW_CUT]
    body += '<section class="pack-section"><h2>Mecanizado</h2>'
    if not member_ops:
        body += (
            '<p class="muted">Sin mecanizados secundarios — solo cortes de '
            "sierra del plan de barras.</p>"
        )
    else:
        body += (
            '<p class="muted">Operaciones secundarias por miembro '
            "(coordenadas en plano del conjunto, origen esquina superior "
            "izquierda del marco nominal). Datos sin autoridad declarada "
            "nunca se emiten.</p>"
        )
        members_by_id = {
            member.member_id: member for unit in fact_units for member in unit.members
        }
        grouped: dict[str, list] = {}
        for op in member_ops:
            grouped.setdefault(str(op.host), []).append(op)
        body += '<div class="pack-grid">'
        for host_id, host_ops in grouped.items():
            member = members_by_id.get(host_id)
            code = labels["member"].get(
                host_id,
                member.semantic_member_id if member is not None else host_id[:10],
            )
            member_dict = (
                member.model_dump(mode="json") if member is not None else {}
            )
            op_dicts = [op.model_dump(mode="json") for op in host_ops]
            body += (
                '<div class="member-card">'
                f"<h4>{escape(code)} · "
                f"{escape(member_dict.get('workshop_sku', '') or '')} · "
                f"{_value(member_dict.get('cut_length_mm'))} mm</h4>"
                + _member_svg(member_dict, op_dicts)
                + '<div class="op-table">'
                + '<table><colgroup>'
                + '<col style="width:7mm"/><col style="width:17mm"/>'
                + '<col style="width:11mm"/><col style="width:14mm"/>'
                + '<col style="width:12mm"/><col style="width:16mm"/><col/>'
                + "</colgroup>"
                + _table_raw(
                    ["N°", "Op", "Dist.", "Ref.", "P.", "Hr.", "Base"],
                    [
                        [
                            index + 1,
                            _OP_LABELS.get(op.kind.value, op.kind.value),
                            _value(
                                _op_anchor(member_dict, op_dicts[index])
                            ),
                            _op_reference(op.detail),
                            _value(op.depth_mm),
                            _TOOL_LABELS.get(
                                str(op.tool_id or ""), _value(op.tool_id)
                            ),
                            _basis_label(op.basis),
                        ]
                        for index, op in enumerate(host_ops)
                    ],
                    ["mark", "", "dimension", "", "dimension", "", ""],
                )
                + "</div>"
                + "</div>"
            )
        body += "</div>"
    body += (
        f'<p class="muted">Cortes de sierra: {len(saw_ops)} — ver plan de '
        "barras para posición en barra.</p></section>"
    )
    # ---- assembly ----
    if fact_units:
        body += '<section class="pack-section"><h2>Ensamblaje</h2>'
        for index, unit in enumerate(fact_units, start=1):
            pos_label = labels["position"].get(unit.position_id, unit.position_id[:8])
            body += (
                f"<h3>Unidad {index} · Posición {escape(str(pos_label))} · "
                f"{_value(unit.nominal_width_mm)}×"
                f"{_value(unit.nominal_height_mm)} mm · "
                f"{escape(_VIEW_LABELS.get(unit.view, unit.view))}</h3>"
                f'<div class="unit-map">{_unit_map_svg(unit, labels)}</div>'
                + _table(
                    ["Código", "Tipo", "Detalle"],
                    [
                        [
                            labels["member"].get(m.member_id, m.semantic_member_id),
                            "Miembro",
                            f"{escape(m.workshop_sku)} · "
                            f"{escape(_ROLE_LABELS.get(m.identity.role.value, m.identity.role.value))}"
                            f" · largo {_value(m.cut_length_mm)} mm",
                        ]
                        for m in unit.members
                    ]
                    + [
                        [
                            labels["reinforcement"].get(r.reinforcement_id, "R"),
                            "Refuerzo",
                            f"{escape(r.workshop_sku)} · "
                            f"{_value(r.cut_length_mm)} mm",
                        ]
                        for r in unit.reinforcements
                    ]
                    + [
                        [
                            labels["infill"].get(i.infill_id, "I"),
                            _INFILL_LABELS.get(i.kind, i.kind),
                            f"{escape(i.technical_sku)} · {escape(i.composition)}",
                        ]
                        for i in unit.infills
                    ]
                    + [
                        [
                            labels["handle"].get(h.handle_id, "MAN"),
                            "Herraje",
                            f"{escape(_SLOT_ES.get(h.handle_domain_slot, h.handle_domain_slot))} · "
                            f"{_value(h.requested_height_mm)} mm",
                        ]
                        for h in unit.handles
                    ],
                    ["", "", ""],
                )
            )
        body += "</section>"
    # ---- glazing ----
    if glasses:
        edge_names = {
            "top": "sup.",
            "right": "der.",
            "bottom": "inf.",
            "left": "izq.",
        }

        def polish_for(piece: dict[str, object]) -> str:
            for entry in polishing:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("bay_id")) != str(piece.get("bay_id")):
                    continue
                if str(entry.get("leaf_id") or "") != str(piece.get("leaf_id") or ""):
                    continue
                edges = entry.get("edges") or {}
                picked = [
                    edge_names[name]
                    for name in ("top", "right", "bottom", "left")
                    if edges.get(name)
                ]
                return " ".join(picked) if picked else "sin pulido"
            return "—"

        groups: dict[str, list[dict[str, object]]] = {}
        for glass in glasses:
            key = str(
                glass.get("glass_spec")
                or glass.get("article_sku")
                or "sin composición"
            )
            groups.setdefault(key, []).append(glass)
        body += '<section class="pack-section"><h2>Acristalamiento</h2>'
        for spec, pieces in groups.items():
            body += f"<h3>{escape(spec)} · {len(pieces)} piezas</h3>" + _table(
                [
                    "Ubicación",
                    "Medidas",
                    "Área",
                    "Peso",
                    "Espesor neto",
                    "Pulido",
                ],
                [
                    [
                        _location(
                            labels, glass.get("bay_id"), glass.get("leaf_id")
                        ),
                        f"{_value(glass.get('width_mm'))}×"
                        f"{_value(glass.get('height_mm'))}",
                        _value(glass.get("area_m2")),
                        _value(glass.get("weight_kg")),
                        _value(glass.get("thickness_net_mm")),
                        polish_for(glass),
                    ]
                    for glass in pieces
                ],
                ["", "dimension", "dimension", "dimension", "dimension", ""],
            )
        body += "</section>"
    # ---- QC ----
    rows = _qc_rows(fact_units, labels)
    if rows:
        body += (
            '<section class="pack-section"><h2>Control de calidad</h2>'
            '<p class="muted">Verifica cada pieza contra el valor esperado '
            "de la revisión sellada; registra la medida real y marca "
            "conforme/no conforme.</p>"
            + '<table><thead><tr><th>Pieza</th><th>Esperado</th>'
            "<th>Medido</th><th>OK</th><th>NC</th></tr></thead><tbody>"
            + "".join(
                f"<tr><td>{escape(_value(row[0]))}</td>"
                f"<td>{escape(_value(row[1]))}</td><td></td>"
                f'<td class="qc-cell"><span class="qc-check"></span></td>'
                f'<td class="qc-cell"><span class="qc-check"></span></td></tr>'
                for row in rows
            )
            + "</tbody></table>"
            + '<div class="sign-row">'
            '<div class="sign-cell sign-date"><span class="sign-label">Fecha</span></div>'
            '<div class="sign-cell"><span class="sign-label">Operario</span></div>'
            '<div class="sign-cell"><span class="sign-label">Supervisor</span></div>'
            "</div></section>"
        )
    # ---- labels ----
    packing = payload.get("packing") or {}
    units = packing.get("units") or []
    body += '<section class="pack-section"><h2>Etiquetas de bulto</h2>'
    if not units:
        body += (
            '<p class="warn-note">Sin packing generado — emitir el packing '
            "de la orden para producir etiquetas con QR por unidad.</p>"
        )
    else:
        body += (
            '<p class="muted">Etiqueta de bulto a tamaño real: 100×50 mm — '
            "imprimir al 100%, sin 'ajustar a página'.</p>"
        )
        body += '<div class="label-grid">'
        for unit in units:
            if not isinstance(unit, dict):
                continue
            label_code = _value(unit.get("label_code"))
            pieces = sum(
                int(unit.get(key) or 0)
                for key in (
                    "profiles",
                    "reinforcements",
                    "glasses",
                    "panels",
                    "hardware",
                    "fittings",
                )
            )
            qr = segno.make(
                f"DEKOPEN|{order_code}|{label_code}|{pieces}", error="m"
            ).svg_inline(border=3, scale=5, dark="#161C1F", light="#FFFFFF")
            body += (
                f'<div class="unit-label"><div class="qr">{qr}</div>'
                f'<div class="label-body"><h4>{escape(label_code)}</h4>'
                f'<p class="muted">{escape(order_code)} · {pieces} piezas<br>'
                f"perfiles {unit.get('profiles') or 0} · refuerzos "
                f"{unit.get('reinforcements') or 0} · vidrios "
                f"{unit.get('glasses') or 0} · paneles "
                f"{unit.get('panels') or 0} · herrajes "
                f"{unit.get('hardware') or 0} · accesorios cristal "
                f"{unit.get('fittings') or 0}</p></div></div>"
            )
        body += "</div>"
    body += (
        f'<p class="muted">Huella completa del plan: {escape(fingerprint)}'
        "</p></section></main>"
    )
    return (
        '<!doctype html><html lang="es-CL"><head><meta charset="utf-8">'
        f"<style>{_CSS}{_CSS_PACK}{_CSS_BUNDLE}</style></head>"
        f"<body>{body}</body></html>"
    )


def render_production_pack(*, org_id: UUID, order_id: UUID) -> tuple[bytes, str]:
    """PDF bytes for the complete production pack of the order's current
    optimization plan; refuses missing/invalidated plans."""
    from weasyprint import HTML

    with transaction.atomic(), documentary_backend():
        order = one(
            """
            SELECT id, order_code, status::text, payload_json,
                   project_version_id
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            """,
            [str(order_id), str(org_id)],
            "work_order_not_found",
        )
        payload = _decoded(order["payload_json"])
        optimization = payload.get("optimization")
        if not isinstance(optimization, dict) or not optimization.get("bars"):
            raise DocumentaryError("cut_pack_requires_optimization")
        if optimization.get("invalidated"):
            raise DocumentaryError("plan_invalidated")
        version = one(
            "SELECT snapshot_json::text AS snapshot_json "
            "FROM public.project_versions WHERE id=%s AND org_id=%s",
            [str(order["project_version_id"]), str(org_id)],
            "version_not_found",
        )
        snapshot = decoded(version["snapshot_json"])
        if not isinstance(snapshot, dict):
            snapshot = {}
        labels = _piece_labels(
            {
                **snapshot,
                "manufacturing": snapshot.get("manufacturing")
                if isinstance(snapshot.get("manufacturing"), list)
                else [],
                "positions": snapshot.get("positions")
                if isinstance(snapshot.get("positions"), list)
                else [],
            }
        )
        fact_units = [
            ManufacturingFactsV1.model_validate_json(json.dumps(unit))
            for unit in _raw_fact_units(
                snapshot, str(payload.get("position_id") or "") or None
            )
        ]
        fingerprint = _optimization_fingerprint(optimization)
        html = _pack_html(
            order=order,
            payload=payload,
            optimization=optimization,
            snapshot=snapshot,
            labels=labels,
            cut_map=_cut_member_map(snapshot, labels),
            infills=_infill_code_map(snapshot, labels),
            fact_units=fact_units,
            fingerprint=fingerprint,
        )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=f"production-pack-{order['order_code']}",
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, f"{order['order_code']}-pack-produccion.pdf"
