"""Deterministic catalog-article parser — supplier rows become article candidates.

Trust contract (§D): prose heuristics never prove a technical field. A SKU, a
role keyword or a nearby number is a *candidate*, not evidence — "Marco 70 × 58
mm" does not prove face_width_mm = 70, so a line with several plausible
measurements resolves none of them.

Confidence levels:
- ``VERIFIED_STRUCTURED``: explicit structured table/header mapping with a
  declared unit and known source location. This parser never emits it — prose
  extraction is never structured-verified.
- ``HIGH_CANDIDATE``: strong, unambiguous prose parse (every field extracted,
  exactly one measurement candidate, no warnings) — still unconfirmed.
- ``REVIEW_REQUIRED``: heuristic parse with missing fields.
- ``LOW``: ambiguous evidence (e.g. multiple measurements compete for a field).

Every candidate carries ``evidence`` — per-field original/normalized values,
source location and the parser version — so review audits what the parser
actually saw, and candidates stay suggestions until a human confirms.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

ROLES = (
    "FRAME",
    "SASH",
    "SLIDING_SASH",
    "DOOR_SASH",
    "MULLION_V",
    "MULLION_H",
    "INTERLOCK",
    "RAIL",
    "INVERSOR",
    "GLAZING_BEAD",
    "COUPLER",
    "ADDITIONAL",
    "THRESHOLD",
    "FRAME_EXTENSION",
    "SILL",
    "COVER_TRIM",
    "SKIRT",
)

_ROLE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    # More specific sliding/door roles resolve before the generic leaf and
    # rail keywords — "hoja corredera" is a SLIDING_SASH, not a SASH.
    (("puerta", "door"), "DOOR_SASH"),
    (("corredera", "corredizo", "sliding"), "SLIDING_SASH"),
    (("encuentro", "interlock", "enganche"), "INTERLOCK"),
    (("riel", "rail", "guia"), "RAIL"),
    (("marco", "frame", "kasa"), "FRAME"),
    (("hoja", "sash", "ventana"), "SASH"),
    (("montante", "mullion", "vertical"), "MULLION_V"),
    (("travesa", "horizontal", "jamba"), "MULLION_H"),
    (("inversor", "adaptador", "inverter"), "INVERSOR"),
    (("contravidrio", "junta", "vidrio", "bead", "clip"), "GLAZING_BEAD"),
    (("acoplamiento", "bayo", "coupler", "union", "acople"), "COUPLER"),
    (("umbral", "threshold", "zocalo"), "THRESHOLD"),
    (("refuerzo", "steel", "acero", "reinforcement"), "ADDITIONAL"),
    (("tapa", "tapacanal", "cover", "cap"), "COVER_TRIM"),
    (("vierteaguas", "sill", "repisa"), "SILL"),
)

_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_/]{0,29}$")
_NUMBER = re.compile(r"\d{1,5}(?:[.,]\d{1,4})?")
_KG_M = re.compile(r"(\d{1,3}(?:[.,]\d{1,4})?)\s*kg/?m", re.IGNORECASE)
_MM = re.compile(r"(\d{1,4}(?:[.,]\d{1,4})?)\s*mm", re.IGNORECASE)
# A dimension pair ("70 × 58 mm") is two measurements, not one — the regex
# alone would see only the value next to "mm".
_DIM_PAIR = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,4})?)\s*[×x]\s*(\d{1,4}(?:[.,]\d{1,4})?)\s*mm",
    re.IGNORECASE,
)
_REINFORCEMENT = re.compile(
    r"(?:refuerzo|acero|steel|ref\.)\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9.\-_/]{0,29})",
    re.IGNORECASE,
)

PARSER_VERSION = "catalog-parser/2"
CONFIDENCE_VERIFIED_STRUCTURED = "VERIFIED_STRUCTURED"
CONFIDENCE_HIGH_CANDIDATE = "HIGH_CANDIDATE"
CONFIDENCE_REVIEW_REQUIRED = "REVIEW_REQUIRED"
CONFIDENCE_LOW = "LOW"


def _decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token.replace(",", "."))
    except InvalidOperation:
        return None


def _role_of(text: str) -> tuple[str | None, str | None]:
    lowered = text.lower()
    for keywords, role in _ROLE_KEYWORDS:
        for keyword in keywords:
            if keyword in lowered:
                return role, keyword
    return None, None


def parse_article_line(
    line: str, key: str, source_ref: str | None = None
) -> dict[str, Any] | None:
    """Parse one catalog row; None when the line carries no article signal."""
    stripped = line.strip()
    if len(stripped) < 4:
        return None
    tokens = stripped.split()
    if not tokens or not _SKU.match(tokens[0]):
        return None
    sku = tokens[0].upper()
    if not any(ch.isdigit() for ch in sku):
        return None
    rest = " ".join(tokens[1:])

    warnings: list[str] = []
    numeric_spans: list[tuple[int, int]] = []

    kg_match = _KG_M.search(rest)
    weight = _decimal(kg_match.group(1)) if kg_match else None
    if kg_match:
        numeric_spans.append(kg_match.span(0))

    reinforcement = _REINFORCEMENT.search(rest)
    reinforcement_sku = reinforcement.group(1).upper() if reinforcement else None

    # Every plausible measurement is a candidate for face width — never the
    # first. "Marco 70 × 58 mm" offers two; picking either would fabricate the
    # field, so ambiguity leaves it unset and flags the line.
    pair_spans: list[tuple[int, int]] = []
    mm_candidates: list[tuple[Decimal, str]] = []
    for match in _DIM_PAIR.finditer(rest):
        pair_spans.append(match.span(0))
        numeric_spans.append(match.span(0))
        for group in (1, 2):
            value = _decimal(match.group(group))
            if value is not None and Decimal(5) <= value <= Decimal(300):
                mm_candidates.append((value, match.group(0)))

    def _in_pair(span: tuple[int, int]) -> bool:
        return any(span[0] < other[1] and span[1] > other[0] for other in pair_spans)

    for match in _MM.finditer(rest):
        if _in_pair(match.span(0)):
            continue
        value = _decimal(match.group(1))
        if value is not None and Decimal(5) <= value <= Decimal(300):
            mm_candidates.append((value, match.group(0)))
            numeric_spans.append(match.span(0))
    distinct_widths = {value for value, _ in mm_candidates}
    face_width = next(iter(distinct_widths)) if len(distinct_widths) == 1 else None

    role, role_keyword = _role_of(rest)

    def _masked(span: tuple[int, int]) -> bool:
        return any(
            span[0] < other[1] and span[1] > other[0] for other in numeric_spans
        )

    # The name ends at the first recognized measurement or metadata field —
    # "Marco 78 mm" is named "Marco", never "Marco 78 mm".
    boundaries = [span[0] for span in numeric_spans]
    if reinforcement:
        boundaries.append(reinforcement.start(0))
    for match in _NUMBER.finditer(rest):
        if _masked(match.span(0)):
            continue
        boundaries.append(match.start())
        break

    end = min(boundaries) if boundaries else len(rest)
    name = re.sub(r"[|,;:\s]+$", "", rest[:end].strip(" |,;:"))
    name = re.sub(r"\s{2,}", " ", name).strip()
    if len(name) > 120:
        name = name[:117].rstrip() + "..."

    if not name:
        warnings.append("catalog_name_missing")
        name = sku
    if role is None:
        warnings.append("catalog_role_unknown")
    if not mm_candidates:
        warnings.append("catalog_face_width_missing")
    elif len(distinct_widths) > 1:
        warnings.append("catalog_face_width_ambiguous")

    evidence: dict[str, Any] = {
        "parser_version": PARSER_VERSION,
        "source": {"ref": source_ref, "text": stripped[:300]},
        "fields": {
            "sku": {"normalized": sku, "original": tokens[0], "source": "first_token"},
            "name": {"normalized": name, "original": rest[:end].strip(), "source": "name_prefix"},
            "role": (
                {"normalized": role, "original": role_keyword, "source": "keyword"}
                if role
                else {"normalized": "ADDITIONAL", "original": None, "source": "default"}
            ),
            "face_width_mm": {
                "normalized": face_width,
                "original": (
                    mm_candidates[0][1]
                    if len(distinct_widths) == 1
                    else sorted({token for _, token in mm_candidates}) or None
                ),
                "unit": "mm",
                "source": "measurement_token",
            },
            "weight_kg_m": (
                {"normalized": weight, "original": kg_match.group(0), "unit": "kg/m", "source": "unit_token"}
                if kg_match
                else {"normalized": None, "original": None, "unit": "kg/m", "source": None}
            ),
            "reinforcement_sku": (
                {"normalized": reinforcement_sku, "original": reinforcement.group(0), "source": "explicit_token"}
                if reinforcement
                else {"normalized": None, "original": None, "source": None}
            ),
        },
    }

    if "catalog_face_width_ambiguous" in warnings:
        confidence = CONFIDENCE_LOW
    elif warnings:
        confidence = CONFIDENCE_REVIEW_REQUIRED
    else:
        confidence = CONFIDENCE_HIGH_CANDIDATE

    return {
        "key": key,
        "sku": sku,
        "name": name,
        "role": role or "ADDITIONAL",
        "face_width_mm": face_width,
        "commercial_length_mm": None,
        "welding_loss_mm": None,
        "reinforcement_sku": reinforcement_sku,
        "weight_kg_m": weight,
        "steel_weight_kg_m": None,
        "confidence": confidence,
        "warnings": warnings,
        "source_text": stripped[:300],
        "source_ref": source_ref,
        "evidence": evidence,
    }


_ENTITY_KEYS = {
    "SYSTEM": "system",
    "PROFILE": "profile",
    "CUT_RULE": "cut rule",
    "REINFORCEMENT_RULE": "reinforcement rule",
    "TYPOLOGY_LIMIT": "typology limit",
    "FINISH": "finish",
    "GLAZING_RULE": "glazing rule",
    "HARDWARE_KIT": "hardware kit",
    "PRICE": "price",
}


def parse_ai_candidates(output: str) -> list[dict[str, Any]]:
    """AI compile output → typed candidates. Two contracts:

    - JSON array of ``{"entity", "fields": {...}}`` objects — the provider's
      structured extraction for every catalog entity kind.
    - Legacy plain text — falls back to the prose line parser (PROFILE only).

    AI extraction can never reach VERIFIED_STRUCTURED: fields the model could
    not ground stay None (UNKNOWN), and every candidate lands at
    REVIEW_REQUIRED or below — the reviewer, not the model, is the authority.
    """
    stripped = output.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except ValueError:
        payload = None
    if not isinstance(payload, list):
        return parse_catalog_lines(stripped.splitlines())
    candidates: list[dict[str, Any]] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            continue
        entity = str(entry.get("entity") or "PROFILE").upper()
        if entity not in _ENTITY_KEYS:
            entity = "PROFILE"
        fields = entry.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        confidence = str(entry.get("confidence") or "REVIEW_REQUIRED").upper()
        if confidence == CONFIDENCE_VERIFIED_STRUCTURED:
            # Never granted to AI output — clamp to review-required.
            confidence = CONFIDENCE_REVIEW_REQUIRED
        elif confidence not in (
            CONFIDENCE_HIGH_CANDIDATE, CONFIDENCE_LOW, CONFIDENCE_REVIEW_REQUIRED
        ):
            confidence = CONFIDENCE_LOW
        warnings = [str(w) for w in entry.get("warnings") or []]
        if confidence == CONFIDENCE_LOW:
            # Low confidence = fields the model could not ground — force
            # UNKNOWN instead of letting an invented value ride through.
            fields = {
                key: (value if key in ("sku", "name", "role", "code") else None)
                for key, value in fields.items()
            }
            warnings.append("catalog_low_confidence_unknown")
        candidate: dict[str, Any] = {
            "key": f"ai:{index}",
            "entity": entity,
            "confidence": confidence,
            "warnings": warnings,
            "row_errors": [],
            "source_ref": entry.get("source_ref"),
            "fields": fields,
            "evidence": {
                "parser_version": f"{PARSER_VERSION}+ai",
                "source": {"ref": entry.get("source_ref"), "text": ""},
                "fields": {
                    name: {
                        "normalized": None if value is None else str(value),
                        "original": None if value is None else str(value),
                        "source": "ai_compile",
                    }
                    for name, value in fields.items()
                },
            },
        }
        if entity == "PROFILE":
            candidate.update(
                {
                    "sku": fields.get("sku"),
                    "name": fields.get("name"),
                    "role": fields.get("role") or "ADDITIONAL",
                    "face_width_mm": fields.get("face_width_mm"),
                    "commercial_length_mm": fields.get("commercial_length_mm"),
                    "welding_loss_mm": fields.get("welding_loss_mm"),
                    "reinforcement_sku": fields.get("reinforcement_sku"),
                    "weight_kg_m": fields.get("weight_kg_m"),
                    "steel_weight_kg_m": fields.get("steel_weight_kg_m"),
                }
            )
        candidates.append(candidate)
    return candidates


def parse_catalog_lines(lines: list[Any]) -> list[dict[str, Any]]:
    """Entries may be plain lines or (line, source-ref) pairs — the ref rides
    onto the candidate so review shows where in the document it came from."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(lines):
        text, ref = entry if isinstance(entry, tuple) else (entry, None)
        parsed = parse_article_line(text, key=f"c{index}", source_ref=ref)
        if parsed is None or parsed["sku"] in seen:
            continue
        seen.add(parsed["sku"])
        # Uniform candidate shape: prose lines are PROFILE entities.
        parsed.setdefault("entity", "PROFILE")
        parsed.setdefault("row_errors", [])
        candidates.append(parsed)
    return candidates
