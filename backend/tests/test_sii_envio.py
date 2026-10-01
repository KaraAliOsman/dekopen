"""SII envío — certificate upload/wrapping, envelope signing, send + replay."""

import base64
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as utc_timezone
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

from authentication.errors import ContractAPIException, contract_error
from projects import sii, sii_envio


class _Storage:
    def __init__(self):
        self.uploads = []
        self.deleted = []
        self.objects = {}

    def upload_immutable(self, object_key, content, content_type):
        self.uploads.append((object_key, content, content_type))
        self.objects[object_key] = content

    def download(self, object_key):
        return self.objects[object_key]

    def delete_object(self, object_key):
        self.deleted.append(object_key)

    def signed_url(self, object_key, expires_in=None):
        return f"https://storage.test/{object_key}?exp={expires_in}"


@contextmanager
def _noop(*args, **kwargs):
    yield


def _rsa_key():
    return rsa.generate_private_key(3, 2048)


# A fake issuing authority — the service rejects self-signed certificates, so
# test leaves are always CA-signed, mirroring SII-issued personal certs.
_CA_KEY = _rsa_key()


def _ca_cert():
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Autoridad Prueba SII")])
    now = datetime.now(utc_timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(_CA_KEY.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=400))
        .not_valid_after(now + timedelta(days=3650))
        .sign(_CA_KEY, hashes.SHA256())
    )


_CA_CERT = _ca_cert()


def _leaf(key, rut="13037614-2", expired=False, signing=True):
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Firmante Prueba"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, rut),
        ]
    )
    now = datetime.now(utc_timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(_CA_CERT.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=400 if expired else 1))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=365))
        .add_extension(
            x509.KeyUsage(
                digital_signature=signing,
                content_commitment=signing,
                key_encipherment=not signing,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )
    return builder.sign(_CA_KEY, hashes.SHA256())


def _self_signed(key, rut="13037614-2", expired=False):
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Firmante Prueba"),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, rut),
        ]
    )
    now = datetime.now(utc_timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=400 if expired else 1))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=365))
    )
    return builder.sign(key, hashes.SHA256())


def _pfx(password=b"secret", rut="13037614-2", key=None, expired=False, signing=True):
    key = key or _rsa_key()
    cert = _leaf(key, rut=rut, expired=expired, signing=signing)
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"cert", key=key, cert=cert, cas=None, encryption_algorithm=encryption
    ), key, cert


def _cert_row(org_id, pfx, password="secret", over=None):
    file_hash = sii_envio._sha256(pfx)
    aad = sii_envio._cert_aad(str(org_id), file_hash)
    now = datetime.now(utc_timezone.utc)
    row = {
        "id": uuid4(),
        "org_id": org_id,
        "subject": "CN=Firmante Prueba",
        "rut_firma": "13037614-2",
        "serial_number": "123",
        "valid_from": now - timedelta(days=1),
        "valid_to": now + timedelta(days=365),
        "pfx_wrapped": sii._wrap_rsask(base64.b64encode(pfx).decode("ascii"), aad),
        "password_wrapped": sii._wrap_rsask(password, aad) if password else None,
        "file_sha256": file_hash,
        "nro_resol": 0,
        "fch_resol": "2026-10-01",
        "active": True,
        "uploaded_by": uuid4(),
        "created_at": now,
    }
    row.update(over or {})
    return row


def _dte_xml(folio=7, tipo=33):
    return (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        '<DTE xmlns="http://www.sii.cl/SiiDte" version="1.0">'
        f'<Documento ID="F{tipo}T{folio}">'
        f"<Encabezado><IdDoc><TipoDTE>{tipo}</TipoDTE>"
        f"<Folio>{folio}</Folio><FchEmis>2026-10-02</FchEmis></IdDoc>"
        "<Emisor><RUTEmisor>76123456-0</RUTEmisor></Emisor>"
        "<Receptor><RUTRecep>76543210-3</RUTRecep></Receptor>"
        "<Totales><MntTotal>1190</MntTotal></Totales></Encabezado>"
        "<Detalle><NroLinDet>1</NroLinDet><NmbItem>VENTANA</NmbItem>"
        "<QtyItem>1</QtyItem><MontoItem>1000</MontoItem></Detalle>"
        f'<TED version="1.0"><DD><RE>76123456-0</RE><TD>{tipo}</TD>'
        f"<F>{folio}</F><ND>0</ND><RR>76543210-3</RR><RSR>C</RSR>"
        "<MNT>1190</MNT><IT1>VENTANA</IT1><CAF/>"
        "<TSTED>2026-10-02T10:00:00</TSTED></DD>"
        '<FRMT algoritmo="SHA1withRSA">eA==</FRMT></TED>'
        "<TmstFirma>2026-10-02T10:00:00</TmstFirma>"
        "</Documento></DTE>"
    ).encode("iso-8859-1")


