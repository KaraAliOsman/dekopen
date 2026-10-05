"""§10 workshop cut pack — the printable pack bound to a work order's live
optimization. It re-renders on demand: re-optimizing invalidates the old
plan (and therefore the old pack) so the print always matches authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from uuid import UUID

from documents.renderers import (
    _CATEGORY_ES,
    finish_key_label,
    _CSS,
    _ROLE_ES,
    _cldate,
    _cut_key,
    _cut_member_map,
    _cut_piece_ids,
    _infill_code_map,
    _infill_key,
    _location,
    _member_op_marks,
    _pct,
    _piece_labels,
    _role_name,
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

from production.service import _decoded, _optimization_fingerprint


_CSS_PACK = """
@page { size: letter landscape; margin: 10mm 10mm 16mm;
        @bottom-center { content: element(titleblock); } }
.bar-svg { width: 100%; height: auto; display: block; }
.bar-svg text { font-family: 'IBM Plex Mono', monospace; }
.sheet-svg { display: block; margin: 0 auto; }
.sheet-svg text { font-family: 'IBM Plex Mono', monospace; }
.bar-block { break-inside: avoid; margin-bottom: 3.5mm; }
.bar-block table th { font-size: 7pt; padding: 0.9mm 1.6mm; }
.bar-block table td { font-size: 9.5pt; padding: 1mm 1.6mm; }
.bar-cont th { background: #EEF3F2 !important; color: #465158 !important;
               font-weight: 600; }
