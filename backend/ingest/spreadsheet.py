"""Structured XLSX/CSV catalog ingestion — the manual path (D01).

Two entry points:

- ``build_template`` returns the official ``plantilla-catalogo.xlsx`` — a
  workbook whose nine sheets mirror the catalog authority tables. Anyone can
  fill it with Excel/LibreOffice; nothing needs the AI provider.
- ``parse_catalog_spreadsheet`` reads an upload that follows the template
  (sheet names or header rows are the contract) and emits the same typed
  candidate dicts the AI compile path produces: ``entity``, ``key``,
  ``confidence``, ``evidence`` (per-field original/normalized/source) and
  ``row_errors`` — Spanish, per row, one message per problem.

Rows that fail validation still appear in review flagged ERROR so the
reviewer sees exactly which row to fix — but the confirm path refuses them:
a broken row never becomes catalog authority. Clean structured rows carry
``VERIFIED_STRUCTURED`` — a declared-unit column is the only extraction that
can earn that confidence.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation
from typing import Any

PARSER_VERSION = "catalog-spreadsheet/1"

# Entities a manual import can declare — the review groups candidates by
# entity and confirm writes each to its own authority table.
ENTITY_PROFILE = "PROFILE"
ENTITY_SYSTEM = "SYSTEM"
ENTITY_CUT_RULE = "CUT_RULE"
ENTITY_REINFORCEMENT = "REINFORCEMENT_RULE"
ENTITY_LIMIT = "TYPOLOGY_LIMIT"
ENTITY_FINISH = "FINISH"
ENTITY_GLAZING = "GLAZING_RULE"
ENTITY_HARDWARE = "HARDWARE_KIT"
ENTITY_HARDWARE_FAMILY = "HARDWARE_FAMILY"
ENTITY_HANDLE_MODEL = "HANDLE_MODEL"
ENTITY_HANDLE_COLOR = "HANDLE_COLOR"
ENTITY_HARDWARE_OPTION = "HARDWARE_OPTION"
ENTITY_PRICE = "PRICE"
ENTITY_GLASS_PRODUCT = "GLASS_PRODUCT"
ENTITY_GLASS_SURCHARGE = "GLASS_SURCHARGE"
ENTITY_GLASS_SAFETY = "GLASS_SAFETY_RULE"
ENTITY_GLASS_LIMIT = "GLASS_TYPE_LIMIT"
ENTITY_EXTRA = "EXTRA_ARTICLE"
ENTITY_SERVICE = "SERVICE_ARTICLE"

ENTITIES = (
    ENTITY_PROFILE,
    ENTITY_SYSTEM,
    ENTITY_CUT_RULE,
    ENTITY_REINFORCEMENT,
    ENTITY_LIMIT,
    ENTITY_FINISH,
    ENTITY_GLAZING,
    ENTITY_HARDWARE,
    ENTITY_HARDWARE_FAMILY,
    ENTITY_HANDLE_MODEL,
    ENTITY_HANDLE_COLOR,
    ENTITY_HARDWARE_OPTION,
    ENTITY_PRICE,
    ENTITY_GLASS_PRODUCT,
    ENTITY_GLASS_SURCHARGE,
    ENTITY_GLASS_SAFETY,
    ENTITY_GLASS_LIMIT,
    ENTITY_EXTRA,
    ENTITY_SERVICE,
)

CONFIDENCE_VERIFIED_STRUCTURED = "VERIFIED_STRUCTURED"
CONFIDENCE_ERROR = "ERROR"

_PROFILE_ROLES = (
    "FRAME",
    "SASH",
    "SLIDING_SASH",
    "DOOR_SASH",
    "MULLION_V",
    "MULLION_H",
    "INTERLOCK",
    "RAIL",
    "INVERSOR",
    "GLAZING_BEAD",
    "COUPLER",
    "ADDITIONAL",
    "THRESHOLD",
    "FRAME_EXTENSION",
    "SILL",
    "COVER_TRIM",
    "SKIRT",
)
_MATERIALS = ("PVC", "ALUMINIUM")
_FAMILIES = ("CASEMENT", "SLIDING", "LIFT_SLIDE", "DOOR", "FACADE_FIXED")
_FINISH_CLASSES = ("ALL", "WHITE", "NON_WHITE")
_OPENING_TYPES = (
    "FIXED",
    "TURN_LEFT",
    "TURN_RIGHT",
    "TILT_TURN_LEFT",
    "TILT_TURN_RIGHT",
    "AWNING",
    "DOOR_ENTRY",
    "DOOR_DOUBLE",
    "SLIDING_2L",
    "SLIDING_3L",
    "SLIDING_4L",
    "SLIDING",
)
_RAIL_TYPES = ("mono", "dual")
_SAFETY_CLASSES = ("A", "B", "C")
_REQUIRED_SAFETY = (
    "TEMPERED",
    "LAMINATED",
    "SAFETY_GLASS",
    "SAFETY_CLASS_A",
    "SAFETY_CLASS_B",
    "SAFETY_CLASS_C",
)
_SEVERITIES = ("WARNING", "MANDATORY")
# Engine surcharge/units — kept in sync by contract (models.py Literal sets
# and glass_pricing rate units).
_SURCHARGE_KINDS = ("TEMPERED", "EDGE_POLISH", "DRILL", "PALILLAJE")
_SURCHARGE_UNITS = ("M2", "M", "EA", "CROSS")
# Engine _LAMINA_KIND_ALIASES — kept in sync by contract.
_LAMINA_KINDS = (
    "ANY",
    "FLOAT",
    "TINTED",
    "TEMPERED",
    "HEAT_STRENGTHENED",
    "LAMINATED",
    "LOW_E",
    "SOLAR_CONTROL",
    "REFLECTIVE",
    "MIRROR",
    "SATIN",
    "PRINTED",
)
# Kit classes/options are scoped to the normalized opening family (same
# grain as hardware_kits.opening_type / chk_kits_opening_type).
_OPENING_FAMILIES = ("TURN", "TILT_TURN", "SLIDING", "DOOR", "AWNING")
_HANDLE_HEIGHT_RULES = ("CENTERED", "FIXED_FROM_BASE", "RANGE")
_HANDLE_KINDS = ("STANDARD", "LOCKABLE", "BUTTON", "DOOR_ESCUTCHEON")
_OPTION_KINDS = (
    "SECURITY",
    "OPENING_LIMITER",
    "MICROVENTILATION",
    "CONCEALED_HINGES",
)
# Engine enum mirrors (D06): ExtraKind / ExtraPricingUnit / ServiceKind /
# ServiceQtyRule — same contract the catalog serializer validates.
_EXTRA_KINDS = (
    "SILL",
    "FRAME_EXTENSION",
    "COVER_TRIM",
    "MOSQUITO_SCREEN",
    "VENTILATOR",
)
_EXTRA_UNITS = ("M", "EA")
_EXTRA_UNIT_KINDS = ("WINDOW", "DOOR")
_SERVICE_KINDS = (
    "INSTALLATION",
    "SEALING",
    "REMOVAL",
    "SCAFFOLDING",
    "FREIGHT",
)
_SERVICE_QTY_RULES = (
    "PER_LINEAR_METER",
    "PER_M2",
    "PER_POSITION_UNIT",
    "FIXED",
)

# Column kind → how the cell is read. `enum` values are normalized
# (upper, accents kept) and validated; `bool` accepts si/no/true/false/1/0.
# Each entry: (header, field, kind, required, enum_or_None)
_SHEETS: dict[str, dict[str, Any]] = {
    "Sistemas": {
        "entity": ENTITY_SYSTEM,
        "columns": [
            ("codigo", "code", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("profundidad_mm", "depth_mm", "decimal", True, None),
            ("material", "material", "enum", True, _MATERIALS),
            ("familia", "system_family", "enum", True, _FAMILIES),
            ("deduccion_vidrio_ancho_mm", "sliding_glazing_deduction_width_mm", "decimal", True, None),
            ("deduccion_vidrio_alto_mm", "sliding_glazing_deduction_height_mm", "decimal", True, None),
            ("holgura_lateral_puerta_mm", "door_leaf_side_clearance_mm", "decimal", True, None),
            ("acabados", "finishes", "csv_list", False, None),
        ],
    },
    "Perfiles": {
        "entity": ENTITY_PROFILE,
        "columns": [
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("rol", "role", "enum", True, _PROFILE_ROLES),
            ("ancho_cara_mm", "face_width_mm", "decimal", True, None),
            ("largo_comercial_mm", "commercial_length_mm", "decimal", False, None),
            ("perdida_soldadura_mm", "welding_loss_mm", "decimal", False, None),
            ("peso_kg_m", "weight_kg_m", "decimal", False, None),
            ("peso_acero_kg_m", "steel_weight_kg_m", "decimal", False, None),
            ("refuerzo_sku", "reinforcement_sku", "text", False, None),
        ],
    },
    "Reglas de corte": {
        "entity": ENTITY_CUT_RULE,
        "columns": [
            ("rol", "role", "enum", True, _PROFILE_ROLES),
            ("angulo_corte_grados", "cut_angle_deg", "decimal", True, None),
            ("extremos_soldados", "welded_ends", "int0_2", False, None),
            ("deduccion_encuentro_mm", "interlock_deduction_mm", "decimal", False, None),
            ("redondeo_mm", "rounding_mm", "decimal", False, None),
            ("refuerzo_sku", "reinforcement_sku", "text", False, None),
        ],
    },
    "Refuerzos": {
        "entity": ENTITY_REINFORCEMENT,
        "columns": [
            ("rol", "role", "enum", True, _PROFILE_ROLES),
            ("clase_acabado", "finish_class", "enum", True, _FINISH_CLASSES),
            ("largo_minimo_mm", "min_length_mm", "decimal", False, None),
            ("obligatorio", "mandatory", "bool", True, None),
            ("refuerzo_sku", "reinforcement_sku", "text", False, None),
            ("deduccion_corte_mm", "cut_deduction_mm", "decimal", False, None),
            ("tornillos_por_m", "screws_per_m", "decimal", False, None),
            ("tornillo_sku", "screw_sku", "text", False, None),
        ],
    },
    "Límites": {
        "entity": ENTITY_LIMIT,
        "columns": [
            ("tipologia", "opening_type", "enum", True, _OPENING_TYPES),
            ("ancho_hoja_min_mm", "min_leaf_width_mm", "decimal", False, None),
            ("ancho_hoja_max_mm", "max_leaf_width_mm", "decimal", False, None),
            ("alto_hoja_min_mm", "min_leaf_height_mm", "decimal", False, None),
            ("alto_hoja_max_mm", "max_leaf_height_mm", "decimal", False, None),
            ("peso_hoja_max_kg", "max_leaf_weight_kg", "decimal", False, None),
            ("relacion_max", "max_aspect_ratio", "decimal", False, None),
        ],
    },
    "Colores-SKU": {
        "entity": ENTITY_FINISH,
        "columns": [
            ("codigo_acabado", "finish_code", "text", True, None),
            ("nombre", "name", "text", True, None),
        ],
    },
    "Vidrios": {
        "entity": ENTITY_GLAZING,
        "columns": [
            ("espesor_vidrio_mm", "glass_thickness_mm", "decimal", True, None),
            ("junquillo_sku", "bead_sku", "text", True, None),
            ("ancho_junquillo_mm", "bead_width_mm", "decimal", True, None),
            ("junta_interior_mm", "gasket_interior_mm", "decimal", False, None),
            ("junta_exterior_mm", "gasket_exterior_mm", "decimal", False, None),
        ],
    },
    "Herrajes": {
        "entity": ENTITY_HARDWARE,
        "columns": [
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("apertura", "opening_type", "enum", True, _OPENING_TYPES),
            ("ancho_min_mm", "min_leaf_width_mm", "decimal", True, None),
            ("ancho_max_mm", "max_leaf_width_mm", "decimal", True, None),
            ("alto_min_mm", "min_leaf_height_mm", "decimal", True, None),
            ("alto_max_mm", "max_leaf_height_mm", "decimal", True, None),
            ("peso_max_kg", "max_leaf_weight_kg", "decimal", True, None),
            ("tipo_riel", "rail_type", "enum", False, _RAIL_TYPES),
            ("carros", "carriages_qty", "int", False, None),
            ("brazos", "stay_arms_qty", "int", False, None),
            ("peso_kit_kg", "weight_kg", "decimal", False, None),
            ("contenido_json", "contents", "json", False, None),
            # D04: the class the kit plays inside its family plus the
            # declared restrictions beyond the size envelope.
            ("clase", "class_label", "text", False, None),
            ("relacion_ancho_alto_max", "max_aspect_ratio", "decimal", False, None),
            ("alto_minimo_compas_mm", "min_stay_height_mm", "decimal", False, None),
        ],
    },
    "Familias de herraje": {
        "entity": ENTITY_HARDWARE_FAMILY,
        "columns": [
            ("apertura", "opening_type", "enum", True, _OPENING_FAMILIES),
            ("regla_altura_manilla", "handle_height_rule", "enum", False, _HANDLE_HEIGHT_RULES),
            ("altura_manilla_min_mm", "handle_height_min_mm", "decimal", False, None),
            ("altura_manilla_max_mm", "handle_height_max_mm", "decimal", False, None),
            ("altura_manilla_defecto_mm", "handle_height_default_mm", "decimal", False, None),
        ],
    },
    "Manillas": {
        "entity": ENTITY_HANDLE_MODEL,
        "columns": [
            ("apertura", "opening_type", "enum", True, _OPENING_FAMILIES),
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("tipo_manilla", "kind", "enum", True, _HANDLE_KINDS),
            ("delta_precio_clp", "price_delta_clp", "decimal", False, None),
        ],
    },
    "Colores de manilla": {
        "entity": ENTITY_HANDLE_COLOR,
        "columns": [
            ("apertura", "opening_type", "enum", True, _OPENING_FAMILIES),
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("delta_precio_clp", "price_delta_clp", "decimal", False, None),
        ],
    },
    "Opciones de herraje": {
        "entity": ENTITY_HARDWARE_OPTION,
        "columns": [
            ("apertura", "opening_type", "enum", True, _OPENING_FAMILIES),
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("tipo_opcion", "kind", "enum", True, _OPTION_KINDS),
            ("delta_precio_clp", "price_delta_clp", "decimal", False, None),
            ("contenido_json", "components", "json", False, None),
        ],
    },
    "Precios": {
        "entity": ENTITY_PRICE,
        "columns": [
            ("sku_compra", "purchase_sku", "text", True, None),
            ("tipo", "item_type", "text", True, None),
            ("unidad", "unit", "text", True, None),
            ("precio", "unit_cost", "decimal", True, None),
            ("moneda", "currency", "text", False, None),
        ],
    },
    "Productos vidrio": {
        # D02: a declared supplier product — the structured composition is
        # parsed from `notacion` at confirm (unparseable imports keep a
        # UNKNOWN composition and review_pending; never invented layers).
        "entity": ENTITY_GLASS_PRODUCT,
        "columns": [
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("notacion", "notation", "text", True, None),
            ("clase_seguridad", "safety_class", "enum", False, _SAFETY_CLASSES),
            ("ug_w_m2k", "ug_w_m2k", "decimal", False, None),
            ("factor_solar_g", "g_value", "decimal", False, None),
            ("transmitancia_luz_pct", "light_transmission_pct", "decimal", False, None),
            ("peso_kg_m2", "weight_kg_m2", "decimal", False, None),
            ("area_minima_m2", "min_billable_area_m2", "decimal", False, None),
            ("nivel_precio", "price_tier", "int", False, None),
            ("proveedor", "supplier", "text", False, None),
        ],
    },
    "Recargos vidrio": {
        # D02: priced extras per product — the row resolves the product by
        # sku inside the same org+system scope the engine repository uses.
        "entity": ENTITY_GLASS_SURCHARGE,
        "columns": [
            ("sku_producto", "product_sku", "text", True, None),
            ("tipo", "kind", "enum", True, _SURCHARGE_KINDS),
            ("unidad", "unit", "enum", True, _SURCHARGE_UNITS),
            ("costo", "unit_cost", "decimal", True, None),
            ("moneda", "currency", "text", False, None),
            ("etiqueta", "label", "text", False, None),
        ],
    },
    "Extras": {
        # D06: position accessories — geometry-linked (vierteaguas,
        # ensanche, tapajunta) and counted (mosquitero, aireador). The
        # engine measures quantities; the sheet declares price/cost,
        # applicability predicates and the suggestion reason.
        "entity": ENTITY_EXTRA,
        "columns": [
            ("sku", "sku", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("tipo", "kind", "enum", True, _EXTRA_KINDS),
            ("unidad", "pricing_unit", "enum", True, _EXTRA_UNITS),
            ("precio", "unit_price", "decimal", False, None),
            ("moneda", "unit_price_currency", "text", False, None),
            ("costo", "unit_cost", "decimal", False, None),
            ("moneda_costo", "unit_cost_currency", "text", False, None),
            ("perfil_corte", "cut_profile_sku", "text", False, None),
            ("material_corte", "cut_material", "enum", False, _MATERIALS),
            ("vuelo_mm", "vuelo_default_mm", "decimal", False, None),
            ("familias", "families", "csv_list", False, None),
            ("tipos_unidad", "unit_kinds", "csv_list", False, None),
            ("motivo", "suggestion_reason", "text", False, None),
        ],
    },
    "Servicios": {
        # D06: project services (instalación, sellado, retiro, andamio,
        # flete) — org data, not bound to the importing system. The qty
        # rule fixes how pricing measures the charge off the positions.
        "entity": ENTITY_SERVICE,
        "columns": [
            ("codigo", "code", "text", True, None),
            ("nombre", "name", "text", True, None),
            ("tipo", "kind", "enum", True, _SERVICE_KINDS),
            ("regla", "qty_rule", "enum", True, _SERVICE_QTY_RULES),
            ("precio", "unit_price", "decimal", False, None),
            ("moneda", "unit_price_currency", "text", False, None),
            ("costo", "unit_cost", "decimal", False, None),
            ("moneda_costo", "unit_cost_currency", "text", False, None),
        ],
    },
    "Seguridad vidrio": {
        # D02 NCh-135-family rules as org-editable data — the official
        # wording never ships; fuente carries the cited reference.
        "entity": ENTITY_GLASS_SAFETY,
        "columns": [
            ("codigo", "code", "text", True, None),
            ("titulo", "title", "text", True, None),
            ("mensaje", "message", "text", False, None),
            ("aperturas", "applies_openings", "csv_list", False, None),
            ("antepecho_menor_mm", "sill_below_mm", "decimal", False, None),
            ("area_minima_m2", "min_area_m2", "decimal", False, None),
            ("requiere_puerta", "requires_door", "bool", False, None),
            ("requiere_puerta_adyacente", "requires_adjacent_door", "bool", False, None),
            ("seguridad_requerida", "required_safety", "enum", True, _REQUIRED_SAFETY),
            ("severidad", "severity", "enum", False, _SEVERITIES),
            ("fuente", "source_ref", "text", False, None),
        ],
    },
    "Límites vidrio": {
        "entity": ENTITY_GLASS_LIMIT,
        "columns": [
            ("codigo", "code", "text", True, None),
            ("tipo_lamina", "lamina_kind", "enum", True, _LAMINA_KINDS),
            ("espesor_min_mm", "thickness_min_mm", "decimal", False, None),
            ("espesor_max_mm", "thickness_max_mm", "decimal", False, None),
            ("lado_min_mm", "min_side_mm", "decimal", False, None),
            ("lado_max_mm", "max_side_mm", "decimal", False, None),
            ("area_min_m2", "min_area_m2", "decimal", False, None),
            ("area_max_m2", "max_area_m2", "decimal", False, None),
            ("relacion_max", "max_aspect_ratio", "decimal", False, None),
            ("corte_exacto", "requires_exact_cut", "bool", False, None),
            ("severidad", "severity", "enum", False, _SEVERITIES),
            ("fuente", "source_ref", "text", False, None),
        ],
    },
}

_LEEME = "LEEME"
SHEET_ORDER = [_LEEME, *_SHEETS.keys()]

_EXAMPLES: dict[str, list[list[str]]] = {
    "Sistemas": [["MI-SERIE-60", "Mi Serie 60mm PVC", "60", "PVC", "CASEMENT", "20", "20", "7", "WHITE,FOILED"]],
    "Perfiles": [["MARCO-60", "Marco 60", "FRAME", "58", "6000", "6", "1.90", "1.70", ""]],
    "Reglas de corte": [["FRAME", "45", "2", "0", "0.01", ""]],
    "Refuerzos": [["SASH", "NON_WHITE", "0", "si", "ACERO-35", "0", "4", "TORNILLO-4X16"]],
    "Límites": [["TURN_LEFT", "350", "1400", "400", "2400", "80", ""]],
    "Colores-SKU": [["WHITE", "Blanco"]],
    "Vidrios": [["24", "JQ-60-24", "24", "3", "3"]],
    "Herrajes": [
        [
            "KIT-TT-60", "Kit oscilobatiente 60", "TILT_TURN_RIGHT",
            "450", "1600", "500", "2400", "130", "dual", "0", "1", "3.40",
            '[{"sku":"MAN-60","name":"Manilla","qty":1,"unit":"unit","category":"HANDLE"}]',
            "estándar", "", "",
        ]
    ],
    "Familias de herraje": [["TILT_TURN", "RANGE", "900", "1300", "1000"]],
    "Manillas": [["TILT_TURN", "MAN-60-EST", "Manilla estándar", "STANDARD", "0"]],
    "Colores de manilla": [["TILT_TURN", "COL-BLANCO", "Blanco", "0"]],
    "Opciones de herraje": [
        [
            "TILT_TURN", "OPT-MICROVENT", "Microventilación",
            "MICROVENTILATION", "15000",
            '[{"sku":"MICROVENT","name":"Conjunto microventilación","qty":1,"unit":"unit","category":"FITTING"}]',
        ]
    ],
    "Precios": [["COMPRA-MARCO-60", "PROFILE", "BAR", "12500", "CLP"]],
    "Productos vidrio": [[
        "VID-LOWE-24", "Termopanel Low-E 4·16·4", "4 / 16 Ar / 4 Low-E (c3)",
        "B", "1.400", "0.630", "80", "20", "0.30", "4", "Vidriería Sur",
    ]],
    "Recargos vidrio": [[
        "VID-LOWE-24", "PALILLAJE", "CROSS", "1500", "CLP", "Palillaje interior",
    ]],
    "Extras": [[
        "EXT-VIERT-60", "Vierteaguas aluminio", "SILL", "M",
        "11000", "CLP", "5500", "CLP", "VIERT-ALU-60", "ALUMINIUM",
        "30", "", "", "Ventana con alféizar expuesto",
    ]],
    "Servicios": [[
        "INST-ML", "Instalación por metro lineal", "INSTALLATION",
        "PER_LINEAR_METER", "4500", "CLP", "2800", "CLP",
    ]],
    "Seguridad vidrio": [[
        "GLASS-SAFETY-DOOR", "Paño vidriado en puerta",
        "El paño de una puerta vidriada debería llevar vidrio de seguridad.",
        "", "", "", "si", "", "SAFETY_GLASS", "WARNING", "NCh 135/2",
    ]],
    "Límites vidrio": [[
        "GLASS-LIMIT-TEMPERED-EXACT-CUT", "TEMPERED", "", "", "", "3200",
        "", "", "", "si", "WARNING", "Práctica vidriera",
    ]],
}

_LEEME_LINES = [
    "Plantilla oficial de catálogo DEKOPEN",
    "",
    "Completa una fila por elemento en cada hoja. La primera fila de cada",
    "hoja es el encabezado — no la borres ni la renombres. Los valores se",
    "expresan en mm, kg/m, kg y CLP según la columna.",
    "",
    "Todo lo que subas pasa por revisión humana antes de publicarse:",
    "nada llega al catálogo sin que una persona lo confirme.",
    "",
    "Enumerados válidos:",
    f"  material: {', '.join(_MATERIALS)}",
    f"  familia: {', '.join(_FAMILIES)}",
    f"  rol: {', '.join(_PROFILE_ROLES)}",
    f"  tipologia / apertura: {', '.join(_OPENING_TYPES)}",
    f"  clase_acabado: {', '.join(_FINISH_CLASSES)}",
    "  tipo_riel: mono, dual",
    "  obligatorio: si / no",
    f"  tipo recargo vidrio: {', '.join(_SURCHARGE_KINDS)}",
    f"  unidad recargo vidrio: {', '.join(_SURCHARGE_UNITS)}",
    f"  tipo_lamina: {', '.join(_LAMINA_KINDS)}",
    f"  seguridad_requerida: {', '.join(_REQUIRED_SAFETY)}",
    f"  severidad: {', '.join(_SEVERITIES)}",
    f"  apertura (herrajes): {', '.join(_OPENING_FAMILIES)}",
    f"  regla_altura_manilla: {', '.join(_HANDLE_HEIGHT_RULES)}",
    f"  tipo_manilla: {', '.join(_HANDLE_KINDS)}",
    f"  tipo_opcion: {', '.join(_OPTION_KINDS)}",
    "",
    "En «Herrajes», «contenido_json» admite por componente además de",
    "qty: qty_rule ({kind: PER_WIDTH|PER_HEIGHT, per_mm, min_qty, max_qty})",
    "para cantidades por rango, cut_rule ({axis: WIDTH|HEIGHT, minus_mm})",
    "para largos de corte, weight_kg, cost_clp y machining (declaraciones",
    "de mecanizado: cerradero, alojamiento de cremona, bisagras).",
]


def build_template() -> bytes:
    """The official XLSX template — LEEME + the declared sheets."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    workbook = Workbook()
    readme = workbook.active
    readme.title = _LEEME
    for index, line in enumerate(_LEEME_LINES, start=1):
        cell = readme.cell(row=index, column=1, value=line)
        if index == 1:
            cell.font = Font(bold=True)
    readme.column_dimensions["A"].width = 90
    for sheet_name, spec in _SHEETS.items():
        sheet = workbook.create_sheet(sheet_name)
        for column_index, (header, *_rest) in enumerate(spec["columns"], start=1):
            cell = sheet.cell(row=1, column=column_index, value=header)
            cell.font = Font(bold=True)
            sheet.column_dimensions[cell.column_letter].width = max(
                len(header) + 4, 14
            )
        for row_index, example in enumerate(_EXAMPLES.get(sheet_name, []), start=2):
            for column_index, value in enumerate(example, start=1):
                sheet.cell(row=row_index, column=column_index, value=value)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _header_index(
    headers: list[str], expected: list[tuple[str, str, str, bool, Any]]
) -> tuple[dict[int, tuple[str, str, str, bool, Any]], list[str]]:
    """Map column index → spec by declared header names; returns the map and
    the list of expected headers the sheet is missing."""
    positions = {header.lower(): i for i, header in enumerate(headers)}
    mapping: dict[int, tuple[str, str, str, bool, Any]] = {}
    missing: list[str] = []
    for header, field, kind, required, enum in expected:
        if header.lower() in positions:
            mapping[positions[header.lower()]] = (header, field, kind, required, enum)
        elif required:
            # Optional columns may be dropped; a missing required column makes
            # the sheet unparseable.
            missing.append(header)
    return mapping, missing


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _cell(
    raw: object,
    spec: tuple[str, str, str, bool, Any],
    *,
    sheet: str,
    row_number: int,
    errors: list[str],
) -> object:
    header, field, kind, required, enum = spec
    text = "" if raw is None else str(raw).strip()
    if isinstance(raw, float) and raw == int(raw):
        # openpyxl hands back 60.0 for a written 60 — keep integers honest.
        text = str(int(raw))
    if required and not text:
        errors.append(f"Fila {row_number} de «{sheet}»: «{header}» es obligatorio.")
        return None
    if not text:
        return None
    if kind == "text":
        return text[:200]
    if kind == "csv_list":
        return [part.strip() for part in re_split_list(text) if part.strip()]
    if kind == "decimal":
        value = _decimal(text)
        if value is None:
            errors.append(
                f"Fila {row_number} de «{sheet}»: «{header}» debe ser un número (ej. 58 o 58.5), llegó «{text}»."
            )
        return value
    if kind == "int":
        value = _decimal(text)
        if value is None or value != int(value):
            errors.append(
                f"Fila {row_number} de «{sheet}»: «{header}» debe ser un entero, llegó «{text}»."
            )
            return None
        return int(value)
    if kind == "int0_2":
        value = _decimal(text)
        if value is None or int(value) not in (0, 1, 2) or value != int(value):
            errors.append(
                f"Fila {row_number} de «{sheet}»: «{header}» debe ser 0, 1 o 2 (extremos soldados), llegó «{text}»."
            )
            return None
        return int(value)
    if kind == "bool":
        lowered = text.lower()
        if lowered in ("si", "sí", "true", "1", "x"):
            return True
        if lowered in ("no", "false", "0", ""):
            return False
        errors.append(
            f"Fila {row_number} de «{sheet}»: «{header}» debe ser sí o no, llegó «{text}»."
        )
        return None
    if kind == "enum":
        normalized = text.strip().upper().replace(" ", "_")
        for allowed in enum:
            if normalized == allowed.upper():
                return allowed
        errors.append(
            f"Fila {row_number} de «{sheet}»: «{header}» debe ser uno de "
            f"{', '.join(enum)}; llegó «{text}»."
        )
        return None
    if kind == "json":
        try:
            value = json.loads(text)
        except ValueError:
            errors.append(
                f"Fila {row_number} de «{sheet}»: «{header}» no es JSON válido."
            )
            return None
        if not isinstance(value, list):
            errors.append(
                f"Fila {row_number} de «{sheet}»: «{header}» debe ser una lista JSON."
            )
            return None
        return value
    return text


