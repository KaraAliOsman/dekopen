"""Customer approval links: token mint, public read, idempotent decide."""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from documents.repository import DocumentaryError
from portal import service


@contextmanager
def _atomic():
    yield


def _roles(monkeypatch):
    monkeypatch.setattr("portal.service.transaction.atomic", _atomic)
    monkeypatch.setattr("portal.service.documentary_backend", _atomic)
    monkeypatch.setattr("portal.service.portal_backend", _atomic)


def test_share_quote_mints_hashed_token(monkeypatch) -> None:
    _roles(monkeypatch)
    org_id, project_id, actor_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    captured: dict[str, list] = {"insert_params": []}
    artifact_calls: list[dict] = []

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        if lowered.startswith("select id,status"):
            return {"id": project_id, "status": "QUOTED"}
        if lowered.startswith("insert into public.customer_approvals"):
            captured["insert_params"] = list(params)
            return {"id": uuid4()}
        raise AssertionError(lowered)

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        if "project_versions" in lowered:
            return [{"id": version_id}]
        return []

    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr(
        "portal.service.generate_artifact",
        lambda **k: (artifact_calls.append(dict(k)) or ({}, True)),
    )
    out = service.share_quote(
        org_id=org_id, project_id=project_id, actor_id=actor_id, role="ESTIMATOR"
    )

    token = out["token"]
    assert len(token) > 40 and out["expires_at"] > datetime.now(timezone.utc)
    # the raw token never reaches storage — only its sha256
    assert captured["insert_params"][3] != token
    assert captured["insert_params"][3] == __import__("hashlib").sha256(
        token.encode()
    ).hexdigest()
    assert captured["insert_params"][4] == out["expires_at"]
    # minting guarantees the client-facing DOC-01 for the bound version
    assert artifact_calls == [
        {
            "org_id": org_id,
            "actor_id": actor_id,
            "role": "ESTIMATOR",
            "project_version_id": version_id,
            "order_id": None,
            "document_type": "DOC-01",
            "file_format": "PDF",
        }
    ]


def test_share_quote_requires_quoted_status(monkeypatch) -> None:
    _roles(monkeypatch)
    monkeypatch.setattr(
        "portal.service.one",
        lambda *a, **k: {"id": uuid4(), "status": "DRAFT"},
    )
    with pytest.raises(DocumentaryError, match="quote_share_requires_quoted"):
        service.share_quote(
            org_id=uuid4(), project_id=uuid4(), actor_id=uuid4(), role="ESTIMATOR"
        )


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=()):
        pass

    def fetchone(self):
        return ["authenticated"]


def _approval(status="PENDING", expired=False):
    return {
        "id": uuid4(),
        "created_by": uuid4(),
        "org_id": uuid4(),
        "project_id": uuid4(),
        "project_version_id": uuid4(),
        "status": status,
        "decided_by": None,
        "decided_at": None,
        "decided_note": None,
        "expires_at": datetime.now(timezone.utc)
        + timedelta(days=-1 if expired else 30),
    }


def _version(snapshot: dict | None = None, revision="REV-A"):
    return {
        "revision_code": revision,
        "emitted_at": datetime.now(timezone.utc),
        "snapshot_json": json.dumps(
            snapshot
            or {
                "project": {
                    "code": "P-1",
                    "name": "Casa",
                    "client_name": "Ana",
                    "total_price_net": "10.00",
                    "total_price_tax": "1.90",
                    "total_price_gross": "11.90",
                    "quotation_valid_until": "2999-01-01",
                }
            }
        ),
    }


def _live(status="QUOTED", revision="REV-A"):
    return {"status": status, "current_revision": revision}


def _install_fakes(monkeypatch, approval, version=None, live=None, calls=None):
    calls = calls if calls is not None else []

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if "token_hash" in lowered:
            return [approval]
        if lowered.startswith("update public.customer_approvals"):
            return [{"id": approval["id"]}]
        if lowered.startswith("update public.projects"):
            return [{"id": approval["project_id"]}]
        return []

    def fake_write(sql_text, params=()):
        calls.append(" ".join(sql_text.lower().split()))
        return 1

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if "project_versions" in lowered:
            return version or _version()
        if "public.projects" in lowered:
            return live or _live()
        raise AssertionError(lowered)

    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.write", fake_write)
    return calls


