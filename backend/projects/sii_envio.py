"""SII envío — the transport layer that turns a stamped DTE into a real tax
document.

A timbrado (the sealed DTE artifact emitted by ``projects.sii``) only reaches
the SII inside a signed ``<EnvioDTE>`` envelope: a ``<SetDTE>`` carries a
``<Caratula>`` identifying the sender plus the DTE itself, and both the DTE's
``<Documento>`` and the envelope are signed XML-DSig with the organization's
digital certificate — a different credential from the CAF's RSASK, owned by a
person the SII authorized to send documents for the company.

The envío row seals the envelope XML as immutable evidence and commits
``PENDING`` *before* any network call: a TRACKID is receipt, not acceptance,
and ACCEPTED/REJECTED only ever land from a status verdict. A retried send
resumes the same row — re-uploading only when no TRACKID was recorded, so an
uncertain transport outcome can never produce a second submission.

Adapters (the sealed payload always records which one answered):

- ``_HttpSiiClient`` — the documented UploadEnvio multipart contract against
  ``SII_WS_ENVIO_URL`` (``rutSender``/``dvSender``/``rutCompany``/
  ``dvCompany`` + ``archivo`` file + ``TOKEN`` cookie from ``SII_WS_TOKEN``);
  the verdict comes from ``SII_WS_STATUS_URL`` when configured. Endpoints are
  restricted to https on ``*.sii.cl`` or hosts in
  ``SII_WS_ENVIO_ALLOWED_HOSTS`` — the signed tax XML can never be posted to
  an arbitrary internal address.
- ``_MockSiiClient`` — deterministic development stand-in, active only under
  the explicit ``SII_WS_ENVIO_MOCK=1`` opt-in; a deployment missing its SII
  configuration fails closed with ``sii_envio_unconfigured`` instead of
  silently simulating acceptance.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone as utc_timezone
from urllib.parse import urlparse
from uuid import UUID

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12

from django.db import transaction
from django.utils import timezone
from lxml import etree

from authentication.errors import contract_error
from documents.repository import documentary_backend
from documents.storage import SupabaseDocumentStorage
from pricing.repository import one, rows
from projects.sii import (
    SIGNED_URL_TTL_SECONDS,
    _rut_normalize,
    _sha256,
    _unwrap_rsask,
    _wrap_rsask,
)

# The SII is the fixed receptor of every envío envelope.
SII_RECEPTOR_RUT = "60803000-K"
_DS = "http://www.w3.org/2000/09/xmldsig#"
_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
_MAX_PFX_BYTES = 65536
_RUT_IN_TEXT = re.compile(
    r"(?<!\d)(?:\d{7,8}|\d{1,2}(?:\.\d{3}){2})-[\dkK](?!\w)"
)
# DTE artifacts are parsed back from storage when the envelope is assembled —
# entity resolution and network access stay disabled regardless of content.
_SII_HOST_SUFFIX = ".sii.cl"


def _xml_parse(content):
    """Hardened parse: no entity resolution, no DTD loading, no network — a
    crafted DTE can never expand entities or fetch external resources here."""
    return etree.fromstring(
        content,
        parser=etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False
        ),
    )

try:
    # SII timestamps are continental-Chile wall time.
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    _SII_TZ = ZoneInfo("America/Santiago")
except ZoneInfoNotFoundError:  # pragma: no cover - container without tzdata
    _SII_TZ = utc_timezone(timedelta(hours=-3))


def _cert_aad(org_id: str, file_sha256: str) -> bytes:
    """AES-GCM associated data binding the wrapped pfx to its org + content —
    ciphertext copied onto another row can never be decrypted."""
    return f"sii_certificates:{org_id}:{file_sha256}".encode("utf-8")


def _cert_rut(cert: x509.Certificate) -> str | None:
    """The signing person's RUT inside a SII personal certificate lives in the
    subject — usually serialNumber, sometimes folded into the CN."""
    for attribute in cert.subject:
        for match in _RUT_IN_TEXT.findall(str(attribute.value or "")):
            normalized = _rut_normalize(match)
            if normalized is not None:
                return normalized
    return None


def _load_pfx(pfx: bytes, password: str | None) -> tuple:
    try:
        key, cert, _extra = pkcs12.load_key_and_certificates(
            pfx, password.encode("utf-8") if password else None
        )
    except Exception as error:
        raise contract_error(
            422, "sii_cert_invalid", "El certificado no se pudo abrir."
        ) from error
    if key is None or cert is None:
        raise contract_error(
            422, "sii_cert_invalid", "El archivo no trae llave privada y certificado."
        )
    if not isinstance(key, rsa.RSAPrivateKey):
        raise contract_error(
            422, "sii_cert_not_rsa", "El certificado debe tener una llave RSA."
        )
    if cert.issuer == cert.subject:
        raise contract_error(
            422,
            "sii_cert_self_signed",
            "El certificado debe ser emitido por una autoridad, no autofirmado.",
        )
    try:
        usage = cert.extensions.get_extension_for_oid(
            x509.ExtensionOID.KEY_USAGE
        ).value
    except x509.ExtensionNotFound:
        usage = None
    if usage is not None and not (
        usage.digital_signature or usage.content_commitment
    ):
        raise contract_error(
            422,
            "sii_cert_usage",
            "El certificado no está habilitado para firmar documentos.",
        )
    return key, cert


def _cert_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "subject": row["subject"],
        "rut_firma": row["rut_firma"],
        "serial_number": row.get("serial_number"),
        "valid_from": str(row["valid_from"]),
        "valid_to": str(row["valid_to"]),
        "nro_resol": int(row["nro_resol"]),
        "fch_resol": str(row["fch_resol"]),
        "active": bool(row["active"]),
        "created_at": str(row["created_at"]),
    }


def certificate_status(*, org_id: UUID) -> dict | None:
    """Public metadata of the org's active certificate — never key material.
    Reads only the column-granted metadata set so the tenant-scoped query never
    touches the wrapped blobs (which authenticated has no privilege on)."""
    found = rows(
        "SELECT id,subject,rut_firma,serial_number,valid_from,valid_to,"
        "nro_resol,fch_resol,active,created_at FROM public.sii_certificates "
        "WHERE org_id=%s AND active",
        [str(org_id)],
    )
    return _cert_public(found[0]) if found else None


def upload_certificate(
    *,
    org_id: UUID,
    actor_id: UUID,
    pfx_b64: str,
    password: str | None,
    nro_resol: int,
    fch_resol: str,
) -> dict:
    """Install the org's digital certificate: validate the .pfx is a real RSA
    credential carrying a RUT, not expired, then store the blob wrapped with
    the deployment KEK. Uploading a new certificate retires the previous one —
    envíos always sign with the single active row."""
    try:
        pfx = base64.b64decode(pfx_b64 or "", validate=True)
    except Exception as error:
        raise contract_error(
            422, "sii_cert_invalid", "El certificado no es base64 válido."
        ) from error
    if not pfx or len(pfx) > _MAX_PFX_BYTES:
        raise contract_error(
            422, "sii_cert_invalid", "El tamaño del certificado no es válido."
        )
    _key, cert = _load_pfx(pfx, password)
    if _cert_rut(cert) is None:
        raise contract_error(
            422, "sii_cert_rut_missing", "El certificado no identifica un RUT de firmante."
        )
    now = timezone.now()
    try:
        valid_to = cert.not_valid_after_utc
        valid_from = cert.not_valid_before_utc
    except AttributeError:  # pragma: no cover - cryptography < 42
        valid_to = cert.not_valid_after.replace(tzinfo=utc_timezone.utc)
        valid_from = cert.not_valid_before.replace(tzinfo=utc_timezone.utc)
    if valid_to <= now:
        raise contract_error(
            422, "sii_cert_expired", "El certificado está vencido."
        )
    if valid_from > now:
        raise contract_error(
            422,
            "sii_cert_not_yet_valid",
            "El certificado aún no entra en vigencia.",
        )
    try:
        resol_date = datetime.strptime(str(fch_resol or "")[:10], "%Y-%m-%d").date()
    except ValueError as error:
        raise contract_error(
            422, "sii_resolucion_invalid", "La fecha de resolución no es válida."
        ) from error
    file_hash = _sha256(pfx)
    aad = _cert_aad(str(org_id), file_hash)
    org_id_s = str(org_id)
    with transaction.atomic(), documentary_backend():
        one(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            [f"sii_certs:{org_id_s}"],
        )
        rows(
            "UPDATE public.sii_certificates SET active=false "
            "WHERE org_id=%s AND active RETURNING id",
            [org_id_s],
        )
        row = one(
            "INSERT INTO public.sii_certificates("
            "org_id,subject,rut_firma,serial_number,valid_from,valid_to,"
            "pfx_wrapped,password_wrapped,file_sha256,nro_resol,fch_resol,"
            "active,uploaded_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s) "
            "RETURNING *",
            [
                org_id_s,
                cert.subject.rfc4514_string()[:256],
                _cert_rut(cert),
                format(cert.serial_number, "d")[:40] or None,
                valid_from,
                valid_to,
                _wrap_rsask(base64.b64encode(pfx).decode("ascii"), aad),
                _wrap_rsask(password, aad) if password else None,
                file_hash,
                int(nro_resol),
                resol_date,
                str(actor_id),
            ],
        )
    return _cert_public(row)


def _cert_material(cert_row: dict) -> tuple:
    """Unwrap the stored pfx and return (private_key, certificate)."""
    aad = _cert_aad(str(cert_row["org_id"]), str(cert_row["file_sha256"]))
    pfx = base64.b64decode(_unwrap_rsask(str(cert_row["pfx_wrapped"]), aad))
    password = (
        _unwrap_rsask(str(cert_row["password_wrapped"]), aad)
        if cert_row.get("password_wrapped")
        else None
    )
    return _load_pfx(pfx, password)


def _c14n(element) -> bytes:
    """Canonical XML (REC-xml-c14n-20010315, inclusive, no comments) — the
    byte form both signatures digest."""
    return etree.tostring(element, method="c14n", with_comments=False)


def _rsa_key_value(privkey) -> tuple[str, str]:
    numbers = privkey.public_key().public_numbers()
    modulus = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    exponent = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    return (
        base64.b64encode(modulus).decode("ascii"),
        base64.b64encode(exponent).decode("ascii"),
    )


def _find_id(root, element_id: str):
    for element in root.iter():
        if element.get("ID") == element_id:
            return element
    raise ValueError(f"element {element_id} not found")


def _build_signature(target_id: str, digest_b64: str, privkey,
                     cert_der_b64: str) -> str:
    """The <Signature> element over an element already digested. Enveloped
    transform — the signature itself never enters the digest — RSA-SHA1."""
    modulus, exponent = _rsa_key_value(privkey)
    return (
        f'<Signature xmlns="{_DS}">'
        f"<SignedInfo>"
        f'<CanonicalizationMethod Algorithm="{_C14N}"/>'
        f'<SignatureMethod Algorithm="{_DS}rsa-sha1"/>'
        f'<Reference URI="#{target_id}">'
        f'<Transforms><Transform Algorithm="{_DS}enveloped-signature"/></Transforms>'
        f'<DigestMethod Algorithm="{_DS}sha1"/>'
        f"<DigestValue>{digest_b64}</DigestValue>"
        f"</Reference></SignedInfo>"
        f"<SignatureValue></SignatureValue>"
        f"<KeyInfo><KeyValue><RSAKeyValue>"
        f"<Modulus>{modulus}</Modulus><Exponent>{exponent}</Exponent>"
        f"</RSAKeyValue></KeyValue>"
        f"<X509Data><X509Certificate>{cert_der_b64}</X509Certificate></X509Data>"
        f"</KeyInfo></Signature>"
    )


def _envelope_sign(root, target_id: str, privkey, cert_der_b64: str) -> None:
    """Sign the element carrying ID=target_id with an enveloped xmldsig
    Signature placed as its *sibling* — the shape the SII schema requires:
    ``<DTE><Documento/><Signature/></DTE>`` and ``<EnvioDTE><SetDTE/><Signature
    /></EnvioDTE>``. The digest is computed before the Signature exists and the
    SignedInfo is canonicalized in its final position so ancestor namespaces
    digest identically on verify."""
    target = _find_id(root, target_id)
    digest = base64.b64encode(hashlib.sha1(_c14n(target)).digest()).decode("ascii")
    skeleton = _build_signature(target_id, digest, privkey, cert_der_b64)
    signature_el = _xml_parse(skeleton.encode("utf-8"))
    target.addnext(signature_el)
    signed_info = signature_el.find(f"{{{_DS}}}SignedInfo")
    signature_el.find(f"{{{_DS}}}SignatureValue").text = base64.b64encode(
        privkey.sign(_c14n(signed_info), padding.PKCS1v15(), hashes.SHA1())
    ).decode("ascii")


def _render_envio_envelope(
    dte_xml: bytes,
    dte: dict,
    privkey,
    cert: x509.Certificate,
    caf: dict,
    cert_row: dict,
    sent_at,
) -> bytes:
    """Build the full <EnvioDTE>: embed the stored DTE unsigned, then sign
    Documento *inside the envelope* and finally SetDoc. c14n pulls in-scope
    ancestor namespaces into the digest — signing before embedding would
    produce a SignedInfo that no longer canonicalizes identically once
    EnvioDTE's xmlns:xsi is in scope, so both signatures are created in the
    tree's final shape. The stored timbraje file is never touched."""
    dte_root = _xml_parse(dte_xml)
    cert_der_b64 = base64.b64encode(
        cert.public_bytes(serialization.Encoding.DER)
    ).decode("ascii")
    local = sent_at.astimezone(_SII_TZ)
    tmst = local.strftime("%Y-%m-%dT%H:%M:%S")
    caratula = (
        f'<Caratula version="1.0"><RutEmisor>{caf["rut_emisor"]}</RutEmisor>'
        f"<RutEnvia>{cert_row['rut_firma']}</RutEnvia>"
        f"<RutReceptor>{SII_RECEPTOR_RUT}</RutReceptor>"
        f"<FchResol>{cert_row['fch_resol']}</FchResol>"
        f"<NroResol>{int(cert_row['nro_resol'])}</NroResol>"
        f"<TmstFirmaEnv>{tmst}</TmstFirmaEnv>"
        f"<SubTotDTE><TpoDTE>{int(dte['dte_type'])}</TpoDTE>"
        f"<NroDTE>1</NroDTE></SubTotDTE></Caratula>"
    )
    dte_inner = etree.tostring(dte_root, encoding="unicode")
    envelope_xml = (
        '<EnvioDTE xmlns="http://www.sii.cl/SiiDte" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="http://www.sii.cl/SiiDte EnvioDTE_v10.xsd" '
        'version="1.0"><SetDTE ID="SetDoc">'
        f"{caratula}{dte_inner}</SetDTE></EnvioDTE>"
    )
    env_root = _xml_parse(envelope_xml.encode("utf-8"))
    documento_id = f"F{int(dte['dte_type'])}T{int(dte['folio'])}"
    _envelope_sign(env_root, documento_id, privkey, cert_der_b64)
    _envelope_sign(env_root, "SetDoc", privkey, cert_der_b64)
    return etree.tostring(env_root, encoding="iso-8859-1", xml_declaration=True)


