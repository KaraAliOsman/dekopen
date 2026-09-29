"""Render DOC-01 commercial PDFs for synthetic snapshots — visual QA fixtures.

Usage: python backend/scripts/render_doc_fixtures.py [out_dir]
Writes <out_dir>/doc01-<case>.pdf + .html for inspection.
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


def _position(i, location, typology, w, h, qty, price, ci="WHITE", ce="WHITE",
              discount="0"):
    return {
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
        "parametric_tree": {
            "type": "ROOT",
            "color_interior": ci,
            "color_exterior": ce,
            "children": [
                {
                    "type": "BAY",
                    "opening_type": {
                        "TILT_TURN": "TILT_TURN_LEFT",
                        "AWNING": "AWNING",
                        "SLIDING_2L": "SLIDING_2L",
                        "DOOR_ENTRY": "DOOR_ENTRY",
                    }.get(typology, "FIXED"),
                    "glass_spec": "DVC 4-12-4",
                    "children": [],
                }
            ],
        },
    }


def _snapshot(project_overrides, positions, revision="A"):
    project = {
        "code": "PTY-1042",
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
        "total_price_net": sum(Decimal(p["price_net"]) for p in positions),
    }
    project.update(project_overrides)
    net = project["total_price_net"]
    project["total_price_tax"] = net * Decimal("0.19")
    project["total_price_gross"] = net + project["total_price_tax"]
    return {
        "project": project,
        "organization": {
            "name": "Ventanas Osorno SpA",
            "tax_id": "77.123.456-0",
            "commercial_name": "Ventanas Osorno",
            "giro": "Fabricación de ventanas",
            "brand_address": "Los Maquis 1800, Osorno",
            "brand_phone": "+56 64 2233 445",
            "brand_email": "contacto@ventanasosorno.cl",
        },
        "positions": positions,
        "revision": revision,
        "sealed_at": "2026-09-25T01:00:00Z",
        "bom_hash": "9f2c4a7e1b38d56f2a4099c77e0b1d6f8a2345bb92cd10ef34a8b67d0e1f2a3b",
    }


CASES = {
    "residential": _snapshot(
        {},
        [
            _position(1, "Living", "TILT_TURN", 2400, 1800, 1, 685000),
            _position(2, "Dormitorio 1", "FIXED", 1200, 1400, 1, 198000),
            _position(3, "Dormitorio 2", "TILT_TURN", 1400, 1400, 2, 268000,
                      discount="10"),
            _position(4, "Baño", "AWNING", 600, 900, 1, 98000, "FOILED", "FOILED"),
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


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/docqa")
    out.mkdir(parents=True, exist_ok=True)
    from weasyprint import HTML

    for name, snapshot in CASES.items():
        body = _doc01(snapshot)
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
