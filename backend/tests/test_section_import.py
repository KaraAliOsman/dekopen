"""Section drawing ingestion — parser + service contract tests."""
import pytest

from catalogs import section_import, service


SQUARE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="70mm" '
    'viewBox="0 0 60 70">'
    '<polygon points="0,0 60,0 60,70 0,70"/></svg>'
).encode()


def test_svg_polygon_mm_units():
    result = section_import.import_section("frame.svg", SQUARE_SVG)
    assert result.format == "svg"
    assert result.mm_per_unit is not None and str(result.mm_per_unit) == "1"
    assert len(result.candidates) == 1
    assert result.candidates[0]["area"] == "4200.00"
    assert result.warnings == []


def test_svg_viewbox_ratio_derives_scale():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="70mm" '
        'viewBox="0 0 600 700">'
        '<polygon points="0,0 600,0 600,700 0,700"/></svg>'
    ).encode()
    result = section_import.import_section("scaled.svg", content)
    # 60 physical mm across 600 user units → 0.1 mm per unit.
    assert str(result.mm_per_unit) == "0.1"


def test_svg_aspect_none_refuses_single_scale():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="60mm" height="70mm" '
        'viewBox="0 0 600 350" preserveAspectRatio="none">'
        '<polygon points="0,0 600,0 600,350 0,350"/></svg>'
    ).encode()
    result = section_import.import_section("stretch.svg", content)
    assert result.mm_per_unit is None
    assert any("preserveAspectRatio" in w for w in result.warnings)


def test_svg_viewbox_without_physical_size_needs_confirmation():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 60 70">'
        '<polygon points="0,0 60,0 60,70 0,70"/></svg>'
    ).encode()
    result = section_import.import_section("unscaled.svg", content)
    assert result.mm_per_unit is None
    assert any("scale must be confirmed" in w for w in result.warnings)


def test_svg_polyline_must_be_closed():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm">'
        '<polyline points="0,0 60,0 60,70"/>'
        '<polygon points="0,0 60,0 60,70 0,70"/></svg>'
    ).encode()
    result = section_import.import_section("profile.svg", content)
    assert len(result.candidates) == 1
    assert any("open outline" in w for w in result.warnings)


def test_svg_path_and_transforms_apply():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="80mm">'
        '<g transform="translate(10,5) scale(2)">'
        '<path d="M0,0 L30,0 L30,35 L0,35 Z"/></g></svg>'
    ).encode()
    result = section_import.import_section("sash.svg", content)
    pts = result.candidates[0]["points"]
    # The Z-close duplicate is stripped — the contract wants distinct vertices
    # at the transform's fixed 0.000001mm precision.
    assert [p[0] for p in pts] == ["10.000000", "70.000000", "70.000000", "10.000000"]
    assert result.candidates[0]["area"] == "4200.00"


def test_svg_curved_path_samples_to_polygon():
    content = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm">'
        '<path d="M0,0 L60,0 C60,10 60,20 60,30 L0,30 Z"/></svg>'
    ).encode()
    result = section_import.import_section("bead.svg", content)
    assert len(result.candidates) == 1
    # Curve sampled: more vertices than the 4 corners.
    assert len(result.candidates[0]["points"]) > 8


def test_dxf_polyline_vertices_emit_candidate():
    content = (
        "0\nSECTION\n2\nENTITIES\n0\nPOLYLINE\n70\n1\n"
        "0\nVERTEX\n10\n0\n20\n0\n"
        "0\nVERTEX\n10\n60\n20\n0\n"
        "0\nVERTEX\n10\n60\n20\n70\n"
        "0\nVERTEX\n10\n0\n20\n70\n"
        "0\nSEQEND\n0\nENDSEC\n0\nEOF\n"
    ).encode()
    result = section_import.import_section("frame.dxf", content)
    assert len(result.candidates) == 1
    assert result.candidates[0]["tag"].startswith("POLYLINE")
    assert result.candidates[0]["area"] == "4200.00"


def test_svg_px_flagged_for_review():
    content = b'<svg xmlns="http://www.w3.org/2000/svg" width="60px"><polygon points="0,0 60,0 60,70 0,70"/></svg>'
    result = section_import.import_section("web.svg", content)
    assert any("96 dpi" in w for w in result.warnings)


