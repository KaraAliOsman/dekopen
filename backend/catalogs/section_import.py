"""Section drawing ingestion — parse a manufacturer DXF or SVG into
candidate closed outlines in drawing units.

The parser DETECTS geometry; it never certifies it. Callers persist the
uploaded document, return the candidates for human review, and only a
confirmed article PATCH (orientation, origin, role, scale) turns one
outline into a ProfileSection with `source=DXF_REFERENCE` + `drawing_ref`.
A detected contour is evidence, not authority — matching the same rule
catalog imports follow for prose extraction.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterator

from defusedxml import ElementTree

PARSER_VERSION = "section-import/1.0"

# Enough segments that a bead groove or rounded pull doesn't collapse to a
# chord visibly different from the drawing — while staying a straight-edged
# polygon the ProfileSection contract accepts.
ARC_SEGMENTS = 12
MAX_CANDIDATES = 8
MAX_POINTS = 2000
# Parse work budgets — a permitted upload can be adversarially dense, so the
# parser itself bounds effort before `_finish` ever sees the geometry.
MAX_ELEMENTS = 20000      # SVG elements walked per document
MAX_PATH_TOKENS = 100000  # tokens per path `d` attribute
MAX_SUBPATHS = 64         # subpaths emitted per `d`
MAX_OUTLINES = 128        # outlines (candidates + open) per document
# $INSUNITS → millimetres per drawing unit (AutoCAD/DXF spec).
INSUNIT_MM = {
    1: Decimal("25.4"),        # inches
    2: Decimal("304.8"),       # feet
    4: Decimal("1"),           # millimetres
    5: Decimal("10"),          # centimetres
    6: Decimal("1000"),        # metres
    7: Decimal("1000000"),     # kilometres
    8: Decimal("0.0000254"),   # microinches
    9: Decimal("0.0254"),      # mils
    10: Decimal("914.4"),      # yards
    11: Decimal("0.0000001"),  # angstroms
    12: Decimal("0.000001"),   # nanometres
    13: Decimal("0.001"),      # microns
    14: Decimal("100"),        # decimetres
}
SVG_UNIT_MM = {
    "mm": Decimal("1"),
    "cm": Decimal("10"),
    "in": Decimal("25.4"),
    "pt": Decimal("25.4") / 72,
    "pc": Decimal("25.4") / 6,
    # CSS px at 96dpi — a declared standard, flagged in warnings.
    "px": Decimal("25.4") / 96,
    "": Decimal("25.4") / 96,
}


class SectionImportError(ValueError):
    """Raised when a drawing cannot be parsed into the import contract."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass
class SectionCandidate:
    tag: str
    points: list[tuple[Decimal, Decimal]]
    closed: bool = True


@dataclass
class SectionImportResult:
    format: str
    mm_per_unit: Decimal | None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_format(file_name: str, content: bytes) -> str:
    name = file_name.lower().rsplit(".", 1)[-1]
    if name in ("svg", "dxf"):
        return name
    head = content[:512].lstrip()
    if head.startswith(b"<") and (b"<svg" in head or head.startswith(b"<?xml")):
        return "svg"
    # A DXF starts with code/value pairs — a bare integer line is enough.
    first = head.split(None, 1)[0] if head else b""
    if re.fullmatch(rb"\s*\d+\s*", first):
        return "dxf"
    raise SectionImportError(
        "section_format_unknown", "The file is neither SVG nor DXF."
    )


# ---------------------------------------------------------------- SVG ----


def _num(value: str | None, default: Decimal = Decimal(0)) -> Decimal:
    if value is None:
        return default
    match = re.match(r"\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)", value)
    if not match:
        return default
    try:
        return Decimal(match.group(1))
    except InvalidOperation:
        return default


def _svg_unit_factor(value: str | None) -> Decimal | None:
    """Unit suffix on a width/height attribute gives the drawing's scale."""
    if value is None:
        return None
    match = re.match(r"\s*[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?\s*(mm|cm|in|pt|pc|px)?\s*$", value)
    if not match:
        return None
    return SVG_UNIT_MM[match.group(1) or ""]


