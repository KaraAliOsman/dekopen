"""Org document branding — the white-label identity emitted documents
render instead of the bare DEKOPEN masthead. The logo is content-addressed:
each upload lands at a new key pinned by sha256, so a document frozen with
a logo key can never render a different image.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one
from documents.storage import SupabaseDocumentStorage


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
    }


_FIELDS = (
    "name, tax_id, commercial_name, giro, brand_address, brand_phone,"
    " brand_email, brand_logo_key, brand_logo_sha256"
)


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


def _save_branding(*, org_id: UUID, data: dict) -> dict:
    row = one(
        "UPDATE public.tenancy_organizations SET "
        "commercial_name=%s, giro=%s, brand_address=%s, brand_phone=%s,"
        " brand_email=%s, updated_at=now() "
        "WHERE id=%s RETURNING " + _FIELDS,
        [
            _blank(data.get("commercial_name"))[:255] if data.get("commercial_name") else None,
            _blank(data.get("giro"))[:255] if data.get("giro") else None,
            _blank(data.get("brand_address"))[:255] if data.get("brand_address") else None,
            _blank(data.get("brand_phone"))[:64] if data.get("brand_phone") else None,
            _blank(data.get("brand_email"))[:255] if data.get("brand_email") else None,
            str(org_id),
        ],
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