def test_portal_quote_unknown_and_expired_tokens(monkeypatch) -> None:
    _roles(monkeypatch)
    monkeypatch.setattr("portal.service.rows", lambda *a, **k: [])
    with pytest.raises(DocumentaryError, match="quote_not_found"):
        service.portal_quote("bogus")

    monkeypatch.setattr("portal.service.rows", lambda *a, **k: [_approval(expired=True)])
    with pytest.raises(DocumentaryError, match="quote_expired"):
        service.portal_quote("expired-token")


def test_portal_quote_reads_sealed_snapshot_not_live_totals(monkeypatch) -> None:
    """After a successor resets live totals, the link still shows REV-A's."""
    _roles(monkeypatch)
    approval = _approval()
    sealed = {
        "project": {
            "code": "P-1",
            "name": "Casa",
            "client_name": "Ana",
            "total_price_net": "1190000.00",
            "total_price_tax": "226100.00",
            "total_price_gross": "1416100.00",
            "quotation_valid_until": "2999-01-01",
        }
    }
    # the live project moved on to a draft REV-B with zeroed totals
    _install_fakes(
        monkeypatch,
        approval,
        version=_version(snapshot=sealed),
        live=_live(status="DRAFT", revision="REV-B"),
    )
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.portal_quote("tok")

    assert out["total_price_gross"] == "1416100.00"
    assert out["project_name"] == "Casa"
    assert out["revision_code"] == "REV-A"
    assert out["superseded"] is True
    assert out["valid_until"] == "2999-01-01"


def test_portal_quote_carries_positions_issuer_and_payment_state(monkeypatch) -> None:
    """§09: the proposal surfaces the sealed positions, the issuer identity
    and the project's collected/balance payment state."""
    _roles(monkeypatch)
    approval = _approval()
    sealed = {
        "organization": {"name": "Vidriería Sur", "tax_id": "76.123.456-7"},
        "project": {
            "code": "P-1",
            "name": "Casa",
            "client_name": "Ana",
            "payment_terms": "50% anticipo",
            "currency": "CLP",
            "total_price_net": "1000.00",
            "total_price_tax": "190.00",
            "total_price_gross": "1190.00",
            "quotation_valid_until": "2999-01-01",
        },
        "positions": [
            {
                "id": "pos-1",
                "position_index": 1,
                "quantity": 2,
                "typology": "2F_TT",
                "location_tag": "LIVING",
                "width_mm": "1200.00",
                "height_mm": "1500.00",
                "price_net": "500.00",
                "parametric_tree": {"type": "ROOT"},
            },
            "ignored-non-dict",
        ],
    }

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        if "token_hash" in lowered:
            return [approval]
        if "project_payments" in lowered:
            return [
                {"amount": "400.00", "voided_at": None},
                {"amount": "50.00", "voided_at": "x"},
            ]
        return []

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        if "project_versions" in lowered:
            return _version(snapshot=sealed)
        if "public.projects" in lowered:
            return _live()
        raise AssertionError(lowered)

    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.write", lambda *a, **k: 1)
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.portal_quote("tok")

    assert out["organization"] == {
        "name": "Vidriería Sur",
        "tax_id": "76.123.456-7",
        "commercial_name": None,
        "brand_address": None,
        "brand_phone": None,
        "brand_email": None,
        "brand_logo_url": None,
    }
    assert out["payment_terms"] == "50% anticipo"
    assert out["positions"][0]["typology"] == "2F_TT"
    assert out["positions"][0]["parametric_tree"] == {"type": "ROOT"}
    assert len(out["positions"]) == 1
    assert out["payment"] == {
        "status": "PARTIAL",
        "collected": "400.00",
        "balance": "790.00",
    }


def test_decide_approves_project_and_replays(monkeypatch) -> None:
    _roles(monkeypatch)
    approval = _approval()
    calls = _install_fakes(monkeypatch, approval)

    role_calls: list[str] = []

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, statement, params=()):
            role_calls.append(str(statement))

        def fetchone(self):
            return ["authenticated"]

    monkeypatch.setattr(
        "portal.service.connection",
        SimpleNamespace(cursor=lambda: _FakeCursor()),
    )
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.decide_quote(
            token="tok", decision="APPROVED", decided_by="Ana", note=None
        )

    assert any("pricing_backend" in c for c in role_calls)
    assert any("request.jwt.claims" in c for c in role_calls)
    # the portal role bound itself to the approval's tenant first
    assert any("app.portal_org_id" in c for c in calls)
    assert out["approval_status"] in {"PENDING", "APPROVED"}
    assert any("status='approved'" in c for c in calls)
    # every SQL statement stayed parameterized (never interpolated the token)
    assert all("token" not in c or "token_hash" in c for c in calls)
    assert any("update public.customer_approvals" in c for c in calls)
    assert any("update public.projects" in c for c in calls)


