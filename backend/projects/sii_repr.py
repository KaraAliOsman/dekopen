"""Fiscal identity on printed copies — the "representación impresa" cover.

An unstamped PDF is an internal document. The moment a DTE exists, the copy a
customer receives must carry the document's fiscal identity: emisor RUT and
razón social, the stamped folio, the DTE type and the TED barcode (SII's
PDF417 timbre). Sealed artifacts stay immutable — this module composes a
*new* sealed artifact: a fiscal cover page (rendered from the sealed DTE XML
itself) followed by the untouched sealed document body, stored with its own
hash on the project_dtes row.
"""

from html import escape
from io import BytesIO

import pdf417gen
from defusedxml import ElementTree
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

from authentication.errors import contract_error

_DTE_NAME = {
    33: "Factura electrónica",
    52: "Guía de despacho electrónica",
    61: "Nota de crédito electrónica",
}


_SII_NS = "{http://www.sii.cl/SiiDte}"


def _find(node, path):
    """Namespaced-or-plain lookup — an Element without children is falsy, so
    `or` would silently fall through; test explicitly."""
    found = node.find(path)
    if found is not None:
        return found
    if path.startswith(".//"):
        return node.find(".//" + _SII_NS + path[3:])
    return node.find("/".join(_SII_NS + part for part in path.split("/")))


def _fields(dte_xml: bytes) -> dict:
    """The fiscal facts the cover prints — all from the sealed XML, which is
    itself the stamped authority."""
    try:
        root = ElementTree.fromstring(dte_xml)
    except ElementTree.ParseError:
        raise contract_error(500, "sii_dte_xml_unreadable", "El DTE sellado no es XML legible.")
    doc = _find(root, ".//Documento")
    if doc is None:
        raise contract_error(500, "sii_dte_xml_unreadable", "El DTE sellado no trae Documento.")
    ted = _find(doc, "TED")
    if ted is None or _find(ted, "DD") is None:
        raise contract_error(500, "sii_dte_xml_unreadable", "El DTE sellado no trae TED.")
    iddoc = _find(doc, "Encabezado/IdDoc")
    emisor = _find(doc, "Encabezado/Emisor")
    receptor = _find(doc, "Encabezado/Receptor")
    if iddoc is None or emisor is None or receptor is None:
        raise contract_error(500, "sii_dte_xml_unreadable", "El DTE sellado está incompleto.")

    def text(node, tag):
        return (_find(node, tag).text or "") if _find(node, tag) is not None else ""

    return {
        "ted_xml": ElementTree.tostring(ted, encoding="unicode"),
        "tipo": int(text(iddoc, "TipoDTE") or "0"),
        "folio": text(iddoc, "Folio").strip(),
        "fecha": text(iddoc, "FchEmis").strip(),
        "rut_emisor": text(emisor, "RUTEmisor").strip(),
        "razon_social": text(emisor, "RznSoc").strip(),
        "rut_receptor": text(receptor, "RUTRecep").strip(),
        "receptor": text(receptor, "RznSocRecep").strip(),
    }


def _cover_html(f: dict) -> str:
    svg_root = pdf417gen.render_svg(
        pdf417gen.encode(f["ted_xml"], columns=6), scale=3, ratio=3
    ).getroot()
    barcode = ElementTree.tostring(svg_root, encoding="unicode")
    tipo_name = _DTE_NAME.get(f["tipo"], f"DTE {f['tipo']}")
    esc = {k: escape(str(v)) for k, v in f.items() if k != "ted_xml"}
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
@page {{ size: letter; margin: 14mm; }}
body {{ font-family: 'DejaVu Sans', sans-serif; color: #14181d; margin: 0; }}
.band {{ border-top: 6px solid #14181d; padding-top: 6mm; }}
.title {{ font-size: 8.5pt; letter-spacing: .14em; text-transform: uppercase;
         color: #5a6570; margin-bottom: 3mm; }}
h1 {{ font-size: 21pt; margin: 0 0 1mm; }}
.rut {{ font-size: 13pt; font-weight: 700; margin: 0; }}
.meta {{ width: 100%; border-collapse: collapse; margin: 5mm 0 4mm; }}
.meta td {{ border: 0.4pt solid #c6ccd2; padding: 3.2mm 4mm; }}
.meta .k {{ font-size: 7pt; letter-spacing: .1em; text-transform: uppercase;
           color: #5a6570; width: 30mm; }}
.meta .v {{ font-size: 13pt; font-weight: 700; }}
.ted {{ border: 0.4pt solid #c6ccd2; padding: 3mm; text-align: center; margin-top: 3mm; }}
.ted svg {{ width: 128mm; }}
.note {{ font-size: 7.5pt; color: #5a6570; margin-top: 4mm; text-align: center; }}
.foot {{ margin-top: 7mm; font-size: 7pt; color: #8a929a; text-align: center; }}
</style></head><body>
<div class="band">
  <div class="title">Representación impresa · Documento tributario electrónico</div>
  <h1>{esc['razon_social']}</h1>
  <p class="rut">RUT {esc['rut_emisor']}</p>
  <table class="meta">
    <tr><td class="k">Documento</td><td class="v">{tipo_name} (DTE {f['tipo']})</td>
        <td class="k">Folio</td><td class="v">N° {esc['folio']}</td></tr>
    <tr><td class="k">Fecha de emisión</td><td class="v">{esc['fecha']}</td>
        <td class="k">Receptor</td><td class="v">{esc['receptor']} · RUT {esc['rut_receptor']}</td></tr>
  </table>
  <div class="ted">{barcode}</div>
  <div class="note">Timbre electrónico del SII — verifique el documento con la resolución
      correspondiente en www.sii.cl</div>
</div>
<div class="foot">Documento generado con DEKOPEN</div>
</body></html>"""


def compose_tributario_pdf(*, dte_xml: bytes, parent_pdf: bytes) -> bytes:
    """Fiscal cover page + the sealed document body, merged. Both inputs are
    immutable evidence; the composition is deterministic from them."""
    cover_pdf = HTML(string=_cover_html(_fields(dte_xml))).write_pdf()
    writer = PdfWriter()
    for source in (BytesIO(cover_pdf), BytesIO(parent_pdf)):
        for page in PdfReader(source).pages:
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
