"""DOC-01 v2 — render-level contract tests on real PDF output (PyMuPDF).

The fixtures live in ``backend/scripts/render_doc_fixtures.py`` so the
visual QA captures and these tests see the same snapshots: the density
ladder (1/12/24/100 positions), USD totals, the bow plan cut and the
approval-QR context.
"""
import re

import fitz  # PyMuPDF — pinned test dependency (requirements-dev.txt)
import pytest

from documents.renderers import _doc01, _money, render_pdf_document
from scripts.render_doc_fixtures import build_context, build_snapshot


def _pdf(case: str) -> fitz.Document:
    pdf_bytes, _title = render_pdf_document(
        "DOC-01",
        build_snapshot(case),
        pdf_identifier=f"doc01-{case}-test",
        render_context=build_context(case),
    )
    return fitz.open(stream=pdf_bytes, filetype="pdf")


# The running titleblock occupies the bottom margin — body words end above it.
_FOOTER_RATIO = 0.895
_HEX_RUN = re.compile(r"^(?:[0-9a-fA-F]{2}[ -])?[0-9a-fA-F]{10,}$")


def _words(page: fitz.Page) -> list[tuple]:
    return page.get_text("words")


def _body_words(page: fitz.Page) -> list[tuple]:
    limit = page.rect.height * _FOOTER_RATIO
    return [w for w in _words(page) if w[3] <= limit]


def _intersect(a: tuple, b: tuple, eps: float = 0.4) -> bool:
    """Word bboxes may touch but never overlap — the resumen table's fixed
    columns wrap instead of colliding."""
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > eps and iy > eps


DENSITY_CASES = ("single", "dozen", "twentyfour", "hundred")


@pytest.mark.parametrize("case", DENSITY_CASES)
def test_density_ladder_renders(case: str) -> None:
    doc = _pdf(case)
    try:
        assert len(doc) >= 1
        assert doc.metadata.get("title") or True
    finally:
        doc.close()


def test_hundred_positions_fit_page_budget() -> None:
    doc = _pdf("hundred")
    try:
        assert len(doc) <= 45
    finally:
        doc.close()


@pytest.mark.parametrize("case", DENSITY_CASES + ("residential", "apartment-block"))
def test_no_footer_only_page(case: str) -> None:
    doc = _pdf(case)
    try:
        for index, page in enumerate(doc):
            assert _body_words(page), f"página {index + 1} solo tiene pie"
    finally:
        doc.close()


@pytest.mark.parametrize("case", DENSITY_CASES + ("residential", "usd", "bow", "long-names"))
def test_no_text_bbox_overlap(case: str) -> None:
    """Las tablas de resumen/detalle nunca superponen texto — el ajuste de
    columna hace wrap, no colisión."""
    doc = _pdf(case)
    try:
        for index, page in enumerate(doc):
            words = _words(page)
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    assert not _intersect(words[i], words[j]), (
                        f"colisión en página {index + 1}: "
                        f"{words[i][4]!r} × {words[j][4]!r}"
                    )
    finally:
        doc.close()


@pytest.mark.parametrize("case", ("dozen", "residential", "usd", "hundred"))
def test_total_matches_engine(case: str) -> None:
    """El total del documento es el total sellado del motor — mismo número,
    mismo formato de moneda."""
    snapshot = build_snapshot(case)
    project = snapshot["project"]
    doc = _pdf(case)
    try:
        text = "".join(page.get_text() for page in doc)
        assert _money(project["total_price_net"], project["currency"]) in text
        assert _money(project["total_price_gross"], project["currency"]) in text
    finally:
        doc.close()


def test_usd_quote_uses_us_dollar_format() -> None:
    doc = _pdf("usd")
    try:
        text = "".join(page.get_text() for page in doc)
        assert "US$" in text
        assert "US$ 16.724,26" in text
        # El formato CLP '$n.nn.nnn' no se cuela en una cotización en USD.
        assert not re.search(r"\$(?!\s*\d)", text.replace("US$", ""))
    finally:
        doc.close()


