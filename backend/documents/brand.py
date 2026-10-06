"""White-label brand color — the fabricator's primary color may appear on
documents, the client portal and client emails only when it survives a
WCAG AA check against paper (4.5:1); anything else falls back to
teal-800 and reports the fallback so Ajustes can warn."""

from __future__ import annotations

import re

BRAND_COLOR_FALLBACK = "#075F5A"

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def effective_brand_color(raw: object) -> tuple[str, bool]:
    """Return (usable_color, passed). `passed` is True only when the
    declared #RRGGBB reaches 4.5:1 against white paper."""
    color = (str(raw or "")).strip()
    if not _HEX.fullmatch(color):
        return BRAND_COLOR_FALLBACK, False
    if _contrast_ratio(_hex_rgb(color), (1.0, 1.0, 1.0)) >= 4.5:
        return color.upper(), True
    return BRAND_COLOR_FALLBACK, False


def _hex_rgb(color: str) -> tuple[float, float, float]:
    return (
        int(color[1:3], 16) / 255,
        int(color[3:5], 16) / 255,
        int(color[5:7], 16) / 255,
    )


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _contrast_ratio(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> float:
    lum_a = 0.2126 * _linear(a[0]) + 0.7152 * _linear(a[1]) + 0.0722 * _linear(a[2])
    lum_b = 0.2126 * _linear(b[0]) + 0.7152 * _linear(b[1]) + 0.0722 * _linear(b[2])
    light, dark = max(lum_a, lum_b), min(lum_a, lum_b)
    return (light + 0.05) / (dark + 0.05)
