"""Section geometry checks — the validations a declared profile section must
pass before its article may carry a VERIFICADO review stamp.

Declared geometry is authority: a polygon that contradicts itself, whose
bounding box disagrees with the declared depth, or whose local origin is not
where the row claims, cannot be certified — the technical reviewer must fix
the geometry first. The same checks run in the workspace so failures are
visible before the review is attempted.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from dekopen_engine.models import polygon_self_intersects

# A declared section is hand-authored data: the depth may legitimately differ
# from the drawn extent by a draft tolerance (chamfers, radii), so the check
# tolerates a small absolute/relative delta before calling the row a
# contradiction. Same slack for the origin anchor.
DEPTH_TOLERANCE_MM = Decimal("0.5")
ORIGIN_TOLERANCE_MM = Decimal("0.5")
DEPTH_TOLERANCE_REL = Decimal("0.02")  # 2 % of the declared depth


def _num(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _points(section: dict) -> list[tuple[Decimal, Decimal]] | None:
    polygon = section.get("polygon")
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None
    points: list[tuple[Decimal, Decimal]] = []
    for vertex in polygon:
        if not isinstance(vertex, dict):
            return None
        x = _num(vertex.get("x_mm"))
        y = _num(vertex.get("y_mm"))
        if x is None or y is None:
            return None
        points.append((x, y))
    if len(set(points)) != len(points):
        return None
    return points


def _centroid(points: list[tuple[Decimal, Decimal]]) -> tuple[Decimal, Decimal]:
    area = Decimal(0)
    cx = Decimal(0)
    cy = Decimal(0)
    count = len(points)
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % count]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if area == 0:
        sx = sum(p[0] for p in points)
        sy = sum(p[1] for p in points)
        return (sx / count, sy / count)
    return (cx / (area * 3), cy / (area * 3))


def section_checks(section: dict | None) -> list[dict]:
    """Validation results for one article section — each check reports a
    code, a pass/fail flag, the measured value and the limit it was checked
    against. An empty list means no section was declared (a legitimate
    state — the row renders the approximate fallback, never a fake shape)."""
    if section is None:
        return []
    checks: list[dict] = []
    points = _points(section)
    if points is None:
        checks.append(
            {
                "code": "section_shape",
                "ok": False,
                "value": None,
                "limit": "3+ vértices únicos",
            }
        )
        return checks
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox_height = max(ys) - min(ys)
    checks.append(
        {"code": "section_shape", "ok": True, "value": str(len(points)), "limit": None}
    )

    checks.append(
        {
            "code": "self_intersection",
            "ok": not polygon_self_intersects(points),
            "value": None,
            "limit": None,
        }
    )

    depth = _num(section.get("depth_mm"))
    if depth is None or depth <= 0:
        checks.append(
            {
                "code": "depth_bounds",
                "ok": False,
                "value": str(section.get("depth_mm")),
                "limit": "> 0",
            }
        )
    else:
        tolerance = max(
            DEPTH_TOLERANCE_MM,
            (abs(depth) * DEPTH_TOLERANCE_REL).quantize(Decimal("0.001")),
        )
        delta = abs(bbox_height - depth)
        checks.append(
            {
                "code": "depth_bounds",
                "ok": delta <= tolerance,
                "value": str(bbox_height.quantize(Decimal("0.01"))),
                "limit": str(depth.quantize(Decimal("0.01"))),
            }
        )

    origin = section.get("local_origin") or "TOP_LEFT"
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    anchors = {
        "TOP_LEFT": (min_x, min_y),
        "TOP_RIGHT": (max_x, min_y),
        "BOTTOM_LEFT": (min_x, max_y),
        "BOTTOM_RIGHT": (max_x, max_y),
        "CENTROID": _centroid(points),
    }
    anchor = anchors.get(origin)
    if anchor is None:
        checks.append(
            {"code": "local_origin", "ok": False, "value": origin, "limit": None}
        )
    else:
        distance = max(abs(anchor[0]), abs(anchor[1]))
        checks.append(
            {
                "code": "local_origin",
                "ok": distance <= ORIGIN_TOLERANCE_MM,
                "value": f"({anchor[0].quantize(Decimal('0.01'))}; "
                f"{anchor[1].quantize(Decimal('0.01'))})",
                "limit": str(ORIGIN_TOLERANCE_MM),
            }
        )
    return checks


def section_check_failures(section: dict | None) -> list[dict]:
    """Only the failing checks — review() blocks on any of them."""
    return [check for check in section_checks(section) if not check["ok"]]
