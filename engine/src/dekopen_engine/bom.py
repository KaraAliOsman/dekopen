"""Deterministic assembly helpers for the SHOT-03 base bill of materials."""

from __future__ import annotations

from collections.abc import Sequence

from dekopen_engine.models import (
    EngineResult,
    FittingPiece,
    GlassPiece,
    PanelPiece,
    HardwareItem,
    LeafWeight,
    ProfileCut,
    ProfileRole,
    ReinforcementPiece,
)

_PROFILE_ROLE_ORDER = {
    ProfileRole.FRAME: 0,
    ProfileRole.MULLION_V: 1,
    ProfileRole.MULLION_H: 2,
    ProfileRole.SASH: 3,
    ProfileRole.GLAZING_BEAD: 4,
    ProfileRole.INVERSOR: 5,
    ProfileRole.COUPLER: 6,
    ProfileRole.ADDITIONAL: 7,
    ProfileRole.THRESHOLD: 8,
    ProfileRole.CHANNEL: 9,
    ProfileRole.SLIDING_SASH: 10,
    ProfileRole.INTERLOCK: 11,
    ProfileRole.RAIL: 12,
    ProfileRole.DOOR_SASH: 13,
    ProfileRole.FRAME_EXTENSION: 14,
    ProfileRole.SILL: 15,
    ProfileRole.COVER_TRIM: 16,
    ProfileRole.SKIRT: 17,
}


def build_engine_result(
    *,
    profile_cuts: Sequence[ProfileCut],
    reinforcements: Sequence[ReinforcementPiece],
    glasses: Sequence[GlassPiece],
    panels: Sequence[PanelPiece] = (),
    fittings: Sequence[FittingPiece] = (),
    hardware_items: Sequence[HardwareItem] = (),
    leaf_weights: Sequence[LeafWeight] = (),
) -> EngineResult:
    """Copy and stably order BOM categories without recalculating geometry."""

    ordered_profile_cuts = sorted(
        profile_cuts,
        key=lambda cut: _PROFILE_ROLE_ORDER[cut.role],
    )
    ordered_reinforcements = sorted(
        reinforcements,
        key=lambda piece: _PROFILE_ROLE_ORDER[piece.role],
    )
    return EngineResult(
        profile_cuts=ordered_profile_cuts,
        reinforcements=ordered_reinforcements,
        glasses=list(glasses),
        panels=list(panels),
        fittings=list(fittings),
        hardware_items=list(hardware_items),
        leaf_weights=list(leaf_weights),
    )
