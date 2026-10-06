"""Render DOC-01 commercial PDFs for synthetic snapshots — visual QA fixtures.

Usage: python backend/scripts/render_doc_fixtures.py [out_dir]
Writes <out_dir>/doc01-<case>.pdf + .html for inspection.

The same ``build_snapshot``/``build_context`` helpers back
``backend/tests/test_doc01_render.py`` — the density ladder (1/12/24/100
positions), USD totals, the bow plan cut and the approval QR all render
from this file so the tests and the visual captures see the same input.
"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from documents.renderers import _doc01, _CSS  # noqa: E402

_OPENINGS = {
    "TILT_TURN": "TILT_TURN_LEFT",
    "AWNING": "AWNING",
    "SLIDING_2L": "SLIDING_2L",
    "DOOR_ENTRY": "DOOR_ENTRY",
    "COMPOSITE": "FIXED",
    "FIXED": "FIXED",
}

_GLASS_PRODUCTS = {
    "DVC-4124": {
        "name": "Termopanel DVC 4-12-4 incoloro",
        "ug_w_m2k": "1.10",
        "g_value": "0.62",
        "light_transmission_pct": "80",
        "safety_class": None,
    },
    "LAM-33.1": {
        "name": "Laminado 3+3.1 incoloro PVB",
        "ug_w_m2k": "1.10",
        "g_value": "0.58",
        "light_transmission_pct": "76",
        "safety_class": "P2A",
    },
}


def _position(i, location, typology, w, h, qty, price, ci="WHITE", ce="WHITE",
              discount="0", system="Deceuninck Eforte 70", skus=("DVC-4124",),
              measurement=None, accessories=None, extras=None, tree=None,
              plan=None):
    position = {
        "position_index": str(i),
        "location_tag": location,
        "typology": typology,
        "width_mm": Decimal(w),
        "height_mm": Decimal(h),
        "quantity": Decimal(qty),
        # price_net is the sealed LINE total — unit price × quantity.
        "price_net": Decimal(price) * Decimal(qty),
        "discount_pct": Decimal(discount),
        "color_interior": ci,
        "color_exterior": ce,
        "system_name": system,
        "glass_products": {k: _GLASS_PRODUCTS[k] for k in skus},
    }
    if measurement is not None:
        position["measurement"] = measurement
    if accessories is not None:
        position["accessory_schedule"] = accessories
    if extras is not None:
        position["bom"] = {"extra_lines": extras}
    if plan is not None:
        position["plan"] = plan
    position["parametric_tree"] = tree if tree is not None else {
        "type": "ROOT",
        "color_interior": ci,
        "color_exterior": ce,
        "children": [
            {
                "type": "BAY",
                "opening_type": _OPENINGS.get(typology, "FIXED"),
                "glass_spec": "DVC 4-12-4",
                "glass_article_sku": skus[0],
                "children": [],
            }
        ],
    }
    return position


def _split_tree(ci, ce, sku, children, root_extra=None):
    tree = {
        "type": "ROOT",
        "color_interior": ci,
        "color_exterior": ce,
        "children": children,
    }
    if root_extra:
        tree.update(root_extra)
    for node in children:
        _assign_sku(node, sku)
    return tree


def _assign_sku(node, sku):
    if isinstance(node, dict):
        if node.get("type") == "BAY":
            node["glass_article_sku"] = sku
            node.setdefault("glass_spec", "DVC 4-12-4")
        for child in node.get("children") or []:
            _assign_sku(child, sku)


def _two_bay_tree(ci="WHITE", ce="WHITE", sku="DVC-4124"):
    """Hoja + fijo: SPLIT_V with an AWNING bay over a FIXED bay."""
    return _split_tree(ci, ce, sku, [
        {
            "type": "SPLIT_V",
            "split_offset_mm": "1200",
            "children": [
                {
                    "type": "BAY",
                    "opening_type": "TILT_TURN_LEFT",
                    "glass_spec": "DVC 4-12-4",
                    "children": [],
                },
                {
                    "type": "SPLIT_H",
                    "split_offset_mm": "900",
                    "children": [
                        {"type": "BAY", "opening_type": "AWNING",
                         "glass_spec": "DVC 4-12-4", "children": []},
                        {"type": "BAY", "opening_type": "FIXED",
                         "glass_spec": "DVC 4-12-4", "children": []},
                    ],
                },
            ],
        },
    ])


def _bow_tree():
    """product-v2 bow: three coupled modules at 15° (P06 plan cut)."""
    def module(index, opening="FIXED", sku="DVC-4124"):
        return {
            "id": f"m{index}",
            "width_mm": "700.00",
            "height_mm": "1400.00",
            "tree": {
                "id": "B1",
                "type": "BAY",
                "opening_type": opening,
                "glass_spec": "4-16-4 Float Incoloro",
                "glass_thickness_mm": "24.00",
                "glass_article_sku": sku,
            },
        }

    return {
        "version": "product-v2",
        "assembly": {
            "modules": [
                module(1),
                module(2, opening="TURN_LEFT", sku="LAM-33.1"),
                module(3),
            ],
            "couplings": [
                {"id": "c1", "angle_deg": "15",
                 "coupler_profile_sku": "COPLE-60"},
                {"id": "c2", "angle_deg": "15",
                 "coupler_profile_sku": "COPLE-60"},
            ],
        },
    }


def _bow_plan():
    """Sealed PlanGeometry shape (model_dump) for the bow fixture —
    three 700 mm fronts at 15°, backs ~160 mm behind the front chain."""
    return {
        "front_chain": [
            {"x_mm": "0", "y_mm": "0"},
            {"x_mm": "700.00", "y_mm": "0"},
            {"x_mm": "1376.30", "y_mm": "181.16"},
            {"x_mm": "2052.60", "y_mm": "362.32"},
        ],
        "modules": [
            {"module_id": "m1", "corners": [
                {"x_mm": "0", "y_mm": "0"},
                {"x_mm": "700.00", "y_mm": "0"},
                {"x_mm": "700.00", "y_mm": "-160.00"},
                {"x_mm": "0", "y_mm": "-160.00"},
            ]},
            {"module_id": "m2", "corners": [
                {"x_mm": "700.00", "y_mm": "0"},
                {"x_mm": "1376.30", "y_mm": "181.16"},
                {"x_mm": "1334.90", "y_mm": "26.59"},
                {"x_mm": "658.60", "y_mm": "-154.57"},
            ]},
            {"module_id": "m3", "corners": [
                {"x_mm": "1376.30", "y_mm": "181.16"},
                {"x_mm": "2052.60", "y_mm": "362.32"},
                {"x_mm": "1969.80", "y_mm": "53.18"},
                {"x_mm": "1293.50", "y_mm": "-127.98"},
            ]},
        ],
        "couplings": [
            {"coupling_id": "c1", "polygon": [
                {"x_mm": "700.00", "y_mm": "0"},
                {"x_mm": "658.60", "y_mm": "-154.57"},
                {"x_mm": "745.00", "y_mm": "-160.00"},
            ]},
            {"coupling_id": "c2", "polygon": [
                {"x_mm": "1376.30", "y_mm": "181.16"},
                {"x_mm": "1293.50", "y_mm": "-127.98"},
                {"x_mm": "1418.00", "y_mm": "-118.00"},
            ]},
        ],
        "min_x_mm": "0",
        "min_y_mm": "-154.57",
        "width_mm": "2052.60",
        "height_mm": "516.89",
    }


def _snapshot(project_overrides, positions, revision="A", org_overrides=None,
              services=None):
    project = {
        "code": "PTY-1042",
        "name": "Casa Altos del Sur",
        "client_name": "Constructora Altos del Sur SpA",
        "client_rut": "76.543.210-8",
        "client_giro": "Construcción de edificios residenciales",
        "client_comuna": "Puerto Varas",
        "client_address": "Camino Ensenada km 12, sitio 4",
        "client_email": "compras@altosdelsur.cl",
        "client_phone": "+56 65 2234 900",
        "delivery_address": "Camino Ensenada km 12, sitio 4, Puerto Varas",
        "currency": "CLP",
        "payment_terms": "Anticipo 40% al aprobar, saldo contra entrega",
        "quotation_valid_until": "2026-10-15",
        "notes_commercial": "Incluye instalación y sellado. No incluye terminaciones interiores.",
    }
    positions_net = sum(
        Decimal(p["price_net"])
        * (Decimal("1") - (
            Decimal(str(p["discount_pct"])) / 100
            if Decimal(str(p["discount_pct"])) > 1
            else Decimal(str(p["discount_pct"]))
        ))
        for p in positions
    )
    extras_net = Decimal("0")
    for position in positions:
        bom = position.get("bom") or {}
        for line in bom.get("extra_lines") or []:
            extras_net += _num_line_total(line)
    service_lines = services or []
    services_net = sum(
        (Decimal(str(s.get("total") or s.get("amount") or "0"))
         for s in service_lines),
        Decimal("0"),
    )
    # Engine semantics: total_price_net is post-discount and already
    # includes extras/services — the document reconciles against it.
    project["total_price_net"] = positions_net + extras_net + services_net
    project.update(project_overrides)
    net = project["total_price_net"]
    project["total_price_tax"] = (net * Decimal("0.19")).quantize(Decimal("0.01"))
    project["total_price_gross"] = net + project["total_price_tax"]
    organization = {
        "name": "Ventanas Osorno SpA",
        "tax_id": "77.123.456-0",
        "commercial_name": "Ventanas Osorno",
        "giro": "Fabricación de ventanas",
        "brand_address": "Los Maquis 1800, Osorno",
        "brand_phone": "+56 64 2233 445",
        "brand_email": "contacto@ventanasosorno.cl",
    }
    organization.update(org_overrides or {})
    return {
        "project": project,
        "organization": organization,
        "positions": positions,
        "revision": revision,
        "sealed_at": "2026-09-25T01:00:00Z",
        "bom_hash": "9f2c4a7e1b38d56f2a4099c77e0b1d6f8a2345bb92cd10ef34a8b67d0e1f2a3b",
        "pricing": {
            "request": {
                "currency": project["currency"],
                "discount_pct": "0",
                "extras": [],
            },
            "result": {
                "line_detail": [
                    {
                        "position_index": p["position_index"],
                        "quantity": str(p["quantity"]),
                        "unit_price": str(
                            (Decimal(p["price_net"]) / Decimal(p["quantity"]))
                            .quantize(Decimal("0.0001"))
                        ),
                        "discount_pct": str(p.get("discount_pct") or "0"),
                    }
                    for p in positions
                ],
                "service_lines": service_lines,
                "extras_net": str(extras_net),
            },
        },
    }


def _num_line_total(line):
    if not isinstance(line, dict):
        return Decimal("0")
    total = line.get("total") or line.get("total_net")
    if total is not None:
        return Decimal(str(total))
    qty = Decimal(str(line.get("quantity") or "1"))
    unit = Decimal(str(line.get("unit_price") or "0"))
    return qty * unit


CASES = {
    "residential": _snapshot(
        {},
        [
            _position(1, "Living", "TILT_TURN", 2400, 1800, 1, 685000,
                      measurement={"width_mm": "2430", "height_mm": "1830",
                                   "mounting_kind": "INTERIOR"},
                      accessories=["Tapa gotas exterior", "Cornisa interior"],
                      extras=[{"label": "Cuadrante interior 18×18",
                               "quantity": "4.8", "unit_price": "3200",
                               "total": "15360"}]),
            _position(2, "Dormitorio 1", "FIXED", 1200, 1400, 1, 198000),
            _position(3, "Dormitorio 2", "TILT_TURN", 1400, 1400, 2, 268000,
                      discount="10"),
            _position(4, "Baño", "AWNING", 600, 900, 1, 98000, "FOILED",
                      "FOILED"),
            _position(5, "Cocina — mesón", "COMPOSITE", 2400, 1200, 1, 455000,
                      tree=_two_bay_tree(), skus=("DVC-4124", "LAM-33.1")),
        ],
    ),
    "single": _snapshot(
        {"code": "PTY-1100", "name": "Ampliación casa patronal"},
        [
            _position(1, "Acceso principal", "DOOR_ENTRY", 1000, 2200, 1,
                      890000, skus=("LAM-33.1",),
                      measurement={"width_mm": "1030", "height_mm": "2230",
                                   "mounting_kind": "INTERIOR"}),
        ],
    ),
    "dozen": _snapshot(
        {"code": "PTY-1120", "name": "Condominio Los Alerces — etapa 1"},
        [
            _position(i, f"Casa {i}", "TILT_TURN" if i % 3 else "FIXED",
                      1200 + 200 * (i % 4), 1400 + 200 * (i % 2), 1,
                      220000 + i * 12000)
            for i in range(1, 13)
        ],
    ),
    "twentyfour": _snapshot(
        {"code": "PTY-1201", "name": "Edificio Mirador — torre A"},
        [
            _position(f"{i:02d}", f"Depto {i}", "SLIDING_2L" if i % 2 else "TILT_TURN",
                      1500 + 100 * (i % 5), 1500, 1, 310000 + i * 9000)
            for i in range(1, 25)
        ],
    ),
    "hundred": _snapshot(
        {"code": "EDF-3301", "name": "Edificio Costanera — torres A y B"},
        [
            _position(f"{t}.{u}.{i}", f"Torre {t} Dpto {u}", "SLIDING_2L",
                      1800 + 100 * (i % 4), 1500, 1,
                      385000 + i * 15000 + u * 1000)
            for t in "AB"
            for u in range(1, 26)
            for i in range(1, 3)
        ],
    ),
    "apartment-block": _snapshot(
        {"code": "EDF-2209"},
        [
            _position(f"{u}.{i}", f"Dpto {u}", "TILT_TURN", 1800, 1500, 1, 385000)
            for u in range(1, 21)
            for i in range(1, 3)
        ]
        + [
            _position(f"{u}.3", f"Dpto {u}", "SLIDING_2L", 2400, 1500, 1, 512000)
            for u in range(1, 21)
        ],
    ),
    "usd": _snapshot(
        {
            "code": "PTY-1055",
            "currency": "USD",
            "client_name": "Patagonia Lodge Ltd.",
            "payment_terms": "50% wire on approval, balance on delivery",
            "quotation_valid_until": "2026-10-31",
        },
        [
            _position(1, "Reception", "TILT_TURN", 2400, 1800, 2, 3580,
                      discount="10"),
            _position(2, "Deck room", "SLIDING_2L", 3000, 2100, 1, 7160),
        ],
        services=[{"label": "Instalación especial en altura",
                   "quantity": "1", "unit_price": "450", "total": "450"}],
    ),
    "bow": _snapshot(
        {"code": "PTY-1300", "name": "Casa Lago Rupanco"},
        [
            _position(1, "Comedor — paño curvo", "COMPOSITE", 2100, 1400, 1,
                      1240000, tree=_bow_tree(), plan=_bow_plan(),
                      skus=("DVC-4124", "LAM-33.1"),
                      measurement={"width_mm": "2160", "height_mm": "1430",
                                   "mounting_kind": "EXTERIOR"}),
            _position(2, "Cocina", "TILT_TURN", 1200, 1200, 1, 245000),
        ],
    ),
    "terms": _snapshot(
        {},
        [
            _position(1, "Living", "TILT_TURN", 2400, 1800, 1, 685000),
            _position(2, "Dormitorio", "FIXED", 1200, 1400, 1, 198000),
        ],
        org_overrides={
            "doc_paper_size": "A4",
            "doc_terms": {
                "plazo_entrega": "30 días hábiles desde aprobación y anticipo",
                "instalacion": "Cuadrilla propia; faena de 2 días en obra",
                "exclusiones": "No incluye cortinas, cierres de albañilería "
                               "ni terminaciones interiores",
                "garantia": "10 años perfiles, 5 años herrajes y termopanel",
                "jurisdiccion": "Tribunales de Osorno",
            },
        },
    ),
    "long-names": _snapshot(
        {
            "client_name": (
                "Asociación de Condominios Residenciales del Parque "
                "Forestal Poniente Sector B Etapa Tres Comité de "
                "Administración Legal"
            ),
            "client_address": (
                "Avenida de los Conquistadores y Libertadores "
                "del Sur Poniente Número Dieciocho Mil Quinientos Treinta y Cuatro, "
                "oficina 1001-B, sector residencial norte"
            ),
            "delivery_address": (
                "Bodega número siete del complejo habitacional, "
                "acceso por calle interior, portón secundario con reja, "
                "Puerto Varas, Región de Los Lagos"
            ),
            "payment_terms": (
                "Anticipo del treinta por ciento en cheque a fecha "
                "contra recepción conforme del proyecto aprobado por el comité de "
                "administración, saldo en dos cuotas iguales a treinta y sesenta días "
                "contra entrega efectiva del material en obra, sujeto a inspección"
            ),
            "notes_commercial": (
                "Valores incluyen instalación con equipo propio, "
                "sellado perimetral con poliuretano de baja expansión, remates "
                "metálicos exteriores color blanco, retiro de escombros a punto "
                "de acopio municipal. No incluye cortinas, decapé de paredes "
                "interiores, ni reparación de revoques existentes."
            ),
        },
        [
            _position(
                i,
                f"Unidad residencial tipo A piso {i} dormitorio principal oriente",
                "TILT_TURN" if i % 2 else "COMPOSITE",
                2400,
                1800,
                1,
                685000 + i * 7000,
            )
            for i in range(1, 9)
        ],
    ),
}

CONTEXTS = {
    # The acceptance block shows the QR when the sealed document was
    # re-rendered for a live approval link (portal share_quote).
    "terms": {"approval_url": "https://app.dekopen.cl/cotizacion/muestra-dev"},
}


def build_snapshot(name):
    """Fixture snapshot by case name — shared with the pytest render tests."""
    return CASES[name]


def build_context(name):
    return CONTEXTS.get(name)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/docqa")
    out.mkdir(parents=True, exist_ok=True)
    from weasyprint import HTML

    for name, snapshot in CASES.items():
        body = _doc01(snapshot, render_context=build_context(name))
        html = (
            '<!doctype html><html lang="es-CL"><head><meta charset="utf-8">'
            f"<style>{_CSS}</style></head><body>{body}</body></html>"
        )
        (out / f"doc01-{name}.html").write_text(html, encoding="utf-8")
        pdf = HTML(string=html).write_pdf(pdf_identifier=f"doc01-{name}-qa")
        (out / f"doc01-{name}.pdf").write_bytes(pdf)
        print(f"{name}: {len(pdf):,} bytes → {out}/doc01-{name}.pdf")


if __name__ == "__main__":
    main()