def _svg_physical_mm(value: str | None) -> Decimal | None:
    """A width/height attribute resolved to millimetres, or None when the
    attribute is absent or declares no usable unit value."""
    if value is None:
        return None
    match = re.match(
        r"\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|pc|px)?\s*$",
        value,
    )
    if not match:
        return None
    try:
        return Decimal(match.group(1)) * SVG_UNIT_MM[match.group(2) or ""]
    except InvalidOperation:
        return None


_MICRO = Decimal("0.000001")


def _trig(value: float) -> Decimal:
    """Transcendental matrix terms are computed in double then captured at
    full precision — never rounded early; the transform's own 0.000001mm
    quantization is the only precision boundary."""
    return Decimal(repr(value))


def _apply_matrix(
    m: tuple[Decimal, ...], x: Decimal, y: Decimal
) -> tuple[Decimal, Decimal]:
    a, b, c, d, e, f = m
    return (
        (a * x + c * y + e).quantize(_MICRO, rounding=ROUND_HALF_UP),
        (b * x + d * y + f).quantize(_MICRO, rounding=ROUND_HALF_UP),
    )


def _compose(
    m1: tuple[Decimal, ...], m2: tuple[Decimal, ...]
) -> tuple[Decimal, ...]:
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _parse_transform(value: str | None) -> tuple[Decimal, ...]:
    """SVG transform attribute → affine matrix, applied left to right.
    Exact Decimal arithmetic — float never enters the declared-coordinate
    path (rotate/skew trig arrives quantized only at application)."""
    zero, one = Decimal(0), Decimal(1)
    m: tuple[Decimal, ...] = (one, zero, zero, one, zero, zero)
    if not value:
        return m
    for kind, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", value):
        nums = [Decimal(n) for n in re.findall(r"[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", args)]
        step: tuple[Decimal, ...]
        if kind == "matrix" and len(nums) == 6:
            step = tuple(nums)
        elif kind == "translate":
            step = (
                one,
                zero,
                zero,
                one,
                nums[0] if nums else zero,
                nums[1] if len(nums) > 1 else zero,
            )
        elif kind == "scale":
            step = (
                nums[0],
                zero,
                zero,
                nums[1] if len(nums) > 1 else nums[0],
                zero,
                zero,
            )
        elif kind == "rotate":
            rad = math.radians(float(nums[0]))
            cos_, sin_ = _trig(math.cos(rad)), _trig(math.sin(rad))
            step = (cos_, sin_, -sin_, cos_, zero, zero)
            if len(nums) >= 3:
                cx, cy = nums[1], nums[2]
                step = _compose(
                    _compose((one, zero, zero, one, cx, cy), step),
                    (one, zero, zero, one, -cx, -cy),
                )
        elif kind == "skewX":
            step = (
                one,
                zero,
                _trig(math.tan(math.radians(float(nums[0])))),
                one,
                zero,
                zero,
            )
        else:  # skewY
            step = (
                one,
                _trig(math.tan(math.radians(float(nums[0])))),
                zero,
                one,
                zero,
                zero,
            )
        m = _compose(m, step)
    return m


def _sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> list[tuple[float, float]]:
    out = []
    for i in range(1, ARC_SEGMENTS + 1):
        t = i / ARC_SEGMENTS
        u = 1 - t
        out.append(
            (
                u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
            )
        )
    return out


def _sample_quadratic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> list[tuple[float, float]]:
    out = []
    for i in range(1, ARC_SEGMENTS + 1):
        t = i / ARC_SEGMENTS
        u = 1 - t
        out.append(
            (
                u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
            )
        )
    return out


