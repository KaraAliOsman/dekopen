"""IA2 — ops tipadas, validador y herramientas del motor.

Cubre el encargo §1/§2/§3 sin Postgres ni red: el registro de ops mínimo,
la expansión `parts` de split_bay con la convención de offsets del reducer
del canvas, el valor por defecto de módulo único, el cierre aritmético de
`_citable_values` (número derivado ≠ número inventado), el canal `clarify`
y las herramientas `{"kind":"tool"}` sobre las filas fixture del arnés IA1.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ai_gateway.evals import fixtures
from ai_gateway.evals.harness import _tools_rows
from projects import design_assist
from projects.ops_registry import (
    OP_INDEX,
    OPS,
    batchable_ops,
    ops_contract,
)


CATALOG = fixtures.CATALOGS[str(fixtures.DEMO_60_ID)]


def _summary(product: dict | None = None):
    return design_assist._summary(
        product or fixtures.product_editor_vacia(),
        width_mm="1500.00",
        height_mm="1200.00",
    )


def _declared(prompt: str, summary=None):
    return design_assist._citable_values(
        design_assist._declared_values(prompt),
        design_assist._context_numbers(summary or _summary(), CATALOG),
    )


def _validate(ops, summary=None, prompt: str = ""):
    product_summary = summary or _summary()
    return design_assist._validate_ops(
        ops,
        product_summary,
        CATALOG,
        _declared(prompt, product_summary),
        declared_strict=design_assist._declared_values(prompt),
    )


# ---------------------------------------------------------------------------
# §1 — registro único de ops
# ---------------------------------------------------------------------------


def test_registry_covers_the_required_vocabulary():
    """El vocabulario mínimo del encargo: las ops de diseño/posición/proyecto
    en el registro; las `prepare_*` son acciones del agente (`kind:"prepare"`,
    sólo abren la superficie real) — declaradas en PREPARE_ROUTES, no como
    ops aplicables (nunca se ejecutan solas). `apply_to_positions` se
    materializa como paso `batch_ops` sobre las ops `batchable`."""
    required = {
        "split_bay",
        "move_divider",
        "remove_divider",
        "set_bay_size",
        "equalize_bays",
        "set_sliding_layout",
        "set_travel",
        "set_opening",
        "set_handle_height",
        "flip_handing",
        "set_glass",
        "set_glass_thickness",
        "set_panel",
        "set_finish",
        "set_system",
        "set_location",
        "set_quantity",
        "add_position",
        "duplicate_position",
        "remove_position",
        "update_position",
    }
    assert required <= set(OP_INDEX), f"faltan: {required - set(OP_INDEX)}"

    from ai_gateway.agent import BATCH_OPS, PREPARE_ROUTES, PREPARE_TOOLS

    assert {
        "prepare_emit",
        "prepare_release",
        "prepare_purchase",
        "prepare_payment_link",
    } <= set(PREPARE_ROUTES)
    for action in ("prepare_emit", "prepare_release", "prepare_purchase"):
        assert PREPARE_TOOLS[action]  # la tool real a la que abre la superficie
    # apply_to_positions: el lote aplica cualquier op batchable a N posiciones.
    assert BATCH_OPS and BATCH_OPS <= set(OP_INDEX)
    assert {"set_glass", "set_opening", "set_handle_height"} <= BATCH_OPS


def test_registry_contract_declares_params_and_scopes():
    contract = ops_contract()
    assert set(contract) == {"product", "position", "project"}
    names = {line.split(" {", 1)[0] for lines in contract.values() for line in lines}
    assert names == set(OP_INDEX)
    for op in OPS:
        for param in op.params:
            assert param.kind, f"{op.name}.{param.name}"
    # split_bay ganó `parts` (IA2) — "N hojas iguales" sin inventar offsets.
    parts = next(p for p in OP_INDEX["split_bay"].params if p.name == "parts")
    assert parts.kind == "int"
    assert not parts.required


def test_batch_ops_subset_of_registry():
    batchable = batchable_ops()
    assert batchable <= set(OP_INDEX)
    for name in ("set_glass", "set_opening", "set_handle_height"):
        assert name in batchable
    assert "add_position" not in batchable  # alta es una op, no un ajuste


# ---------------------------------------------------------------------------
# §1 — split_bay con parts: el motor calcula los cortes
# ---------------------------------------------------------------------------


def test_split_bay_parts_expands_with_absolute_root_offset():
    """parts=3 → dos cortes secuenciales; el raíz guarda la centerline
    absoluta (origen de región + parte local) como el reducer del canvas."""
    accepted, rejected, _ = _validate(
        [
            {"op": "split_bay", "axis": "V", "parts": 3},
        ],
        prompt="la quiero en tres hojas iguales",
    )
    assert rejected == []
    assert len(accepted) == 2
    # Región del vano: 60..1440 (1380) → primer corte local 460 → centerline
    # absoluta 60+460 = 520 guardada en el split raíz.
    assert Decimal(str(accepted[0]["offset_mm"])) == Decimal("520")
    assert accepted[0]["bay"] == "m1"
    # El segundo corte divide added_b1 — ref sintética direccionable.
    assert accepted[1]["bay"] == "added_b1"
    assert accepted[0]["new_divider"] == "added_d1"
    assert accepted[1]["new_bay"] == "added_b2" or accepted[1]["new_bay"]
    assert accepted[1]["new_divider"] == "added_d2"


def test_split_bay_parts_requires_declared_number():
    accepted, rejected, _ = _validate(
        [{"op": "split_bay", "axis": "V", "parts": 3}],
        prompt="divídela",  # no declara "tres" ni 3
    )
    assert accepted == []
    assert rejected[0]["reason"] == "partes_no_declaradas"


def test_split_bay_parts_bounds():
    for parts in (0, 1, 9, "3", 2.5, True):
        _, rejected, _ = _validate(
            [{"op": "split_bay", "axis": "V", "parts": parts}],
            prompt=f"{parts} partes",
        )
        assert rejected, f"parts={parts} debió rechazarse"


def test_split_bay_sole_module_default():
    """Un solo módulo: la op sin `module` resuelve la única hoja — igual que
    el click de la UI sobre el único módulo visible."""
    accepted, rejected, _ = _validate(
        [{"op": "split_bay", "axis": "V", "offset_mm": "750"}],
        prompt="divídela en dos",
    )
    assert rejected == []
    assert accepted[0]["module"] == "m1"


def test_set_opening_after_parts_addresses_synthetic_bays():
    accepted, rejected, _ = _validate(
        [
            {"op": "split_bay", "axis": "V", "parts": 3},
            {"op": "set_opening", "bay": 0, "opening": "TURN_LEFT"},
            {"op": "set_opening", "bay": 2, "opening": "TURN_RIGHT"},
        ],
        prompt="tres hojas fija al centro abatibles espejo",
    )
    assert rejected == []
    assert len(accepted) == 4  # 2 cortes + 2 aperturas


# ---------------------------------------------------------------------------
# §3 — clarify tipado
# ---------------------------------------------------------------------------


def test_clarify_validates_shape():
    good = {
        "question": "¿1050 mm es la altura de instalación o la final?",
        "options": [
            {"value": "instalacion", "label": "Altura de instalación"},
            {"value": "elevacion", "label": "Altura sobre el piso"},
        ],
    }
    assert design_assist._clarify({"clarify": good}) == good
    assert design_assist._clarify({"clarify": {}}) is None
    # Las opciones se normalizan: value obligatorio, label con fallback.
    out = design_assist._clarify(
        {"clarify": {"question": "¿cuál?", "options": [{"value": "a"}, "b"]}}
    )
    assert out is not None
    assert out["options"] == [
        {"value": "a", "label": "a"},
        {"value": "b", "label": "b"},
    ]
    assert design_assist._clarify({"clarify": "pregunta libre"}) is None
    assert design_assist._clarify({"clarify": {"question": "  "}}) is None


# ---------------------------------------------------------------------------
# §2 — cierre aritmético: derivado ≠ inventado
# ---------------------------------------------------------------------------


def test_derived_numbers_are_citable_but_invented_are_not():
    declared = _declared("20 cm más ancha")
    assert Decimal("1700") in declared  # 1500 + 200
    assert Decimal("750") in declared  # la mitad
    assert Decimal("999") not in declared


def test_set_total_width_accepts_derived_sum():
    """"20 cm más ancha" — el modelo calcula 1700; el validador lo acepta
    porque el número viene del cierre de los valores declarados (nunca un
    literal que la IA inventó)."""
    accepted, rejected, _ = _validate(
        [{"op": "set_total_width", "width_mm": "1700"}],
        prompt="hazla 20 cm más ancha",
    )
    assert rejected == []
    assert accepted and Decimal(str(accepted[0]["width_mm"])) == Decimal("1700")


def test_invented_measure_still_rejected():
    accepted, rejected, _ = _validate(
        [{"op": "set_total_width", "width_mm": "9999"}],
        prompt="hazla más ancha",
    )
    assert accepted == []
    assert rejected[0]["reason"] == "ancho_no_declarado"


# ---------------------------------------------------------------------------
# §2 — herramientas del motor (sin Postgres: filas fixture del arnés)
# ---------------------------------------------------------------------------


@pytest.fixture
def tool_rows(monkeypatch):
    from ai_gateway import tools

    given = fixtures.given("proyecto")
    monkeypatch.setattr(tools, "rows", _tools_rows(given))
    return tools, given


def test_tool_names_match_the_encargo(tool_rows):
    tools, _ = tool_rows
    assert set(tools.TOOL_NAMES) == {
        "calculate_position",
        "validate_position",
        "price_position",
        "price_project",
        "explain_price_delta",
        "list_catalog_options",
        "get_blockers",
        "simulate_ops",
    }
    assert set(tools.TOOL_IMPLS) == set(tools.TOOL_NAMES)


def test_calculate_position_cites_persisted_weights(tool_rows):
    tools, given = tool_rows
    position = given["positions"][0]
    out = tools.calculate_position(
        fixtures.ORG_ID,
        {"position_id": str(position["id"])},
        frozenset(),
    )
    assert out["ok"] is True
    assert out["has_bom"] is True
    assert out["leaf_weights"], "el BOM fixture trae pesos por hoja"
    assert all(Decimal(str(w["total_weight_kg"])) > 0 for w in out["leaf_weights"])


def test_price_project_reports_every_position_in_order(tool_rows):
    """price_project nunca adivina: recorre las posiciones reales del
    proyecto ordenadas y reporta costo o el error honesto por fila (la
    tabla de precios no está en las filas fixture — la posición se
    reporta con `error`, no se aborta la lista)."""
    tools, given = tool_rows
    out = tools.price_project(
        fixtures.ORG_ID,
        {"project_id": str(fixtures.PROJECT_ID)},
        frozenset(),
    )
    assert out["ok"] is True
    indexes = [p["index"] for p in out["positions"]]
    assert indexes == sorted(indexes)
    assert len(out["positions"]) == len(given["positions"])
    for item in out["positions"]:
        assert item["ok"] in (True, False)
        if item["ok"]:
            assert Decimal(str(item["line_cost"])) >= 0
        else:
            assert item["error"]


def test_unobserved_position_ref_is_an_error_not_a_fetch(tool_rows):
    tools, _ = tool_rows
    out = tools.calculate_position(
        fixtures.ORG_ID,
        {"position_id": "00000000-0000-0000-0000-00000000dead"},
        frozenset(),
    )
    assert out == {"ok": False, "error": "position_not_found"}
