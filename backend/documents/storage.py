"""Private Supabase Storage adapter with immutable writes and fixed signed access."""

from __future__ import annotations

from urllib.parse import quote, urljoin

from django.conf import settings
import httpx

from documents.repository import DocumentaryError

SIGNED_URL_TTL_SECONDS = 3600
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


def sanitize_storage_key(object_key: str) -> str:
    """The one canonical storage-key rule for new objects.

    A canonical key is ``/``-joined segments where every segment is non-empty,
    never ``.``/``..``, and carries no ``\\``, ``%``, control bytes or edge
    whitespace. Rejected here rather than canonicalized so a corrupted row or
    smuggled name can never be reshaped into another object's key — callers
    get a deterministic ``storage_key_invalid`` instead of a foreign object.
    """
    if not isinstance(object_key, str) or not object_key:
        raise DocumentaryError("storage_key_invalid")
    segments = object_key.split("/")
    for segment in segments:
        if not segment or segment in (".", ".."):
            raise DocumentaryError("storage_key_invalid")
        if segment != segment.strip():
            raise DocumentaryError("storage_key_invalid")
        if "\\" in segment or "%" in segment:
            raise DocumentaryError("storage_key_invalid")
        if any(ord(char) < 32 for char in segment):
            raise DocumentaryError("storage_key_invalid")
    return object_key


def readable_storage_key(object_key: str) -> str:
    """The read-path rule for keys already stored: identical to
    :func:`sanitize_storage_key` except a literal ``%`` is allowed — it is a
    filename character the request layer percent-encodes, not a traversal
    vector. Anything that could escape the bucket stays rejected."""
    if not isinstance(object_key, str) or not object_key:
        raise DocumentaryError("storage_key_invalid")
    for segment in object_key.split("/"):
        if not segment or segment in (".", ".."):
            raise DocumentaryError("storage_key_invalid")
        if segment != segment.strip() or "\\" in segment:
            raise DocumentaryError("storage_key_invalid")
        if any(ord(char) < 32 for char in segment):
            raise DocumentaryError("storage_key_invalid")
    return object_key


class SupabaseDocumentStorage:
    def __init__(self) -> None:
        self.base_url = str(settings.SUPABASE_URL).rstrip("/")
        self.service_key = str(settings.SUPABASE_SERVICE_ROLE_KEY)
        self.bucket = str(settings.SUPABASE_STORAGE_BUCKET_DOCS)
        if not self.service_key:
            raise DocumentaryError("document_storage_not_configured")
        if self.bucket != "documents":
            raise DocumentaryError("document_storage_bucket_invalid")

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        result = {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }
        if content_type is not None:
            result["Content-Type"] = content_type
        return result

    def _object_url(self, object_key: str) -> str:
        encoded = "/".join(
            quote(part, safe="") for part in sanitize_storage_key(object_key).split("/")
        )
        return f"{self.base_url}/storage/v1/object/{self.bucket}/{encoded}"

    def _read_url(self, object_key: str) -> str:
        """Stored objects keep a read path even when their key predates the
        canonical rule — a literal ``%`` is just a filename character once it
        is percent-encoded, but traversal (``.``/``..``/empty/backslash/edge
        space/control bytes) stays rejected."""
        encoded = "/".join(
            quote(part, safe="") for part in readable_storage_key(object_key).split("/")
        )
        return f"{self.base_url}/storage/v1/object/{self.bucket}/{encoded}"

    def upload_immutable(self, object_key: str, content: bytes, content_type: str) -> None:
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise DocumentaryError("document_file_size_invalid")
        with httpx.Client(timeout=20) as client:
            response = client.post(
                self._object_url(object_key),
                content=content,
                headers={**self._headers(content_type), "x-upsert": "false"},
            )
            if response.status_code in (200, 201):
                return
            if response.status_code in (400, 409):
                existing = client.get(self._object_url(object_key), headers=self._headers())
                if existing.status_code == 200 and existing.content == content:
                    return
            raise DocumentaryError("document_storage_upload_failed")

    def download(self, object_key: str) -> bytes:
        with httpx.Client(timeout=30) as client:
            response = client.get(self._read_url(object_key), headers=self._headers())
        if response.status_code != 200:
            raise DocumentaryError("document_storage_download_failed")
        return response.content

    def download_bounded(self, object_key: str, max_bytes: int) -> bytes | None:
        """Download only when the object fits — the stream is aborted the
        moment it exceeds `max_bytes`, so a huge document never buffers whole
        in memory. None means over the cap; callers fall back to a URL-based
        hand-off."""
        chunks: list[bytes] = []
        received = 0
        with httpx.Client(timeout=30) as client:
            with client.stream(
                "GET", self._read_url(object_key), headers=self._headers()
            ) as response:
                if response.status_code != 200:
                    raise DocumentaryError("document_storage_download_failed")
                for chunk in response.iter_bytes():
                    received += len(chunk)
                    if received > max_bytes:
                        return None
                    chunks.append(chunk)
        return b"".join(chunks)

    def delete_object(self, object_key: str) -> None:
        with httpx.Client(timeout=10) as client:
            response = client.delete(
                self._read_url(object_key), headers=self._headers()
            )
        if response.status_code not in (200, 204, 404):
            raise DocumentaryError("document_storage_delete_failed")

    def signed_url(self, object_key: str, expires_in: int | None = None) -> str:
        encoded = "/".join(
            quote(part, safe="") for part in readable_storage_key(object_key).split("/")
        )
        endpoint = f"{self.base_url}/storage/v1/object/sign/{self.bucket}/{encoded}"
        with httpx.Client(timeout=10) as client:
            response = client.post(
                endpoint,
                json={"expiresIn": expires_in or SIGNED_URL_TTL_SECONDS},
                headers=self._headers("application/json"),
            )
        if response.status_code != 200:
            raise DocumentaryError("document_storage_sign_failed")
        payload = response.json()
        signed = payload.get("signedURL") if isinstance(payload, dict) else None
        if not isinstance(signed, str) or not signed:
            raise DocumentaryError("document_storage_sign_failed")
        if signed.startswith("http"):
            return signed
        relative = signed.lstrip("/")
        if not relative.startswith("storage/v1/"):
            relative = f"storage/v1/{relative}"
        return urljoin(self.base_url + "/", relative)