def _sample_elliptic(
    p0: tuple[float, float], rx: float, ry: float, rot: float, large: int, sweep: int, p1: tuple[float, float]
) -> list[tuple[float, float]]:
    """SVG arc → parametric sampling on the true ellipse (SVG 1.1 F.6.5)."""
    if rx == 0 or ry == 0 or (p0[0] == p1[0] and p0[1] == p1[1]):
        return [p1]
    phi = math.radians(rot % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p * x1p / (rx * rx) + y1p * y1p / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    coef = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        coef = -coef
    cxp = coef * rx * y1p / ry
    cyp = -coef * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (p0[0] + p1[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        dot = ux * vx + uy * vy
        mag = math.hypot(ux, uy) * math.hypot(vx, vy)
        value = math.acos(max(-1.0, min(1.0, dot / mag))) if mag else 0.0
        return -value if ux * vy - uy * vx < 0 else value

    start = angle(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle(
        (x1p - cxp) / rx,
        (y1p - cyp) / ry,
        (-x1p - cxp) / rx,
        (-y1p - cyp) / ry,
    )
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(2, int(ARC_SEGMENTS * abs(delta) / math.pi))
    out = []
    for i in range(1, steps + 1):
        theta = start + delta * i / steps
        out.append(
            (
                cx + rx * math.cos(theta) * cos_phi - ry * math.sin(theta) * sin_phi,
                cy + rx * math.cos(theta) * sin_phi + ry * math.sin(theta) * cos_phi,
            )
        )
    out[-1] = p1
    return out


def _path_points(d: str) -> tuple[list[list[tuple[Decimal, Decimal]]], bool]:
    """Path `d` → list of subpath polylines. Curves and arcs are sampled to
    straight segments so every candidate satisfies the polygon contract."""
    tokens = re.findall(
        r"[MmLlHhVvCcSsQqTtAaZz]|[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", d
    )
    if len(tokens) > MAX_PATH_TOKENS:
        raise SectionImportError(
            "section_too_complex", "A path exceeds the parsing token budget."
        )
    subpaths: list[list[tuple[Decimal, Decimal]]] = []
    current: list[tuple[Decimal, Decimal]] = []
    pos = (0.0, 0.0)
    start: tuple[float, float] | None = None
    pending = ""
    closed_here = False
    i = 0
    pending_smooth: tuple[float, float] | None = None
    # SVG smooth commands reflect the previous control point ONLY within the
    # same curve family — S after C/S, T after Q/T. A mixed C→T or Q→S falls
    # back to the current position (no reflection), never the wrong family.
    pending_smooth_family: str | None = None

    def flush() -> None:
        nonlocal current, start, closed_here, pending_smooth, pending_smooth_family
        if current:
            if closed_here and current[0] != current[-1]:
                current.append(current[0])
            subpaths.append(current)
        current = []
        start = None
        closed_here = False
        pending_smooth = None
        pending_smooth_family = None

    def take(n: int) -> list[float]:
        nonlocal i
        out: list[float] = []
        while len(out) < n and i < len(tokens):
            token = tokens[i]
            if re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz]", token):
                break
            out.append(float(token))
            i += 1
        return out

    while i < len(tokens):
        if len(subpaths) >= MAX_SUBPATHS:
            break
        if len(current) > MAX_POINTS:
            raise SectionImportError(
                "section_too_complex", "A path exceeds the point budget."
            )
        token = tokens[i]
        if re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz]", token):
            pending = token
            i += 1
            if pending in "Zz":
                closed_here = True
                # Per SVG spec the pen returns to the subpath's start — a
                # relative command after Z must resolve from it, not from
                # the last drawn vertex.
                if start is not None:
                    pos = start
                flush()
                pending = ""
            continue
        if pending == "":
            i += 1
            continue
        rel = pending.islower()
        cmd = pending.upper()

        def pt(x: float, y: float) -> tuple[float, float]:
            return (pos[0] + x, pos[1] + y) if rel else (x, y)

        if cmd == "M":
            values = take(2)
            if len(values) < 2:
                continue
            flush()
            nxt = pt(values[0], values[1])
            pos = nxt
            start = nxt
            current = [(Decimal(str(round(nxt[0], 6))), Decimal(str(round(nxt[1], 6))))]
            pending = "l" if rel else "L"  # implicit line-tos follow
        elif cmd == "L":
            values = take(2)
            if len(values) < 2:
                continue
            nxt = pt(values[0], values[1])
            pos = nxt
            current.append((Decimal(str(round(nxt[0], 6))), Decimal(str(round(nxt[1], 6)))))
            pending_smooth = None
        elif cmd == "H":
            values = take(1)
            if not values:
                continue
            x = pos[0] + values[0] if rel else values[0]
            pos = (x, pos[1])
            current.append((Decimal(str(round(x, 6))), Decimal(str(round(pos[1], 6)))))
            pending_smooth = None
        elif cmd == "V":
            values = take(1)
            if not values:
                continue
            y = pos[1] + values[0] if rel else values[0]
            pos = (pos[0], y)
            current.append((Decimal(str(round(pos[0], 6))), Decimal(str(round(y, 6)))))
            pending_smooth = None
        elif cmd == "C":
            values = take(6)
            if len(values) < 6:
                continue
            c1, c2, nxt = pt(*values[0:2]), pt(*values[2:4]), pt(*values[4:6])
            for x, y in _sample_cubic(pos, c1, c2, nxt):
                current.append((Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))))
            pos = nxt
            pending_smooth = c2
            pending_smooth_family = "C"
        elif cmd == "S":
            values = take(4)
            if len(values) < 4:
                continue
            c1 = (
                (2 * pos[0] - pending_smooth[0], 2 * pos[1] - pending_smooth[1])
                if pending_smooth and pending_smooth_family == "C"
                else pos
            )
            c2, nxt = pt(*values[0:2]), pt(*values[2:4])
            for x, y in _sample_cubic(pos, c1, c2, nxt):
                current.append((Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))))
            pos = nxt
            pending_smooth = c2
            pending_smooth_family = "C"
        elif cmd == "Q":
            values = take(4)
            if len(values) < 4:
                continue
            c1, nxt = pt(*values[0:2]), pt(*values[2:4])
            for x, y in _sample_quadratic(pos, c1, nxt):
                current.append((Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))))
            pos = nxt
            pending_smooth = c1
            pending_smooth_family = "Q"
        elif cmd == "T":
            values = take(2)
            if len(values) < 2:
                continue
            c1 = (
                (2 * pos[0] - pending_smooth[0], 2 * pos[1] - pending_smooth[1])
                if pending_smooth and pending_smooth_family == "Q"
                else pos
            )
            nxt = pt(*values[0:2])
            for x, y in _sample_quadratic(pos, c1, nxt):
                current.append((Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))))
            pos = nxt
            pending_smooth = c1
            pending_smooth_family = "Q"
        elif cmd == "A":
            values = take(7)
            if len(values) < 7:
                continue
            nxt = pt(values[5], values[6])
            for x, y in _sample_elliptic(
                pos, values[0], values[1], values[2], int(values[3]), int(values[4]), nxt
            ):
                current.append((Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))))
            pos = nxt
            pending_smooth = None
    flush()
    return subpaths, bool(subpaths)


