"""§10 workshop cut pack — the printable pack bound to a work order's live
optimization. It re-renders on demand: re-optimizing invalidates the old
plan (and therefore the old pack) so the print always matches authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from uuid import UUID

import segno
from documents.renderers import (
    _CATEGORY_ES,
    finish_key_label,
    _CSS,
    _ROLE_ES,
    _bar_assignments,
    _cldate,
    _fmt_mm as _eng_fmt_mm,
    _cut_key,
    _cut_member_map,
    _infill_code_map,
    _infill_key,
    _join_codes,
    _location,
    _member_ops,
    _pct,
    _claim_piece,  # noqa: F401 — re-exportado para pack.py
    _piece_labels,
    _piece_pools,  # noqa: F401 — re-exportado para pack.py
    _reinforcement_parents,
    _role_name,
    _sheet_assignments,
    _table,
    _url_fetcher,
    _value,
)
from django.db import transaction

from documents.repository import (
    DocumentaryError,
    decoded,
    documentary_backend,
    one,
    rows,
)

from production.service import (
    _BAR_DROP_STATIONS,
    _STEP_LABELS,
    _decoded,
    _optimization_fingerprint,
)


_LABEL_PAPER = {"LETTER": "letter", "LEGAL": "legal", "A4": "a4"}

_CSS_PACK = """
@page { size: letter landscape; margin: 10mm 10mm 16mm;
        @bottom-center { content: element(titleblock); } }
@page piece-labels { size: letter portrait; margin: 6mm;
        @bottom-center { content: element(titleblock); } }