class _MockSiiClient:
    """Deterministic local stand-in for the SII webservice — selected only by
    the explicit ``SII_WS_ENVIO_MOCK=1`` opt-in, stamped ``adapter=mock`` in the
    sealed payload, and modeling the real lifecycle: upload only *acknowledges
    receipt*, so ACCEPTED comes from ``query_status`` exactly like the real
    adapter's reconciliation."""

    adapter = "mock"

    def submit(self, content: bytes, *, rut_emisor: str, rut_envia: str) -> dict:
        return {
            "track_id": f"MOCK-{hashlib.sha256(content).hexdigest()[:12].upper()}",
            "glosa": "Envío simulado localmente",
        }

    def query_status(self, *, track_id: str, rut_emisor: str) -> dict:
        return {"status": "ACCEPTED", "glosa": "Envío simulado localmente"}


def _rut_parts(rut: str) -> tuple[str, str]:
    """`76123456-7` → `("76123456", "7")` — the upload contract splits them."""
    numero, dv = rut.split("-", 1)
    return numero, dv


class _HttpSiiClient:
    """Real SII submission: the documented UploadEnvio multipart contract —
    sender and company RUTs split into their own fields, the envelope attached
    as ``archivo``, and the session ``TOKEN`` cookie acquired out-of-band
    (``SII_WS_TOKEN``). The response's TRACKID is a *receipt*, not acceptance:
    the envío stays PENDING until ``query_status`` returns a verdict."""

    adapter = "sii-ws"

    def __init__(self, url: str, status_url: str | None, token: str) -> None:
        self._url = url
        self._status_url = status_url
        self._token = token

    def submit(self, content: bytes, *, rut_emisor: str, rut_envia: str) -> dict:
        rut_s, dv_s = _rut_parts(rut_envia)
        rut_c, dv_c = _rut_parts(rut_emisor)
        try:
            response = httpx.post(
                self._url,
                data={
                    "rutSender": rut_s,
                    "dvSender": dv_s,
                    "rutCompany": rut_c,
                    "dvCompany": dv_c,
                },
                files={"archivo": ("envio.xml", content, "text/xml")},
                cookies={"TOKEN": self._token},
                timeout=30,
                follow_redirects=False,
            )
        except httpx.HTTPError as error:
            raise contract_error(
                503,
                "sii_envio_unreachable",
                "El SII no respondió — el envío quedó pendiente para reintento.",
            ) from error
        if response.status_code != 200:
            raise contract_error(
                503,
                "sii_envio_unreachable",
                f"El SII respondió {response.status_code} — el envío quedó pendiente.",
            )
        match = re.search(r"<TRACKID>(\d+)</TRACKID>", response.text or "")
        if match is None:
            raise contract_error(
                503,
                "sii_envio_bad_response",
                "La respuesta del SII no trae TRACKID — el envío quedó pendiente.",
            )
        glosa = re.search(r"<GLOSA>([^<]*)</GLOSA>", response.text or "")
        return {
            "track_id": match.group(1),
            "glosa": glosa.group(1) if glosa else None,
        }

    def query_status(self, *, track_id: str, rut_emisor: str) -> dict | None:
        """Ask the SII status endpoint for the final processing verdict. A
        missing status URL or a transport error leaves the envío PENDING —
        acceptance is only ever recorded from an explicit verdict."""
        if not self._status_url:
            return None
        rut_c, dv_c = _rut_parts(rut_emisor)
        try:
            response = httpx.post(
                self._status_url,
                data={
                    "TRACKID": track_id,
                    "rutCompany": rut_c,
                    "dvCompany": dv_c,
                },
                cookies={"TOKEN": self._token},
                timeout=30,
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            body_root = _xml_parse(response.content)
        except etree.XMLSyntaxError:
            return None

        def _field(*names: str) -> str | None:
            for element in body_root.iter():
                if etree.QName(element).localname.upper() in names and element.text:
                    return element.text.strip()
            return None

        glosa = _field("GLOSA", "GLOSA_ESTADO", "GLOSA_ERR")
        code = (_field("ESTADO", "STATUS", "COD_ESTATUS") or "").upper()

        def _count(*names: str) -> int | None:
            raw = _field(*names)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        # EPR means "processed", not "accepted" — the outcome counters decide:
        # a rejected DTE inside a processed envelope is a REJECTED envío.
        rejected = _count("RECHAZADOS")
        if code in {"RPR", "RECHAZADO", "DNK", "FAU", "FAN"} or (
            rejected is not None and rejected > 0
        ):
            return {"status": "REJECTED", "glosa": glosa}
        if code in {"EPR", "ACEPTADO", "FOK", "ENC", "FIN"}:
            return {"status": "ACCEPTED", "glosa": glosa}
        return {"status": "PENDING", "glosa": glosa}


def _endpoint_allowed(url: str) -> bool:
    """Outbound SII calls only ever reach https on *.sii.cl or hosts the
    deployment explicitly allowlists — signed tax XML can never be posted to
    an arbitrary internal address."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "sii.cl" or host.endswith(_SII_HOST_SUFFIX):
        return True
    extra = os.environ.get("SII_WS_ENVIO_ALLOWED_HOSTS", "")
    return host in {h.strip().lower() for h in extra.split(",") if h.strip()}


def _sii_client():
    """Pick the submission adapter. Real endpoint: requires an allowlisted
    https URL plus the session token. Mock: only under the explicit
    ``SII_WS_ENVIO_MOCK=1`` development opt-in — never silently accepted in a
    deployment that forgot its SII configuration."""
    url = os.environ.get("SII_WS_ENVIO_URL", "").strip()
    if url:
        if not _endpoint_allowed(url):
            raise contract_error(
                503,
                "sii_envio_endpoint_forbidden",
                "El endpoint SII configurado no es un destino permitido.",
            )
        token = os.environ.get("SII_WS_TOKEN", "").strip()
        if not token:
            raise contract_error(
                503,
                "sii_envio_unconfigured",
                "Falta el token de sesión SII (SII_WS_TOKEN).",
            )
        status_url = os.environ.get("SII_WS_STATUS_URL", "").strip() or None
        if status_url and not _endpoint_allowed(status_url):
            raise contract_error(
                503,
                "sii_envio_endpoint_forbidden",
                "El endpoint de estado SII no es un destino permitido.",
            )
        return _HttpSiiClient(url, status_url, token)
    if os.environ.get("SII_WS_ENVIO_MOCK", "").strip() == "1":
        return _MockSiiClient()
    raise contract_error(
        503,
        "sii_envio_unconfigured",
        "El envío al SII no está configurado — defina SII_WS_ENVIO_URL y "
        "SII_WS_TOKEN, o habilite SII_WS_ENVIO_MOCK=1 en desarrollo.",
    )


def _payload(row: dict) -> dict:
    """The sealed envío evidence — psycopg hands JSONB back either parsed or
    as raw text depending on the connection; normalize once."""
    payload = row.get("payload_json")
    return json.loads(payload) if isinstance(payload, str) else (payload or {})


def _ts(value) -> datetime | None:
    """ISO timestamp from the sealed payload — missing or malformed → None."""
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=utc_timezone.utc) if parsed.tzinfo is None else parsed


def _envio_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "dte_id": str(row["dte_id"]),
        "status": row["status"],
        "track_id": row.get("track_id"),
        "glosa": row.get("glosa"),
        "sent_at": str(row["sent_at"]),
        "attempted": bool(_payload(row).get("submit_attempted_at")),
    }


def _purge_unreferenced_envio(*, org_id: UUID, object_key: str) -> None:
    """Compensating delete for a rolled-back envío: an orphan object is
    removed without masking the original failure."""
    try:
        SupabaseDocumentStorage().delete_object(object_key)
    except Exception as cleanup_error:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "envio_cleanup_failed",
            extra={"storage_object_key": object_key, "cleanup_error": str(cleanup_error)},
        )


def _parent_dte(
    *,
    org_id_s: str,
    project_id_s: str,
    invoice_id_s: str | None = None,
    credit_note_id_s: str | None = None,
    dispatch_note_id_s: str | None = None,
) -> dict:
    """The stamped DTE of a parent document, scoped to the path's project —
    a route that names a foreign project or document resolves to nothing."""
    if invoice_id_s is not None:
        found = rows(
            "SELECT * FROM public.project_dtes "
            "WHERE org_id=%s AND project_id=%s AND invoice_id=%s "
            "AND credit_note_id IS NULL",
            [org_id_s, project_id_s, invoice_id_s],
        )
    elif credit_note_id_s is not None:
        found = rows(
            "SELECT * FROM public.project_dtes "
            "WHERE org_id=%s AND project_id=%s AND credit_note_id=%s",
            [org_id_s, project_id_s, credit_note_id_s],
        )
    elif dispatch_note_id_s is not None:
        found = rows(
            "SELECT * FROM public.project_dtes "
            "WHERE org_id=%s AND project_id=%s AND dispatch_note_id=%s",
            [org_id_s, project_id_s, dispatch_note_id_s],
        )
    else:  # pragma: no cover - internal contract
        raise AssertionError("parent document required")
    if not found:
        raise contract_error(
            409,
            "sii_dte_missing",
            "El documento aún no está timbrado — emita el DTE primero.",
        )
    return found[0]


def _seal_pending_envio(
    *,
    org_id_s: str,
    project_id_s: str,
    dte: dict,
    actor_id: UUID,
) -> tuple[dict, bytes | None]:
    """Commit the PENDING envío + immutable envelope *before* any network call —
    the row is the replay record, so a later retry can never submit a second
    envelope for the same DTE. Returns (row, envelope) — envelope bytes are
    only built on first seal; resumed rows re-download by key."""
    storage = SupabaseDocumentStorage()
    cert_rows = rows(
        "SELECT * FROM public.sii_certificates WHERE org_id=%s AND active",
        [org_id_s],
    )
    if not cert_rows:
        raise contract_error(
            409,
            "sii_certificate_missing",
            "Suba el certificado digital de la empresa antes de enviar al SII.",
        )
    cert_row = cert_rows[0]
    now = timezone.now()
    valid_to = cert_row["valid_to"]
    if valid_to.tzinfo is None:
        valid_to = valid_to.replace(tzinfo=utc_timezone.utc)
    valid_from = cert_row["valid_from"]
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=utc_timezone.utc)
    if valid_to <= now:
        raise contract_error(
            409, "sii_cert_expired", "El certificado digital está vencido."
        )
    if valid_from > now:
        raise contract_error(
            409,
            "sii_cert_not_yet_valid",
            "El certificado digital aún no entra en vigencia.",
        )
    caf = one(
        "SELECT * FROM public.sii_cafs WHERE id=%s",
        [str(dte["caf_id"])],
        "sii_caf_missing",
    )
    dte_xml = storage.download(str(dte["storage_object_key"]))
    privkey, cert = _cert_material(cert_row)
    sent_at = timezone.now()
    try:
        envelope = _render_envio_envelope(
            dte_xml, dte, privkey, cert, caf, cert_row, sent_at
        )
    except etree.XMLSyntaxError as error:
        raise contract_error(
            409,
            "sii_dte_unreadable",
            "El DTE almacenado no se pudo interpretar — el envío no se generó.",
        ) from error
    envelope_hash = _sha256(envelope)
    object_key = (
        f"org_{org_id_s}/projects/{project_id_s}/envios/"
        f"envio-dte{dte['dte_type']}-{dte['folio']}_{envelope_hash[:16]}.xml"
    )
    storage.upload_immutable(object_key, envelope, "application/xml")
    try:
        row = one(
            "INSERT INTO public.sii_envios("
            "org_id,project_id,dte_id,status,payload_json,storage_bucket,"
            "storage_object_key,file_sha256,media_type,byte_size,sent_by,"
            "sent_at) VALUES(%s,%s,%s,'PENDING',%s,'documents',%s,%s,"
            "'application/xml',%s,%s,%s) RETURNING *",
            [
                org_id_s,
                project_id_s,
                str(dte["id"]),
                json.dumps(
                    {
                        "dte_type": int(dte["dte_type"]),
                        "folio": int(dte["folio"]),
                        "dte_id": str(dte["id"]),
                        "caf_id": str(caf["id"]),
                        "emisor": {
                            "rut": caf["rut_emisor"],
                            "razon_social": caf["razon_social"],
                        },
                        "envia": cert_row["rut_firma"],
                        "caratula": {
                            "nro_resol": int(cert_row["nro_resol"]),
                            "fch_resol": str(cert_row["fch_resol"]),
                            "rut_receptor": SII_RECEPTOR_RUT,
                        },
                    }
                ),
                object_key,
                envelope_hash,
                len(envelope),
                str(actor_id),
                sent_at,
            ],
        )
    except Exception:
        storage.delete_object(object_key)
        raise
    return row, envelope


def _send_dte_envio(
    *,
    org_id_s: str,
    project_id_s: str,
    dte: dict,
    actor_id: UUID,
    resubmit: bool,
) -> dict:
    """Submit a stamped DTE to the SII. The envío row is committed
    PENDING *before* any network call, so an uncertain transport outcome never
    orphans a submission: a retry resumes the same row — re-sending only when
    no TRACKID was ever recorded, otherwise reconciling status. Receipt is not
    acceptance: ACCEPTED/REJECTED only land from a status verdict."""
    with transaction.atomic(), documentary_backend():
        one(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            [f"sii_envios:{org_id_s}:{dte['id']}"],
        )
        existing = rows(
            "SELECT * FROM public.sii_envios "
            "WHERE org_id=%s AND project_id=%s AND dte_id=%s",
            [org_id_s, project_id_s, str(dte["id"])],
        )
        envelope: bytes | None = None
        if existing:
            row = existing[0]
        else:
            row, envelope = _seal_pending_envio(
                org_id_s=org_id_s,
                project_id_s=project_id_s,
                dte=dte,
                actor_id=actor_id,
            )
    if row["status"] != "PENDING":
        return _envio_public(row)

    client = _sii_client()
    storage = SupabaseDocumentStorage()
    with transaction.atomic(), documentary_backend():
        one(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
            [f"sii_envios:{org_id_s}:{dte['id']}"],
        )
        row = one(
            "SELECT * FROM public.sii_envios WHERE id=%s",
            [str(row["id"])],
            "sii_envio_missing",
        )
        if row["status"] != "PENDING":
            return _envio_public(row)
        payload = _payload(row)
        if not row["track_id"]:
            # A previous attempt may have reached the SII without its response
            # reaching us — no TRACKID was ever recorded. Never auto-resubmit:
            # the mock is exempt (its track id is a pure function of the same
            # bytes, so a retry cannot duplicate), everything else requires the
            # explicit human recovery decision (`resubmit`).
            attempted_at = _ts(payload.get("submit_attempted_at"))
            if (
                attempted_at is not None
                and client.adapter != "mock"
                and not resubmit
            ):
                raise contract_error(
                    409,
                    "sii_envio_uncertain",
                    "El intento anterior no confirmó recepción — confirme el "
                    "reintento para enviar el mismo sobre nuevamente.",
                )
            # Atomic claim: only the request that lands this guarded lease may
            # submit — the advisory lock ends before the network call, so a
            # racing resubmit must be excluded *here*, at the row. A loser
            # reports the current state instead of posting a duplicate.
            claimed = rows(
                "UPDATE public.sii_envios "
                "SET payload_json = payload_json || %s::jsonb "
                "WHERE id=%s AND status='PENDING' AND track_id IS NULL AND ("
                "payload_json->>'submit_inflight_until' IS NULL OR "
                "(payload_json->>'submit_inflight_until')::timestamptz < %s"
                ") RETURNING *",
                [
                    json.dumps(
                        {
                            "submit_attempted_at": timezone.now().isoformat(),
                            "submit_resubmitted": attempted_at is not None,
                            "submit_inflight_until": (
                                timezone.now() + timedelta(seconds=90)
                            ).isoformat(),
                        }
                    ),
                    str(row["id"]),
                    timezone.now().isoformat(),
                ],
            )
            if not claimed:
                row = one(
                    "SELECT * FROM public.sii_envios WHERE id=%s",
                    [str(row["id"])],
                    "sii_envio_missing",
                )
                return _envio_public(row)
            row = claimed[0]
    row_payload = _payload(row)
    if not row["track_id"]:
        if envelope is None:
            envelope = storage.download(str(row["storage_object_key"]))
        receipt = client.submit(
            envelope,
            rut_emisor=str(row_payload["emisor"]["rut"]),
            rut_envia=str(row_payload["envia"]),
        )
        with transaction.atomic(), documentary_backend():
            one(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                [f"sii_envios:{org_id_s}:{dte['id']}"],
            )
            updated = rows(
                "UPDATE public.sii_envios SET track_id=%s, glosa=%s,"
                "payload_json = payload_json || %s::jsonb "
                "WHERE id=%s AND status='PENDING' AND track_id IS NULL RETURNING *",
                [
                    receipt.get("track_id"),
                    receipt.get("glosa"),
                    json.dumps(
                        {
                            "adapter": client.adapter,
                            "track_id": receipt.get("track_id"),
                        }
                    ),
                    str(row["id"]),
                ],
            )
            # A concurrent send may have recorded its receipt first — re-read
            # the winner instead of clobbering it.
            row = updated[0] if updated else one(
                "SELECT * FROM public.sii_envios WHERE id=%s",
                [str(row["id"])],
                "sii_envio_missing",
            )
    verdict = client.query_status(
        track_id=str(row["track_id"]),
        rut_emisor=str(row_payload["emisor"]["rut"]),
    )
    if verdict is not None:
        with transaction.atomic(), documentary_backend():
            if verdict.get("status") in ("ACCEPTED", "REJECTED"):
                updated = rows(
                    "UPDATE public.sii_envios SET status=%s, glosa=%s "
                    "WHERE id=%s AND status='PENDING' RETURNING *",
                    [verdict["status"], verdict.get("glosa"), str(row["id"])],
                )
                row = updated[0] if updated else one(
                    "SELECT * FROM public.sii_envios WHERE id=%s",
                    [str(row["id"])],
                    "sii_envio_missing",
                )
            elif verdict.get("glosa"):
                # A stale PENDING verdict must never overwrite a finalized
                # row's explanation — same guarded update, loser re-reads.
                updated = rows(
                    "UPDATE public.sii_envios SET glosa=%s "
                    "WHERE id=%s AND status='PENDING' RETURNING *",
                    [verdict["glosa"], str(row["id"])],
                )
                row = updated[0] if updated else one(
                    "SELECT * FROM public.sii_envios WHERE id=%s",
                    [str(row["id"])],
                    "sii_envio_missing",
                )
    return _envio_public(row)


def send_invoice_envio(
    *,
    org_id: UUID,
    project_id: UUID,
    invoice_id: UUID,
    actor_id: UUID,
    resubmit: bool = False,
) -> dict:
    """Submit a stamped factura's DTE to the SII."""
    org_id_s, project_id_s = str(org_id), str(project_id)
    with transaction.atomic(), documentary_backend():
        dte = _parent_dte(
            org_id_s=org_id_s,
            project_id_s=project_id_s,
            invoice_id_s=str(invoice_id),
        )
    return _send_dte_envio(
        org_id_s=org_id_s,
        project_id_s=project_id_s,
        dte=dte,
        actor_id=actor_id,
        resubmit=resubmit,
    )


def send_credit_note_envio(
    *,
    org_id: UUID,
    project_id: UUID,
    credit_note_id: UUID,
    actor_id: UUID,
    resubmit: bool = False,
) -> dict:
    """Submit a stamped nota de crédito's DTE-61 to the SII — the annulment
    only exists for the tax authority once its envelope lands."""
    org_id_s, project_id_s = str(org_id), str(project_id)
    with transaction.atomic(), documentary_backend():
        dte = _parent_dte(
            org_id_s=org_id_s,
            project_id_s=project_id_s,
            credit_note_id_s=str(credit_note_id),
        )
    return _send_dte_envio(
        org_id_s=org_id_s,
        project_id_s=project_id_s,
        dte=dte,
        actor_id=actor_id,
        resubmit=resubmit,
    )


def send_dispatch_note_envio(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    resubmit: bool = False,
) -> dict:
    """Submit a stamped guía de despacho's DTE-52 to the SII."""
    org_id_s, order_id_s = str(org_id), str(order_id)
    with transaction.atomic(), documentary_backend():
        order = one(
            "SELECT id, project_id FROM public.orders WHERE id=%s AND org_id=%s",
            [order_id_s, org_id_s],
            "work_order_not_found",
        )
        note = one(
            "SELECT id FROM public.dispatch_notes "
            "WHERE work_order_id=%s AND org_id=%s AND voided_at IS NULL",
            [order_id_s, org_id_s],
            "dispatch_note_missing",
        )
        dte = _parent_dte(
            org_id_s=org_id_s,
            project_id_s=str(order["project_id"]),
            dispatch_note_id_s=str(note["id"]),
        )
    return _send_dte_envio(
        org_id_s=org_id_s,
        project_id_s=str(order["project_id"]),
        dte=dte,
        actor_id=actor_id,
        resubmit=resubmit,
    )


def envios_by_invoice(*, org_id: UUID, project_id: UUID) -> dict:
    """invoice_id → light envío badge for the cobranza invoice listing —
    only the parent factura's envío."""
    return {
        str(row["invoice_id"]): {
            "id": str(row["id"]),
            "status": row["status"],
            "track_id": row["track_id"],
            "attempted": bool(row["attempted"]),
        }
        for row in rows(
            "SELECT e.id, e.status, e.track_id, d.invoice_id, "
            "(e.payload_json->'submit_attempted_at' IS NOT NULL) AS attempted "
            "FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "WHERE e.org_id=%s AND e.project_id=%s AND d.credit_note_id IS NULL",
            [str(org_id), str(project_id)],
        )
    }


def envios_by_credit_note(*, org_id: UUID, project_id: UUID) -> dict:
    """credit_note_id → light envío badge for the cobranza invoice listing."""
    return {
        str(row["credit_note_id"]): {
            "id": str(row["id"]),
            "status": row["status"],
            "track_id": row["track_id"],
            "attempted": bool(row["attempted"]),
        }
        for row in rows(
            "SELECT e.id, e.status, e.track_id, d.credit_note_id, "
            "(e.payload_json->'submit_attempted_at' IS NOT NULL) AS attempted "
            "FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "WHERE e.org_id=%s AND e.project_id=%s AND d.credit_note_id IS NOT NULL",
            [str(org_id), str(project_id)],
        )
    }


def envios_by_dispatch_note(*, org_id: UUID) -> dict:
    """dispatch_note_id → light envío badge for production order detail."""
    return {
        str(row["dispatch_note_id"]): {
            "id": str(row["id"]),
            "status": row["status"],
            "track_id": row["track_id"],
            "attempted": bool(row["attempted"]),
        }
        for row in rows(
            "SELECT e.id, e.status, e.track_id, d.dispatch_note_id, "
            "(e.payload_json->'submit_attempted_at' IS NOT NULL) AS attempted "
            "FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "WHERE e.org_id=%s AND d.dispatch_note_id IS NOT NULL",
            [str(org_id)],
        )
    }


def invoice_envio_access(*, org_id: UUID, project_id: UUID, invoice_id: UUID) -> dict:
    """Read the envío of an invoice's DTE — public row plus a short-lived
    signed URL to the sealed envelope. The project filter keeps an invoice
    id from another route ever resolving this org's evidence."""
    with documentary_backend():
        found = rows(
            "SELECT e.* FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "WHERE e.org_id=%s AND e.project_id=%s AND d.invoice_id=%s "
            "AND d.project_id=%s AND d.credit_note_id IS NULL",
            [str(org_id), str(project_id), str(invoice_id), str(project_id)],
        )
        if not found:
            raise contract_error(
                404, "sii_envio_missing", "El DTE de la factura no fue enviado."
            )
        row = found[0]
    storage = SupabaseDocumentStorage()
    out = _envio_public(row)
    out["signed_url"] = storage.signed_url(
        str(row["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
    )
    return out


def credit_note_envio_access(
    *, org_id: UUID, project_id: UUID, credit_note_id: UUID
) -> dict:
    """Read the envío of a nota de crédito's DTE — same project scoping."""
    with documentary_backend():
        found = rows(
            "SELECT e.* FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "WHERE e.org_id=%s AND e.project_id=%s AND d.credit_note_id=%s",
            [str(org_id), str(project_id), str(credit_note_id)],
        )
        if not found:
            raise contract_error(
                404,
                "sii_envio_missing",
                "El DTE de la nota de crédito no fue enviado.",
            )
        row = found[0]
    storage = SupabaseDocumentStorage()
    out = _envio_public(row)
    out["signed_url"] = storage.signed_url(
        str(row["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
    )
    return out


def dispatch_note_envio_access(*, org_id: UUID, order_id: UUID) -> dict:
    """Read the envío of a guía's DTE, resolved by work order."""
    with documentary_backend():
        found = rows(
            "SELECT e.* FROM public.sii_envios e "
            "JOIN public.project_dtes d ON d.id = e.dte_id "
            "JOIN public.dispatch_notes n ON n.id = d.dispatch_note_id "
            "WHERE e.org_id=%s AND n.work_order_id=%s",
            [str(org_id), str(order_id)],
        )
        if not found:
            raise contract_error(
                404,
                "sii_envio_missing",
                "El DTE de la guía no fue enviado.",
            )
        row = found[0]
    storage = SupabaseDocumentStorage()
    out = _envio_public(row)
    out["signed_url"] = storage.signed_url(
        str(row["storage_object_key"]), expires_in=SIGNED_URL_TTL_SECONDS
    )
    return out
