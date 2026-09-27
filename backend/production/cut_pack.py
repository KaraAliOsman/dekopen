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
    _CSS,
    _cldate,
    _cut_key,
    _cut_member_map,
    _infill_code_map,
    _infill_key,
    _location,
    _pct,
    _piece_labels,
    _table,
    _url_fetcher,
    _value,
)
from django.db import transaction

from documents.repository import DocumentaryError, decoded, documentary_backend, one

from production.service import _decoded, _optimization_fingerprint


_CSS_PACK = """
@page { size: letter landscape; margin: 10mm 10mm 16mm;
        @bottom-center { content: element(titleblock); } }
.bar-svg { width: 100%; height: auto; display: block; }
.bar-svg text { font-family: 'IBM Plex Mono', monospace; }
.sheet-svg { display: block; margin: 0 auto; }
.sheet-svg text { font-family: 'IBM Plex Mono', monospace; }
.bar-band { break-inside: avoid; display: inline-block; width: 100%;
            margin-bottom: 6mm; }
.pack-meta { display: flex; gap: 8mm; font: 8pt 'IBM Plex Mono', monospace;
             margin: 2mm 0 4mm; }
.pack-meta strong { color: #161C1F; }
.badge { display: inline-block; padding: 0.4mm 2mm; border-radius: 1mm;
         font-size: 6.5pt; font-weight: 600; letter-spacing: 0.4pt;
         text-transform: uppercase; }
.badge-new { background: #E6F4F2; color: #075F5A; }
.badge-remnant { background: #FDF1E3; color: #B25E09; }
.qr { width: 22mm; height: 22mm; }
"""


def _mm(value: object) -> Decimal:
    return Decimal(str(value))


