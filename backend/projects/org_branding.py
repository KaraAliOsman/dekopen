"""Org document branding — the white-label identity emitted documents
render instead of the bare DEKOPEN masthead. The logo is content-addressed:
each upload lands at a new key pinned by sha256, so a document frozen with
a logo key can never render a different image.
"""

from __future__ import annotations

import hashlib
import json
import re  # regex solo para validar brand_color en _save_branding
from uuid import UUID

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one
from documents.storage import SupabaseDocumentStorage

# Re-export: la utilidad AA vive en documents.brand (módulo hoja);
# settings y el módulo de correo la consumen desde aquí.
from documents.brand import effective_brand_color  # noqa: F401

__all__ = [
    "effective_brand_color",
    "get_branding",
    "branding_for_snapshot",
    "save_branding",
    "save_logo",
    "clear_logo",
    "logo_bytes",
]


_MAX_LOGO_BYTES = 512 * 1024
_LOGO_TYPES = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"RIFF": ("webp", "image/webp"),
}


def _detect(content: bytes) -> tuple[str, str] | None:
    if len(content) < 12:
        return None
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp", "image/webp"
    for magic, detected in _LOGO_TYPES.items():
        if content.startswith(magic):
            return detected
    return None


def _branding(row: dict) -> dict:
    return {
        "name": row.get("name"),
        "tax_id": row.get("tax_id"),
        "commercial_name": row.get("commercial_name"),
        "giro": row.get("giro"),
        "brand_address": row.get("brand_address"),
        "brand_phone": row.get("brand_phone"),
        "brand_email": row.get("brand_email"),
        "brand_logo_key": row.get("brand_logo_key"),
        "brand_logo_sha256": row.get("brand_logo_sha256"),
        "brand_color": row.get("brand_color"),
        "doc_dekopen_credit": bool(row.get("doc_dekopen_credit")),
        "vano_spread_tolerance_mm": (
            None
            if row.get("vano_spread_tolerance_mm") is None
            else str(row["vano_spread_tolerance_mm"])
        ),
        "doc_paper_size": row.get("doc_paper_size") or "LETTER",
        "doc_terms": _doc_terms(row.get("doc_terms")),
        "workshop_label_format": row.get("workshop_label_format") or "GRID",
        "remnant_alert_days": (
            int(row["remnant_alert_days"])
            if row.get("remnant_alert_days") is not None
            else 30
        ),
        "doc_validity_days": int(row.get("doc_validity_days") or 15),
        "doc_warranty_months": (
            int(row["doc_warranty_months"])
            if row.get("doc_warranty_months") is not None
            else 24
        ),
    }


_FIELDS = (
    "name, tax_id, commercial_name, giro, brand_address, brand_phone,"
    " brand_email, brand_logo_key, brand_logo_sha256, brand_color,"
    " doc_dekopen_credit, vano_spread_tolerance_mm,"
    " doc_paper_size, doc_terms, workshop_label_format, remnant_alert_days,"
    " doc_validity_days, doc_warranty_months"
)

# P09 — claves legales declaradas que el documento del cliente imprime en
# "Condiciones comerciales". La misma lista gobierna el CHECK de la
# migración, el serializer y el congelado: una clave nueva es una decisión
# de producto, no un texto libre.
_DOC_TERM_KEYS = (
    "plazo_entrega",
    "instalacion",
    "exclusiones",
    "garantia",
    "jurisdiccion",
    # 'pago' es la plantilla del calendario de pagos: se prellena en el
    # constructor pero no se imprime en el bloque legal del DOC-01 (la
    # propuesta ya imprime payment_terms arriba).
    "pago",
)
_DOC_PAPER_SIZES = ("LETTER", "LEGAL", "A4")
# P13 — formato de la hoja de etiquetas del pack de corte: grilla sobre el
# papel documental o rollo térmico 100×50 mm para etiquetadoras de taller.
_LABEL_FORMATS = ("GRID", "THERMAL_100X50")
_DOC_VALIDITY_MIN = 1
_DOC_VALIDITY_MAX = 365


