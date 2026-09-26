"""Frozen-authority PDF producers for DOC-01, DOC-03 through DOC-07."""

from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal
from html import escape
from pathlib import Path

from dekopen_engine.contour import Contour, contour_points
from dekopen_engine.models import PlanPoint
from dekopen_engine.product import ElevationMember, elevation_layout
from documents.repository import DocumentaryError
from engine_api.adapter import parse_product_model

_PDF_MEDIA = "application/pdf"
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

# DEKOPEN document language — teal/graphite tokens from the visual-identity
# study: #075F5A teal-800, #0B7770 teal-700, #E6F4F2 teal-50, graphite ramp
# #161C1F..#FCFDFC, Plex Sans + Plex Mono, hairline rules instead of tinted
# boxes, ISO-7200-style title block in the bottom margin.
_TEAL_800 = "#075F5A"
_TEAL_700 = "#0B7770"
_TEAL_50 = "#E6F4F2"
_G_950 = "#161C1F"
_G_800 = "#252D31"
_G_700 = "#465158"
_G_500 = "#727D82"
_G_300 = "#CDD5D6"
_G_50 = "#F5F7F6"
_PAPER = "#FCFDFC"
_MARK = "#E56A32"
_DANGER = "#991B1B"


def _font_face(family: str, weight: int, filename: str) -> str:
    uri = (_FONTS_DIR / filename).as_uri()
    return (
        "@font-face {"
        f" font-family: '{family}'; font-style: normal; font-weight: {weight};"
        f" src: url('{uri}') format('truetype');"
        " }"
    )


_FONTS = "".join(
    [
        _font_face("IBM Plex Sans", 400, "IBMPlexSans-400.ttf"),
        _font_face("IBM Plex Sans", 500, "IBMPlexSans-500.ttf"),
        _font_face("IBM Plex Sans", 600, "IBMPlexSans-600.ttf"),
        _font_face("IBM Plex Sans", 700, "IBMPlexSans-700.ttf"),
        _font_face("IBM Plex Mono", 400, "IBMPlexMono-400.ttf"),
        _font_face("IBM Plex Mono", 500, "IBMPlexMono-500.ttf"),
    ]
)

_CSS = _FONTS + """
@page { size: letter portrait; margin: 13mm 12mm 22mm; @bottom-center { content: element(titleblock); } }
* { box-sizing: border-box; } body { color: #161C1F; font: 9.5pt 'IBM Plex Sans', sans-serif; margin: 0; }
.titleblock { position: running(titleblock); display: table; width: 100%; border-collapse: collapse; border-top: 1.5pt solid #075F5A; font-family: 'IBM Plex Mono', monospace; }
.titleblock .tb-cell { display: table-cell; border-left: 0.5pt solid #CDD5D6; border-bottom: 0.5pt solid #CDD5D6; padding: 1.2mm 2mm; vertical-align: top; }
.titleblock .tb-cell:first-child { border-left: none; padding-left: 0; }
.titleblock .tb-wide { width: 34%; }
.tb-label { display: block; font: 6.5pt 'IBM Plex Sans', sans-serif; text-transform: uppercase; letter-spacing: 0.5pt; color: #727D82; margin-bottom: 0.6mm; }
.tb-value { display: block; font: 8pt 'IBM Plex Mono', monospace; color: #252D31; overflow-wrap: anywhere; }
.pg::after { content: counter(page) " / " counter(pages); }
h1 { font-size: 16pt; font-weight: 600; margin: 0 0 4mm; letter-spacing: -0.2pt; color: #161C1F; }
h2 { font-size: 11pt; font-weight: 600; margin: 5mm 0 2mm; border-bottom: 0.75pt solid #465158; padding-bottom: 1.2mm; color: #161C1F; }
h3 { font-size: 9.5pt; font-weight: 600; margin: 4mm 0 1.5mm; color: #252D31; } p { margin: 1.5mm 0; orphans: 3; widows: 3; }
.masthead { position: relative; display: flex; justify-content: space-between; padding-bottom: 4mm; margin-bottom: 1.6mm; }
.brand { color: #075F5A; font-weight: 600; font-size: 12pt; letter-spacing: 2.4pt; }
.brand .mark { display: inline-block; width: 2.4mm; height: 2.4mm; background: #E56A32; margin-left: 1.6mm; }
.brand-logo { display: block; max-height: 12mm; max-width: 48mm; }
.brand-sub { font-size: 6.5pt; color: #727D82; letter-spacing: 0.9pt; margin-top: 1.2mm; }
.meta { text-align: right; color: #727D82; font: 8pt 'IBM Plex Mono', monospace; padding-right: 11mm; }
.meta strong { color: #252D31; font-weight: 500; }
.rule-stack { border-top: 1.5pt solid #075F5A; border-bottom: 0.5pt solid #CDD5D6; height: 1.2mm; margin-bottom: 6mm; }
.miter { position: absolute; top: 0; right: 0; width: 8mm; height: 8mm; }
.hero { position: relative; background: #E6F4F2; border-left: 3px solid #0B7770; padding: 3mm 5mm; margin: 2.5mm 0 4mm; }
.hero p { color: #465158; } .total { font-size: 14pt; font-weight: 600; color: #075F5A; }
table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm; table-layout: fixed; }
thead { border-top: 0.9pt solid #465158; }
th { color: #465158; font: 6.5pt 'IBM Plex Sans', sans-serif; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5pt; text-align: left; border-bottom: 0.9pt solid #465158; padding: 1.4mm 1.8mm; }
td { border-bottom: 0.5pt solid #CDD5D6; padding: 1.6mm 1.8mm; vertical-align: top; overflow-wrap: break-word; hyphens: manual; orphans: 2; widows: 2; }
tbody tr:last-child td { border-bottom: 0.9pt solid #465158; }
.workshop h1 { font-size: 14pt; } .workshop th { background: #252D31; color: #FCFDFC; }
.dimension { font: 11pt 'IBM Plex Mono', monospace; font-weight: 500; color: #161C1F; }
.hash { font: 6.5pt 'IBM Plex Mono', monospace; color: #465158; overflow-wrap: anywhere; }
.break-avoid { break-inside: avoid; } h2, h3 { break-after: avoid; } .blank { display: inline-block; width: 5mm; height: 5mm; border: 1px solid #252D31; vertical-align: middle; }
.confidential { color: #991B1B; font-weight: 600; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.8pt; }
.voided-banner { border: 1.5pt solid #991B1B; color: #991B1B; padding: 3mm 5mm; margin: 3mm 0; break-inside: avoid; }
.voided-banner p { margin: 0; } .voided-title { font-size: 16pt; font-weight: 700; letter-spacing: 2pt; margin-bottom: 1.5mm; }
.muted { color: #727D82; } .signature { height: 15mm; border-bottom: 0.5pt solid #465158; margin-top: 6mm; }
.signoff { break-inside: avoid; }
.keep { break-inside: avoid; }
.sign-row { display: flex; gap: 8mm; margin-top: 4mm; margin-bottom: 4mm; }
.sign-cell { flex: 1; height: 10mm; border-bottom: 0.5pt solid #465158; position: relative; }
.sign-cell.sign-date { flex: 0 0 22mm; }
.sign-label { position: absolute; bottom: -4.5mm; left: 0; font: 600 6pt 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: 0.08em; color: #727D82; }
table tr { break-inside: avoid; }
.sol-table td.dimension, table td.dimension { text-align: right; white-space: nowrap; }
.nowrap { white-space: nowrap; }
svg:not(.miter) { max-width: 100%; height: auto; display: block; } svg text { font-family: 'IBM Plex Mono', monospace; }
.figures { display: flex; flex-wrap: wrap; gap: 4mm; margin: 2mm 0 4mm; }
.figures figure { margin: 0; width: 46mm; break-inside: avoid; }
/* Extreme-aspect openings (500×2300) at fixed width would render taller than
   the page and bleed through the footer — cap the drawable height. */
.figures svg { max-height: 190mm; }
.figures figcaption { color: #4A5559; font-size: 7pt; line-height: 1.45; margin-top: 1mm; }
.figures .figpos { color: #161C1F; font-weight: 600; }
.figures .figdim { font-family: 'IBM Plex Mono', monospace; font-size: 7.5pt; }
.workshop-figure svg { max-height: 170mm; }
"""


def _object(value: object, code: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DocumentaryError(code)
    return value


def _array(value: object, code: str) -> list[object]:
    if not isinstance(value, list):
        raise DocumentaryError(code)
    return value


def _value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, (str, int)):
        return str(value)
    if isinstance(value, float):
        raise DocumentaryError("pdf_float_authority_forbidden")
    raise DocumentaryError("pdf_value_not_scalar")


def _cell(value: object, class_name: str = "") -> str:
    css = f' class="{escape(class_name)}"' if class_name else ""
    return f"<td{css}>{escape(_value(value))}</td>"


def _row(values: list[object], classes: list[str] | None = None) -> str:
    styles = classes or [""] * len(values)
    return "<tr>" + "".join(_cell(value, styles[index]) for index, value in enumerate(values)) + "</tr>"


def _table(headers: list[str], rows: list[list[object]], classes: list[str] | None = None) -> str:
    head = "<tr>" + "".join(f"<th>{escape(header)}</th>" for header in headers) + "</tr>"
    return "<table><thead>" + head + "</thead><tbody>" + "".join(
        _row(row, classes) for row in rows
    ) + "</tbody></table>"


def _url_fetcher(url: str, *args: object, **kwargs: object) -> object:
    """Frozen-authority fetcher: only the bundled Plex TTFs may load.

    Every other URL — remote or local — is denied so emitted documents can
    never exfiltrate or depend on network state.
    """
    if url.startswith("data:"):
        # Embedded bytes we generated server-side (e.g. a sealed signature
        # PNG) — no fetch happens, so the frozen-authority contract holds.
        from weasyprint import URLFetcher

        return URLFetcher(allowed_protocols={"data"}).fetch(url)
    if url.startswith("file://"):
        target = Path(url.removeprefix("file://")).resolve()
        if target.parent == _FONTS_DIR and target.suffix == ".ttf":
            from weasyprint import URLFetcher

            return URLFetcher(allowed_protocols={"file"}).fetch(url)
    raise DocumentaryError(f"External PDF resource forbidden: {url}")


_MITER = (
    '<svg class="miter" width="8mm" height="8mm" viewBox="0 0 32 32" '
    'xmlns="http://www.w3.org/2000/svg">'
    f'<path d="M0,0 L32,0 L32,32 Z" fill="{_PAPER}" stroke="{_TEAL_800}" '
    'stroke-width="2"/></svg>'
)


_LOGO_MAX_BYTES = 512 * 1024
_LOGO_MAGICS = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",
}