def re_split_list(text: str) -> list[str]:
    import re

    return re.split(r"[,;|]", text)


def _parse_sheet(
    sheet_name: str, rows_data: list[list[object]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """One sheet → typed candidates + sheet-level errors."""
    spec = _SHEETS[sheet_name]
    entity = spec["entity"]
    expected = spec["columns"]
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    if not rows_data:
        return candidates, errors
    headers = ["" if cell is None else str(cell).strip() for cell in rows_data[0]]
    mapping, missing = _header_index(headers, expected)
    if missing:
        errors.append(
            f"La hoja «{sheet_name}» no tiene las columnas {', '.join(missing)} "
            "— usa la plantilla oficial sin renombrar encabezados."
        )
        return candidates, errors
    for row_index, row in enumerate(rows_data[1:], start=2):
        cells = ["" if cell is None else cell for cell in row]
        if not any(str(cell).strip() for cell in cells):
            continue
        row_errors: list[str] = []
        fields: dict[str, object] = {}
        field_evidence: dict[str, object] = {}
        for column_index, column_spec in mapping.items():
            raw = cells[column_index] if column_index < len(cells) else None
            header = column_spec[0]
            value = _cell(
                raw, column_spec, sheet=sheet_name, row_number=row_index,
                errors=row_errors,
            )
            fields[column_spec[1]] = value
            field_evidence[column_spec[1]] = {
                "normalized": None if value is None else str(value),
                "original": None if raw is None else str(raw),
                "source": f"hoja {sheet_name} · columna {header} · fila {row_index}",
            }
        candidates.append(
            {
                "key": f"{entity}:{sheet_name}:{row_index}",
                "entity": entity,
                "confidence": (
                    CONFIDENCE_ERROR if row_errors else CONFIDENCE_VERIFIED_STRUCTURED
                ),
                "row_errors": row_errors,
                "warnings": [],
                "source_ref": f"hoja {sheet_name} · fila {row_index}",
                "fields": fields,
                # Legacy review keeps the article shape for PROFILE rows.
                **(
                    {
                        "sku": fields.get("sku"),
                        "name": fields.get("name"),
                        "role": fields.get("role"),
                        "face_width_mm": fields.get("face_width_mm"),
                        "commercial_length_mm": fields.get("commercial_length_mm"),
                        "welding_loss_mm": fields.get("welding_loss_mm"),
                        "reinforcement_sku": fields.get("reinforcement_sku"),
                        "weight_kg_m": fields.get("weight_kg_m"),
                        "steel_weight_kg_m": fields.get("steel_weight_kg_m"),
                    }
                    if entity == ENTITY_PROFILE
                    else {}
                ),
                "evidence": {
                    "parser_version": PARSER_VERSION,
                    "source": {
                        "ref": f"hoja {sheet_name} · fila {row_index}",
                        "text": " | ".join(
                            str(cell) for cell in cells if str(cell).strip()
                        )[:300],
                    },
                    "fields": field_evidence,
                },
            }
        )
    return candidates, errors


def _xlsx_sheets(content: bytes) -> dict[str, list[list[object]]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheets: dict[str, list[list[object]]] = {}
    for sheet in workbook.worksheets:
        if sheet.title == _LEEME:
            continue
        sheets[sheet.title] = [
            list(row) for row in sheet.iter_rows(values_only=True)
        ]
    workbook.close()
    return sheets


def looks_like_template(kind: str, content: bytes) -> bool:
    """True when the upload follows the declared sheet/column contract —
    the structured parser claims it, the prose parser stands down."""
    try:
        if kind == "XLSX":
            return any(name in _SHEETS for name in _xlsx_sheets(content))
        if kind == "CSV":
            header = _csv_rows(content)[:1]
            if not header:
                return False
            headers = {str(cell).strip().lower() for cell in header[0]}
            return all(
                expected[0].lower() in headers
                for expected in _SHEETS["Perfiles"]["columns"][:3]
            )
    except Exception:
        return False
    return False


def _csv_rows(content: bytes) -> list[list[object]]:
    text = content.decode("utf-8-sig", errors="replace")
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]


def parse_catalog_spreadsheet(
    kind: str, content: bytes
) -> tuple[list[dict[str, Any]], list[str]]:
    """(candidates, sheet_errors). Every row becomes one candidate; rows with
    problems carry row_errors and confidence ERROR — review sees them,
    confirm refuses them."""
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    if kind == "XLSX":
        sheets = _xlsx_sheets(content)
        for sheet_name, rows_data in sheets.items():
            if sheet_name not in _SHEETS:
                errors.append(
                    f"La hoja «{sheet_name}» no forma parte de la plantilla y se ignoró."
                )
                continue
            found, sheet_errors = _parse_sheet(sheet_name, rows_data)
            candidates.extend(found)
            errors.extend(sheet_errors)
    elif kind == "CSV":
        found, sheet_errors = _parse_sheet("Perfiles", _csv_rows(content))
        candidates.extend(found)
        errors.extend(sheet_errors)
    return candidates, errors