def _dte_row(org_id, invoice_id, caf_id, folio=7, over=None):
    row = {
        "id": uuid4(),
        "org_id": org_id,
        "project_id": uuid4(),
        "invoice_id": invoice_id,
        "credit_note_id": None,
        "dte_type": 33,
        "folio": folio,
        "caf_id": caf_id,
        "storage_object_key": f"org_{org_id}/dtes/dte33-{folio}.xml",
        "issued_at": "2026-10-02T10:00:00+00:00",
    }
    row.update(over or {})
    return row


def _patch_envio(
    monkeypatch,
    storage,
    *,
    dte=None,
    existing_envio=None,
    certs=None,
    caf=None,
    client=None,
    insert_row=None,
    order=None,
    note=None,
):
    state = {"inserted": None}
    monkeypatch.setenv("SII_WS_ENVIO_MOCK", "1")
    monkeypatch.delenv("SII_WS_ENVIO_URL", raising=False)
    monkeypatch.delenv("SII_WS_STATUS_URL", raising=False)
    monkeypatch.delenv("SII_WS_TOKEN", raising=False)

    def fake_one(sql, params=None, *args, **kw):
        text = str(sql)
        if "INSERT INTO public.sii_envios" in text:
            row = insert_row or {
                "id": uuid4(),
                "org_id": params[0],
                "project_id": params[1],
                "dte_id": (dte[0]["id"] if dte else uuid4()),
                "status": "PENDING",
                "track_id": None,
                "glosa": None,
                "payload_json": {"emisor": {"rut": "76123456-0"}, "envia": "13037614-2"},
                "storage_object_key": "org_x/envios/e.xml",
                "sent_at": "2026-10-03T10:00:00+00:00",
            }
            state["inserted"] = row
            return row
        if "SELECT * FROM public.sii_envios" in text:
            if existing_envio:
                return dict(existing_envio[0])
            return dict(state["inserted"] or {})
        if "UPDATE public.sii_envios" in text:
            row = dict(state["inserted"] or (existing_envio or [{}])[0])
            if "SET payload_json = payload_json ||" in text:
                payload = row.get("payload_json") or {}
                if isinstance(payload, str):
                    payload = json.loads(payload)
                row["payload_json"] = {**payload, **json.loads(params[0])}
            elif "SET track_id" in text:
                row.update({"track_id": params[0], "glosa": params[1]})
            elif "SET status" in text:
                row.update({"status": params[0], "glosa": params[1]})
            else:
                row.update({"glosa": params[0]})
            state["inserted"] = row
            return row
        if "INSERT INTO public.sii_certificates" in text:
            return {
                "id": uuid4(),
                "org_id": uuid4(),
                "subject": params[1],
                "rut_firma": params[2],
                "serial_number": params[3],
                "valid_from": params[4],
                "valid_to": params[5],
                "pfx_wrapped": params[6],
                "password_wrapped": params[7],
                "file_sha256": params[8],
                "nro_resol": params[9],
                "fch_resol": params[10],
                "active": True,
                "created_at": "2026-10-03T10:00:00+00:00",
            }
        if "FROM public.sii_cafs" in text:
            if caf is None:
                raise contract_error(404, "sii_caf_missing", "x")
            return caf
        if "FROM public.orders" in text:
            if order is None:
                raise contract_error(404, "work_order_not_found", "x")
            return order
        if "FROM public.dispatch_notes" in text:
            if note is None:
                raise contract_error(404, "dispatch_note_missing", "x")
            return note
        if "pg_advisory_xact_lock" in text:
            return {}
        return {}

    def fake_rows(sql, params=None):
        if "FROM public.project_dtes" in sql:
            found = list(dte or [])
            if "project_id=%s" in sql and params is not None:
                found = [r for r in found if str(r["project_id"]) == str(params[1])]
            return found
        if "UPDATE public.sii_envios" in sql:
            row = dict(state["inserted"] or (existing_envio or [{}])[0])
            payload = row.get("payload_json") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            if "SET track_id" in sql:
                if row.get("status") != "PENDING" or row.get("track_id"):
                    return []
                row.update({"track_id": params[0], "glosa": params[1]})
                row["payload_json"] = {**payload, **json.loads(params[2])}
            elif "SET status" in sql:
                if row.get("status") != "PENDING":
                    return []
                row.update({"status": params[0], "glosa": params[1]})
            elif "SET glosa" in sql:
                # Stale PENDING verdicts can't overwrite a finalized row.
                if row.get("status") != "PENDING":
                    return []
                row.update({"glosa": params[0]})
            elif "submit_inflight_until" in sql:
                # The atomic submission claim honors the same guards the real
                # WHERE carries: pending, untracked, and no live lease.
                if row.get("status") != "PENDING" or row.get("track_id"):
                    return []
                until = payload.get("submit_inflight_until")
                if until and until >= str(params[2]):
                    return []
                row["payload_json"] = {**payload, **json.loads(params[0])}
            state["inserted"] = row
            return [row]
        if "FROM public.sii_envios" in sql:
            found = [dict(state["inserted"])] if state["inserted"] is not None else []
            found += list(existing_envio or [])
            if "project_id=%s" in sql and params is not None:
                found = [r for r in found if str(r.get("project_id")) == str(params[1])]
            return found
        if "FROM public.sii_certificates" in sql and "SET active=false" in sql:
            return []
        if "FROM public.sii_certificates" in sql:
            return list(certs or [])
        return []

    monkeypatch.setattr(sii_envio, "one", fake_one)
    monkeypatch.setattr(sii_envio, "rows", fake_rows)
    monkeypatch.setattr(sii, "_kek", lambda: b"\x01" * 32)
    monkeypatch.setattr(sii_envio, "SupabaseDocumentStorage", lambda: storage)
    monkeypatch.setattr(sii_envio.transaction, "atomic", _noop)
    monkeypatch.setattr(sii_envio, "documentary_backend", _noop)
    if client is not None:
        monkeypatch.setattr(sii_envio, "_sii_client", lambda: client)
    return state