def _logo_uri(organization: dict | None) -> str | None:
    """Embed the frozen brand logo as a data URI when its stored sha pins the
    bytes — a document never fails (or changes identity) over a logo, so any
    storage or integrity failure renders the plain brand name instead."""
    if not isinstance(organization, dict):
        return None
    object_key = _value(organization.get("brand_logo_key"))
    expected = _value(organization.get("brand_logo_sha256"))
    if object_key == "—" or expected == "—":
        return None
    try:
        from documents.storage import SupabaseDocumentStorage

        content = SupabaseDocumentStorage().download_bounded(
            object_key, _LOGO_MAX_BYTES
        )
    except Exception:
        return None
    if not content or hashlib.sha256(content).hexdigest() != expected:
        return None
    media = None
    if content.startswith(b"RIFF") and len(content) > 11 and content[8:12] == b"WEBP":
        media = "image/webp"
    else:
        for magic, kind in _LOGO_MAGICS.items():
            if content.startswith(magic):
                media = kind
                break
    if media is None:
        return None
    return f"data:{media};base64,{base64.b64encode(content).decode('ascii')}"


def _brand_block(organization: dict | None) -> str:
    """White-label masthead brand: the org's logo or commercial name leads;
    'Generado con DEKOPEN' stays as the discreet tool attribution. A snapshot
    frozen before branding renders the bare DEKOPEN wordmark."""
    org = organization if isinstance(organization, dict) else {}
    uri = _logo_uri(org)
    if uri:
        brand = f'<img class="brand-logo" src="{uri}" alt="">'
    else:
        label = (
            _value(org.get("commercial_name"))
            if _value(org.get("commercial_name")) != "—"
            else _value(org.get("name"))
        )
        if label == "—":
            label = "DEKOPEN"
            brand = f'<div class="brand">{label}<span class="mark"></span></div>'
        else:
            brand = f'<div class="brand">{escape(label)}</div>'
    attribution = (
        '<div class="brand-sub">Generado con DEKOPEN</div>'
        if isinstance(organization, dict) and organization.get("name")
        else ""
    )
    return f"<div>{brand}{attribution}</div>"


_SVG_INSET = Decimal("0.06")


def _money(amount: object, currency: object) -> str:
    value = _num(amount)
    code = _value(currency)
    if code == "CLP":
        grouped = f"{value:,.0f}".replace(",", ".")
        return f"$\u00a0{grouped}"
    return f"{code}\u00a0{value:,.2f}"


def _cldate(raw: object) -> str:
    text = _value(raw)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}-{text[5:7]}-{text[0:4]}"
    return text[:10]



def _num(value: object) -> Decimal:
    if isinstance(value, bool):
        raise DocumentaryError("svg_dimension_invalid")
    if isinstance(value, (Decimal, int)):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except ArithmeticError:
            raise DocumentaryError("svg_dimension_invalid") from None
    raise DocumentaryError("svg_dimension_invalid")