def _doc_terms(raw: object) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    terms = raw if isinstance(raw, dict) else {}
    return {
        key: str(terms[key]).strip()
        for key in _DOC_TERM_KEYS
        if isinstance(terms.get(key), str) and terms[key].strip()
    }


def get_branding(*, org_id: UUID) -> dict:
    row = one(
        f"SELECT {_FIELDS} FROM public.tenancy_organizations WHERE id=%s",
        [str(org_id)],
        "organization_not_found",
    )
    return _branding(row)


def branding_for_snapshot(*, org_id: UUID) -> dict:
    """Frozen-authority identity block: only fields that belong on a sealed
    document. The sha-pinned key means re-rendering later can prove the logo
    bytes are the ones the document was sealed with."""
    return get_branding(org_id=org_id)


def _blank(value):
    return (value or "").strip() or None


def save_branding(*, org_id: UUID, data: dict) -> dict:
    with transaction.atomic(), documentary_backend():
        row = _save_branding(org_id=org_id, data=data)
    return row


_BRAND_FIELDS = {
    "commercial_name": 255,
    "giro": 255,
    "brand_address": 255,
    "brand_phone": 64,
    "brand_email": 255,
}

def _save_branding(*, org_id: UUID, data: dict) -> dict:
    # A key absent from the validated payload keeps the stored value — a
    # key sent null clears it. Distinction matters: the workshop-rules card
    # writes only the tolerance and must not wipe the brand fields.
    assignments: list[str] = []
    params: list[object] = []
    for field, limit in _BRAND_FIELDS.items():
        if field not in data:
            continue
        assignments.append(f"{field}=%s")
        raw = data.get(field)
        params.append(_blank(raw)[:limit] if raw else None)
    if "brand_color" in data:
        assignments.append("brand_color=%s")
        raw_color = _blank(data.get("brand_color"))
        if raw_color is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", raw_color):
            raise contract_error(
                400,
                "brand_color_invalid",
                "El color de marca debe ser un valor #RRGGBB (ej. #075F5A).",
            )
        params.append(raw_color.upper() if raw_color else None)
    if "doc_dekopen_credit" in data:
        assignments.append("doc_dekopen_credit=%s")
        params.append(bool(data.get("doc_dekopen_credit")))
    if "vano_spread_tolerance_mm" in data:
        assignments.append("vano_spread_tolerance_mm=%s")
        params.append(data.get("vano_spread_tolerance_mm"))
    if "remnant_alert_days" in data:
        assignments.append("remnant_alert_days=%s")
        try:
            days = int(data["remnant_alert_days"])
        except (TypeError, ValueError):
            raise contract_error(
                400,
                "remnant_alert_days_invalid",
                "Los días de alerta de retazos deben ser un entero.",
            ) from None
        if not 1 <= days <= 365:
            raise contract_error(
                400,
                "remnant_alert_days_invalid",
                "Los días de alerta de retazos deben estar entre 1 y 365.",
            )
        params.append(days)
    if "doc_paper_size" in data:
        assignments.append("doc_paper_size=%s")
        size = str(data.get("doc_paper_size") or "").strip().upper()
        if size not in _DOC_PAPER_SIZES:
            raise contract_error(
                400,
                "doc_paper_size_invalid",
                "El papel debe ser Carta, Oficio o A4.",
            )
        params.append(size)
    if "workshop_label_format" in data:
        assignments.append("workshop_label_format=%s")
        label_format = str(
            data.get("workshop_label_format") or ""
        ).strip().upper()
        if label_format not in _LABEL_FORMATS:
            raise contract_error(
                400,
                "workshop_label_format_invalid",
                "El formato de etiquetas debe ser grilla A4/Carta o rollo térmico 100×50 mm.",
            )
        params.append(label_format)
    if "doc_terms" in data:
        assignments.append("doc_terms=%s::jsonb")
        raw_terms = data.get("doc_terms")
        if raw_terms is not None and not isinstance(raw_terms, dict):
            raise contract_error(
                400,
                "doc_terms_invalid",
                "Los textos de documento deben ser un objeto de claves declaradas.",
            )
        terms = raw_terms or {}
        unknown = [key for key in terms if key not in _DOC_TERM_KEYS]
        if unknown:
            raise contract_error(
                400,
                "doc_terms_invalid",
                "Claves de texto no reconocidas: " + ", ".join(sorted(unknown)) + ".",
            )
        params.append(json.dumps(_doc_terms(terms)))
    if "doc_validity_days" in data:
        raw_days = data.get("doc_validity_days")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 0
        if not (_DOC_VALIDITY_MIN <= days <= _DOC_VALIDITY_MAX):
            raise contract_error(
                400,
                "doc_validity_days_invalid",
                "La vigencia por defecto debe ser entre 1 y 365 días.",
            )
        assignments.append("doc_validity_days=%s")
        params.append(days)
    if "doc_warranty_months" in data:
        raw_months = data.get("doc_warranty_months")
        try:
            months = int(raw_months)
        except (TypeError, ValueError):
            months = -1
        if not (0 <= months <= 240):
            raise contract_error(
                400,
                "doc_warranty_months_invalid",
                "Los meses de garantía por defecto deben ser entre 0 y 240.",
            )
        assignments.append("doc_warranty_months=%s")
        params.append(months)
    if not assignments:
        row = one(
            f"SELECT {_FIELDS} FROM public.tenancy_organizations WHERE id=%s",
            [str(org_id)],
            "organization_not_found",
        )
        return _branding(row)
    assignments.append("updated_at=now()")
    row = one(
        "UPDATE public.tenancy_organizations SET "
        + ", ".join(assignments)
        + " WHERE id=%s RETURNING " + _FIELDS,
        [*params, str(org_id)],
        "organization_not_found",
    )
    return _branding(row)