def parse_svg(content: bytes) -> SectionImportResult:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise SectionImportError("section_svg_invalid", f"SVG does not parse: {error}")
    tag_name = root.tag.rsplit("}", 1)[-1]
    if tag_name.lower() != "svg":
        raise SectionImportError("section_svg_invalid", "Document root is not <svg>.")

    mm_per_unit: Decimal | None = None
    warnings: list[str] = []
    viewbox = root.get("viewBox") or root.get("viewbox")
    vb: list[Decimal] = []
    if viewbox:
        vb = [
            Decimal(part)
            for part in re.findall(
                r"[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", viewbox
            )
        ]
    w_mm = _svg_physical_mm(root.get("width"))
    h_mm = _svg_physical_mm(root.get("height"))
    aspect = (root.get("preserveAspectRatio") or "").split()
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        # Paths live in viewBox user units; only the declared physical
        # viewport size maps them to millimetres.
        if aspect and aspect[0].lower() == "none":
            warnings.append(
                "SVG uses preserveAspectRatio='none' — x and y scale "
                "independently; confirm a uniform scale."
            )
        else:
            ratios = [
                ratio
                for ratio in (
                    (w_mm / vb[2]) if w_mm is not None else None,
                    (h_mm / vb[3]) if h_mm is not None else None,
                )
                if ratio is not None
            ]
            if ratios:
                # Default 'meet' fits inside (min); 'slice' fills (max).
                mm_per_unit = max(ratios) if "slice" in aspect else min(ratios)
            else:
                warnings.append(
                    "SVG has a viewBox but no physical width/height — "
                    "scale must be confirmed by the reviewer."
                )
    else:
        # No viewBox → user units are CSS px by spec; a physical width alone
        # says nothing about coordinate scale.
        mm_per_unit = SVG_UNIT_MM["px"]
        warnings.append(
            "SVG has no physical unit; px is assumed at 96 dpi — confirm scale."
        )

    candidates: list[SectionCandidate] = []
    open_count = 0

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    MAX_DEPTH = 64
    deep_count = 0

    element_count = 0

    def walk(element, transform, depth: int = 0):
        nonlocal open_count, deep_count, element_count
        element_count += 1
        if element_count > MAX_ELEMENTS or len(candidates) + open_count >= MAX_OUTLINES:
            raise SectionImportError(
                "section_too_complex", "The document exceeds the parsing budget."
            )
        if depth > MAX_DEPTH:
            # Nesting deeper than a real drawing needs is adversarial input —
            # stop descending before the interpreter stack does.
            deep_count += 1
            return
        m = _compose(transform, _parse_transform(element.get("transform")))
        name = local(element.tag)
        # Every independently closed outline is its own candidate — a single
        # path can carry the frame contour AND the channel contour.
        outlines: list[tuple[list[tuple[Decimal, Decimal]], bool]] = []
        if name in ("polygon", "polyline"):
            nums = [
                Decimal(n)
                for n in re.findall(
                    r"[+-]?\d*\.?\d+(?:[eE][+-]?\d+)?", element.get("points") or ""
                )
            ]
            if len(nums) > 2 * MAX_POINTS:
                raise SectionImportError(
                    "section_too_complex", "A polygon exceeds the point budget."
                )
            points = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
            closed = name == "polygon" or (
                len(points) > 2 and points[0] == points[-1]
            )
            if points:
                outlines.append((points, closed))
        elif name == "path":
            subs, _ = _path_points(element.get("d") or "")
            for sub in subs:
                if len(sub) >= 3:
                    outlines.append((sub, sub[0] == sub[-1]))
        for child in element:
            walk(child, m, depth + 1)
        for points, closed in outlines:
            world = [_apply_matrix(m, x, y) for x, y in points]
            if closed:
                # A Z-closed outline repeats its first vertex at the end —
                # the section contract requires distinct vertices.
                if len(world) > 1 and world[0] == world[-1]:
                    world = world[:-1]
                candidates.append(
                    SectionCandidate(
                        tag=f"{name}#{len(candidates) + 1}", points=world
                    )
                )
            else:
                open_count += 1

    walk(
        root,
        (Decimal(1), Decimal(0), Decimal(0), Decimal(1), Decimal(0), Decimal(0)),
    )
    if deep_count:
        warnings.append(
            f"{deep_count} nested element(s) deeper than {MAX_DEPTH} levels skipped."
        )
    if open_count:
        warnings.append(f"{open_count} open outline(s) skipped — only closed shapes qualify.")
    return _finish("svg", mm_per_unit, candidates, warnings)


