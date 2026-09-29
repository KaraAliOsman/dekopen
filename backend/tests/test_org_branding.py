"""Org branding: role gates, logo validation, sha-pinned upload, integrity."""

from __future__ import annotations

import hashlib
import struct
import zlib
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

import projects.views as project_views
from documents.repository import DocumentaryError
from projects import org_branding


def _png(width: int = 2, height: int = 2) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@contextmanager
def _noop_ctx():
    yield


_FAKE_TX = SimpleNamespace(atomic=_noop_ctx)


def _client(monkeypatch, role: str):
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        if role not in allowed:
            raise APIException(code="pricing_permission_denied", detail="denied")
        yield token, SimpleNamespace(), org_id

    monkeypatch.setattr(project_views, "scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    return client, org_id


def test_branding_get_and_put_persist_fields(monkeypatch):
    client, org_id = _client(monkeypatch, "OWNER")
    writes = []

    def fake_one(sql, params=None, *args, **kwargs):
        if "UPDATE public.tenancy_organizations" in sql:
            writes.append(params)
        return {
            "name": "Org", "tax_id": "76123456-0", "commercial_name": "Fábrica Norte",
            "giro": "Ventanas", "brand_address": None, "brand_phone": None,
            "brand_email": "hola@norte.cl", "brand_logo_key": None,
            "brand_logo_sha256": None,
        }

    monkeypatch.setattr(org_branding, "one", fake_one)
    monkeypatch.setattr(org_branding, "documentary_backend", _noop_ctx)
    monkeypatch.setattr(org_branding, "transaction", _FAKE_TX)

    response = client.put(
        "/api/v1/organization/branding/",
        {"commercial_name": "Fábrica Norte", "giro": "Ventanas", "brand_email": "hola@norte.cl"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["commercial_name"] == "Fábrica Norte"
    assert writes and "Fábrica Norte" in writes[0]


def test_branding_write_forbidden_for_installer(monkeypatch):
    client, _ = _client(monkeypatch, "INSTALLER")
    response = client.put(
        "/api/v1/organization/branding/", {"commercial_name": "X"}, format="json"
    )
    assert response.status_code >= 400


def test_logo_rejects_non_image_bytes(monkeypatch):
    client, _ = _client(monkeypatch, "OWNER")
    file = SimpleUploadedFile("logo.gif", b"GIF89a" + b"\x00" * 64, content_type="image/gif")
    response = client.put("/api/v1/organization/branding/logo/", {"file": file}, format="multipart")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "brand_logo_type_invalid"


def test_logo_uploads_content_addressed_and_pins_sha(monkeypatch):
    client, org_id = _client(monkeypatch, "OWNER")
    payload = _png()
    sha = hashlib.sha256(payload).hexdigest()
    uploads = []
    writes = []

    storage = SimpleNamespace(
        upload_immutable=lambda key, data, ctype: uploads.append((key, data, ctype))
    )
    monkeypatch.setattr(org_branding, "SupabaseDocumentStorage", lambda: storage)

    def fake_one(sql, params=None, *args, **kwargs):
        writes.append(params)
        return {
            "name": "Org", "tax_id": None, "commercial_name": None, "giro": None,
            "brand_address": None, "brand_phone": None, "brand_email": None,
            "brand_logo_key": params[0] if "brand_logo_key" in sql else None,
            "brand_logo_sha256": params[1] if "brand_logo_sha256" in sql else None,
        }

    monkeypatch.setattr(org_branding, "one", fake_one)
    monkeypatch.setattr(org_branding, "documentary_backend", _noop_ctx)
    monkeypatch.setattr(org_branding, "transaction", _FAKE_TX)

    file = SimpleUploadedFile("logo.png", payload, content_type="image/png")
    response = client.put("/api/v1/organization/branding/logo/", {"file": file}, format="multipart")
    assert response.status_code == 200
    assert uploads == [(f"org_{org_id}/branding/logo_{sha[:12]}.png", payload, "image/png")]
    assert writes and writes[0][1] == sha


def test_logo_bytes_verify_integrity(monkeypatch):
    payload = _png()
    good_sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(
        org_branding, "one",
        lambda *a, **k: {"brand_logo_key": "org_x/branding/logo_ab.png", "brand_logo_sha256": good_sha},
    )
    monkeypatch.setattr(
        org_branding,
        "SupabaseDocumentStorage",
        lambda: SimpleNamespace(download_bounded=lambda key, bound: payload),
    )
    content, ctype = org_branding.logo_bytes(org_id=uuid4())
    assert content == payload and ctype == "image/png"

    monkeypatch.setattr(
        org_branding,
        "SupabaseDocumentStorage",
        lambda: SimpleNamespace(download_bounded=lambda key, bound: payload + b"x"),
    )
    try:
        org_branding.logo_bytes(org_id=uuid4())
        assert False, "expected integrity failure"
    except DocumentaryError as error:
        assert error.code == "brand_logo_integrity_failed"


def test_logo_bytes_404_without_logo(monkeypatch):
    monkeypatch.setattr(
        org_branding, "one", lambda *a, **k: {"brand_logo_key": None, "brand_logo_sha256": None}
    )
    try:
        org_branding.logo_bytes(org_id=uuid4())
        assert False, "expected 404"
    except APIException as error:
        assert error.get_codes() == "brand_logo_not_found"