def save_logo(*, org_id: UUID, content: bytes) -> dict:
    if not content or len(content) > _MAX_LOGO_BYTES:
        raise contract_error(400, "brand_logo_size_invalid", "El logo debe ser PNG/JPEG/WebP ≤ 512KB.")
    detected = _detect(content)
    if detected is None:
        raise contract_error(400, "brand_logo_type_invalid", "El logo debe ser PNG, JPEG o WebP.")
    extension, content_type = detected
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"org_{org_id}/branding/logo_{digest[:12]}.{extension}"
    SupabaseDocumentStorage().upload_immutable(object_key, content, content_type)
    with transaction.atomic(), documentary_backend():
        row = _clear_logo_row(org_id=org_id, key=object_key, sha=digest)
    return row


def _clear_logo_row(*, org_id: UUID, key: str, sha: str) -> dict:
    row = one(
        "UPDATE public.tenancy_organizations SET "
        "brand_logo_key=%s, brand_logo_sha256=%s, updated_at=now() "
        "WHERE id=%s RETURNING " + _FIELDS,
        [key, sha, str(org_id)],
        "organization_not_found",
    )
    return _branding(row)


def clear_logo(*, org_id: UUID) -> dict:
    """Dereference the logo — the object itself stays so sealed documents
    keep rendering it."""
    with transaction.atomic(), documentary_backend():
        row = one(
            "UPDATE public.tenancy_organizations SET "
            "brand_logo_key=NULL, brand_logo_sha256=NULL, updated_at=now() "
            "WHERE id=%s RETURNING " + _FIELDS,
            [str(org_id)],
            "organization_not_found",
        )
    return _branding(row)


def logo_bytes(*, org_id: UUID) -> tuple[bytes, str]:
    row = one(
        "SELECT brand_logo_key, brand_logo_sha256 FROM public.tenancy_organizations WHERE id=%s",
        [str(org_id)],
        "organization_not_found",
    )
    if not row.get("brand_logo_key"):
        raise contract_error(404, "brand_logo_not_found", "La organización no tiene logo.")
    content = SupabaseDocumentStorage().download_bounded(
        row["brand_logo_key"], _MAX_LOGO_BYTES
    )
    if not content or hashlib.sha256(content).hexdigest() != row["brand_logo_sha256"]:
        raise DocumentaryError("brand_logo_integrity_failed")
    detected = _detect(content)
    content_type = detected[1] if detected else "image/png"
    return content, content_type