def _caf(org_id):
    return {
        "id": uuid4(),
        "org_id": org_id,
        "rut_emisor": "76123456-0",
        "razon_social": "Ventanas Prueba SpA",
    }


def test_upload_certificate_wraps_and_stores():
    storage = _Storage()
    org_id = uuid4()
    pfx, _key, cert = _pfx()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage)
        result = sii_envio.upload_certificate(
            org_id=org_id,
            actor_id=uuid4(),
            pfx_b64=base64.b64encode(pfx).decode("ascii"),
            password="secret",
            nro_resol=0,
            fch_resol="2026-10-01",
        )
    assert result["rut_firma"] == "13037614-2"
    assert result["active"] is True


def test_upload_certificate_rejects_bad_base64():
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64="%%%",
                password=None,
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_invalid"


def test_upload_certificate_rejects_no_rut_cert():
    # name without any RUT: a cert whose subject carries no RUT at all
    key = _rsa_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Sin Rut")])
    now = datetime.now(utc_timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(_CA_CERT.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(_CA_KEY, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"c",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64=base64.b64encode(pfx).decode("ascii"),
                password=None,
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_rut_missing"


def test_upload_certificate_rejects_expired():
    pfx, _key, _cert = _pfx(expired=True)
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64=base64.b64encode(pfx).decode("ascii"),
                password="secret",
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_expired"


def test_upload_certificate_rejects_non_rsa():
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _leaf(key)
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"c",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64=base64.b64encode(pfx).decode("ascii"),
                password=None,
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_not_rsa"


def _verify_signature(target, cert):
    """Verify one enveloped RSA-SHA1 signature on ``target``: DigestValue must
    match sha1(c14n(target)) and SignatureValue must verify over
    c14n(SignedInfo) with the cert's public key. SII shape: the Signature is
    the target's *sibling* — ``<DTE><Documento/><Signature/></DTE>`` and
    ``<EnvioDTE><SetDTE/><Signature/></EnvioDTE>`` — not a nested child.
    Verification removes it from the shared parent (the digestable subtree
    never contains it anyway)."""
    parent = target.getparent()
    sig = target.getnext()
    assert sig is not None and sig.tag == f"{{{sii_envio._DS}}}Signature"
    assert sig.getparent() is parent  # schema-required sibling placement
    signed_info = sig.find(f"{{{sii_envio._DS}}}SignedInfo")
    digest_value = signed_info.find(
        f"{{{sii_envio._DS}}}Reference/{{{sii_envio._DS}}}DigestValue"
    ).text
    signature_b64 = sig.find(f"{{{sii_envio._DS}}}SignatureValue").text
    cert.public_key().verify(
        base64.b64decode(signature_b64),
        sii_envio._c14n(signed_info),
        padding.PKCS1v15(),
        hashes.SHA1(),
    )
    parent.remove(sig)
    try:
        computed = base64.b64encode(
            hashlib.sha1(sii_envio._c14n(target)).digest()
        ).decode("ascii")
        assert computed == digest_value
    finally:
        target.addnext(sig)


def test_send_envio_seals_signed_envelope_and_records_track():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"], folio=7)
    pfx, _key, cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=7)
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("SII_WS_ENVIO_URL", raising=False)
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    assert result["status"] == "ACCEPTED"
    assert result["track_id"].startswith("MOCK-")
    envelope_key, envelope, media = storage.uploads[0]
    assert envelope_key.endswith(".xml") and media == "application/xml"
    assert "<SubTotDTE><TpoDTE>33</TpoDTE><NroDTE>1</NroDTE>" in envelope.decode(
        "iso-8859-1"
    )
    root = etree.fromstring(envelope)
    assert root.tag == "{http://www.sii.cl/SiiDte}EnvioDTE"
    caratula = root.find("{http://www.sii.cl/SiiDte}SetDTE/{http://www.sii.cl/SiiDte}Caratula")
    assert caratula.findtext("{http://www.sii.cl/SiiDte}RutReceptor") == "60803000-K"
    assert caratula.findtext("{http://www.sii.cl/SiiDte}RutEnvia") == "13037614-2"
    documento = sii_envio._find_id(root, "F33T7")
    _verify_signature(documento, cert)
    set_dte = sii_envio._find_id(root, "SetDoc")
    _verify_signature(set_dte, cert)


def test_send_envio_escapes_non_latin1_characters_in_envelope():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"], folio=8)
    pfx, _key, _cert = _pfx()
    dte_bytes = _dte_xml(folio=8).replace(
        b"VENTANA", "VENTANA &#8212; \xda\xd1O".encode("latin-1"))
    storage.objects[dte["storage_object_key"]] = dte_bytes
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("SII_WS_ENVIO_URL", raising=False)
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    _key, envelope, _media = storage.uploads[0]
    assert b"&#8212;" in envelope
    assert b"\xe2\x80\x94" not in envelope
    assert b"\xda\xd1" in envelope
    root = etree.fromstring(envelope)
    item = root.findtext(".//{http://www.sii.cl/SiiDte}NmbItem")
    assert item == "VENTANA — ÚÑO"


def test_send_envio_requires_dte():
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage(), dte=[])
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=uuid4(), project_id=uuid4(), invoice_id=uuid4(), actor_id=uuid4()
            )
    assert error.value.contract_code == "sii_dte_missing"