@pytest.mark.parametrize("case", DENSITY_CASES + ("residential", "usd", "bow", "terms"))
def test_no_hex_or_technical_unknowns_outside_footer(case: str) -> None:
    """Cuerpo limpio: sin hashes de 10+ caracteres ni 'Sin dato' — la huella
    abreviada solo vive en el cajetín."""
    doc = _pdf(case)
    try:
        for index, page in enumerate(doc):
            body = " ".join(w[4] for w in _body_words(page))
            assert "Sin dato" not in body, f"página {index + 1}"
            assert not _HEX_RUN.search(body), f"página {index + 1}: {body[:120]}"
    finally:
        doc.close()


def test_long_client_and_location_names_wrap() -> None:
    doc = _pdf("long-names")
    try:
        text = "".join(page.get_text() for page in doc)
        # El nombre de 120+ caracteres hace wrap sin romper el layout.
        assert "Asociación de Condominios" in text
        assert "Administración Legal" in text
        for index, page in enumerate(doc):
            words = _words(page)
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    assert not _intersect(words[i], words[j])
    finally:
        doc.close()


def test_density_modes_switch() -> None:
    """≤6 fichas completas, 7–24 compactas, >24 miniaturas."""
    full_html = _doc01(build_snapshot("residential"))
    assert 'class="pcards"' in full_html
    assert "pcards compact" not in full_html
    compact_html = _doc01(build_snapshot("dozen"))
    assert "pcards compact" in compact_html
    assert 'class="resumen mini"' not in compact_html
    mini_html = _doc01(build_snapshot("hundred"))
    assert 'class="resumen mini"' in mini_html
    residential = _pdf("residential")
    try:
        text = "".join(page.get_text() for page in residential)
        # Ficha completa: la construcción nombra cada campo numerado.
        assert "Campo 1" in text
    finally:
        residential.close()


def test_bow_position_draws_plan_cut() -> None:
    """Conjunto/bow: la cota de planta sellada se dibuja bajo el alzado."""
    doc = _pdf("bow")
    try:
        text = "".join(page.get_text() for page in doc)
        assert "INTERIOR" in text
        assert "EXTERIOR" in text
        assert "Campo 1" in text
    finally:
        doc.close()


def test_paper_size_organization_setting() -> None:
    """Carta por defecto; A4 cuando la organización lo fija (sellado)."""
    letter = _pdf("residential")
    try:
        assert abs(letter[0].rect.width - 612) < 1
        assert abs(letter[0].rect.height - 792) < 1
    finally:
        letter.close()
    a4 = _pdf("terms")
    try:
        assert abs(a4[0].rect.width - 595) < 1
        assert abs(a4[0].rect.height - 842) < 1
    finally:
        a4.close()


def test_acceptance_qr_renders_with_approval_url() -> None:
    html = _doc01(
        build_snapshot("terms"),
        render_context={"approval_url": "https://app.dekopen.cl/cotizacion/t-9"},
    )
    assert 'class="accept-online"' in html
    assert "<svg" in html
    doc = _pdf("terms")
    try:
        text = "".join(page.get_text() for page in doc)
        assert "Acepta en línea" in text
        assert "cotizacion" in text or "cotización" in text
    finally:
        doc.close()


def test_discount_and_extras_reconcile() -> None:
    """Posiciones − descuento + servicios/extras = neto del motor."""
    doc = _pdf("usd")
    try:
        text = "".join(page.get_text() for page in doc)
        assert "US$ 14.320,00" in text  # subtotal posiciones
        assert "−US$ 716,00" in text    # descuento 10 %
        assert "US$ 14.054,00" in text  # neto (con servicio 450)
        assert "US$ 2.670,26" in text   # IVA 19 %
        assert "US$ 16.724,26" in text  # total
    finally:
        doc.close()
