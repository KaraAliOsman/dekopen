"""Mundo fixture del diagnóstico IA1 — copia fiel del fixture de desarrollo
(`scripts/dev_fixture.py`, org "Ventanas del Sur SpA") y del catálogo demo de
`supabase/seed.sql`, en forma de proyecciones de contexto ya resueltas.

Los contextos imitan byte a byte lo que `context.build_context` devolvería
sobre Postgres para que el modelo vea exactamente los mismos datos que en la
app real; las posiciones conservan el `parametric_tree` como lo persiste el
editor (árbol de intención desnudo en posiciones de un solo módulo — la forma
real en la base).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

# ---------------------------------------------------------------------------
# Identidad del fixture
# ---------------------------------------------------------------------------

ORG_ID = uuid5(NAMESPACE_URL, "https://dekopen.local/evals/org")
USER_ID = uuid5(NAMESPACE_URL, "https://dekopen.local/evals/user")
ORG_NAME = "Ventanas del Sur SpA"

PROJECT_ID = uuid5(NAMESPACE_URL, "https://dekopen.local/evals/project/vivienda")
EDITOR_POSITION_ID = uuid5(NAMESPACE_URL, "https://dekopen.local/evals/pos/editor")

# El sistema practicable del fixture: DEMO_60 (misma uuid que seed.sql).
DEMO_60_ID = UUID("3067da09-3119-5ad0-a1d5-498cd2dfd753")
DEMO_60_CODE = "DEMO_60"
DEMO_60_NAME = "Demo 60 — practicable PVC"


def _id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://dekopen.local/evals/{key}"))


# ---------------------------------------------------------------------------
# Catálogo DEMO_60 — lo que `design_assist._catalog` devuelve sobre seed.sql:
# un solo SKU de vidrio (VIDRIO-BASE, receta '4 Float Incoloro'), el panel
# sándwich de 24 mm y la matriz de junquillos {4,5,6,20,24}.
# ---------------------------------------------------------------------------

CATALOGS: dict[str, dict] = {
    str(DEMO_60_ID): {
        "glass_skus": {"VIDRIO-BASE"},
        "glass_recipes": {"VIDRIO-BASE": "4 Float Incoloro"},
        "panel_skus": {"PANEL-SANDWICH-DEMO-24"},
        "thicknesses": {4, 5, 6, 20, 24},
    }
}


def catalog_for(system_id: Any) -> dict | None:
    return CATALOGS.get(str(system_id))


# ---------------------------------------------------------------------------
# Árboles de intención y productos — idénticos a scripts/dev_fixture.py
# (glass_spec '4-16-4 Float Incoloro', espesor 24.00, VIDRIO-BASE).
# ---------------------------------------------------------------------------


def bay(opening: str, *, bay_id: str = "m1") -> dict:
    node: dict[str, Any] = {
        "id": bay_id,
        "type": "BAY",
        "opening_type": opening,
        "glass_thickness_mm": "24.00",
        "glass_spec": "4-16-4 Float Incoloro",
        "glass_article_sku": "VIDRIO-BASE",
    }
    if opening == "SLIDING_2L":
        node["sliding_layout"] = {
            "preset": "SLIDING_2L",
            "primary_index": 0,
            "overlap_mm": "60",
        }
    return node


def split_v(left: dict, right: dict, offset_mm: str, *, split_id: str = "s1") -> dict:
    return {
        "id": split_id,
        "type": "SPLIT_V",
        "split_offset_mm": offset_mm,
        "mullion_profile_sku": "POSTE-V-60",
        "children": [left, right],
    }


def product(modules: list[dict], couplings: list[dict] | None = None) -> dict:
    """ProductJson product-v2, la forma que el canvas tiene abierta."""
    return {
        "version": "product-v2",
        "assembly": {"modules": modules, "couplings": couplings or []},
    }


def module(tree: dict, width_mm: str, height_mm: str, *, module_id: str = "m1") -> dict:
    return {"id": module_id, "width_mm": width_mm, "height_mm": height_mm, "tree": tree}


def wire_product(product_json: dict) -> dict:
    """La forma plana {modules, couplings} que `designAssistProduct` envía —
    `design_assist._summary` la consume tal cual."""
    assembly = product_json["assembly"]
    modules = []
    for item in assembly["modules"]:
        entry = {
            "id": item["id"],
            "width_mm": item["width_mm"],
            "height_mm": item["height_mm"],
            "tree": item["tree"],
        }
        for extra in ("contour", "frameless"):
            if extra in item:
                entry[extra] = item[extra]
        modules.append(entry)
    couplings = []
    for item in assembly["couplings"]:
        entry = {"id": item["id"], "angle_deg": item["angle_deg"]}
        for extra in ("kind", "modules", "edges"):
            if item.get(extra) is not None:
                entry[extra] = item[extra]
        couplings.append(entry)
    return {"modules": modules, "couplings": couplings}


# Variantes de producto del editor (posición 1500 × 1200 de DEMO_60).


def product_editor_vacia() -> dict:
    """Posición vacía: un módulo, una bahía FIXED."""
    return product([module(bay("FIXED"), "1500.00", "1200.00")])


def product_editor_dividida() -> dict:
    """Como quedaría E02: montante al medio, fija | oscilobatiente izq."""
    tree = split_v(bay("FIXED", bay_id="b1"), bay("TILT_TURN_LEFT", bay_id="b2"), "750.00")
    return product([module(tree, "1500.00", "1200.00")])


def product_editor_oscilobatiente() -> dict:
    return product([module(bay("TILT_TURN_LEFT"), "1500.00", "1200.00")])


PRODUCT_VARIANTS = {
    "vacia": product_editor_vacia,
    "dividida": product_editor_dividida,
    "oscilobatiente": product_editor_oscilobatiente,
}


# ---------------------------------------------------------------------------
# Contexto `position` — espejo de context._position sobre una posición de un
# solo módulo del editor.
# ---------------------------------------------------------------------------


def _module_intent(tree: dict) -> dict:
    openings: list[str] = []
    glass_skus: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "BAY":
            opening = node.get("opening_type")
            sku = node.get("glass_article_sku")
            if isinstance(opening, str) and opening not in openings:
                openings.append(opening)
            if isinstance(sku, str) and sku and sku not in glass_skus:
                glass_skus.append(sku)
        for child in node.get("children") or []:
            walk(child)

    walk(tree)
    return {"openings": openings, "glass_skus": glass_skus}


def position_context(
    *,
    product_json: dict,
    width_mm: str = "1500.00",
    height_mm: str = "1200.00",
    location: str = "Editor — evaluación",
    typology: str = "FIXED",
) -> dict:
    modules = []
    for item in product_json["assembly"]["modules"]:
        modules.append(
            {
                "id": item["id"],
                "width_mm": item["width_mm"],
                "height_mm": item["height_mm"],
                **_module_intent(item["tree"]),
                **({"single": True} if len(product_json["assembly"]["modules"]) == 1 else {}),
            }
        )
    return {
        "id": str(EDITOR_POSITION_ID),
        "project": {"id": str(PROJECT_ID), "code": "CASA_LOMAS", "name": "Vivienda Lomas"},
        "index": 1,
        "location": location,
        "typology": typology,
        "system": {"code": DEMO_60_CODE, "name": DEMO_60_NAME, "material": "PVC"},
        "width_mm": width_mm,
        "height_mm": height_mm,
        "modules": modules,
        "couplings": len(product_json["assembly"]["couplings"]),
        "selected": None,
    }


def editor_position_row() -> dict:
    """Lo que `projects_service.position_row` devuelve para la posición."""
    return {
        "id": str(EDITOR_POSITION_ID),
        "project_id": str(PROJECT_ID),
        "system_id": str(DEMO_60_ID),
        "position_index": 1,
        "location_tag": "Editor — evaluación",
        "typology": "FIXED",
        "width_mm": "1500.00",
        "height_mm": "1200.00",
        "parametric_tree": {"type": "BAY", "opening_type": "FIXED"},
    }


# ---------------------------------------------------------------------------
# Proyecto de 12 posiciones — espejo del VIVIENDA de scripts/dev_fixture.py
# (CASA_LOMAS, DRAFT, sin revisión emitida → editable).
# ---------------------------------------------------------------------------

# (location, width, height, typology, árbol de intención desnudo)
_POSITIONS_SPEC: list[tuple[str, str, str, str, dict]] = [
    (
        "Dormitorio principal",
        "1600.00",
        "1200.00",
        "COMPOSITE",
        split_v(bay("FIXED", bay_id="b1"), bay("TILT_TURN_RIGHT", bay_id="b2"), "800.00"),
    ),
    ("Baño", "600.00", "800.00", "FIXED", bay("FIXED")),
    (
        "Living",
        "2400.00",
        "1500.00",
        "COMPOSITE",
        split_v(bay("TILT_TURN_LEFT", bay_id="b1"), bay("FIXED", bay_id="b2"), "1600.00"),
    ),
    ("Cocina", "1200.00", "900.00", "FIXED", bay("FIXED")),
    ("Logia", "900.00", "900.00", "TURN", bay("TURN_LEFT")),
    ("Estar segundo piso", "1800.00", "1200.00", "SLIDING_2L", bay("SLIDING_2L")),
    ("Dormitorio norte", "1400.00", "1100.00", "TILT_TURN", bay("TILT_TURN_LEFT")),
    ("Pasillo", "700.00", "1400.00", "FIXED", bay("FIXED")),
    ("Acceso terraza", "900.00", "2100.00", "TURN", bay("TURN_RIGHT")),
    ("Bow comedor modulo 1", "900.00", "1300.00", "FIXED", bay("FIXED")),
    ("Bow comedor modulo 2", "900.00", "1300.00", "FIXED", bay("FIXED")),
    (
        "Conjunto acoplado escritorio",
        "2200.00",
        "1300.00",
        "COMPOSITE",
        split_v(bay("FIXED", bay_id="b1"), bay("TILT_TURN_RIGHT", bay_id="b2"), "1400.00"),
    ),
]


def project_positions_rows() -> list[dict]:
    """Filas de `project_positions` tal como `_batch_positions` las lee."""
    rows = []
    for index, (location, width, height, typology, tree) in enumerate(_POSITIONS_SPEC, 1):
        rows.append(
            {
                "id": _id(f"pos/{index}"),
                "position_index": index,
                "location_tag": location,
                "typology": typology,
                "width_mm": width,
                "height_mm": height,
                "system_id": str(DEMO_60_ID),
                "parametric_tree": tree,
            }
        )
    return rows


def project_context() -> dict:
    """Espejo de context._project: DRAFT sin revisión sellada → editable."""
    return {
        "id": str(PROJECT_ID),
        "code": "CASA_LOMAS",
        "name": "Vivienda Lomas",
        "client": "María Paz Rojas",
        "status": "DRAFT",
        "current_revision": None,
        "totals": {"net": None, "tax": None, "gross": None},
        "payments": {"collected": "0.00", "pending": None, "items": []},
        "positions": [
            {
                "id": row["id"],
                "index": row["position_index"],
                "location": row["location_tag"],
                "typology": row["typology"],
                "width_mm": row["width_mm"],
                "height_mm": row["height_mm"],
            }
            for row in project_positions_rows()
        ],
        "editable": True,
    }


def project_context_cotizado() -> dict:
    """Variante con REV-A emitida sin sellar (para comparar versiones): sigue
    editable por ser DRAFT con revisión corriente distinta de la última."""
    context = project_context()
    context["current_revision"] = "REV-A"
    context["latest_version"] = {
        "revision": "REV-B",
        "documentary_complete": True,
        "production_allowed": False,
    }
    context["totals"] = {"net": "4350000.00", "tax": "826500.00", "gross": "5176500.00"}
    context["payments"] = {"collected": "0.00", "pending": "5176500.00", "items": []}
    return context


# ---------------------------------------------------------------------------
# Producción y compras — espejos de context._production, _work_order,
# _purchase_plan y _dashboard.
# ---------------------------------------------------------------------------

WORK_ORDER_BLOCKED_ID = _id("wo/m09")
WORK_ORDER_OK_ID = _id("wo/m12")


def production_context() -> dict:
    """La vista Producción: dos OT, una con estación pendiente (bloqueada)."""
    return {
        "work_orders": [
            {
                "id": WORK_ORDER_BLOCKED_ID,
                "code": "OT-0009",
                "status": "IN_PRODUCTION",
                "steps_done": 2,
                "steps_total": 6,
            },
            {
                "id": WORK_ORDER_OK_ID,
                "code": "OT-0012",
                "status": "IN_PRODUCTION",
                "steps_done": 5,
                "steps_total": 5,
            },
        ],
        "truncated": False,
    }


def work_order_context() -> dict:
    """Detalle de la OT bloqueada: estación de corte pendiente por material
    faltante (shortages=1) — la causa real de "por qué está bloqueada"."""
    return {
        "id": WORK_ORDER_BLOCKED_ID,
        "order_code": "OT-0009",
        "status": "IN_PRODUCTION",
        "shortages": 1,
        "steps": [
            {"sequence": 1, "code": "PREP", "label": "Preparación", "status": "DONE"},
            {"sequence": 2, "code": "CORTE", "label": "Corte de perfiles", "status": "IN_PROGRESS"},
            {"sequence": 3, "code": "ARMADO", "label": "Armado", "status": "PENDING"},
            {
                "sequence": 4,
                "code": "VIDRIO",
                "label": "Instalación de vidrio",
                "status": "PENDING",
            },
            {"sequence": 5, "code": "QC", "label": "Control de calidad", "status": "PENDING"},
            {"sequence": 6, "code": "DESPACHO", "label": "Despacho", "status": "PENDING"},
        ],
        "cnc": {"issues": [], "members": [], "programs": []},
    }


def work_order_ok_context() -> dict:
    """OT sin escasez, todas las estaciones cerradas salvo despacho."""
    return {
        "id": WORK_ORDER_OK_ID,
        "order_code": "OT-0012",
        "status": "IN_PRODUCTION",
        "shortages": 0,
        "steps": [
            {"sequence": 1, "code": "PREP", "label": "Preparación", "status": "DONE"},
            {"sequence": 2, "code": "CORTE", "label": "Corte de perfiles", "status": "DONE"},
            {"sequence": 3, "code": "ARMADO", "label": "Armado", "status": "DONE"},
            {"sequence": 4, "code": "VIDRIO", "label": "Instalación de vidrio", "status": "DONE"},
            {"sequence": 5, "code": "QC", "label": "Control de calidad", "status": "DONE"},
        ],
        "cnc": {"issues": [], "members": [], "programs": []},
    }


def purchase_plan_context() -> dict:
    """Compras: dos líneas sin cobertura en la última versión del proyecto,
    con proveedores elegibles reales — lo que un plan de compra cita."""
    line_a = _id("prl/perfiles")
    line_b = _id("prl/vidrio")
    return {
        "uncovered_lines": [
            {
                "id": line_a,
                "requirement_key": "perfiles/marco",
                "order_type": "SUPPLIER_PROFILES",
                "category": "Perfiles PVC",
                "sku": "MARCO-60",
                "unit": "barra",
                "quantity": "42.000",
                "project_id": str(PROJECT_ID),
                "version_id": _id("ver/rev-b"),
                "project_code": "CASA_LOMAS",
            },
            {
                "id": line_b,
                "requirement_key": "vidrio/dvh",
                "order_type": "SUPPLIER_GLASS",
                "category": "Vidrios",
                "sku": "VIDRIO-BASE",
                "unit": "unidad",
                "quantity": "18.000",
                "project_id": str(PROJECT_ID),
                "version_id": _id("ver/rev-b"),
                "project_code": "CASA_LOMAS",
            },
        ],
        "uncovered_total": 2,
        "truncated": False,
        "coverage_verified": True,
        "suppliers": [
            {"order_type": "SUPPLIER_PROFILES", "supplier": "Perfilados Andina Ltda."},
            {"order_type": "SUPPLIER_GLASS", "supplier": "Cristales del Sur S.A."},
        ],
        "open_purchase_orders": [],
    }


def dashboard_context() -> dict:
    return {
        "counts": {
            "projects": 6,
            "positions": 42,
            "work_orders_open": 2,
            "clients": 4,
            "profile_systems": 3,
        },
        "recent_projects": [
            {
                "id": str(PROJECT_ID),
                "code": "CASA_LOMAS",
                "name": "Vivienda Lomas",
                "client": "María Paz Rojas",
                "status": "DRAFT",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Resolución `fixture:` → `given` de cada caso
# ---------------------------------------------------------------------------


def _wrap(surface: str, context: dict) -> dict:
    """build_context agrega surface/organization/context_version — el fixture
    las lleva igual para que el grounding cuente la organización real."""
    return {
        **context,
        "surface": surface,
        "organization": {"id": str(ORG_ID), "name": ORG_NAME},
        "context_version": 1,
    }


def given(fixture: str, *, product_variant: str = "vacia") -> dict:
    """El `given` completo del caso: contextos por superficie, producto del
    canvas, fila de posición, catálogos y filas de posiciones del lote."""
    if fixture == "editor":
        product_json = PRODUCT_VARIANTS[product_variant]()
        context = position_context(product_json=product_json)
        return {
            "contexts": {"position": [{"refs": {}, "context": _wrap("position", context)}]},
            "product": product_json,
            "position": editor_position_row(),
            "catalogs": CATALOGS,
            "positions": [],
        }
    if fixture == "proyecto":
        return {
            "contexts": {
                "project": [{"refs": {}, "context": _wrap("project", project_context())}],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": project_positions_rows(),
        }
    if fixture == "proyecto_cotizado":
        return {
            "contexts": {
                "project": [{"refs": {}, "context": _wrap("project", project_context_cotizado())}],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": project_positions_rows(),
        }
    if fixture == "produccion":
        return {
            "contexts": {
                "production": [{"refs": {}, "context": _wrap("production", production_context())}],
                "work_order": [
                    {
                        "refs": {"work_order_id": WORK_ORDER_BLOCKED_ID},
                        "context": _wrap("work_order", work_order_context()),
                    },
                    {
                        "refs": {"work_order_id": WORK_ORDER_OK_ID},
                        "context": _wrap("work_order", work_order_ok_context()),
                    },
                ],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": [],
        }
    if fixture == "work_order":
        return {
            "contexts": {
                "work_order": [
                    {
                        "refs": {"work_order_id": WORK_ORDER_BLOCKED_ID},
                        "context": _wrap("work_order", work_order_context()),
                    }
                ],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": [],
        }
    if fixture == "compras":
        return {
            "contexts": {
                "purchase_plan": [
                    {"refs": {}, "context": _wrap("purchase_plan", purchase_plan_context())}
                ],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": [],
        }
    if fixture == "dashboard":
        return {
            "contexts": {
                "dashboard": [{"refs": {}, "context": _wrap("dashboard", dashboard_context())}],
                "project": [{"refs": {}, "context": _wrap("project", project_context())}],
            },
            "product": None,
            "position": None,
            "catalogs": CATALOGS,
            "positions": project_positions_rows(),
        }
    raise KeyError(f"fixture desconocido: {fixture}")