@page label-roll { size: 100mm 50mm; margin: 0; }
.labels-sheet { page: piece-labels; }
.label-roll-sheet { page: label-roll; }
.bar-svg { width: 100%; height: auto; display: block; }
.bar-svg text { font-family: 'IBM Plex Mono', monospace; }
.sheet-svg { display: block; margin: 0 auto; }
.sheet-svg text { font-family: 'IBM Plex Mono', monospace; }
.bar-block { break-inside: avoid; margin-bottom: 2.5mm; }
.pack-legend { font-size: 8pt; color: #465158; margin: 0 0 1.5mm; }
.bar-head { display: flex; align-items: baseline; gap: 3mm; margin: 2mm 0 0.5mm; }
.bar-head h3 { margin: 0; }
.bar-orient { display: flex; gap: 4mm; align-items: center;
              font-size: 8pt; color: #465158; margin: 0 0 0.5mm; }
.bar-orient .conv { flex: 1; }
.bar-foot { display: flex; gap: 5mm; align-items: baseline;
            margin: 0.8mm 0 0; }
.bar-foot .bar-balance { flex: 1 1 auto; }
.bar-foot .bar-remnant { flex: 0 0 auto; text-align: right; }
.bar-balance { font: 8.5pt 'IBM Plex Mono', monospace; color: #252D31;
               margin: 0; }
.bar-balance.ok { color: #075F5A; }
.bar-balance.diff { color: #991B1B; font-weight: 600; }
.bar-remnant { font-size: 8.5pt; color: #465158; }
.section-svg { width: 16mm; height: 11mm; flex: none; }
.pack-meta { display: flex; flex-wrap: wrap; gap: 4mm 7mm;
             font: 8.5pt 'IBM Plex Mono', monospace; margin: 2mm 0 4mm; }
.pack-meta strong { color: #161C1F; }
.badge { display: inline-block; padding: 0.4mm 2mm; border-radius: 1mm;
         font-size: 8pt; font-weight: 600; letter-spacing: 0.4pt;
         text-transform: uppercase; }
/* Legibilidad P13: dentro del pack el texto de cuerpo no baja de 8pt —
   los encabezados de tabla del sistema (7pt) no aplican aquí. */
.workshop th { font-size: 8pt; }
/* Piso de impresión P13: en el pack ni una etiqueta baja de 8pt — la
   franja del título corre fuera de <main> pero comparte esta hoja. */
.tb-label, .sign-label { font-size: 8pt; }
.badge-new { background: #E6F4F2; color: #075F5A; }
.badge-remnant { background: #FDF1E3; color: #B25E09; }
.qr { width: 22mm; height: 22mm; }
.piece-label { display: inline-flex; gap: 1.6mm; padding: 1.4mm;
               border: 0.35mm solid #161C1F; box-sizing: border-box;
               width: 64.7mm; height: 38mm; break-inside: avoid;
               overflow: hidden; line-height: 1.3; }
/* La grilla va en flujo de línea (no flex): WeasyPrint no fragmenta un
   contenedor flex entre páginas y un pack grande quedaría aplastado
   en una sola plana. */
.labels-grid { display: block; font-size: 0; line-height: 0; }
.labels-grid .piece-label { vertical-align: top; margin: 0 2mm 2mm 0; }
.label-roll .piece-label { width: 97mm; height: 47mm; margin: 1.5mm;
                           page-break-after: always; }
.piece-label .pl-qr { flex: none; width: 13.5mm; }
.piece-label .pl-qr svg { width: 13.5mm; height: 13.5mm; display: block; }
.label-roll .piece-label .pl-qr { width: 19mm; }
.label-roll .piece-label .pl-qr svg { width: 19mm; height: 19mm; }
.piece-label .pl-body { min-width: 0; }
.piece-label .pl-code { font: 700 9.5pt 'IBM Plex Mono', monospace;
                        color: #161C1F; }
.label-roll .piece-label .pl-code { font-size: 12pt; }
.piece-label .pl-line { font-size: 8pt; color: #252D31; line-height: 1.3;
                        white-space: nowrap; overflow: hidden;
                        text-overflow: ellipsis; }
.label-roll .piece-label .pl-line { font-size: 9pt; }
.piece-label .pl-next { font-size: 8pt; font-weight: 600; color: #075F5A; }
.label-roll .piece-label .pl-next { font-size: 9pt; }
.piece-label .pl-writein { font: 8pt 'IBM Plex Mono', monospace;
                           color: #727D82; }
.piece-label.remnant-label { background: #FDF1E3; }
"""

_MATERIAL_ES = {
    "PVC": "PVC",
    "STEEL": "Acero",
    "ALUMINIUM": "Aluminio",
    "ALUMINUM": "Aluminio",
    "WOOD": "Madera",
    "GLASS": "Vidrio",
    "STEEL_REINFORCEMENT": "Acero",
}

_ORIENTATION_ES = {
    "EXTERIOR_DOWN": "cara exterior abajo",
    "EXTERIOR_UP": "cara exterior arriba",
    "EXTERIOR_LEFT": "cara exterior a la izquierda",
    "EXTERIOR_RIGHT": "cara exterior a la derecha",
}


def _fmt_mm(value: object) -> str:
    """Printed mm per §3.3 — thin-space grouping, comma decimal:
    6000.00 → '6 000', 1319.50 → '1 319,5'. Internal data stays
    Decimal — only the glyph changes."""
    text = _value(value)
    if text in ("", "—"):
        return "—"
    try:
        number = Decimal(str(value))
    except Exception:
        return text
    out = _eng_fmt_mm(number.normalize())
    return out if out else "0"


def _mm(value: object) -> Decimal:
    return Decimal(str(value))


def _bar_svg(
    bar: dict[str, object],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
    codes: list[str] | None = None,
    *,
    span_mm: Decimal = Decimal("260"),
) -> str:
    """The wide strip the saw operator reads: head trim → pieces separated
    by kerf marks → tail trim → remainder (green when reusable, hatched when
    waste). Text is sized in physical millimetres — a 6000mm bar and a 900mm
    remnant render the same print size — and dense small pieces take leader
    labels in alternating lanes so codes never overlap. ``span_mm`` is the
    printed width available on the page (landscape pack ≈ 260, portrait
    DOC-05 ≈ 186)."""
    stock = _mm(bar["stock_length_mm"])
    head_trim = _mm(bar["head_trim_mm"])
    tail_trim = _mm(bar["tail_trim_mm"])
    kerf = _mm(bar["kerf_mm"])
    remainder = _mm(bar["remainder_mm"])
    cuts = [c for c in bar.get("cuts") or [] if isinstance(c, dict)]
    # The strip renders ~span_mm wide on the page: `u` viewBox units ≈ 1
    # printed mm. Sizing every label off `u` keeps real print size constant
    # regardless of the stock length.
    u = max(stock / span_mm, Decimal("4"))
    fs_code = u * Decimal("3.2")
    # fs_dim imprime exactamente 3.0 mm (~8.5 pt) — el piso de legibilidad
    # del encargo, fijo respecto al largo de la barra.
    fs_dim = u * Decimal("3.0")
    fs_seq = u * Decimal("3.4")
    bar_h = u * Decimal("9")
    # Adaptive vertical budget: leaders exist only when a segment is too
    # narrow to hold its label inside — a bar of wide pieces shouldn't pay
    # for three empty lanes. Pre-compute the inside/outside decision per cut
    # (same predicate the draw pass uses) and size the padding to the lanes
    # actually reachable.
    def _est(text: str, fs: Decimal) -> Decimal:
        return Decimal(len(text)) * fs * Decimal("0.62")

    def _cut_label(cut: dict[str, object], index: int) -> str:
        if codes is not None and index < len(codes):
            return codes[index]
        piece_id = str(cut.get("piece_id") or "")
        return cut_map.get(
            _cut_key(cut),
            labels["member"].get(
                piece_id, labels["reinforcement"].get(piece_id, piece_id[:10])
            ),
        )

    def _angle(value: object) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("90")

    inside_flags: list[bool] = []
    for index, cut in enumerate(cuts):
        label_code = _cut_label(cut, index)
        cut_location = _location(
            labels, cut.get("bay_id"), cut.get("leaf_id")
        )
        piece_len = _mm(cut["length_mm"])
        inside_flags.append(
            _est(label_code, fs_code) < piece_len * Decimal("0.9")
            and _est(cut_location, fs_dim) < piece_len * Decimal("0.9")
        )
    leader_above = any(
        not flag and index % 2 == 0 for index, flag in enumerate(inside_flags)
    )
    leader_below = any(
        not flag and index % 2 == 1 for index, flag in enumerate(inside_flags)
    )
    pad_top = u * Decimal("19") if leader_above else u * Decimal("5")
    pad_bottom = u * Decimal("22") if leader_below else u * Decimal("13")
    # Horizontal pad lets edge-segment leader labels use the margin instead
    # of clipping at the viewBox boundary (first segment lost "1 · M-…").
    pad_x = u * Decimal("7")
    height = pad_top + bar_h + pad_bottom
    svg = [
        f'<svg class="bar-svg" viewBox="-{pad_x} 0 {stock + pad_x * 2} {height}" '
        'preserveAspectRatio="xMinYMid meet" '
        'xmlns="http://www.w3.org/2000/svg">'
    ]

    lane_step = u * Decimal("6.4")
    lane_ys = {
        "above": [pad_top - u * Decimal("4") - i * lane_step for i in range(3)],
        "below": [
            pad_top + bar_h + u * Decimal("8") + i * lane_step for i in range(3)
        ],
    }
    lane_used: dict[str, list[list[Decimal]]] = {
        "above": [[Decimal("0"), Decimal("0")] for _ in range(3)],
        "below": [[Decimal("0"), Decimal("0")] for _ in range(3)],
    }
    # Under-bar dimension rows ride two alternating lanes with used extents —
    # adjacent wide pieces can no longer run their `1256.00 mm · 45.0°/45.0°`
    # strings into each other.
    dim_ys = [
        pad_top + bar_h + u * Decimal("4.5"),
        pad_top + bar_h + u * Decimal("11"),
    ]
    dim_used: list[list[Decimal]] = [
        [Decimal("0"), Decimal("0")] for _ in range(2)
    ]

    def _clamp_cx(cx: Decimal, half: Decimal) -> Decimal:
        return min(max(cx, half - pad_x + u), stock + pad_x - half - u)

    x = Decimal("0")
    usable_end = stock - remainder
    # head trim
    if head_trim > 0:
        svg.append(
            f'<rect x="{x}" y="{pad_top}" width="{head_trim}" height="{bar_h}" '
            'fill="#465158" stroke="#161C1F" stroke-width="1"/>'
        )
        if head_trim >= u * Decimal("6"):
            svg.append(
                f'<text x="{x + head_trim / 2}" y="{pad_top + bar_h / 2}" '
                'text-anchor="middle" dominant-baseline="middle" fill="#FCFDFC" '
                f'font-size="{fs_dim}" transform="rotate(-90 '
                f'{x + head_trim / 2} {pad_top + bar_h / 2})">'
                f'desp. {_fmt_mm(head_trim)}</text>'
            )
        x += head_trim
    # Feed arrow — the declared convention: the head-trim end enters the
    # saw first and angles are read left/right off that end.
    svg.append(
        f'<line x1="{-pad_x * Decimal("0.8")}" y1="{pad_top + bar_h / 2}" '
        f'x2="{-pad_x * Decimal("0.15")}" y2="{pad_top + bar_h / 2}" '
        'stroke="#465158" stroke-width="1.5" marker-end="url(#feed-arrow)"/>'
    )
    svg.insert(
        1,
        '<defs><marker id="feed-arrow" markerWidth="6" markerHeight="6" '
        'refX="5" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#465158"/></marker></defs>',
    )
    for index, cut in enumerate(cuts):
        piece_len = _mm(cut["length_mm"])
        code = _cut_label(cut, index)
        location = _location(labels, cut.get("bay_id"), cut.get("leaf_id"))
        position = labels["position"].get(cut.get("source_position_id"), "")
        angles = (
            f"{_value(cut.get('angle_left'))}°/{_value(cut.get('angle_right'))}°"
        )
        seq = str(cut.get("sequence") or index + 1)
        svg.append(
            f'<rect x="{x}" y="{pad_top}" width="{piece_len}" height="{bar_h}" '
            'fill="#0B7770" stroke="#075F5A" stroke-width="1.5"/>'
        )
        # Miter ticks — a slanted corner mark per non-90° end. The mark only
        # says "this end is mitered"; the cut direction comes from the
        # left/right angles in the table (drawing a direction would invent
        # geometry the plan does not carry).
        miter = bar_h * Decimal("0.45")
        if _angle(cut.get("angle_left")) != Decimal("90"):
            svg.append(
                f'<line x1="{x + u * Decimal("0.4")}" '
                f'y1="{pad_top}" x2="{x + u * Decimal("0.4") + miter}" '
                f'y2="{pad_top + miter}" stroke="#FCFDFC" stroke-width="2"/>'
            )
        if _angle(cut.get("angle_right")) != Decimal("90"):
            svg.append(
                f'<line x1="{x + piece_len - u * Decimal("0.4")}" '
                f'y1="{pad_top}" '
                f'x2="{x + piece_len - u * Decimal("0.4") - miter}" '
                f'y2="{pad_top + miter}" stroke="#FCFDFC" stroke-width="2"/>'
            )
        center = x + piece_len / 2
        inside = (
            _est(code, fs_code) < piece_len * Decimal("0.9")
            and _est(location, fs_dim) < piece_len * Decimal("0.9")
        )
        if inside:
            svg.append(
                f'<text x="{center}" y="{pad_top + bar_h * Decimal("0.38")}" '
                'text-anchor="middle" fill="#FCFDFC" '
                f'font-size="{fs_code}" font-weight="600">{escape(code)}</text>'
                f'<text x="{center}" y="{pad_top + bar_h * Decimal("0.78")}" '
                'text-anchor="middle" fill="#FCFDFC" '
                f'font-size="{fs_dim}">'
                f'{escape(location)}{" " if position else ""}'
                f'{escape(str(position))}</text>'
            )
            dim_label = f'{_fmt_mm(cut.get("length_mm"))} mm · {angles}'
            dim_half = _est(dim_label, fs_dim) / 2
            dim_lane = next(
                (
                    lane
                    for lane in range(2)
                    if dim_used[lane][1] == 0
                    or center - dim_half > dim_used[lane][1]
                ),
                None,
            )
            if dim_lane is not None:
                dim_cx = _clamp_cx(center, dim_half)
                dim_used[dim_lane] = [dim_cx - dim_half, dim_cx + dim_half]
                svg.append(
                    f'<text x="{dim_cx}" y="{dim_ys[dim_lane]}" '
                    'text-anchor="middle" fill="#161C1F" '
                    f'font-size="{fs_dim}">{dim_label}</text>'
                )
        else:
            if _est(seq, fs_seq) < piece_len * Decimal("0.8"):
                svg.append(
                    f'<text x="{center}" y="{pad_top + bar_h / 2}" '
                    'text-anchor="middle" dominant-baseline="middle" '
                    f'fill="#FCFDFC" font-size="{fs_seq}" '
                    f'font-weight="600">{seq}</text>'
                )
            side = "above" if index % 2 == 0 else "below"
            # Secuencia + etiqueta + largo + ángulos — la fila de tabla que
            # llevaba esto se retiró: el diagrama es la lista de corte.
            label = (
                f"{seq} · {code} · {_fmt_mm(cut.get('length_mm'))} mm · "
                f"{_fmt_mm(cut.get('angle_left'))}°/{_fmt_mm(cut.get('angle_right'))}°"
            )
            half = _est(label, fs_code) / 2
            lane = 0
            while (
                lane < 2
                and center - half <= lane_used[side][lane][1]
                and lane_used[side][lane][1] > 0
            ):
                lane += 1
            cx = center
            if lane_used[side][lane][1] > 0 and cx - half <= lane_used[side][lane][1]:
                # Deepest lane already busy — nudge the label right of the
                # used extent; the leader line slants but never overlaps.
                cx = lane_used[side][lane][1] + half + u * Decimal("1.5")
            cx = _clamp_cx(cx, half)
            lane_used[side][lane] = [cx - half, cx + half]
            ly = lane_ys[side][lane]
            anchor_y = pad_top if side == "above" else pad_top + bar_h
            svg.append(
                f'<line x1="{center}" y1="{anchor_y}" '
                f'x2="{cx - half}" y2="{ly + (u * Decimal("1.2") if side == "above" else -u * Decimal("3.4"))}" '
                'stroke="#465158" stroke-width="1"/>'
                f'<text x="{cx}" y="{ly}" text-anchor="middle" '
                f'fill="#161C1F" font-size="{fs_code}" '
                f'font-weight="600">{escape(label)}</text>'
            )
        x += piece_len
        if index < len(cuts) - 1 and kerf > 0:
            svg.append(
                f'<rect x="{x}" y="{pad_top - u * Decimal("0.8")}" width="{kerf}" '
                f'height="{bar_h + u * Decimal("1.6")}" fill="#E56A32"/>'
            )
            x += kerf
    if tail_trim > 0:
        svg.append(
            f'<rect x="{x}" y="{pad_top}" width="{tail_trim}" height="{bar_h}" '
            'fill="#465158" stroke="#161C1F" stroke-width="1"/>'
        )
        if tail_trim >= u * Decimal("6"):
            svg.append(
                f'<text x="{x + tail_trim / 2}" y="{pad_top + bar_h / 2}" '
                'text-anchor="middle" dominant-baseline="middle" fill="#FCFDFC" '
                f'font-size="{fs_dim}" transform="rotate(-90 '
                f'{x + tail_trim / 2} {pad_top + bar_h / 2})">'
                f'desp. {_fmt_mm(tail_trim)}</text>'
            )
        x += tail_trim
    if remainder > 0:
        reusable = bool(bar.get("remainder_reusable"))
        fill = "#BFE6E0" if reusable else "#F4D8CB"
        svg.append(
            f'<rect x="{x}" y="{pad_top}" width="{remainder}" height="{bar_h}" '
            f'fill="{fill}" stroke="#161C1F" stroke-width="1" '
            'stroke-dasharray="6 3"/>'
        )
        tag = "retazo" if reusable else "desecho"
        if remainder >= u * Decimal("4"):
            # The full label only goes inside when the remainder can hold it —
            # a narrow tail otherwise bleeds its text over the last segment.
            # The mm value already prints in the bar's h3 line.
            inside_label = f"{tag} {_fmt_mm(remainder)} mm"
            fits = _est(inside_label, fs_dim) <= remainder - u
            label = inside_label if fits else tag
            if fits:
                cx = min(
                    x + remainder / 2,
                    stock - u * Decimal("0.5") - _est(label, fs_dim) / 2,
                )
                svg.append(
                    f'<text x="{cx}" y="{pad_top + bar_h / 2}" '
                    'text-anchor="middle" dominant-baseline="middle" '
                    f'fill="#161C1F" font-size="{fs_dim}">'
                    f'{tag} {escape(_fmt_mm(remainder))} mm</text>'
                )
            elif _est(label, fs_dim) <= remainder - u * Decimal("0.5"):
                svg.append(
                    f'<text x="{x + remainder / 2}" y="{pad_top + bar_h / 2}" '
                    'text-anchor="middle" dominant-baseline="middle" '
                    f'fill="#161C1F" font-size="{fs_dim}">{tag}</text>'
                )
            else:
                cx = _clamp_cx(x + remainder / 2, _est(label, fs_dim) / 2)
                svg.append(
                    f'<line x1="{x + remainder / 2}" y1="{pad_top}" '
                    f'x2="{cx}" y2="{pad_top - u * Decimal("4")}" '
                    'stroke="#465158" stroke-width="1"/>'
                    f'<text x="{cx}" y="{pad_top - u * Decimal("4")}" '
                    'text-anchor="middle" fill="#161C1F" '
                    f'font-size="{fs_dim}">{tag}</text>'
                )
    # stock baseline
    svg.append(
        f'<line x1="0" y1="{pad_top + bar_h + 6}" x2="{usable_end}" '
        f'y2="{pad_top + bar_h + 6}" stroke="#161C1F" stroke-width="1.5"/>'
    )
    svg.append("</svg>")
    return "".join(svg)


# _piece_pools / _claim_piece live in documents.renderers — pack.py imports
# them through this module; the top-level import re-export keeps that
# contract stable.


def _section_svg(section: object) -> str:
    """Declared article cross-section as a small oriented thumbnail — real
    geometry, never an invented silhouette. The exterior face is marked on
    the declared side."""
    if not isinstance(section, dict):
        return ""
    polygon = section.get("polygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        return ""
    points: list[tuple[Decimal, Decimal]] = []
    for point in polygon:
        if not isinstance(point, dict):
            return ""
        try:
            points.append(
                (Decimal(str(point["x_mm"])), Decimal(str(point["y_mm"])))
            )
        except Exception:
            return ""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, min_y = min(xs), min(ys)
    width = max(xs) - min_x
    height = max(ys) - min_y
    if width <= 0 or height <= 0:
        return ""
    pad = Decimal("4")
    vb_w, vb_h = width + pad * 2, height + pad * 2
    path = " ".join(
        f"{x - min_x + pad},{(max(ys) - y) + pad}" for x, y in points
    )
    orientation = str(section.get("orientation") or "")
    edge = {
        "EXTERIOR_DOWN": f'<line x1="0" y1="{vb_h}" x2="{vb_w}" y2="{vb_h}"/>',
        "EXTERIOR_UP": f'<line x1="0" y1="0" x2="{vb_w}" y2="0"/>',
        "EXTERIOR_LEFT": f'<line x1="0" y1="0" x2="0" y2="{vb_h}"/>',
        "EXTERIOR_RIGHT": f'<line x1="{vb_w}" y1="0" x2="{vb_w}" y2="{vb_h}"/>',
    }.get(orientation, "")
    return (
        f'<svg class="section-svg" viewBox="0 0 {vb_w} {vb_h}" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<polygon points="{path}" fill="#E6F4F2" stroke="#075F5A" '
        'stroke-width="1.5"/>'
        f'<g stroke="#B25E09" stroke-width="3">{edge}</g></svg>'
    )


def _bar_context(
    org_id: UUID,
    bars: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    """commercial_sku → declared article facts (name, workshop sku, section)
    plus remnant_id → rack for REMNANT-source bars. One query each — the
    printed plan names real stock, not table keys."""
    skus = sorted(
        {str(b.get("commercial_sku")) for b in bars if b.get("commercial_sku")}
    )
    context: dict[str, dict[str, object]] = {}
    if skus:
        for row in rows(
            "SELECT m.commercial_sku, a.sku, a.name, a.section::text AS section "
            "FROM public.profile_purchase_mappings m "
            "JOIN public.profile_articles a ON a.id = m.profile_article_id "
            "WHERE m.commercial_sku = ANY(%s) "
            "AND (m.org_id = %s OR m.org_id IS NULL)",
            [skus, str(org_id)],
        ):
            entry = context.setdefault(str(row["commercial_sku"]), {})
            entry.update(
                {
                    "article_sku": row.get("sku"),
                    "name": row.get("name"),
                    "section": decoded(row.get("section")),
                }
            )
        for row in rows(
            "SELECT commercial_sku, sku, name "
            "FROM public.reinforcement_articles "
            "WHERE commercial_sku = ANY(%s) AND (org_id = %s OR org_id IS NULL)",
            [skus, str(org_id)],
        ):
            entry = context.setdefault(str(row["commercial_sku"]), {})
            entry.setdefault("article_sku", row.get("sku"))
            entry.setdefault("name", row.get("name"))
    return context


_UNNEST_REASONS = {
    "shaped_glass_outline": "Vidrio con forma — corte por plantilla",
    "no_declared_sheet": "Sin formato de lámina declarado en el catálogo",
    "piece_larger_than_usable_sheet": "Pieza mayor que la lámina útil",
}

_UNNEST_ACTIONS = {
    "no_declared_sheet": "Catálogo › Vidrios › Formatos",
    "piece_larger_than_usable_sheet": (
        "Catálogo › Vidrios › Formatos o pedido a medida al proveedor"
    ),
    "shaped_glass_outline": "Mesa de corte por plantilla — plantilla en el DXF",
}


def _sheet_svg(
    sheet: dict[str, object],
    labels: dict[str, dict[object, str]],
    infills: dict[tuple[str, str, str], str],
    assignments: dict[tuple[object, object], tuple[str, object | None]] | None = None,
) -> str:
    sheet_w = _mm(sheet["sheet_width_mm"])
    sheet_h = _mm(sheet["sheet_height_mm"])
    margin = Decimal("60")
    # Explicit mm sizing — ~1:20 print scale, capped to fit the landscape
    # content box (~259×190mm after h2/h3). WeasyPrint ignores CSS height on
    # SVGs inside shrink-wrap contexts, so the scale lives on the element.
    vb_w = sheet_w + margin * 2
    vb_h = sheet_h + margin * 2
    scale = min(
        Decimal("0.05"),
        Decimal("250") / vb_w,
        Decimal("150") / vb_h,
    )
    svg = [
        f'<svg class="sheet-svg" width="{vb_w * scale}mm" '
        f'height="{vb_h * scale}mm" viewBox="{-margin} {-margin} '
        f'{vb_w} {vb_h}" '
        'preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">',
        f'<rect x="0" y="0" width="{sheet_w}" height="{sheet_h}" fill="#F5F7F6" '
        'stroke="#161C1F" stroke-width="4"/>',
    ]
    for placement in sheet.get("placements") or []:
        if not isinstance(placement, dict):
            continue
        x, y = _mm(placement["x_mm"]), _mm(placement["y_mm"])
        w, h = _mm(placement["width_mm"]), _mm(placement["height_mm"])
        location = _location(labels, placement.get("bay_id"), placement.get("leaf_id"))
        assigned = (assignments or {}).get(
            (sheet.get("sheet_index"), placement.get("sequence"))
        )
        code = (assigned[0] if assigned and assigned[0] else None) or infills.get(
            _infill_key(placement), str(placement.get("piece_id") or "")
        )
        rotated = bool(placement.get("rotated"))
        # Print-size labels: a full-height piece earns ~5mm code text; fonts
        # shrink with the smaller piece dimension so narrow panes stay
        # legible — but never below the pack's 8pt print floor (≈2.84mm at
        # the sheet's scale); a pane too small for the floor spills over
        # its edge rather than printing unreadable.
        min_font = Decimal("2.84") / scale
        fs_code = max(
            min(
                h * Decimal("0.075"),
                w * Decimal("0.9")
                / (Decimal("0.62") * Decimal(max(len(code), 1))),
            ),
            min_font,
        )
        fs_dim = max(fs_code * Decimal("0.8"), min_font)
        fs_loc = max(fs_code * Decimal("0.62"), min_font)
        gap = fs_code * Decimal("1.15")
        svg.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#BFE6E0" '
            'stroke="#075F5A" stroke-width="3"/>'
            f'<text x="{x + w / 2}" y="{y + h / 2 - gap}" text-anchor="middle" '
            'fill="#0B4D49" '
            f'font-size="{fs_code}" font-weight="600">'
            f'{escape(code)}{" ⟳" if rotated else ""}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + fs_dim}" text-anchor="middle" '
            'fill="#161C1F" '
            f'font-size="{fs_dim}">'
            f'{_fmt_mm(w)}×{_fmt_mm(h)}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + gap + fs_dim}" '
            'text-anchor="middle" '
            f'fill="#4A5559" font-size="{fs_loc}">{escape(location)}</text>'
        )
    for remnant in sheet.get("produced_remnants") or []:
        if not isinstance(remnant, dict):
            continue
        svg.append(
            f'<rect x="{_mm(remnant["x_mm"])}" y="{_mm(remnant["y_mm"])}" '
            f'width="{_mm(remnant["width_mm"])}" height="{_mm(remnant["height_mm"])}" '
            'fill="none" stroke="#B25E09" stroke-width="2.5" '
            'stroke-dasharray="18 8"/>'
        )
    svg.append("</svg>")
    return "".join(svg)


def _piece_label_html(
    *,
    code: str,
    order_code: str,
    fp8: str,
    line1: str,
    line2: str,
    next_station: str,
    qr_payload: str | None = None,
    remnant: bool = False,
) -> str:
    qr = (
        f'<div class="pl-qr">{segno.make(qr_payload, error="m").svg_inline(border=1, scale=4)}</div>'
        if qr_payload
        else '<div class="pl-qr"></div>'
    )
    return (
        f'<div class="piece-label{" remnant-label" if remnant else ""}">{qr}'
        '<div class="pl-body">'
        f'<div class="pl-code">{escape(code)}</div>'
        f'<div class="pl-line">{escape(line1)}</div>'
        f'<div class="pl-line">{escape(line2)}</div>'
        f'<div class="pl-next">→ {escape(next_station)}</div>'
        f'<div class="pl-writein">{escape(order_code)} · plan {escape(fp8)}</div>'
        "</div></div>"
    )


def _cut_label_rows(
    *,
    bars: list[dict[str, object]],
    sheets: list[dict[str, object]],
    assignments: dict[tuple[object, object], tuple[str, object | None]],
    sheet_assignments: dict[tuple[object, object], tuple[str, object | None]],
    order_code: str,
    fp8: str,
    labels: dict[str, dict[object, str]],
    next_station: dict[object, str],
    default_station: str,
    infill_station: str,
    color_label: str,
) -> str:
    """One piece label per physical piece, printed in cut order: bars first
    (bar, sequence), then sheet placements (sheet, sequence). Same codes as
    the diagrams, the CSV and the DXF — that is the contract."""
    out = []
    for bar in bars:
        for cut in [c for c in (bar.get("cuts") or []) if isinstance(c, dict)]:
            code, entity_id = assignments.get(
                (bar.get("bar_index"), cut.get("sequence")), ("", None)
            )
            role = _ROLE_ES.get(
                _role_name(cut.get("role")), _value(cut.get("role"))
            )
            function = " · ".join(
                part
                for part in (
                    _CATEGORY_ES.get(
                        str(cut.get("source_kind")),
                        _value(cut.get("source_kind")),
                    ),
                    role,
                )
                if part
            )
            station = (
                next_station.get(entity_id)
                if entity_id is not None
                else None
            ) or default_station
            position = labels["position"].get(cut.get("source_position_id"), "")
            location = _location(
                labels, cut.get("bay_id"), cut.get("leaf_id")
            )
            angles = "/".join(
                f"{_fmt_mm(cut.get(k))}°"
                for k in ("angle_left", "angle_right")
                if cut.get(k) not in (None, "")
            ) or "—"
            out.append(
                _piece_label_html(
                    code=code or "—",
                    order_code=order_code,
                    fp8=fp8,
                    line1=(
                        f"{position} {location}".strip()
                        + f" · {function}"
                    ),
                    line2=(
                        f"{_fmt_mm(cut.get('length_mm'))} mm · {angles} · "
                        f"{color_label}"
                    ),
                    next_station=station,
                    qr_payload=(
                        f"DEKOPEN|{order_code}|{code}|{fp8}"
                        if code
                        else None
                    ),
                )
            )
    for sheet in sheets:
        for piece in [
            p for p in (sheet.get("placements") or []) if isinstance(p, dict)
        ]:
            code, _entity = sheet_assignments.get(
                (sheet.get("sheet_index"), piece.get("sequence")), ("", None)
            )
            position = labels["position"].get(piece.get("source_position_id"), "")
            location = _location(
                labels, piece.get("bay_id"), piece.get("leaf_id")
            )
            out.append(
                _piece_label_html(
                    code=code or "—",
                    order_code=order_code,
                    fp8=fp8,
                    line1=f"{position} {location}".strip() + " · Vidrio/panel",
                    line2=(
                        f"{_fmt_mm(piece.get('width_mm'))}×"
                        f"{_fmt_mm(piece.get('height_mm'))} mm · lámina "
                        f"{_value(sheet.get('sheet_index'))}"
                    ),
                    next_station=infill_station,
                    qr_payload=(
                        f"DEKOPEN|{order_code}|{code}|{fp8}"
                        if code
                        else None
                    ),
                )
            )
    return "".join(out)


def _next_folio(
    produced: dict[tuple[object, ...], list[str]], key: tuple[object, ...]
) -> str | None:
    """FIFO: a bar's remainder claims the oldest produced-remnant folio of
    its (stock authority, length) — two identical drops never share a code."""
    queue = produced.get(key)
    if not queue:
        return None
    folio = queue.pop(0)
    if not queue:
        del produced[key]
    return folio


def _next_station_map(
    snapshot: dict[str, object], payload: dict[str, object] | None
) -> tuple[dict[object, str], str, str]:
    """entity id → next station label after its bar/sheeter cut.

    Members with machining ops route to the op's mapped station; plain
    members follow the first non-cutting routing step (weld/crimp/assemble);
    reinforcements ride with their host member; panes go to glazing. The
    routing the order carries is the sealed ladder — never invented."""
    routing = [
        str(step) for step in ((payload or {}).get("routing") or [])
    ]
    operation_map = {
        str(k): str(v)
        for k, v in (
            ((payload or {}).get("process_authority") or {}).get(
                "operation_station_map"
            )
            or {}
        ).items()
    }
    after_cut = next(
        (code for code in routing if code not in _BAR_DROP_STATIONS),
        "",
    )
    member_ops = _member_ops(snapshot)
    stations: dict[object, str] = {}
    for member_id, kinds in member_ops.items():
        station = operation_map.get(kinds[0]) if kinds else None
        stations[member_id] = _STEP_LABELS.get(
            str(station) if station else (after_cut or "ASSEMBLE"),
            str(station) if station else (after_cut or "Armado"),
        )
    # Reinforcements follow the member they reinforce.
    manufacturing = snapshot.get("manufacturing")
    if isinstance(manufacturing, list):
        for fact in manufacturing:
            if not isinstance(fact, dict):
                continue
            for item in fact.get("reinforcements") or []:
                if not isinstance(item, dict):
                    continue
                parent = item.get("parent_member_id")
                stations[item.get("reinforcement_id")] = stations.get(
                    parent,
                    _STEP_LABELS.get(after_cut or "ASSEMBLE", after_cut or "Armado"),
                )
    default_member = _STEP_LABELS.get(
        after_cut or "ASSEMBLE", after_cut or "Armado"
    )
    infill_station = _STEP_LABELS.get(
        "GLAZE" if "GLAZE" in routing else (after_cut or "QC"),
        "Vidriado y paneles",
    )
    return stations, default_member, infill_station


def _pack_html(
    *,
    order: dict[str, object],
    optimization: dict[str, object],
    snapshot: dict[str, object],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
    infills: dict[tuple[str, str, str], str],
    bar_meta: dict[str, dict[str, object]],
    remnant_racks: dict[str, str],
    fingerprint: str,
    produced_folios: dict[tuple[object, ...], list[str]] | None = None,
    payload: dict[str, object] | None = None,
    label_format: str = "GRID",
    label_paper: str = "LETTER",
) -> str:
    order_code = _value(order["order_code"])
    # El QR lleva 16 hex de huella — suficiente colisión cero para verificar
    # el plan en taller; el pie imprime 8, la forma "abreviada" §3.3.
    qr_fp = fingerprint[:16]
    short_fp = fingerprint[:8]
    qr_payload = f"DEKOPEN|{order_code}|CUTPACK|{qr_fp}"
    qr_svg = segno.make(qr_payload, error="m").svg_inline(border=2, scale=6)
    bars = [b for b in (optimization.get("bars") or {}).get("workshop_cut_plan") or []
            if isinstance(b, dict)]
    sheets = [s for s in optimization.get("sheets") or [] if isinstance(s, dict)]
    unnested = [u for u in optimization.get("unnested") or [] if isinstance(u, dict)]
    sheet_purchases = [
        p for p in (optimization.get("sheet_purchases") or [])
        if isinstance(p, dict)
    ]
    stats = optimization.get("stats") or {}
    metrics = (optimization.get("bars") or {}).get("metrics") or {}
    generated = _cldate(datetime.now(timezone.utc).isoformat())
    strategy = _value(optimization.get("applied_strategy")
                      or optimization.get("strategy"))

    assignments = _bar_assignments(snapshot, labels, cut_map, bars)
    default_pos = ""
    positions = snapshot.get("positions") or []
    if positions and isinstance(positions[0], dict):
        default_pos = str(positions[0].get("id") or "")
    sheet_assign = _sheet_assignments(
        snapshot, labels, sheets, default_position=default_pos
    )
    parents = _reinforcement_parents(snapshot, labels)
    next_stations, default_station, infill_station = _next_station_map(
        snapshot, payload
    )
    produced = produced_folios or {}
    # Folio RT- por retazo producido, asignado una sola vez: la línea de
    # cierre de la barra y la etiqueta de retazo imprimen el mismo código.
    bar_folio: dict[object, str] = {}
    for bar in bars:
        remainder = _mm(bar.get("remainder_mm") or "0")
        if remainder <= 0 or not bar.get("remainder_reusable"):
            continue
        folio = _next_folio(
            produced,
            ("BAR", str(bar.get("stock_authority_id") or ""), str(remainder)),
        )
        if folio:
            bar_folio[bar.get("bar_index")] = folio
    sheet_folio_produced: dict[tuple[object, int], str] = {}
    for sheet in sheets:
        for index, rem in enumerate(sheet.get("produced_remnants") or []):
            if not isinstance(rem, dict):
                continue
            folio = _next_folio(
                produced,
                ("SHEET", str(sheet.get("workshop_sku") or ""),
                 str(_mm(rem.get("width_mm") or "0")),
                 str(_mm(rem.get("height_mm") or "0"))),
            )
            if folio:
                sheet_folio_produced[(sheet.get("sheet_index"), index)] = folio
    color_label = finish_key_label(optimization.get("color"))

    body = (
        '<div class="titleblock">'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Orden de trabajo</span>'
        f'<span class="tb-value">{escape(order_code)} · Pack de corte</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Huella del plan</span>'
        f'<span class="tb-value">{escape(short_fp)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Emitido</span>'
        f'<span class="tb-value">{escape(generated)}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value pg"></span></div></div>'
        '<main class="workshop">'
        '<div class="masthead"><span class="brand">DEKOPEN<span class="mark">'
        "</span></span>"
        f'<div class="meta"><strong>{escape(order_code)}</strong><br/>'
        'Pack de corte</div></div>'
        '<div class="rule-stack"></div>'
        '<div class="pack-meta">'
        f'<span>Color: <strong>{escape(color_label)}</strong></span>'
        f'<span>Unidades: <strong>{_value(optimization.get("units"))}</strong></span>'
        f'<span>Estrategia: <strong>{escape(strategy)}</strong></span>'
        f'<span>Barras nuevas: <strong>{_value(stats.get("bars_new", metrics.get("bars")))}</strong></span>'
        f'<span>Barras de retazo: <strong>{_value(stats.get("bars_remnant", 0))}</strong></span>'
        f'<span>Cortes: <strong>{_value(stats.get("cuts_total", metrics.get("cuts")))}</strong></span>'
        f'<span>Material útil: <strong>{_fmt_mm(metrics.get("productive_length_mm"))} mm</strong></span>'
        f'<span>Desperdicio de proceso: <strong>{_fmt_mm(metrics.get("process_waste_mm"))} mm</strong></span>'
        f'<span>Retazo recuperable: <strong>{_fmt_mm(metrics.get("reusable_remnant_mm"))} mm</strong></span>'
        f'<span>Sin solución: <strong>{_value(stats.get("unnested_count", len(unnested)))}</strong></span>'
        "</div>"
    )
    if bars:
        body += (
            "<h2>Lista de corte</h2>"
            '<p class="pack-legend">Convenciones — extremo inicial a la '
            "izquierda, alimentación →; ángulos izq/der medidos sobre ese "
            "extremo, visto desde arriba; la marca blanca de esquina indica "
            "extremo ingleteado; disco y despuntes se descontan por barra en "
            "su cierre. La misma etiqueta de pieza va en el CSV, el DXF y la "
            "etiqueta impresa.</p>"
        )
        for bar in bars:
            source = str(bar.get("source") or "NEW")
            remnant_id = str(bar.get("remnant_id") or "")
            rack = remnant_racks.get(remnant_id)
            remnant_folio = _value(bar.get("remnant_code"))
            badge = (
                '<span class="badge badge-remnant">retazo'
                + (f" {escape(remnant_folio)}" if remnant_folio != "—" else "")
                + (f" · rack {escape(rack)}" if rack else "")
                + "</span>"
                if source == "REMNANT"
                else '<span class="badge badge-new">barra nueva</span>'
            )
            sku = _value(bar.get("commercial_sku"))
            meta = bar_meta.get(sku) or {}
            section = _section_svg(meta.get("section"))
            article = str(meta.get("name") or meta.get("article_sku") or "")
            material = _MATERIAL_ES.get(
                str(bar.get("material")), _value(bar.get("material"))
            )
            color = finish_key_label(bar.get("color"))
            stock = _mm(bar.get("stock_length_mm"))
            head_trim = _mm(bar.get("head_trim_mm") or "0")
            tail_trim = _mm(bar.get("tail_trim_mm") or "0")
            remainder = _mm(bar.get("remainder_mm") or "0")
            kerf_total = _mm(bar.get("kerf_total_mm") or "0")
            cuts = [
                c for c in (bar.get("cuts") or []) if isinstance(c, dict)
            ]
            pieces_mm = sum(
                (_mm(c.get("length_mm") or "0") for c in cuts), Decimal("0")
            )
            accounted = pieces_mm + kerf_total + head_trim + tail_trim + remainder
            diff = stock - accounted
            codes = [
                assignments.get(
                    (bar.get("bar_index"), cut.get("sequence")), ("", None)
                )[0]
                for cut in cuts
            ]
            orient_bits: list[str] = []
            if section:
                orient_bits.append(
                    "Sección declarada — "
                    + _ORIENTATION_ES.get(
                        str((meta.get("section") or {}).get("orientation") or ""),
                        "orientación según dibujo",
                    )
                )
            elif meta:
                orient_bits.append("Sin sección declarada.")
            remnant_line = ""
            if remainder > 0:
                if bar.get("remainder_reusable"):
                    folio = bar_folio.get(bar.get("bar_index"))
                    remnant_line = (
                        f"Retazo {_fmt_mm(remainder)} mm → "
                        + (
                            f"{folio} · devolver a stock."
                            if folio
                            else "stock de retazos (folio RT- al cerrar el corte)."
                        )
                    )
                else:
                    remnant_line = (
                        f"Cola {_fmt_mm(remainder)} mm → desecho, no "
                        "retorna a stock."
                    )
            body += (
                '<div class="bar-block">'
                + '<div class="bar-head"><h3>'
                + f"Barra {_value(bar.get('bar_index'))} · "
                f"{escape(sku)}{' — ' + escape(article) if article else ''} · "
                f"{escape(material)} · {escape(color)} · "
                f"{_fmt_mm(stock)} mm</h3>{badge}"
                f'<span class="muted">aprovechamiento '
                f"{_pct(bar.get('yield_pct'))} %</span></div>"
                + (
                    f'<div class="bar-orient">{section}'
                    f'<span class="conv">{escape(" ".join(orient_bits))}</span>'
                    "</div>"
                    if orient_bits
                    else ""
                )
                + _bar_svg(bar, labels, cut_map, codes)
                + '<div class="bar-foot">'
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
                + "</div></div>"
            )
        # Vista agrupada — misma física agrupada por spec para sierras
        # manuales; cada grupo lista las etiquetas exactas que lo componen.
        groups: dict[tuple[object, ...], dict[str, object]] = {}
        for bar in bars:
            for cut in [
                c for c in (bar.get("cuts") or []) if isinstance(c, dict)
            ]:
                key = (
                    str(bar.get("commercial_sku") or ""),
                    _cut_key(cut),
                )
                entry = groups.setdefault(
                    key,
                    {
                        "cut": cut,
                        "sku": str(bar.get("commercial_sku") or ""),
                        "codes": [],
                        "bars": set(),
                        "qty": 0,
                    },
                )
                entry["codes"].append(
                    assignments.get(
                        (bar.get("bar_index"), cut.get("sequence")),
                        ("", None),
                    )[0]
                )
                entry["bars"].add(str(bar.get("bar_index") or ""))
                entry["qty"] += 1
        group_rows = []
        for (sku, _key), entry in groups.items():
            cut = entry["cut"]
            notes = []
            if cut.get("sagitta_mm") not in (None, "", "0", "0.00"):
                notes.append(f"sagitta {_fmt_mm(cut.get('sagitta_mm'))} mm")
            group_rows.append(
                [
                    sku,
                    _fmt_mm(cut.get("length_mm")),
                    f"{_fmt_mm(cut.get('angle_left'))}°",
                    f"{_fmt_mm(cut.get('angle_right'))}°",
                    entry["qty"],
                    _join_codes([c for c in entry["codes"] if c]),
                    ", ".join(sorted(entry["bars"], key=lambda b: int(b or 0))),
                    " · ".join(notes) if notes else "—",
                ]
            )
        group_rows.sort(key=lambda r: (str(r[0]), str(r[1])))
        body += (
            "<h2>Cortes agrupados — sierra manual</h2>"
            '<p class="pack-legend">Cortes idénticos agregados con su '
            "cantidad; cada grupo mantiene la lista exacta de etiquetas — "
            "la trazabilidad no se pierde al agrupar.</p>"
            + _table(
                ["Perfil", "Corte mm", "∠ izq.", "∠ der.", "Cantidad",
                 "Etiquetas", "Barras", "Notas"],
                group_rows,
                ["", "dimension", "dimension", "dimension", "", "", "", ""],
            )
        )
        # Refuerzos y junquillos — la relación a su pieza padre en una sola
        # sección para la mesa de acero y la gualandera.
        detail_rows = []
        for bar in bars:
            for cut in [
                c for c in (bar.get("cuts") or []) if isinstance(c, dict)
            ]:
                kind = str(cut.get("source_kind") or "")
                role = _role_name(cut.get("role"))
                if kind != "REINFORCEMENT" and role != "GLAZING_BEAD":
                    continue
                code, entity_id = assignments.get(
                    (bar.get("bar_index"), cut.get("sequence")), ("", None)
                )
                parent = (
                    parents.get(entity_id, "—")
                    if kind == "REINFORCEMENT"
                    else _location(
                        labels, cut.get("bay_id"), cut.get("leaf_id")
                    )
                )
                detail_rows.append(
                    [
                        code or "—",
                        "Refuerzo" if kind == "REINFORCEMENT" else "Junquillo",
                        parent,
                        _fmt_mm(cut.get("length_mm")),
                        f"{_fmt_mm(cut.get('angle_left'))}°",
                        f"{_fmt_mm(cut.get('angle_right'))}°",
                        f"Barra {_value(bar.get('bar_index'))}",
                    ]
                )
        if detail_rows:
            body += (
                "<h2>Refuerzos y junquillos</h2>"
                + _table(
                    ["Etiqueta", "Tipo", "Pieza padre", "Corte mm",
                     "∠ izq.", "∠ der.", "Barra"],
                    detail_rows,
                    ["", "", "", "dimension", "dimension", "dimension", ""],
                )
            )
    if sheets:
        first = True
        for sheet in sheets:
            # The h2 rides inside the first block — break-after:avoid is
            # unreliable across pages in WeasyPrint, while an inline-level
            # box is atomic by construction.
            sheet_folio = _value(sheet.get("remnant_code"))
            body += (
                '<div class="bar-block">'
                + ("<h2>Plan de láminas</h2>" if first else "")
                + f"<h3>Lámina {_value(sheet.get('sheet_index'))} · "
                f"{escape(_value(sheet.get('purchasing_sku')))} · "
                f"{_fmt_mm(sheet.get('sheet_width_mm'))}×"
                f"{_fmt_mm(sheet.get('sheet_height_mm'))} mm · "
                f"aprovechamiento {_pct(sheet.get('yield_pct'))} %"
                + (
                    f" · retazo {escape(sheet_folio)}"
                    if sheet_folio != "—"
                    else ""
                )
                + "</h3>"
                + _sheet_svg(sheet, labels, infills, sheet_assign)
                + "</div>"
            )
            first = False
    if sheet_purchases:
        body += (
            "<h2>Vidrio / lámina a medida — pedido</h2>"
            '<p class="muted">Comprado al tamaño final; no se corta en '
            "taller.</p>"
            + _table(
                ["Grupo", "Medidas", "Cantidad", "Identidad"],
                [
                    [
                        _value(purchase.get("workshop_sku")
                               or purchase.get("purchasing_sku")
                               or purchase.get("group")),
                        (
                            f"{_fmt_mm(purchase.get('width_mm'))}×"
                            f"{_fmt_mm(purchase.get('height_mm'))} mm"
                        ),
                        _value(purchase.get("quantity") or 1),
                        _value(purchase.get("group_kind") or "—"),
                    ]
                    for purchase in sheet_purchases
                ],
                ["", "dimension", "", ""],
            )
        )
    # Vidrios — mm enteros, composición, cantidad y destino por pieza.
    glass_rows: dict[tuple[str, ...], dict[str, object]] = {}
    infill_dest: dict[object, str] = {}
    for sheet in sheets:
        for piece in [
            p for p in (sheet.get("placements") or []) if isinstance(p, dict)
        ]:
            _c, entity_id = sheet_assign.get(
                (sheet.get("sheet_index"), piece.get("sequence")), ("", None)
            )
            if entity_id is not None:
                infill_dest[entity_id] = (
                    f"Lámina {_value(sheet.get('sheet_index'))}"
                )
    manufacturing = snapshot.get("manufacturing")
    if isinstance(manufacturing, list):
        for fact in manufacturing:
            if not isinstance(fact, dict):
                continue
            for item in fact.get("infills") or []:
                if not isinstance(item, dict):
                    continue
                rect = item.get("rect") or {}
                composition = _value(
                    item.get("technical_sku") or item.get("composition")
                    or item.get("kind")
                )
                key = (
                    str(item.get("position_id") or ""),
                    str(item.get("bay_id") or ""),
                    str(item.get("leaf_id") or ""),
                    str(rect.get("width_mm") or item.get("width_mm") or ""),
                    str(rect.get("height_mm") or item.get("height_mm") or ""),
                    composition,
                )
                entry = glass_rows.setdefault(
                    key,
                    {
                        "codes": [],
                        "dests": set(),
                        "position": labels["position"].get(
                            item.get("position_id"), ""
                        ),
                        "location": _location(
                            labels, item.get("bay_id"), item.get("leaf_id")
                        ),
                        "w": rect.get("width_mm") or item.get("width_mm"),
                        "h": rect.get("height_mm") or item.get("height_mm"),
                        "composition": composition,
                    },
                )
                entry["codes"].append(
                    labels["infill"].get(
                        item.get("infill_id"),
                        str(item.get("infill_id") or "")[:10],
                    )
                )
                dest = infill_dest.get(item.get("infill_id"))
                entry["dests"].add(dest or "Sin ubicar")
    if glass_rows:
        body += (
            "<h2>Vidrios</h2>"
            + _table(
                ["Etiquetas", "Posición", "Vano / hoja", "Medidas mm",
                 "Composición", "Cantidad", "Destino"],
                [
                    [
                        _join_codes(entry["codes"]),
                        entry["position"],
                        entry["location"],
                        f"{_fmt_mm(entry['w'])}×{_fmt_mm(entry['h'])}",
                        entry["composition"],
                        len(entry["codes"]),
                        ", ".join(sorted(entry["dests"])),
                    ]
                    for entry in glass_rows.values()
                ],
                ["", "", "", "dimension", "", "", ""],
            )
        )
    if unnested:
        body += (
            "<h2>Piezas no ubicadas</h2>"
            '<p class="muted">Cada pieza dice qué hacer — el taller no '
            "adivina.</p>"
            + _table(
                ["Pieza", "Grupo", "Medidas", "Motivo → acción"],
                [[infills.get(
                      _infill_key(item),
                      str(item.get("kind") or "") + " · "
                      + _location(labels, item.get("bay_id"), item.get("leaf_id")),
                  ),
                  item.get("group"),
                  f"{_fmt_mm(item.get('width_mm'))}×{_fmt_mm(item.get('height_mm'))}"
                  if item.get("width_mm") else _fmt_mm(item.get("length_mm")),
                  _UNNEST_REASONS.get(str(item.get("reason") or ""),
                                      _value(item.get("reason")))
                  + " → "
                  + _UNNEST_ACTIONS.get(str(item.get("reason") or ""),
                                        "Revisar optimización")]
                 for item in unnested],
                ["", "", "dimension", ""],
            )
        )
    # Etiquetas de pieza — en la secuencia de corte, más las etiquetas de
    # retazo producido. La grilla usa el papel documental de la org; el
    # rollo es 100×50 mm por etiqueta.
    labels_html = _cut_label_rows(
        bars=bars,
        sheets=sheets,
        assignments=assignments,
        sheet_assignments=sheet_assign,
        order_code=order_code,
        fp8=short_fp,
        labels=labels,
        next_station=next_stations,
        default_station=default_station,
        infill_station=infill_station,
        color_label=color_label,
    )
    remnant_labels = []
    for bar in bars:
        remainder = _mm(bar.get("remainder_mm") or "0")
        if remainder <= 0 or not bar.get("remainder_reusable"):
            continue
        folio = bar_folio.get(bar.get("bar_index"))
        sku = _value(bar.get("commercial_sku"))
        remnant_labels.append(
            _piece_label_html(
                code=folio or "RETAZO",
                order_code=order_code,
                fp8=short_fp,
                line1=f"{sku} · {_fmt_mm(remainder)} mm",
                line2=(
                    f"Barra {_value(bar.get('bar_index'))} · {order_code}"
                ),
                next_station="Stock de retazos",
                qr_payload=(
                    f"DEKOPEN|REMNANT|{folio}" if folio else None
                ),
                remnant=True,
            )
        )
    for sheet in sheets:
        for index, rem in enumerate(sheet.get("produced_remnants") or []):
            if not isinstance(rem, dict):
                continue
            folio = sheet_folio_produced.get((sheet.get("sheet_index"), index))
            remnant_labels.append(
                _piece_label_html(
                    code=folio or "RETAZO",
                    order_code=order_code,
                    fp8=short_fp,
                    line1=(
                        f"{_value(sheet.get('workshop_sku'))} · "
                        f"{_fmt_mm(rem.get('width_mm'))}×"
                        f"{_fmt_mm(rem.get('height_mm'))} mm"
                    ),
                    line2=(
                        f"Lámina {_value(sheet.get('sheet_index'))} · "
                        f"{order_code}"
                    ),
                    next_station="Stock de retazos",
                    qr_payload=(
                        f"DEKOPEN|REMNANT|{folio}" if folio else None
                    ),
                    remnant=True,
                )
            )
    if labels_html or remnant_labels:
        if label_format == "THERMAL_100X50":
            # Un título ocuparía una etiqueta entera de 100×50 — el rollo
            # imprime solo etiquetas.
            body += (
                '<section class="label-roll-sheet"><div class="label-roll">'
                + labels_html
                + "".join(remnant_labels)
                + "</div></section>"
            )
        else:
            body += (
                '<section class="labels-sheet">'
                "<h2>Etiquetas de pieza — en secuencia de corte</h2>"
                '<p class="pack-legend">Una etiqueta por pieza física, más '
                "las etiquetas de retazo al final; el QR lleva el código y "
                "la huella del plan.</p>"
                '<div class="labels-grid">'
                + labels_html
                + "".join(remnant_labels)
                + "</div></section>"
            )
    body += (
        f'<h2>Identidad</h2><div class="sign-row"><div class="qr">{qr_svg}</div>'
        '<div class="sign-cell sign-date"><span class="sign-label">Fecha</span></div>'
        '<div class="sign-cell"><span class="sign-label">Operario</span></div>'
        '<div class="sign-cell"><span class="sign-label">Verificado por</span></div>'
        "</div></main>"
    )
    if label_format == "THERMAL_100X50":
        # El cajetín corriente vive en @bottom-center del @page base y los
        # márgenes con nombre heredan margin boxes — hay que anularlo o la
        # franja se imprime encima de la etiqueta.
        extra_css = (
            "@page label-roll { size: 100mm 50mm; margin: 0; "
            "@bottom-center { content: none; } }"
        )
    else:
        paper = _LABEL_PAPER.get(str(label_paper).upper(), "letter")
        extra_css = (
            f"@page piece-labels {{ size: {paper} portrait; margin: 6mm; "
            "@bottom-center { content: element(titleblock); } }}"
        )
    return (
        '<!doctype html><html lang="es-CL"><head><meta charset="utf-8">'
        f"<style>{_CSS}{_CSS_PACK}{extra_css}</style></head><body>{body}</body></html>"
    )


def render_cut_pack(*, org_id: UUID, order_id: UUID) -> tuple[bytes, str]:
    """PDF bytes for the order's current optimization plan; refuses when the
    plan is missing or was invalidated by a newer optimization run."""
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
        labels = _piece_labels({
            **snapshot,
            "manufacturing": snapshot.get("manufacturing")
            if isinstance(snapshot.get("manufacturing"), list)
            else [],
            "positions": snapshot.get("positions")
            if isinstance(snapshot.get("positions"), list)
            else [],
        })
        bars = [
            b
            for b in (optimization.get("bars") or {}).get("workshop_cut_plan")
            or []
            if isinstance(b, dict)
        ]
        remnant_racks = {
            str(entry["id"]): str(entry.get("rack_location") or "")
            for entry in (optimization.get("remnants") or {}).get("consumed")
            or []
            if isinstance(entry, dict) and entry.get("id")
        }
        # Folios RT- de los retazos que el plan produce — se asignan al
        # cerrar el primer paso de corte; si aún no existen la etiqueta
        # lleva su línea de escritura y la barra dice "folio al cerrar".
        produced_folios: dict[tuple[object, ...], list[str]] = {}
        for row in rows(
            "SELECT remnant_code, kind, stock_authority_id::text, "
            "sheet_workshop_sku, length_mm, width_mm, height_mm "
            "FROM public.inventory_remnants "
            "WHERE org_id = %s AND origin_order_id = %s AND origin = 'PRODUCTION' "
            "ORDER BY remnant_code",
            [str(org_id), str(order_id)],
        ):
            if row.get("kind") == "BAR":
                key = (
                    "BAR",
                    str(row.get("stock_authority_id") or ""),
                    str(Decimal(str(row.get("length_mm") or "0"))),
                )
            else:
                key = (
                    "SHEET",
                    str(row.get("sheet_workshop_sku") or ""),
                    str(Decimal(str(row.get("width_mm") or "0"))),
                    str(Decimal(str(row.get("height_mm") or "0"))),
                )
            produced_folios.setdefault(key, []).append(
                str(row.get("remnant_code"))
            )
        org_row = one(
            "SELECT doc_paper_size, workshop_label_format "
            "FROM public.tenancy_organizations WHERE id = %s",
            [str(org_id)],
            "organization_not_found",
        )
        fingerprint = _optimization_fingerprint(optimization)
        html = _pack_html(
            order=order,
            optimization=optimization,
            snapshot=snapshot,
            labels=labels,
            cut_map=_cut_member_map(snapshot, labels),
            infills=_infill_code_map(snapshot, labels),
            bar_meta=_bar_context(org_id, bars),
            remnant_racks=remnant_racks,
            fingerprint=fingerprint,
            produced_folios=produced_folios,
            payload=payload,
            label_format=str(
                org_row.get("workshop_label_format") or "GRID"
            ),
            label_paper=str(org_row.get("doc_paper_size") or "LETTER"),
        )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=f"cut-pack-{order['order_code']}",
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, f"{order['order_code']}-pack-corte.pdf"