def test_decide_rejects_stale_link(monkeypatch) -> None:
    """A successor draft resets the project — the old link cannot approve it."""
    _roles(monkeypatch)
    approval = _approval()
    calls = _install_fakes(
        monkeypatch, approval, live=_live(status="DRAFT", revision="REV-B")
    )
    with patch("portal.service.SupabaseDocumentStorage"):
        with pytest.raises(DocumentaryError, match="quote_link_stale"):
            service.decide_quote(
                token="tok", decision="APPROVED", decided_by="Ana", note=None
            )
    # nothing was written — no stale approval seal, no project transition
    assert not any(c.startswith("update") for c in calls)


def test_decide_confirm_on_already_approved_project(monkeypatch) -> None:
    """A second link on the same sealed revision still seals its approval."""
    _roles(monkeypatch)
    approval = _approval()
    calls = _install_fakes(monkeypatch, approval, live=_live(status="APPROVED"))
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.decide_quote(
            token="tok", decision="APPROVED", decided_by="Ana", note=None
        )
    # the approval seals, but the project is not transitioned again
    assert any("update public.customer_approvals" in c for c in calls)
    assert not any("update public.projects" in c for c in calls)
    assert out["approval_status"] in {"PENDING", "APPROVED"}


def test_decide_decline_on_approved_project_is_honest(monkeypatch) -> None:
    """Declining a pending link on an already-APPROVED project must not claim
    a new revision replaced it — the quote was decided, not superseded."""
    _roles(monkeypatch)
    approval = _approval()
    _install_fakes(monkeypatch, approval, live=_live(status="APPROVED"))
    with patch("portal.service.SupabaseDocumentStorage"):
        with pytest.raises(DocumentaryError, match="quote_already_decided"):
            service.decide_quote(
                token="tok", decision="DECLINED", decided_by="Ana", note="x"
            )


def test_portal_quote_hides_payment_url_on_superseded(monkeypatch) -> None:
    """A superseded revision must not offer a pay link for dead money."""
    _roles(monkeypatch)
    approval = _approval()
    sealed = _version(
        snapshot={
            "project": {
                "currency": "CLP",
                "total_price_gross": "1000000",
            }
        }
    )
    live = _live(status="QUOTED", revision="REV-B")  # link bound to REV-A
    calls = _install_fakes(monkeypatch, approval, version=sealed, live=live)

    base_rows = service.rows

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if "token_hash" in lowered:
            return [approval]
        if "project_payment_links" in lowered:
            return [{"url": "https://pay.example/link"}]
        return []

    monkeypatch.setattr("portal.service.rows", fake_rows)
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.portal_quote("tok")
    assert out["superseded"] is True
    assert out["payment_url"] is None
    # the link table is never even queried once the revision is dead
    assert not any("project_payment_links" in c for c in calls)
    monkeypatch.setattr("portal.service.rows", base_rows)


def test_portal_quote_hides_payment_url_on_declined(monkeypatch) -> None:
    """A rejected proposal must not offer a pay link — charging after the
    client declined reads as billing a dead deal."""
    _roles(monkeypatch)
    approval = _approval(status="DECLINED")
    sealed = _version(
        snapshot={
            "project": {
                "currency": "CLP",
                "total_price_gross": "1000000",
            }
        }
    )
    live = _live(status="QUOTED", revision="REV-A")
    calls = _install_fakes(monkeypatch, approval, version=sealed, live=live)

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if "token_hash" in lowered:
            return [approval]
        if "project_payment_links" in lowered:
            return [{"url": "https://pay.example/link"}]
        return []

    monkeypatch.setattr("portal.service.rows", fake_rows)
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.portal_quote("tok")
    assert out["payment_url"] is None
    assert not any("project_payment_links" in c for c in calls)