def _pt(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _svg_elements(node: dict[str, object], x: Decimal, y: Decimal,
                  width: Decimal, height: Decimal, out: list[str],
                  marker: str, glyph_only: bool = False) -> None:
    node_type = str(node.get("type"))
    children = node.get("children")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise DocumentaryError("invalid_frozen_parametric_tree")
    if node_type == "ROOT":
        if len(children) != 1 or not isinstance(children[0], dict):
            raise DocumentaryError("invalid_frozen_parametric_tree")
        _svg_elements(children[0], x, y, width, height, out, marker, glyph_only)
        return
    if node_type in ("SPLIT_V", "SPLIT_H"):
        offset = node.get("split_offset_mm")
        if offset is None or len(children) != 2:
            raise DocumentaryError("invalid_frozen_parametric_tree")
        split = _num(offset)
        first, second = children
        if not isinstance(first, dict) or not isinstance(second, dict):
            raise DocumentaryError("invalid_frozen_parametric_tree")
        if node_type == "SPLIT_V":
            out.append(
                f'<line x1="{_pt(x + split)}" y1="{_pt(y)}" x2="{_pt(x + split)}" '
                f'y2="{_pt(y + height)}" stroke="#465158" stroke-width="'
                f'{_pt(height / Decimal("60"))}"/>'
            )
            _svg_elements(first, x, y, split, height, out, marker, glyph_only)
            _svg_elements(second, x + split, y, width - split, height, out, marker, glyph_only)
        else:
            out.append(
                f'<line x1="{_pt(x)}" y1="{_pt(y + split)}" x2="{_pt(x + width)}" '
                f'y2="{_pt(y + split)}" stroke="#465158" stroke-width="'
                f'{_pt(width / Decimal("60"))}"/>'
            )
            _svg_elements(first, x, y, width, split, out, marker, glyph_only)
            _svg_elements(second, x, y + split, width, height - split, out, marker, glyph_only)
        return
    if node_type != "BAY":
        raise DocumentaryError("invalid_frozen_parametric_tree")
    inset_x = width * _SVG_INSET
    inset_y = height * _SVG_INSET
    ix, iy = x + inset_x, y + inset_y
    iw, ih = width - inset_x * 2, height - inset_y * 2
    stroke = _pt(min(width, height) / Decimal("120"))
    if not glyph_only:
        out.append(
            f'<rect x="{_pt(x)}" y="{_pt(y)}" width="{_pt(width)}" height="{_pt(height)}" '
            'fill="none" stroke="#075F5A" stroke-width="' + _pt(min(width, height) / Decimal("40"))
            + '"/>'
        )
        out.append(
            f'<rect x="{_pt(ix)}" y="{_pt(iy)}" width="{_pt(iw)}" height="{_pt(ih)}" '
            f'fill="#E6F4F2" stroke="#075F5A" stroke-width="{stroke}"/>'
        )
    opening = node.get("opening_type")
    mx, my = ix + iw / 2, iy + ih / 2
    if opening in ("TURN_LEFT", "TILT_TURN_LEFT"):
        out.append(
            f'<polygon points="{_pt(ix)},{_pt(iy)} {_pt(ix)},{_pt(iy + ih)} '
            f'{_pt(ix + iw)},{_pt(my)}" fill="none" stroke="#075F5A" '
            f'stroke-width="{stroke}"/>'
        )
    elif opening in ("TURN_RIGHT", "TILT_TURN_RIGHT"):
        out.append(
            f'<polygon points="{_pt(ix + iw)},{_pt(iy)} {_pt(ix + iw)},{_pt(iy + ih)} '
            f'{_pt(ix)},{_pt(my)}" fill="none" stroke="#075F5A" '
            f'stroke-width="{stroke}"/>'
        )
    if opening in ("TILT_TURN_LEFT", "TILT_TURN_RIGHT"):
        out.append(
            f'<polygon points="{_pt(ix)},{_pt(iy + ih)} {_pt(ix + iw)},{_pt(iy + ih)} '
            f'{_pt(mx)},{_pt(iy)}" fill="none" stroke="#075F5A" stroke-width="{stroke}"/>'
        )
    elif opening == "AWNING":
        out.append(
            f'<polygon points="{_pt(ix)},{_pt(iy)} {_pt(ix + iw)},{_pt(iy)} '
            f'{_pt(mx)},{_pt(iy + ih)}" fill="none" stroke="#075F5A" '
            f'stroke-width="{stroke}"/>'
        )
    elif opening in ("SLIDING_2L", "SLIDING_3L", "SLIDING_4L", "SLIDING"):
        layout = node.get("sliding_layout")
        layout_panels = (
            layout.get("panels")
            if isinstance(layout, dict) and isinstance(layout.get("panels"), list)
            and layout["panels"] else None
        )
        if layout_panels is None:
            leaf_count = {"SLIDING_2L": 2, "SLIDING_3L": 3, "SLIDING_4L": 4}.get(
                str(opening), 2
            )
            layout_panels = [{"kind": "MOVING"} for _ in range(leaf_count)]
        leaf_w = iw / len(layout_panels)
        for index, panel in enumerate(layout_panels):
            lx = ix + leaf_w * index
            out.append(
                f'<rect x="{_pt(lx)}" y="{_pt(iy)}" width="{_pt(leaf_w)}" '
                f'height="{_pt(ih)}" fill="none" stroke="#075F5A" '
                f'stroke-width="{stroke}"/>'
            )
            if not isinstance(panel, dict) or panel.get("kind") == "MOVING":
                out.append(
                    f'<line x1="{_pt(lx + leaf_w / 4)}" y1="{_pt(my)}" '
                    f'x2="{_pt(lx + leaf_w * 3 / 4)}" y2="{_pt(my)}" stroke="#075F5A" '
                    f'stroke-width="{stroke}" marker-end="url(#{marker})"/>'
                )
    elif opening in ("DOOR_ENTRY", "DOOR_DOUBLE"):
        out.append(
            f'<line x1="{_pt(ix)}" y1="{_pt(iy + ih)}" x2="{_pt(ix + iw)}" '
            f'y2="{_pt(iy + ih)}" stroke="#E56A32" stroke-width="{stroke}"/>'
        )
        if opening == "DOOR_DOUBLE":
            out.append(
                f'<line x1="{_pt(mx)}" y1="{_pt(iy)}" x2="{_pt(mx)}" '
                f'y2="{_pt(iy + ih)}" stroke="#075F5A" stroke-width="{stroke}"/>'
            )


def _frameless_pane(frameless: dict[str, object], x: Decimal, y: Decimal,
                    width: Decimal, height: Decimal, out: list[str]) -> None:
    """Glass-only module figure: the pane itself plus its DECLARED edge
    supports — no fake frame, no invented fitting positions."""
    stroke = _pt(min(width, height) / Decimal("140"))
    support_stroke = _pt(min(width, height) / Decimal("30"))
    out.append(
        f'<rect x="{_pt(x)}" y="{_pt(y)}" width="{_pt(width)}" height="{_pt(height)}" '
        f'fill="#E6F4F2" stroke="#075F5A" stroke-width="{stroke}"/>'
    )
    segments = {
        "top": (x, y, x + width, y),
        "bottom": (x, y + height, x + width, y + height),
        "left": (x, y, x, y + height),
        "right": (x + width, y, x + width, y + height),
    }
    for raw in _array(frameless.get("supports"), "invalid_frozen_parametric_tree"):
        support = _object(raw, "invalid_frozen_parametric_tree")
        edge = segments.get(str(support.get("edge")))
        if edge is None:
            continue
        x1, y1, x2, y2 = edge
        mx1 = x1 + (x2 - x1) / Decimal("4")
        my1 = y1 + (y2 - y1) / Decimal("4")
        mx2 = x2 - (x2 - x1) / Decimal("4")
        my2 = y2 - (y2 - y1) / Decimal("4")
        out.append(
            f'<line x1="{_pt(mx1)}" y1="{_pt(my1)}" x2="{_pt(mx2)}" '
            f'y2="{_pt(my2)}" stroke="#E56A32" stroke-width="{support_stroke}"/>'
        )
    fittings = _array(frameless.get("fittings"), "invalid_frozen_parametric_tree")
    if fittings:
        out.append(
            f'<text x="{_pt(x + width / Decimal("6"))}" '
            f'y="{_pt(y + height / Decimal("6"))}" '
            f'font-size="{_pt(min(width, height) / Decimal("12"))}" '
            f'fill="#465158">+{len(fittings)}</text>'
        )


def _contour_svg_path(
    contour_payload: object,
) -> tuple[str, Decimal, Decimal, Decimal, Decimal]:
    """Sampled SVG `d` for a stored module contour, plus its sampled extrema.

    The boundary comes from the engine's own sampler (vertices exact, arcs
    chord-sampled), so issued documents render the same shape the geometry
    evaluated — never a bounding-box stand-in. Returns (path_d, top, bottom,
    left, right) — the sampled bounds in module-local coordinates. An arc
    can overshoot the vertex box on any side, so the caller must bound the
    viewBox from these extrema, not the nominal dims."""
    raw = _object(contour_payload, "invalid_frozen_parametric_tree")
    vertices = [
        PlanPoint(
            x_mm=_num(_object(point, "invalid_frozen_parametric_tree").get("x_mm")),
            y_mm=_num(_object(point, "invalid_frozen_parametric_tree").get("y_mm")),
        )
        for point in _array(raw.get("vertices"), "invalid_frozen_parametric_tree")
    ]
    bulges = [
        None if bulge is None else _num(bulge)
        for bulge in _array(raw.get("bulges"), "invalid_frozen_parametric_tree")
    ]
    try:
        points = contour_points(Contour(vertices=vertices, bulges=bulges))
    except ValueError as error:
        raise DocumentaryError("svg_dimension_invalid") from error
    if not points:
        raise DocumentaryError("svg_dimension_invalid")
    top = max(point.y_mm for point in points)
    bottom = min(point.y_mm for point in points)
    left = min(point.x_mm for point in points)
    right = max(point.x_mm for point in points)
    commands = [
        f"{'M' if index == 0 else 'L'}{_pt(point.x_mm)},{_pt(top - point.y_mm)}"
        for index, point in enumerate(points)
    ]
    return " ".join(commands) + " Z", top, bottom, left, right


def _position_svg(position: dict[str, object]) -> str:
    tree = _object(position.get("parametric_tree"), "invalid_frozen_parametric_tree")
    marker = f"arrow-{escape(_value(position.get('position_index')))}"
    elements: list[str] = [
        f'<defs><marker id="{marker}" markerWidth="8" markerHeight="8" refX="6" refY="3" '
        'orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#075F5A" '
        'stroke-width="1"/></marker></defs>'
    ]
    if tree.get("version") == "product-v2":
        assembly = _object(tree.get("assembly"), "invalid_frozen_parametric_tree")
        modules = [
            _object(module, "invalid_frozen_parametric_tree")
            for module in _array(assembly.get("modules"), "invalid_frozen_parametric_tree")
        ]
        # The front elevation comes from the engine's layout: front columns
        # advance left→right, STACKED members sit above their column root,
        # and joints are typed (INLINE seams vertical, STACKED contacts
        # horizontal) — never the side-by-side declaration order.
        try:
            layout = elevation_layout(parse_product_model(tree).assembly)
        except (ValueError, KeyError, DocumentaryError) as error:
            raise DocumentaryError("invalid_frozen_parametric_tree") from error
        modules_by_id = {str(module.get("id")): module for module in modules}

        # A contour may overshoot its nominal box (an arch rises above it; a
        # down-swinging arc dips below). Members on one column share the
        # column's baseline; every column still shares ONE sill line.
        draws: list[
            tuple[dict[str, object], ElevationMember, Decimal, Decimal, Decimal, str | None]
        ] = []
        top_edge = Decimal("0")
        bottom_edge = Decimal("0")
        left_edge = Decimal("0")
        right_edge = Decimal("0")
        for index, member in enumerate(layout.members):
            module = modules_by_id.get(member.module_id)
            if module is None:
                raise DocumentaryError("invalid_frozen_parametric_tree")
            if member.width_mm <= 0 or member.height_mm <= 0:
                raise DocumentaryError("svg_dimension_invalid")
            path_d: str | None = None
            member_top = member.height_mm
            member_bottom = Decimal("0")
            member_left = member.x_mm
            member_right = member.x_mm + member.width_mm
            contour_payload = module.get("contour")
            if contour_payload is not None:
                path_d, ctop, cbottom, cleft, cright = _contour_svg_path(contour_payload)
                member_top = ctop
                member_bottom = cbottom
                member_left = member.x_mm + cleft
                member_right = member.x_mm + cright
            draws.append(
                (module, member, member.width_mm, member.height_mm, member_top, path_d)
            )
            top_edge = max(top_edge, member.sill_mm + member_top)
            bottom_edge = min(bottom_edge, member.sill_mm + member_bottom)
            left_edge = member_left if index == 0 else min(left_edge, member_left)
            right_edge = member_right if index == 0 else max(right_edge, member_right)
        height = top_edge - bottom_edge
        width = right_edge - left_edge if layout.members else Decimal("0")

        for module, member, module_width, module_height, member_top, path_d in draws:
            x = member.x_mm - left_edge
            baseline = top_edge - (member.sill_mm + member_top)
            frameless = module.get("frameless")
            if path_d is not None:
                stroke = module_width / Decimal("150")
                elements.append(
                    f'<g transform="translate({_pt(x)} {_pt(baseline)})">'
                    f'<path d="{path_d}" fill="none" stroke="#252D31" '
                    f'stroke-width="{_pt(stroke)}"/></g>'
                )
                # A contour module still has opening semantics — draw its
                # glyphs inside the bounding box, just not the frame rects.
                _svg_elements(
                    _object(module.get("tree"), "invalid_frozen_parametric_tree"),
                    x, baseline, module_width, module_height, elements, marker,
                    glyph_only=True,
                )
            elif frameless is not None:
                _frameless_pane(
                    _object(frameless, "invalid_frozen_parametric_tree"),
                    x, baseline, module_width, module_height, elements,
                )
            else:
                _svg_elements(
                    _object(module.get("tree"), "invalid_frozen_parametric_tree"),
                    x, baseline, module_width, module_height, elements, marker,
                )
            # Module-id labels drop on sliver modules — squeezed text
            # colliding with the next unit's label reads worse than none.
            label = _value(module.get("id"))
            label_size = module_height / Decimal("18")
            if module_width / Decimal("30") + (
                Decimal(len(label)) * label_size * Decimal("0.65")
            ) < module_width:
                elements.append(
                    f'<text x="{_pt(x + module_width / Decimal("30"))}" '
                    f'y="{_pt(baseline + module_height - module_height / Decimal("30"))}" '
                    f'font-size="{_pt(label_size)}" '
                    f'fill="#727D82">{escape(label)}</text>'
                )
        for joint in layout.column_joints:
            seam_x = joint.x_mm - left_edge
            seam_top = top_edge - joint.top_mm
            seam_bottom = top_edge
            joint_width = joint.width_mm / Decimal("60")
            elements.append(
                f'<line x1="{_pt(seam_x)}" y1="{_pt(seam_top)}" x2="{_pt(seam_x)}" '
                f'y2="{_pt(seam_bottom)}" stroke="#E56A32" '
                f'stroke-width="{_pt(joint_width)}"/>'
            )
            if joint.angle_deg is not None:
                elements.append(
                    f'<text x="{_pt(seam_x)}" y="{_pt(seam_bottom - joint.top_mm / Decimal("18"))}" '
                    f'font-size="{_pt(joint.top_mm / Decimal("16"))}" '
                    f'fill="#E56A32" text-anchor="middle">'
                    f'{escape(str(joint.angle_deg))}°</text>'
                )
        for joint in layout.stack_joints:
            seam_x = joint.x_mm - left_edge
            seam_y = top_edge - joint.y_mm
            joint_width = joint.width_mm / Decimal("60")
            elements.append(
                f'<line x1="{_pt(seam_x)}" y1="{_pt(seam_y)}" '
                f'x2="{_pt(seam_x + joint.width_mm)}" y2="{_pt(seam_y)}" '
                f'stroke="#E56A32" stroke-width="{_pt(joint_width)}"/>'
            )
    else:
        width = _num(position.get("width_mm"))
        height = _num(position.get("height_mm"))
        if width <= 0 or height <= 0:
            raise DocumentaryError("svg_dimension_invalid")
        _svg_elements(tree, Decimal("0"), Decimal("0"), width, height, elements, marker)
    return (
        f'<svg viewBox="0 0 {_pt(width)} {_pt(height)}" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="Vano {_value(position.get("position_index"))}">'
        + "".join(elements) + "</svg>"
    )


def _glass_specs(node: object) -> list[str]:
    if not isinstance(node, dict):
        raise DocumentaryError("invalid_frozen_parametric_tree")
    result = []
    if node.get("glass_spec") is not None:
        result.append(_value(node["glass_spec"]))
    children = node.get("children", [])
    if not isinstance(children, list):
        raise DocumentaryError("invalid_frozen_parametric_tree")
    for child in children:
        result.extend(_glass_specs(child))
    return result


def _position_glass_specs(position: dict[str, object]) -> list[str]:
    tree = _object(position.get("parametric_tree"), "invalid_frozen_parametric_tree")
    if tree.get("version") == "product-v2":
        assembly = _object(tree.get("assembly"), "invalid_frozen_parametric_tree")
        specs: list[str] = []
        for module in _array(assembly.get("modules"), "invalid_frozen_parametric_tree"):
            specs.extend(
                _glass_specs(
                    _object(module, "invalid_frozen_parametric_tree").get("tree")
                )
            )
        return specs
    return _glass_specs(tree)


def frozen_glass_specs(position: dict[str, object]) -> list[str]:
    """Public wrapper — portal/print surfaces reuse the sealed-tree walk."""
    return _position_glass_specs(position)


def _revision_header(
    snapshot: dict[str, object], title: str, doc_code: str, workshop: bool = False
) -> tuple[str, str]:
    """Masthead + titleblock. ``workshop`` docs carry the full BOM hash — a
    shop-floor integrity anchor; commercial docs show a short fingerprint
    only, since the sealed hash is the machine identity, not client copy."""
    project = _object(snapshot.get("project"), "invalid_frozen_revision_snapshot")
    issuer = ""
    organization = snapshot.get("organization")
    if isinstance(organization, dict):
        issuer_name = _value(organization.get("name"))
        if issuer_name:
            issuer = (
                f"{escape(issuer_name)}"
                f" · RUT {escape(_value(organization.get('tax_id')))}<br>"
            )
        contact = " · ".join(
            part
            for part in (
                _value(organization.get("brand_address")),
                _value(organization.get("brand_phone")),
                _value(organization.get("brand_email")),
            )
            if part and part != "—"
        )
        if contact:
            issuer += f"{escape(contact)}<br>"
    bom_hash = _value(snapshot.get("bom_hash"))
    class_name = "workshop" if workshop else ""
    sealed_at = _value(snapshot.get("sealed_at"))
    revision = _value(snapshot.get("revision"))
    project_code = _value(project.get("code"))
    # The BOM hash is the machine identity — only workshop documents carry it;
    # customer-facing documents keep it in metadata/QR instead of printing a
    # meaningless hex chunk.
    fingerprint = (
        '<div class="tb-cell tb-wide"><span class="tb-label">Huella BOM</span>'
        f'<span class="tb-value">{escape(bom_hash)}</span></div>'
        if workshop
        else ""
    )
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(project_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        f'<span class="tb-value">{escape(doc_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Rev.</span>'
        f'<span class="tb-value">{escape(revision)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(sealed_at))}</span></div>'
        f"{fingerprint}"
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    header = (
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"{issuer}"
        f"<strong>{escape(project_code)}</strong><br>"
        f"{escape(doc_code)} · Rev. {escape(revision)}<br>"
        f"{escape(_cldate(sealed_at))}</div></div>"
        '<div class="rule-stack"></div>'
        f"<h1>{escape(title)}</h1>"
    )
    return f'<main class="{class_name}">{titleblock}{header}', bom_hash


def _doc01(snapshot: dict[str, object]) -> str:
    project = _object(snapshot.get("project"), "invalid_frozen_revision_snapshot")
    currency = project.get("currency")
    positions = [_object(item, "invalid_frozen_position")
                 for item in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot")]
    # Identical openings collapse into one row; location lists stay honest.
    groups: dict[tuple[object, ...], dict[str, object]] = {}
    for position in positions:
        specs = ", ".join(_position_glass_specs(position)) or "Panel declarado"
        # The sealed tree is the design signature — mirrored pairs (TURN_LEFT
        # vs TURN_RIGHT) and any leaf/panel difference must NOT group, or the
        # one rendered figure would lie about handedness.
        tree_sig = json.dumps(
            position.get("parametric_tree"), sort_keys=True, default=str
        )
        key = (
            _value(position.get("typology")), _value(position.get("width_mm")),
            _value(position.get("height_mm")), specs,
            _value(position.get("color_interior")),
            _value(position.get("color_exterior")),
            _value(position.get("price_net")),
            _value(position.get("discount_pct")), tree_sig,
        )
        bucket = groups.setdefault(key, {
            "indexes": [], "locations": [], "quantity": Decimal("0"),
            "price_net": Decimal("0"), "specs": specs, "priced": True,
            "ref_position": position,
        })
        bucket["indexes"].append(_value(position.get("position_index")))
        location = _value(position.get("location_tag"))
        if location and location not in bucket["locations"]:
            bucket["locations"].append(location)
        bucket["quantity"] += _num(position.get("quantity"))
        if position.get("price_net") is None:
            # Revisions frozen before line pricing carry no per-position net.
            bucket["priced"] = False
        else:
            bucket["price_net"] += _num(position.get("price_net"))
    opening_rows = []
    for key, bucket in groups.items():
        typology, width_mm, height_mm, specs, ci, ce = key[:6]
        discount_pct = key[7]
        indexes = bucket["indexes"]
        # Long grouped index lists wrap horribly — compact to first…last + n.
        index_cell = (
            ", ".join(indexes)
            if len(indexes) <= 6
            else f"{indexes[0]} … {indexes[-1]} ({len(indexes)})"
        )
        table_locations = bucket["locations"]
        opening_rows.append([
            index_cell,
            (", ".join(table_locations)
             if len(table_locations) <= 6
             else f"{table_locations[0]} … {table_locations[-1]} ({len(table_locations)})")
            or "—",
            _TYPOLOGY_ES.get(typology, typology),
            f"{width_mm}\u00a0×\u00a0{height_mm}",
            bucket["quantity"], specs, _finish(ci, ce),
            (
                f"{format(_num(discount_pct).normalize(), 'f')}%"
                if discount_pct not in ("0", "0.00", "0.0000", "—", "")
                else "—"
            ),
            _money(bucket["price_net"] / bucket["quantity"], currency)
            if bucket["priced"] and bucket["quantity"]
            else "—",
            _money(bucket["price_net"], currency) if bucket["priced"] else "—",
        ])
    quote_folio = f"COT-{_value(project.get('code'))}-{_value(snapshot.get('revision'))}"
    body, _ = _revision_header(snapshot, "Cotización comercial", quote_folio)
    client_lines = []
    for label, field in (("RUT", "client_rut"), ("Giro", "client_giro"),
                         ("Comuna", "client_comuna"), ("Dirección", "client_address"),
                         ("Contacto", "client_email"), ("Teléfono", "client_phone")):
        value = _value(project.get(field))
        if value and value != "—":
            client_lines.append(f"<p><strong>{label}:</strong> {escape(value)}</p>")
    delivery = _value(project.get("delivery_address"))
    if delivery and delivery != "—":
        client_lines.append(f"<p><strong>Entrega:</strong> {escape(delivery)}</p>")
    body += (
        '<section class="hero"><p>Preparado para</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        + "".join(client_lines)
        + f'<p class="total">Total: {escape(_money(project.get("total_price_gross"), currency))}</p>'
        "</section>"
        "<h2>Solución propuesta</h2>"
        '<table class="sol-table"><colgroup>'
        '<col style="width:4%"><col style="width:16%"><col style="width:13%">'
        '<col style="width:11%"><col style="width:5%"><col style="width:15%">'
        '<col style="width:9%"><col style="width:5%"><col style="width:10%">'
        '<col style="width:12%">'
        "</colgroup><thead><tr>"
        "<th>Pos.</th><th>Ubicación</th><th>Tipología</th>"
        "<th>Dimensiones (mm)</th><th>Cant.</th><th>Vidrio / relleno</th>"
        "<th>Acabado</th><th>Dcto.</th><th>P. unit.</th><th>Neto</th></tr></thead><tbody>"
        + "".join(
            _row(row, ["", "", "", "nowrap", "dimension", "", "", "", "dimension", "dimension"])
            for row in opening_rows
        )
        + "</tbody></table>"
    )
    # One figure per opening group — identical units share a drawing and the
    # caption lists every position it covers, keeping long quotes compact.
    # The flex grid can't fragment mid-page in WeasyPrint, so it sits between
    # the totals and the commercial close — conditions and the signature block
    # keep flowing on the same page instead of orphaning a final page.
    figures = '<h2>Vistas de los productos</h2><div class="figures">'
    for bucket in groups.values():
        ref = bucket["ref_position"]
        location_list = bucket["locations"]
        locations = (
            ", ".join(location_list)
            if len(location_list) <= 6
            else f"{location_list[0]} … {location_list[-1]} ({len(location_list)})"
        ) or "—"
        index_list = bucket["indexes"]
        indexes = (
            ", ".join(index_list)
            if len(index_list) <= 6
            else f"{index_list[0]} … {index_list[-1]} ({len(index_list)})"
        )
        figures += (
            f'<figure>{_position_svg(ref)}'
            f'<figcaption><span class="figpos">Pos. '
            f'{escape(indexes)}</span> · {escape(locations)}<br/>'
            f'<span class="figdim">{escape(_value(ref.get("width_mm")))} × '
            f'{escape(_value(ref.get("height_mm")))} mm</span> · Cant. '
            f'{escape(_value(bucket["quantity"]))}</figcaption></figure>'
        )
    figures += "</div>"
    granted_discounts = sorted(
        {
            key[7]
            for key in groups
            if key[7] not in ("0", "0.00", "0.0000", "—", "")
        },
        key=lambda item: _num(item),
    )
    discount_note = (
        "<p class=\"muted\">Precios incluyen descuento del "
        + " / ".join(
            f"{format(_num(pct).normalize(), 'f')}%" for pct in granted_discounts
        )
        + ".</p>"
        if granted_discounts
        else ""
    )
    body += (
        "<h2>Resumen comercial</h2>"
        + _table(["Neto", "Impuesto", "Total"], [[
            _money(project.get("total_price_net"), currency),
            _money(project.get("total_price_tax"), currency),
            _money(project.get("total_price_gross"), currency),
        ]], ["dimension", "dimension", "dimension"])
        + discount_note
        + figures
        + '<div class="keep">'
        + f"<h2>Condiciones</h2><p><strong>Pago:</strong> {escape(_value(project.get('payment_terms')))}</p>"
        + "<p><strong>Oferta válida hasta:</strong> "
        + escape(_cldate(project.get("quotation_valid_until"))) + "</p>"
        + f"<p>{escape(_value(project.get('notes_commercial')))}</p>"
        + '<div class="signoff"><div class="sign-row">'
        '<div class="sign-cell"><span class="sign-label">Nombre</span></div>'
        '<div class="sign-cell"><span class="sign-label">RUT</span></div>'
        '<div class="sign-cell"><span class="sign-label">Firma</span></div>'
        '<div class="sign-cell sign-date"><span class="sign-label">Fecha</span></div>'
        "</div>"
        '<p class="muted">Aceptación del cliente — la firma confirma la '
        "aceptación de esta cotización.</p></div></div></main>"
    )
    return body


def _doc03(snapshot: dict[str, object]) -> str:
    if snapshot.get("production_allowed") is not True:
        raise DocumentaryError("production_document_blocked")
    if snapshot.get("documentary_complete") is not True:
        raise DocumentaryError("manufacturing_document_incomplete")
    facts = [_object(item, "invalid_manufacturing_fact")
             for item in _array(snapshot.get("manufacturing"), "invalid_frozen_revision_snapshot")]
    positions_list = [
        _object(item, "invalid_frozen_position")
        for item in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot")
    ]
    positions_by_index = {item.get("position_index"): item for item in positions_list}
    annotated_positions: set[object] = set()
    labels = _piece_labels(snapshot)
    body, _ = _revision_header(snapshot, "Orden de trabajo de taller", "DOC-03", workshop=True)
    for fact in facts:
        members = [_object(item, "invalid_manufacturing_member")
                   for item in _array(fact.get("members"), "invalid_manufacturing_fact")]
        reinforcements = [_object(item, "invalid_reinforcement_fact")
                          for item in _array(fact.get("reinforcements"), "invalid_manufacturing_fact")]
        handles = [_object(item, "invalid_handle_fact")
                   for item in _array(fact.get("handles"), "invalid_manufacturing_fact")]
        infills = [_object(item, "invalid_infill_fact")
                   for item in _array(fact.get("infills"), "invalid_manufacturing_fact")]
        body += (
            f'<section><h2>Posición {escape(_value(fact.get("position_index")))} · '
            f'Repetición {escape(_value(fact.get("repetition_index")))}</h2>'
            f'<p class="dimension">{escape(_value(fact.get("nominal_width_mm")))} × '
            f'{escape(_value(fact.get("nominal_height_mm")))} mm</p>'
            + _table(
                ["Pieza", "Rol / slot", "SKU taller", "Corte mm", "Ángulos", "Flecha mm", "Referencia X/Y"],
                [[
                    labels["member"].get(member.get("member_id"), member.get("member_id")),
                    f"{_ROLE_ES.get(_value(_object(member.get('identity'), 'invalid_member_identity').get('role')), _value(_object(member.get('identity'), 'invalid_member_identity').get('role')))} / "
                    f"{_SLOT_ES.get(_value(_object(member.get('identity'), 'invalid_member_identity').get('physical_member_slot')), _value(_object(member.get('identity'), 'invalid_member_identity').get('physical_member_slot')))}",
                    member.get("workshop_sku"), member.get("cut_length_mm"),
                    f"{_value(member.get('angle_left'))}° / {_value(member.get('angle_right'))}°",
                    member.get("sagitta_mm") if member.get("sagitta_mm") is not None else "—",
                    f"({_value(_object(member.get('start'), 'invalid_member_point').get('x_mm'))}, "
                    f"{_value(_object(member.get('start'), 'invalid_member_point').get('y_mm'))}) → "
                    f"({_value(_object(member.get('end'), 'invalid_member_point').get('x_mm'))}, "
                    f"{_value(_object(member.get('end'), 'invalid_member_point').get('y_mm'))})",
                ] for member in members], ["hash", "", "", "dimension", "", "dimension", ""]
            )
        )
        if reinforcements:
            body += _table(
                ["Refuerzo", "Pieza padre", "SKU acero", "Corte mm", "Ángulos", "Flecha mm"],
                [[labels["reinforcement"].get(item.get("reinforcement_id"), item.get("reinforcement_id")),
                  labels["member"].get(item.get("parent_member_id"), item.get("parent_member_id")),
                  item.get("workshop_sku"), item.get("cut_length_mm"),
                  f"{_value(item.get('angle_left'))}° / {_value(item.get('angle_right'))}°",
                  item.get("sagitta_mm") if item.get("sagitta_mm") is not None else "—"]
                 for item in reinforcements], ["hash", "hash", "", "dimension", "", "dimension"]
            )
        if infills:
            body += _table(
                ["Relleno", "Vano / hoja", "Especificación", "Dimensiones (mm)", "Forma", "Retención"],
                [[labels["infill"].get(item.get("infill_id"), item.get("infill_id")),
                  _location(labels, item.get("bay_id"), item.get("leaf_id")),
                  item.get("composition"),
                  f"{_value(_object(item.get('rect'), 'invalid_infill_rect').get('width_mm'))} × "
                  f"{_value(_object(item.get('rect'), 'invalid_infill_rect').get('height_mm'))}",
                  (f"Perfilado {len(item['shape'])} vértices" if item.get("shape") else "Rectangular"),
                  "Junquillos identificados en matriz"] for item in infills],
                ["hash", "", "", "dimension", "", ""],
            )
        if handles:
            body += _table(
                ["Manilla", "Vano / hoja", "Pieza host", "Punto X/Y mm",
                 "Altura solicitada mm", "Referencia vertical"],
                [[labels["handle"].get(item.get("handle_id"), item.get("handle_id")),
                  _location(labels, item.get("bay_id"), item.get("leaf_id")),
                  labels["member"].get(item.get("host_member_id"), item.get("host_member_id")),
                  f"{_value(_object(item.get('point'), 'invalid_handle_point').get('x_mm'))} / "
                  f"{_value(_object(item.get('point'), 'invalid_handle_point').get('y_mm'))}",
                  item.get("requested_height_mm"),
                  _SLOT_ES.get(
                      _value(item.get("vertical_reference")),
                      item.get("vertical_reference"),
                  )] for item in handles],
                ["hash", "", "hash", "dimension", "dimension", ""]
            )
        if fact.get("position_index") not in annotated_positions:
            annotated_positions.add(fact.get("position_index"))
            position = positions_by_index.get(fact.get("position_index"))
            if position is None:
                raise DocumentaryError("invalid_frozen_revision_snapshot")
            body += (
                f'<div class="break-avoid workshop-figure" style="text-align:center">'
                f'<div style="display:inline-block;max-width:100mm">'
                f'{_position_svg(_object(position, "invalid_frozen_position"))}</div></div>'
            )
            annotations = [
                _object(item, "invalid_workshop_annotations")
                for item in _array(
                    position.get("workshop_annotations"), "invalid_workshop_annotations"
                )
            ]
            if annotations:
                body += "<h3>Anotaciones de taller congeladas</h3>" + _table(
                    ["Vano", "Hoja", "Desagüe inferior mm", "Cierres perímetro mm",
                     "Ancho continuo mm", "Acabado", "Coplador"],
                    [[
                        item.get("bay_id"), item.get("leaf_id"),
                        ", ".join(_value(number) for number in _array(
                            item.get("bottom_drain_holes_mm"), "invalid_workshop_annotations"
                        )) if item.get("bottom_drain_holes_mm") is not None else "—",
                        ", ".join(_value(number) for number in _array(
                            item.get("closing_points_perimeter_mm"),
                            "invalid_workshop_annotations",
                        )) if item.get("closing_points_perimeter_mm") is not None else "—",
                        item.get("continuous_width_mm"), item.get("finish_class"),
                        item.get("has_coupler"),
                    ] for item in annotations],
                    ["", "", "dimension", "dimension", "dimension", "", ""],
                )
        relationships = [
            _object(item, "invalid_assembly_relationship")
            for item in _array(fact.get("relationships"), "invalid_manufacturing_fact")
        ]
        if relationships:
            endpoints = {
                **labels["member"],
                **labels["reinforcement"],
                **labels["infill"],
                **labels["leaf_fact"],
            }
            body += "<h3>Matriz de ensamble</h3>" + _table(
                ["Relación", "Pieza origen", "Pieza destino"],
                [[item.get("relationship"),
                  endpoints.get(item.get("source_id"), item.get("source_id")),
                  endpoints.get(item.get("target_id"), item.get("target_id"))]
                 for item in relationships],
                ["", "hash", "hash"],
            )
        body += "</section>"
    return body + "</main>"


def _piece_labels(
    snapshot: dict[str, object],
) -> dict[str, dict[object, str]]:
    """Sequential workshop-facing piece codes (M-01, R-01, I-01, MAN-01) plus
    location codes (P-01, V-01, H-01) so emitted documents never print raw
    engineering ids. The frozen snapshot keeps the full identities."""
    member: dict[object, str] = {}
    reinforcement: dict[object, str] = {}
    infill: dict[object, str] = {}
    handle: dict[object, str] = {}
    bay: dict[object, str] = {}
    leaf: dict[object, str] = {}
    leaf_fact: dict[object, str] = {}
    for fact in _array(snapshot.get("manufacturing"), "invalid_frozen_revision_snapshot"):
        for item in _array(fact.get("members"), "invalid_manufacturing_fact"):
            member.setdefault(item.get("member_id"), f"M-{len(member) + 1:02d}")
            if item.get("bay_id") is not None:
                bay.setdefault(item.get("bay_id"), f"V-{len(bay) + 1:02d}")
        for item in _array(fact.get("reinforcements"), "invalid_manufacturing_fact"):
            reinforcement.setdefault(item.get("reinforcement_id"), f"R-{len(reinforcement) + 1:02d}")
        for item in _array(fact.get("infills"), "invalid_manufacturing_fact"):
            infill.setdefault(item.get("infill_id"), f"I-{len(infill) + 1:02d}")
        for item in _array(fact.get("handles"), "invalid_manufacturing_fact"):
            handle.setdefault(item.get("handle_id"), f"MAN-{len(handle) + 1:02d}")
        for item in [
            *_array(fact.get("infills"), "invalid_manufacturing_fact"),
            *_array(fact.get("handles"), "invalid_manufacturing_fact"),
        ]:
            if item.get("bay_id") is not None:
                bay.setdefault(item.get("bay_id"), f"V-{len(bay) + 1:02d}")
            if item.get("leaf_id") is not None:
                leaf.setdefault(item.get("leaf_id"), f"H-{len(leaf) + 1:02d}")
        for item in fact.get("leaves") if isinstance(fact.get("leaves"), list) else []:
            leaf_id = item.get("leaf_id")
            bay_id = item.get("bay_id")
            if leaf_id is not None:
                leaf.setdefault(leaf_id, f"H-{len(leaf) + 1:02d}")
                leaf_fact[item.get("leaf_fact_id")] = leaf[leaf_id]
            elif bay_id is not None:
                bay.setdefault(bay_id, f"V-{len(bay) + 1:02d}")
                leaf_fact[item.get("leaf_fact_id")] = bay[bay_id]
    position: dict[object, str] = {}
    for item in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot"):
        position[item.get("id")] = f"P{item.get('position_index')}"
    return {
        "member": member,
        "reinforcement": reinforcement,
        "infill": infill,
        "handle": handle,
        "bay": bay,
        "leaf": leaf,
        "leaf_fact": leaf_fact,
        "position": position,
    }


def _short_id(value: object) -> str:
    """Raw 64-hex/UUID identities dump a full hash cell — truncate for
    display while staying recognizably unique to the shop."""
    text = _value(value)
    if len(text) > 20:
        return text[:12] + "…"
    return text


def _norm_dec(value: object) -> str:
    """Normalize a Decimal-serialized value for join keys — '1800.00' and
    '1800' must collide, trailing zeros must not split identities."""
    if value is None:
        return ""
    return format(Decimal(str(value)).normalize(), "f")


def _role_name(value: object) -> str:
    """Enum identities travel as 'ProfileRole.FRAME' through stored JSON and
    as 'FRAME' through live engine dumps — collapse both to the name."""
    return str(value if value is not None else "").rsplit(".", 1)[-1]


def _join_codes(codes: list[str]) -> str:
    unique = sorted(set(codes))
    if len(unique) <= 3:
        return " · ".join(unique)
    return f"{unique[0]} · +{len(unique) - 1}"


def _cut_member_map(
    snapshot: dict[str, object], labels: dict[str, dict[object, str]]
) -> dict[tuple[str, ...], str]:
    """Cut-spec → member/reinforcement codes for saw output.

    A bar cut's piece_id is a sha256 of the cut spec, never the frozen member
    identity, so cut artifacts used to print hash prefixes. The join runs on
    the deterministic spec tuple. Identical members share one spec — the
    printed code lists every member the piece serves, which stays honest
    because those pieces are physically interchangeable.
    """
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return {}
    spec: dict[tuple[str, ...], list[str]] = {}
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        members = {
            str(item.get("member_id")): item
            for item in _array(fact.get("members"), "invalid_manufacturing_fact")
        }
        for item in members.values():
            identity = _object(item.get("identity"), "invalid_manufacturing_fact")
            key = (
                "PROFILE",
                str(item.get("workshop_sku") or ""),
                _norm_dec(item.get("cut_length_mm")),
                _norm_dec(item.get("angle_left")),
                _norm_dec(item.get("angle_right")),
                _role_name(identity.get("role")),
                str(item.get("bay_id") or ""),
                str(item.get("leaf_id") or ""),
                str(identity.get("position_id") or ""),
                _norm_dec(item.get("sagitta_mm")),
            )
            spec.setdefault(key, []).append(
                labels["member"].get(
                    item.get("member_id"), str(item.get("member_id") or "")[:10]
                )
            )
        for item in _array(fact.get("reinforcements"), "invalid_manufacturing_fact"):
            parent = members.get(str(item.get("parent_member_id")))
            if parent is None:
                continue
            identity = _object(parent.get("identity"), "invalid_manufacturing_fact")
            key = (
                "REINFORCEMENT",
                str(item.get("workshop_sku") or ""),
                _norm_dec(item.get("cut_length_mm")),
                _norm_dec(item.get("angle_left")),
                _norm_dec(item.get("angle_right")),
                _role_name(identity.get("role")),
                str(parent.get("bay_id") or ""),
                str(parent.get("leaf_id") or ""),
                str(identity.get("position_id") or ""),
                "",
            )
            spec.setdefault(key, []).append(
                labels["reinforcement"].get(
                    item.get("reinforcement_id"),
                    str(item.get("reinforcement_id") or "")[:10],
                )
            )
    return {key: _join_codes(codes) for key, codes in spec.items()}


def _cut_key(cut: dict[str, object]) -> tuple[str, ...]:
    """The spec tuple a placed cut joins on — mirrors _cut_member_map."""
    return (
        str(cut.get("source_kind") or "PROFILE"),
        str(cut.get("workshop_sku") or ""),
        _norm_dec(cut.get("length_mm")),
        _norm_dec(cut.get("angle_left")),
        _norm_dec(cut.get("angle_right")),
        _role_name(cut.get("role")),
        str(cut.get("bay_id") or ""),
        str(cut.get("leaf_id") or ""),
        str(cut.get("source_position_id") or ""),
        _norm_dec(cut.get("sagitta_mm")),
    )


def _infill_code_map(
    snapshot: dict[str, object], labels: dict[str, dict[object, str]]
) -> dict[tuple[str, str, str], str]:
    """(position, bay, leaf) → infill codes, so sheet/nested pieces print the
    I-xx identity the assembly map and glazing table already use instead of a
    sheet-local V-xx counter that collides with bay codes."""
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return {}
    spec: dict[tuple[str, str, str], list[str]] = {}
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        for item in _array(fact.get("infills"), "invalid_manufacturing_fact"):
            key = (
                str(item.get("position_id") or ""),
                str(item.get("bay_id") or ""),
                str(item.get("leaf_id") or ""),
            )
            spec.setdefault(key, []).append(
                labels["infill"].get(
                    item.get("infill_id"), str(item.get("infill_id") or "")[:10]
                )
            )
    return {key: _join_codes(codes) for key, codes in spec.items()}


def _infill_key(piece: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(piece.get("source_position_id") or ""),
        str(piece.get("bay_id") or ""),
        str(piece.get("leaf_id") or ""),
    )


def _location(labels: dict[str, dict[object, str]], bay_id: object, leaf_id: object) -> str:
    bay = labels["bay"].get(bay_id, _value(bay_id))
    if leaf_id is None:
        return str(bay)
    return f"{bay} / {labels['leaf'].get(leaf_id, _value(leaf_id))}"


def _doc05(snapshot: dict[str, object]) -> str:
    if snapshot.get("production_allowed") is not True:
        raise DocumentaryError("production_document_blocked")
    if snapshot.get("documentary_complete") is not True:
        raise DocumentaryError("manufacturing_document_incomplete")
    purchase = _object(snapshot.get("purchase_requirements"), "invalid_purchase_projection")
    groups = [_object(item, "invalid_stock_group")
              for item in _array(purchase.get("stock_groups"), "invalid_purchase_projection")]
    labels = _piece_labels(snapshot)
    cut_map = _cut_member_map(snapshot, labels)
    body, _ = _revision_header(snapshot, "Plan de corte 1D", "DOC-05", workshop=True)
    for group in groups:
        body += (
            f"<h2>{escape(_value(group.get('purchasing_sku')))} · "
            f"{escape(_value(group.get('source_kind')))}</h2>"
            f"<p><strong>Stock físico:</strong> {escape(_short_id(group.get('physical_stock_identity')))} · "
            f"<strong>Largo:</strong> {escape(_value(group.get('stock_length_mm')))} mm · "
            f"<strong>Barras:</strong> {escape(_value(group.get('purchased_bar_count')))}</p>"
        )
        for bar_value in _array(group.get("bars"), "invalid_stock_group"):
            bar = _object(bar_value, "invalid_cut_bar")
            cuts = [_object(item, "invalid_cut_piece")
                    for item in _array(bar.get("cuts"), "invalid_cut_bar")]
            body += (
                f"<h3>Barra {escape(_value(bar.get('bar_index')))} · remanente "
                f"{escape(_value(bar.get('remainder_mm')))} mm</h3>"
                + _table(
                    ["Sec.", "Pieza física", "Posición", "Vano / hoja", "SKU taller", "Corte mm", "Ángulos", "Flecha mm"],
                    [[cut.get("sequence"),
                      cut_map.get(_cut_key(cut), _short_id(cut.get("piece_id"))),
                      labels["position"].get(
                          cut.get("source_position_id"),
                          _short_id(cut.get("source_position_id")),
                      ),
                      _location(labels, cut.get("bay_id"), cut.get("leaf_id")),
                      cut.get("workshop_sku"), cut.get("length_mm"),
                      f"{_value(cut.get('angle_left'))}° / {_value(cut.get('angle_right'))}°",
                      cut.get("sagitta_mm") if cut.get("sagitta_mm") is not None else "—"]
                     for cut in cuts], ["", "hash", "", "", "", "dimension", "", "dimension"]
                )
            )
    return body + "</main>"


def _doc06(snapshot: dict[str, object]) -> str:
    if snapshot.get("production_allowed") is not True:
        raise DocumentaryError("production_document_blocked")
    if snapshot.get("documentary_complete") is not True:
        raise DocumentaryError("manufacturing_document_incomplete")
    inspector = [_object(item, "invalid_inspector_evidence")
                 for item in _array(snapshot.get("inspector"), "invalid_frozen_revision_snapshot")]
    body, _ = _revision_header(snapshot, "Checklist de control final", "DOC-06", workshop=True)
    tolerance = "—"
    if inspector:
        config = _object(inspector[0].get("config"), "invalid_inspector_evidence")
        r10 = config.get("R10")
        if isinstance(r10, dict) and r10.get("tolerance_mm") is not None:
            tolerance = _value(r10.get("tolerance_mm"))
    rows = [
        ["Escuadra de diagonales", f"Diferencia ≤ {tolerance} mm", "□", "________________"],
        ["Burletes y estanqueidad", "Continuidad visual y cierre", "□", "________________"],
        ["Desagües", "Libres y según diseño congelado", "□", "________________"],
        ["Herrajes", "Operación y calibración física", "□", "________________"],
        ["Vidrios / paneles", "Sin daño y correctamente retenidos", "□", "________________"],
    ]
    body += _table(["Control", "Criterio esperado", "Cumple", "Medición / observación"], rows)
    body += (
        "<p><strong>Operador:</strong> ______________________________</p>"
        "<p><strong>Fecha de ejecución QC:</strong> __________________</p>"
        "<p><strong>Resultado físico:</strong> ☐ Pendiente &nbsp; ☐ Conforme &nbsp; ☐ No conforme</p>"
        "<div class=\"signature\"></div><p>Firma responsable QC</p></main>"
    )
    return body


def _doc07(snapshot: dict[str, object]) -> str:
    project = _object(snapshot.get("project"), "invalid_frozen_revision_snapshot")
    pricing = _object(snapshot.get("pricing"), "invalid_frozen_revision_snapshot")
    input_snapshot = _object(pricing.get("input_snapshot"), "invalid_pricing_evidence")
    costs = _array(input_snapshot.get("cost_lines"), "invalid_pricing_evidence")
    realized = _object(snapshot.get("realized_waste"), "invalid_frozen_revision_snapshot")
    body, _ = _revision_header(snapshot, "Informe ejecutivo de costos y margen", "DOC-07")
    currency = _value(project.get("currency"))
    body += '<p class="confidential">CONFIDENCIAL · SOLO PROPIETARIO</p>'
    body += _table(
        ["Posición", "Costo capturado"],
        [[_array(item, "invalid_pricing_evidence")[0],
          _money(_array(item, "invalid_pricing_evidence")[1], currency)]
         for item in costs], ["", "dimension"],
    )
    body += _table(
        ["Costo neto", "Venta neta", "Impuesto", "Venta total"],
        [[_money(pricing.get("applied_total_cost_net"), currency),
          _money(project.get("total_price_net"), currency),
          _money(project.get("total_price_tax"), currency),
          _money(project.get("total_price_gross"), currency)]],
        ["dimension", "dimension", "", "dimension"],
    )
    status = realized.get("status")
    if status != "NOT_RECORDED" or realized.get("value") is not None:
        raise DocumentaryError("realized_waste_authority_invalid")
    body += "<h2>Merma realizada</h2><p><strong>NO REGISTRADA</strong> · valor: —</p></main>"
    return body


def _doc04(snapshot: dict[str, object]) -> str:
    order = _object(snapshot.get("order"), "invalid_order_snapshot")
    revision = _object(snapshot.get("revision"), "invalid_order_snapshot")
    if order.get("order_type") != "SUPPLIER_PROFILE_PO":
        raise DocumentaryError("document_scope_mismatch")
    lines = [_object(item, "invalid_order_line")
             for item in _array(snapshot.get("lines"), "invalid_order_snapshot")]
    pseudo_revision = {
        "project": {"code": order.get("project_code")},
        "revision": revision.get("revision_code"),
        "sealed_at": order.get("confirmed_at"),
        "bom_hash": revision.get("bom_hash"),
        "organization": snapshot.get("organization"),
    }
    body, _ = _revision_header(pseudo_revision, "Pedido de perfiles", "DOC-04", workshop=True)
    body += (
        f"<p><strong>Orden:</strong> {escape(_value(order.get('order_code')))} · "
        f"<strong>Proveedor:</strong> {escape(_value(order.get('supplier_name')))}</p>"
        + _table(
            ["Requisito", "Categoría", "SKU taller", "SKU compra", "Largo barra (mm)",
             "Cantidad", "Unidad", "Perfil de corte", "Trazabilidad"],
            [[_value(line.get("requirement_key")),
              _CATEGORY_ES.get(_value(line.get("category")), line.get("category")),
              ", ".join(_value(item) for item in _array(line.get("technical_skus"), "invalid_order_line")),
              line.get("purchasing_sku"),
              _object(line.get("specification"), "invalid_order_line").get("stock_length_mm"),
              line.get("quantity"), line.get("unit"),
              _object(line.get("specification"), "invalid_order_line").get("cutting_profile_id"),
              ", ".join(_value(item) for item in _array(line.get("source_trace"), "invalid_order_line"))]
             for line in lines], ["hash", "", "", "", "dimension", "dimension", "", "", ""],
        )
        + "</main>"
    )
    return body


def _doc08(snapshot: dict[str, object]) -> str:
    order = _object(snapshot.get("order"), "invalid_order_snapshot")
    revision = _object(snapshot.get("revision"), "invalid_order_snapshot")
    if order.get("order_type") not in ("SUPPLIER_HARDWARE_PO", "SUPPLIER_PANEL_PO"):
        raise DocumentaryError("document_scope_mismatch")
    lines = [_object(item, "invalid_order_line")
             for item in _array(snapshot.get("lines"), "invalid_order_snapshot")]
    pseudo_revision = {
        "project": {"code": order.get("project_code")},
        "revision": revision.get("revision_code"),
        "sealed_at": order.get("confirmed_at"),
        "bom_hash": revision.get("bom_hash"),
        "organization": snapshot.get("organization"),
    }
    body, _ = _revision_header(pseudo_revision, "Orden de compra", "DOC-08", workshop=True)
    body += (
        f"<p><strong>Orden:</strong> {escape(_value(order.get('order_code')))} · "
        f"<strong>Proveedor:</strong> {escape(_value(order.get('supplier_name')))}</p>"
        + _table(
            ["Requisito", "Categoría", "SKU taller", "SKU compra",
             "Cantidad", "Unidad", "Detalle", "Trazabilidad"],
            [[_value(line.get("requirement_key")),
              _CATEGORY_ES.get(_value(line.get("category")), line.get("category")),
              ", ".join(_value(item) for item in _array(line.get("technical_skus"), "invalid_order_line")),
              line.get("purchasing_sku"),
              line.get("quantity"), line.get("unit"),
              "; ".join(
                  f"{key}={_value(value)}"
                  for key, value in sorted(
                      _object(line.get("specification"), "invalid_order_line").items()
                  )
              ),
              ", ".join(_value(item) for item in _array(line.get("source_trace"), "invalid_order_line"))]
             for line in lines], ["hash", "", "", "", "dimension", "", "", ""],
        )
        + "</main>"
    )
    return body


def render_pdf_document(
    document_type: str, snapshot: dict[str, object], *, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    if document_type == "DOC-01":
        body = _doc01(snapshot)
    elif document_type == "DOC-03":
        body = _doc03(snapshot)
    elif document_type == "DOC-04":
        body = _doc04(snapshot)
    elif document_type == "DOC-05":
        body = _doc05(snapshot)
    elif document_type == "DOC-06":
        body = _doc06(snapshot)
    elif document_type == "DOC-07":
        body = _doc07(snapshot)
    elif document_type == "DOC-08":
        body = _doc08(snapshot)
    else:
        raise DocumentaryError("pdf_document_type_invalid")
    # Order-scoped payloads (DOC-02/DOC-04/DOC-07) carry `order`, not
    # `project` — resolve the code from whichever envelope the snapshot is.
    project_obj = snapshot.get("project")
    if isinstance(project_obj, dict):
        title_code = project_obj.get("code")
    else:
        order_obj = snapshot.get("order")
        title_code = order_obj.get("project_code") if isinstance(order_obj, dict) else None
    title = escape(f"{document_type} {_value(title_code)}")
    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA


_PAYMENT_KIND_ES = {"ANTICIPO": "Anticipo", "PARCIAL": "Abono parcial", "SALDO": "Saldo"}
_PAYMENT_METHOD_ES = {
    "TRANSFER": "Transferencia",
    "CASH": "Efectivo",
    "CARD": "Tarjeta",
    "CHECK": "Cheque",
    "FLOW": "Flow",
    "OTHER": "Otro",
}


def _receipt_body(payload: dict[str, object]) -> str:
    project = _object(payload.get("project"), "invalid_receipt_project")
    payment = _object(payload.get("payment"), "invalid_receipt_payment")
    balance = _object(payload.get("balance"), "invalid_receipt_balance")
    issued_at = _value(payload.get("issued_at"))
    receipt_code = _value(payload.get("receipt_code"))
    organization = payload.get("organization")
    currency = _value(project.get("currency"))
    kind = _PAYMENT_KIND_ES.get(_value(payment.get("kind")), _value(payment.get("kind")))
    method = _PAYMENT_METHOD_ES.get(
        _value(payment.get("method")), _value(payment.get("method"))
    )
    voided = payload.get("voided")
    voided_block = ""
    if isinstance(voided, dict):
        voided_block = (
            '<section class="voided-banner"><p class="voided-title">ANULADO</p>'
            f'<p>Este comprobante fue anulado el {escape(_cldate(voided.get("at")))}'
            + (
                f' — motivo: {escape(_value(voided.get("reason")))}'
                if _value(voided.get("reason")) != "—"
                else ""
            )
            + ". El registro permanece como evidencia; no representa un cobro vigente.</p></section>"
        )
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        '<span class="tb-value">Comprobante de pago</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Recibo</span>'
        f'<span class="tb-value">{escape(receipt_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(issued_at))}</span></div>'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Concepto</span>'
        f'<span class="tb-value">{escape(kind)}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    body = (
        f'<main>{titleblock}'
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(receipt_code)}</strong><br>"
        f"Comprobante de pago<br>{escape(_cldate(issued_at))}</div></div>"
        '<div class="rule-stack"></div>'
        "<h1>Comprobante de pago</h1>"
        f"{voided_block}"
        '<section class="hero"><p>Recibido de</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}"
        + (
            f" · {escape(_value(project.get('client_address')))}"
            if _value(project.get("client_address")) != "—"
            else (
                f" · {escape(_value(project.get('client_comuna')))}"
                if _value(project.get("client_comuna")) != "—"
                else ""
            )
        )
        + "</p>"
        f'<p class="total">Monto: {escape(_money(payment.get("amount"), currency))}</p></section>'
    )
    body += (
        "<h2>Detalle del cobro</h2>"
        + _table(
            ["Concepto", "Método", "Referencia", "Fecha de cobro"],
            [[kind, method, payment.get("reference"), _cldate(payment.get("recorded_at"))]],
        )
    )
    note = _value(payment.get("note"))
    if note != "—":
        body += f"<p><strong>Nota:</strong> {escape(note)}</p>"
    body += (
        "<h2>Estado del trato</h2>"
        + _table(
            ["Total cotizado", "Cobrado", "Saldo"],
            [
                [
                    _money(balance.get("deal_total"), currency),
                    _money(balance.get("collected"), currency),
                    _money(balance.get("remaining"), currency),
                ]
            ],
            ["", "", "dimension"],
        )
        + "<div class=\"signoff\"><div class=\"signature\"></div>"
        + "<p class=\"muted\">Recibido por</p></div></main>"
    )
    return body


def render_payment_receipt(
    payload: dict[str, object], *, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(_value(payload.get('receipt_code')))} — Comprobante de pago</title>"
        f"<style>{_CSS}</style></head><body>{_receipt_body(payload)}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA


def _dispatch_note_body(payload: dict[str, object]) -> str:
    order = _object(payload.get("order"), "invalid_dispatch_note_order")
    project = _object(payload.get("project"), "invalid_dispatch_note_project")
    totals = _object(payload.get("totals"), "invalid_dispatch_note_totals")
    dispatch = _object(payload.get("dispatch"), "invalid_dispatch_note_dispatch")
    units = payload.get("units") or []
    issued_at = _value(payload.get("issued_at"))
    note_code = _value(payload.get("note_code"))
    organization = payload.get("organization")
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        '<span class="tb-value">Guía de despacho</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Guía</span>'
        f'<span class="tb-value">{escape(note_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(issued_at))}</span></div>'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Orden</span>'
        f'<span class="tb-value">{escape(_value(order.get("code")))}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    body = (
        f'<main>{titleblock}'
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(note_code)}</strong><br>"
        f"Guía de despacho<br>{escape(_cldate(issued_at))}</div></div>"
    )
    body += (
        '<div class="rule-stack"></div>'
        "<h1>Guía de despacho</h1>"
        '<section class="hero"><p>Destinatario</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}</p>"
        f"<p>{escape(_value(project.get('delivery_address')))}</p>"
        f'<p class="total">'
        + ("Bultos" if units else "Unidades")
        + f': {escape(_value(totals.get("units")))}</p></section>'
    )
    if units:
        body += (
            "<h2>Bultos</h2>"
            + _table(
                ["Etiqueta", "Perfiles", "Refuerzos", "Vidrios", "Paneles", "Herrajes", "Accesorios"],
                [
                    [
                        unit.get("label_code"),
                        unit.get("profiles"),
                        unit.get("reinforcements"),
                        unit.get("glasses"),
                        unit.get("panels"),
                        unit.get("hardware"),
                        unit.get("fittings"),
                    ]
                    for unit in units
                ],
                ["", "dimension", "dimension", "dimension", "dimension", "dimension", "dimension"],
            )
        )
    else:
        body += (
            "<h2>Bultos</h2><p class=\"muted\">Sin manifiesto de embalaje "
            "registrado — la orden se despacha sin desglose por bulto.</p>"
        )
    note = _value(dispatch.get("note"))
    if note != "—":
        body += f"<p><strong>Nota:</strong> {escape(note)}</p>"
    body += (
        "<h2>Resumen de contenido</h2>"
        + _table(
            ["Perfiles", "Refuerzos", "Vidrios", "Paneles", "Herrajes", "Accesorios"],
            [
                [
                    totals.get("profiles"),
                    totals.get("reinforcements"),
                    totals.get("glasses"),
                    totals.get("panels"),
                    totals.get("hardware"),
                    totals.get("fittings"),
                ]
            ],
            ["dimension", "dimension", "dimension", "dimension", "dimension", "dimension"],
        )
        + "<div class=\"signoff\"><div class=\"signature\"></div>"
        + "<p class=\"muted\">Despachado por / Recibido conforme</p></div></main>"
    )
    return body