def test_send_credit_note_envio_submits_dte61():
    # The NC's DTE-61 resolves by credit_note_id — the annulment only
    # exists for the SII once its envelope is submitted.
    storage = _Storage()
    org_id, invoice_id, cn_id = uuid4(), uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(
        org_id, invoice_id, caf["id"], folio=9,
        over={"dte_type": 61, "credit_note_id": cn_id},
    )
    pfx, _key, cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=9, tipo=61)
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("SII_WS_ENVIO_URL", raising=False)
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        result = sii_envio.send_credit_note_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            credit_note_id=cn_id,
            actor_id=uuid4(),
        )
    assert result["status"] == "ACCEPTED"
    assert result["track_id"].startswith("MOCK-")
    root = etree.fromstring(storage.uploads[0][1])
    assert root.tag == "{http://www.sii.cl/SiiDte}EnvioDTE"
    documento = sii_envio._find_id(root, "F61T9")
    _verify_signature(documento, cert)


def test_send_credit_note_envio_requires_dte():
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage(), dte=[])
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_credit_note_envio(
                org_id=uuid4(),
                project_id=uuid4(),
                credit_note_id=uuid4(),
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_dte_missing"


def test_send_dispatch_note_envio_resolves_through_order():
    # Production routes name a work order; the envío resolves
    # order → guía → DTE-52 and submits the same sealed envelope.
    storage = _Storage()
    org_id, order_id, note_id = uuid4(), uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(
        org_id, None, caf["id"], folio=4,
        over={"dte_type": 52, "invoice_id": None, "dispatch_note_id": note_id},
    )
    pfx, _key, cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=4, tipo=52)
    order = {"id": order_id, "org_id": org_id, "project_id": dte["project_id"]}
    note = {"id": note_id, "work_order_id": order_id, "org_id": org_id}
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("SII_WS_ENVIO_URL", raising=False)
        _patch_envio(
            mp, storage, dte=[dte], certs=[], caf=caf,
            order=order, note=note,
        )
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(
            mp, storage, dte=[dte], certs=[cert_row], caf=caf,
            order=order, note=note,
        )
        result = sii_envio.send_dispatch_note_envio(
            org_id=org_id, order_id=order_id, actor_id=uuid4()
        )
    assert result["status"] == "ACCEPTED"
    root = etree.fromstring(storage.uploads[0][1])
    documento = sii_envio._find_id(root, "F52T4")
    _verify_signature(documento, cert)


def test_send_dispatch_note_envio_requires_note():
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(
            mp, _Storage(), dte=[],
            order={"id": uuid4(), "org_id": uuid4(), "project_id": uuid4()},
        )
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_dispatch_note_envio(
                org_id=uuid4(), order_id=uuid4(), actor_id=uuid4()
            )
    assert error.value.contract_code == "dispatch_note_missing"