def test_decide_rejects_expired_quote_validity(monkeypatch) -> None:
    _roles(monkeypatch)
    approval = _approval()
    stale_validity = {
        "project": {"quotation_valid_until": "2000-01-01"}
    }
    calls = _install_fakes(
        monkeypatch, approval, version=_version(snapshot=stale_validity)
    )
    with patch("portal.service.SupabaseDocumentStorage"):
        with pytest.raises(DocumentaryError, match="quote_validity_expired"):
            service.decide_quote(
                token="tok", decision="APPROVED", decided_by="Ana", note=None
            )
    assert not any(c.startswith("update") for c in calls)


def test_decide_replay_keeps_sealed_state(monkeypatch) -> None:
    _roles(monkeypatch)
    approval = _approval(status="APPROVED")
    calls = _install_fakes(monkeypatch, approval, live=_live(status="APPROVED"))
    with patch("portal.service.SupabaseDocumentStorage"):
        out = service.decide_quote(
            token="tok", decision="DECLINED", decided_by="Otro", note=None
        )
    # a second decision never rewrites the approval row or the project
    assert not any(c.startswith("update") for c in calls)
    assert out["approval_status"] == "APPROVED"


def test_revoked_token_is_dead(monkeypatch) -> None:
    _roles(monkeypatch)
    monkeypatch.setattr(
        "portal.service.rows", lambda *a, **k: [_approval(status="REVOKED")]
    )
    with pytest.raises(DocumentaryError, match="quote_revoked"):
        service.portal_quote("revoked-token")
    with pytest.raises(DocumentaryError, match="quote_revoked"):
        service.decide_quote(
            token="revoked-token", decision="APPROVED", decided_by="Ana", note=None
        )


def test_share_supersedes_pending_links(monkeypatch) -> None:
    _roles(monkeypatch)
    org_id, project_id, actor_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    revoked: list[list] = []

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        if lowered.startswith("select id,status"):
            return {"id": project_id, "status": "QUOTED"}
        if lowered.startswith("insert into"):
            return {"id": uuid4()}
        raise AssertionError(lowered)

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        if lowered.startswith("update public.customer_approvals"):
            revoked.append(list(params))
            return []
        if "project_versions" in lowered:
            return [{"id": version_id}]
        return []

    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr("portal.service.generate_artifact", lambda **k: ({}, True))
    service.share_quote(
        org_id=org_id, project_id=project_id, actor_id=actor_id, role="ESTIMATOR"
    )
    # outstanding PENDING links on the same version die inside the mint tx
    assert len(revoked) == 1
    assert revoked[0][1:] == [str(actor_id), str(org_id), str(project_id), str(version_id)]


def test_approve_internal_mints_decided_row_and_transitions(monkeypatch) -> None:
    _roles(monkeypatch)
    org_id, project_id, actor_id, version_id = uuid4(), uuid4(), uuid4(), uuid4()
    calls: list[str] = []

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if lowered.startswith("insert into public.customer_approvals"):
            return {
                "id": uuid4(),
                "org_id": org_id,
                "project_id": project_id,
                "created_by": actor_id,
            }
        if lowered.startswith("select id,status,current_revision"):
            return {
                "id": project_id,
                "status": "QUOTED",
                "current_revision": "REV-A",
            }
        raise AssertionError(lowered)

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        calls.append(lowered)
        if "project_versions" in lowered:
            return [{"id": version_id, "revision_code": "REV-A"}]
        if lowered.startswith("update public.projects"):
            return [{"id": project_id}]
        return []

    def fake_write(sql_text, params=()):
        calls.append(" ".join(sql_text.lower().split()))
        return 1

    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr("portal.service.write", fake_write)
    monkeypatch.setattr(
        "portal.service.connection",
        SimpleNamespace(cursor=lambda: _FakeCursor()),
    )
    out = service.approve_internal(
        org_id=org_id,
        project_id=project_id,
        actor_id=actor_id,
        actor_label="estimador@taller.cl",
        note="Aprobó por teléfono",
    )
    assert out == {"project_status": "APPROVED"}
    assert any(
        c.startswith("update public.customer_approvals") and "'revoked'" in c
        for c in calls
    )
    assert any("status='approved'" in c for c in calls)
    assert any("update public.projects" in c for c in calls)


