"""Del vano de obra a la medida de fabricación (D07).

The estimator measures the rough opening (vano) — optionally at three
points per axis — and the engine derives the fabrication measure from the
mounting rule selected for the system: in-vano with perimeter clearance,
subframe, over-opening overlap, flush overlap, or an insert into an
existing frame. Every number here is Decimal and deterministic; the
breakdown is evidence ("Vano 1520 - holgura 10 + 10 = 1500"), never prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MM = Decimal

MOUNTING_TYPES = (
    "EN_VANO",        # en vano con holgura perimetral
    "PREMARCO",       # con premarco
    "SOBRE_VANO",     # sobre vano (marco tapa el vano)
    "TRASLAPADO",     # traslapado / solape exterior
    "RENOVACION",     # renovación sobre marco existente
)

WALL_TYPES = ("MASONRY", "CONCRETE", "PARTITION", "WOOD")

SIDE_ORDER = ("top", "right", "bottom", "left")

SIDE_LABELS = {
    "top": "superior",
    "right": "derecho",
    "bottom": "inferior",
    "left": "izquierdo",
}


class VanoError(ValueError):
    """Malformed vano record or mounting rule authority."""


def _mm(value: object, field_name: str) -> Decimal:
    try:
        return MM(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise VanoError(f"invalid_{field_name}") from error


@dataclass(frozen=True)
class MountingRule:
    """One mounting type for one system: signed per-side mm added to the
    vano measure, plus the declared ensanches and fixing accessories the
    installation needs. `sides` values are signed adds: -10.00 takes 10 mm
    off the vano per side, +20.00 adds overlap."""

    code: str
    label: str
    sides: dict[str, Decimal]
    side_labels: dict[str, str]
    frame_extensions: tuple[dict[str, object], ...] = ()
    fixings: tuple[dict[str, object], ...] = ()
    wall_notes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in MOUNTING_TYPES:
            raise VanoError("invalid_mounting_type")
        missing = [side for side in SIDE_ORDER if side not in self.sides]
        if missing:
            raise VanoError("mounting_rule_missing_side")


@dataclass(frozen=True)
class VanoInput:
    """The measured opening record. Points are the 1–3 readings per axis;
    the minimum rules the fabrication measure (never fabricate bigger than
    the tightest reading)."""

    width_points_mm: tuple[Decimal, ...]
    height_points_mm: tuple[Decimal, ...]
    wall_type: str | None = None
    square_mm: Decimal | None = None
    plumb_mm: Decimal | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.width_points_mm) <= 3:
            raise VanoError("vano_width_points_out_of_range")
        if not 1 <= len(self.height_points_mm) <= 3:
            raise VanoError("vano_height_points_out_of_range")
        if self.wall_type is not None and self.wall_type not in WALL_TYPES:
            raise VanoError("invalid_wall_type")


@dataclass(frozen=True)
class FabricationLock:
    """A manually pinned fabrication measure. The pin is evidence, not a
    silent override: the resolution still reports the derived value and the
    divergence as a warning."""

    width_mm: Decimal
    height_mm: Decimal


@dataclass(frozen=True)
class BreakdownItem:
    """One line of the desglose: which side, what it is called, how many mm
    it adds (negative = deducted from the vano)."""

    side: str
    label: str
    mm: Decimal


@dataclass(frozen=True)
class VanoWarning:
    code: str
    message: str


@dataclass(frozen=True)
class VanoResolution:
    """What the vano + mounting rule resolve to.

    fabrication_source: DERIVED (from vano+rule), MANUAL_LOCK (pinned),
    DECLARED (no vano record — the product measure stands as declared).
    `used_width_mm`/`used_height_mm` are the vano dims the engine used —
    the smallest measured point per axis, or the position dims when no
    vano was recorded; `coherent` says the position's own dims agree with
    the resolved measure within tolerance."""

    vano_width_mm: Decimal | None
    vano_height_mm: Decimal | None
    width_spread_mm: Decimal
    height_spread_mm: Decimal
    fabrication_width_mm: Decimal
    fabrication_height_mm: Decimal
    fabrication_source: str
    used_width_mm: Decimal
    used_height_mm: Decimal
    coherent: bool
    breakdown: tuple[BreakdownItem, ...]
    warnings: tuple[VanoWarning, ...]


def mounting_rule_from_json(raw: object, *, code_hint: str | None = None) -> MountingRule:
    """Parse a mounting_rules.authority JSONB body. The table row's `code`
    and `label` columns carry the identity; the authority carries the math."""
    if not isinstance(raw, dict):
        raise VanoError("invalid_mounting_rule")
    code = code_hint or raw.get("code")
    sides_raw = raw.get("sides")
    if not isinstance(sides_raw, dict):
        raise VanoError("mounting_rule_missing_sides")
    sides: dict[str, Decimal] = {}
    side_labels: dict[str, str] = {}
    for side in SIDE_ORDER:
        entry = sides_raw.get(side)
        if entry is None:
            raise VanoError("mounting_rule_missing_side")
        if isinstance(entry, dict):
            sides[side] = _mm(entry.get("mm"), f"{side}_mm")
            label = entry.get("label")
            side_labels[side] = label if isinstance(label, str) and label.strip() else _default_side_label(sides[side], side)
        else:
            sides[side] = _mm(entry, f"{side}_mm")
            side_labels[side] = _default_side_label(sides[side], side)
    label = raw.get("label")
    frame_extensions = raw.get("frame_extensions") or ()
    fixings = raw.get("fixings") or ()
    wall_notes = raw.get("wall_notes") or {}
    if not isinstance(wall_notes, dict):
        raise VanoError("invalid_wall_notes")
    return MountingRule(
        code=str(code) if code else "",
        label=str(label) if label else str(code or ""),
        sides=sides,
        side_labels=side_labels,
        frame_extensions=tuple(frame_extensions),
        fixings=tuple(fixings),
        wall_notes={str(k): str(v) for k, v in wall_notes.items()},
    )


def _default_side_label(mm: Decimal, side: str) -> str:
    noun = "Solape" if mm > 0 else "Holgura" if mm < 0 else "Ajuste"
    return f"{noun} {SIDE_LABELS[side]}"


def vano_from_json(raw: object) -> VanoInput:
    if not isinstance(raw, dict):
        raise VanoError("invalid_vano_record")
    width_points = _points(raw.get("width_points_mm"), "width_points_mm")
    height_points = _points(raw.get("height_points_mm"), "height_points_mm")
    wall_type = raw.get("wall_type")
    return VanoInput(
        width_points_mm=width_points,
        height_points_mm=height_points,
        wall_type=str(wall_type) if wall_type else None,
        square_mm=_mm(raw["square_mm"], "square_mm") if raw.get("square_mm") is not None else None,
        plumb_mm=_mm(raw["plumb_mm"], "plumb_mm") if raw.get("plumb_mm") is not None else None,
        notes=raw.get("notes") if isinstance(raw.get("notes"), str) else None,
    )


def _points(raw: object, field_name: str) -> tuple[Decimal, ...]:
    if not isinstance(raw, list) or not raw:
        raise VanoError(f"invalid_{field_name}")
    points = tuple(_mm(item, field_name) for item in raw)
    if any(point <= 0 for point in points):
        raise VanoError(f"{field_name}_not_positive")
    return points


def resolve_fabrication(
    *,
    vano: VanoInput | None,
    rule: MountingRule | None,
    lock: FabricationLock | None = None,
    position_width_mm: Decimal,
    position_height_mm: Decimal,
    spread_tolerance_mm: Decimal = MM("10.00"),
    coherence_tolerance_mm: Decimal = MM("10.00"),
) -> VanoResolution:
    """Resolve the fabrication measure and judge the position dims against it.

    `position_*_mm` are the dims the product is actually being fabricated at
    (the position's nominal dims); `used_*_mm` in the resolution reports the
    vano measure the engine used — the smallest of the measured points, or
    the position dims themselves when nothing was measured.

    vano=None + rule=None is the declared-measure case: nothing recorded,
    the position's own dims stand. A vano without a rule cannot resolve —
    that is a VanoError, not a silent pass."""
    warnings: list[VanoWarning] = []
    breakdown: list[BreakdownItem] = []

    if vano is None:
        if rule is not None:
            raise VanoError("mounting_rule_without_vano")
        if lock is None:
            return VanoResolution(
                vano_width_mm=None,
                vano_height_mm=None,
                width_spread_mm=MM("0"),
                height_spread_mm=MM("0"),
                fabrication_width_mm=position_width_mm,
                fabrication_height_mm=position_height_mm,
                fabrication_source="DECLARED",
                used_width_mm=position_width_mm,
                used_height_mm=position_height_mm,
                coherent=True,
                breakdown=(),
                warnings=(),
            )
        fab_w, fab_h = lock.width_mm, lock.height_mm
        coherent = _within(fab_w, position_width_mm, coherence_tolerance_mm) and _within(
            fab_h, position_height_mm, coherence_tolerance_mm
        )
        if not coherent:
            warnings.append(VanoWarning(
                "FAB_USED_DIVERGES",
                "El producto no se está fabricando con la medida fijada manualmente.",
            ))
        return VanoResolution(
            vano_width_mm=None,
            vano_height_mm=None,
            width_spread_mm=MM("0"),
            height_spread_mm=MM("0"),
            fabrication_width_mm=fab_w,
            fabrication_height_mm=fab_h,
            fabrication_source="MANUAL_LOCK",
            used_width_mm=position_width_mm,
            used_height_mm=position_height_mm,
            coherent=coherent,
            breakdown=(),
            warnings=tuple(warnings),
        )

    if rule is None:
        raise VanoError("vano_without_mounting_rule")

    vano_w = min(vano.width_points_mm)
    vano_h = min(vano.height_points_mm)
    spread_w = max(vano.width_points_mm) - vano_w
    spread_h = max(vano.height_points_mm) - vano_h
    if spread_w > spread_tolerance_mm:
        warnings.append(VanoWarning(
            "VANO_WIDTH_SPREAD",
            "El ancho del vano varía más que la tolerancia; se usa la medida menor.",
        ))
    if spread_h > spread_tolerance_mm:
        warnings.append(VanoWarning(
            "VANO_HEIGHT_SPREAD",
            "El alto del vano varía más que la tolerancia; se usa la medida menor.",
        ))

    derived_w = vano_w + rule.sides["left"] + rule.sides["right"]
    derived_h = vano_h + rule.sides["top"] + rule.sides["bottom"]
    for side in SIDE_ORDER:
        mm = rule.sides[side]
        if mm != 0:
            breakdown.append(BreakdownItem(side=side, label=rule.side_labels[side], mm=mm))

    wall_note = rule.wall_notes.get(vano.wall_type or "")
    if wall_note:
        warnings.append(VanoWarning("WALL_NOTE", wall_note))

    if derived_w <= 0 or derived_h <= 0:
        warnings.append(VanoWarning(
            "FAB_NONPOSITIVE",
            "La regla de montaje deja la medida de fabricación en cero o menos; revisa la holgura.",
        ))

    if lock is not None:
        source = "MANUAL_LOCK"
        fab_w, fab_h = lock.width_mm, lock.height_mm
        coherent = True
        if not (_within(fab_w, derived_w, coherence_tolerance_mm) and _within(
            fab_h, derived_h, coherence_tolerance_mm
        )):
            coherent = False
            warnings.append(VanoWarning(
                "FAB_LOCK_DIVERGES",
                "La medida fijada no es coherente con el vano medido y la regla de montaje.",
            ))
        if not (_within(fab_w, position_width_mm, coherence_tolerance_mm) and _within(
            fab_h, position_height_mm, coherence_tolerance_mm
        )):
            coherent = False
            warnings.append(VanoWarning(
                "FAB_USED_DIVERGES",
                "El producto no se está fabricando con la medida fijada manualmente.",
            ))
    else:
        source = "DERIVED"
        fab_w, fab_h = derived_w, derived_h
        coherent = _within(position_width_mm, derived_w, coherence_tolerance_mm) and _within(
            position_height_mm, derived_h, coherence_tolerance_mm
        )
        if not coherent:
            warnings.append(VanoWarning(
                "FAB_USED_DIVERGES",
                "La medida de fabricación del producto no es coherente con el vano medido.",
            ))

    return VanoResolution(
        vano_width_mm=vano_w,
        vano_height_mm=vano_h,
        width_spread_mm=spread_w,
        height_spread_mm=spread_h,
        fabrication_width_mm=fab_w,
        fabrication_height_mm=fab_h,
        fabrication_source=source,
        used_width_mm=vano_w,
        used_height_mm=vano_h,
        coherent=coherent,
        breakdown=tuple(breakdown),
        warnings=tuple(warnings),
    )


def _within(actual: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(actual - expected) <= tolerance
