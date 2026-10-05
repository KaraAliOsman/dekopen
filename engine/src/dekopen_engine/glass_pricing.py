"""Glass pricing — billable area with product minimum, per-piece
surcharges. Pure functions: the caller injects cost data, the engine
computes. Every line is explicit so the quotation can show where each
peso came from.

Kinds of surcharge (``GlassSurchargeRate`` on the product, declared per
org or global catalog):

- ``TEMPERED``    — automatic when the composition holds a tempered ply
                    (unit M2: per billable m²).
- ``EDGE_POLISH`` — per polished metre. The qty is the summed length of
                    the polished edges declared in the piece's
                    ``glass_options`` (or every declared exposed edge).
- ``DRILL``       — per perforation (unit EA: count declared on the piece).
- ``PALILLAJE``   — georgian-bar grid inside the IGU. Declared by grid
                    columns × rows; priced per crossing (unit CROSS =
                    columns·rows) or per bar metre (unit M =
                    columns·height + rows·width).

``billable_area_m2`` never lets a small pane bill below the product's
declared minimum — the supplier charges the cut, not the square.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from dekopen_engine.glass_composition import GlassComposition
from dekopen_engine.engine_base import EngineModel
from dekopen_engine.models import (
    GlassSurchargeRate,
    GlassSurchargeSelection,
)


_M2 = "M2"
_M = "M"
_EA = "EA"
_CROSS = "CROSS"

SURCHARGE_UNITS = (_M2, _M, _EA, _CROSS)


class GlassPriceLine(EngineModel):
    kind: str
    sku: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    cost: Decimal
    label: str | None = None


def billable_area_m2(exact_area_m2: Decimal, min_area_m2: Decimal | None) -> Decimal:
    """Supplier bills the cut: never below the product's declared minimum."""
    if min_area_m2 is None or min_area_m2 <= 0:
        return exact_area_m2
    return max(exact_area_m2, min_area_m2)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _polished_metres(
    edges: list[str] | list[Literal["top", "right", "bottom", "left"]],
    width_mm: Decimal,
    height_mm: Decimal,
) -> Decimal:
    mm = Decimal("0")
    for edge in edges:
        if edge in ("top", "bottom"):
            mm += width_mm
        elif edge in ("left", "right"):
            mm += height_mm
    return mm / Decimal("1000")


def _palillaje_quantities(
    *,
    columns: int | None,
    rows: int | None,
    count: int | None,
    width_mm: Decimal,
    height_mm: Decimal,
) -> dict[str, Decimal]:
    """Derived palillaje quantities — crossings and bar metres."""
    cols = columns or 0
    rws = rows or 0
    crossings = Decimal(count) if count is not None else Decimal(cols * rws)
    bars_mm = Decimal(cols) * height_mm + Decimal(rws) * width_mm
    return {"CROSS": crossings, "M": bars_mm / Decimal("1000")}


def glass_price_lines(
    *,
    sku: str,
    cost_per_m2: Decimal,
    exact_area_m2: Decimal,
    min_area_m2: Decimal | None,
    surcharges: list[GlassSurchargeRate],
    selections: list[GlassSurchargeSelection] | None,
    composition: GlassComposition | None,
    width_mm: Decimal,
    height_mm: Decimal,
    exposed_edges: list[str] | None = None,
) -> list[GlassPriceLine]:
    """All cost lines for one pane: base m² over the billable area plus a
    line per applicable surcharge. Selection-free kinds (TEMPERED) derive
    from the composition; selection kinds (EDGE_POLISH/DRILL/PALILLAJE)
    need the declared extras on the piece."""
    lines = [
        GlassPriceLine(
            kind="GLASS",
            sku=sku,
            quantity=_q4(billable_area_m2(exact_area_m2, min_area_m2)),
            unit=_M2,
            unit_cost=cost_per_m2,
            cost=_q4(billable_area_m2(exact_area_m2, min_area_m2) * cost_per_m2),
            label=None,
        )
    ]
    chosen = selections or []
    for rate in surcharges:
        qty: Decimal | None = None
        if rate.kind == "TEMPERED":
            if composition is not None and composition.has_tempered:
                qty = billable_area_m2(exact_area_m2, min_area_m2) if rate.unit == _M2 else Decimal("1")
        elif rate.kind == "EDGE_POLISH":
            selection = next(
                (sel for sel in chosen if sel.kind == "EDGE_POLISH"), None
            )
            if selection is not None:
                edges: list[str] = list(selection.edges or []) or list(
                    exposed_edges or []
                )
                qty = _polished_metres(edges, width_mm, height_mm)
        elif rate.kind == "DRILL":
            selection = next(
                (sel for sel in chosen if sel.kind == "DRILL"), None
            )
            if selection is not None and selection.count:
                qty = Decimal(selection.count)
        elif rate.kind == "PALILLAJE":
            selection = next(
                (sel for sel in chosen if sel.kind == "PALILLAJE"), None
            )
            if selection is not None:
                quantities = _palillaje_quantities(
                    columns=selection.columns,
                    rows=selection.rows,
                    count=selection.count,
                    width_mm=width_mm,
                    height_mm=height_mm,
                )
                qty = quantities.get(rate.unit)
        if qty is None or qty <= 0:
            continue
        lines.append(
            GlassPriceLine(
                kind=f"GLASS_{rate.kind}",
                sku=sku,
                quantity=_q4(qty),
                unit=rate.unit,
                unit_cost=rate.amount,
                cost=_q4(qty * rate.amount),
                label=rate.label,
            )
        )
    return lines