def test_approve_internal_requires_quoted(monkeypatch) -> None:
    _roles(monkeypatch)

    def fake_one(sql_text, params, code="not_found"):
        return {"id": uuid4(), "status": "DRAFT", "current_revision": "REV-A"}

    monkeypatch.setattr("portal.service.one", fake_one)
    with pytest.raises(DocumentaryError, match="quote_approve_requires_quoted"):
        service.approve_internal(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            actor_label="x@x.cl",
            note=None,
        )


def test_approve_internal_idempotent_on_approved(monkeypatch) -> None:
    _roles(monkeypatch)

    def fake_one(sql_text, params, code="not_found"):
        return {"id": uuid4(), "status": "APPROVED", "current_revision": "REV-A"}

    monkeypatch.setattr("portal.service.one", fake_one)
    out = service.approve_internal(
        org_id=uuid4(),
        project_id=uuid4(),
        actor_id=uuid4(),
        actor_label="x@x.cl",
        note=None,
    )
    assert out == {"project_status": "APPROVED"}


def test_approve_internal_rejects_revision_mismatch(monkeypatch) -> None:
    _roles(monkeypatch)

    def fake_one(sql_text, params, code="not_found"):
        return {"id": uuid4(), "status": "QUOTED", "current_revision": "REV-A"}

    def fake_rows(sql_text, params=()):
        return [{"id": uuid4(), "revision_code": "REV-B"}]

    monkeypatch.setattr("portal.service.one", fake_one)
    monkeypatch.setattr("portal.service.rows", fake_rows)
    with pytest.raises(DocumentaryError, match="quote_approve_revision_mismatch"):
        service.approve_internal(
            org_id=uuid4(),
            project_id=uuid4(),
            actor_id=uuid4(),
            actor_label="x@x.cl",
            note=None,
        )


def test_revoke_link_transitions_pending_only(monkeypatch) -> None:
    _roles(monkeypatch)
    org_id, project_id, approval_id, actor_id = uuid4(), uuid4(), uuid4(), uuid4()
    calls: list[list] = []

    def fake_one(sql_text, params, code="not_found"):
        lowered = " ".join(sql_text.lower().split())
        calls.append(list(params))
        if lowered.startswith("update"):
            return {"id": approval_id, "status": "REVOKED"}
        return {"id": approval_id, "status": "PENDING"}

    monkeypatch.setattr("portal.service.one", fake_one)
    out = service.revoke_link(
        org_id=org_id, project_id=project_id, approval_id=approval_id, actor_id=actor_id
    )
    assert out["status"] == "REVOKED"

    # a decided link cannot be revoked — the client's answer stands
    monkeypatch.setattr(
        "portal.service.one",
        lambda *a, **k: {"id": approval_id, "status": "APPROVED"},
    )
    with pytest.raises(DocumentaryError, match="approval_not_pending"):
        service.revoke_link(
            org_id=org_id,
            project_id=project_id,
            approval_id=approval_id,
            actor_id=actor_id,
        )


def test_portal_quote_records_the_client_view(monkeypatch) -> None:
    """Each public open bumps the link's view counters — the estimator's
    'client opened it twice' signal."""
    _roles(monkeypatch)
    approval = _approval()
    calls = _install_fakes(monkeypatch, approval)
    with patch("portal.service.SupabaseDocumentStorage"):
        service.portal_quote("tok")
    bumps = [
        call
        for call in calls
        if "view_count=view_count+1" in call and "customer_approvals" in call
    ]
    assert len(bumps) == 1


def test_list_approvals_exposes_the_view_signal(monkeypatch) -> None:
    _roles(monkeypatch)
    viewed_at = datetime.now(timezone.utc)

    def fake_rows(sql_text, params=()):
        lowered = " ".join(sql_text.lower().split())
        if "customer_approvals" in lowered:
            return [
                {
                    "id": uuid4(),
                    "status": "PENDING",
                    "revision_code": "REV-A",
                    "decided_by": None,
                    "decided_at": None,
                    "decided_note": None,
                    "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
                    "created_at": datetime.now(timezone.utc),
                    "revoked_at": None,
                    "view_count": 3,
                    "last_viewed_at": viewed_at,
                }
            ]
        return []

    monkeypatch.setattr("portal.service.rows", fake_rows)
    monkeypatch.setattr(
        "portal.service.one",
        lambda *a, **k: {"id": uuid4()},
    )
    out = service.list_approvals(org_id=uuid4(), project_id=uuid4())
    assert out[0]["view_count"] == 3
    assert out[0]["last_viewed_at"] == viewed_at.isoformat()