.bar-head { display: flex; align-items: baseline; gap: 3mm; margin: 3mm 0 1mm; }
.bar-head h3 { margin: 0; }
.bar-orient { display: flex; gap: 4mm; align-items: center;
              font-size: 8pt; color: #465158; margin: 0 0 1mm; }
.bar-orient .conv { flex: 1; }
.bar-balance { font: 8.5pt 'IBM Plex Mono', monospace; color: #252D31;
               margin: 1mm 0 0; }
.bar-balance.ok { color: #075F5A; }
.bar-balance.diff { color: #991B1B; font-weight: 600; }
.bar-remnant { font-size: 8.5pt; color: #465158; margin-top: 0.6mm; }
.section-svg { width: 16mm; height: 11mm; flex: none; }
.pack-meta { display: flex; flex-wrap: wrap; gap: 4mm 7mm;
             font: 8.5pt 'IBM Plex Mono', monospace; margin: 2mm 0 4mm; }
.pack-meta strong { color: #161C1F; }
.badge { display: inline-block; padding: 0.4mm 2mm; border-radius: 1mm;
         font-size: 7pt; font-weight: 600; letter-spacing: 0.4pt;
         text-transform: uppercase; }
.badge-new { background: #E6F4F2; color: #075F5A; }
.badge-remnant { background: #FDF1E3; color: #B25E09; }
.qr { width: 22mm; height: 22mm; }
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
    """Printed mm without decorative decimals: 6000.00 → '6000',
    1319.50 → '1319.5'. Internal data stays Decimal — only the glyph
    is shortened."""
    text = _value(value)
    if text in ("", "—"):
        return "—"
    try:
        number = Decimal(str(value))
    except Exception:
        return text
    out = format(number.normalize(), "f")
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
    fs_dim = u * Decimal("2.8")
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
            dim_label = f'{_value(cut.get("length_mm"))} mm · {angles}'
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
            label = f"{seq} · {code} · {_value(cut.get('length_mm'))}"
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
            inside_label = f"{tag} {_value(remainder)} mm"
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
                    f'{tag} {escape(_value(remainder))} mm</text>'
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


def _piece_pools(
    piece_ids: dict[tuple[str, ...], dict[str, list[object]]],
    labels: dict[str, dict[object, str]],
) -> dict[tuple[str, ...], dict[str, list[object]]]:
    """spec key → unit → member ids sorted by printed code. The pools are
    consumed across the whole pack — a physical piece prints exactly once,
    per its quantity."""
    pools: dict[tuple[str, ...], dict[str, list[object]]] = {}
    for key, units in piece_ids.items():
        table = labels["member" if key[0] == "PROFILE" else "reinforcement"]
        pools[key] = {
            unit: sorted(
                ids,
                key=lambda entity_id: str(table.get(entity_id) or entity_id),
            )
            for unit, ids in units.items()
        }
    return pools


def _claim_piece(
    cut: dict[str, object],
    pools: dict[tuple[str, ...], dict[str, list[object]]],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
) -> tuple[str, object | None]:
    """Physical piece code for one placed cut: consume the next member id
    of the cut's spec inside its unit (unit_index = frozen repetition_index).
    Falls back to the spec-group label for payloads frozen before the
    identity fields existed."""
    key = _cut_key(cut)
    ids = pools.get(key, {}).get(str(cut.get("unit_index") or "")) or []
    entity_id = ids.pop(0) if ids else None
    table = labels["member" if key[0] == "PROFILE" else "reinforcement"]
    code = table.get(entity_id) if entity_id is not None else None
    if code is None:
        code = cut_map.get(
            key,
            labels["member"].get(
                cut.get("piece_id"),
                labels["reinforcement"].get(
                    cut.get("piece_id"), str(cut.get("piece_id") or "")[:10]
                ),
            ),
        )
    return code, entity_id


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
    "no_declared_sheet": "Sin lámina declarada",
    "piece_larger_than_usable_sheet": "Pieza mayor que la lámina útil",
}


def _sheet_svg(
    sheet: dict[str, object],
    labels: dict[str, dict[object, str]],
    infills: dict[tuple[str, str, str], str],
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
        code = infills.get(_infill_key(placement), str(placement.get("piece_id") or ""))
        rotated = bool(placement.get("rotated"))
        # Print-size labels: a full-height piece earns ~5mm code text; fonts
        # shrink with the smaller piece dimension so narrow panes stay legible.
        fs_code = min(
            h * Decimal("0.075"),
            w * Decimal("0.9") / (Decimal("0.62") * Decimal(max(len(code), 1))),
        )
        fs_dim = fs_code * Decimal("0.8")
        fs_loc = fs_code * Decimal("0.62")
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
            f'{_value(w)}×{_value(h)}</text>'
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
) -> str:
    order_code = _value(order["order_code"])
    short_fp = fingerprint[:16]
    qr_payload = f"DEKOPEN|{order_code}|CUTPACK|{short_fp}"
    import segno

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

    pools = _piece_pools(_cut_piece_ids(snapshot), labels)
    op_marks = _member_op_marks(snapshot)

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
        f'Pack de corte · {escape(short_fp)}</div></div>'
        '<div class="rule-stack"></div>'
        '<div class="pack-meta">'
        f'<span>Color: <strong>{escape(finish_key_label(optimization.get("color")))}</strong></span>'
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
        first = True
        for bar in bars:
            source = str(bar.get("source") or "NEW")
            remnant_id = str(bar.get("remnant_id") or "")
            rack = remnant_racks.get(remnant_id)
            badge = (
                '<span class="badge badge-remnant">retazo RET-'
                + escape(remnant_id[:8].upper())
                + (f" · rack {escape(rack)}" if rack else "")
                + "</span>"
                if source == "REMNANT"
                else '<span class="badge badge-new">barra nueva</span>'
            )
            sku = _value(bar.get("commercial_sku"))
            meta = bar_meta.get(sku) or {}
            section = _section_svg(meta.get("section"))
            article = _value(meta.get("name")) or _value(meta.get("article_sku"))
            material = _MATERIAL_ES.get(
                str(bar.get("material")), _value(bar.get("material"))
            )
            color = finish_key_label(bar.get("color"))
            stock = _mm(bar.get("stock_length_mm"))
            kerf = _mm(bar.get("kerf_mm") or "0")
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
            codes: list[str] = []
            rows_data: list[list[object]] = []
            for index, cut in enumerate(cuts):
                code, entity_id = _claim_piece(cut, pools, labels, cut_map)
                codes.append(code)
                notes = []
                if cut.get("sagitta_mm") not in (None, "", "0", "0.00"):
                    notes.append(f"sagitta {_fmt_mm(cut.get('sagitta_mm'))} mm")
                if entity_id is not None and op_marks.get(str(entity_id)):
                    notes.append("lleva mecanizado")
                function = " · ".join(
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
                )
                rows_data.append(
                    [
                        cut.get("sequence") or index + 1,
                        code,
                        function,
                        _location(labels, cut.get("bay_id"), cut.get("leaf_id")),
                        _fmt_mm(cut.get("length_mm")),
                        f"{_fmt_mm(cut.get('angle_left'))}°",
                        f"{_fmt_mm(cut.get('angle_right'))}°",
                        " · ".join(notes) if notes else "—",
                    ]
                )
            convention = (
                "Extremo inicial a la izquierda; alimentación →. "
                "Ángulos izq/der medidos sobre ese extremo, visto desde "
                "arriba; marca de esquina = extremo ingleteado. "
                f"Disco {_fmt_mm(kerf)} mm · despuntes "
                f"{_fmt_mm(head_trim)}/{_fmt_mm(tail_trim)} mm."
            )
            orient_bits = [convention]
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
                    remnant_line = (
                        f"Retazo {_fmt_mm(remainder)} mm recuperable — "
                        "etiquetar y devolver a stock."
                    )
                else:
                    remnant_line = (
                        f"Cola {_fmt_mm(remainder)} mm — desecho, no "
                        "retorna a stock."
                    )
            body += (
                '<div class="bar-block">'
                + ("<h2>Plan de barras</h2>" if first else "")
                + '<div class="bar-head"><h3>'
                + f"Barra {_value(bar.get('bar_index'))} · "
                f"{escape(sku)}{' — ' + escape(article) if article else ''} · "
                f"{escape(material)} · {escape(color)} · "
                f"{_fmt_mm(stock)} mm</h3>{badge}"
                f'<span class="muted">aprovechamiento '
                f"{_pct(bar.get('yield_pct'))}%</span></div>"
                + f'<div class="bar-orient">{section}'
                f'<span class="conv">{escape(" ".join(orient_bits))}</span>'
                "</div>"
                + _bar_svg(bar, labels, cut_map, codes)
                + _table(
                    ["Sec.", "Pieza", "Función", "Vano / hoja", "Corte mm",
                     "∠ izq.", "∠ der.", "Obs."],
                    rows_data,
                    ["", "", "", "", "dimension", "dimension", "dimension", ""],
                    thead_extra=(
                        f'<tr class="bar-cont"><th colspan="8">Tabla de cortes — '
                        f"Barra {_value(bar.get('bar_index'))} · "
                        f"{escape(sku)}</th></tr>"
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
    if sheets:
        first = True
        for sheet in sheets:
            # The h2 rides inside the first block — break-after:avoid is
            # unreliable across pages in WeasyPrint, while an inline-level
            # box is atomic by construction.
            body += (
                '<div class="bar-block">'
                + ("<h2>Plan de láminas</h2>" if first else "")
                + f"<h3>Lámina {_value(sheet.get('sheet_index'))} · "
                f"{escape(_value(sheet.get('purchasing_sku')))} · "
                f"{_fmt_mm(sheet.get('sheet_width_mm'))}×"
                f"{_fmt_mm(sheet.get('sheet_height_mm'))} mm · "
                f"aprovechamiento {_pct(sheet.get('yield_pct'))}%</h3>"
                + _sheet_svg(sheet, labels, infills)
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
    if unnested:
        body += (
            "<h2>Piezas no ubicadas</h2>"
            + _table(
                ["Pieza", "Grupo", "Medidas", "Motivo"],
                [[infills.get(
                      _infill_key(item),
                      str(item.get("kind") or "") + " · "
                      + _location(labels, item.get("bay_id"), item.get("leaf_id")),
                  ),
                  item.get("group"),
                  f"{_value(item.get('width_mm'))}×{_value(item.get('height_mm'))}"
                  if item.get("width_mm") else _value(item.get("length_mm")),
                  _UNNEST_REASONS.get(str(item.get("reason") or ""),
                                      _value(item.get("reason")))]
                 for item in unnested],
                ["", "", "dimension", ""],
            )
        )
    body += (
        f'<h2>Identidad</h2><div class="sign-row"><div class="qr">{qr_svg}</div>'
        '<div class="sign-cell sign-date"><span class="sign-label">Fecha</span></div>'
        '<div class="sign-cell"><span class="sign-label">Operario</span></div>'
        '<div class="sign-cell"><span class="sign-label">Verificado por</span></div>'
        f"</div><p class=\"muted\">Huella completa: {escape(fingerprint)}</p></main>"
    )
    return (
        '<!doctype html><html lang="es-CL"><head><meta charset="utf-8">'
        f"<style>{_CSS}{_CSS_PACK}</style></head><body>{body}</body></html>"
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
        )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=f"cut-pack-{order['order_code']}",
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, f"{order['order_code']}-pack-corte.pdf"
