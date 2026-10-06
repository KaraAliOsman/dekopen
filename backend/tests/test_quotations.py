"""Cotizaciones: estado comercial derivado del enlace vigente de la
revisión actual — «vista por el cliente» incluida — nunca en el frontend."""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone

from projects import quotations


@contextmanager
def _atomic():
    yield


class _Ts:
    def __init__(self, dt):
        self._dt = dt

    def isoformat(self):
        return self._dt.isoformat()


def _run(monkeypatch, projects, approvals):
    org_id = uuid4()
    captured: list[tuple[str, list]] = []

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        captured.append((lowered, list(params)))
        assert str(org_id) in params
        if "customer_approvals" in lowered:
            return approvals
        return projects

    monkeypatch.setattr("projects.quotations.rows", fake_rows)
    with patch(
        "projects.quotations.transaction.atomic", side_effect=_atomic
    ), patch("projects.quotations.documentary_backend", side_effect=_atomic):
        out = quotations.list_quotations(org_id=org_id)
    return out


def _project(**over):
    base = {
        "id": uuid4(),
        "code": "P-000001",
        "name": "Obra X",
        "client_name": "Cliente",
        "status": "QUOTED",
        "current_revision": "REV-A",
        "currency": "CLP",
        "total_price_gross": "1000000",
        "updated_at": _Ts(timezone.now()),
        "versions_count": 1,
        "last_sealed_at": _Ts(timezone.now()),
    }
    base.update(over)
    return base


def _approval(project, **over):
    now = timezone.now()
    base = {
        "project_id": project["id"],
        "id": uuid4(),
        "status": "PENDING",
        "expires_at": now + timedelta(days=10),
        "view_count": 0,
        "first_viewed_at": None,
        "last_viewed_at": None,
        "decided_by": None,
        "decided_at": None,
        "decided_note": None,
        "created_at": now,
    }
    base.update(over)
    return base


def test_quote_states_cover_sent_viewed_approved_declined_expired(monkeypatch):
    now = timezone.now()
    projects = [
        _project(code="P-000001"),
        _project(code="P-000002"),
        _project(code="P-000003"),
        _project(code="P-000004"),
        _project(code="P-000005"),
        _project(code="P-000006"),
    ]
    approvals = [
        _approval(projects[0], view_count=0),  # enviada sin vistas
        _approval(projects[1], view_count=2, first_viewed_at=now),
        _approval(projects[2], status="APPROVED", decided_at=now),
        _approval(
            projects[3],
            status="DECLINED",
            decided_at=now,
            decided_note="Cambiar aluminio",
        ),
        _approval(projects[4], expires_at=now - timedelta(days=1)),
        _approval(projects[5], status="REVOKED"),
    ]
    out = _run(monkeypatch, projects, approvals)
    by_code = {item["project_code"]: item for item in out["items"]}
    assert by_code["P-000001"]["quote_state"] == "sent"
    assert by_code["P-000002"]["quote_state"] == "viewed"
    assert by_code["P-000002"]["approval"]["view_count"] == 2
    assert by_code["P-000003"]["quote_state"] == "approved"
    assert by_code["P-000004"]["quote_state"] == "declined"
    assert by_code["P-000004"]["approval"]["decided_note"] == "Cambiar aluminio"
    assert by_code["P-000005"]["quote_state"] == "expired"
    assert by_code["P-000006"]["quote_state"] == "no_link"


def test_project_without_link_is_no_link(monkeypatch):
    projects = [_project(code="P-000010")]
    out = _run(monkeypatch, projects, [])
    assert out["items"][0]["quote_state"] == "no_link"
    assert out["items"][0]["approval"] is None


def test_approval_sql_follows_current_revision(monkeypatch):
    """El enlace que cuenta es el de la revisión vigente — una revisión
    reemplazada no puede marcar la cotización como «enviada»."""
    captured: list[str] = []
    org_scoped: list[list] = []

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        captured.append(lowered)
        org_scoped.append(list(params))
        if "customer_approvals" in lowered:
            return []
        return [_project(code="P-000099")]

    org_id = uuid4()
    monkeypatch.setattr("projects.quotations.rows", fake_rows)
    with patch(
        "projects.quotations.transaction.atomic", side_effect=_atomic
    ), patch("projects.quotations.documentary_backend", side_effect=_atomic):
        out = quotations.list_quotations(org_id=org_id)

    assert len(out["items"]) == 1
    assert any("v.revision_code = p.current_revision" in sql for sql in captured)
    assert all(p[0] == str(org_id) for p in org_scoped)