def _bar_svg(
    bar: dict[str, object],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
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
    # Lanes reach pad_top-16.8u above and pad_top+bar_h+20.8u below — keep
    # padding beyond the deepest lane so the third leader line never clips.
    pad_top = u * Decimal("19")
    pad_bottom = u * Decimal("22")
    height = pad_top + bar_h + pad_bottom
    svg = [
        f'<svg class="bar-svg" viewBox="0 0 {stock} {height}" '
        'preserveAspectRatio="xMinYMid meet" '
        'xmlns="http://www.w3.org/2000/svg">'
    ]

    def _est(text: str, fs: Decimal) -> Decimal:
        return Decimal(len(text)) * fs * Decimal("0.62")

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

    def _cut_label(cut: dict[str, object]) -> str:
        piece_id = str(cut.get("piece_id") or "")
        return cut_map.get(
            _cut_key(cut),
            labels["member"].get(
                piece_id, labels["reinforcement"].get(piece_id, piece_id[:10])
            ),
        )

    x = Decimal("0")
    usable_end = stock - remainder
    # head trim
    if head_trim > 0:
        svg.append(
            f'<rect x="{x}" y="{pad_top}" width="{head_trim}" height="{bar_h}" '
            'fill="#465158" stroke="#161C1F" stroke-width="1"/>'
        )
        if head_trim >= u * Decimal("3"):
            svg.append(
                f'<text x="{x + head_trim / 2}" y="{pad_top + bar_h / 2}" '
                'text-anchor="middle" dominant-baseline="middle" fill="#FCFDFC" '
                f'font-size="{fs_dim}">punta</text>'
            )
        x += head_trim
    for index, cut in enumerate(cuts):
        piece_len = _mm(cut["length_mm"])
        code = _cut_label(cut)
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
            svg.append(
                f'<text x="{center}" y="{pad_top + bar_h + u * Decimal("4.5")}" '
                'text-anchor="middle" fill="#161C1F" '
                f'font-size="{fs_dim}">'
                f'{_value(cut.get("length_mm"))} mm · {angles}</text>'
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
            # Clamp the label inside the piece — a narrow remainder at the
            # right edge otherwise spills past the viewBox.
            label = f"{tag} {_value(remainder)} mm"
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
    # stock baseline
    svg.append(
        f'<line x1="0" y1="{pad_top + bar_h + 6}" x2="{usable_end}" '
        f'y2="{pad_top + bar_h + 6}" stroke="#161C1F" stroke-width="1.5"/>'
    )
    svg.append("</svg>")
    return "".join(svg)


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
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
    infills: dict[tuple[str, str, str], str],
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
    metrics = (optimization.get("bars") or {}).get("metrics") or {}
    generated = _cldate(datetime.now(timezone.utc).isoformat())

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
        f'<span>Color: <strong>{escape(_value(optimization.get("color")))}</strong></span>'
        f'<span>Unidades: <strong>{_value(optimization.get("units"))}</strong></span>'
        f'<span>Estrategia: <strong>{escape(_value(optimization.get("strategy")))}</strong></span>'
        f'<span>Barras: <strong>{_value(metrics.get("bars"))}</strong></span>'
        f'<span>Cortes: <strong>{_value(metrics.get("cuts"))}</strong></span>'
        f'<span>Merma de proceso: <strong>{_value(metrics.get("process_waste_mm"))} mm</strong></span>'
        f'<span>Retazo reutilizable: <strong>{_value(metrics.get("reusable_remnant_mm"))} mm</strong></span>'
        "</div>"
    )
    if bars:
        first = True
        for bar in bars:
            source = str(bar.get("source") or "NEW")
            badge = (
                '<span class="badge badge-remnant">remanente '
                + escape(_value(bar.get("remnant_id")))
                + "</span>"
                if source == "REMNANT"
                else '<span class="badge badge-new">barra nueva</span>'
            )
            body += (
                '<div class="bar-band">'
                + ("<h2>Plan de barras</h2>" if first else "")
                + f"<h3>Barra {_value(bar.get('bar_index'))} · "
                f"{escape(_value(bar.get('commercial_sku')))} · "
                f"{escape(_value(bar.get('material')))} · "
                f"{_value(bar.get('stock_length_mm'))} mm {badge} · "
                f"rendimiento {_pct(bar.get('yield_pct'))}%</h3>"
                + _bar_svg(bar, labels, cut_map)
                + "</div>"
                + _table(
                    ["Sec.", "Pieza", "Posición", "Vano / hoja", "Corte mm", "Ángulos", "Sagitta"],
                    [[cut.get("sequence"),
                      cut_map.get(
                          _cut_key(cut),
                          labels["member"].get(
                              cut.get("piece_id"),
                              labels["reinforcement"].get(
                                  cut.get("piece_id"),
                                  str(cut.get("piece_id") or "")[:10],
                              ),
                          ),
                      ),
                      labels["position"].get(
                          cut.get("source_position_id"),
                          cut.get("source_position_id"),
                      ),
                      _location(labels, cut.get("bay_id"), cut.get("leaf_id")),
                      cut.get("length_mm"),
                      f"{_value(cut.get('angle_left'))}° / {_value(cut.get('angle_right'))}°",
                      _value(cut.get("sagitta_mm"))]
                     for cut in (bar.get("cuts") or [])
                     if isinstance(cut, dict)],
                    ["", "", "", "", "dimension", "", "dimension"],
                )
            )
            first = False
    if sheets:
        first = True
        for sheet in sheets:
            # The h2 rides inside the first band — break-after:avoid is
            # unreliable across pages in WeasyPrint, while an inline-level
            # box is atomic by construction.
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
        fingerprint = _optimization_fingerprint(optimization)
        html = _pack_html(
            order=order,
            optimization=optimization,
            labels=labels,
            cut_map=_cut_member_map(snapshot, labels),
            infills=_infill_code_map(snapshot, labels),
            fingerprint=fingerprint,
        )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=f"cut-pack-{order['order_code']}",
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, f"{order['order_code']}-pack-corte.pdf"
