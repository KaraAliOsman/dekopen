"""Evidencia fotográfica de terreno (P23).

Las fotos viven en el mismo bucket privado que los documentos sellados,
bajo ``org_<org>/field/<uuid>.<ext>`` y registradas en ``field_photos``:
la URL firmada solo se emite si la clave pertenece a la organización del
solicitante — una foto de otra obra u org jamás se resuelve.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from uuid import uuid4

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one, rows
from documents.storage import SupabaseDocumentStorage

_MAX_BYTES = 4 * 1024 * 1024
_SIGNED_TTL_SECONDS = 600
_TYPES = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"RIFF": ("webp", "image/webp"),
}


def _detect(content: bytes) -> tuple[str, str] | None:
    if len(content) < 12:
        return None
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "webp", "image/webp"
    for magic, detected in _TYPES.items():
        if content.startswith(magic):
            return detected
    return None


def upload_evidence(*, org_id, content_b64: str, label: str | None, actor_id) -> dict:
    try:
        content = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError):
        raise contract_error(
            400, "field_photo_invalid", "La foto no es una imagen válida."
        ) from None
    if not content or len(content) > _MAX_BYTES:
        raise contract_error(
            400, "field_photo_invalid", "La foto debe ser PNG/JPEG/WebP ≤ 4 MB."
        )
    detected = _detect(content)
    if detected is None:
        raise contract_error(
            400, "field_photo_invalid", "La foto debe ser PNG, JPEG o WebP."
        )
    extension, content_type = detected
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"org_{org_id}/field/{uuid4()}.{extension}"
    SupabaseDocumentStorage().upload_immutable(object_key, content, content_type)
    with transaction.atomic(), documentary_backend():
        row = one(
            """
            INSERT INTO public.field_photos
                (org_id, object_key, sha256, label, uploaded_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING object_key, sha256
            """,
            [
                str(org_id),
                object_key,
                digest,
                (label or "").strip() or None,
                str(actor_id),
            ],
            "field_photo_rejected",
        )
    return {"key": row["object_key"], "sha256": row["sha256"]}


def evidence_access(*, org_id, object_key: str) -> dict:
    """Signed URL for one registered field photo. The registry row is the
    ACL: a key the org never uploaded never gets a URL."""
    if not re.fullmatch(r"org_[0-9a-fA-F-]{36}/field/[0-9A-Za-z._-]+", object_key or ""):
        raise DocumentaryError("field_photo_not_found")
    with documentary_backend():
        found = rows(
            "SELECT object_key FROM public.field_photos "
            "WHERE org_id=%s AND object_key=%s",
            [str(org_id), object_key],
        )
    if not found:
        raise DocumentaryError("field_photo_not_found")
    url = SupabaseDocumentStorage().signed_url(
        object_key, expires_in=_SIGNED_TTL_SECONDS
    )
    return {"url": url, "expires_in": _SIGNED_TTL_SECONDS}


def _photo_entries(raw) -> list[dict]:
    """Photos submitted inside a write payload must be registered keys of
    this org — the registry keeps untracked keys (and other orgs') out."""
    if not raw:
        return []
    entries = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        label = item.get("label")
        entries.append(
            {
                "key": key,
                "sha256": item.get("sha256"),
                "label": (str(label)[:120] if label else None),
            }
        )
    return entries


def validated_photos(*, org_id, raw) -> list[dict]:
    entries = _photo_entries(raw)
    if not entries:
        return []
    keys = [entry["key"] for entry in entries]
    with documentary_backend():
        registered = {
            row["object_key"]
            for row in rows(
                "SELECT object_key FROM public.field_photos "
                "WHERE org_id=%s AND object_key = ANY(%s)",
                [str(org_id), keys],
            )
        }
    for entry in entries:
        if entry["key"] not in registered:
            raise contract_error(
                400, "field_photo_unknown", "Una foto no pertenece a esta obra."
            )
    return entries