def test_send_envio_requires_certificate():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_certificate_missing"


def test_send_envio_rejects_expired_certificate():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(
            org_id,
            pfx,
            over={"valid_to": datetime.now(utc_timezone.utc) - timedelta(days=1)},
        )
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_cert_expired"


def test_send_envio_replays_existing_row():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    envio = {
        "id": uuid4(),
        "dte_id": dte["id"],
        "project_id": dte["project_id"],
        "status": "ACCEPTED",
        "track_id": "MOCK-1",
        "glosa": None,
        "sent_at": "2026-10-03T10:00:00+00:00",
    }
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], existing_envio=[envio], caf=caf)
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    assert result["id"] == str(envio["id"])
    assert storage.uploads == []


def test_envio_access_returns_signed_url():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    dte = _dte_row(org_id, invoice_id, uuid4())
    envio = {
        "id": uuid4(),
        "dte_id": dte["id"],
        "project_id": dte["project_id"],
        "status": "ACCEPTED",
        "track_id": "MOCK-1",
        "glosa": "ok",
        "sent_at": "2026-10-03T10:00:00+00:00",
        "storage_object_key": "org_x/envios/e.xml",
    }

    def fake_rows(sql, params=None):
        if "FROM public.sii_envios" in str(sql):
            return [envio]
        return []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio, "rows", fake_rows)
        mp.setattr(sii_envio, "SupabaseDocumentStorage", lambda: storage)
        mp.setattr(sii_envio, "documentary_backend", _noop)
        result = sii_envio.invoice_envio_access(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
        )
    assert result["signed_url"].startswith("https://storage.test/")
    assert result["track_id"] == "MOCK-1"


def test_envio_access_missing_returns_404():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio, "rows", lambda *a, **k: [])
        mp.setattr(sii_envio, "documentary_backend", _noop)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.invoice_envio_access(
                org_id=uuid4(), project_id=uuid4(), invoice_id=uuid4()
            )
    assert error.value.contract_code == "sii_envio_missing"


def _pending_envio(dte, **over):
    row = {
        "id": uuid4(),
        "dte_id": dte["id"],
        "project_id": dte["project_id"],
        "status": "PENDING",
        "track_id": None,
        "glosa": None,
        "payload_json": {"emisor": {"rut": "76123456-0"}, "envia": "13037614-2"},
        "storage_object_key": f"org_{dte['org_id']}/envios/e.xml",
        "sent_at": "2026-10-03T10:00:00+00:00",
    }
    row.update(over)
    return row


class _RecordingClient:
    adapter = "mock"

    def __init__(self, verdict=None, fail_submit=False):
        self.submits = 0
        self.queries = 0
        self.verdict = verdict or {"status": "ACCEPTED", "glosa": "ok"}
        self.fail_submit = fail_submit

    def submit(self, content, *, rut_emisor, rut_envia):
        self.submits += 1
        if self.fail_submit:
            raise ContractAPIException(
                status_code=503, code="sii_envio_unreachable", detail="x"
            )
        return {"track_id": "TRK-9", "glosa": "receipt"}

    def query_status(self, *, track_id, rut_emisor):
        self.queries += 1
        return self.verdict


def test_send_envio_resumes_pending_row_without_reseal():
    """A PENDING row committed before the network outage is resumed — the same
    stored envelope is submitted; nothing is re-rendered or re-inserted."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    dte = _dte_row(org_id, invoice_id, uuid4())
    envio = _pending_envio(dte)
    storage.objects[envio["storage_object_key"]] = _dte_xml(folio=9)
    client = _RecordingClient()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(
            mp, storage, dte=[dte], existing_envio=[envio], caf=_caf(org_id),
            client=client,
        )
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    assert result["status"] == "ACCEPTED"
    assert result["track_id"] == "TRK-9"
    assert client.submits == 1
    assert client.queries == 1
    assert storage.uploads == []


def test_send_envio_pending_with_track_only_reconciles():
    """A TRACKID was already recorded — the retry never re-submits; it only
    queries the verdict."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    dte = _dte_row(org_id, invoice_id, uuid4())
    envio = _pending_envio(dte, track_id="TRK-OLD")
    client = _RecordingClient(verdict={"status": "REJECTED", "glosa": "dato malo"})
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(
            mp, storage, dte=[dte], existing_envio=[envio], caf=_caf(org_id),
            client=client,
        )
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    assert result["status"] == "REJECTED"
    assert client.submits == 0
    assert client.queries == 1