def render_dispatch_note(
    payload: dict[str, object], *, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(_value(payload.get('note_code')))} — Guía de despacho</title>"
        f"<style>{_CSS}</style></head><body>{_dispatch_note_body(payload)}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA


_TYPOLOGY_ES = {
    "FIXED": "Fijo",
    "TURN": "Abatible",
    "TILT": "Oscilante",
    "TILT_TURN": "Oscilobatiente",
    "SLIDING_2L": "Corredera 2 hojas",
    "SLIDING_3L": "Corredera 3 hojas",
    "SLIDING_4L": "Corredera 4 hojas",
    "SLIDING": "Corredera",
    "AWNING": "Proyectante",
    "DOOR_ENTRY": "Puerta",
    "DOOR_DOUBLE": "Puerta doble",
    "CORNER": "Esquinero",
    "BOW": "Ventana en arco",
    "FRAMELESS": "Vidrio sin marco",
    "COMPOSITE": "Conjunto",
}

_COLOR_ES = {
    "WHITE": "Blanco",
    "FOILED": "Foliado",
}

_CATEGORY_ES = {
    "PROFILE": "Perfil", "REINFORCEMENT": "Refuerzo", "GLASS": "Vidrio",
    "HARDWARE_KIT": "Kit herraje", "PANEL": "Panel",
    "ACCESSORY": "Accesorio", "FITTING": "Fijación",
}

