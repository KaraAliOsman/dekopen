"""Finish (color) domain for the Dekopen engine (encargo D05).

`SystemParams.color_options` is the declared per-system color catalog:
each `ColorOption` is a real finish the series sells — manufacturer code,
kind, finish class, render color and declared surcharge. This module owns:

* `resolve_color` — code → declared `ColorOption`, with the legacy
  fallback (declared code without a catalog row keeps pre-D05 semantics:
  non-WHITE = foiled).
* `resolve_color_selection` — the interior+exterior pair validation.
  Every impossible combination raises `ColorCombinationError` with a
  stable machine code and a Spanish user-facing message; nothing is
  silently coerced.
* `apply_color_surcharges` — declared surcharges →
  `ColorSurchargeApplication` rows carrying the BOM-derived basis.

The engine stays pure: everything here is declared data applied
deterministically — no invented colours, clearances or rates.
"""

from __future__ import annotations

from decimal import Decimal

from dekopen_engine.models import (
    ColorKind,
    ColorOption,
    ColorSelection,
    ColorSurchargeApplication,
    EngineResult,
    SystemParams,
)

Q = Decimal("0.001")
Q_AREA = Decimal("0.0001")

# Kinds that occupy the whole bar — they can never carry a different
# finish on the opposite face. MASS is the bar's own colour and stays
# pairable: PVC bicolor is precisely a white mass bar filmed on one
# face; anodized soaks the whole surface and cannot take a second face.
WHOLE_BAR_KINDS = frozenset({ColorKind.ANODIZED})


class ColorCombinationError(ValueError):
    """Raised when a finish pair cannot be manufactured (D05).

    `code` is the stable machine token the API boundary maps to a
    contract error; `message` is the es-CL user-facing text — every
    error names the real constraint, never a fabricated reason.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _legacy_option(code: str) -> ColorOption:
    """Declared finish code with no catalog row — pre-D05 semantics:
    non-WHITE is foiled (NON_WHITE class + film clearance)."""
    return ColorOption(
        code=code,
        name=code,
        kind=ColorKind.MASS if code == "WHITE" else ColorKind.FOIL,
        finish_class="WHITE" if code == "WHITE" else "NON_WHITE",
        film_clearance=code != "WHITE",
        data_provenance="LEGACY_UNVERIFIED",
    )


def resolve_color(params: SystemParams, code: str) -> ColorOption:
    """Resolve one finish code against the declared catalog.

    A catalog row wins; a code only declared in `params.finishes` keeps
    the legacy foil semantics; anything else is `color_not_declared`.
    """
    option = params.color_options.get(code)
    if option is not None:
        return option
    if code not in params.finishes:
        raise ColorCombinationError(
            "color_not_declared",
            f"El color «{code}» no está declarado en el sistema {params.system_code}.",
        )
    return _legacy_option(code)


def _check_face(option: ColorOption, face: str, *, system_code: str) -> None:
    if option.faces == "BOTH":
        return
    allowed = option.faces.replace("_ONLY", "")
    if face != allowed:
        face_label = "exterior" if face == "EXTERIOR" else "interior"
        raise ColorCombinationError(
            "color_face_forbidden",
            f"El acabado «{option.name}» no se fabrica en la cara {face_label} "
            f"del sistema {system_code}.",
        )


def resolve_color_selection(
    params: SystemParams,
    interior_code: str,
    exterior_code: str,
) -> ColorSelection:
    """Validate and resolve the interior+exterior finish pair.

    Equal codes only check face availability. Different codes require the
    system's declared bicolor capability, respect per-face availability
    and `pair_code`, and forbid whole-bar kinds on either face.
    """
    interior = resolve_color(params, interior_code)
    exterior = resolve_color(params, exterior_code)
    _check_face(interior, "INTERIOR", system_code=params.system_code)
    _check_face(exterior, "EXTERIOR", system_code=params.system_code)
    if interior_code == exterior_code:
        return ColorSelection(interior=interior, exterior=exterior)

    if not params.bicolor_allowed:
        raise ColorCombinationError(
            "bicolor_not_allowed",
            f"El sistema {params.system_code} no admite acabados bicolor "
            f"(«{exterior.name}» exterior / «{interior.name}» interior).",
        )
    for option in (interior, exterior):
        if option.kind in WHOLE_BAR_KINDS:
            raise ColorCombinationError(
                "color_pair_incompatible",
                f"El acabado «{option.name}» es de barra completa "
                f"({option.kind.value}) — no admite una cara distinta.",
            )
    # Two different mass colours can't occupy one bar — the body colour
    # is what the bar is extruded as; only applied finishes layer over it.
    if interior.kind is ColorKind.MASS and exterior.kind is ColorKind.MASS:
        raise ColorCombinationError(
            "color_pair_incompatible",
            f"Los acabados «{exterior.name}» y «{interior.name}» son ambos "
            f"colores de masa — una misma barra no lleva dos.",
        )
    for option, other in ((interior, exterior), (exterior, interior)):
        if option.pair_code and other.code != option.pair_code:
            raise ColorCombinationError(
                "color_pair_requires",
                f"El acabado «{option.name}» exige «{other.code}» = "
                f"«{option.pair_code}» en la cara opuesta.",
            )
    return ColorSelection(interior=interior, exterior=exterior)


def apply_color_surcharges(
    selection: ColorSelection,
    result: EngineResult,
    *,
    area_m2: Decimal,
) -> list[ColorSurchargeApplication]:
    """Declared finish surcharges → application rows on the BOM.

    The engine derives the basis from the BOM it already computed — cut
    profile metres, position area or the unit — and carries the declared
    rate. `PCT_OF_MATERIALS` carries a `None` basis: the priced materials
    total exists only at the pricing boundary.
    """
    applications: list[ColorSurchargeApplication] = []
    metres = (
        sum(
            (cut.length_mm * cut.qty for cut in result.profile_cuts),
            start=Decimal("0"),
        )
        / Decimal("1000")
    ).quantize(Q)
    seen: set[str] = set()
    for option, surcharge in selection.surcharges():
        # Bicolor bars keep one identity per code — a duplicated declared
        # option never bills twice.
        if option.code in seen:
            continue
        seen.add(option.code)
        if surcharge.kind == "PER_PROFILE_METER":
            basis: Decimal | None = metres
            unit = "M"
        elif surcharge.kind == "PER_M2":
            basis = area_m2.quantize(Q_AREA)
            unit = "M2"
        elif surcharge.kind == "FIXED_PER_POSITION":
            basis = Decimal("1")
            unit = "POSITION"
        else:  # PCT_OF_MATERIALS
            basis = None
            unit = "MATERIALS_PCT"
        applications.append(
            ColorSurchargeApplication(
                option_code=option.code,
                option_name=option.name,
                kind=surcharge.kind,
                rate=surcharge.amount,
                currency=surcharge.currency,
                label=surcharge.label,
                basis=basis,
                basis_unit=unit,  # type: ignore[arg-type]
            )
        )
    return applications