# ---------------------------------------------------------------- DXF ----


def _dxf_pairs(content: bytes) -> Iterator[tuple[str, str]]:
    try:
        text = content.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    lines = [line.rstrip("\r") for line in text.split("\n")]
    for index in range(0, len(lines) - 1, 2):
        yield lines[index].strip(), lines[index + 1].rstrip()


def _dxf_insunits(pairs: Iterator[tuple[str, str]]) -> tuple[Decimal | None, int]:
    """Scan HEADER for $INSUNITS; returns the mm hint and 0 — pairs are a
    generator, so the caller must rebuild it for a second pass."""
    insunits: int | None = None
    in_header = False
    collecting = False
    for code, value in pairs:
        if code == "2" and value == "HEADER":
            in_header = True
        elif code == "2" and in_header and value == "ENTITIES":
            break
        elif code == "2" and in_header:
            in_header = value != "ENDSEC" or in_header
        if in_header and code == "9" and value == "$INSUNITS":
            collecting = True
        elif collecting and code == "70":
            try:
                insunits = int(value)
            except ValueError:
                insunits = None
            collecting = False
    return (INSUNIT_MM.get(insunits or -1), insunits or -1)


def _bulge_arc(
    p1: tuple[Decimal, Decimal], p2: tuple[Decimal, Decimal], bulge: Decimal
) -> list[tuple[Decimal, Decimal]]:
    """DXF bulge → sampled arc points between p1 and p2 (p2 excluded)."""
    b = float(bulge)
    if b == 0:
        return []
    x1, y1, x2, y2 = float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1])
    theta = 4 * math.atan(b)
    chord = math.hypot(x2 - x1, y2 - y1)
    if chord == 0:
        return []
    radius = chord / (2 * math.sin(theta / 2))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    h = radius * math.cos(theta / 2)
    nx, ny = -(y2 - y1) / chord, (x2 - x1) / chord
    cx, cy = mx + nx * h, my + ny * h
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    delta = a2 - a1
    # Match bulge direction: positive bulge sweeps counter-clockwise.
    if b > 0:
        while delta < 0:
            delta += 2 * math.pi
    else:
        while delta > 0:
            delta -= 2 * math.pi
    steps = max(2, int(ARC_SEGMENTS * abs(delta) / math.pi))
    out = []
    for i in range(1, steps):
        angle = a1 + delta * i / steps
        out.append(
            (
                Decimal(str(round(cx + abs(radius) * math.cos(angle), 6))),
                Decimal(str(round(cy + abs(radius) * math.sin(angle), 6))),
            )
        )
    return out


