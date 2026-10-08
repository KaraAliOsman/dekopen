"""Structured glass composition — the single source of truth for what a pane IS.

A composition is an ordered stack exterior → interior of laminae and chambers:

- ``GlassLamina`` — one or more glass plies (``panes``), an optional
  interlayer (laminated glass declares PVB 0,38 / PVB 0,76 / acoustic PVB),
  a tint, a heat treatment (tempered / heat-strengthened) and a coating
  (low-e, solar control, reflective, mirror, satin, printed) with the face
  it lives on (cN, counting surfaces from the exterior).
- ``GlassChamber`` — a hermetic cavity: width, gas (air/argon), spacer kind
  (aluminium / warm edge) and sealant.

``parse_glass_notation`` accepts the workshop notations in the wild
("4-16-4", "4 / 12 aire / 4", "5 / 12 Ar / 4 Low-E (c3)", "3+3 PVB 0,38",
"4+4 / 16 / 6 templado", "DVH 5-12-5", "44.2" laminate shorthand, comma
decimals, any case) and ``format_glass_notation`` writes the canonical
"4 / 12 aire / 4" ida-vuelta form. Parsing never raises: an unreadable
string returns ``None`` and the caller surfaces UNKNOWN — an unparseable
spec must never fabricate a composition (or a weight) silently.

All derived numbers come from the composition, nowhere else:

- ``net_thickness_mm``  — glass mass only (plies, no PVB, no chambers);
- ``total_thickness_mm`` — the glazing-package thickness incl. interlayers
  and chambers: this is the key the glazing-bead matrix indexes;
- ``composition_weight_kg_m2`` — glass at 2.50 kg/m²·mm plus PVB at
  1.07 kg/m²·mm per interlayer millimetre.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from enum import Enum

from dekopen_engine.engine_base import EngineModel


# PVB film density ≈ 1.07 g/cm³ → kg per m² per interlayer millimetre.
PVB_WEIGHT_FACTOR_KG_M2_PER_MM = Decimal("1.07")
GLASS_KG_M2_PER_MM = Decimal("2.50")


class LaminaTint(str, Enum):
    CLEAR = "CLEAR"
    BRONZE = "BRONZE"
    GREY = "GREY"
    GREEN = "GREEN"


class GlassTreatment(str, Enum):
    TEMPERED = "TEMPERED"
    HEAT_STRENGTHENED = "HEAT_STRENGTHENED"


class GlassCoating(str, Enum):
    LOW_E = "LOW_E"
    SOLAR_CONTROL = "SOLAR_CONTROL"
    REFLECTIVE = "REFLECTIVE"
    MIRROR = "MIRROR"
    SATIN = "SATIN"
    PRINTED = "PRINTED"


class InterlayerKind(str, Enum):
    PVB_038 = "PVB_038"
    PVB_076 = "PVB_076"
    PVB_152 = "PVB_152"
    PVB_ACOUSTIC = "PVB_ACOUSTIC"


INTERLAYER_THICKNESS_MM = {
    InterlayerKind.PVB_038: Decimal("0.38"),
    InterlayerKind.PVB_076: Decimal("0.76"),
    InterlayerKind.PVB_152: Decimal("1.52"),
    InterlayerKind.PVB_ACOUSTIC: Decimal("0.76"),
}

_INTERLAYER_NOTATION = {
    InterlayerKind.PVB_038: "PVB 0,38",
    InterlayerKind.PVB_076: "PVB 0,76",
    InterlayerKind.PVB_152: "PVB 1,52",
    InterlayerKind.PVB_ACOUSTIC: "PVB acústico",
}


class ChamberGas(str, Enum):
    AIR = "AIR"
    ARGON = "ARGON"


class SpacerKind(str, Enum):
    ALUMINIUM = "ALUMINIUM"
    WARM_EDGE = "WARM_EDGE"


class SealantKind(str, Enum):
    PIB_BUTYL = "PIB_BUTYL"
    POLYSULFIDE = "POLYSULFIDE"
    SILICONE = "SILICONE"
    POLYURETHANE = "POLYURETHANE"


class GlassLamina(EngineModel):
    """One glazing ply group: identical plies plus the interlayer bonding
    them. A single pane is ``panes=[4]``; a laminate is ``panes=[3,3]``
    with ``interlayer`` set. Properties (tint, treatment, coating) apply to
    every ply of the lamina."""

    panes: list[Decimal]
    interlayer: InterlayerKind | None = None
    tint: LaminaTint = LaminaTint.CLEAR
    treatment: GlassTreatment | None = None
    coating: GlassCoating | None = None
    # Glass-face number the coating lives on, counted from the exterior
    # surface (1 = outer face of the outer pane). None when uncoated or the
    # declaration lacks a face.
    coating_face: int | None = None
    # Supplier article for the lamina itself (catalog SKU of the glass sheet),
    # not the composed product SKU.
    supplier_sku: str | None = None

    def model_post_init(self, __context: object) -> None:
        if not self.panes:
            raise ValueError("a lamina requires at least one ply")
        if self.coating_face is not None and self.coating_face < 1:
            raise ValueError("coating face counts from 1")
        # The face's upper bound is a composition concern — it is checked
        # there against the lamina's own face pair.

    @property
    def glass_thickness_mm(self) -> Decimal:
        return sum(self.panes, Decimal("0"))

    @property
    def interlayer_thickness_mm(self) -> Decimal:
        if self.interlayer is None or len(self.panes) < 2:
            return Decimal("0")
        return INTERLAYER_THICKNESS_MM[self.interlayer] * Decimal(
            len(self.panes) - 1
        )

    @property
    def total_thickness_mm(self) -> Decimal:
        return self.glass_thickness_mm + self.interlayer_thickness_mm

    @property
    def is_laminate(self) -> bool:
        return len(self.panes) > 1


class GlassChamber(EngineModel):
    width_mm: Decimal
    gas: ChamberGas = ChamberGas.AIR
    spacer: SpacerKind = SpacerKind.ALUMINIUM
    sealant: SealantKind | None = None


class GlassComposition(EngineModel):
    """The ordered exterior → interior layer stack. Validation happens in
    the constructor: strictly alternating, first and last are laminae, at
    least one lamina."""

    layers: list[GlassLamina | GlassChamber]

    def model_post_init(self, __context: object) -> None:
        if not self.layers:
            raise ValueError("glass composition requires at least one lamina")
        if not isinstance(self.layers[0], GlassLamina) or not isinstance(
            self.layers[-1], GlassLamina
        ):
            raise ValueError("glass composition must start and end with a lamina")
        for index, layer in enumerate(self.layers):
            expected = GlassLamina if index % 2 == 0 else GlassChamber
            if not isinstance(layer, expected):
                raise ValueError(
                    "glass composition must alternate lamina/chamber "
                    "exterior to interior"
                )
        for index, lamina in enumerate(self.laminae):
            # Each lamina owns exactly two faces: lamina 0 → faces 1-2,
            # lamina 1 → 3-4, … (interlayer faces are never exposed).
            if lamina.coating_face is not None and not (
                2 * index + 1 <= lamina.coating_face <= 2 * index + 2
            ):
                raise ValueError(
                    f"coating face {lamina.coating_face} does not belong to "
                    f"lamina {index + 1} (faces {2 * index + 1}-"
                    f"{2 * index + 2})"
                )

    @property
    def laminae(self) -> list[GlassLamina]:
        return [
            layer for layer in self.layers if isinstance(layer, GlassLamina)
        ]

    @property
    def chambers(self) -> list[GlassChamber]:
        return [
            layer for layer in self.layers if isinstance(layer, GlassChamber)
        ]

    @property
    def is_igu(self) -> bool:
        return len(self.chambers) > 0

    @property
    def has_laminate(self) -> bool:
        return any(lamina.is_laminate for lamina in self.laminae)

    @property
    def has_tempered(self) -> bool:
        return any(
            lamina.treatment is GlassTreatment.TEMPERED
            for lamina in self.laminae
        )

    def net_thickness_mm(self) -> Decimal:
        """Glass mass only — plies; interlayers and chambers carry no glass."""
        return sum(
            (lamina.glass_thickness_mm for lamina in self.laminae),
            Decimal("0"),
        )

    def total_thickness_mm(self) -> Decimal:
        """Full glazing-package thickness — the glazing-bead key."""
        total = Decimal("0")
        for layer in self.layers:
            if isinstance(layer, GlassLamina):
                total += layer.total_thickness_mm
            else:
                total += layer.width_mm
        return total

    def weight_kg_m2(self) -> Decimal:
        """kg per m² — glass at 2.50 kg/m²·mm plus each PVB interlayer at
        1.07 kg/m²·mm (PVB density ≈ 1.07 g/cm³)."""
        glass = sum(
            (lamina.glass_thickness_mm for lamina in self.laminae),
            Decimal("0"),
        ) * GLASS_KG_M2_PER_MM
        pvb = sum(
            (lamina.interlayer_thickness_mm for lamina in self.laminae),
            Decimal("0"),
        ) * PVB_WEIGHT_FACTOR_KG_M2_PER_MM
        return glass + pvb


# --------------------------------------------------------------------------
# Notation parser
# --------------------------------------------------------------------------

_ACCENT = str.maketrans("áéíóúü", "aeiouu")


def _normalize_notation(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).lower().translate(_ACCENT)
    # Protect hyphenated keywords before '-' becomes a layer separator.
    text = re.sub(r"low[-\s]?e\b", "lowe", text)
    text = re.sub(r"bajo[-\s]?emisivo\b", "lowe", text)
    text = re.sub(r"warm[-\s]?edge\b", "warm edge", text)
    text = re.sub(r"borde[-\s]?caliente\b", "borde caliente", text)
    text = re.sub(r"control[-\s]?solar\b", "control solar", text)
    text = re.sub(r"termo[-\s]?endurecido\b", "termoendurecido", text)
    text = re.sub(r"heat[-\s]?strengthened\b", "termoendurecido", text)
    # `(c 3)`, `cara 3`, `#3` all denote the coating face → `(c3)`.
    text = re.sub(r"\(\s*c(?:ara)?\s*(\d)\s*\)", r"(c\1)", text)
    text = re.sub(r"\bcara\s*(\d)\b", r"(c\1)", text)
    text = re.sub(r"#\s*(\d)\b", r"(c\1)", text)
    # Marketing prefixes carry no data.
    text = re.sub(
        r"^\s*(?:dvh|thd|termopanel|thermopanel|doble\s+vidrio\s+hermetico|"
        r"vidrio\s+hermetico|hermetico|h\.)\s*[:=-]?\s*",
        "",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


# A '-' only separates layers when it sits between digits (or a ')'),
# never inside a word: "4-16-4" splits, "low-e" does not.
_LAYER_SPLIT_RE = re.compile(r"/|(?<=[\d)])\s*-\s*(?=\d)")
_LAMINATE_SHORTHAND_RE = re.compile(r"^(\d)(\d)[.,](\d)$")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_COATING_FACE_RE = re.compile(r"\(c(\d)\)")

_TINT_TOKENS = {
    "bronce": LaminaTint.BRONZE,
    "bronze": LaminaTint.BRONZE,
    "gris": LaminaTint.GREY,
    "grey": LaminaTint.GREY,
    "gray": LaminaTint.GREY,
    "verde": LaminaTint.GREEN,
    "green": LaminaTint.GREEN,
}
_CLEAR_TOKENS = {
    "float", "flotado", "incoloro", "natural", "crudo", "cristal",
    "vidrio", "claro", "clear", "monolito", "monolitico", "comun",
    "estandar", "std",
}
_TREATMENT_TOKENS = {
    "templado": GlassTreatment.TEMPERED,
    "tempered": GlassTreatment.TEMPERED,
    "temp": GlassTreatment.TEMPERED,
    "termoendurecido": GlassTreatment.HEAT_STRENGTHENED,
    "termoendurecido.": GlassTreatment.HEAT_STRENGTHENED,
    "hs": GlassTreatment.HEAT_STRENGTHENED,
    "hst": GlassTreatment.HEAT_STRENGTHENED,
}
_COATING_TOKENS = {
    "lowe": GlassCoating.LOW_E,
    "low-e": GlassCoating.LOW_E,
    "emisivo": GlassCoating.LOW_E,
    "bajoe": GlassCoating.LOW_E,
    "control": GlassCoating.SOLAR_CONTROL,
    "solar": GlassCoating.SOLAR_CONTROL,
    "reflex": GlassCoating.REFLECTIVE,
    "reflectivo": GlassCoating.REFLECTIVE,
    "reflective": GlassCoating.REFLECTIVE,
    "espejo": GlassCoating.MIRROR,
    "mirror": GlassCoating.MIRROR,
    "espejado": GlassCoating.MIRROR,
    "satin": GlassCoating.SATIN,
    "satinado": GlassCoating.SATIN,
    "satine": GlassCoating.SATIN,
    "arenado": GlassCoating.SATIN,
    "esmerilado": GlassCoating.SATIN,
    "frosted": GlassCoating.SATIN,
    "impreso": GlassCoating.PRINTED,
    "printed": GlassCoating.PRINTED,
    "serigrafiado": GlassCoating.PRINTED,
    "serigrafia": GlassCoating.PRINTED,
}
_GAS_TOKENS = {
    "aire": ChamberGas.AIR,
    "air": ChamberGas.AIR,
    "ar": ChamberGas.ARGON,
    "ar.": ChamberGas.ARGON,
    "argon": ChamberGas.ARGON,
    "argon90": ChamberGas.ARGON,
    "ar90": ChamberGas.ARGON,
}
_SPACER_TOKENS = {
    "al": SpacerKind.ALUMINIUM,
    "aluminio": SpacerKind.ALUMINIUM,
    "aluminium": SpacerKind.ALUMINIUM,
    "bc": SpacerKind.WARM_EDGE,
    "we": SpacerKind.WARM_EDGE,
    "termoplastico": SpacerKind.WARM_EDGE,
    "termoplastica": SpacerKind.WARM_EDGE,
    "borde": SpacerKind.WARM_EDGE,
    "caliente": SpacerKind.WARM_EDGE,
    "warm": SpacerKind.WARM_EDGE,
    "edge": SpacerKind.WARM_EDGE,
    "hibrido": SpacerKind.WARM_EDGE,
}
_SEALANT_TOKENS = {
    "butilo": SealantKind.PIB_BUTYL,
    "pib": SealantKind.PIB_BUTYL,
    "tiokol": SealantKind.POLYSULFIDE,
    "polisulfuro": SealantKind.POLYSULFIDE,
    "silicona": SealantKind.SILICONE,
    "poliuretano": SealantKind.POLYURETHANE,
}
_LAMINATE_TOKENS = {"lam", "laminado", "laminated", "laminado."}
# Interlayer index in the NN.N laminate shorthand (industry notation:
# 33.1 = 3+3 PVB 0.38, 44.2 = 4+4 PVB 0.76, 44.4 = 4+4 PVB 1.52).
_LAMINATE_INDEX_INTERLAYER = {
    "1": InterlayerKind.PVB_038,
    "2": InterlayerKind.PVB_076,
    "4": InterlayerKind.PVB_152,
}
_PVB_EXPLICIT_RE = re.compile(r"pvb\s*(?:de\s*)?(\d+[.,]\d+)")


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _interlayer_from_number(text: str) -> InterlayerKind | None:
    value = _decimal(text)
    if value is None:
        return None
    for kind, thickness in INTERLAYER_THICKNESS_MM.items():
        if thickness == value:
            return kind
    if value == Decimal("1.52"):
        return InterlayerKind.PVB_152
    return None


def _parse_lamina(token: str) -> GlassLamina | None:
    """One layer token → lamina: thickness plies, laminate shorthand,
    interlayer declaration, tint/treatment/coating annotations."""
    text = token.strip()
    coating_face = None
    face_match = _COATING_FACE_RE.search(text)
    if face_match:
        coating_face = int(face_match.group(1))
        text = text[: face_match.start()] + text[face_match.end():]

    words = [
        word
        for word in re.split(r"[\s()]+", text)
        if word and word != ","
    ]
    numbers: list[str] = []
    # A number word already consumed as the PVB thickness ("PVB 0,38")
    # must not trip the "stray bare number" check.
    pvb_consumed: list[str] = []
    panes: list[Decimal] = []
    interlayer: InterlayerKind | None = None
    tint = LaminaTint.CLEAR
    treatment: GlassTreatment | None = None
    coating: GlassCoating | None = None
    laminate_hint = False
    saw_gas = False
    saw_spacer = False
    i = 0
    while i < len(words):
        stripped = words[i].rstrip(",;")
        lowered = stripped.rstrip(".")
        # `4+4` / `3+3+3` ply runs: a word of '+'-joined numbers. The
        # last ply may carry the interlayer index shorthand — "3+3,1" is
        # 3+3 with one PVB film (0,38), not a 3.1 mm pane.
        if "+" in stripped and all(
            _NUMBER_RE.fullmatch(part) for part in stripped.split("+")
        ):
            parts = stripped.split("+")
            last = parts[-1]
            suffix_match = re.fullmatch(r"(\d+)[.,](\d)", last)
            if len(parts) > 1 and suffix_match and (
                suffix_match.group(2) in _LAMINATE_INDEX_INTERLAYER
            ):
                parts[-1] = suffix_match.group(1)
                interlayer = _LAMINATE_INDEX_INTERLAYER[
                    suffix_match.group(2)
                ]
            panes = [
                _decimal(part) or Decimal("0")
                for part in parts
            ]
            laminate_hint = laminate_hint or len(panes) > 1
            i += 1
            continue
        shorthand = _LAMINATE_SHORTHAND_RE.fullmatch(stripped)
        if shorthand:
            panes = [
                Decimal(shorthand.group(1)),
                Decimal(shorthand.group(2)),
            ]
            interlayer = _LAMINATE_INDEX_INTERLAYER.get(shorthand.group(3))
            laminate_hint = True
            i += 1
            continue
        if lowered.startswith("pvb"):
            explicit = _PVB_EXPLICIT_RE.search(token)
            if explicit:
                interlayer = _interlayer_from_number(explicit.group(1))
                pvb_consumed.append(explicit.group(1))
            else:
                interlayer = InterlayerKind.PVB_038
            i += 1
            continue
        if _NUMBER_RE.fullmatch(stripped):
            if stripped in pvb_consumed:
                pvb_consumed.remove(stripped)
            else:
                numbers.append(stripped)
            i += 1
            continue
        if lowered in ("acustico", "acoustic", "ac"):
            interlayer = InterlayerKind.PVB_ACOUSTIC
            i += 1
            continue
        if lowered in _LAMINATE_TOKENS:
            laminate_hint = True
            i += 1
            continue
        if lowered in _TINT_TOKENS:
            tint = _TINT_TOKENS[lowered]
            i += 1
            continue
        if lowered in _CLEAR_TOKENS:
            i += 1
            continue
        if lowered in _TREATMENT_TOKENS:
            treatment = _TREATMENT_TOKENS[lowered]
            i += 1
            continue
        if lowered in _COATING_TOKENS:
            coating = _COATING_TOKENS[lowered]
            i += 1
            continue
        if lowered in _GAS_TOKENS:
            saw_gas = True
            i += 1
            continue
        if lowered in _SPACER_TOKENS:
            saw_spacer = True
            i += 1
            continue
        # Unknown word in a lamina slot → the token is not a clean lamina.
        return None
    if not panes:
        if len(numbers) == 1:
            panes = [_decimal(numbers[0]) or Decimal("0")]
        else:
            return None
    elif numbers:
        # Extra bare numbers beyond the ply run are not lamina data.
        return None
    if saw_gas or saw_spacer:
        # A lamina never carries gas/spacer words — the token was a chamber.
        return None
    if laminate_hint and len(panes) == 1:
        # "6 laminado" names the laminate by its total build — the only
        # honest reading is two equal plies (3+3). An odd/undersized total
        # cannot split → UNKNOWN, never a guessed stack.
        pane = panes[0]
        half = pane / Decimal("2")
        if pane >= Decimal("4") and half == half.to_integral_value():
            panes = [half, half]
            laminate_hint = True
        else:
            return None
    if laminate_hint and len(panes) > 1 and interlayer is None:
        interlayer = InterlayerKind.PVB_038
    if coating_face is not None and coating is None:
        coating = GlassCoating.LOW_E
    if any(pane <= 0 or pane > Decimal("25") for pane in panes):
        return None
    return GlassLamina(
        panes=panes,
        interlayer=interlayer if len(panes) > 1 else None,
        tint=tint,
        treatment=treatment,
        coating=coating,
        coating_face=coating_face,
    )


def _parse_chamber(token: str) -> GlassChamber | None:
    text = token.strip()
    width: Decimal | None = None
    gas = ChamberGas.AIR
    spacer = SpacerKind.ALUMINIUM
    sealant: SealantKind | None = None
    for word in re.split(r"\s+", text):
        lowered = word.rstrip(",;")
        if not lowered:
            continue
        if _NUMBER_RE.fullmatch(lowered):
            if width is not None:
                return None
            width = _decimal(lowered)
            continue
        key = lowered.rstrip(".")
        if key in _GAS_TOKENS or lowered in _GAS_TOKENS:
            gas = _GAS_TOKENS.get(key) or _GAS_TOKENS[lowered]
            continue
        if lowered in ("sellante", "sellador"):
            continue
        if key in _SPACER_TOKENS:
            spacer = _SPACER_TOKENS[key]
            continue
        if lowered == "edge" or key == "edge":
            spacer = SpacerKind.WARM_EDGE
            continue
        if key in _SEALANT_TOKENS:
            sealant = _SEALANT_TOKENS[key]
            continue
        return None
    if width is None or width <= 0 or width > Decimal("60"):
        return None
    return GlassChamber(
        width_mm=width, gas=gas, spacer=spacer, sealant=sealant
    )


def _parse_stack(text: str) -> GlassComposition | None:
    tokens = [
        token.strip() for token in _LAYER_SPLIT_RE.split(text)
        if token.strip()
    ]
    if not tokens:
        return None

    layers: list[GlassLamina | GlassChamber] = []
    expect_lamina = True
    for token in tokens:
        if expect_lamina:
            lamina = _parse_lamina(token)
            if lamina is None:
                return None
            layers.append(lamina)
            expect_lamina = False
            continue
        chamber = _parse_chamber(token)
        if chamber is not None:
            layers.append(chamber)
            expect_lamina = True
            continue
        # A lamina sitting in a chamber slot means the notation is not
        # alternating — reject instead of guessing.
        return None
    if expect_lamina:
        # Odd token count ending mid-stack ("4 / 12") is not a product.
        return None
    try:
        return GlassComposition(layers=layers)
    except ValueError:
        return None


_TRAILING_GAS_RE = re.compile(r"\s+(aire|air|ar\.?|argon|argon90|ar90)\s*$")


def parse_glass_notation(raw: str | None) -> GlassComposition | None:
    """Workshop notation → ordered exterior→interior composition.

    Returns ``None`` for anything unreadable: the caller reports UNKNOWN
    instead of inheriting a fabricated composition. Accepts '/', '-'
    separators, '+' ply runs, NN.N laminate shorthand, gas/spacer/sealant
    words, coating faces "(cN)", comma decimals and any case."""
    if raw is None:
        return None
    text = _normalize_notation(raw)
    if not text:
        return None
    composition = _parse_stack(text)
    if composition is not None:
        return composition
    # "DVH 5-12-5 argon" carries the gas as a whole-composition suffix:
    # strip it, reparse, and apply it to every chamber.
    trailing_gas = _TRAILING_GAS_RE.search(text)
    if trailing_gas:
        stripped = text[: trailing_gas.start()].strip()
        composition = _parse_stack(stripped)
        if composition is None or not composition.chambers:
            return None
        gas = _GAS_TOKENS[trailing_gas.group(1).rstrip(".")]
        try:
            return GlassComposition(
                layers=[
                    layer
                    if isinstance(layer, GlassLamina)
                    else GlassChamber(
                        width_mm=layer.width_mm,
                        gas=gas,
                        spacer=layer.spacer,
                        sealant=layer.sealant,
                    )
                    for layer in composition.layers
                ]
            )
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------
# Canonical formatter
# --------------------------------------------------------------------------

def _fmt_mm(value: Decimal) -> str:
    """Canonical es-CL mm: integers bare, fractions with comma."""
    if value == value.to_integral_value():
        return str(int(value))
    return str(value.normalize()).replace(".", ",")


def _format_lamina(lamina: GlassLamina) -> str:
    base = "+".join(_fmt_mm(pane) for pane in lamina.panes)
    if len(lamina.panes) > 1 and lamina.interlayer is not None:
        base = f"{base} {_INTERLAYER_NOTATION[lamina.interlayer]}"
    if lamina.tint is not LaminaTint.CLEAR:
        base += {
            LaminaTint.BRONZE: " bronce",
            LaminaTint.GREY: " gris",
            LaminaTint.GREEN: " verde",
            LaminaTint.CLEAR: "",
        }[lamina.tint]
    if lamina.treatment is GlassTreatment.TEMPERED:
        base += " templado"
    elif lamina.treatment is GlassTreatment.HEAT_STRENGTHENED:
        base += " termoendurecido"
    if lamina.coating is not None:
        base += {
            GlassCoating.LOW_E: " Low-E",
            GlassCoating.SOLAR_CONTROL: " control solar",
            GlassCoating.REFLECTIVE: " reflectivo",
            GlassCoating.MIRROR: " espejo",
            GlassCoating.SATIN: " satinado",
            GlassCoating.PRINTED: " impreso",
        }[lamina.coating]
        if lamina.coating_face is not None:
            base += f" (c{lamina.coating_face})"
    return base


def _format_chamber(chamber: GlassChamber) -> str:
    gas = "Ar" if chamber.gas is ChamberGas.ARGON else "aire"
    spacer = " BC" if chamber.spacer is SpacerKind.WARM_EDGE else ""
    sealant = (
        f" sellante {_SEALANT_NOTATION[chamber.sealant]}"
        if chamber.sealant is not None
        else ""
    )
    return f"{_fmt_mm(chamber.width_mm)} {gas}{spacer}{sealant}"


_SEALANT_NOTATION = {
    SealantKind.PIB_BUTYL: "butilo",
    SealantKind.POLYSULFIDE: "tiokol",
    SealantKind.SILICONE: "silicona",
    SealantKind.POLYURETHANE: "poliuretano",
}


def format_glass_notation(composition: GlassComposition) -> str:
    """Canonical "4 / 12 aire / 4" — round-trips through the parser."""
    parts: list[str] = []
    for layer in composition.layers:
        parts.append(
            _format_lamina(layer)
            if isinstance(layer, GlassLamina)
            else _format_chamber(layer)
        )
    return " / ".join(parts)


# --------------------------------------------------------------------------
# Structured serialization (JSONB storage / API payloads)
# --------------------------------------------------------------------------

def composition_to_dict(composition: GlassComposition) -> dict[str, object]:
    layers: list[dict[str, object]] = []
    for layer in composition.layers:
        if isinstance(layer, GlassLamina):
            layers.append(
                {
                    "type": "lamina",
                    "panes": [_fmt_mm(pane) for pane in layer.panes],
                    "interlayer": (
                        layer.interlayer.value if layer.interlayer else None
                    ),
                    "tint": layer.tint.value,
                    "treatment": (
                        layer.treatment.value if layer.treatment else None
                    ),
                    "coating": layer.coating.value if layer.coating else None,
                    "coating_face": layer.coating_face,
                    "supplier_sku": layer.supplier_sku,
                }
            )
        else:
            layers.append(
                {
                    "type": "chamber",
                    "width_mm": _fmt_mm(layer.width_mm),
                    "gas": layer.gas.value,
                    "spacer": layer.spacer.value,
                    "sealant": (
                        layer.sealant.value if layer.sealant else None
                    ),
                }
            )
    return {"layers": layers}


def composition_from_dict(data: object) -> GlassComposition | None:
    """The inverse of ``composition_to_dict`` — a malformed stored payload
    reads as unknown rather than raising into a request path."""
    if not isinstance(data, dict):
        return None
    raw_layers = data.get("layers")
    if not isinstance(raw_layers, list):
        return None
    layers: list[GlassLamina | GlassChamber] = []
    try:
        for item in raw_layers:
            if not isinstance(item, dict):
                return None
            kind = item.get("type")
            if kind == "lamina":
                panes = [
                    Decimal(str(p).replace(",", "."))
                    for p in item.get("panes") or []
                ]
                if not panes:
                    return None
                layers.append(
                    GlassLamina(
                        panes=panes,
                        interlayer=(
                            InterlayerKind(item["interlayer"])
                            if item.get("interlayer")
                            else None
                        ),
                        tint=LaminaTint(item.get("tint") or "CLEAR"),
                        treatment=(
                            GlassTreatment(item["treatment"])
                            if item.get("treatment")
                            else None
                        ),
                        coating=(
                            GlassCoating(item["coating"])
                            if item.get("coating")
                            else None
                        ),
                        coating_face=(
                            int(item["coating_face"])
                            if item.get("coating_face") is not None
                            else None
                        ),
                        supplier_sku=(
                            str(item["supplier_sku"])
                            if item.get("supplier_sku")
                            else None
                        ),
                    )
                )
            elif kind == "chamber":
                layers.append(
                    GlassChamber(
                        width_mm=Decimal(
                            str(item.get("width_mm") or "0").replace(",", ".")
                        ),
                        gas=ChamberGas(item.get("gas") or "AIR"),
                        spacer=SpacerKind(item.get("spacer") or "ALUMINIUM"),
                        sealant=(
                            SealantKind(item["sealant"])
                            if item.get("sealant")
                            else None
                        ),
                    )
                )
            else:
                return None
        return GlassComposition(layers=layers)
    except (ValueError, KeyError, InvalidOperation, TypeError):
        return None