_ROLE_ES = {
    "FRAME": "Marco", "SASH": "Hoja", "MULLION_V": "Montante",
    "MULLION_H": "Travesaño", "INVERSOR": "Inversor",
    "GLAZING_BEAD": "Juntaquillo", "COUPLER": "Cople",
    "ADDITIONAL": "Adicional", "THRESHOLD": "Umbral", "CHANNEL": "Canal",
}

_SLOT_ES = {
    "OUTER_TOP": "Lado superior marco",
    "OUTER_BOTTOM": "Lado inferior marco",
    "LEAF_TOP": "Lado superior hoja",
    "LEAF_BOTTOM": "Lado inferior hoja",
    "CENTER": "Centro",
    "left": "Izquierda", "right": "Derecha",
    "top": "Superior", "bottom": "Inferior",
}


def _finish(ci: object, ce: object) -> str:
    interior = _COLOR_ES.get(ci, ci)
    exterior = _COLOR_ES.get(ce, ce)
    return interior if interior == exterior else f"{interior} / {exterior}"


def finish_label(color_interior: object, color_exterior: object) -> str:
    """Public wrapper — non-document surfaces reuse the sealed finish label."""
    return _finish(color_interior, color_exterior)


def _invoice_body(payload: dict[str, object]) -> str:
    project = _object(payload.get("project"), "invalid_invoice_project")
    deal = _object(payload.get("deal"), "invalid_invoice_deal")
    balance = _object(payload.get("balance"), "invalid_invoice_balance")
    positions = payload.get("positions") or []
    issued_at = _value(payload.get("issued_at"))
    invoice_code = _value(payload.get("invoice_code"))
    revision = _value(payload.get("revision_code"))
    currency = _value(project.get("currency"))
    organization = payload.get("organization")
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        '<span class="tb-value">Factura</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Factura</span>'
        f'<span class="tb-value">{escape(invoice_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(issued_at))}</span></div>'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Revisión</span>'
        f'<span class="tb-value">{escape(revision)}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    body = (
        f'<main>{titleblock}'
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(invoice_code)}</strong><br>"
        f"Factura<br>{escape(_cldate(issued_at))}</div></div>"
        '<div class="rule-stack"></div>'
        "<h1>Factura</h1>"
        '<section class="hero"><p>Facturar a</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}"
        + (
            f" · {escape(_value(project.get('client_giro')))}"
            if _value(project.get("client_giro")) != "—"
            else ""
        )
        + (
            f" · {escape(_value(project.get('client_address')))}"
            if _value(project.get("client_address")) != "—"
            else (
                f" · {escape(_value(project.get('client_comuna')))}"
                if _value(project.get("client_comuna")) != "—"
                else ""
            )
        )
        + "</p>"
        f'<p class="total">Total: {escape(_money(deal.get("total_gross"), currency))}</p></section>'
    )
    if positions:
        body += (
            "<h2>Detalle</h2>"
            + _table(
                ["Posición", "Tipología", "Medidas (mm)", "Cantidad", "Neto"],
                [
                    [
                        position.get("position_index"),
                        _TYPOLOGY_ES.get(
                            _value(position.get("typology")),
                            _value(position.get("typology")),
                        ),
                        f"{_value(position.get('width_mm'))}\u00a0×\u00a0"
                        f"{_value(position.get('height_mm'))}"
                        + (
                            f" · {_value(position.get('location_tag'))}"
                            if _value(position.get("location_tag")) != "—"
                            else ""
                        ),
                        position.get("quantity"),
                        (
                            _money(position.get("price_net"), currency)
                            if position.get("price_net") not in (None, "")
                            else "—"
                        ),
                    ]
                    for position in positions
                ],
                ["", "", "", "dimension", "dimension"],
            )
        )
    payment_terms = _value(project.get("payment_terms"))
    if payment_terms != "—":
        body += f"<p><strong>Condiciones de pago:</strong> {escape(payment_terms)}</p>"
    body += (
        "<h2>Totales</h2>"
        + _table(
            ["Neto", "IVA", "Total", "Abonado", "Saldo"],
            [
                [
                    _money(deal.get("total_net"), currency),
                    _money(deal.get("total_tax"), currency),
                    _money(deal.get("total_gross"), currency),
                    _money(balance.get("collected"), currency),
                    _money(balance.get("amount_due"), currency),
                ]
            ],
            ["dimension", "dimension", "dimension", "dimension", "dimension"],
        )
        + "<div class=\"signoff\"><div class=\"signature\"></div>"
        + "<p class=\"muted\">Emitido por / Recibido conforme</p></div></main>"
    )
    return body