def test_send_envio_submit_failure_leaves_pending_row():
    """Transport failure → the envío stays PENDING and the error surfaces —
    the sealed evidence is never deleted and the retry can resume."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=7)
    client = _RecordingClient(fail_submit=True)
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf, client=client)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(
            mp, storage, dte=[dte], certs=[cert_row], caf=caf, client=client
        )
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_envio_unreachable"
    assert client.submits == 1
    assert storage.uploads  # the sealed envelope was committed, not purged


def test_send_envio_foreign_project_is_not_found():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    dte = _dte_row(org_id, invoice_id, uuid4())
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], caf=_caf(org_id))
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=uuid4(),  # not the DTE's project
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_dte_missing"


def test_send_envio_requires_adapter_configuration():
    """Production with no SII endpoint and no explicit mock flag fails closed —
    the row may seal PENDING but no simulated acceptance is recorded."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=7)
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        mp.delenv("SII_WS_ENVIO_MOCK", raising=False)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_envio_unconfigured"


def test_sii_client_rejects_non_sii_endpoint():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SII_WS_ENVIO_URL", "http://169.254.169.254/latest")
        mp.setenv("SII_WS_TOKEN", "t")
        with pytest.raises(ContractAPIException) as error:
            sii_envio._sii_client()
    assert error.value.contract_code == "sii_envio_endpoint_forbidden"


def test_sii_client_requires_token_for_real_endpoint():
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SII_WS_ENVIO_URL", "https://palena.sii.cl/cgi-bin/UploadEnvio")
        mp.delenv("SII_WS_TOKEN", raising=False)
        with pytest.raises(ContractAPIException) as error:
            sii_envio._sii_client()
    assert error.value.contract_code == "sii_envio_unconfigured"


def test_http_client_posts_sii_multipart_contract():
    """The real adapter speaks the documented UploadEnvio shape: RUTs split
    into sender/company fields, archivo file part, TOKEN cookie."""
    calls = {}

    def fake_post(url, **kw):
        calls["url"] = url
        calls["kw"] = kw

        class _R:
            status_code = 200
            text = "<RESP_UPLOAD><TRACKID>4242</TRACKID></RESP_UPLOAD>"

        return _R()

    client = sii_envio._HttpSiiClient(
        "https://palena.sii.cl/cgi-bin/UploadEnvio", None, "TOK"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio.httpx, "post", fake_post)
        out = client.submit(b"<x/>", rut_emisor="76123456-0", rut_envia="13037614-2")
    assert out["track_id"] == "4242"
    assert calls["kw"]["data"]["rutCompany"] == "76123456"
    assert calls["kw"]["data"]["dvCompany"] == "0"
    assert calls["kw"]["data"]["rutSender"] == "13037614"
    assert calls["kw"]["data"]["dvSender"] == "2"
    assert calls["kw"]["cookies"]["TOKEN"] == "TOK"
    assert calls["kw"]["follow_redirects"] is False
    assert "archivo" in calls["kw"]["files"]


def _attempted_pending(dte, **over):
    """A PENDING envío whose first submit attempt already ran but never
    confirmed a receipt — the uncertain-attempt state."""
    payload = {
        "emisor": {"rut": "76123456-0"},
        "envia": "13037614-2",
        "submit_attempted_at": "2026-10-03T10:00:00+00:00",
    }
    payload.update(over.pop("payload", {}))
    return _pending_envio(dte, payload_json=payload, **over)


class _WsClient(_RecordingClient):
    adapter = "sii-ws"


def test_send_envio_uncertain_attempt_never_auto_resubmits():
    """A prior attempt may have reached the SII — resubmitting identical
    bytes is a human decision, never an automatic retry."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    pending = _attempted_pending(dte, dte_id=dte["id"], project_id=dte["project_id"])
    client = _WsClient()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf, client=client)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(
            mp,
            storage,
            dte=[dte],
            existing_envio=[pending],
            certs=[cert_row],
            caf=caf,
            client=client,
        )
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_envio_uncertain"
    assert client.submits == 0


def test_send_envio_resubmit_is_the_explicit_recovery():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    pending = _attempted_pending(dte, dte_id=dte["id"], project_id=dte["project_id"])
    storage.objects[pending["storage_object_key"]] = _dte_xml(folio=9)
    client = _WsClient()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf, client=client)
        cert_row = _cert_row(org_id, pfx)
        state = _patch_envio(
            mp,
            storage,
            dte=[dte],
            existing_envio=[pending],
            certs=[cert_row],
            caf=caf,
            client=client,
        )
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
            resubmit=True,
        )
    assert client.submits == 1
    assert result["status"] == "ACCEPTED"
    payload = state["inserted"]["payload_json"]
    assert payload["submit_resubmitted"] is True


def test_send_envio_concurrent_resubmit_never_duplicates():
    """Two resubmits racing the same uncertain row: the atomic claim lets only
    one through — the loser gets the current state, never a second SII post."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    pending = _attempted_pending(
        dte,
        dte_id=dte["id"],
        project_id=dte["project_id"],
        payload={
            "submit_inflight_until": (
                datetime.now(utc_timezone.utc) + timedelta(minutes=5)
            ).isoformat(),
        },
    )
    client = _WsClient()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf, client=client)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(
            mp,
            storage,
            dte=[dte],
            existing_envio=[pending],
            certs=[cert_row],
            caf=caf,
            client=client,
        )
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
            resubmit=True,
        )
    assert result["status"] == "PENDING"
    assert client.submits == 0
    assert client.queries == 0