LWPOLY_DXF = """  0
SECTION
  2
HEADER
  9
$INSUNITS
 70
     4
  0
ENDSEC
  0
SECTION
  2
ENTITIES
  0
LWPOLYLINE
  5
100
 70
     1
 90
        4
 10
0.0
 20
0.0
 10
60.0
 20
0.0
 10
60.0
 20
70.0
 10
0.0
 20
70.0
  0
ENDSEC
  0
EOF
""".encode()


def test_dxf_closed_lwpolyline_insunits_mm():
    result = section_import.import_section("frame.dxf", LWPOLY_DXF)
    assert result.format == "dxf"
    assert result.mm_per_unit is not None and str(result.mm_per_unit) == "1"
    assert result.candidates[0]["area"] == "4200.00"
    assert len(result.candidates[0]["points"]) == 4


def test_dxf_without_insunits_warns():
    content = LWPOLY_DXF.replace(b"  9\n$INSUNITS\n 70\n     4\n", b"")
    result = section_import.import_section("drawing.dxf", content)
    assert result.mm_per_unit is None
    assert any("$INSUNITS" in w for w in result.warnings)


def test_dxf_bulge_expands_arc():
    content = LWPOLY_DXF.replace(
        b" 10\n60.0\n 20\n70.0\n", b" 10\n60.0\n 20\n70.0\n 42\n1.0\n"
    )
    result = section_import.import_section("arched.dxf", content)
    # The bulged closing edge samples into additional points.
    assert len(result.candidates[0]["points"]) > 4


def test_dxf_open_polyline_skipped():
    content = LWPOLY_DXF.replace(b" 70\n     1\n", b" 70\n     0\n")
    with pytest.raises(section_import.SectionImportError):
        section_import.import_section("open.dxf", content)


def test_empty_file_rejected():
    with pytest.raises(section_import.SectionImportError):
        section_import.import_section("blank.dxf", b"")


class _Storage:
    def __init__(self):
        self.writes = []

    def upload_immutable(self, object_key, content, content_type):
        self.writes.append((object_key, content_type))


def test_service_parses_and_stores(monkeypatch):
    storage = _Storage()
    monkeypatch.setattr(
        "documents.storage.SupabaseDocumentStorage", lambda: storage
    )
    # The service imports the storage class lazily inside the function.
    import documents.storage as storage_mod

    monkeypatch.setattr(storage_mod, "SupabaseDocumentStorage", lambda: storage)
    out = service.import_section_drawing(
        org_id="org-1",
        file_name="frame.dxf",
        content=LWPOLY_DXF,
        content_type="application/dxf",
    )
    assert out["document_path"].startswith("section-imports/org-1/")
    assert out["document_path"].endswith("/frame.dxf")
    assert out["format"] == "dxf"
    assert out["mm_per_unit"] is not None
    assert storage.writes and storage.writes[0][1] == "application/dxf"


def test_service_rejects_bad_name(monkeypatch):
    with pytest.raises(Exception) as exc:
        service.import_section_drawing(
            org_id="org-1", file_name="../escape.dxf", content=LWPOLY_DXF, content_type=""
        )
    assert "section_file_name" in str(exc.value)


def test_service_rejects_unparseable(monkeypatch):
    with pytest.raises(Exception) as exc:
        service.import_section_drawing(
            org_id="org-1", file_name="notes.txt", content=b"hello world", content_type=""
        )
    assert "section" in str(exc.value)