def _dxf_num(value: str) -> Decimal:
    """Group values are raw drawing bytes — a nonnumeric coordinate is bad
    input, so it converts to the import contract rather than a server error."""
    try:
        return Decimal(value or "0")
    except InvalidOperation:
        raise SectionImportError(
            "section_dxf_invalid", f"A coordinate is not numeric: {value!r}."
        ) from None


def parse_dxf(content: bytes) -> SectionImportResult:
    pairs = list(_dxf_pairs(content))
    mm_per_unit, _ = _dxf_insunits(iter(pairs))
    warnings: list[str] = []
    if mm_per_unit is None:
        warnings.append("DXF has no $INSUNITS or an unmapped unit — confirm scale.")

    candidates: list[SectionCandidate] = []
    open_count = 0
    in_entities = False
    in_vertex = False
    entity: str | None = None
    vertices: list[tuple[Decimal, Decimal, Decimal]] = []
    closed = False
    tag_index = 0

    def flush() -> None:
        nonlocal vertices, closed, tag_index, open_count
        if len(candidates) + open_count >= MAX_OUTLINES:
            raise SectionImportError(
                "section_too_complex", "The document exceeds the parsing budget."
            )
        if entity in ("LWPOLYLINE", "POLYLINE") and len(vertices) > MAX_POINTS:
            raise SectionImportError(
                "section_too_complex", "A polyline exceeds the point budget."
            )
        if entity in ("LWPOLYLINE", "POLYLINE") and len(vertices) >= 3:
            points: list[tuple[Decimal, Decimal]] = []
            for i, (x, y, bulge) in enumerate(vertices):
                points.append((x, y))
                if bulge != 0:
                    nxt = vertices[(i + 1) % len(vertices)]
                    if i + 1 < len(vertices) or closed:
                        points.extend(_bulge_arc((x, y), (nxt[0], nxt[1]), bulge))
            if closed:
                tag_index += 1
                candidates.append(
                    SectionCandidate(tag=f"{entity}#{tag_index}", points=points)
                )
            else:
                open_count += 1
        vertices = []
        closed = False

    entity_count = 0
    for code, value in pairs:
        if code == "2" and value == "ENTITIES":
            in_entities = True
            continue
        if not in_entities:
            continue
        if code == "0":
            entity_count += 1
            if entity_count > MAX_ELEMENTS:
                raise SectionImportError(
                    "section_too_complex",
                    "The document exceeds the parsing budget.",
                )
            if value == "VERTEX" and entity == "POLYLINE":
                # VERTEX records feed the open POLYLINE — the parent flushes
                # only at SEQEND or the next non-vertex entity.
                in_vertex = True
                vertices.append((Decimal(0), Decimal(0), Decimal(0)))
                continue
            in_vertex = False
            flush()
            entity = None if value == "SEQEND" else value
            continue
        if in_vertex:
            if len(vertices) > MAX_POINTS:
                raise SectionImportError(
                    "section_too_complex", "A polyline exceeds the point budget."
                )
            x, y, bulge = vertices[-1]
            if code == "10":
                x = _dxf_num(value)
            elif code == "20":
                y = _dxf_num(value)
            elif code == "42":
                bulge = _dxf_num(value)
            else:
                continue
            vertices[-1] = (x, y, bulge)
            continue
        if entity in ("LWPOLYLINE", "POLYLINE"):
            if code == "10" and entity == "LWPOLYLINE":
                vertices.append((_dxf_num(value), Decimal(0), Decimal(0)))
            elif code == "20" and vertices and entity == "LWPOLYLINE":
                vertices[-1] = (vertices[-1][0], _dxf_num(value), vertices[-1][2])
            elif code == "42" and vertices and entity == "LWPOLYLINE":
                vertices[-1] = (vertices[-1][0], vertices[-1][1], _dxf_num(value))
            elif code == "70":
                try:
                    closed = bool(int(value) & 1)
                except ValueError:
                    closed = False
    flush()
    if open_count:
        warnings.append(f"{open_count} open polyline(s) skipped — only closed shapes qualify.")
    return _finish("dxf", mm_per_unit, candidates, warnings)


