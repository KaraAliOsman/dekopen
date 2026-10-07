"""«Hoy» por rol: la cola de acciones se arma en el backend, con códigos
humanos, razón y enlace filtrado — el frontend solo la dibuja."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from uuid import uuid4

from analytics import today


@contextmanager
def _atomic():
    yield


def _run(monkeypatch, role, responses, user_id=None):
    org_id = uuid4()
    uid = user_id or uuid4()
    calls: list[tuple[str, list]] = []

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        calls.append((lowered, list(params)))
        # Toda consulta corre con el org_id del tenant verificado.
        assert str(org_id) in params, lowered
        for marker, result in responses:
            if marker in lowered:
                return result
        return []

    monkeypatch.setattr("analytics.today.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.station_queue", lambda *, org_id: {"stations": []}
    )
    with patch("analytics.today.transaction.atomic", side_effect=_atomic), patch(
        "analytics.today.documentary_backend", side_effect=_atomic
    ):
        out = today.today_queue(org_id=org_id, role=role, user_id=uid)
    return out, calls


TZ = "America/Santiago"


def test_estimator_queue_phrases_and_links(monkeypatch):
    now = datetime.now(dt_timezone.utc)
    pid, pos, approval = uuid4(), uuid4(), uuid4()
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        (
            "customer_approvals",
            [
                {
                    "id": approval,
                    "status": "PENDING",
                    "expires_at": now - timedelta(days=1),
                    "view_count": 2,
                    "decided_by": None,
                    "decided_note": None,
                    "project_id": pid,
                    "project_code": "P-000012",
                    "project_name": "Edificio Prat",
                },
                {
                    "id": uuid4(),
                    "status": "DECLINED",
                    "expires_at": now + timedelta(days=20),
                    "view_count": 3,
                    "decided_by": "Cliente",
                    "decided_note": "Cambiar el corredero por abatible",
                    "project_id": uuid4(),
                    "project_code": "P-000013",
                    "project_name": "Casa Pérez",
                },
            ],
        ),
        (
            "pricing_operations",
            [
                {
                    "state": "REJECTED",
                    "project_id": uuid4(),
                    "project_code": "P-000014",
                    "project_name": "Local Centro",
                    "project_status": "DRAFT",
                }
            ],
        ),
        (
            "project_positions",
            [
                {
                    "id": pos,
                    "location_tag": "Pos. 03 Living",
                    "position_index": 3,
                    "project_id": pid,
                    "project_code": "P-000012",
                    "project_name": "Edificio Prat",
                }
            ],
        ),
    ]
    out, calls = _run(monkeypatch, "ESTIMATOR", responses)
    kinds = [item["kind"] for item in out["items"]]
    assert kinds == [
        "quote_expired",
        "changes_requested",
        "price_rejected",
        "position_blocked",
    ]
    expired, declined, rejected, blocked = out["items"]
    assert expired["urgency"] == "overdue"
    assert expired["entity_code"] == "P-000012"
    assert expired["to"] == f"/projects/{pid}"
    assert "Venció el" in expired["reason"]
    assert declined["urgency"] == "today"
    assert "«Cambiar el corredero" in declined["reason"]
    assert rejected["to"].endswith("/pricing")
    assert blocked["to"] == f"/projects/{pid}/positions/{pos}/edit"
    assert calls  # la cola se arma consultando, no calculando en memoria


def test_estimator_views_without_reply(monkeypatch):
    now = datetime.now(dt_timezone.utc)
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        (
            "customer_approvals",
            [
                {
                    "id": uuid4(),
                    "status": "PENDING",
                    "expires_at": now + timedelta(days=10),
                    "view_count": 4,
                    "decided_by": None,
                    "decided_note": None,
                    "project_id": uuid4(),
                    "project_code": "P-000020",
                    "project_name": "Torre Sur",
                }
            ],
        ),
        ("pricing_operations", []),
        ("project_positions", []),
    ]
    out, _ = _run(monkeypatch, "ESTIMATOR", responses)
    assert [i["kind"] for i in out["items"]] == ["proposal_viewed"]
    assert "4 veces" in out["items"][0]["reason"]


def test_owner_queue_panels_and_receivables(monkeypatch):
    project_id = uuid4()
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        (
            "pricing_operations",
            [
                {
                    "project_id": project_id,
                    "target_margin": "0.28",
                    "project_code": "P-000030",
                    "project_name": "Bodega Norte",
                }
            ],
        ),
        (
            "project_payments",
            [
                {
                    "id": project_id,
                    "project_code": "P-000031",
                    "project_name": "Casa Lagos",
                    "status": "COMPLETED",
                    "total_price_gross": "1435471",
                    "currency": "CLP",
                    "collected": "700000",
                    "reminder_drafted": False,
                }
            ],
        ),
        ("from public.orders", [{"held": 2, "remakes": 0}]),
        ("public.deliveries", [{"overdue": 1, "today": 2}]),
        (
            "group by p.status",
            [
                {
                    "status": "QUOTED",
                    "currency": "CLP",
                    "n": 3,
                    "total": "4200000",
                }
            ],
        ),
    ]
    out, _ = _run(monkeypatch, "OWNER", responses)
    kinds = {item["kind"] for item in out["items"]}
    assert kinds >= {
        "margin_approval",
        "collection_overdue",
        "ot_held",
        "deliveries_overdue",
        "deliveries_today",
    }
    approval = next(i for i in out["items"] if i["kind"] == "margin_approval")
    assert approval["to"] == f"/projects/{project_id}/pricing"
    assert "28 %" in approval["reason"]
    collection = next(i for i in out["items"] if i["kind"] == "collection_overdue")
    assert collection["urgency"] == "overdue"
    assert "$735.471" in collection["reason"]
    pipeline = out["panels"][0]
    assert pipeline["kind"] == "pipeline"
    assert {row["label"] for row in pipeline["rows"]} == {"Cotizado", "Por cobrar"}
    por_cobrar = next(r for r in pipeline["rows"] if r["label"] == "Por cobrar")
    assert por_cobrar["value"] == "$735.471"


def test_manager_queue_groups_counts(monkeypatch):
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        ("stock_reservations", [{"n": 2}]),
        (
            "from public.orders",
            [{"held": 3, "remakes": 1}],
        ),
        ("public.deliveries", [{"overdue": 0, "today": 1}]),
    ]
    monkeypatch_stations = [
        {
            "code": "CUT",
            "label": "Corte",
            "pending": 6,
            "in_progress": 1,
            "blocked": 2,
            "entries": [],
        },
        {
            "code": "GLAZE",
            "label": "Vidriería",
            "pending": 2,
            "in_progress": 0,
            "blocked": 0,
            "entries": [],
        },
    ]
    org_id = uuid4()
    calls: list[tuple[str, list]] = []

    def fake_rows(sql_text: str, params: list = ()):
        lowered = " ".join(sql_text.lower().split())
        calls.append((lowered, list(params)))
        assert str(org_id) in params, lowered
        for marker, result in responses:
            if marker in lowered:
                return result
        return []

    monkeypatch.setattr("analytics.today.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.station_queue",
        lambda *, org_id: {"stations": monkeypatch_stations},
    )
    with patch("analytics.today.transaction.atomic", side_effect=_atomic), patch(
        "analytics.today.documentary_backend", side_effect=_atomic
    ):
        out = today.today_queue(org_id=org_id, role="WORKSHOP_MANAGER", user_id=uuid4())

    kinds = [i["kind"] for i in out["items"]]
    assert kinds[0] == "deliveries_today"
    assert "ot_held" in kinds and "ot_shortage" in kinds and "remakes_open" in kinds
    held = next(i for i in out["items"] if i["kind"] == "ot_held")
    assert held["to"] == "/production?blocked=1"
    shortage = next(i for i in out["items"] if i["kind"] == "ot_shortage")
    assert shortage["to"] == "/production?shortage=1"
    cut = next(i for i in out["items"] if i["kind"] == "station_backlog")
    assert "Corte" in cut["phrase"] and cut["count"] == 9


def test_installer_queue_per_delivery(monkeypatch):
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        (
            "public.deliveries",
            [
                {
                    "id": uuid4(),
                    "scheduled_date": date.today(),
                    "time_window": "AM",
                    "status": "SCHEDULED",
                    "address": "Camino Penco km 8",
                    "installer_name": "Cuadrilla A",
                    "notes": None,
                    "order_code": "OT-P-000005-REV-A-03",
                    "order_status": "DISPATCHED",
                    "project_code": "P-000040",
                    "project_name": "Vivienda Camino Penco",
                },
                {
                    "id": uuid4(),
                    "scheduled_date": date.today() - timedelta(days=2),
                    "time_window": "PM",
                    "status": "FAILED",
                    "address": "Lirquén 801",
                    "installer_name": "Cuadrilla B",
                    "notes": None,
                    "order_code": "OT-P-000041-REV-A-01",
                    "order_status": "DISPATCHED",
                    "project_code": "P-000041",
                    "project_name": "Depto Lirquén",
                },
            ],
        ),
    ]
    out, _ = _run(monkeypatch, "INSTALLER", responses)
    by_kind = {i["kind"]: i for i in out["items"]}
    assert set(by_kind) == {"delivery_failed", "delivery_due"}
    assert by_kind["delivery_failed"]["urgency"] == "overdue"
    assert by_kind["delivery_failed"]["to"] == "/deliveries?when=open"
    assert by_kind["delivery_due"]["urgency"] in ("overdue", "today", "soon")
    assert by_kind["delivery_due"]["entity_code"] == "OT-P-000005-REV-A-03"


def test_operator_queue_empty_shows_idle(monkeypatch):
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        ("production_steps", []),
    ]
    out, _ = _run(monkeypatch, "OPERATOR", responses)
    assert [i["kind"] for i in out["items"]] == ["station_idle"]
    assert out["items"][0]["to"] == "/production"


def test_every_item_links_to_a_real_route(monkeypatch):
    """Cada ítem enlaza a una ruta existente con su filtro — la regla que el
    test de frontend re-verifica desde el contrato."""
    now = datetime.now(dt_timezone.utc)
    responses = [
        ("tenancy_organizations", [{"timezone": TZ, "currency": "CLP"}]),
        (
            "customer_approvals",
            [
                {
                    "id": uuid4(),
                    "status": "PENDING",
                    "expires_at": now - timedelta(days=1),
                    "view_count": 0,
                    "decided_by": None,
                    "decided_note": None,
                    "project_id": uuid4(),
                    "project_code": "P-1",
                    "project_name": "X",
                }
            ],
        ),
        ("pricing_operations", []),
        ("project_positions", []),
    ]
    out, _ = _run(monkeypatch, "ESTIMATOR", responses)
    for item in out["items"]:
        assert item["to"].startswith("/")
        assert item["cta"]
        assert item["phrase"]