def test_svg_path_with_two_closed_subpaths_yields_two_candidates():
    from catalogs.section_import import parse_svg

    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
        width="100mm" height="100mm">
      <path d="M 0 0 L 100 0 L 100 100 L 0 100 Z
               M 20 20 L 80 20 L 80 80 L 20 80 Z"/>
    </svg>"""
    result = parse_svg(svg)
    assert len(result.candidates) == 2


def test_svg_deeply_nested_groups_do_not_recurse_forever():
    from catalogs.section_import import parse_svg

    depth = 200
    svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        + b"<g>" * depth
        + b'<rect x="0" y="0" width="5" height="5"/>'
        + b"</g>" * depth
        + b"</svg>"
    )
    try:
        result = parse_svg(svg)
    except Exception as error:  # no closed candidate is fine — never RecursionError
        assert not isinstance(error, RecursionError)
        return
    assert any("deeper than" in w for w in result.warnings)


def test_svg_z_returns_pen_to_subpath_start():
    """After Z, a relative move resolves from the closed subpath's start —
    the second contour must not shift by the first's last vertex."""
    from catalogs.section_import import parse_svg

    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm">
      <path d="M 0 0 L 10 0 L 10 10 L 0 10 Z m 5 5 l 5 0 l 0 5 l -5 0 z"/>
    </svg>"""
    result = parse_svg(svg)
    assert len(result.candidates) == 2
    starts = {tuple(c["points"][0]) for c in result.candidates}
    assert ("5.000000", "5.000000") in starts  # relative `m` after Z resolved from (0,0)


def test_svg_path_token_budget():
    from catalogs.section_import import SectionImportError, parse_svg
    import pytest

    huge = "M 0 0 " + "l 1 0 " * 40000
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{huge}"/></svg>'
    with pytest.raises(SectionImportError, match="budget"):
        parse_svg(svg.encode())


def test_svg_subpath_count_is_bounded():
    from catalogs.section_import import parse_svg

    subs = " ".join(
        f"M {i} {i} l 1 0 l 0 1 z" for i in range(200)
    )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{subs}"/></svg>'
    result = parse_svg(svg.encode())
    # The document parses but the subpath budget trims before 200 outlines.
    assert len(result.candidates) <= 8


def test_dxf_vertex_budget():
    from catalogs.section_import import SectionImportError, parse_dxf
    import pytest

    rows = ["0", "SECTION", "2", "ENTITIES", "0", "LWPOLYLINE", "70", "1"]
    for i in range(2100):
        rows += ["10", str(i), "20", str(i)]
    rows += ["0", "ENDSEC", "0", "EOF"]
    with pytest.raises(SectionImportError, match="budget"):
        parse_dxf(("\n".join(rows)).encode())


def test_svg_mixed_curve_families_do_not_cross_reflect():
    """Per SVG spec, S reflects only after C/S and T only after Q/T. A
    quadratic control point must never reflect into a cubic S (and vice
    versa) — the smooth command falls back to the current position."""
    from catalogs.section_import import ARC_SEGMENTS, _path_points
    from decimal import Decimal

    subs, _ = _path_points("M0 0 Q10 10 20 0 S30 -10 40 0 z")
    points = subs[0]
    # S after Q: c1 falls back to pos=(20,0). First S sample sits at
    # y≈-0.19 with the fallback vs y≈-2.29 when Q's (10,10) is wrongly
    # reflected into the cubic — index 1+ARC_SEGMENTS is that sample.
    first_s = points[1 + ARC_SEGMENTS]
    assert first_s[1] > Decimal("-1")

    subs2, _ = _path_points("M0 0 C0 10 10 10 20 0 T40 0 z")
    # T after C: no quadratic reflection — the segment is flat (y=0);
    # a wrongly reflected cubic c2=(10,10) dips to y≈-1.53.
    first_t = subs2[0][1 + ARC_SEGMENTS]
    assert first_t[1] > Decimal("-1")

    # Same-family smooth still reflects: S after C mirrors the cubic c2.
    subs3, _ = _path_points("M0 0 C0 10 10 10 20 0 S20 -10 40 0 z")
    mirrored = [p for p in subs3[0] if p[1] < Decimal("-2")]
    assert mirrored != []


def test_dxf_malformed_coordinate_rejects_as_import_error():
    from catalogs.section_import import SectionImportError, parse_dxf
    import pytest

    rows = [
        "0", "SECTION", "2", "ENTITIES", "0", "LWPOLYLINE", "70", "1",
        "10", "NOT-A-NUMBER", "20", "5",
        "10", "10", "20", "0",
        "10", "10", "20", "10",
        "0", "ENDSEC", "0", "EOF",
    ]
    with pytest.raises(SectionImportError) as excinfo:
        parse_dxf(("\n".join(rows)).encode())
    assert excinfo.value.code == "section_dxf_invalid"
