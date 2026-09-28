"""Parameter-evidence registry: declaration, server-stamped review, and
import-time attestation pinning. The DB layer is faked — SQL/RLS-level
enforcement is covered by pgTAP 172 against the live stack."""

from uuid import uuid4

import pytest

from authentication.errors import ContractAPIException
from catalogs import evidence


class _NullAtomic:
    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _RecordedBackend:
    """Captures every query the service issues and lets a test seed rows."""

    def __init__(self, canned=None):
        self.calls = []
        self._canned = canned if canned is not None else []

    def __call__(self, query, parameters=()):
        self.calls.append((query, parameters))
        return self._canned


@pytest.fixture
def backend(monkeypatch):
    recorded = _RecordedBackend()
    monkeypatch.setattr(evidence, "rows", recorded)
    monkeypatch.setattr(evidence, "catalog_backend", _NullAtomic())
    return recorded


def _declare_payload(**overrides):
    payload = {
        "authority_table": "profile_articles",
        "row_id": uuid4(),
        "field_name": "face_width_mm",
        "value_text": "78.00",
        "unit": "mm",
        "scope": "SYSTEM",
        "applicability": "hoja batiente",
        "source_document": "aluprof_mb86.pdf",
        "source_page": 12,
        "source_url": "https://example.test/doc.pdf",
    }
    payload.update(overrides)
    return payload


def test_declare_inserts_under_backend_role_with_server_actor(backend, monkeypatch):
    # authority row exists and is visible to the org
    monkeypatch.setattr(
        evidence,
        "_authority_row_visible",
        lambda org_id, table, row_id: {"id": row_id},
    )
    org, actor = uuid4(), uuid4()
    inserted = {
        "id": uuid4(),
        "org_id": org,
        "authority_table": "profile_articles",
        "row_id": uuid4(),
        "field_name": "face_width_mm",
        "value_text": "78.00",
        "unit": "mm",
        "scope": "SYSTEM",
        "applicability": None,
        "source_document": "doc.pdf",
        "source_page": 3,
        "source_url": None,
        "declared_by": actor,
        "declared_at": "2026-12-27T00:00:00Z",
        "review_state": "PENDING",
        "reviewed_by": None,
        "reviewed_at": None,
    }
    backend._canned = [inserted]

    result = evidence.declare_evidence(
        org_id=org, actor_id=actor, values=_declare_payload()
    )

    query, params = backend.calls[-1]
    assert "INSERT INTO public.catalog_parameter_evidence" in query
    assert params[0] == str(org)  # org-scoped even on global authorities
    assert params[-1] == str(actor)
    assert result["review_state"] == "PENDING"
    assert result["declared_by"] == str(actor)


def test_declare_rejects_unknown_authority_table(backend):
    with pytest.raises(ContractAPIException) as error:
        evidence.declare_evidence(
            org_id=uuid4(),
            actor_id=uuid4(),
            values=_declare_payload(authority_table="project_positions"),
        )
    assert error.value.status_code == 400
    assert backend.calls == []  # rejected before touching the DB


def test_declare_rejects_invisible_target(backend):
    backend._canned = []  # authority row not found / not in this org
    with pytest.raises(ContractAPIException) as error:
        evidence.declare_evidence(
            org_id=uuid4(), actor_id=uuid4(), values=_declare_payload()
        )
    assert error.value.status_code == 404


def test_declare_rejects_bad_unit(backend, monkeypatch):
    monkeypatch.setattr(
        evidence, "_authority_row_visible", lambda *args, **kwargs: {"id": uuid4()}
    )
    with pytest.raises(ContractAPIException) as error:
        evidence.declare_evidence(
            org_id=uuid4(), actor_id=uuid4(), values=_declare_payload(unit="psi")
        )
    assert error.value.status_code == 400


def test_review_stamps_server_side(backend, monkeypatch):
    org, actor, evidence_id = uuid4(), uuid4(), uuid4()
    reviewed = {
        "id": evidence_id,
        "org_id": org,
        "authority_table": "profile_articles",
        "row_id": uuid4(),
        "field_name": "face_width_mm",
        "value_text": "78.00",
        "unit": "mm",
        "scope": "SYSTEM",
        "applicability": None,
        "source_document": "doc.pdf",
        "source_page": 3,
        "source_url": None,
        "declared_by": uuid4(),
        "declared_at": "2026-12-27T00:00:00Z",
        "review_state": "REVIEWED",
        "reviewed_by": actor,
        "reviewed_at": "2026-12-27T01:00:00Z",
    }
    backend._canned = [reviewed]
    result = evidence.review_evidence(
        org_id=org, evidence_id=evidence_id, actor_id=actor, state="REVIEWED"
    )
    query, params = backend.calls[-1]
    assert "reviewed_by" in query and "PENDING" in query
    assert params[1] == str(actor)
    assert params[3] == str(org)  # org filter — cannot stamp another org's row
    assert result["reviewed_by"] == str(actor)


def test_review_rejects_non_pending(backend):
    backend._canned = []  # UPDATE matched nothing — already reviewed or foreign
    with pytest.raises(ContractAPIException) as error:
        evidence.review_evidence(
            org_id=uuid4(), evidence_id=uuid4(), actor_id=uuid4(), state="REVIEWED"
        )
    assert error.value.status_code == 409


def test_review_rejects_arbitrary_state(backend):
    with pytest.raises(ContractAPIException) as error:
        evidence.review_evidence(
            org_id=uuid4(), evidence_id=uuid4(), actor_id=uuid4(), state="PENDING"
        )
    assert error.value.status_code == 400
    assert backend.calls == []


def test_list_requires_visible_system(backend):
    backend._canned = []
    with pytest.raises(ContractAPIException) as error:
        evidence.list_evidence(org_id=uuid4(), system_id=uuid4())
    assert error.value.status_code == 404


def test_stamp_import_evidence_pins_fields_to_article(backend):
    org, actor, import_id, article = uuid4(), uuid4(), uuid4(), uuid4()
    evidence.stamp_import_evidence(
        org_id=org,
        actor_id=actor,
        import_id=import_id,
        article_id=article,
        candidate={
            "source_document": "ficha_tecnica.pdf (import 9)",
            "source_ref": "pág. 4",
            "evidence": {
                "fields": {
                    "face_width_mm": {
                        "normalized": "78",
                        "original": "78 mm",
                        "unit": "mm",
                    },
                    "weight_kg_m": {
                        "normalized": "1.45",
                        "original": "1,45 kg/ml",
                        "unit": "psi",  # parser garbage → dropped, not stored
                    },
                }
            },
        },
    )
    assert len(backend.calls) == 2
    for query, params in backend.calls:
        assert "ON CONFLICT DO NOTHING" in query
        assert params[1] == "profile_articles"
        assert params[2] == str(article)
        assert params[7] == "pág. 4"
        assert params[8].startswith("ficha_tecnica.pdf")
        assert params[9] == str(actor)
    units = [params[5] for _, params in backend.calls]
    assert units.count("mm") == 1 and units.count(None) == 1


def test_stamp_import_evidence_without_fields_writes_nothing(backend):
    evidence.stamp_import_evidence(
        org_id=uuid4(),
        actor_id=uuid4(),
        import_id=uuid4(),
        article_id=uuid4(),
        candidate={"evidence": {"fields": {}}},
    )
    assert backend.calls == []