def render_project_invoice(
    payload: dict[str, object], *, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(_value(payload.get('invoice_code')))} — Factura</title>"
        f"<style>{_CSS}</style></head><body>{_invoice_body(payload)}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA


def _credit_note_body(payload: dict[str, object]) -> str:
    invoice = _object(payload.get("invoice"), "invalid_credit_note_invoice")
    project = _object(payload.get("project"), "invalid_credit_note_project")
    deal = _object(payload.get("deal"), "invalid_credit_note_deal")
    positions = payload.get("positions") or []
    issued_at = _value(payload.get("issued_at"))
    credit_code = _value(payload.get("credit_code"))
    invoice_code = _value(invoice.get("invoice_code"))
    revision = _value(payload.get("revision_code"))
    currency = _value((deal or {}).get("currency")) or _value(project.get("currency"))
    organization = payload.get("organization")
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        '<span class="tb-value">Nota de crédito</span></div>'
        f'<div class="tb-cell"><span class="tb-label">N. de crédito</span>'
        f'<span class="tb-value">{escape(credit_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(issued_at))}</span></div>'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Revisión</span>'
        f'<span class="tb-value">{escape(revision)}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    body = (
        f'<main>{titleblock}'
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(credit_code)}</strong><br>"
        f"Nota de crédito<br>{escape(_cldate(issued_at))}</div></div>"
        '<div class="rule-stack"></div>'
        "<h1>Nota de crédito</h1>"
        '<section class="hero"><p>Acreditar a</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}</p>"
        f'<p class="total">Crédito: {escape(_money(deal.get("total_gross"), currency))}</p></section>'
    )
    body += (
        f"<p><strong>Referencia:</strong> anula Factura {escape(invoice_code)}"
        + (
            f" emitida el {escape(_cldate(invoice.get('issued_at')))}"
            if invoice.get("issued_at")
            else ""
        )
        + "</p>"
    )
    reason = _value(payload.get("reason"))
    if reason != "—":
        body += f"<p><strong>Motivo:</strong> {escape(reason)}</p>"
    if positions:
        body += (
            "<h2>Detalle</h2>"
            + _table(
                ["Posición", "Tipología", "Medidas (mm)", "Cantidad", "Neto"],
                [
                    [
                        position.get("position_index"),
                        _TYPOLOGY_ES.get(
                            _value(position.get("typology")),
                            _value(position.get("typology")),
                        ),
                        f"{_value(position.get('width_mm'))}\u00a0×\u00a0"
                        f"{_value(position.get('height_mm'))}"
                        + (
                            f" · {_value(position.get('location_tag'))}"
                            if _value(position.get("location_tag")) != "—"
                            else ""
                        ),
                        position.get("quantity"),
                        (
                            _money(position.get("price_net"), currency)
                            if position.get("price_net") not in (None, "")
                            else "—"
                        ),
                    ]
                    for position in positions
                ],
                ["", "", "", "dimension", "dimension"],
            )
        )
    body += (
        "<h2>Totales acreditados</h2>"
        + _table(
            ["Neto", "IVA", "Total"],
            [
                [
                    _money(deal.get("total_net"), currency),
                    _money(deal.get("total_tax"), currency),
                    _money(deal.get("total_gross"), currency),
                ]
            ],
            ["dimension", "dimension", "dimension"],
        )
        + "<div class=\"signoff\"><div class=\"signature\"></div>"
        + "<p class=\"muted\">Emitido por / Recibido conforme</p></div></main>"
    )
    return body