def test_send_envio_attempt_is_marked_before_submit():
    """Submit raises after the marker committed: the row keeps
    submit_attempted_at and the next call refuses the blind retry."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    storage.objects[dte["storage_object_key"]] = _dte_xml(folio=7)
    client = _WsClient(fail_submit=True)
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf, client=client)
        cert_row = _cert_row(org_id, pfx)
        state = _patch_envio(
            mp,
            storage,
            dte=[dte],
            certs=[cert_row],
            caf=caf,
            client=client,
        )
        with pytest.raises(ContractAPIException):
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
        payload = state["inserted"]["payload_json"]
        assert payload["submit_attempted_at"]
        assert client.submits == 1
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_envio_uncertain"
    assert client.submits == 1


def test_query_status_ignores_zero_rejection_count():
    """<RECHAZADOS>0</RECHAZADOS> is a count, not a verdict — only the ESTADO
    code decides ACCEPTED/REJECTED."""

    def fake_post(url, **kw):
        class _R:
            status_code = 200
            content = (
                b"<RESP_STATUS><TRACKID>9</TRACKID><ESTADO>EPR</ESTADO>"
                b"<GLOSA>procesado</GLOSA><RECHAZADOS>0</RECHAZADOS></RESP_STATUS>"
            )

        return _R()

    client = sii_envio._HttpSiiClient(
        "https://palena.sii.cl/cgi-bin/UploadEnvio",
        "https://palena.sii.cl/cgi-bin/QueryEstUp",
        "TOK",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio.httpx, "post", fake_post)
        verdict = client.query_status(track_id="9", rut_emisor="76123456-0")
    assert verdict["status"] == "ACCEPTED"


def test_query_status_maps_rechazado_verdict():
    def fake_post(url, **kw):
        class _R:
            status_code = 200
            content = (
                b"<RESP_STATUS><TRACKID>9</TRACKID><ESTADO>RPR</ESTADO>"
                b"<GLOSA>firma no v\xc3\xa1lida</GLOSA></RESP_STATUS>"
            )

        return _R()

    client = sii_envio._HttpSiiClient(
        "https://palena.sii.cl/cgi-bin/UploadEnvio",
        "https://palena.sii.cl/cgi-bin/QueryEstUp",
        "TOK",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio.httpx, "post", fake_post)
        verdict = client.query_status(track_id="9", rut_emisor="76123456-0")
    assert verdict["status"] == "REJECTED"
    assert verdict["glosa"] == "firma no válida"


def test_send_envio_rejects_not_yet_valid_certificate():
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"])
    pfx, _key, _cert = _pfx()
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(
            org_id,
            pfx,
            over={"valid_from": datetime.now(utc_timezone.utc) + timedelta(days=1)},
        )
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_cert_not_yet_valid"


def test_envio_entity_references_are_never_expanded():
    """A stored DTE smuggling an entity declaration fails closed — the
    hardened parser refuses the document and no envelope is ever sealed."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    caf = _caf(org_id)
    dte = _dte_row(org_id, invoice_id, caf["id"], folio=11)
    pfx, _key, _cert = _pfx()
    hostile = _dte_xml(folio=11).replace(
        b"<DTE ", b'<!DOCTYPE r [<!ENTITY x "INJECTED">]><DTE ', 1
    ).replace(b"VENTANA", b"&x;", 1)
    storage.objects[dte["storage_object_key"]] = hostile
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, storage, dte=[dte], certs=[], caf=caf)
        cert_row = _cert_row(org_id, pfx)
        _patch_envio(mp, storage, dte=[dte], certs=[cert_row], caf=caf)
        with pytest.raises(ContractAPIException) as error:
            sii_envio.send_invoice_envio(
                org_id=org_id,
                project_id=dte["project_id"],
                invoice_id=invoice_id,
                actor_id=uuid4(),
            )
    assert error.value.contract_code == "sii_dte_unreadable"
    assert storage.uploads == []