# ------------------------------------------------------------- shared ----


def _finish(
    fmt: str,
    mm_per_unit: Decimal | None,
    candidates: list[SectionCandidate],
    warnings: list[str],
) -> SectionImportResult:
    if not candidates:
        raise SectionImportError(
            "section_no_candidates",
            "The drawing contains no closed outline to review.",
        )

    def area(points: list[tuple[Decimal, Decimal]]) -> Decimal:
        total = Decimal(0)
        for i, (x1, y1) in enumerate(points):
            x2, y2 = points[(i + 1) % len(points)]
            total += x1 * y2 - x2 * y1
        return abs(total) / 2

    ranked = sorted(candidates, key=lambda c: -area(c.points))[:MAX_CANDIDATES]
    result = SectionImportResult(format=fmt, mm_per_unit=mm_per_unit, warnings=warnings)
    if len(candidates) > MAX_CANDIDATES:
        warnings.append(
            f"{len(candidates) - MAX_CANDIDATES} smaller outline(s) omitted — review the largest."
        )
    for index, candidate in enumerate(ranked):
        points = candidate.points[:MAX_POINTS]
        if len(candidate.points) > MAX_POINTS:
            warnings.append(f"{candidate.tag} exceeded {MAX_POINTS} points — truncated.")
        result.candidates.append(
            {
                "index": index,
                "tag": candidate.tag,
                "points": [[str(x), str(y)] for x, y in points],
                "area": str(
                    area(points).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
            }
        )
    return result


def import_section(file_name: str, content: bytes) -> SectionImportResult:
    if not content:
        raise SectionImportError("section_file_empty", "The uploaded file is empty.")
    fmt = detect_format(file_name, content)
    return parse_svg(content) if fmt == "svg" else parse_dxf(content)


def storage_key(org_id: str, file_name: str) -> str:
    return f"section-imports/{org_id}/{uuid.uuid4()}/{file_name}"