def render_credit_note(
    payload: dict[str, object], *, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(_value(payload.get('note_code')))} — Nota de crédito</title>"
        f"<style>{_CSS}</style></head><body>{_credit_note_body(payload)}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA


def _delivery_pod_body(payload: dict[str, object], signature_b64: str) -> str:
    order = _object(payload.get("order"), "invalid_pod_order")
    project = _object(payload.get("project"), "invalid_pod_project")
    delivery = _object(payload.get("delivery"), "invalid_pod_delivery")
    receiver = _object(payload.get("receiver"), "invalid_pod_receiver")
    totals = _object(payload.get("totals"), "invalid_pod_totals")
    currency = project.get("currency")
    units = payload.get("units") or []
    payment = payload.get("payment")
    issued_at = _value(payload.get("issued_at"))
    confirmation_code = _value(payload.get("confirmation_code"))
    organization = payload.get("organization")
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        '<span class="tb-value">Comprobante de entrega</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Comprobante</span>'
        f'<span class="tb-value">{escape(confirmation_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(issued_at))}</span></div>'
        f'<div class="tb-cell tb-wide"><span class="tb-label">Orden</span>'
        f'<span class="tb-value">{escape(_value(order.get("code")))}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    body = (
        f'<main>{titleblock}'
        f'<div class="masthead">{_MITER}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(confirmation_code)}</strong><br>"
        f"Comprobante de entrega<br>{escape(_cldate(issued_at))}</div></div>"
        '<div class="rule-stack"></div>'
        "<h1>Comprobante de entrega</h1>"
        '<section class="hero"><p>Recibido por</p>'
        f"<h2>{escape(_value(receiver.get('name')))}</h2>"
        f"<p>RUT: {escape(_value(receiver.get('rut')))}</p>"
        f"<p>{escape(_value(delivery.get('address')))} · "
        f"{escape(_cldate(delivery.get('scheduled_date')))} "
        f"{escape(_value(delivery.get('time_window')))}</p>"
        f'<p class="total">'
        + ("Bultos" if units else "Unidades")
        + f': {escape(_value(totals.get("units")))}</p></section>'
    )
    if units:
        body += (
            "<h2>Bultos entregados</h2>"
            + _table(
                ["Etiqueta", "Perfiles", "Refuerzos", "Vidrios", "Paneles", "Herrajes", "Accesorios"],
                [
                    [
                        unit.get("label_code"),
                        unit.get("profiles"),
                        unit.get("reinforcements"),
                        unit.get("glasses"),
                        unit.get("panels"),
                        unit.get("hardware"),
                        unit.get("fittings"),
                    ]
                    for unit in units
                ],
                ["", "dimension", "dimension", "dimension", "dimension", "dimension", "dimension"],
            )
        )
    contact = _value(delivery.get("contact_name"))
    installer = _value(delivery.get("installer_name"))
    detail_rows = [
        ["Entrega programada", f"{_cldate(delivery.get('scheduled_date'))} · {_value(delivery.get('time_window'))}"],
        ["Contacto en sitio", contact],
        ["Cuadrilla", installer],
    ]
    body += "<h2>Entrega</h2>" + _table(
        ["Campo", "Valor"], detail_rows, ["", ""]
    )
    if payment:
        body += (
            "<h2>Cobro contra entrega</h2>"
            + _table(
                ["Medio", "Tipo", "Monto", "Referencia"],
                [
                    [
                        _PAYMENT_METHOD_ES.get(
                            _value(payment.get("method")), _value(payment.get("method"))
                        ),
                        _PAYMENT_KIND_ES.get(
                            _value(payment.get("kind")), _value(payment.get("kind"))
                        ),
                        _money(payment.get("amount"), currency),
                        payment.get("reference"),
                    ]
                ],
                ["", "", "dimension", ""],
            )
        )
    body += (
        "<h2>Firma del receptor</h2>"
        f'<img class="pod-signature" src="data:image/png;base64,{signature_b64}" alt="Firma">'
        '<div class="signoff"><div class="signature"></div>'
        f'<p class="muted">{escape(_value(receiver.get("name")))} — Recibido conforme</p></div></main>'
    )
    return body


def render_delivery_pod(
    payload: dict[str, object], *, signature_png: bytes, pdf_identifier: str
) -> tuple[bytes, str]:
    from weasyprint import HTML

    signature_b64 = base64.b64encode(signature_png).decode("ascii")
    html = (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{escape(_value(payload.get('confirmation_code')))} — Comprobante de entrega</title>"
        f"<style>{_CSS}"
        ".pod-signature{max-width:70mm;max-height:28mm;border:0.4pt solid "
        "#e5e7eb;border-radius:4px;padding:2mm;background:#fff}"
        f"</style></head><body>{_delivery_pod_body(payload, signature_b64)}</body></html>"
    )
    content = HTML(string=html, url_fetcher=_url_fetcher).write_pdf(
        pdf_identifier=pdf_identifier,
    )
    if not isinstance(content, bytes) or not content.startswith(b"%PDF-"):
        raise DocumentaryError("pdf_generation_failed")
    return content, _PDF_MEDIA
