"""D05 — real finishes: declared color catalog, bicolor validation,
finish-driven rules and per-color stock identity.

Coverage of the encargo's engine contract:
- the declared catalog resolves interior+exterior pairs; every
  impossible combination raises `ColorCombinationError` with a stable
  code and a Spanish, user-facing message;
- finish class drives reinforcement rules — a NON_WHITE position
  (foil/dark/coextruded) gets its declared mandatory steel where WHITE
  members only reinforce above the declared minimum length;
- the BOM carries the stock key (plain code or ``EXT/INT`` bicolor),
  the quotation label and the declared surcharges with their basis;
- glazing clearance and leaf-envelope factors come from the finish,
  never from a hardcoded foil switch;
- systems without a declared catalog keep the pre-D05 WHITE/FOILED
  fallback.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine import (
    BayOpeningType,
    ColorKind,
    ColorOption,
    ColorSurcharge,
    EngineResult,
    NodeType,
    ParametricNode,
    ProfileRole,
    SystemParams,
    calculate_geometry,
)
from dekopen_engine.finishes import (
    ColorCombinationError,
    apply_color_surcharges,
    resolve_color,
    resolve_color_selection,
)
from engine.tests.catalog import demo_60_params as build_demo_60_params


def d(value: str) -> Decimal:
    return Decimal(value)


def _bay(width_mm: str, height_mm: str, opening: BayOpeningType) -> ParametricNode:
    return ParametricNode(
        id="d05",
        type=NodeType.BAY,
        width_mm=d(width_mm),
        height_mm=d(height_mm),
        opening_type=opening,
        glass_thickness_mm=d("4.00"),
        glass_spec="4",
    )


def _colored_params() -> SystemParams:
    """DEMO_70-like finish catalog over the DEMO_60 machining base."""
    options = {
        "WHITE": ColorOption(
            code="WHITE",
            name="Blanco",
            kind=ColorKind.MASS,
            render_color="#E9EBE4",
            sort_order=0,
        ),
        "NOGAL": ColorOption(
            code="NOGAL",
            name="Nogal",
            kind=ColorKind.FOIL,
            manufacturer_code="REH 2178-034",
            render_color="#6B4A2F",
            render_texture="WOOD_GRAIN",
            finish_class="NON_WHITE",
            film_clearance=True,
            dark=True,
            sort_order=20,
            surcharge=ColorSurcharge(
                kind="PER_PROFILE_METER",
                amount=d("850"),
                label="Recargo foliado por metro de perfil",
            ),
        ),
        "NOGAL-EXT": ColorOption(
            code="NOGAL-EXT",
            name="Nogal",
            kind=ColorKind.FOIL,
            manufacturer_code="REH 2178-034",
            render_color="#6B4A2F",
            render_texture="WOOD_GRAIN",
            finish_class="NON_WHITE",
            film_clearance=True,
            dark=True,
            faces="EXTERIOR_ONLY",
            pair_code="WHITE",
            sort_order=30,
            surcharge=ColorSurcharge(kind="PER_M2", amount=d("4200")),
        ),
        "ANTRACITA": ColorOption(
            code="ANTRACITA",
            name="Antracita",
            kind=ColorKind.FOIL,
            manufacturer_code="REH 701605",
            gloss="MATE",
            render_color="#3A3F44",
            finish_class="NON_WHITE",
            film_clearance=True,
            dark=True,
            size_factor=d("0.9"),
            sort_order=40,
            surcharge=ColorSurcharge(kind="PER_M2", amount=d("6800")),
        ),
        "COEX-ANTR": ColorOption(
            code="COEX-ANTR",
            name="Antracita coextruida",
            kind=ColorKind.COEXTRUDED,
            manufacturer_code="RAU CX-7016",
            render_color="#33373C",
            finish_class="NON_WHITE",
            film_clearance=True,
            dark=True,
            faces="EXTERIOR_ONLY",
            pair_code="WHITE",
            sort_order=50,
            surcharge=ColorSurcharge(kind="FIXED_PER_POSITION", amount=d("9500")),
        ),
        # Whole-bar mass colour — it can never pair bicolor.
        "ROBLE_MASA": ColorOption(
            code="ROBLE_MASA",
            name="Roble en masa",
            kind=ColorKind.MASS,
            render_color="#8A6A45",
            finish_class="NON_WHITE",
            dark=True,
            sort_order=60,
        ),
        # Explicit per-finish clearance override.
        "GRANATE": ColorOption(
            code="GRANATE",
            name="Granate",
            kind=ColorKind.FOIL,
            render_color="#5E2B32",
            finish_class="NON_WHITE",
            glass_clearance_mm=d("4.50"),
            sort_order=70,
        ),
    }
    params = build_demo_60_params()
    return params.model_copy(
        update={
            "system_code": "DEMO_70",
            "finishes": tuple(options),
            "bicolor_allowed": True,
            "color_options": options,
            # Divergent declared clearances so the film-vs-white path is
            # observable (the DEMO_60 base declares both at 5 mm).
            "glass_clearance_white_mm": d("3.00"),
            "glass_clearance_foil_mm": d("5.00"),
        }
    )


def _steel_lengths(result: "EngineResult", role: ProfileRole) -> list[Decimal]:
    return sorted(
        piece.length_mm for piece in result.reinforcements if piece.role is role
    )


# ── Pair validation ───────────────────────────────────────────────────


def test_monochrome_selection_resolves() -> None:
    params = _colored_params()
    selection = resolve_color_selection(params, "NOGAL", "NOGAL")
    assert selection.interior.code == selection.exterior.code == "NOGAL"
    assert not selection.bicolor
    assert selection.stock_key() == "NOGAL"
    assert selection.display_name() == "Nogal"
    assert selection.finish_class == "NON_WHITE"


def test_bicolor_selection_resolves_and_labels_per_face() -> None:
    params = _colored_params()
    selection = resolve_color_selection(params, "WHITE", "NOGAL-EXT")
    assert selection.bicolor
    assert selection.stock_key() == "NOGAL-EXT/WHITE"
    assert selection.display_name() == "Nogal exterior / Blanco interior"
    assert selection.finish_class == "NON_WHITE"


def test_bicolor_rejected_when_system_disallows_it() -> None:
    params = _colored_params().model_copy(update={"bicolor_allowed": False})
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "WHITE", "ANTRACITA")
    assert error.value.code == "bicolor_not_allowed"
    assert "no admite acabados bicolor" in str(error.value)


def test_undeclared_color_rejected() -> None:
    params = _colored_params()
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "MAGENTA", "WHITE")
    assert error.value.code == "color_not_declared"
    assert "MAGENTA" in str(error.value)


def test_face_restricted_option_rejected_on_wrong_face() -> None:
    params = _colored_params()
    # NOGAL-EXT only exists on the exterior face.
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "NOGAL-EXT", "WHITE")
    assert error.value.code == "color_face_forbidden"
    assert "interior" in str(error.value)


def test_two_mass_colors_reject_bicolor() -> None:
    params = _colored_params()
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "WHITE", "ROBLE_MASA")
    assert error.value.code == "color_pair_incompatible"
    assert "colores de masa" in str(error.value)


def test_whole_bar_kind_rejects_bicolor() -> None:
    params = _colored_params()
    anodized = params.color_options["NATURAL"] = ColorOption(
        code="NATURAL",
        name="Natural anodizado",
        kind=ColorKind.ANODIZED,
        render_color="#B9BEC4",
    )
    params.finishes = params.finishes + ("NATURAL",)
    assert anodized is not None
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "WHITE", "NATURAL")
    assert error.value.code == "color_pair_incompatible"
    assert "barra completa" in str(error.value)


def test_pair_code_requirement_enforced() -> None:
    params = _colored_params()
    # COEX-ANTR declares WHITE as the required opposite face.
    with pytest.raises(ColorCombinationError) as error:
        resolve_color_selection(params, "NOGAL", "COEX-ANTR")
    assert error.value.code == "color_pair_requires"
    assert "WHITE" in str(error.value)


def test_legacy_finishes_keep_binary_semantics() -> None:
    params = build_demo_60_params()
    selection = resolve_color_selection(params, "FOILED", "FOILED")
    assert selection.finish_class == "NON_WHITE"
    assert selection.stock_key() == "FOILED"
    assert resolve_color(params, "FOILED").film_clearance


# ── Finish-driven rules ──────────────────────────────────────────────


def test_foiled_selection_drives_mandatory_reinforcement() -> None:
    """Golden: the declared NON_WHITE rule reinforces every SASH member;
    the WHITE rule only fires above its declared minimum length."""
    params = _colored_params()
    node = _bay("800.00", "1200.00", BayOpeningType.TURN_LEFT)

    white = calculate_geometry(
        node,
        params,
        color_selection=resolve_color_selection(params, "WHITE", "WHITE"),
    )
    nogal = calculate_geometry(
        node,
        params,
        color_selection=resolve_color_selection(params, "NOGAL", "NOGAL"),
    )

    assert _steel_lengths(white, ProfileRole.SASH) == [d("1066.00")]
    assert _steel_lengths(nogal, ProfileRole.SASH) == [d("666.00"), d("1066.00")]
    assert nogal.finish_key == "NOGAL"
    assert nogal.finish_label == "Nogal"
    assert nogal.finish_class == "NON_WHITE"


def test_bicolor_stock_key_stamps_on_bom() -> None:
    params = _colored_params()
    node = _bay("800.00", "1200.00", BayOpeningType.TURN_LEFT)
    result = calculate_geometry(
        node,
        params,
        color_selection=resolve_color_selection(params, "WHITE", "NOGAL-EXT"),
    )
    assert result.finish_key == "NOGAL-EXT/WHITE"
    assert result.finish_label == "Nogal exterior / Blanco interior"
    # One foiled face still means the member is non-white for machining.
    assert result.finish_class == "NON_WHITE"


def test_film_clearance_follows_the_resolved_selection() -> None:
    params = _colored_params()
    white_selection = resolve_color_selection(params, "WHITE", "WHITE")
    foil_selection = resolve_color_selection(params, "NOGAL", "NOGAL")
    assert white_selection.glass_clearance_mm(params) == d("3.00")
    assert foil_selection.glass_clearance_mm(params) == d("5.00")
    # An explicit per-finish override wins over the kind defaults.
    override = resolve_color_selection(params, "GRANATE", "GRANATE")
    assert override.glass_clearance_mm(params) == d("4.50")


def test_dark_finish_shrinks_the_leaf_envelope() -> None:
    params = _colored_params()
    selection = resolve_color_selection(params, "WHITE", "ANTRACITA")
    assert selection.envelope_factor() == d("0.9")
    neutral = resolve_color_selection(params, "WHITE", "WHITE")
    assert neutral.envelope_factor() == d("1")


# ── Declared surcharges on the BOM ────────────────────────────────────


def test_surcharge_applications_carry_engine_basis() -> None:
    params = _colored_params()
    node = _bay("1000.00", "1000.00", BayOpeningType.FIXED)
    result = calculate_geometry(
        node,
        params,
        color_selection=resolve_color_selection(params, "NOGAL", "NOGAL"),
    )
    (application,) = result.color_surcharges
    assert application.option_code == "NOGAL"
    assert application.kind == "PER_PROFILE_METER"
    assert application.rate == d("850")
    # The basis is the BOM's own cut metres — 2 vertical + 2 horizontal
    # frame cuts plus 4 bead cuts on the fixed golden.
    metres = sum(cut.length_mm * cut.qty for cut in result.profile_cuts) / d("1000")
    assert application.basis == metres.quantize(d("0.001"))


def test_per_m2_and_fixed_bases() -> None:
    params = _colored_params()
    selection = resolve_color_selection(params, "WHITE", "COEX-ANTR")
    node = _bay("1000.00", "1000.00", BayOpeningType.FIXED)
    result = calculate_geometry(node, params, color_selection=selection)
    applications = {item.kind: item for item in result.color_surcharges}
    assert applications["FIXED_PER_POSITION"].basis == d("1")
    assert applications["FIXED_PER_POSITION"].rate == d("9500")
    # COEX-ANTR pairs exterior-only; interior face has no surcharge.
    assert len(result.color_surcharges) == 1

    selection = resolve_color_selection(params, "WHITE", "NOGAL-EXT")
    applications_ext = apply_color_surcharges(
        selection, result, area_m2=d("2.5")
    )
    (m2,) = [item for item in applications_ext if item.kind == "PER_M2"]
    assert m2.basis == d("2.5000")
    assert m2.rate == d("4200")
