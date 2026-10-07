"""Frozen-authority PDF producers for DOC-01, DOC-03 through DOC-07."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from html import escape
from pathlib import Path

import segno

from dekopen_engine.contour import Contour, contour_points
from dekopen_engine.models import (
    BayLeaf,
    HingeSide,
    OpeningDirection,
    OpeningMovement,
    Opening,
    OpeningSpec,
    PlanPoint,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SlidingTravel,
    UnitKind,
)
from dekopen_engine.opening_symbols import (
    ElevationView,
    GlyphPrimitive,
    glyph_paths,
    leaf_primitives,
    sliding_primitives,
)
from dekopen_engine.openings import opening_leaf_name_es, spec_display_name_es
from dekopen_engine.product import ElevationMember, elevation_layout
from documents.brand import effective_brand_color
from documents.repository import DocumentaryError
from engine_api.adapter import (
    InvalidEngineRequest,
    _parse_leaves,
    _parse_opening,
    parse_product_model,
)

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


def _font_face(family: str, weight: int, filename: str, *, embedded: bool = False) -> str:
    """`file://` para el PDF sellado (lo resuelve el url_fetcher congela-
    do); `data:` para la vista previa en pantalla, cuyo <iframe> no puede
    leer el disco del servidor."""
    if embedded:
        uri = "data:font/truetype;base64," + base64.b64encode(
            (_FONTS_DIR / filename).read_bytes()
        ).decode("ascii")
    else:
        uri = (_FONTS_DIR / filename).as_uri()
    return (
        "@font-face {"
        f" font-family: '{family}'; font-style: normal; font-weight: {weight};"
        f" src: url('{uri}') format('truetype');"
        " }"
    )


_FONT_FILES = (
    ("IBM Plex Sans", 400, "IBMPlexSans-400.ttf"),
    ("IBM Plex Sans", 500, "IBMPlexSans-500.ttf"),
    ("IBM Plex Sans", 600, "IBMPlexSans-600.ttf"),
    ("IBM Plex Sans", 700, "IBMPlexSans-700.ttf"),
    ("IBM Plex Mono", 400, "IBMPlexMono-400.ttf"),
    ("IBM Plex Mono", 500, "IBMPlexMono-500.ttf"),
)

_FONTS = "".join(_font_face(*spec) for spec in _FONT_FILES)


@lru_cache(maxsize=1)
def _fonts_embedded() -> str:
    return "".join(_font_face(*spec, embedded=True) for spec in _FONT_FILES)

_CSS_BODY = """
@page { size: letter portrait; margin: 13mm 12mm 22mm; @bottom-center { content: element(titleblock); } }
* { box-sizing: border-box; } body { color: #161C1F; font: 9.5pt 'IBM Plex Sans', sans-serif; margin: 0; }
.titleblock { position: running(titleblock); display: table; width: 100%; border-collapse: collapse; border-top: 1.5pt solid #075F5A; font-family: 'IBM Plex Mono', monospace; }
.titleblock .tb-row { display: table-row; }
.titleblock .tb-cell { display: table-cell; border-left: 0.5pt solid #CDD5D6; border-bottom: 0.5pt solid #CDD5D6; padding: 1.2mm 2mm; vertical-align: top; }
.titleblock .tb-cell:first-child { border-left: none; padding-left: 0; }
.titleblock .tb-wide { width: 34%; }
/* Fila legal del cajetín: emisor + huella, en pequeño — los datos de la
   primera fila (folio, rev, página) mandan siempre. */
.titleblock .tb-legal .tb-cell { padding: 0.8mm 2mm; }
.titleblock .tb-legal .tb-label { font-size: 5.5pt; margin-bottom: 0.3mm; }
.titleblock .tb-legal .tb-value { font-size: 6pt; font-weight: 400; }
.tb-label { display: block; font: 7pt 'IBM Plex Sans', sans-serif; text-transform: uppercase; letter-spacing: 0.5pt; color: #727D82; margin-bottom: 0.6mm; }
.tb-value { display: block; font: 8pt 'IBM Plex Mono', monospace; color: #252D31; overflow-wrap: break-word; }
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
th { color: #465158; font: 7pt 'IBM Plex Sans', sans-serif; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5pt; text-align: left; border-bottom: 0.9pt solid #465158; padding: 1.4mm 1.8mm; }
td { border-bottom: 0.5pt solid #CDD5D6; padding: 1.6mm 1.8mm; vertical-align: top; overflow-wrap: break-word; hyphens: manual; orphans: 2; widows: 2; }
tbody tr:last-child td { border-bottom: 0.9pt solid #465158; }
.workshop h1 { font-size: 14pt; } .workshop th { background: #252D31; color: #FCFDFC; }
.dimension { font: 11pt 'IBM Plex Mono', monospace; font-weight: 500; color: #161C1F; }
.hash { font: 6.5pt 'IBM Plex Mono', monospace; color: #465158; overflow-wrap: anywhere; }
.qc-box { display: inline-block; width: 3.2mm; height: 3.2mm; border: 0.45mm solid #111;
    vertical-align: -0.5mm; }
.bar-band { break-inside: avoid; display: inline-block; width: 100%; margin-bottom: 4mm; }
.bar-svg { width: 100%; height: auto; display: block; }
.bar-svg text { font-family: 'IBM Plex Mono', monospace; }
.break-avoid { break-inside: avoid; } h2, h3 { break-after: avoid; } .blank { display: inline-block; width: 5mm; height: 5mm; border: 1px solid #252D31; vertical-align: middle; }
.confidential { color: #991B1B; font-weight: 600; font-size: 6.5pt; text-transform: uppercase; letter-spacing: 0.8pt; }
.voided-banner { border: 1.5pt solid #991B1B; color: #991B1B; padding: 3mm 5mm; margin: 3mm 0; break-inside: avoid; }
.tributary-note { border: 0.75pt solid #465158; color: #252D31; padding: 2mm 4mm; margin: 2.5mm 0; font-size: 7.5pt; letter-spacing: 0.2pt; break-inside: avoid; }
.voided-banner p { margin: 0; } .voided-title { font-size: 16pt; font-weight: 700; letter-spacing: 2pt; margin-bottom: 1.5mm; }
.muted { color: #727D82; } .signature { height: 15mm; border-bottom: 0.5pt solid #465158; margin-top: 6mm; }
.signoff { break-inside: avoid; }
.keep { break-inside: avoid; }
.sign-row { display: flex; gap: 8mm; margin-top: 3mm; margin-bottom: 6mm; }
.sign-cell { flex: 1; height: 9mm; border-bottom: 0.5pt solid #465158; position: relative; }
.sign-cell.sign-date { flex: 0 0 22mm; }
.sign-label { position: absolute; bottom: -4.5mm; left: 0; font: 600 7pt 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: 0.08em; color: #727D82; }
table tr { break-inside: avoid; }
.sol-table td.dimension, table td.dimension { text-align: right; overflow-wrap: break-word; }
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

/* ── Supplier-facing purchase order (DOC-04/DOC-08) ─────────────────
   A PO is a contract document between two parties: buyer block and
   supplier block side by side, then the order meta strip. Table stays
   in workshop register — it is a technical order, not a proposal. */
.po-parties { display: flex; gap: 6mm; margin: 2mm 0 3mm; }
.po-party { flex: 1; border: 0.9pt solid #465158; padding: 2.5mm 3mm; break-inside: avoid; }
.po-party .po-party-role { font: 600 6pt 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: 0.9pt; color: #727D82; margin-bottom: 1.2mm; }
.po-party .po-party-name { font: 700 10.5pt 'IBM Plex Sans', sans-serif; margin-bottom: 0.8mm; }
.po-party .po-party-line { font-size: 7.5pt; color: #465158; line-height: 1.5; }
.po-meta { display: flex; border: 0.9pt solid #465158; border-top: none; margin: -3mm 0 3mm; }
.po-meta .tb-cell { display: table-cell; border-left: 0.5pt solid #CDD5D6; padding: 1.6mm 2mm; vertical-align: top; flex: 1; }
.po-meta .tb-cell:first-child { border-left: none; }
.po-meta .tb-label { display: block; font: 600 6pt 'IBM Plex Mono', monospace; text-transform: uppercase; letter-spacing: 0.7pt; color: #727D82; margin-bottom: 0.6mm; }
.po-meta .tb-value { font-size: 9pt; font-weight: 600; }
.po-meta .tb-value.po-needed { color: #991B1B; font-weight: 700; }

/* ── Commercial proposal language (DOC-01) ───────────────────────────
   Same type family and tokens, different composition: a real cover, a
   stat-level summary, product cards instead of a data table, and a
   dedicated investment block. Nothing here styles workshop docs. */
.commercial h1 { font-size: 19pt; letter-spacing: -0.3pt; }
.commercial h2 { font-size: 12.5pt; border-bottom: none; margin: 7mm 0 3mm; break-after: avoid; break-inside: avoid; }
.commercial h2::after { content: ""; display: block; width: 14mm; height: 1.4mm; background: #E56A32; margin-top: 1.6mm; }
.kicker { font-size: 7.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 1.6pt; color: #0B7770; margin: 0 0 2mm; }
.cover { break-after: page; }
.cover-top { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1.5pt solid #075F5A; padding-bottom: 5mm; }
.cover-top .brand { font-size: 15pt; }
.cover-top .brand-logo { max-height: 16mm; max-width: 62mm; }
.cover-doc { text-align: right; font: 8pt 'IBM Plex Mono', monospace; color: #465158; line-height: 1.7; }
.cover-doc strong { display: block; font: 600 11pt 'IBM Plex Sans', sans-serif; color: #161C1F; letter-spacing: 0.2pt; }
.cover-main { display: flex; gap: 10mm; align-items: center; margin: 32mm 0 14mm; }
.cover-left { flex: 1; }
.cover-client { font-size: 24pt; font-weight: 600; letter-spacing: -0.4pt; margin: 0 0 2.5mm; }
.cover-project { font-size: 11pt; color: #252D31; margin: 0 0 1mm; }
.cover-meta { color: #727D82; font-size: 8.5pt; line-height: 1.75; margin-top: 4mm; }
.cover-figure { width: 82mm; flex: 0 0 82mm; background: #F5F7F7; border: 0.25pt solid #E2E7E7; padding: 4mm 4mm 2mm; }
.cover-figure svg { max-height: 105mm; display: block; margin: 0 auto; }
.cover-figure .figcap { font: 7pt 'IBM Plex Sans', sans-serif; color: #727D82; text-align: center; margin-top: 2mm; }
.cover-invest { display: flex; border: 1pt solid #075F5A; padding: 4mm 0; }
.inv-cell { flex: 1; padding: 0 5mm; border-left: 0.5pt solid #CDD5D6; }
.inv-cell:first-child { border-left: none; }
.inv-cell span { display: block; font-size: 6.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7pt; color: #727D82; margin-bottom: 1.2mm; }
.inv-cell strong { font-size: 10.5pt; font-weight: 600; color: #161C1F; }
.inv-cell.inv-total strong { font-size: 15pt; color: #075F5A; }
.cover-foot { margin-top: 5mm; font-size: 7.5pt; color: #727D82; line-height: 1.6; }
.dochead { border-bottom: 1.5pt solid #075F5A; padding-bottom: 4mm; margin-bottom: 6mm; }
.dochead .cover-top { border-bottom: none; padding-bottom: 0; }
.dochead-client { font-size: 10.5pt; color: #161C1F; margin: 4.5mm 0 0; }
.dochead-client .kicker { margin: 0 1mm 0 0; }
.dochead .cover-invest { margin-top: 3.5mm; }
.dochead .cover-foot { margin-top: 2.5mm; }
/* Long client/project/typology names wrap inside their column — a width
   guard, never a truncation. */
.cover-client, .cover-project, .dochead-client, .pcard-body h3,
.pcard-specs li, .pcard-dims { overflow-wrap: break-word; }
.stat-strip { display: flex; border: 0.5pt solid #CDD5D6; border-left: 2pt solid #075F5A; margin: 0 0 5mm; }
.stat-cell { flex: 1; padding: 2.6mm 4mm; border-left: 0.5pt solid #CDD5D6; }
.stat-cell:first-child { border-left: none; }
.stat-cell .stat-n { display: block; font: 600 13pt 'IBM Plex Sans', sans-serif; color: #161C1F; }
.stat-cell .stat-k { display: block; font-size: 6.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6pt; color: #727D82; margin-top: 0.8mm; }
.chips { margin: 2mm 0 0; }
.chips span { display: inline-block; border: 0.5pt solid #CDD5D6; border-radius: 2pt; padding: 0.8mm 2.4mm; margin: 0 1.5mm 1.5mm 0; font-size: 7.5pt; color: #465158; }
/* block layout (not flex-wrap) so WeasyPrint can paginate between cards */
.pcards { display: block; margin: 2mm 0 4mm; }
.pcard { display: flex; width: 100%; border: 0.75pt solid #CDD5D6; margin: 0 0 5mm; break-inside: avoid; }
.pcard-fig { flex: 0 0 62mm; padding: 5mm 4mm; border-right: 0.5pt solid #CDD5D6; background: #F2F5F4; display: flex; align-items: center; justify-content: center; }
.pcard-fig svg { max-height: 62mm; max-width: 54mm; }
.pcard-body { flex: 1; padding: 4mm 5mm; }
.pcard-body h3 { margin: 0 0 1mm; font-size: 12pt; }
.pcard-dims { font: 500 10pt 'IBM Plex Mono', monospace; color: #075F5A; margin: 0 0 2.5mm; }
.pcard-specs { margin: 0; padding: 0; list-style: none; font-size: 8pt; color: #465158; line-height: 1.7; }
.pcard-specs li { margin: 0; }
.pcard-specs .plabel { color: #727D82; font-size: 6.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5pt; }
.pcard-price { flex: 0 0 40mm; padding: 4mm 5mm; text-align: right; background: #F5F7F6; }
.pcard-price .plabel { display: block; font-size: 6.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5pt; color: #727D82; margin: 2mm 0 0.5mm; }
.pcard-price .plabel:first-child { margin-top: 0; }
.pcard-price strong { font-size: 10.5pt; }
.pcard-price strong.line { display: block; font-size: 13pt; color: #075F5A; }
.pcard-price .off { display: inline-block; background: #E56A32; color: #FCFDFC; font-size: 6.5pt; font-weight: 600; letter-spacing: 0.5pt; padding: 0.6mm 2mm; border-radius: 2pt; }
.pcards.compact .pcard { margin-bottom: 4mm; }
.pcards.compact .pcard-fig { flex: 0 0 50mm; padding: 3mm; }
.pcards.compact .pcard-fig svg { max-height: 34mm; max-width: 44mm; }
.pcards.compact .pcard-body { padding: 3mm 4mm; }
.pcards.compact .pcard-body h3 { font-size: 10.5pt; }
.pcards.compact .pcard-price { flex: 0 0 36mm; padding: 3mm 4mm; }
.invest { display: flex; gap: 8mm; align-items: stretch; margin: 2mm 0 4mm; }
.invest-panel { flex: 0 0 74mm; background: #075F5A; color: #FCFDFC; padding: 5mm 6mm; break-inside: avoid; }
.invest-panel .inv-row { display: flex; justify-content: space-between; font-size: 8.5pt; padding: 1.4mm 0; border-bottom: 0.5pt solid #0B7770; }
.invest-panel .inv-total-row { font-size: 13pt; font-weight: 600; border-bottom: none; padding-top: 2.5mm; }
.invest-note { flex: 1; font-size: 8.5pt; color: #465158; line-height: 1.7; }
.invest-note p { margin: 0 0 1.5mm; }
.service-lines { margin: 0 0 5mm; }
.service-lines h3 { margin: 0 0 1.5mm; font-size: 10pt; }
.service-lines ul { margin: 0; padding: 0; list-style: none; font-size: 8.5pt; color: #252D31; }
.service-lines li { padding: 1mm 0; border-bottom: 0.5pt solid #CDD5D6; }
.service-lines p { margin: 0; font-size: 8.5pt; color: #465158; line-height: 1.7; }
.service-lines .service-note { margin-top: 1.2mm; font-size: 7.5pt; color: #727D82; }
.terms { border-left: 2pt solid #CDD5D6; padding-left: 5mm; }
.terms p { margin: 1.2mm 0; }
.terms .tlabel { color: #727D82; font-size: 6.5pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5pt; }
.doc-col { break-inside: avoid; }
.doc-duo { display: flex; gap: 9mm; align-items: flex-start; break-inside: avoid; }
.doc-duo .doc-col { flex: 1; min-width: 0; }
.doc-duo h2 { margin-top: 4mm; }
.doc-duo .invest { flex-direction: column; gap: 4mm; margin: 2mm 0 0; }
.doc-duo .invest-panel { flex: 0 0 auto; }
.accept { break-inside: avoid; margin-top: 4mm; }
.accept h2 { margin-top: 0; }
.sign-col .sign-cell { margin-bottom: 9mm; }
.sign-col .sign-cell:last-child { margin-bottom: 0; }
.accept-recap { font-size: 8.5pt; color: #465158; margin-bottom: 3mm; }

/* ── DOC-01 v2 (P09) — lectura comercial de presupuesto ────────────
   Cajetín en dos filas, tabla de posiciones de columnas fijas, fichas
   Musterangebot con campos numerados y cotas por campo, resumen
   comercial con desglose y aceptación con QR. */
.dochead-meta { margin-top: 2mm; }
table.resumen th, table.resumen td { font-size: 7.5pt; }
table.resumen td { overflow-wrap: break-word; }
table.resumen tfoot td { border-bottom: none; border-top: 0.9pt solid #465158; font: 600 7pt 'IBM Plex Sans', sans-serif; text-transform: uppercase; letter-spacing: 0.5pt; }
table.resumen tfoot td.dimension { font-size: 9pt; }
table.mini td.mini-fig { padding: 1mm; vertical-align: middle; }
table.mini td.mini-fig svg { max-height: 13mm; margin: 0 auto; }
.pcard { display: block; }
.pcard-head { display: flex; justify-content: space-between; align-items: baseline; gap: 4mm; border-bottom: 0.5pt solid #CDD5D6; padding: 2.2mm 4mm 1.8mm; }
.pcard-title { font: 600 9pt 'IBM Plex Sans', sans-serif; color: #161C1F; }
.pcard-money { font: 8pt 'IBM Plex Mono', monospace; color: #252D31; white-space: nowrap; }
.pcard-money .off { display: inline-block; background: #E56A32; color: #FCFDFC; font-size: 6.5pt; font-weight: 600; letter-spacing: 0.5pt; padding: 0.6mm 2mm; border-radius: 2pt; margin-left: 1.5mm; }
.pcard-cols { display: flex; width: 100%; }
.pcard-campo-head { margin-top: 1.6mm; }
.pcard-campo { padding-left: 3.5mm; font-size: 7.5pt; }
.pcards.compact .pcard-head { padding: 1.6mm 3mm 1.4mm; }
.pcards.compact .pcard-title { font-size: 8pt; }
.pcards.compact .pcard-money { font-size: 7pt; }
.accept-online { display: flex; gap: 4mm; align-items: center; border: 0.75pt solid #CDD5D6; padding: 3mm; margin: 0 0 3.5mm; }
.accept-online .qr svg { width: 20mm; height: 20mm; display: block; }
.accept-online-copy { font-size: 8pt; color: #252D31; overflow-wrap: anywhere; }
.accept-online-copy a { color: #075F5A; text-decoration: none; font-family: 'IBM Plex Mono', monospace; font-size: 6.8pt; }
"""
_CSS = _FONTS + _CSS_BODY
_CSS_EMBEDDED = _fonts_embedded() + _CSS_BODY



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


def _spec_value(value: object) -> str:
    """Order-line spec detail — nested structures flatten to 'k=v' pairs so a
    structured spec never crashes the renderer."""
    if isinstance(value, dict):
        return "; ".join(
            f"{key}={_spec_value(val)}"
            for key, val in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, list):
        return ", ".join(_spec_value(item) for item in value)
    return _value(value)


def _hardware_sellable_line(position_ref: object) -> str:
    """Sellable hardware for the client document (D04): handle model +
    colour and chosen options — never the class, kit BOM or internals.
    Only emitted when the sealed BOM carries a declared selection."""
    if not isinstance(position_ref, dict):
        return ""
    snapshot = position_ref.get("bom_snapshot")
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except ValueError:
            snapshot = None
    if not isinstance(snapshot, dict):
        return ""
    parts: list[str] = []
    options: list[str] = []
    seen_options: set[str] = set()
    for item in snapshot.get("hardware_items") or []:
        if not isinstance(item, dict):
            continue
        model = item.get("handle_model_name")
        if model:
            color = item.get("handle_color_name")
            parts.append(
                f"Manilla {model}" + (f" · {color}" if color else "")
            )
        for name in item.get("option_names") or []:
            if name and name not in seen_options:
                seen_options.add(name)
                options.append(name)
    parts.extend(options)
    return "; ".join(dict.fromkeys(parts))


def _group(digits: str, sep: str) -> str:
    """Agrupa de a tres la parte entera — 2400 → '2\u2009400' (mm) o
    1435471 → '1.435.471' (pesos)."""
    groups: list[str] = []
    while len(digits) > 3:
        groups.append(digits[-3:])
        digits = digits[:-3]
    groups.append(digits)
    return sep.join(reversed(groups))


def _es_decimal(number: Decimal, decimals: int) -> str:
    """Formato es-CL: separador de miles punto y decimal coma —
    1234.5 con 2 decimales → '1.234,50'."""
    quant = Decimal(1).scaleb(-decimals)
    text = format(number.quantize(quant), f",.{decimals}f")
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _fmt_mm(number: Decimal) -> str:
    """§3.3: milímetros agrupados con espacio fino (U+2009) — '2 400';
    con precisión declarada el decimal va con coma — '1 249,5'."""
    text = format(number, "f")
    int_part, _, frac = text.partition(".")
    grouped = _group(int_part, "\u2009")
    return f"{grouped},{frac}" if frac else grouped


def _pct(value: object) -> str:
    """Porcentajes imprimen a un decimal con coma — '93,5', no '93.4667'."""
    if value is None:
        return "—"
    try:
        return _es_decimal(Decimal(str(value)).quantize(Decimal("0.1")), 1)
    except (InvalidOperation, ValueError):
        return _value(value)


def _dim(value: object) -> str:
    """Millimetre display §3.3 — strips stored trailing zeros so a dimension
    never prints as `1200.00 mm`, then groups with thin space: `1 200`."""
    if value is None:
        return "—"
    try:
        return _fmt_mm(Decimal(str(value)).normalize())
    except InvalidOperation:
        return _value(value)


class _Raw(str):
    """Marks a cell that renders its HTML verbatim inside `_table` — only for
    hardcoded markup (e.g. a drawn checkbox), never for payload content."""


def _cell(value: object, class_name: str = "") -> str:
    css = f' class="{escape(class_name)}"' if class_name else ""
    if isinstance(value, _Raw):
        return f"<td{css}>{value}</td>"
    return f"<td{css}>{escape(_value(value))}</td>"


def _row(values: list[object], classes: list[str] | None = None) -> str:
    styles = classes or [""] * len(values)
    return "<tr>" + "".join(_cell(value, styles[index]) for index, value in enumerate(values)) + "</tr>"


def _table(
    headers: list[str],
    rows: list[list[object]],
    classes: list[str] | None = None,
    thead_extra: str = "",
) -> str:
    head = "<tr>" + "".join(f"<th>{escape(header)}</th>" for header in headers) + "</tr>"
    return "<table><thead>" + thead_extra + head + "</thead><tbody>" + "".join(
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


def _miter(accent: str) -> str:
    return (
        '<svg class="miter" width="8mm" height="8mm" viewBox="0 0 32 32" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="M0,0 L32,0 L32,32 Z" fill="{_PAPER}" stroke="{accent}" '
        'stroke-width="2"/></svg>'
    )


def _brand_accent(organization: dict | None) -> str:
    """Acento de marca del masthead: el primario declarado por la org cuando
    pasa la validación AA contra papel; teal-800 (la marca propia) en caso
    contrario. Documento white-label: el acento acompaña al emisor, no a
    DEKOPEN."""
    if isinstance(organization, dict):
        color, passed = effective_brand_color(organization.get("brand_color"))
        if passed:
            return color
    return _TEAL_800



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
    """White-label masthead brand: the org's logo or commercial name leads,
    colored by its declared primario (AA-checked). 'Generado con DEKOPEN'
    only prints when the org opted in (`doc_dekopen_credit`) — client
    documents are white-label by default. A snapshot frozen before branding
    renders the bare DEKOPEN wordmark."""
    org = organization if isinstance(organization, dict) else {}
    uri = _logo_uri(org)
    accent = _brand_accent(org)
    name = (
        _value(org.get("commercial_name"))
        if _value(org.get("commercial_name")) != "—"
        else _value(org.get("name"))
    )
    if uri:
        # Logo + commercial name together — the name must survive the logo.
        name_line = (
            f'<div class="brand" style="font-size:9pt;letter-spacing:1.2pt;'
            f'color:{accent}">{escape(name)}</div>'
            if name != "—"
            else ""
        )
        brand = f'<img class="brand-logo" src="{uri}" alt="">{name_line}'
    else:
        if name == "—":
            brand = '<div class="brand">DEKOPEN<span class="mark"></span></div>'
        else:
            brand = f'<div class="brand" style="color:{accent}">{escape(name)}</div>'
    attribution = (
        '<div class="brand-sub">Generado con DEKOPEN</div>'
        if org.get("name") and org.get("doc_dekopen_credit")
        else ""
    )
    return f"<div>{brand}{attribution}</div>"


_SVG_INSET = Decimal("0.06")


def _money(amount: object, currency: object) -> str:
    """§3.3: CLP sin decimales '$1.435.471', USD 'US$ 1.234,50',
    UF 'UF 38,4521'. Otras monedas conservan su código con 2 decimales."""
    value = _num(amount)
    code = _value(currency)
    if code == "CLP":
        return f"${_es_decimal(value, 0)}"
    if code == "USD":
        return f"US$ {_es_decimal(value, 2)}"
    if code == "UF":
        return f"UF {_es_decimal(value, 4)}"
    return f"{code} {_es_decimal(value, 2)}"


def _cldate(raw: object) -> str:
    text = _value(raw)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return f"{text[8:10]}-{text[5:7]}-{text[0:4]}"
    return text[:10]


def _discount_label(raw: object) -> str:
    """discount_pct is a fraction (0.10 = 10%); values > 1 are already percent.
    Whole percents read '10 %', fractional ones '12,5 %'."""
    value = _num(raw)
    if value <= 1:
        value = value * 100
    if value == value.to_integral_value():
        return f"{_es_decimal(value, 0)} %"
    return f"{_pct(value)} %"


def _rev_display(raw: object) -> str:
    """'REV-A' reads 'A' under a Rev. label — the folio keeps the full code."""
    text = _value(raw)
    return text[4:] if text.upper().startswith("REV-") else text



def _num(value: object) -> Decimal:
    if isinstance(value, bool):
        raise DocumentaryError("svg_dimension_invalid")
    if isinstance(value, (Decimal, int)):
        number = Decimal(value)
    elif isinstance(value, str):
        try:
            number = Decimal(value)
        except ArithmeticError:
            raise DocumentaryError("svg_dimension_invalid") from None
    else:
        raise DocumentaryError("svg_dimension_invalid")
    # NaN/±Infinity reach Decimal through payload strings — geometry math on
    # them raises InvalidOperation mid-render instead of rejecting here.
    if not number.is_finite():
        raise DocumentaryError("svg_dimension_invalid")
    return number


def _pt(value: Decimal) -> str:
    return format(value.normalize(), "f")


# Drawing palettes — the technical elevation (workshop/docs) keeps the
# flat teal-on-paper look; the commercial figure renders the same sealed
# geometry with product materials: finish-colored profiles, tinted glass
# with a sheen, and real hardware marks (hinges on the hinge edge, lever
# on the free edge). Presentation only — geometry and authority unchanged.
_PAL_TECH = {
    "frame_fill": "none", "frame_edge": _TEAL_800,
    "bay_fill": _TEAL_50, "bay_edge": _TEAL_800,
    "split": _G_700, "glyph": _TEAL_800, "accent": _MARK,
    "sheen": None, "hardware": None, "label": _G_500,
}


def _darken_hex(value: str, *, amount: float = 0.55) -> str:
    """Derive the stroke/edge tone from a declared hex — presentation
    only, the fill stays the declared authority."""
    digits = value.lstrip("#")
    r, g, b = (int(digits[i:i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(
        f"{int(channel * amount):02X}" for channel in (r, g, b)
    )


def _commercial_palette(position: dict[str, object]) -> dict[str, str | None]:
    """Profile finish → rendered face color. D05 seals the resolved finish
    option (with its declared linear-sRGB render color) on the position —
    when it exists, that hex is the authority. Older positions carry only a
    finish label (WHITE/FOILED + org-entered names), so map the common
    material words and stay neutral-grey on anything unrecognized — never
    invent a wood grain or anthracite that wasn't declared."""
    detail = position.get("color_exterior_detail")
    declared = detail.get("render_color") if isinstance(detail, dict) else None
    if isinstance(declared, str) and declared.startswith("#"):
        fill = declared
        edge = _darken_hex(declared)
    else:
        color = str(position.get("color_exterior") or "").upper()
        if color == "FOILED" or "FOIL" in color or "WOOD" in color or "MADERA" in color or "ROBLE" in color:
            fill, edge = "#7B5A3B", "#4E3A24"
        elif "ANTRAC" in color or "GRIS" in color or "GREY" in color or "NEGRO" in color or "BLACK" in color:
            fill, edge = "#3B4045", "#20242A"
        else:
            fill, edge = "#EEF0ED", "#98A2A5"
    return {
        "frame_fill": fill, "frame_edge": edge,
        "bay_fill": "#DCEBEE", "bay_edge": edge,
        "split": edge, "glyph": "#4A7B78", "accent": _MARK,
        "sheen": "#FFFFFF", "hardware": "#3C4346", "label": _G_500,
    }


def _hardware_marks(opening: str, handedness: str, ix: Decimal, iy: Decimal,
                    iw: Decimal, ih: Decimal, out: list[str],
                    pal: dict[str, str | None]) -> None:
    """Lever + hinge marks on the leaf — commercial figures only. Hinge
    side follows the same DIN convention as the 3D scene: the opening name
    (or declared door handedness) is the hinge edge; the lever sits on the
    free edge at handle height."""
    hw = pal.get("hardware")
    if not hw:
        return
    hinge_left: bool | None = None
    if opening in ("TURN_LEFT", "TILT_TURN_LEFT"):
        hinge_left = True
    elif opening in ("TURN_RIGHT", "TILT_TURN_RIGHT"):
        hinge_left = False
    elif opening == "DOOR_ENTRY":
        hinge_left = handedness != "RIGHT"
    w_tick = max(iw * Decimal("0.022"), Decimal("0.9"))
    lever_w = max(iw * Decimal("0.03"), Decimal("1.1"))
    lever_h = ih * Decimal("0.085")
    lever_y = iy + ih * Decimal("0.52")
    if opening == "DOOR_DOUBLE":
        # Meeting stiles: a lever on each leaf's inner edge.
        for cx in (ix + iw / 2 - lever_w * Decimal("1.4"), ix + iw / 2 + lever_w * Decimal("0.4")):
            out.append(
                f'<rect x="{_pt(cx)}" y="{_pt(lever_y)}" width="{_pt(lever_w)}" '
                f'height="{_pt(lever_h)}" rx="{_pt(lever_w / 2)}" fill="{hw}"/>'
            )
    elif hinge_left is not None:
        hx = ix if hinge_left else ix + iw - w_tick
        # Fitting schedule — doors hang on 3+ hinges, windows on 2; the
        # figure follows the 3D scene's leaf-height rule.
        door = opening == "DOOR_ENTRY"
        fracs = (
            (Decimal("0.12"), Decimal("0.38"), Decimal("0.62"), Decimal("0.88"))
            if door and ih > 2200
            else (Decimal("0.14"), Decimal("0.50"), Decimal("0.86"))
            if door
            else (Decimal("0.16"), Decimal("0.84"))
        )
        for frac in fracs:
            hy = iy + ih * frac - ih * Decimal("0.045")
            out.append(
                f'<rect x="{_pt(hx)}" y="{_pt(hy)}" width="{_pt(w_tick)}" '
                f'height="{_pt(ih * Decimal("0.09"))}" fill="{hw}"/>'
            )
        lx = ix + iw - lever_w * Decimal("1.6") if hinge_left else ix + lever_w * Decimal("0.6")
        out.append(
            f'<rect x="{_pt(lx)}" y="{_pt(lever_y)}" width="{_pt(lever_w)}" '
            f'height="{_pt(lever_h)}" rx="{_pt(lever_w / 2)}" fill="{hw}"/>'
        )
    elif opening == "AWNING":
        out.append(
            f'<rect x="{_pt(ix + iw / 2 - lever_w / 2)}" y="{_pt(iy + ih - lever_h * Decimal("1.5"))}" '
            f'width="{_pt(lever_w)}" height="{_pt(lever_h)}" '
            f'rx="{_pt(lever_w / 2)}" fill="{hw}"/>'
        )


def _glyph_paths_out(
    prims: list[GlyphPrimitive],
    x: Decimal,
    y: Decimal,
    w: Decimal,
    h: Decimal,
    out: list[str],
    pal: dict[str, str | None],
    stroke_mm: Decimal,
    *,
    leaf_bottom: Decimal | None = None,
    inferred_opacity: bool = True,
) -> None:
    """Emit the contract's canonical path data — the same strings the
    canvas draws (engine/tests/fixtures/symbols pins both sides)."""
    for prim, (path_d, dash) in zip(
        prims, glyph_paths(prims, x, y, w, h, leaf_bottom=leaf_bottom)
    ):
        attrs = ""
        if dash:
            dsh = f"{_pt(stroke_mm * Decimal('2.4'))} {_pt(stroke_mm * Decimal('2'))}"
            attrs += f' stroke-dasharray="{dsh}"'
        if prim.inferred and inferred_opacity:
            attrs += ' stroke-opacity="0.72"'
        # The door sill is a threshold accent, not a glyph mark — keep the
        # orange the factory reads as "walkable edge" on both palettes.
        color = pal["accent"] if prim.k == "sill" else pal["glyph"]
        out.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" '
            f'stroke-width="{_pt(stroke_mm)}"{attrs}/>'
        )


def _parse_sliding_layout(raw: object) -> SlidingLayout | None:
    """Rebuild a ``SlidingLayout`` from a frozen-tree dict.

    Engine models require enum *instances*, and frozen payloads store the
    string values — coerce ``kind``/``travel`` before constructing, or
    every issued sliding document silently degrades to the 2-panel
    schematic. Returns None when the dict is not a usable layout."""
    if not isinstance(raw, dict):
        return None
    raw_panels = raw.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        return None
    panels: list[SlidingPanel] = []
    for i, raw_panel in enumerate(raw_panels):
        if not isinstance(raw_panel, dict):
            return None
        try:
            kind = SlidingPanelKind(str(raw_panel.get("kind") or "MOVING"))
            travel_raw = raw_panel.get("travel")
            travel = SlidingTravel(str(travel_raw)) if travel_raw else None
            track_raw = raw_panel.get("track")
            panels.append(
                SlidingPanel(
                    slot=str(raw_panel.get("slot") or f"P{i + 1}"),
                    kind=kind,
                    track=int(track_raw) if track_raw is not None else None,
                    travel=travel,
                )
            )
        except (TypeError, ValueError):
            return None
    primary_raw = raw.get("primary_index")
    try:
        return SlidingLayout(
            tracks=int(raw.get("tracks") or 1),
            panels=panels,
            primary_index=int(primary_raw) if primary_raw is not None else None,
        )
    except (TypeError, ValueError):
        return None


def _bay_slide_movement(node: dict[str, object]) -> OpeningMovement:
    """The sliding-family movement a bay declares — LIFT_SLIDE (HST),
    PARALLEL_SLIDE (PSK) or plain SLIDE — read off its spec leaves or
    its single opening. Falls back to SLIDE for a legacy layout-only
    bay."""
    slide_family = {
        OpeningMovement.LIFT_SLIDE,
        OpeningMovement.PARALLEL_SLIDE,
        OpeningMovement.SLIDE,
    }
    raw_leaves = node.get("leaves")
    if isinstance(raw_leaves, list):
        for raw_leaf in raw_leaves:
            if not isinstance(raw_leaf, dict):
                continue
            raw_opening = raw_leaf.get("opening")
            if not isinstance(raw_opening, dict):
                continue
            try:
                movement = OpeningMovement(str(raw_opening.get("movement")))
            except ValueError:
                continue
            if movement in slide_family:
                return movement
    raw_opening = node.get("opening")
    if isinstance(raw_opening, dict):
        try:
            movement = OpeningMovement(str(raw_opening.get("movement")))
        except ValueError:
            return OpeningMovement.SLIDE
        if movement in slide_family:
            return movement
    return OpeningMovement.SLIDE


def _bay_plan_kind(node: dict[str, object]) -> str | None:
    """Which plan strip a bay draws under the elevation — None when it
    has no plan semantics. The sliding family (corredera, HST,
    osciloparalela) draws rail tracks; FOLD draws the folded package,
    PIVOT the declared axis, VERTICAL_SLIDE the two stacked sashes."""
    if node.get("sliding_layout") is not None:
        return "sliding"
    opening = str(node.get("opening_type") or "")
    if opening.startswith("SLIDING"):
        return "sliding"

    def _leaf_movements() -> list[OpeningMovement]:
        movements: list[OpeningMovement] = []
        raw_leaves = node.get("leaves")
        if isinstance(raw_leaves, list):
            for raw_leaf in raw_leaves:
                if not isinstance(raw_leaf, dict):
                    continue
                raw_opening = raw_leaf.get("opening")
                if not isinstance(raw_opening, dict):
                    continue
                try:
                    movements.append(
                        OpeningMovement(str(raw_opening.get("movement")))
                    )
                except ValueError:
                    continue
        raw_opening = node.get("opening")
        if not movements and isinstance(raw_opening, dict):
            try:
                movements.append(
                    OpeningMovement(str(raw_opening.get("movement")))
                )
            except ValueError:
                pass
        return movements

    movements = _leaf_movements()
    if not movements:
        return None
    if any(
        m in (OpeningMovement.LIFT_SLIDE, OpeningMovement.PARALLEL_SLIDE)
        for m in movements
    ):
        return "sliding"
    if any(m is OpeningMovement.FOLD for m in movements):
        return "fold"
    if any(
        m in (OpeningMovement.PIVOT_V, OpeningMovement.PIVOT_H)
        for m in movements
    ):
        return "pivot"
    if any(m is OpeningMovement.VERTICAL_SLIDE for m in movements):
        return "guillotina"
    return None


def _legacy_leaf_specs(
    opening: str, node: dict[str, object]
) -> tuple[list[Opening], "UnitKind"]:
    """Map a legacy ``opening_type`` enum to the spec-leaf vocabulary the
    glyph contract consumes — same table as the canvas's
    ``glyphLeafSpec``. Door enums resolve to DOOR unit so the sill accent
    and the door handle come free from the contract."""
    handed = str(node.get("door_handedness") or "")
    inward = OpeningDirection.INWARD

    def leaf(movement: OpeningMovement, hinge: "HingeSide | None") -> Opening:
        return Opening(movement=movement, hinge_side=hinge, direction=inward)

    table: dict[str, tuple[list[Opening], "UnitKind"]] = {
        "TURN_LEFT": ([leaf(OpeningMovement.TURN, HingeSide.LEFT)], UnitKind.WINDOW),
        "TURN_RIGHT": ([leaf(OpeningMovement.TURN, HingeSide.RIGHT)], UnitKind.WINDOW),
        "TILT_TURN_LEFT": ([leaf(OpeningMovement.TILT_TURN, HingeSide.LEFT)], UnitKind.WINDOW),
        "TILT_TURN_RIGHT": ([leaf(OpeningMovement.TILT_TURN, HingeSide.RIGHT)], UnitKind.WINDOW),
        "AWNING": (
            [Opening(movement=OpeningMovement.TOP_HUNG, hinge_side=HingeSide.TOP,
                     direction=OpeningDirection.OUTWARD)],
            UnitKind.WINDOW,
        ),
        "DOOR_ENTRY": (
            [leaf(OpeningMovement.TURN, HingeSide.RIGHT if handed == "RIGHT" else HingeSide.LEFT)],
            UnitKind.DOOR,
        ),
        "DOOR_DOUBLE": (
            [leaf(OpeningMovement.TURN, HingeSide.LEFT), leaf(OpeningMovement.TURN, HingeSide.RIGHT)],
            UnitKind.DOOR,
        ),
    }
    return table.get(opening, ([], UnitKind.WINDOW))


def _svg_elements(node: dict[str, object], x: Decimal, y: Decimal,
                  width: Decimal, height: Decimal, out: list[str],
                  marker: str, glyph_only: bool = False,
                  pal: dict[str, str | None] | None = None,
                  unit: "UnitKind" = UnitKind.WINDOW) -> None:
    if pal is None:
        pal = _PAL_TECH
    node_type = str(node.get("type"))
    try:
        unit = UnitKind(str(node.get("unit_kind") or unit.value))
    except ValueError:
        pass
    children = node.get("children")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise DocumentaryError("invalid_frozen_parametric_tree")
    if node_type == "ROOT":
        if len(children) != 1 or not isinstance(children[0], dict):
            raise DocumentaryError("invalid_frozen_parametric_tree")
        _svg_elements(children[0], x, y, width, height, out, marker, glyph_only, unit=unit)
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
                f'y2="{_pt(y + height)}" stroke="{pal["split"]}" stroke-width="'
                f'{_pt(height / Decimal("60"))}"/>'
            )
            _svg_elements(first, x, y, split, height, out, marker, glyph_only, pal, unit)
            _svg_elements(second, x + split, y, width - split, height, out, marker, glyph_only, pal, unit)
        else:
            out.append(
                f'<line x1="{_pt(x)}" y1="{_pt(y + split)}" x2="{_pt(x + width)}" '
                f'y2="{_pt(y + split)}" stroke="{pal["split"]}" stroke-width="'
                f'{_pt(width / Decimal("60"))}"/>'
            )
            _svg_elements(first, x, y, width, split, out, marker, glyph_only, pal, unit)
            _svg_elements(second, x, y + split, width, height - split, out, marker, glyph_only, pal, unit)
        return
    if node_type != "BAY":
        raise DocumentaryError("invalid_frozen_parametric_tree")
    inset_x = width * _SVG_INSET
    inset_y = height * _SVG_INSET
    ix, iy = x + inset_x, y + inset_y
    iw, ih = width - inset_x * 2, height - inset_y * 2
    stroke_mm = min(width, height) / Decimal("120")
    stroke = _pt(stroke_mm)
    if not glyph_only:
        out.append(
            f'<rect x="{_pt(x)}" y="{_pt(y)}" width="{_pt(width)}" height="{_pt(height)}" '
            f'fill="{pal["frame_fill"]}" stroke="{pal["frame_edge"]}" stroke-width="' + _pt(min(width, height) / Decimal("40"))
            + '"/>'
        )
        out.append(
            f'<rect x="{_pt(ix)}" y="{_pt(iy)}" width="{_pt(iw)}" height="{_pt(ih)}" '
            f'fill="{pal["bay_fill"]}" stroke="{pal["bay_edge"]}" stroke-width="{stroke}"/>'
        )
        if pal.get("sheen"):
            # Soft diagonal highlight — reads as glazing, not a grey box.
            out.append(
                f'<polygon points="{_pt(ix)},{_pt(iy)} {_pt(ix + iw * Decimal("0.38"))},{_pt(iy)} '
                f'{_pt(ix)},{_pt(iy + ih * Decimal("0.72"))}" fill="{pal["sheen"]}" '
                'fill-opacity="0.45"/>'
            )
    opening = node.get("opening_type")
    mx, my = ix + iw / 2, iy + ih / 2
    handle_raw = node.get("handle_height_mm")
    handle_mm = _num(handle_raw) if handle_raw is not None else None
    view: ElevationView = "interior"  # issued elevations are interior unless asked
    spec_leaves: list[tuple[Decimal, Decimal, BayLeaf]] = []
    if opening is None and node.get("sliding_layout") is None:
        # D03 spec form — `opening`/`leaves`/`unit_kind` instead of the
        # legacy enum: resolve each leaf and draw the shared DIN grammar
        # per leaf (interior view; dashed when it opens away). A declared
        # `sliding_layout` wins over spec leaves — the panel topology is
        # the authority on a sliding-family bay (HST, corredera, PSK).
        raw_leaves = node.get("leaves")
        if isinstance(raw_leaves, list) and raw_leaves:
            try:
                spec = OpeningSpec(
                    unit_kind=unit, leaves=_parse_leaves(raw_leaves)
                )
            except (InvalidEngineRequest, ValueError):
                spec = None
            if spec is not None and spec.leaves:
                leaf_w = iw / len(spec.leaves)
                spec_leaves = [
                    (ix + leaf_w * index, leaf_w, leaf)
                    for index, leaf in enumerate(spec.leaves)
                ]
        raw_opening = node.get("opening")
        if not spec_leaves and isinstance(raw_opening, dict):
            try:
                spec_leaves = [
                    (
                        ix,
                        iw,
                        BayLeaf(slot="PRIMARY", opening=_parse_opening(raw_opening)),
                    )
                ]
            except InvalidEngineRequest:
                spec_leaves = []
        if spec_leaves:
            # Meeting stile between leaves (inversor / encuentro) — a real
            # vertical member on hinged pairs, whether window or door.
            for leaf_x, _leaf_w, _leaf in spec_leaves[1:]:
                out.append(
                    f'<line x1="{_pt(leaf_x)}" y1="{_pt(iy)}" x2="{_pt(leaf_x)}" '
                    f'y2="{_pt(iy + ih)}" stroke="{pal["glyph"]}" '
                    f'stroke-width="{stroke}"/>'
                )
            for leaf_x, leaf_w, leaf in spec_leaves:
                _glyph_paths_out(
                    leaf_primitives(
                        leaf.opening,
                        view,
                        unit=unit,
                        handle_mm=handle_mm,
                        axis_mm=leaf.axis_offset_mm,
                        slot=leaf.slot,
                    ),
                    leaf_x, iy, leaf_w, ih, out, pal, stroke_mm,
                )
            if pal.get("hardware"):
                for leaf_x, leaf_w, leaf in spec_leaves:
                    hinge = leaf.opening.hinge_side.value if leaf.opening.hinge_side else None
                    pseudo = {
                        "TILT_TURN": {"LEFT": "TILT_TURN_LEFT", "RIGHT": "TILT_TURN_RIGHT"},
                        "TURN": {"LEFT": "TURN_LEFT", "RIGHT": "TURN_RIGHT"},
                        "TOP_HUNG": {"TOP": "AWNING"},
                    }.get(leaf.opening.movement.value, {}).get(hinge or "")
                    if unit == UnitKind.DOOR and pseudo:
                        pseudo = "DOOR_ENTRY"
                    if pseudo:
                        _hardware_marks(
                            pseudo, "RIGHT" if hinge == "RIGHT" else "",
                            leaf_x, iy, leaf_w, ih, out, pal,
                        )
    elif opening in ("SLIDING_2L", "SLIDING_3L", "SLIDING_4L", "SLIDING") or node.get("sliding_layout") is not None:
        # The layout owns the semantics: track assignment + declared travel.
        # A frozen tree saved before `travel` resolves direction by the
        # documented convention and the arrow carries `inferred`.
        parsed_layout = _parse_sliding_layout(node.get("sliding_layout"))
        if parsed_layout is None or not parsed_layout.panels:
            leaf_count = {"SLIDING_2L": 2, "SLIDING_3L": 3, "SLIDING_4L": 4}.get(
                str(opening), 2
            )
            parsed_layout = SlidingLayout(
                tracks=2,
                panels=[
                    SlidingPanel(slot=str(i), kind=SlidingPanelKind.MOVING)
                    for i in range(leaf_count)
                ],
            )
        leaf_w = iw / len(parsed_layout.panels)
        panel_prims = sliding_primitives(
            parsed_layout, view, movement=_bay_slide_movement(node)
        )
        for index, panel in enumerate(parsed_layout.panels):
            lx = ix + leaf_w * index
            out.append(
                f'<rect x="{_pt(lx)}" y="{_pt(iy)}" width="{_pt(leaf_w)}" '
                f'height="{_pt(ih)}" fill="none" stroke="{pal["bay_edge"]}" '
                f'stroke-width="{stroke}"/>'
            )
            _glyph_paths_out(
                panel_prims[index], lx, iy, leaf_w, ih, out, pal, stroke_mm,
            )
            if pal.get("hardware") and panel.kind != "FIXED":
                # Pull on the meeting-stile edge: panels on the left
                # half pull right, on the right half pull left.
                pull_w = max(leaf_w * Decimal("0.05"), Decimal("1.1"))
                pull_h = ih * Decimal("0.16")
                inner = index * 2 < len(parsed_layout.panels)
                px = (
                    lx + leaf_w - pull_w * Decimal("1.5")
                    if inner
                    else lx + pull_w * Decimal("0.5")
                )
                out.append(
                    f'<rect x="{_pt(px)}" y="{_pt(my - pull_h / 2)}" '
                    f'width="{_pt(pull_w)}" height="{_pt(pull_h)}" '
                    f'rx="{_pt(pull_w / 2)}" fill="{pal["hardware"]}"/>'
                )
    else:
        # Legacy single-enum openings — mapped onto the spec vocabulary and
        # drawn by the same contract (door elevation = DIN triangles + sill;
        # the swing arc stays in plan views, never on the elevation).
        legacy_leaves, legacy_unit = _legacy_leaf_specs(str(opening), node)
        if legacy_leaves:
            leaf_w = iw / len(legacy_leaves)
            for index, leaf in enumerate(legacy_leaves):
                leaf_x = ix + leaf_w * index
                _glyph_paths_out(
                    leaf_primitives(leaf, view, unit=legacy_unit, handle_mm=handle_mm),
                    leaf_x, iy, leaf_w, ih, out, pal, stroke_mm,
                )
            if str(opening) == "DOOR_DOUBLE":
                out.append(
                    f'<line x1="{_pt(mx)}" y1="{_pt(iy)}" x2="{_pt(mx)}" '
                    f'y2="{_pt(iy + ih)}" stroke="{pal["glyph"]}" stroke-width="{stroke}"/>'
                )
    if pal.get("hardware"):
        _hardware_marks(
            str(opening), str(node.get("door_handedness") or ""),
            ix, iy, iw, ih, out, pal,
        )


def _frameless_pane(frameless: dict[str, object], x: Decimal, y: Decimal,
                    width: Decimal, height: Decimal, out: list[str],
                    pal: dict[str, str | None] | None = None) -> None:
    """Glass-only module figure: the pane itself plus its DECLARED edge
    supports — no fake frame, no invented fitting positions."""
    if pal is None:
        pal = _PAL_TECH
    stroke = _pt(min(width, height) / Decimal("140"))
    support_stroke = _pt(min(width, height) / Decimal("30"))
    out.append(
        f'<rect x="{_pt(x)}" y="{_pt(y)}" width="{_pt(width)}" height="{_pt(height)}" '
        f'fill="{pal["bay_fill"]}" stroke="{pal["bay_edge"]}" stroke-width="{stroke}"/>'
    )
    if pal.get("sheen"):
        out.append(
            f'<polygon points="{_pt(x)},{_pt(y)} {_pt(x + width * Decimal("0.38"))},{_pt(y)} '
            f'{_pt(x)},{_pt(y + height * Decimal("0.72"))}" fill="{pal["sheen"]}" '
            'fill-opacity="0.45"/>'
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
            f'y2="{_pt(my2)}" stroke="{pal["accent"]}" stroke-width="{support_stroke}"/>'
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


def _collect_sliding_bays(
    node: dict[str, object],
    x: Decimal,
    y: Decimal,
    width: Decimal,
    height: Decimal,
    acc: list[tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object]]],
) -> None:
    """Mirror the ``_svg_elements`` geometry walk and collect the box of
    every BAY that is a sliding unit — the plan strip draws one block per
    such bay under the technical elevation."""
    node_type = str(node.get("type"))
    children = node.get("children")
    if not isinstance(children, list):
        children = []
    if node_type == "ROOT" and len(children) == 1 and isinstance(children[0], dict):
        _collect_sliding_bays(children[0], x, y, width, height, acc)
        return
    if node_type in ("SPLIT_V", "SPLIT_H") and len(children) == 2:
        offset = node.get("split_offset_mm")
        if offset is None:
            return
        first, second = children
        if not isinstance(first, dict) or not isinstance(second, dict):
            return
        split = _num(offset)
        if node_type == "SPLIT_V":
            _collect_sliding_bays(first, x, y, split, height, acc)
            _collect_sliding_bays(second, x + split, y, width - split, height, acc)
        else:
            _collect_sliding_bays(first, x, y, width, split, acc)
            _collect_sliding_bays(second, x, y + split, width, height - split, acc)
        return
    if node_type != "BAY":
        return
    if _bay_plan_kind(node) is not None:
        acc.append((x, y, width, height, node))


def _sliding_plan_strip(
    bx: Decimal,
    strip_top: Decimal,
    bw: Decimal,
    layout: SlidingLayout,
    out: list[str],
    pal: dict[str, str | None],
    stroke_mm: Decimal,
    font_mm: Decimal,
    track_h: Decimal,
    movement: OpeningMovement = OpeningMovement.SLIDE,
) -> Decimal:
    """Plan cut of a sliding bay under the technical elevation: the wall
    bar on the exterior side, one numbered rail per track, the leaves in
    their slots and the travel arrow — EXTERIOR / INTERIOR declared.
    Returns the strip's total height so the caller can grow the viewBox."""
    tracks = max(layout.tracks, 1)
    wall_h = track_h / Decimal("3")
    pitch = bw / len(layout.panels)
    # Wall bar — the exterior side is always the top of the plan strip.
    out.append(
        f'<rect x="{_pt(bx)}" y="{_pt(strip_top)}" width="{_pt(bw)}" '
        f'height="{_pt(wall_h)}" fill="{pal["frame_edge"]}"/>'
    )
    out.append(
        f'<text x="{_pt(bx + bw)}" y="{_pt(strip_top + wall_h + font_mm)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        f'fill="{pal["glyph"]}">EXTERIOR</text>'
    )
    rails_top = strip_top + wall_h + font_mm * Decimal("1.6")
    for track in range(tracks):
        rail_y = rails_top + track_h * track
        out.append(
            f'<line x1="{_pt(bx)}" y1="{_pt(rail_y)}" x2="{_pt(bx + bw)}" '
            f'y2="{_pt(rail_y)}" stroke="{pal["split"]}" '
            f'stroke-width="{_pt(stroke_mm / 2)}"/>'
        )
        out.append(
            f'<text x="{_pt(bx - font_mm / 3)}" y="{_pt(rail_y + track_h * Decimal("0.6"))}" '
            f'font-size="{_pt(font_mm)}" text-anchor="end" '
            f'fill="{pal["glyph"]}">{track + 1}</text>'
        )
    for index, panel in enumerate(layout.panels):
        slot_x = bx + pitch * index
        track = panel.track if panel.track is not None else 0
        slot_y = rails_top + track_h * track
        out.append(
            f'<rect x="{_pt(slot_x)}" y="{_pt(slot_y)}" width="{_pt(pitch)}" '
            f'height="{_pt(track_h)}" fill="none" stroke="{pal["bay_edge"]}" '
            f'stroke-width="{_pt(stroke_mm)}"/>'
        )
        if panel.kind != "FIXED":
            prim = sliding_primitives(
                layout, "interior", movement=movement
            )[index]
            _glyph_paths_out(
                prim, slot_x, slot_y, pitch, track_h, out, pal, stroke_mm / 2
            )
    interior_y = rails_top + track_h * tracks + font_mm * Decimal("1.4")
    out.append(
        f'<text x="{_pt(bx + bw)}" y="{_pt(interior_y)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        f'fill="{pal["glyph"]}">INTERIOR</text>'
    )
    return interior_y - strip_top + font_mm * Decimal("0.6")


def _typology_plan_strip(
    bx: Decimal,
    strip_top: Decimal,
    bw: Decimal,
    node: dict[str, object],
    kind: str,
    out: list[str],
    pal: dict[str, str | None],
    stroke_mm: Decimal,
    font_mm: Decimal,
    track_h: Decimal,
) -> Decimal:
    """D08 plan cut for non-track typologies — same wall/convention as
    the sliding strip, but the glyph is the typology's real travel:
    ``fold`` draws the package collapsed against its anchor jamb,
    ``pivot`` the leaf on the reveal with its declared axis, and
    ``guillotina`` the two sashes on their parallel depths.
    """
    wall_h = track_h / Decimal("3")
    out.append(
        f'<rect x="{_pt(bx)}" y="{_pt(strip_top)}" width="{_pt(bw)}" '
        f'height="{_pt(wall_h)}" fill="{pal["frame_edge"]}"/>'
    )
    out.append(
        f'<text x="{_pt(bx + bw)}" y="{_pt(strip_top + wall_h + font_mm)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        f'fill="{pal["glyph"]}">EXTERIOR</text>'
    )
    strip_inner_top = strip_top + wall_h + font_mm * Decimal("1.6")

    raw_leaves = node.get("leaves")
    leaves = (
        [leaf for leaf in raw_leaves if isinstance(leaf, dict)]
        if isinstance(raw_leaves, list)
        else []
    )

    if kind == "fold":
        # Paquete plegado: las hojas recogidas junto al jamón de anclaje
        # — la dirección de plegado la declara la bisagra de la primera
        # hoja; el paquete queda en el canto opuesto al de apertura libre.
        count = max(len(leaves), 1)
        first = leaves[0].get("opening") if leaves else None
        hinge = str(first.get("hinge_side") or "LEFT") if isinstance(first, dict) else "LEFT"
        pack_w = track_h * Decimal("1.2")
        pack_x = bx if hinge == "RIGHT" else bx + bw - pack_w
        leaf_h = track_h * Decimal("0.55")
        for index in range(count):
            leaf_x = pack_x + index * (pack_w / max(count, 1) / 2)
            out.append(
                f'<rect x="{_pt(leaf_x)}" y="{_pt(strip_inner_top)}" '
                f'width="{_pt(track_h / 4)}" height="{_pt(leaf_h + index * track_h / 8)}" '
                f'fill="none" stroke="{pal["bay_edge"]}" '
                f'stroke-width="{_pt(stroke_mm)}"/>'
            )
        interior_y = strip_inner_top + leaf_h + count * track_h / 8 + font_mm * Decimal("1.4")
        out.append(
            f'<text x="{_pt(bx + bw)}" y="{_pt(interior_y)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="end" '
            f'fill="{pal["glyph"]}">INTERIOR</text>'
        )
        return interior_y - strip_top + font_mm * Decimal("0.6")

    if kind == "pivot":
        # Hoja pivotante en el vano: la hoja es la línea del paramento y
        # el eje pivotante se marca a la distancia declarada.
        leaf_y = strip_inner_top + track_h * Decimal("0.6")
        out.append(
            f'<line x1="{_pt(bx)}" y1="{_pt(leaf_y)}" x2="{_pt(bx + bw)}" '
            f'y2="{_pt(leaf_y)}" stroke="{pal["bay_edge"]}" '
            f'stroke-width="{_pt(stroke_mm)}"/>'
        )
        axis_raw = leaves[0].get("axis_offset_mm") if leaves else None
        axis_x = bx + (_num(axis_raw) if axis_raw is not None else bw / 2)
        axis_x = min(max(axis_x, bx), bx + bw)
        tick = track_h * Decimal("0.5")
        out.append(
            f'<line x1="{_pt(axis_x)}" y1="{_pt(leaf_y - tick)}" '
            f'x2="{_pt(axis_x)}" y2="{_pt(leaf_y + tick)}" '
            f'stroke="{pal["glyph"]}" stroke-width="{_pt(stroke_mm)}"/>'
        )
        out.append(
            f'<text x="{_pt(axis_x)}" y="{_pt(leaf_y + tick + font_mm)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="middle" '
            f'fill="{pal["glyph"]}">EJE</text>'
        )
        interior_y = leaf_y + tick + font_mm * Decimal("2.2")
        out.append(
            f'<text x="{_pt(bx + bw)}" y="{_pt(interior_y)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="end" '
            f'fill="{pal["glyph"]}">INTERIOR</text>'
        )
        return interior_y - strip_top + font_mm * Decimal("0.6")

    if kind == "guillotina":
        # Dos paños correderos a dos profundidades — la hoja superior en
        # el plano exterior, la inferior en el interior (doble guillotina;
        # con una sola móvil la otra queda fija, sin flecha).
        depth_leaf = {
            depth: next(
                (
                    leaf
                    for leaf in leaves
                    if str(leaf.get("slot")) == ("TOP" if depth == 0 else "BOTTOM")
                ),
                None,
            )
            for depth in range(2)
        }
        for depth in range(2):
            rail_y = strip_inner_top + track_h * depth
            out.append(
                f'<line x1="{_pt(bx)}" y1="{_pt(rail_y)}" x2="{_pt(bx + bw)}" '
                f'y2="{_pt(rail_y)}" stroke="{pal["split"]}" '
                f'stroke-width="{_pt(stroke_mm / 2)}"/>'
            )
            leaf_x = bx + bw * Decimal("0.15")
            out.append(
                f'<rect x="{_pt(leaf_x)}" y="{_pt(rail_y - track_h / 6)}" '
                f'width="{_pt(bw * Decimal("0.7"))}" height="{_pt(track_h / 3)}" '
                f'fill="none" stroke="{pal["bay_edge"]}" '
                f'stroke-width="{_pt(stroke_mm)}"/>'
            )
            leaf = depth_leaf[depth]
            leaf_opening = leaf.get("opening") if isinstance(leaf, dict) else None
            if isinstance(leaf_opening, dict) and leaf_opening.get("movement") == "VERTICAL_SLIDE":
                out.append(
                    f'<text x="{_pt(leaf_x + bw * Decimal("0.35"))}" '
                    f'y="{_pt(rail_y + track_h / 3)}" '
                    f'font-size="{_pt(font_mm)}" text-anchor="middle" '
                    f'fill="{pal["glyph"]}">↕</text>'
                )
        interior_y = strip_inner_top + track_h + font_mm * Decimal("1.4")
        out.append(
            f'<text x="{_pt(bx + bw)}" y="{_pt(interior_y)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="end" '
            f'fill="{pal["glyph"]}">INTERIOR</text>'
        )
        return interior_y - strip_top + font_mm * Decimal("0.6")

    return track_h


def _bay_fields(
    node: dict[str, object],
    x: Decimal,
    y: Decimal,
    width: Decimal,
    height: Decimal,
    acc: list[tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object]]],
) -> None:
    """Mirror the ``_svg_elements`` geometry walk and collect the box of
    every BAY — the commercial figure numbers each one as a Campo and the
    construction list names it in the same DFS order."""
    node_type = str(node.get("type"))
    children = node.get("children")
    if not isinstance(children, list):
        children = []
    if node_type == "ROOT" and len(children) == 1 and isinstance(children[0], dict):
        _bay_fields(children[0], x, y, width, height, acc)
        return
    if node_type in ("SPLIT_V", "SPLIT_H") and len(children) == 2:
        offset = node.get("split_offset_mm")
        if offset is None:
            return
        first, second = children
        if not isinstance(first, dict) or not isinstance(second, dict):
            return
        split = _num(offset)
        if node_type == "SPLIT_V":
            _bay_fields(first, x, y, split, height, acc)
            _bay_fields(second, x + split, y, width - split, height, acc)
        else:
            _bay_fields(first, x, y, width, split, acc)
            _bay_fields(second, x, y + split, width, height - split, acc)
        return
    if node_type == "BAY":
        acc.append((x, y, width, height, node))


def _chain_h(
    spans: list[tuple[Decimal, Decimal]],
    y: Decimal,
    out: list[str],
    pal: dict[str, str | None],
    font_mm: Decimal,
    dim_stroke: str,
) -> None:
    """Horizontal dimension chain: ticks at every boundary, integer mm
    labels centered per span — the Musterangebot reading of a field row."""
    if not spans:
        return
    x0 = spans[0][0]
    x1 = spans[-1][1]
    tick = font_mm / 2
    out.append(
        f'<line x1="{_pt(x0)}" y1="{_pt(y)}" x2="{_pt(x1)}" y2="{_pt(y)}" '
        f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
    )
    for bx in {x0, x1} | {end for _start, end in spans[:-1]}:
        out.append(
            f'<line x1="{_pt(bx)}" y1="{_pt(y - tick)}" x2="{_pt(bx)}" '
            f'y2="{_pt(y + tick)}" stroke="{pal["glyph"]}" '
            f'stroke-width="{dim_stroke}"/>'
        )
    for start, end in spans:
        out.append(
            f'<text x="{_pt((start + end) / 2)}" y="{_pt(y - tick / 2)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="middle" '
            'font-family="IBM Plex Mono, monospace" '
            f'fill="{pal["glyph"]}">{int((end - start).to_integral_value())}</text>'
        )


def _chain_v(
    spans: list[tuple[Decimal, Decimal]],
    x: Decimal,
    out: list[str],
    pal: dict[str, str | None],
    font_mm: Decimal,
    dim_stroke: str,
) -> None:
    """Vertical dimension chain on a member's left edge — rotated integer
    mm labels, one per left-column field."""
    if not spans:
        return
    y0 = spans[0][0]
    y1 = spans[-1][1]
    tick = font_mm / 2
    out.append(
        f'<line x1="{_pt(x)}" y1="{_pt(y0)}" x2="{_pt(x)}" y2="{_pt(y1)}" '
        f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
    )
    for by in {y0, y1} | {end for _start, end in spans[:-1]}:
        out.append(
            f'<line x1="{_pt(x - tick)}" y1="{_pt(by)}" x2="{_pt(x + tick)}" '
            f'y2="{_pt(by)}" stroke="{pal["glyph"]}" '
            f'stroke-width="{dim_stroke}"/>'
        )
    for start, end in spans:
        label_x = x - font_mm * Decimal("0.4")
        label_y = (start + end) / 2
        out.append(
            f'<text x="{_pt(label_x)}" y="{_pt(label_y)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="middle" '
            'font-family="IBM Plex Mono, monospace" '
            f'transform="rotate(-90 {_pt(label_x)} {_pt(label_y)})" '
            f'fill="{pal["glyph"]}">{int((end - start).to_integral_value())}</text>'
        )


def _assembly_plan_strip(
    plan: dict[str, object],
    left_edge: Decimal,
    strip_top: Decimal,
    out: list[str],
    pal: dict[str, str | None],
    stroke_mm: Decimal,
    font_mm: Decimal,
) -> Decimal:
    """Plan cut of a coupled assembly (conjunto/bow) under the commercial
    elevation — the sealed PlanGeometry the engine resolved at seal time:
    module footprints, the front chain and the coupling wedges, with
    EXTERIOR on top and INTERIOR below (same convention as the sliding
    plan strip). Returns the strip height so the viewBox can grow."""
    q = Decimal("0.01")
    min_y = Decimal(str(plan.get("min_y_mm") or "0"))
    span_y = Decimal(str(plan.get("height_mm") or "0"))

    def _px(point: dict[str, object]) -> Decimal:
        return Decimal(str(point["x_mm"])) - left_edge

    def _py(point: dict[str, object]) -> Decimal:
        # Back edges sit at negative y (behind the front chain) — they map
        # to the TOP of the strip (exterior side); the front chain lands
        # at the bottom (interior side).
        return strip_top + (Decimal(str(point["y_mm"])) - min_y).quantize(q)

    def _poly(points: list[dict[str, object]]) -> str:
        return " ".join(f"{_px(p)},{_py(p)}" for p in points)

    for module in plan.get("modules") or []:
        if not isinstance(module, dict):
            continue
        corners = [p for p in (module.get("corners") or []) if isinstance(p, dict)]
        if len(corners) >= 3:
            out.append(
                f'<polygon points="{_poly(corners)}" fill="none" '
                f'stroke="{pal["bay_edge"]}" stroke-width="{_pt(stroke_mm)}"/>'
            )
    for coupling in plan.get("couplings") or []:
        if not isinstance(coupling, dict):
            continue
        polygon = [p for p in (coupling.get("polygon") or []) if isinstance(p, dict)]
        if len(polygon) >= 3:
            out.append(
                f'<polygon points="{_poly(polygon)}" fill="none" '
                'stroke="#E56A32" '
                f'stroke-width="{_pt(stroke_mm)}"/>'
            )
    front = [p for p in (plan.get("front_chain") or []) if isinstance(p, dict)]
    if len(front) >= 2:
        out.append(
            f'<polyline points="{_poly(front)}" fill="none" '
            f'stroke="{pal["frame_edge"]}" '
            f'stroke-width="{_pt(stroke_mm * Decimal("1.6"))}"/>'
        )
    right_x = max((_px(p) for p in front), default=left_edge)
    out.append(
        f'<text x="{_pt(right_x)}" y="{_pt(strip_top + font_mm)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        f'fill="{pal["glyph"]}">EXTERIOR</text>'
    )
    bottom_y = strip_top + span_y + font_mm * Decimal("0.4")
    out.append(
        f'<text x="{_pt(right_x)}" y="{_pt(bottom_y + font_mm)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        f'fill="{pal["glyph"]}">INTERIOR</text>'
    )
    return span_y + font_mm * Decimal("1.8")


def _position_svg(
    position: dict[str, object], *, commercial: bool = False,
    marker_key: str = "", fields: bool = False,
) -> str:
    tree = _object(position.get("parametric_tree"), "invalid_frozen_parametric_tree")
    pal = _commercial_palette(position) if commercial else _PAL_TECH
    # The same position can be drawn twice on a page (hero + card): the
    # marker id must stay unique or the second SVG's arrows mis-resolve.
    marker = f"arrow-{escape(_value(position.get('position_index')))}-{escape(marker_key) or 'x'}"
    elements: list[str] = [
        f'<defs><marker id="{marker}" markerWidth="8" markerHeight="8" refX="6" refY="3" '
        'orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" '
        f'stroke="{pal["glyph"]}" '
        'stroke-width="1"/></marker></defs>'
    ]
    sliding_bays: list[tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object]]] = []
    # Campo boxes for the commercial ficha: (bx, by, bw, bh, node,
    # member_left, member_bottom) — member edges group bays into the
    # column whose bottom/left chains they belong to.
    field_bays: list[
        tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object],
              Decimal, Decimal]
    ] = []
    left_edge = Decimal("0")
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
            module_tree = _object(module.get("tree"), "invalid_frozen_parametric_tree")
            _collect_sliding_bays(
                module_tree,
                x, baseline, module_width, module_height, sliding_bays,
            )
            _module_bays: list[
                tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object]]
            ] = []
            _bay_fields(module_tree, x, baseline, module_width, module_height, _module_bays)
            field_bays.extend(
                (bx, by, bw, bh, node, x, baseline + module_height)
                for bx, by, bw, bh, node in _module_bays
            )
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
                    glyph_only=True, pal=pal,
                )
            elif frameless is not None:
                _frameless_pane(
                    _object(frameless, "invalid_frozen_parametric_tree"),
                    x, baseline, module_width, module_height, elements, pal,
                )
            else:
                _svg_elements(
                    _object(module.get("tree"), "invalid_frozen_parametric_tree"),
                    x, baseline, module_width, module_height, elements, marker,
                    pal=pal,
                )
            # Module-id labels drop on sliver modules — squeezed text
            # colliding with the next unit's label reads worse than none.
            # Under the commercial field mode the Campo number occupies
            # that corner instead (the construction list names each field).
            label = _value(module.get("id"))
            label_size = module_height / Decimal("18")
            if (
                not (commercial and fields)
                and module_width / Decimal("30") + (
                    Decimal(len(label)) * label_size * Decimal("0.65")
                ) < module_width
            ):
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
                # Field mode puts the Campo number in the bottom corner —
                # the angle reads at the seam top instead.
                angle_y = (
                    seam_top + joint.top_mm / Decimal("14")
                    if commercial and fields
                    else seam_bottom - joint.top_mm / Decimal("18")
                )
                elements.append(
                    f'<text x="{_pt(seam_x)}" y="{_pt(angle_y)}" '
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
        _svg_elements(tree, Decimal("0"), Decimal("0"), width, height, elements, marker, pal=pal)
        _collect_sliding_bays(
            tree, Decimal("0"), Decimal("0"), width, height, sliding_bays
        )
        _classic_bays: list[
            tuple[Decimal, Decimal, Decimal, Decimal, dict[str, object]]
        ] = []
        _bay_fields(tree, Decimal("0"), Decimal("0"), width, height, _classic_bays)
        field_bays.extend(
            (bx, by, bw, bh, node, Decimal("0"), height)
            for bx, by, bw, bh, node in _classic_bays
        )
    # P05 — every elevation declares its reading side; the technical
    # figure also carries exterior dims and, under each sliding bay, the
    # plan cut with numbered tracks. The furniture lives in gutters the
    # viewBox grows for; the drawing itself stays at 0,0.
    draw_fields = commercial and fields
    q = Decimal("0.1")
    top_pad = (height / Decimal("18")).quantize(q) if height > 0 else Decimal("0")
    left_pad = (
        (width / Decimal("14")).quantize(q)
        if width > 0 and not commercial
        else (
            (width / Decimal("12")).quantize(q)
            if width > 0 and draw_fields
            else Decimal("0")
        )
    )
    right_pad = (
        (height / Decimal("24")).quantize(q)
        if height > 0 and not commercial
        else Decimal("0")
    )
    bottom_pad = (height / Decimal("14")).quantize(q) if height > 0 else Decimal("0")
    font_mm = (height / Decimal("48")).quantize(q) if height > 0 else Decimal("10")
    dim_stroke = _pt(height / Decimal("700")) if height > 0 else "0.5"
    elements.append(
        f'<text x="{_pt(width)}" y="{_pt(-top_pad / 3)}" '
        f'font-size="{_pt(font_mm)}" text-anchor="end" '
        'font-family="IBM Plex Mono, monospace" '
        f'fill="{pal["glyph"]}">Vista interior</text>'
    )
    if not commercial:
        # Exterior total chains — one width chain on top, one height
        # chain on the left; integer mm, tabular mono face.
        dim_y = -top_pad * Decimal("0.68")
        tick = font_mm / 2
        elements.append(
            f'<line x1="0" y1="{_pt(dim_y)}" x2="{_pt(width)}" y2="{_pt(dim_y)}" '
            f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<line x1="0" y1="{_pt(dim_y - tick)}" x2="0" y2="{_pt(dim_y + tick)}" '
            f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<line x1="{_pt(width)}" y1="{_pt(dim_y - tick)}" x2="{_pt(width)}" '
            f'y2="{_pt(dim_y + tick)}" stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<text x="{_pt(width / 2)}" y="{_pt(dim_y - tick)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="middle" '
            'font-family="IBM Plex Mono, monospace" '
            f'fill="{pal["glyph"]}">{int(width.to_integral_value())}</text>'
        )
        dim_x = -left_pad * Decimal("0.55")
        elements.append(
            f'<line x1="{_pt(dim_x)}" y1="0" x2="{_pt(dim_x)}" y2="{_pt(height)}" '
            f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<line x1="{_pt(dim_x - tick)}" y1="0" x2="{_pt(dim_x + tick)}" y2="0" '
            f'stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<line x1="{_pt(dim_x - tick)}" y1="{_pt(height)}" x2="{_pt(dim_x + tick)}" '
            f'y2="{_pt(height)}" stroke="{pal["glyph"]}" stroke-width="{dim_stroke}"/>'
            f'<text x="{_pt(dim_x - font_mm * Decimal("0.4"))}" y="{_pt(height / 2)}" '
            f'font-size="{_pt(font_mm)}" text-anchor="middle" '
            'font-family="IBM Plex Mono, monospace" '
            f'transform="rotate(-90 {_pt(dim_x - font_mm * Decimal("0.4"))} {_pt(height / 2)})" '
            f'fill="{pal["glyph"]}">{int(height.to_integral_value())}</text>'
        )
    if draw_fields:
        # Campo marks — the commercial ficha reads its fields like a
        # Musterangebot: a field number inside each bay and per-member
        # width/height chains in the gutters the viewBox grows for.
        chain_gap = height / Decimal("28")
        for index, (bx, by, bw, bh, _node, _ml, _mb) in enumerate(field_bays):
            field_size = min(bw, bh) / Decimal("4.5")
            if field_size < Decimal("26"):
                continue  # sliver bay — the construction list still names it
            elements.append(
                f'<text x="{_pt(bx + bw / 26)}" y="{_pt(by + bh - bh / 16)}" '
                f'font-size="{_pt(field_size.quantize(q))}" '
                'font-family="IBM Plex Mono, monospace" '
                f'fill="{pal["label"]}">{index + 1}</text>'
            )
        member_edges = list(
            dict.fromkeys((entry[5], entry[6]) for entry in field_bays)
        )
        for mleft, mbottom in member_edges:
            member_bays = [
                entry for entry in field_bays
                if entry[5] == mleft and entry[6] == mbottom
            ]
            bottom_spans = sorted(
                (entry[0], entry[0] + entry[2])
                for entry in member_bays
                if entry[1] + entry[3] == entry[6]
            )
            _chain_h(
                bottom_spans, mbottom + chain_gap, elements, pal,
                font_mm, dim_stroke,
            )
            left_spans = sorted(
                (entry[1], entry[1] + entry[3])
                for entry in member_bays
                if entry[0] == entry[5]
            )
            _chain_v(
                left_spans, mleft - chain_gap, elements, pal,
                font_mm, dim_stroke,
            )
    if not commercial or draw_fields:
        # Sliding plan strips — one cut per sliding bay, in bay order;
        # a coupled assembly (conjunto/bow) adds the sealed plan cut.
        strip_top = height + bottom_pad
        track_h = max((height / Decimal("40")).quantize(q), Decimal("22"))
        strip_stroke = height / Decimal("120") if height > 0 else Decimal("2")
        plan_bottom = height
        for bx, _by, bw, _bh, bay_node in sliding_bays:
            plan_kind = _bay_plan_kind(bay_node) or "sliding"
            if plan_kind == "sliding":
                bay_layout = _parse_sliding_layout(bay_node.get("sliding_layout"))
                if bay_layout is None or not bay_layout.panels:
                    leaf_count = {
                        "SLIDING_2L": 2, "SLIDING_3L": 3, "SLIDING_4L": 4
                    }.get(str(bay_node.get("opening_type")), 2)
                    bay_layout = SlidingLayout(
                        tracks=2,
                        panels=[
                            SlidingPanel(slot=str(i), kind=SlidingPanelKind.MOVING)
                            for i in range(leaf_count)
                        ],
                    )
                plan_bottom = strip_top + _sliding_plan_strip(
                    bx, strip_top, bw, bay_layout, elements, pal,
                    strip_stroke, font_mm, track_h,
                    movement=_bay_slide_movement(bay_node),
                )
            else:
                # D08 — plegable / pivotante / guillotina: la planta
                # muestra el viaje real de la tipología.
                plan_bottom = strip_top + _typology_plan_strip(
                    bx, strip_top, bw, bay_node, plan_kind, elements, pal,
                    strip_stroke, font_mm, track_h,
                )
            strip_top = plan_bottom + bottom_pad / 2
        if draw_fields:
            plan = position.get("plan")
            if isinstance(plan, dict) and plan.get("front_chain"):
                strip_h = _assembly_plan_strip(
                    plan, left_edge, strip_top, elements, pal,
                    strip_stroke, font_mm,
                )
                plan_bottom = strip_top + strip_h
        bottom_pad = max(bottom_pad, plan_bottom - height)
    return (
        f'<svg viewBox="{_pt(-left_pad)} {_pt(-top_pad)} '
        f'{_pt(width + left_pad + right_pad)} '
        f'{_pt(height + top_pad + bottom_pad)}" '
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
        return list(dict.fromkeys(specs))
    # A composite quotes one glazing per leaf; identical specs dedupe so
    # "4 Float, 4 Float" never prints on a customer document.
    return list(dict.fromkeys(_glass_specs(tree)))


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
        f'<span class="tb-value">{escape(bom_hash[:8])}</span></div>'
        if workshop and bom_hash != "—"
        else ""
    )
    client = _value(project.get("client_name"))
    titleblock = (
        '<div class="titleblock">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(project_code)}</span></div>'
        + (
            '<div class="tb-cell"><span class="tb-label">Cliente</span>'
            f'<span class="tb-value">{escape(client)}</span></div>'
            if client != "—"
            else ""
        )
        + '<div class="tb-cell"><span class="tb-label">Documento</span>'
        + f'<span class="tb-value">{escape(doc_code)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Rev.</span>'
        f'<span class="tb-value">{escape(_rev_display(revision))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(sealed_at))}</span></div>'
        f"{fingerprint}"
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
    )
    header = (
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"{issuer}"
        f"<strong>{escape(project_code)}</strong><br>"
        f"{escape(doc_code)} · Rev. {escape(_rev_display(revision))}<br>"
        f"{escape(_cldate(sealed_at))}</div></div>"
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
        f"<h1>{escape(title)}</h1>"
    )
    return f'<main class="{class_name}">{titleblock}{header}', bom_hash


def _pricing_extras(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """Project-level charges (instalación, traslado) frozen inside the
    applied pricing request — rendered as labeled money rows, never
    re-derived."""
    pricing = snapshot.get("pricing")
    request = pricing.get("request") if isinstance(pricing, dict) else None
    items = request.get("extras") if isinstance(request, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _position_extra_lines(
    snapshot: dict[str, object],
) -> dict[str, list[dict[str, object]]]:
    """D06: sealed engine sublíneas per position — read from the frozen BOM
    (cantidad × precio = total), never re-derived at render time."""
    bom = snapshot.get("bom")
    result: dict[str, list[dict[str, object]]] = {}
    if not isinstance(bom, list):
        return result
    for entry in bom:
        if not isinstance(entry, dict):
            continue
        engine_result = entry.get("engine_result")
        lines = (
            engine_result.get("extra_lines")
            if isinstance(engine_result, dict)
            else None
        )
        if isinstance(lines, list) and lines:
            result[str(entry.get("position_id"))] = [
                item for item in lines if isinstance(item, dict)
            ]
    return result


def _service_lines(snapshot: dict[str, object]) -> list[dict[str, object]]:
    """D06: project services frozen inside the sealed pricing result."""
    pricing = snapshot.get("pricing")
    result = pricing.get("result") if isinstance(pricing, dict) else None
    lines = result.get("service_lines") if isinstance(result, dict) else None
    if not isinstance(lines, list):
        return []
    return [item for item in lines if isinstance(item, dict)]


def _qty_price_total(line: dict[str, object]) -> str:
    """'1,56 m × $ 11.000 = $ 17.160' — sealed math printed verbatim;
    'Sin dato' when the article never declared money."""
    qty = _num(line.get("quantity"))
    unit = _value(line.get("unit"))
    price = line.get("unit_price")
    total = line.get("total_price")
    currency = line.get("unit_price_currency") or "CLP"
    qty_text = _fmt_mm(qty)
    if price is None or total is None:
        return f"{qty_text} {unit} · Sin dato"
    return (
        f"{qty_text} {unit} × "
        f"{_money(price, currency)} = {_money(total, currency)}"
    )


def _bay_nodes(node: dict[str, object]) -> list[dict[str, object]]:
    """BAY leaf nodes in the same DFS order ``_bay_fields`` draws them —
    field N in the construction list is field N inside the figure."""
    nodes: list[dict[str, object]] = []

    def walk(item: dict[str, object]) -> None:
        node_type = str(item.get("type"))
        children = item.get("children")
        if not isinstance(children, list):
            children = []
        if node_type == "ROOT" and len(children) == 1 and isinstance(children[0], dict):
            walk(children[0])
            return
        if node_type in ("SPLIT_V", "SPLIT_H") and len(children) == 2:
            if isinstance(children[0], dict):
                walk(children[0])
            if isinstance(children[1], dict):
                walk(children[1])
            return
        if node_type == "BAY":
            nodes.append(item)

    walk(node)
    return nodes


def _field_lines(position: dict[str, object]) -> list[str]:
    """'Campo N — Oscilobatiente izquierda' per drawn field: the same
    DFS order the figure numbers. Assemblies walk module-by-module in
    the elevation layout's member order, exactly like the drawer."""
    tree = _object(position.get("parametric_tree"), "invalid_frozen_parametric_tree")
    bays: list[dict[str, object]] = []
    if tree.get("version") == "product-v2":
        try:
            layout = elevation_layout(parse_product_model(tree).assembly)
        except (ValueError, KeyError, DocumentaryError):
            return []
        modules_by_id = {
            str(module.get("id")): module
            for module in _array(
                _object(tree.get("assembly"), "invalid_frozen_parametric_tree").get("modules"),
                "invalid_frozen_parametric_tree",
            )
            if isinstance(module, dict)
        }
        for member in layout.members:
            module = modules_by_id.get(member.module_id)
            if module is not None and isinstance(module.get("tree"), dict):
                bays.extend(_bay_nodes(module["tree"]))
    else:
        bays = _bay_nodes(tree)
    lines: list[str] = []
    for index, bay in enumerate(bays):
        labels = _opening_labels(bay)
        label = " · ".join(labels) if labels else "Fijo"
        lines.append(f"Campo {index + 1} — {label}")
    return lines


def _position_skus(node: object, acc: list[str]) -> None:
    """Ordered unique article SKUs declared anywhere in the sealed tree."""
    if not isinstance(node, dict):
        return
    sku = node.get("glass_article_sku")
    if isinstance(sku, str) and sku and sku not in acc:
        acc.append(sku)
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            _position_skus(child, acc)
    assembly = node.get("assembly")
    if isinstance(assembly, dict):
        modules = assembly.get("modules")
        if isinstance(modules, list):
            for module in modules:
                if isinstance(module, dict):
                    _position_skus(module.get("tree"), acc)


def _ug_label(value: object) -> str:
    """Ug/g values print with comma decimals and their unit — '1,1'."""
    text = format(Decimal(str(value)).normalize(), "f")
    return text.replace(".", ",")


def _glass_lines(position: dict[str, object]) -> list[str]:
    """Commercial glazing lines: the declared product name with Ug, g,
    light transmission and safety class from the sealed catalog card —
    printed only cuando existen (an unknown value is an omitted tag,
    never 'Sin dato'). Falls back to the glass_spec notation when the
    position never declared an article sku."""
    products = position.get("glass_products")
    products = products if isinstance(products, dict) else {}
    skus: list[str] = []
    tree = _object(position.get("parametric_tree"), "invalid_frozen_parametric_tree")
    _position_skus(tree, skus)
    lines: list[str] = []
    for sku in skus:
        product = products.get(sku)
        product = product if isinstance(product, dict) else {}
        name = _value(product.get("name") or sku)
        tags = []
        if product.get("ug_w_m2k") is not None:
            tags.append(f"Ug {_ug_label(product['ug_w_m2k'])} W/m²K")
        if product.get("g_value") is not None:
            tags.append(f"g {_ug_label(product['g_value'])}")
        if product.get("light_transmission_pct") is not None:
            tags.append(f"TL {_ug_label(product['light_transmission_pct'])} %")
        if _value(product.get("safety_class")) != "—":
            tags.append(_value(product.get("safety_class")))
        lines.append(name + (" · " + " · ".join(tags) if tags else ""))
    if not lines:
        specs = _position_glass_specs(position)
        lines = specs if specs else ["Panel sándwich"]
    return lines


def _doc01(snapshot: dict[str, object], *, render_context: dict | None = None) -> str:
    """Commercial proposal (DOC-01): a sales document, not a table dump.

    Structure — cover (brand + client + hero unit + investment strip),
    project summary, a compact positions overview, product cards with the
    commercial render beside its spec, the investment block, terms, and
    the acceptance block. Sections with no data are simply not rendered."""
    project = _object(snapshot.get("project"), "invalid_frozen_revision_snapshot")
    currency = project.get("currency")
    positions = [_object(item, "invalid_frozen_position")
                 for item in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot")]
    org_raw = snapshot.get("organization")
    organization = org_raw if isinstance(org_raw, dict) else None
    org = organization if organization is not None else {}
    # Sealed org policy (D06): DETAILED prints each sublínea and service;
    # GROUPED folds them into the position sum. Snapshots sealed before the
    # column existed omit it and render detailed — the behavior they had.
    detailed_extras = _value(org.get("extras_display")) != "GROUPED"
    extra_lines_by_position = _position_extra_lines(snapshot)

    # Identical openings collapse into one group; the sealed tree signature
    # keeps mirrored/handedness pairs apart so the rendered figure never
    # lies about which product the customer is buying.
    groups: dict[tuple[object, ...], dict[str, object]] = {}
    for position in positions:
        specs = ", ".join(_position_glass_specs(position)) or "Panel sándwich"
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
            bucket["priced"] = False
        else:
            bucket["price_net"] += _num(position.get("price_net"))

    # Sell-side unit price — the sealed `line_detail` (pre-discount exact
    # unit, "3 Stück × E-Preis = Gesamt"); the position total falls back
    # to price_net/qty on snapshots sealed before the detail existed.
    pricing = snapshot.get("pricing")
    pricing_result = (
        pricing.get("result") if isinstance(pricing, dict) else None
    )
    pricing_result = pricing_result if isinstance(pricing_result, dict) else {}
    line_detail = pricing_result.get("line_detail")
    unit_by_index = {
        str(item.get("position_index")): _num(item.get("unit_price"))
        for item in (line_detail if isinstance(line_detail, list) else [])
        if isinstance(item, dict) and item.get("unit_price") is not None
    }
    for bucket in groups.values():
        ref = bucket["ref_position"]
        detail_unit = unit_by_index.get(_value(ref.get("position_index")))
        if detail_unit is not None:
            bucket["unit_net"] = detail_unit
        elif bucket["priced"]:
            bucket["unit_net"] = bucket["price_net"] / bucket["quantity"]
        else:
            bucket["unit_net"] = None
        bucket["line_total"] = (
            bucket["unit_net"] * bucket["quantity"]
            if bucket["unit_net"] is not None
            else bucket["price_net"] if bucket["priced"] else None
        )

    def _list(values: list[str]) -> str:
        if not values:
            return "—"
        if len(values) <= 6:
            return ", ".join(values)
        return f"{values[0]} … {values[-1]} ({len(values)})"

    def _figure(position: dict[str, object], key_suffix: str = "") -> str:
        return _position_svg(position, commercial=True, marker_key=key_suffix)

    # ── Cover / dochead ────────────────────────────────────────────────
    # Folio: COT-<código del proyecto>-<revisión sellada> — la única
    # identidad que el cliente debe poder repetir por teléfono.
    quote_folio = f"COT-{_value(project.get('code'))}-{_value(snapshot.get('revision'))}"
    bom_hash = _value(snapshot.get("bom_hash"))
    issuer_legal = " · ".join(
        part
        for part in (
            _value(org.get("name")),
            f"RUT {_value(org.get('tax_id'))}" if _value(org.get("tax_id")) != "—" else "",
            _value(org.get("brand_address")),
            _value(org.get("brand_phone")),
            _value(org.get("brand_email")),
        )
        if part and part != "—"
    )
    # Cajetín: folio · revisión · fecha · página n/N en la fila de
    # identidad; la fila de pie lleva los datos legales del emisor y, en
    # tamaño pequeño, la huella abreviada del BOM (F2 — la cadena del
    # documento, nunca el hash completo).
    titleblock = (
        '<div class="titleblock">'
        '<div class="tb-row">'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(project.get("code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Cliente</span>'
        f'<span class="tb-value">{escape(_value(project.get("client_name")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Documento</span>'
        f'<span class="tb-value">{escape(quote_folio)}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Rev.</span>'
        f'<span class="tb-value">{escape(_rev_display(snapshot.get("revision")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Fecha</span>'
        f'<span class="tb-value">{escape(_cldate(snapshot.get("sealed_at")))}</span></div>'
        '<div class="tb-cell"><span class="tb-label">Página</span>'
        '<span class="tb-value"><span class="pg"></span></span></div>'
        "</div>"
        '<div class="tb-row tb-legal">'
        f'<div class="tb-cell"><span class="tb-label">Emisor</span>'
        f'<span class="tb-value">{escape(issuer_legal)}</span></div>'
        + (
            '<div class="tb-cell"><span class="tb-label">Huella</span>'
            f'<span class="tb-value">{escape(bom_hash[:8])}</span></div>'
            if bom_hash != "—"
            else ""
        )
        + "</div></div>"
    )
    body = f'<main class="commercial">{titleblock}'

    # Hero: la unidad más representativa — la más grande del conjunto —
    # con el renderer comercial real y la vista declarada en la lámina.
    hero_bucket = None
    hero_area = Decimal("-1")
    for bucket in groups.values():
        ref = bucket["ref_position"]
        try:
            area = _num(ref.get("width_mm")) * _num(ref.get("height_mm"))
        except DocumentaryError:
            area = Decimal("0")
        if area > hero_area:
            hero_area, hero_bucket = area, bucket
    hero_figure = ""
    if hero_bucket is not None:
        ref = hero_bucket["ref_position"]
        hero_figure = (
            '<div class="cover-figure">'
            + _position_svg(ref, commercial=True, marker_key="hero")
            + '<div class="figcap">'
            + escape(_TYPOLOGY_ES.get(_value(ref.get("typology")), _value(ref.get("typology"))))
            + " · "
            + escape(_dim(ref.get("width_mm")))
            + " × "
            + escape(_dim(ref.get("height_mm")))
            + " mm · Vista interior</div></div>"
        )

    client_meta = []
    for label, field in (("RUT", "client_rut"), ("Giro", "client_giro"),
                         ("Obra", "name"), ("Comuna", "client_comuna"),
                         ("Dirección", "client_address"),
                         ("Contacto", "client_email"), ("Teléfono", "client_phone"),
                         ("Entrega", "delivery_address")):
        value = _value(project.get(field))
        if value and value != "—":
            client_meta.append(f"<strong>{escape(label)}</strong> {escape(value)}<br>")
    valid_until = _value(project.get("quotation_valid_until"))
    # Pre-pricing snapshots carry no totals — the proposal omits every
    # money cell rather than printing a phantom zero.
    totals_priced = project.get("total_price_gross") is not None
    doc_terms_raw = org.get("doc_terms")
    doc_terms = doc_terms_raw if isinstance(doc_terms_raw, dict) else {}
    cover_invest_cells = []
    if totals_priced:
        cover_invest_cells.append(
            '<div class="inv-cell inv-total"><span>Total</span>'
            f'<strong>{escape(_money(project.get("total_price_gross"), currency))}</strong></div>'
        )
    if _value(project.get("payment_terms")) not in ("", "—"):
        cover_invest_cells.append(
            '<div class="inv-cell"><span>Pago</span>'
            f'<strong>{escape(_value(project.get("payment_terms")))}</strong></div>'
        )
    if doc_terms.get("plazo_entrega"):
        cover_invest_cells.append(
            '<div class="inv-cell"><span>Plazo de entrega</span>'
            f'<strong>{escape(str(doc_terms["plazo_entrega"]))}</strong></div>'
        )
    if doc_terms.get("instalacion"):
        cover_invest_cells.append(
            '<div class="inv-cell"><span>Instalación</span>'
            f'<strong>{escape(str(doc_terms["instalacion"]))}</strong></div>'
        )
    if valid_until and valid_until != "—":
        cover_invest_cells.append(
            '<div class="inv-cell"><span>Válida hasta</span>'
            f'<strong>{escape(_cldate(valid_until))}</strong></div>'
        )
    issuer_line = " · ".join(
        part
        for part in (
            _value(org.get("name")),
            f"RUT {_value(org.get('tax_id'))}" if _value(org.get("tax_id")) != "—" else "",
            _value(org.get("giro")),
            _value(org.get("brand_address")),
            _value(org.get("brand_phone")),
            _value(org.get("brand_email")),
        )
        if part and part != "—"
    )
    cover_top = (
        '<div class="cover-top">'
        f'{_brand_block(organization)}'
        '<div class="cover-doc">'
        "<strong>Propuesta comercial</strong>"
        f"{escape(quote_folio)}<br>"
        f"Revisión {escape(_rev_display(snapshot.get('revision')))} · "
        f"{escape(_cldate(snapshot.get('sealed_at')))}"
        "</div></div>"
    )
    cover_invest = (
        f'<div class="cover-invest">{"".join(cover_invest_cells)}</div>'
        if cover_invest_cells
        else ""
    )
    issuer_foot = (
        f'<div class="cover-foot">{escape(issuer_line)}</div>' if issuer_line else ""
    )
    # Política editorial (mandato §07 + techo §8): la portada existe cuando
    # el documento necesita orientación — un solo producto abre con la
    # ficha en la primera página; un presupuesto grande abre con portada.
    total_units = sum(bucket["quantity"] for bucket in groups.values())
    has_cover = len(groups) > 6 or total_units > 12
    if has_cover:
        body += (
            '<div class="cover">'
            + cover_top
            + '<div class="cover-main"><div class="cover-left">'
            + '<p class="kicker">Preparado para</p>'
            + f'<h1 class="cover-client">{escape(_value(project.get("client_name")))}</h1>'
            + f'<p class="cover-project">{escape(_value(project.get("name")))} · '
            + f'{escape(_value(project.get("code")))}</p>'
            + f'<p class="cover-meta">{"".join(client_meta)}</p>'
            + "</div>"
            + f"{hero_figure}"
            + "</div>"
            + cover_invest
            + issuer_foot
            + "</div>"
        )
    else:
        body += (
            '<div class="dochead">'
            + cover_top
            + '<p class="dochead-client"><span class="kicker">Preparado para</span> '
            + f'<strong>{escape(_value(project.get("client_name")))}</strong>'
            + (f' · RUT {escape(_value(project.get("client_rut")))}'
               if _value(project.get("client_rut")) != "—" else "")
            + ' · ' + escape(_value(project.get("name")))
            + " · "
            + escape(_value(project.get("code")))
            + "</p>"
            + f'<p class="cover-meta dochead-meta">{"".join(client_meta)}</p>'
            + cover_invest
            + issuer_foot
            + "</div>"
        )

    # ── Resumen de posiciones ──────────────────────────────────────────
    # La tabla es el índice legible del documento: columnas de ancho fijo
    # con ajuste de línea (nunca superpuestas), cifras tabulares y
    # encabezado repetido en cada página (display: table-header-group).
    if positions and len(groups) > 1:
        doors = sum(
            bucket["quantity"]
            for key, bucket in groups.items()
            if str(key[0]).startswith("DOOR")
        )
        windows = total_units - doors
        systems = sorted({
            _value(bucket["ref_position"].get("system_name"))
            for bucket in groups.values()
            if _value(bucket["ref_position"].get("system_name")) not in ("", "—")
        })
        finishes = sorted({
            str(bucket["ref_position"].get("finish") or "")
            or _finish(key[4], key[5])
            for key, bucket in groups.items()
            if key[4] or key[5]
        })
        glass = sorted({bucket["specs"] for bucket in groups.values()})
        stat_cells = [
            f'<div class="stat-cell"><span class="stat-n">{escape(str(total_units))}</span>'
            '<span class="stat-k">Unidades</span></div>',
            f'<div class="stat-cell"><span class="stat-n">{escape(str(windows))}</span>'
            '<span class="stat-k">Ventanas</span></div>',
            f'<div class="stat-cell"><span class="stat-n">{escape(str(doors))}</span>'
            '<span class="stat-k">Puertas</span></div>',
            f'<div class="stat-cell"><span class="stat-n">{len(groups)}</span>'
            '<span class="stat-k">Configuraciones</span></div>',
        ]
        body += '<h2>Resumen de posiciones</h2>' + (
            f'<div class="stat-strip">{"".join(stat_cells)}</div>'
        )
        chip_rows = []
        if systems:
            chip_rows.append(
                '<p><span class="tlabel">Sistemas</span></p><div class="chips">'
                + "".join(f"<span>{escape(name)}</span>" for name in systems)
                + "</div>"
            )
        if finishes:
            chip_rows.append(
                '<p><span class="tlabel">Acabados</span></p><div class="chips">'
                + "".join(f"<span>{escape(name)}</span>" for name in finishes)
                + "</div>"
            )
        if glass:
            chip_rows.append(
                '<p><span class="tlabel">Acristalamiento</span></p><div class="chips">'
                + "".join(f"<span>{escape(name)}</span>" for name in glass)
                + "</div>"
            )
        body += "".join(chip_rows)

        subtotal = sum(
            bucket["line_total"]
            for bucket in groups.values()
            if bucket["line_total"] is not None
        )
        all_priced = all(bucket["line_total"] is not None for bucket in groups.values())
        overview_rows = []
        for key, bucket in groups.items():
            ref = bucket["ref_position"]
            unit_cell = (
                _money(bucket["unit_net"], currency)
                if bucket["unit_net"] is not None
                else ""
            )
            overview_rows.append([
                _list(bucket["indexes"]),
                _list(bucket["locations"]),
                _TYPOLOGY_ES.get(key[0], key[0]),
                f"{_dim(key[1])} × {_dim(key[2])}",
                bucket["quantity"],
                unit_cell,
                _money(bucket["line_total"], currency)
                if bucket["line_total"] is not None
                else "",
            ])
        resumen_foot = (
            '<tfoot><tr><td colspan="6">Subtotal posiciones</td>'
            f'<td class="dimension">{escape(_money(subtotal, currency))}</td></tr></tfoot>'
            if all_priced
            else ""
        )
        body += (
            '<table class="resumen"><colgroup>'
            '<col style="width:8%"><col style="width:19%">'
            '<col style="width:15%"><col style="width:14%">'
            '<col style="width:8%"><col style="width:17%">'
            '<col style="width:19%"></colgroup>'
            "<thead><tr><th>Pos.</th><th>Ubicación</th><th>Tipología</th>"
            "<th>Ancho × Alto</th><th>Cant.</th><th>P. unit. neto</th>"
            "<th>Total neto</th></tr></thead><tbody>"
            + "".join(
                _row(row, ["", "", "", "dimension", "dimension",
                           "dimension", "dimension"])
                for row in overview_rows
            )
            + "</tbody>" + resumen_foot + "</table>"
        )

    # ── Detalle por posición ───────────────────────────────────────────
    # Densidad §8: ficha completa (≤6 configuraciones), ficha compacta
    # (≤24) o tabla con miniaturas (>24) — elegido automáticamente por el
    # conteo de configuraciones, nunca por el conteo de unidades.
    body += "<h2>Detalle por posición</h2>"
    if len(groups) > 24:
        mini_rows = []
        for key, bucket in groups.items():
            ref = bucket["ref_position"]
            mini_rows.append([
                _list(bucket["indexes"]),
                _Raw(_figure(ref, "m" + bucket["indexes"][0])),
                _TYPOLOGY_ES.get(key[0], key[0])
                + (" · " + _list(bucket["locations"])
                   if bucket["locations"] else ""),
                f"{_dim(key[1])} × {_dim(key[2])}",

                bucket["quantity"],
                _money(bucket["unit_net"], currency)
                if bucket["unit_net"] is not None
                else "",
                _money(bucket["line_total"], currency)
                if bucket["line_total"] is not None
                else "",
            ])
        body += (
            '<table class="resumen mini"><colgroup>'
            '<col style="width:7%"><col style="width:11%">'
            '<col style="width:20%"><col style="width:13%">'
            '<col style="width:8%"><col style="width:20%">'
            '<col style="width:21%"></colgroup>'
            "<thead><tr><th>Pos.</th><th>Vista</th><th>Tipología · Ubicación</th>"
            "<th>Ancho × Alto</th><th>Cant.</th><th>P. unit. neto</th>"
            "<th>Total neto</th></tr></thead><tbody>"
            + "".join(
                _row(row, ["", "mini-fig", "", "dimension", "dimension",
                           "dimension", "dimension"])
                for row in mini_rows
            )
            + "</tbody></table>"
        )
    else:
        density = "full" if len(groups) <= 6 else "compact"
        body += f'<div class="pcards{" compact" if density == "compact" else ""}">'
        for key, bucket in groups.items():
            typology, width_mm, height_mm, specs, ci, ce = key[:6]
            discount_pct = key[7]
            ref = bucket["ref_position"]
            system_name = _value(ref.get("system_name"))
            pos_label = (
                f"Pos. {escape(_list(bucket['indexes']))}"
                + (f" · {escape(_list(bucket['locations']))}"
                   if bucket["locations"] else "")
            )
            # Franja de cabecera estilo Musterangebot: la posición y su
            # "N unidades × precio unitario = total" antes del dibujo.
            head_money = ""
            if bucket["unit_net"] is not None and bucket["line_total"] is not None:
                discount_badge = (
                    f'<span class="off">-{_discount_label(discount_pct)}</span>'
                    if discount_pct not in ("0", "0.00", "0.0000", "—", "")
                    else ""
                )
                head_money = (
                    '<span class="pcard-money">'
                    f"Cantidad {escape(_value(bucket['quantity']))} × "
                    f"{escape(_money(bucket['unit_net'], currency))} = "
                    f"{escape(_money(bucket['line_total'], currency))}"
                    f"{discount_badge}</span>"
                )
            spec_items = []
            if system_name not in ("", "—"):
                demo = " · DEMO" if ref.get("system_is_demo") else ""
                spec_items.append(
                    f'<li><span class="plabel">Sistema</span> '
                    f"{escape(system_name + demo)}</li>"
                )
            # D07: al cliente le corresponde el vano medido y la del
            # producto (la del encabezado ya es la de fabricación).
            measurement = ref.get("measurement") or {}
            resolution = measurement.get("resolution") or {}
            if resolution.get("used_width_mm") and resolution.get("used_height_mm"):
                mounting = (measurement.get("mounting_rule") or {}).get("label") or ""
                spec_items.append(
                    f'<li><span class="plabel">Vano</span> '
                    f'{escape(_dim(resolution["used_width_mm"]))} × '
                    f'{escape(_dim(resolution["used_height_mm"]))} mm'
                    + (f" · {escape(_value(mounting))}" if mounting else "")
                    + "</li>"
                )
            # El rótulo de la lámina declara la vista real — la tabla de
            # la tarjeta repite la misma lectura (interior por defecto).
            spec_items.append(
                '<li><span class="plabel">Vista</span> Interior</li>'
            )
            finish = str(ref.get("finish") or "") or _finish(ci, ce)
            if finish and finish != "—":
                spec_items.append(
                    f'<li><span class="plabel">Acabado</span> {escape(finish)}</li>'
                )
            hardware_line = _hardware_sellable_line(ref)
            if hardware_line:
                spec_items.append(
                    f'<li><span class="plabel">Herrajes</span> {escape(hardware_line)}</li>'
                )
            glass_lines = _glass_lines(ref)
            spec_items.append(
                '<li><span class="plabel">Vidrio / relleno</span> '
                + "<br>".join(escape(line) for line in glass_lines)
                + "</li>"
            )
            schedule = ref.get("accessory_schedule")
            schedule_items = (
                [item for item in schedule.get("items") or [] if isinstance(item, dict)]
                if isinstance(schedule, dict)
                else []
            )
            if schedule_items:
                names = [
                    _value(item.get("description") or item.get("technical_sku"))
                    for item in schedule_items[:4]
                ]
                if len(schedule_items) > 4:
                    names.append(f"+{len(schedule_items) - 4}")
                spec_items.append(
                    f'<li><span class="plabel">Incluye</span> {escape(", ".join(names))}</li>'
                )
            if detailed_extras:
                # Sublíneas: el total de la posición ya las lleva —
                # descriptivas, jamás re-sumadas. Una línea sin precio se
                # omite (los documentos de cliente no muestran "Sin dato").
                for line in extra_lines_by_position.get(str(ref.get("id")), []):
                    if line.get("unit_price") is None or line.get("total_price") is None:
                        continue
                    spec_items.append(
                        '<li class="pex"><span class="plabel">Extra</span> '
                        f'{escape(_value(line.get("name")))} — '
                        f"{escape(_qty_price_total(line))}</li>"
                    )
            field_items = ""
            if density == "full":
                campo_lines = _field_lines(ref)
                if len(campo_lines) > 1:
                    field_items = (
                        '<li class="pcard-campo-head"><span class="plabel">'
                        "Construcción</span></li>"
                        + "".join(
                            f'<li class="pcard-campo">{escape(line)}</li>'
                            for line in campo_lines
                        )
                    )
            figure_html = _position_svg(
                ref, commercial=True, marker_key="c" + bucket["indexes"][0],
                fields=density == "full",
            )
            price_block = ""
            if density == "compact" and bucket["priced"]:
                price_block = (
                    '<div class="pcard-price">'
                    + '<span class="plabel">Precio unitario</span>'
                    f'<strong>{escape(_money(bucket["unit_net"], currency))}</strong>'
                    '<span class="plabel">Total posición</span>'
                    f'<strong class="line">{escape(_money(bucket["line_total"], currency))}</strong>'
                    "</div>"
                )
            body += (
                '<figure class="pcard">'
                f'<div class="pcard-head"><span class="pcard-title">{pos_label} — '
                f'{escape(_TYPOLOGY_ES.get(typology, typology))} '
                f'{escape(_dim(width_mm))} × {escape(_dim(height_mm))} mm</span>'
                f"{head_money}</div>"
                '<div class="pcard-cols">'
                f'<div class="pcard-fig">{figure_html}</div>'
                '<div class="pcard-body">'
                f'<ul class="pcard-specs">{"".join(spec_items)}{field_items}</ul>'
                "</div>"
                f"{price_block}</div></figure>"
            )
        body += "</div>"

    services = _service_lines(snapshot)
    if services:
        # D06: project services are components of the sealed net — rendered
        # as their own block so they paginate normally (a note squeezed into
        # the unbreakable investment column can overflow past the page).
        if detailed_extras:
            items = "".join(
                "<li>"
                f"{escape(_value(item.get('name')))} — "
                f"{escape(_qty_price_total(item))}"
                "</li>"
                for item in services
                if item.get("unit_price") is not None
                and item.get("total_price") is not None
            )
            if items:
                body += (
                    '<div class="service-lines"><h3>Servicios del proyecto</h3>'
                    f"<ul>{items}</ul>"
                    '<p class="service-note">Incluidos en el neto de esta '
                    "propuesta — no se suman dos veces.</p></div>"
                )
        else:
            body += (
                '<div class="service-lines"><h3>Servicios del proyecto</h3>'
                "<p>"
                + escape(" · ".join(_value(item.get("name")) for item in services))
                + " — incluidos en el neto.</p></div>"
            )

    # ── Resumen comercial ──────────────────────────────────────────────
    # Posiciones → descuento → neto → IVA → total: las cifras selladas del
    # motor (line_detail + result), presentadas como lectura comercial.
    extras_net = pricing_result.get("extras_net")
    discount_amount = Decimal("0")
    discount_pcts: set[str] = set()
    for item in (line_detail if isinstance(line_detail, list) else []):
        if not isinstance(item, dict):
            continue
        pct = _value(item.get("discount_pct"))
        if pct in ("0", "0.00", "0.0000", "—", ""):
            continue
        discount_pcts.add(pct)
        try:
            line_gross = _num(item["unit_price"]) * _num(item["quantity"])
        except (DocumentaryError, KeyError, TypeError):
            continue
        # discount_pct seals as a fraction (0.10); legacy rows may carry
        # a whole percent (10) — same normalization as _discount_label.
        pct_fraction = _num(pct)
        if pct_fraction > 1:
            pct_fraction /= 100
        discount_amount += line_gross * pct_fraction
    granted_discounts = sorted(
        {
            key[7]
            for key in groups
            if key[7] not in ("0", "0.00", "0.0000", "—", "")
        },
        key=lambda item: _num(item),
    )
    discount_label = (
        "Descuento −"
        + " / −".join(_discount_label(pct) for pct in sorted(
            discount_pcts | set(granted_discounts), key=lambda v: _num(v)
        ))
        if (discount_pcts or granted_discounts)
        else "Descuento"
    )
    invest_html = ""
    if totals_priced:
        positions_sub = sum(
            bucket["line_total"]
            for bucket in groups.values()
            if bucket["line_total"] is not None
        )
        invest_rows = [
            '<div class="inv-row"><span>Posiciones'
            + (
                f" ({escape(str(total_units))} unidades)"
                if total_units != 0
                else ""
            )
            + f'</span><strong>{escape(_money(positions_sub, currency))}</strong></div>'
        ]
        if discount_amount > 0:
            invest_rows.append(
                f'<div class="inv-row"><span>{escape(discount_label)}</span>'
                f'<strong>−{escape(_money(discount_amount, currency))}</strong></div>'
            )
        if extras_net is not None and _num(extras_net) != 0:
            invest_rows.append(
                '<div class="inv-row"><span>Servicios y extras (incluidos)</span>'
                f'<strong>{escape(_money(extras_net, currency))}</strong></div>'
            )
        net = _num(project.get("total_price_net"))
        tax = _num(project.get("total_price_tax"))
        tax_label = (
            f"IVA {((tax / net) * 100).quantize(Decimal('1'))} %"
            if net and net != 0
            else "Impuestos"
        )
        invest_rows += [
            '<div class="inv-row"><span>Neto</span>'
            f'<strong>{escape(_money(project.get("total_price_net"), currency))}</strong></div>',
            f'<div class="inv-row"><span>{escape(str(tax_label))}</span>'
            f'<strong>{escape(_money(project.get("total_price_tax"), currency))}</strong></div>',
            '<div class="inv-row inv-total-row"><span>Total</span>'
            f'<strong>{escape(_money(project.get("total_price_gross"), currency))}</strong></div>',
        ]
        invest_note = [
            f'<p><span class="tlabel">Moneda</span> {escape(_value(currency))} — '
            "valores netos más impuesto.</p>",
        ]
        if valid_until and valid_until != "—":
            invest_note.append(
                f'<p><span class="tlabel">Vigencia</span> Esta propuesta es válida '
                f"hasta el {escape(_cldate(valid_until))}.</p>"
            )
        extras = _pricing_extras(snapshot)
        if extras:
            invest_note.append(
                '<p><span class="tlabel">Incluye</span> '
                + escape(
                    " · ".join(
                        f"{_value(item.get('label'))} "
                        + (
                            f"({_money(item.get('amount'), currency)})"
                            if _num(item.get("amount")) != 0
                            else "(sin costo)"
                        )
                        for item in extras
                    )
                )
                + " — dentro del neto.</p>"
            )
        invest_html = (
            '<div class="doc-col"><h2>Resumen comercial</h2>'
            '<div class="invest"><div class="invest-panel">'
            + "".join(invest_rows)
            + "</div>"
            f'<div class="invest-note">{"".join(invest_note)}</div>'
            "</div></div>"
        )

    # ── Condiciones comerciales ────────────────────────────────────────
    # Textos legales declarados por la organización (doc_terms) + la forma
    # de pago del proyecto — todo línea omitida cuando no existe, nunca
    # un "Sin dato" al cliente.
    terms = []
    if _value(project.get("payment_terms")) not in ("", "—"):
        terms.append(
            '<p><span class="tlabel">Forma de pago</span><br>'
            f'{escape(_value(project.get("payment_terms")))}</p>'
        )
    term_labels = (
        ("plazo_entrega", "Plazo de entrega"),
        ("instalacion", "Instalación"),
        ("exclusiones", "Exclusiones"),
        ("garantia", "Garantía"),
        ("jurisdiccion", "Jurisdicción"),
    )
    for key_name, label in term_labels:
        value = doc_terms.get(key_name)
        if isinstance(value, str) and value.strip():
            terms.append(
                f'<p><span class="tlabel">{escape(label)}</span><br>'
                f"{escape(value)}</p>"
            )
    if valid_until and valid_until != "—":
        terms.append(
            '<p><span class="tlabel">Validez de la oferta</span><br>'
            f"Hasta el {escape(_cldate(valid_until))}.</p>"
        )
    if _value(project.get("delivery_address")) not in ("", "—"):
        terms.append(
            '<p><span class="tlabel">Entrega</span><br>'
            f'{escape(_value(project.get("delivery_address")))}</p>'
        )
    notes = _value(project.get("notes_commercial"))
    if notes and notes != "—":
        terms.append(
            '<p><span class="tlabel">Condiciones</span><br>'
            f"{escape(notes)}</p>"
        )
    terms_html = ""
    if terms:
        terms_html = (
            '<div class="doc-col"><h2>Condiciones comerciales</h2>'
            f'<div class="terms">{"".join(terms)}</div></div>'
        )

    # ── Aceptación ─────────────────────────────────────────────────────
    # Nombre, RUT, fecha y firma; cuando el documento se emite con un
    # enlace de portal vigente, "Acepta en línea" lleva el QR y la URL.
    accept_recap = (
        f"{escape(quote_folio)} · Revisión "
        f"{escape(_rev_display(snapshot.get('revision')))}"
        + (
            f" · Total {escape(_money(project.get('total_price_gross'), currency))}"
            if totals_priced
            else ""
        )
        + (
            f" · válida hasta {escape(_cldate(valid_until))}"
            if valid_until and valid_until != "—"
            else ""
        )
    )
    approval_url = (render_context or {}).get("approval_url")
    online_block = ""
    if isinstance(approval_url, str) and approval_url.startswith("http"):
        qr_svg = segno.make(approval_url, error="m").svg_inline(
            border=2, scale=6, dark="#24302A", light=None
        )
        online_block = (
            '<div class="accept-online">'
            f'<div class="qr">{qr_svg}</div>'
            '<div class="accept-online-copy"><strong>Acepta en línea</strong><br>'
            f'<a href="{escape(approval_url)}">{escape(approval_url)}</a></div>'
            "</div>"
        )
    closing_cols = invest_html + terms_html + (
        '<div class="doc-col"><h2>Aceptación</h2>'
        f'<p class="accept-recap">{accept_recap}</p>'
        f"{online_block}"
        '<div class="sign-col">'
        '<div class="sign-cell"><span class="sign-label">Nombre y RUT</span></div>'
        '<div class="sign-cell"><span class="sign-label">Firma</span></div>'
        '<div class="sign-cell"><span class="sign-label">Fecha</span></div>'
        "</div></div>"
    )
    if closing_cols.strip():
        body += f'<div class="doc-duo">{closing_cols}</div>'
    body += "</main>"
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
        position_ref = positions_by_index.get(fact.get("position_index")) or {}
        location_tag = _value(position_ref.get("location_tag"))
        typology_es = _TYPOLOGY_ES.get(
            _value(position_ref.get("typology")), _value(position_ref.get("typology"))
        )
        position_title = f"Posición {_value(fact.get('position_index'))}"
        if location_tag != "—":
            position_title += f" · {location_tag}"
        if typology_es != "—":
            position_title += f" · {typology_es}"
        body += (
            f'<section><h2>{escape(position_title)} · '
            f'Repetición {escape(_value(fact.get("repetition_index")))}</h2>'
            f'<p class="dimension">{escape(_dim(fact.get("nominal_width_mm")))} × '
            f'{escape(_dim(fact.get("nominal_height_mm")))} mm</p>'
            + _table(
                ["Pieza", "Rol / slot", "SKU taller", "Corte mm", "Ángulos", "Flecha mm", "Referencia X/Y"],
                [[
                    labels["member"].get(member.get("member_id"), member.get("member_id")),
                    f"{_ROLE_ES.get(_value(_object(member.get('identity'), 'invalid_member_identity').get('role')), _value(_object(member.get('identity'), 'invalid_member_identity').get('role')))} / "
                    f"{_SLOT_ES.get(_value(_object(member.get('identity'), 'invalid_member_identity').get('physical_member_slot')), _value(_object(member.get('identity'), 'invalid_member_identity').get('physical_member_slot')))}",
                    member.get("workshop_sku"), member.get("cut_length_mm"),
                    f"{_value(member.get('angle_left'))}° / {_value(member.get('angle_right'))}°",
                    member.get("sagitta_mm") if member.get("sagitta_mm") is not None else "—",
                    f"({_dim(_object(member.get('start'), 'invalid_member_point').get('x_mm'))}, "
                    f"{_dim(_object(member.get('start'), 'invalid_member_point').get('y_mm'))}) → "
                    f"({_dim(_object(member.get('end'), 'invalid_member_point').get('x_mm'))}, "
                    f"{_dim(_object(member.get('end'), 'invalid_member_point').get('y_mm'))})",
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
                  f"{_dim(_object(item.get('rect'), 'invalid_infill_rect').get('width_mm'))} × "
                  f"{_dim(_object(item.get('rect'), 'invalid_infill_rect').get('height_mm'))}",
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
                  f"{_dim(_object(item.get('point'), 'invalid_handle_point').get('x_mm'))} / "
                  f"{_dim(_object(item.get('point'), 'invalid_handle_point').get('y_mm'))}",
                  _dim(item.get("requested_height_mm")),
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
                        ", ".join(_dim(number) for number in _array(
                            item.get("bottom_drain_holes_mm"), "invalid_workshop_annotations"
                        )) if item.get("bottom_drain_holes_mm") is not None else "—",
                        ", ".join(_dim(number) for number in _array(
                            item.get("closing_points_perimeter_mm"),
                            "invalid_workshop_annotations",
                        )) if item.get("closing_points_perimeter_mm") is not None else "—",
                        _dim(item.get("continuous_width_mm")), item.get("finish_class"),
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


def _fact_prefix(fact: dict[object, object]) -> str | None:
    """Physical-piece code prefix for one manufacturing fact: the frozen
    (position_index, repetition_index) pair identifies which commercial unit
    the pieces belong to — e.g. P01-U02 — so a printed code survives
    re-optimization and reads legibly at the saw."""
    position_index = fact.get("position_index")
    repetition_index = fact.get("repetition_index")
    if position_index is None or repetition_index is None:
        return None
    try:
        return f"P{int(str(position_index)):02d}-U{int(str(repetition_index)):02d}"
    except (TypeError, ValueError):
        return None


def _piece_labels(
    snapshot: dict[str, object],
) -> dict[str, dict[object, str]]:
    """Workshop-facing piece codes keyed off the frozen identity: members
    print ``P{pos}-U{unit}-M{seq}`` (seq assigned inside the unit by
    semantic_member_id, not by table order), reinforcements inherit their
    parent member's code with a ``·R`` suffix, infills ``-I{seq}`` and
    handles ``-MAN{seq}``. Facts frozen before the identity fields existed
    keep the legacy M-01/R-01/I-01 numbering. Location codes (P-01, V-01,
    H-01) are unchanged."""
    member: dict[object, str] = {}
    reinforcement: dict[object, str] = {}
    infill: dict[object, str] = {}
    handle: dict[object, str] = {}
    bay: dict[object, str] = {}
    leaf: dict[object, str] = {}
    leaf_fact: dict[object, str] = {}
    for fact in _array(snapshot.get("manufacturing"), "invalid_frozen_revision_snapshot"):
        members = _array(fact.get("members"), "invalid_manufacturing_fact")
        reinforcements = _array(
            fact.get("reinforcements"), "invalid_manufacturing_fact"
        )
        infills = _array(fact.get("infills"), "invalid_manufacturing_fact")
        handles = _array(fact.get("handles"), "invalid_manufacturing_fact")
        prefix = _fact_prefix(fact) if isinstance(fact, dict) else None
        if prefix is not None:
            ordered = sorted(
                members,
                key=lambda item: (
                    str(item.get("semantic_member_id") or ""),
                    str(item.get("member_id") or ""),
                ),
            )
            for index, item in enumerate(ordered, 1):
                member[item.get("member_id")] = f"{prefix}-M{index:02d}"
            for index, item in enumerate(reinforcements, 1):
                parent_code = member.get(item.get("parent_member_id"))
                reinforcement[item.get("reinforcement_id")] = (
                    f"{parent_code}·R"
                    if parent_code is not None
                    else f"{prefix}-R{index:02d}"
                )
            for index, item in enumerate(
                sorted(
                    infills,
                    key=lambda item: (
                        str(item.get("bay_id") or ""),
                        str(item.get("leaf_id") or ""),
                        str(item.get("infill_id") or ""),
                    ),
                ),
                1,
            ):
                infill[item.get("infill_id")] = f"{prefix}-I{index:02d}"
            for index, item in enumerate(
                sorted(handles, key=lambda item: str(item.get("handle_id") or "")),
                1,
            ):
                handle[item.get("handle_id")] = f"{prefix}-MAN{index:02d}"
        else:
            for item in members:
                member.setdefault(item.get("member_id"), f"M-{len(member) + 1:02d}")
            for item in reinforcements:
                reinforcement.setdefault(item.get("reinforcement_id"), f"R-{len(reinforcement) + 1:02d}")
            for item in infills:
                infill.setdefault(item.get("infill_id"), f"I-{len(infill) + 1:02d}")
            for item in handles:
                handle.setdefault(item.get("handle_id"), f"MAN-{len(handle) + 1:02d}")
        for item in members:
            if item.get("bay_id") is not None:
                bay.setdefault(item.get("bay_id"), f"V-{len(bay) + 1:02d}")
        for item in [*infills, *handles]:
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
        try:
            position[item.get("id")] = f"P{int(str(item.get('position_index'))):02d}"
        except (TypeError, ValueError):
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
    """Technical-id fallback for a missing human label — a corrupted
    UUID/hash identity never prints hex; it surfaces as '#8f3a', a tag
    short enough to be unmistakably not a folio."""
    text = _value(value)
    clean = text.replace("-", "")
    if len(clean) > 8 and all(
        ch in "0123456789abcdefABCDEF" for ch in clean
    ):
        return "#" + clean[-4:].lower()
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
    """Join printed piece codes without hiding identity. Short lists join
    fully; longer runs of contiguous same-prefix codes compress to a range
    (``M-06–M-09``); only a truly mixed bag falls back to a count suffix."""
    unique = sorted(set(codes))
    if len(unique) <= 4:
        return " · ".join(unique)
    grouped: dict[str, list[int]] = {}
    rest: list[str] = []
    for code in unique:
        match = re.match(r"^([A-ZÁÉÍÓÚÑ]+-?)(\d+)$", code)
        if match:
            grouped.setdefault(match.group(1), []).append(int(match.group(2)))
        else:
            rest.append(code)
    parts: list[str] = []
    for prefix, digits in grouped.items():
        digits.sort()
        start = prev = digits[0]
        run: list[int] = []
        for digit in digits[1:] + [-1]:
            if digit == prev + 1:
                prev = digit
                continue
            if prev - start >= 2:
                parts.append(f"{prefix}{start}–{prefix}{prev}")
            else:
                run.extend(range(start, prev + 1))
            start = prev = digit
        parts.extend(f"{prefix}{d}" for d in run)
    parts.extend(rest)
    joined = " · ".join(parts)
    if len(parts) <= 4:
        return joined
    return f"{parts[0]} · … · {parts[-1]} · +{len(unique) - 2}" if len(unique) > 6 else joined


def _cut_spec_index(
    snapshot: dict[str, object],
) -> dict[tuple[str, ...], list[object]]:
    """Cut-spec tuple → frozen member/reinforcement ids. The id-level index
    behind ``_cut_member_map`` — also used by traceability to resolve a
    printed M-xx/R-xx code back to the pieces that serve it."""
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return {}
    spec: dict[tuple[str, ...], list[object]] = {}
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
            spec.setdefault(key, []).append(item.get("member_id"))
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
            spec.setdefault(key, []).append(item.get("reinforcement_id"))
    return spec


def _member_home(
    snapshot: dict[str, object],
) -> dict[object, object]:
    """member/reinforcement id → owning fact's ``repetition_index`` (the
    physical unit inside its position). A cut's ``unit_index`` joins on this
    to resolve which frozen piece the cut actually makes."""
    home: dict[object, object] = {}
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return home
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        unit = fact.get("repetition_index")
        members = {
            str(item.get("member_id")): item
            for item in _array(fact.get("members"), "invalid_manufacturing_fact")
        }
        for item in members.values():
            home[item.get("member_id")] = unit
        for item in _array(fact.get("reinforcements"), "invalid_manufacturing_fact"):
            if members.get(str(item.get("parent_member_id"))) is not None:
                home[item.get("reinforcement_id")] = unit
    return home


def _cut_piece_ids(
    snapshot: dict[str, object],
) -> dict[tuple[str, ...], dict[object, list[object]]]:
    """spec key → unit_index → ordered member/reinforcement ids, so each
    printed cut resolves to the physical piece it produces."""
    index = _cut_spec_index(snapshot)
    home = _member_home(snapshot)
    out: dict[tuple[str, ...], dict[object, list[object]]] = {}
    for key, ids in index.items():
        units: dict[object, list[object]] = {}
        for entity_id in ids:
            units.setdefault(str(home.get(entity_id)), []).append(entity_id)
        out[key] = units
    return out


def _piece_pools(
    piece_ids: dict[tuple[str, ...], dict[object, list[object]]],
    labels: dict[str, dict[object, str]],
) -> dict[tuple[str, ...], dict[object, list[object]]]:
    """spec key → unit_index → ordered entity ids, each pool sorted by its
    printed code so assignment is deterministic across artifacts."""
    pools: dict[tuple[str, ...], dict[object, list[object]]] = {}
    for key, units in piece_ids.items():
        kind = "member" if key[0] == "PROFILE" else "reinforcement"
        pools[key] = {
            unit: sorted(
                ids,
                key=lambda entity_id: labels[kind].get(
                    entity_id, str(entity_id or "")[:10]
                ),
            )
            for unit, ids in units.items()
        }
    return pools


def _claim_piece(
    cut: dict[str, object],
    pools: dict[tuple[str, ...], dict[object, list[object]]],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
) -> tuple[str, object | None]:
    """Claim the next physical piece for this cut inside its unit pool —
    every artifact (PDF, CSV, DXF, labels) resolves the same code and the
    same frozen entity id for the same placed cut. A cut outside its own
    unit pool falls back to the spec-group label rather than stealing
    another unit's identity."""
    key = _cut_key(cut)
    ids = (pools.get(key) or {}).get(str(cut.get("unit_index") or "")) or []
    entity_id = ids.pop(0) if ids else None
    kind = "member" if key[0] == "PROFILE" else "reinforcement"
    if entity_id is not None:
        return labels[kind].get(entity_id, str(entity_id or "")[:10]), entity_id
    return cut_map.get(key) or "", None


def _bar_assignments(
    snapshot: dict[str, object],
    labels: dict[str, dict[object, str]],
    cut_map: dict[tuple[str, ...], str],
    bars: list[dict[str, object]],
) -> dict[tuple[object, object], tuple[str, object | None]]:
    """(bar_index, sequence) → (piece code, entity id) — the one assignment
    shared by the cut-pack diagram, the CNC CSV, the DXF marks and the
    piece-label sheet, so every artifact prints the same identity."""
    pools = _piece_pools(_cut_piece_ids(snapshot), labels)
    assignments: dict[tuple[object, object], tuple[str, object | None]] = {}
    for bar in bars:
        for cut in _array(bar.get("cuts"), "invalid_work_order_bundle"):
            code, entity_id = _claim_piece(cut, pools, labels, cut_map)
            assignments[(bar.get("bar_index"), cut.get("sequence"))] = (
                code,
                entity_id,
            )
    return assignments


def _infill_home(
    snapshot: dict[str, object],
) -> dict[object, object]:
    """infill id → owning fact's ``repetition_index``, same join as
    ``_member_home`` — a sheet placement's ``unit_index`` resolves which
    frozen pane it cuts."""
    home: dict[object, object] = {}
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return home
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        for item in _array(fact.get("infills"), "invalid_manufacturing_fact"):
            home[item.get("infill_id")] = fact.get("repetition_index")
    return home


def _infill_pools(
    snapshot: dict[str, object],
    labels: dict[str, dict[object, str]],
) -> dict[tuple[str, str, str], dict[object, list[object]]]:
    """(position, bay, leaf) → unit_index → ordered infill ids by printed
    code — the per-unit pool behind sheet assignment."""
    index = _infill_spec_index(snapshot)
    home = _infill_home(snapshot)
    pools: dict[tuple[str, str, str], dict[object, list[object]]] = {}
    for key, ids in index.items():
        units: dict[object, list[object]] = {}
        for infill_id in ids:
            units.setdefault(str(home.get(infill_id)), []).append(infill_id)
        pools[key] = {
            unit: sorted(
                unit_ids,
                key=lambda infill_id: labels["infill"].get(
                    infill_id, str(infill_id or "")[:10]
                ),
            )
            for unit, unit_ids in units.items()
        }
    return pools


def _claim_infill(
    piece: dict[str, object],
    pools: dict[tuple[str, str, str], dict[object, list[object]]],
    labels: dict[str, dict[object, str]],
    *,
    default_position: str = "",
) -> tuple[str, object | None]:
    """Claim the next infill for a sheet placement inside its unit pool —
    a placement outside its own unit pool returns no entity rather than
    stealing another unit's pane identity."""
    key = _infill_key(
        {**piece, "source_position_id": piece.get("source_position_id") or default_position}
    )
    ids = (pools.get(key) or {}).get(str(piece.get("unit_index") or "")) or []
    entity_id = ids.pop(0) if ids else None
    if entity_id is None:
        return "", None
    return labels["infill"].get(entity_id, str(entity_id or "")[:10]), entity_id


def _sheet_assignments(
    snapshot: dict[str, object],
    labels: dict[str, dict[object, str]],
    sheets: list[dict[str, object]],
    *,
    default_position: str = "",
) -> dict[tuple[object, object], tuple[str, object | None]]:
    """(sheet_index, sequence) → (infill code, infill id) — shared by the
    sheet diagram, the CSV and the DXF labels."""
    pools = _infill_pools(snapshot, labels)
    assignments: dict[tuple[object, object], tuple[str, object | None]] = {}
    for sheet in sheets:
        for piece in _array(
            sheet.get("placements"), "invalid_work_order_bundle"
        ):
            code, entity_id = _claim_infill(
                piece, pools, labels, default_position=default_position
            )
            assignments[(sheet.get("sheet_index"), piece.get("sequence"))] = (
                code,
                entity_id,
            )
    return assignments


def _member_op_marks(
    snapshot: dict[str, object],
) -> dict[str, str]:
    """member_id → op signature mark. Two cut-identical members that differ
    in machining are NOT interchangeable downstream — the saw label must say
    which stick carries the prep (operator review #6). Members with member
    ops mark ``(mec.)``; the plain join stays for truly interchangeable
    groups."""
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list) or not manufacturing:
        return {}
    try:
        from dekopen_engine.manufacturing import ManufacturingFactsV1
        from dekopen_engine.operations import operations_from_plan

        fact_units = [
            ManufacturingFactsV1.model_validate_json(json.dumps(fact))
            for fact in manufacturing
            if isinstance(fact, dict)
        ]
        ops = operations_from_plan(bars=[], fact_units=fact_units)
    except Exception:
        return {}
    marks: dict[str, str] = {}
    for op in ops:
        if op.host_kind == "MEMBER":
            marks[op.host] = "mec"
    return marks


def _reinforcement_parents(
    snapshot: dict[str, object], labels: dict[str, dict[object, str]]
) -> dict[object, str]:
    """reinforcement id → its host member's printed code — the parent
    relation the refuerzos section of the cut pack prints."""
    parents: dict[object, str] = {}
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return parents
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        for item in _array(fact.get("reinforcements"), "invalid_manufacturing_fact"):
            parents[item.get("reinforcement_id")] = labels["member"].get(
                item.get("parent_member_id"),
                str(item.get("parent_member_id") or "")[:10],
            )
    return parents


def _member_ops(
    snapshot: dict[str, object],
) -> dict[str, list[str]]:
    """member id → its machining operation kinds in plan order — same
    engine pass as ``_member_op_marks``, kept as one helper so the marks
    and the next-station map agree."""
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list) or not manufacturing:
        return {}
    try:
        from dekopen_engine.manufacturing import ManufacturingFactsV1
        from dekopen_engine.operations import operations_from_plan

        fact_units = [
            ManufacturingFactsV1.model_validate_json(json.dumps(fact))
            for fact in manufacturing
            if isinstance(fact, dict)
        ]
        ops = operations_from_plan(bars=[], fact_units=fact_units)
    except Exception:
        return {}
    members: dict[str, list[str]] = {}
    for op in ops:
        if op.host_kind == "MEMBER":
            members.setdefault(op.host, []).append(op.kind.value)
    return members


def _member_op_marks(
    snapshot: dict[str, object],
) -> dict[str, str]:
    """member id → 'mec' when it carries machining ops — derived from
    ``_member_ops`` so the mark and the next-station map never disagree."""
    return {
        member_id: "mec"
        for member_id, kinds in _member_ops(snapshot).items()
        if kinds
    }


def _cut_member_map(
    snapshot: dict[str, object], labels: dict[str, dict[object, str]]
) -> dict[tuple[str, ...], str]:
    """Cut-spec → member/reinforcement codes for saw output.

    A bar cut's piece_id is a sha256 of the cut spec, never the frozen member
    identity, so cut artifacts used to print hash prefixes. The join runs on
    the deterministic spec tuple. Identical members share one spec — the
    printed code lists every member the piece serves, which stays honest
    because those pieces are physically interchangeable. When members in
    one spec diverge in machining, each machined instance prints ``(mec.)``
    so the operator knows which stick to pull for the prep.
    """
    index = _cut_spec_index(snapshot)
    if not index:
        return {}
    op_marks = _member_op_marks(snapshot)
    out: dict[tuple[str, ...], str] = {}
    for key, ids in index.items():
        marks = {str(entity_id or ""): op_marks.get(str(entity_id or "")) for entity_id in ids}
        divergent = len(set(marks.values())) > 1
        out[key] = _join_codes(
            [
                (
                    labels["member" if key[0] == "PROFILE" else "reinforcement"].get(
                        entity_id, str(entity_id or "")[:10]
                    )
                    + (" (mec.)" if divergent and marks[str(entity_id or "")] else "")
                )
                for entity_id in ids
            ]
        )
    return out


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


def _infill_spec_index(
    snapshot: dict[str, object],
) -> dict[tuple[str, str, str], list[object]]:
    """(position, bay, leaf) → frozen infill ids — the id-level index behind
    ``_infill_code_map``, used by traceability to resolve a printed I-xx code
    back to the sheet pieces that serve it."""
    manufacturing = snapshot.get("manufacturing")
    if not isinstance(manufacturing, list):
        return {}
    spec: dict[tuple[str, str, str], list[object]] = {}
    for fact in manufacturing:
        if not isinstance(fact, dict):
            continue
        for item in _array(fact.get("infills"), "invalid_manufacturing_fact"):
            key = (
                str(item.get("position_id") or ""),
                str(item.get("bay_id") or ""),
                str(item.get("leaf_id") or ""),
            )
            spec.setdefault(key, []).append(item.get("infill_id"))
    return spec


def _infill_code_map(
    snapshot: dict[str, object], labels: dict[str, dict[object, str]]
) -> dict[tuple[str, str, str], str]:
    """(position, bay, leaf) → infill codes, so sheet/nested pieces print the
    I-xx identity the assembly map and glazing table already use instead of a
    sheet-local V-xx counter that collides with bay codes."""
    index = _infill_spec_index(snapshot)
    return {
        key: _join_codes(
            [
                labels["infill"].get(infill_id, str(infill_id or "")[:10])
                for infill_id in ids
            ]
        )
        for key, ids in index.items()
    }


def _infill_key(piece: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(piece.get("source_position_id") or ""),
        str(piece.get("bay_id") or ""),
        str(piece.get("leaf_id") or ""),
    )


def _location(labels: dict[str, dict[object, str]], bay_id: object, leaf_id: object) -> str:
    bay = labels["bay"].get(bay_id, _short_id(bay_id))
    if leaf_id in (None, ""):
        return str(bay)
    return f"{bay} / {labels['leaf'].get(leaf_id, _short_id(leaf_id))}"


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
            f"{escape(_CATEGORY_ES.get(_value(group.get('source_kind')), _value(group.get('source_kind'))))}</h2>"
            f"<p><strong>Largo:</strong> {escape(_dim(group.get('stock_length_mm')))} mm · "
            f"<strong>Barras:</strong> {escape(_value(group.get('purchased_bar_count')))}</p>"
        )
        for bar_value in _array(group.get("bars"), "invalid_stock_group"):
            bar = _object(bar_value, "invalid_cut_bar")
            cuts = [_object(item, "invalid_cut_piece")
                    for item in _array(bar.get("cuts"), "invalid_cut_bar")]
            # Deferred import: cut_pack borrows the shared helpers from this
            # module, so pulling the strip lazily keeps the dependency one-way.
            from production.cut_pack import _bar_svg

            remainder_label = (
                "retazo reutilizable"
                if bar.get("remainder_reusable")
                else "remanente"
            )
            body += (
                f"<h3>Barra {escape(_value(bar.get('bar_index')))} · "
                f"{escape(_value(bar.get('commercial_sku')))} · "
                f"{escape(_dim(bar.get('stock_length_mm')))} mm · "
                f"{remainder_label} {escape(_dim(bar.get('remainder_mm')))} mm"
                + (
                    f" · aprovechamiento {_pct(bar.get('yield_pct'))} %"
                    if bar.get("yield_pct") is not None
                    else ""
                )
                + "</h3>"
                + '<div class="bar-band">'
                + _bar_svg(bar, labels, cut_map, span_mm=Decimal("186"))
                + "</div>"
                + _table(
                    ["Sec.", "Pieza física", "Posición", "Vano / hoja", "SKU taller", "Corte mm", "Ángulos", "Flecha mm"],
                    [[cut.get("sequence"),
                      cut_map.get(_cut_key(cut), _short_id(cut.get("piece_id"))),
                      labels["position"].get(
                          cut.get("source_position_id"),
                          _short_id(cut.get("source_position_id")),
                      ),
                      (f"u{cut.get('unit_index')} · "
                       if cut.get("unit_index") is not None else "")
                      + _location(labels, cut.get("bay_id"), cut.get("leaf_id")),
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
            tolerance = _dim(r10.get("tolerance_mm"))
    # The checklist must bind to the physical units it covers — a QC hold has
    # to name the position it stops, not float over "the revision".
    units_rows = []
    for position in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot"):
        position = _object(position, "invalid_frozen_revision_snapshot")
        units_rows.append([
            f"P{_value(position.get('position_index'))}",
            _value(position.get("location_tag")),
            _TYPOLOGY_ES.get(_value(position.get("typology")), _value(position.get("typology"))),
            _value(position.get("quantity")),
            f"{_dim(position.get('width_mm'))} × {_dim(position.get('height_mm'))} mm",
        ])
    if units_rows:
        body += _table(
            ["Posición", "Ubicación", "Tipología", "Cant.", "Dimensiones"],
            units_rows,
            ["", "", "", "dimension", "dimension"],
        )
    # The Cumple box is a drawn element — glyph boxes (□/☐) rasterize as tofu
    # under several WeasyPrint font stacks.
    box = '<span class="qc-box"></span>'
    rows = [
        ["Escuadra de diagonales", f"Diferencia ≤ {tolerance} mm", box, "________________"],
        ["Burletes y estanqueidad", "Continuidad visual y cierre", box, "________________"],
        ["Desagües", "Libres y según diseño congelado", box, "________________"],
        ["Herrajes", "Operación y calibración física", box, "________________"],
        ["Vidrios / paneles", "Sin daño y correctamente retenidos", box, "________________"],
    ]
    body += _table(
        ["Control", "Criterio esperado", "Cumple", "Medición / observación"],
        [[check, criterion, _Raw(box_html), notes] for check, criterion, box_html, notes in rows],
    )
    body += (
        "<p><strong>Orden de trabajo / unidad:</strong> ______________________</p>"
        "<p><strong>Operador:</strong> ______________________________</p>"
        "<p><strong>Fecha de ejecución QC:</strong> __________________</p>"
        f"<p><strong>Resultado físico:</strong> {box} Pendiente &nbsp; {box} Conforme &nbsp; {box} No conforme</p>"
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
    price_by_index = {}
    for pos in _array(snapshot.get("positions"), "invalid_frozen_revision_snapshot"):
        pos = _object(pos, "invalid_frozen_revision_snapshot")
        price_by_index[str(pos.get("position_index"))] = pos.get("price_net")

    def _cost_row(item: object) -> list[object]:
        line = _array(item, "invalid_pricing_evidence")
        price = price_by_index.get(str(line[0]))
        if price is None:
            return [line[0], _money(line[1], currency), "—", "—", "—"]
        sell = _num(price)
        margin = sell - _num(line[1])
        pct = (
            f"{(margin / sell * 100).quantize(Decimal('0.1'))} %"
            if sell != 0
            else "—"
        )
        return [
            line[0],
            _money(line[1], currency),
            _money(sell, currency),
            _money(margin, currency),
            pct,
        ]

    body += '<p class="confidential">CONFIDENCIAL · SOLO PROPIETARIO</p>'
    body += _table(
        ["Posición", "Costo capturado", "Venta neta", "Margen", "Margen %"],
        [_cost_row(item) for item in costs],
        ["", "dimension", "dimension", "dimension", "dimension"],
    )
    cost_net = _num(pricing.get("applied_total_cost_net"))
    sell_net = _num(project.get("total_price_net"))
    margin_net = sell_net - cost_net
    margin_pct = (
        f"{(margin_net / sell_net * 100).quantize(Decimal('0.1'))} %"
        if sell_net != 0
        else "—"
    )
    body += _table(
        ["Costo neto", "Venta neta", "Margen neto", "Margen %", "Impuesto", "Venta total"],
        [[_money(pricing.get("applied_total_cost_net"), currency),
          _money(project.get("total_price_net"), currency),
          _money(margin_net, currency),
          margin_pct,
          _money(project.get("total_price_tax"), currency),
          _money(project.get("total_price_gross"), currency)]],
        ["dimension", "dimension", "dimension", "dimension", "", "dimension"],
    )
    status = realized.get("status")
    if status != "NOT_RECORDED" or realized.get("value") is not None:
        raise DocumentaryError("realized_waste_authority_invalid")
    body += "<h2>Merma realizada</h2><p><strong>NO REGISTRADA</strong> · valor: —</p></main>"
    return body


def _po_parties(order: dict[str, object], snapshot: dict[str, object]) -> str:
    """Buyer ↔ supplier party blocks + order meta strip (§3).

    The supplier reads: who is buying (org identity + delivery address),
    who they are (sealed eligibility contact), and the order facts —
    code, project, issue date, and the needed-by date set at send time."""
    details = _object(order.get("supplier_details") or {}, "invalid_order_snapshot")
    supplier_lines = "".join(
        f'<div class="po-party-line">{escape(_value(value))}</div>'
        for value in (
            details.get("tax_id") and f"RUT {_value(details['tax_id'])}",
            details.get("address"),
            details.get("phone"),
            details.get("email"),
        )
        if value
    )
    organization = snapshot.get("organization")
    org = organization if isinstance(organization, dict) else {}
    buyer_lines = "".join(
        f'<div class="po-party-line">{escape(_value(value))}</div>'
        for value in (
            org.get("tax_id") and f"RUT {_value(org['tax_id'])}",
            org.get("brand_address"),
            org.get("brand_phone"),
            org.get("brand_email"),
        )
        if value
    )
    buyer_name = _value(org.get("commercial_name"))
    if buyer_name == "—":
        buyer_name = _value(org.get("name"))
    needed = _value(order.get("expected_at"))
    needed_html = (
        f'<div class="tb-cell"><span class="tb-label">Requerida para</span>'
        f'<span class="tb-value po-needed">{escape(_cldate(needed))}</span></div>'
        if needed != "—"
        else ""
    )
    return (
        '<div class="po-parties">'
        f'<div class="po-party"><div class="po-party-role">Emisor / Entregar a</div>'
        f'<div class="po-party-name">{escape(buyer_name)}</div>{buyer_lines}</div>'
        f'<div class="po-party"><div class="po-party-role">Proveedor</div>'
        f'<div class="po-party-name">{escape(_value(order.get("supplier_name")))}</div>'
        f"{supplier_lines}</div></div>"
        '<div class="po-meta">'
        f'<div class="tb-cell"><span class="tb-label">Orden</span>'
        f'<span class="tb-value">{escape(_value(order.get("order_code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Proyecto</span>'
        f'<span class="tb-value">{escape(_value(order.get("project_code")))}</span></div>'
        f'<div class="tb-cell"><span class="tb-label">Emitida</span>'
        f'<span class="tb-value">{escape(_cldate(_value(order.get("confirmed_at"))))}</span></div>'
        f"{needed_html}"
        "</div>"
    )


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
        "organization": snapshot.get("organization"),
    }
    body, _ = _revision_header(pseudo_revision, "Pedido de perfiles", "DOC-04", workshop=True)
    body += (
        _po_parties(order, snapshot)
        + _table(
            ["SKU compra", "Descripción", "SKU taller", "Acabado", "Largo barra (mm)",
             "Cantidad", "Unidad", "Origen"],
            [[line.get("purchasing_sku"),
              (line.get("physical_stock_name")
               or _value(line.get("physical_stock_sku"))
               if line.get("physical_stock_name") or line.get("physical_stock_sku")
               else (_object(line.get("specification"), "invalid_order_line").get("description")
                     or _object(line.get("specification"), "invalid_order_line").get("manufacturer_name")
                     or "—")),
              ", ".join(_value(item) for item in _array(line.get("technical_skus"), "invalid_order_line")),
              _object(line.get("specification"), "invalid_order_line").get("color"),
              _object(line.get("specification"), "invalid_order_line").get("stock_length_mm"),
              line.get("quantity"), line.get("unit"),
              ", ".join(str(label) for label in _array(
                  line.get("source_trace_labels") or [], "invalid_order_line"
              ) if label)]
             for line in lines], ["", "", "", "", "dimension", "dimension", "", ""],
        )
        + "</main>"
    )
    return body


def _doc02(snapshot: dict[str, object]) -> str:
    """Supplier-facing glass order PDF — the same sealed order payload the
    DOC-02 XLSX renders, composed as a professional PO rather than a grid."""
    order = _object(snapshot.get("order"), "invalid_order_snapshot")
    revision = _object(snapshot.get("revision"), "invalid_order_snapshot")
    if order.get("order_type") != "SUPPLIER_GLASS_PO":
        raise DocumentaryError("document_scope_mismatch")
    lines = [_object(item, "invalid_order_line")
             for item in _array(snapshot.get("lines"), "invalid_order_snapshot")]
    pseudo_revision = {
        "project": {"code": order.get("project_code")},
        "revision": revision.get("revision_code"),
        "sealed_at": order.get("confirmed_at"),
        "organization": snapshot.get("organization"),
    }
    rows_data: list[list[object]] = []
    total_area = Decimal("0")
    for line in lines:
        spec = _object(line.get("specification"), "invalid_order_line")
        polishing = _object(spec.get("polishing"), "invalid_order_line")
        quantity = int(line["quantity"])
        width = Decimal(_value(spec.get("oriented_width_mm")))
        height = Decimal(_value(spec.get("oriented_height_mm")))
        area = width * height * quantity / Decimal("1000000")
        total_area += area
        rows_data.append([
            line.get("purchasing_sku"),
            spec.get("composition"),
            ", ".join(_value(item) for item in _array(
                line.get("technical_skus"), "invalid_order_line")),
            f"{_dim(spec.get('oriented_width_mm'))} × {_dim(spec.get('oriented_height_mm'))}",
            quantity,
            line.get("unit"),
            "/".join(
                edge_es
                for edge, edge_es in (
                    ("top", "SUP"), ("right", "DER"),
                    ("bottom", "INF"), ("left", "IZQ"),
                )
                if polishing.get(edge) is True
            ) or "SIN PULIDO",
            spec.get("location_tag"),
            _es_decimal(area, 2),
        ])
    rows_data.append(
        ["TOTAL", "—", "—", "—", "—", "—", "—", "—",
         _es_decimal(total_area, 2)]
    )
    body, _ = _revision_header(pseudo_revision, "Pedido de vidrios", "DOC-02", workshop=True)
    body += (
        _po_parties(order, snapshot)
        + _table(
            ["SKU compra", "Composición", "SKU taller", "Medidas (mm)",
             "Cantidad", "Unidad", "Pulido", "Ubicación", "Área m²"],
            rows_data, ["", "", "", "dimension", "dimension", "", "", "", "dimension"],
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
        "organization": snapshot.get("organization"),
    }
    body, _ = _revision_header(pseudo_revision, "Orden de compra", "DOC-08", workshop=True)
    body += (
        _po_parties(order, snapshot)
        + _table(
            ["SKU compra", "Descripción", "SKU taller",
             "Cantidad", "Unidad", "Detalle", "Origen"],
            [[line.get("purchasing_sku"),
              _object(line.get("specification"), "invalid_order_line").get("description")
              or _object(line.get("specification"), "invalid_order_line").get("manufacturer_name"),
              ", ".join(_value(item) for item in _array(line.get("technical_skus"), "invalid_order_line")),
              line.get("quantity"), line.get("unit"),
              "; ".join(
                  f"{key}={_spec_value(value)}"
                  for key, value in sorted(
                      _object(line.get("specification"), "invalid_order_line").items()
                  )
                  if key not in ("description", "manufacturer_name")
              ),
              ", ".join(str(label) for label in _array(
                  line.get("source_trace_labels") or [], "invalid_order_line"
              ) if label)]
             for line in lines], ["", "", "", "dimension", "", "", ""],
        )
        + "</main>"
    )
    return body


_DOC01_PAGE_SIZES = {"LETTER": "letter", "LEGAL": "legal", "A4": "a4"}


def render_document_html(
    document_type: str,
    snapshot: dict[str, object],
    *,
    render_context: dict | None = None,
    embed_fonts: bool = False,
) -> str:
    """HTML completo del documento — la misma composición que alimenta el
    PDF sellado, expuesta para vistas previas en pantalla que deben ser
    idénticas a lo que el cliente recibe. `embed_fonts` incrusta los Plex
    TTF como data-URI: el <iframe> de vista previa no puede leer file://."""
    if document_type == "DOC-01":
        body = _doc01(snapshot, render_context=render_context)
    if document_type == "DOC-01":
        body = _doc01(snapshot, render_context=render_context)
    elif document_type == "DOC-02":
        body = _doc02(snapshot)
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
    css = _CSS_EMBEDDED if embed_fonts else _CSS
    if document_type == "DOC-01":
        # Tamaño de papel del emisor (ajuste de organización sellado en
        # la revisión): Carta por defecto, Oficio o A4 por branding.
        organization = snapshot.get("organization")
        paper = (
            organization.get("doc_paper_size")
            if isinstance(organization, dict)
            else None
        )
        size = _DOC01_PAGE_SIZES.get(str(paper or "").upper(), "letter")
        if size != "letter":
            css += (
                f"\n@page {{ size: {size} portrait; margin: 13mm 12mm 22mm;"
                " @bottom-center { content: element(titleblock); } }}"
            )
    return (
        "<!doctype html><html lang=\"es-CL\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title>"
        f"<style>{css}</style></head><body>{body}</body></html>"
    )


def render_pdf_document(
    document_type: str,
    snapshot: dict[str, object],
    *,
    pdf_identifier: str,
    render_context: dict | None = None,
) -> tuple[bytes, str]:
    from weasyprint import HTML

    html = render_document_html(
        document_type, snapshot, render_context=render_context
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


def _tributary_notice(payload: dict[str, object]) -> str:
    """Leyenda de honestidad tributaria (P11).

    Si la organización no tenía la integración SII activa y certificada al
    emitir el documento — o el documento precede al marcador — la leyenda
    obligatoria es «Documento interno — no válido como documento tributario
    electrónico». Con integración certificada el archivo sigue siendo una
    copia interna: el respaldo tributario es el DTE firmado, y la leyenda lo
    dice sin hacerse pasar por él. En ninguno de los dos casos se imita el
    timbre electrónico (TED/PDF417) del SII.
    """
    state = payload.get("tributary")
    certified = isinstance(state, dict) and state.get("certified") is True
    if certified:
        return (
            '<p class="tributary-note">Documento interno — el respaldo '
            "tributario es el documento electrónico emitido al SII.</p>"
        )
    return (
        '<p class="tributary-note">Documento interno — no válido como '
        "documento tributario electrónico.</p>"
    )


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
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(receipt_code)}</strong><br>"
        f"Comprobante de pago<br>{escape(_cldate(issued_at))}</div></div>"
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
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
        + _tributary_notice(payload)
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
    delivery = payload.get("delivery")
    delivery = delivery if isinstance(delivery, dict) else {}
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
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(note_code)}</strong><br>"
        f"Guía de despacho<br>{escape(_cldate(issued_at))}</div></div>"
    )
    body += (
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
        "<h1>Guía de despacho</h1>"
        '<section class="hero"><p>Destinatario</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}</p>"
        f'<p class="total">'
        + ("Bultos" if units else "Unidades")
        + f': {escape(_value(totals.get("units")))}</p></section>'
    )
    # The guía proves movement to a physical destination — the delivery row
    # is that destination (scheduled before dispatch); without one the
    # project address is the fallback.
    delivery_lines = []
    if delivery.get("address"):
        delivery_lines.append(
            f"<strong>Dirección de entrega:</strong> {escape(_value(delivery.get('address')))}"
        )
    window = str(delivery.get("time_window") or "")
    window_es = {"AM": "AM", "PM": "PM", "JORNADA": "Jornada completa"}.get(
        window, window
    )
    if delivery.get("scheduled_date"):
        when = f"{escape(_cldate(str(delivery['scheduled_date'])))}"
        if window_es:
            when += f" · {escape(window_es)}"
        delivery_lines.append(f"<strong>Entrega programada:</strong> {when}")
    contact = " · ".join(
        part
        for part in (
            _value(delivery.get("contact_name")),
            _value(delivery.get("contact_phone")),
        )
        if part != "—"
    )
    if contact:
        delivery_lines.append(f"<strong>Contacto:</strong> {escape(contact)}")
    if delivery.get("installer_name"):
        delivery_lines.append(
            f"<strong>Instalador:</strong> {escape(_value(delivery.get('installer_name')))}"
        )
    if delivery_lines:
        body += "<p>" + "<br>".join(delivery_lines) + "</p>"
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
        + _tributary_notice(payload)
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
    "FIXED_SASH": "Fijo en hoja",
    "TURN": "Abatible",
    "TILT": "Solo abatimiento (banderola)",
    "BOTTOM_HUNG": "Abatimiento",
    "TOP_HUNG": "Proyectante",
    "TILT_TURN": "Oscilobatiente",
    "TURN_LEFT": "Abatible izquierda",
    "TURN_RIGHT": "Abatible derecha",
    "TILT_TURN_LEFT": "Oscilobatiente izquierda",
    "TILT_TURN_RIGHT": "Oscilobatiente derecha",
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
    # D05 seeded finish codes — newer positions seal the option's declared
    # `name` directly (`finish`/`color_*_detail` on the position row); this
    # map is the label fallback for binary-era and seed keys.
    "NOGAL": "Nogal",
    "NOGAL-EXT": "Nogal",
    "ANTRACITA": "Antracita",
    "COEX-ANTR": "Antracita coextruida",
    "NATURAL": "Natural anodizado",
    "PINTADO": "Pintado genérico",
    "RAL-9016": "Blanco tráfico RAL 9016",
    "RAL-7016": "Gris antracita RAL 7016",
    "MADERA": "Efecto madera nogal",
    "MADERA-EXT": "Efecto madera nogal",
}


def finish_key_label(key: object) -> str:
    """Label a D05 stock/finish key — a plain code maps through
    ``_COLOR_ES``; a bicolor ``EXT/INT`` key labels each face."""
    key = str(key or "")
    if "/" in key:
        ext, _, interior = key.partition("/")
        return (
            f"{_COLOR_ES.get(ext, ext)} exterior / "
            f"{_COLOR_ES.get(interior, interior)} interior"
        )
    return _COLOR_ES.get(key, key)

_CATEGORY_ES = {
    "PROFILE": "Perfil", "REINFORCEMENT": "Refuerzo", "GLASS": "Vidrio",
    "HARDWARE_KIT": "Kit herraje", "PANEL": "Panel",
    "ACCESSORY": "Accesorio", "FITTING": "Fijación",
}

_LIMIT_SOURCE_LABEL = {
    "SEED_SYNTHETIC": "catálogo demo",
    "MANUAL": "ficha del fabricante",
    "IMPORT": "importación revisada",
    "LEGACY_UNVERIFIED": "catálogo heredado",
}


def _limits_labels(limits: object) -> str:
    """Declared leaf envelope per typology, with its provenance as the source."""
    if not isinstance(limits, list) or not limits:
        return ""
    parts: list[str] = []
    for entry in limits:
        if not isinstance(entry, dict):
            continue
        opening = str(entry.get("opening_type") or "").replace("_", " ").title()
        low_w = entry.get("min_leaf_width_mm")
        high_w = entry.get("max_leaf_width_mm")
        low_h = entry.get("min_leaf_height_mm")
        high_h = entry.get("max_leaf_height_mm")
        span = ""
        if low_w or high_w or low_h or high_h:
            span = (
                f" {low_w or '—'}–{high_w or '—'} × "
                f"{low_h or '—'}–{high_h or '—'} mm"
            )
        source = _LIMIT_SOURCE_LABEL.get(
            str(entry.get("data_provenance") or ""), "catálogo"
        )
        parts.append(f"{opening or '—'}{span} (fuente: {source})")
    return " · ".join(parts)


def _opening_labels(tree: dict[str, object]) -> list[str]:
    """Distinct human opening names declared in the sealed tree (e.g.
    "Oscilobatiente · izquierda") — the card reads what the product
    actually does, not only its typology bucket. Spec-form payloads
    (D03 `opening`/`leaves`/`unit_kind`) resolve through the engine's
    own glossary so the document and the editor name them identically."""
    labels: list[str] = []

    def walk(node: object, unit: UnitKind = UnitKind.WINDOW) -> None:
        if not isinstance(node, dict):
            return
        try:
            kind = UnitKind(str(node.get("unit_kind") or unit.value))
        except ValueError:
            kind = unit
        if isinstance(node.get("leaves"), list):
            try:
                spec = OpeningSpec(
                    unit_kind=kind, leaves=_parse_leaves(node["leaves"])
                )
            except (InvalidEngineRequest, ValueError):
                spec = None
            if spec is not None:
                label = spec_display_name_es(spec)
                if label not in labels:
                    labels.append(label)
        elif isinstance(node.get("opening"), dict):
            try:
                leaf = _parse_opening(node["opening"])
            except InvalidEngineRequest:
                leaf = None
            if leaf is not None:
                label = opening_leaf_name_es(leaf, kind)
                if label not in labels:
                    labels.append(label)
        opening = str(node.get("opening_type") or "")
        if opening and opening != "FIXED":
            label = _TYPOLOGY_ES.get(opening, opening)
            hand = str(node.get("door_handedness") or "")
            if hand == "LEFT":
                label += " · izquierda"
            elif hand == "RIGHT":
                label += " · derecha"
            if label not in labels:
                labels.append(label)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                walk(child, kind)

    assembly = tree.get("assembly")
    if isinstance(assembly, dict):
        modules = assembly.get("modules")
        if isinstance(modules, list):
            for module in modules:
                if isinstance(module, dict):
                    walk(module.get("tree"))
    else:
        walk(tree)
    return labels


_ROLE_ES = {
    "FRAME": "Marco", "SASH": "Hoja", "MULLION_V": "Montante",
    "MULLION_H": "Travesaño", "INVERSOR": "Inversor",
    "GLAZING_BEAD": "Junquillo", "COUPLER": "Cople",
    "ADDITIONAL": "Adicional", "THRESHOLD": "Umbral", "CHANNEL": "Canal",
}

_SLOT_ES = {
    "OUTER_TOP": "Lado superior marco",
    "OUTER_BOTTOM": "Lado inferior marco",
    "LEAF_TOP": "Lado superior hoja",
    "LEAF_BOTTOM": "Lado inferior hoja",
    "CENTER": "Centro",
    "PRIMARY": "Principal",
    "SECONDARY": "Secundaria",
    "LEFT": "Izquierda", "RIGHT": "Derecha",
    "TOP": "Superior", "BOTTOM": "Inferior",
    "left": "Izquierda", "right": "Derecha",
    "top": "Superior", "bottom": "Inferior",
}


def _finish(ci: object, ce: object) -> str:
    # Encargo D05 format: «<exterior> exterior / <interior> interior».
    interior = _COLOR_ES.get(ci, ci)
    exterior = _COLOR_ES.get(ce, ce)
    if interior == exterior:
        return str(interior)
    return f"{exterior} exterior / {interior} interior"


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
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(invoice_code)}</strong><br>"
        f"Factura<br>{escape(_cldate(issued_at))}</div></div>"
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
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
        f'<p class="total">Total: {escape(_money(deal.get("total_gross"), currency))}</p>'
        "</section>"
    )
    def _position_description(position: dict) -> str:
        """Descripción humana de la línea: tipología + medidas + ubicación,
        nunca el código técnico solo."""
        typology = _TYPOLOGY_ES.get(
            _value(position.get("typology")), _value(position.get("typology"))
        )
        parts = [f"P{position.get('position_index')} · {typology}"]
        width, height = position.get("width_mm"), position.get("height_mm")
        if width not in (None, "") and height not in (None, ""):
            parts.append(
                f"{_dim(width)}\u00a0×\u00a0{_dim(height)} mm"
            )
        location = _value(position.get("location_tag"))
        if location != "—":
            parts.append(location)
        return " — ".join(parts)

    def _unit_net(position: dict):
        """Unitario neto sellado (line_detail); fallback: neto/cantidad."""
        unit = position.get("unit_net")
        if unit not in (None, ""):
            return unit
        price = position.get("price_net")
        quantity = position.get("quantity")
        if price in (None, "") or quantity in (None, 0, "0"):
            return None
        return _num(price) / _num(quantity)

    def _discount_pct_fraction(position: dict) -> Decimal:
        pct = _num(position.get("discount_pct") or 0)
        return pct / 100 if pct > 1 else pct

    if positions:
        discount_pcts = sorted(
            {
                _discount_pct_fraction(position)
                for position in positions
                if _discount_pct_fraction(position) > 0
            }
        )
        body += (
            "<h2>Detalle</h2>"
            + _table(
                ["Cantidad", "Descripción", "Unitario neto", "Total neto"],
                [
                    [
                        position.get("quantity"),
                        _position_description(position),
                        (
                            _money(_unit_net(position), currency)
                            if _unit_net(position) is not None
                            else "—"
                        ),
                        (
                            _money(position.get("price_net"), currency)
                            if position.get("price_net") not in (None, "")
                            else "—"
                        ),
                    ]
                    for position in positions
                ],
                ["dimension", "", "dimension", "dimension"],
            )
        )
    else:
        discount_pcts = []
    payment_terms = _value(project.get("payment_terms"))
    if payment_terms != "—":
        body += f"<p><strong>Condiciones de pago:</strong> {escape(payment_terms)}</p>"
    if discount_pcts:
        labels = " / −".join(
            _discount_label(str(pct)) for pct in discount_pcts
        )
        subtotal = _money(deal.get("total_net_before_discount"), currency)
        body += (
            "<p><strong>Descuento aplicado</strong> (−" + escape(labels) + ")"
            + (
                f" — posiciones antes del descuento: {escape(subtotal)}"
                if _value(deal.get("total_net_before_discount")) != "—"
                else ""
            )
            + "</p>"
        )
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
        + _tributary_notice(payload)
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
    # Sealed credit: an explicit amount stays partial; legacy payloads without
    # the field credited the full invoice.
    credited = payload.get("credit_amount_gross")
    if credited in (None, ""):
        credited = deal.get("total_gross")
    partial = payload.get("credit_partial") is True
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
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(credit_code)}</strong><br>"
        f"Nota de crédito<br>{escape(_cldate(issued_at))}</div></div>"
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
        "<h1>Nota de crédito</h1>"
        '<section class="hero"><p>Acreditar a</p>'
        f"<h2>{escape(_value(project.get('client_name')))}</h2>"
        f"<p>RUT: {escape(_value(project.get('client_rut')))}</p>"
        f'<p class="total">Crédito: {escape(_money(credited, currency))}</p></section>'
        + _tributary_notice(payload)
    )
    reference_verb = "abono parcial de la Factura" if partial else "anula Factura"
    body += (
        f"<p><strong>Referencia:</strong> {reference_verb} {escape(invoice_code)}"
        + (
            f" emitida el {escape(_cldate(invoice.get('issued_at')))}"
            if invoice.get("issued_at")
            else ""
        )
        + "</p>"
    )
    if partial:
        body += (
            "<p><strong>Crédito parcial:</strong> la factura queda vigente por "
            f"el saldo de {escape(_money(_num(deal.get('total_gross')) - _num(credited), currency))}.</p>"
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
                        f"{_dim(position.get('width_mm'))}\u00a0×\u00a0"
                        f"{_dim(position.get('height_mm'))}"
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
    if partial:
        # Gross-level truth only — a partial credit's net/IVA split is the
        # fiscal counter-document's job (DTE-61), not this internal note's.
        body += (
            "<h2>Totales acreditados</h2>"
            + _table(
                ["Monto acreditado", "Total factura", "Saldo de la factura"],
                [
                    [
                        _money(credited, currency),
                        _money(deal.get("total_gross"), currency),
                        _money(_num(deal.get("total_gross")) - _num(credited), currency),
                    ]
                ],
                ["dimension", "dimension", "dimension"],
            )
        )
    else:
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
        )
    body += _tributary_notice(payload)
    body += (
        "<div class=\"signoff\"><div class=\"signature\"></div>"
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
        f'<div class="masthead">{_miter(_brand_accent(organization))}{_brand_block(organization)}'
        '<div class="meta">'
        f"<strong>{escape(confirmation_code)}</strong><br>"
        f"Comprobante de entrega<br>{escape(_cldate(issued_at))}</div></div>"
        f'<div class="rule-stack" style="border-top-color:{_brand_accent(organization)}"></div>'
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
    body += _tributary_notice(payload)
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