def test_query_status_epr_with_rejected_dte_is_rejected():
    """EPR means "processed", not "accepted" — a rejection counter inside the
    verdict makes the envío REJECTED even though the envelope code passed."""

    def fake_post(url, **kw):
        class _R:
            status_code = 200
            content = (
                b"<RESP_STATUS><TRACKID>9</TRACKID><ESTADO>EPR</ESTADO>"
                b"<GLOSA>procesado</GLOSA><ACEPTADOS>0</ACEPTADOS>"
                b"<RECHAZADOS>1</RECHAZADOS></RESP_STATUS>"
            )

        return _R()

    client = sii_envio._HttpSiiClient(
        "https://palena.sii.cl/cgi-bin/UploadEnvio",
        "https://palena.sii.cl/cgi-bin/QueryEstUp",
        "TOK",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio.httpx, "post", fake_post)
        verdict = client.query_status(track_id="9", rut_emisor="76123456-0")
    assert verdict["status"] == "REJECTED"


def test_query_status_epr_with_reparos_only_is_accepted():
    """REPAROS are accepted-with-corrections — the envelope is accepted."""

    def fake_post(url, **kw):
        class _R:
            status_code = 200
            content = (
                b"<RESP_STATUS><TRACKID>9</TRACKID><ESTADO>EPR</ESTADO>"
                b"<ACEPTADOS>0</ACEPTADOS><REPAROS>1</REPAROS>"
                b"<RECHAZADOS>0</RECHAZADOS></RESP_STATUS>"
            )

        return _R()

    client = sii_envio._HttpSiiClient(
        "https://palena.sii.cl/cgi-bin/UploadEnvio",
        "https://palena.sii.cl/cgi-bin/QueryEstUp",
        "TOK",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio.httpx, "post", fake_post)
        verdict = client.query_status(track_id="9", rut_emisor="76123456-0")
    assert verdict["status"] == "ACCEPTED"


def test_upload_certificate_rejects_self_signed():
    """An org's signer must be issued by an authority — a self-signed blob can
    never become the active certificate."""
    key = _rsa_key()
    cert = _self_signed(key)
    pfx = pkcs12.serialize_key_and_certificates(
        name=b"c",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"secret"),
    )
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64=base64.b64encode(pfx).decode("ascii"),
                password="secret",
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_self_signed"


def test_upload_certificate_rejects_non_signing_usage():
    pfx, _key, _cert = _pfx(signing=False)
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(mp, _Storage())
        with pytest.raises(ContractAPIException) as error:
            sii_envio.upload_certificate(
                org_id=uuid4(),
                actor_id=uuid4(),
                pfx_b64=base64.b64encode(pfx).decode("ascii"),
                password="secret",
                nro_resol=0,
                fch_resol="2026-10-01",
            )
    assert error.value.contract_code == "sii_cert_usage"


def test_certificate_status_reads_only_granted_columns():
    """The tenant-visible read must never touch the wrapped key material —
    authenticated only holds column grants on the metadata set."""
    seen = {}

    def fake_rows(sql, params=None):
        seen["sql"] = sql
        return []

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sii_envio, "rows", fake_rows)
        assert sii_envio.certificate_status(org_id=uuid4()) is None
    sql = seen["sql"]
    assert "SELECT *" not in sql
    assert "pfx_wrapped" not in sql
    assert "password_wrapped" not in sql


def test_cert_rut_accepts_dotted_form():
    """Signer RUTs may carry Chilean dot separators — the extraction must
    recognize them and normalize through the same mod-11 validation."""
    cert = _leaf(_rsa_key(), rut="13.037.614-2")
    assert sii_envio._cert_rut(cert) == "13037614-2"


def test_pending_verdict_glosa_update_is_pending_guarded():
    """A stale PENDING verdict writes its glosa only while the row is still
    PENDING — a finalized envío's explanation can never be overwritten."""
    storage = _Storage()
    org_id, invoice_id = uuid4(), uuid4()
    dte = _dte_row(org_id, invoice_id, uuid4())
    envio = _pending_envio(dte, track_id="TRK-OLD")
    client = _RecordingClient(verdict={"status": "PENDING", "glosa": "en revisión"})
    seen = []
    with pytest.MonkeyPatch.context() as mp:
        _patch_envio(
            mp, storage, dte=[dte], existing_envio=[envio],
            caf=_caf(org_id), client=client,
        )
        base = sii_envio.rows
        mp.setattr(
            sii_envio,
            "rows",
            lambda sql, params=None: (seen.append(str(sql)), base(sql, params))[1],
        )
        result = sii_envio.send_invoice_envio(
            org_id=org_id,
            project_id=dte["project_id"],
            invoice_id=invoice_id,
            actor_id=uuid4(),
        )
    assert result["status"] == "PENDING"
    assert result["glosa"] == "en revisión"
    glosa_updates = [sql for sql in seen if "SET glosa" in sql]
    assert glosa_updates and all("status='PENDING'" in sql for sql in glosa_updates)
