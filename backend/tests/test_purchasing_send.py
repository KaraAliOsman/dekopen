"""P15 — envío de OC: un solo clic humano produce la transición SENT, el
correo al proveedor por el outbox y el job que emite el PDF de la orden."""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest

from documents.repository import DocumentaryError
from purchasing import service


@contextmanager
def _atomic():
    yield


def _order(status="DRAFT", order_type="SUPPLIER_PROFILE_PO"):
    version_id = uuid4()
    return {
        "id": uuid4(),
        "order_code": "OC-000123",
        "order_type": order_type,
        "status": status,
        "supplier_name": "Perfiles Andina SPA",
        "order_snapshot_hash": "ab" * 32,
        "project_version_id": version_id,
    }


def _sent_row(order):
    return {
        **order,
        "status": "SENT",
        "expected_at": None,
        "sent_to": "ventas@andina.cl",
    }


def test_send_order_delivers_mail_and_pdf_job() -> None:
    org_id, actor_id, order = uuid4(), uuid4(), _order()
    reads = iter([order, _sent_row(order)])
    enqueued = []

    def fake_one(query, params=(), code=None):
        return next(reads)

    def fake_enqueue(**kwargs):
        enqueued.append(kwargs)
        return {"id": uuid4()}, True

    with patch("purchasing.service.one", side_effect=fake_one), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ), patch("purchasing.service.transaction"), patch(
        "mail.service.deliver_order_sent",
        return_value={"id": str(uuid4()), "status": "QUEUED", "to": "ventas@andina.cl"},
    ) as mail, patch(
        "jobs.service.job_backend", return_value=_atomic()
    ), patch(
        "jobs.service.enqueue", side_effect=fake_enqueue
    ):
        output = service.send_order(
            org_id=org_id, actor_id=actor_id, order_id=order["id"],
            confirmed=True, sent_to="ventas@andina.cl",
            role="WORKSHOP_MANAGER",
        )

    assert output["status"] == "SENT"
    assert output["mail"]["status"] == "QUEUED"
    mail.assert_called_once()
    # DOC-04 es el documento proveedor de las OC de perfiles.
    assert output["document_job"]["document_type"] == "DOC-04"
    assert enqueued[0]["job_type"] == "document.artifact.generate"
    assert enqueued[0]["payload"]["order_id"] == str(order["id"])
    assert enqueued[0]["payload"]["project_version_id"] == str(order["project_version_id"])
    assert enqueued[0]["role"] == "WORKSHOP_MANAGER"


def test_send_order_mail_failure_never_breaks_transition() -> None:
    org_id, actor_id, order = uuid4(), uuid4(), _order(order_type="SUPPLIER_GLASS_PO")
    reads = iter([order, _sent_row(order)])

    with patch(
        "purchasing.service.one", side_effect=lambda *a, **k: next(reads)
    ), patch("purchasing.service.documentary_backend", return_value=_atomic()), patch(
        "purchasing.service.transaction"
    ), patch(
        "mail.service.deliver_order_sent", side_effect=RuntimeError("smtp caído")
    ), patch(
        "jobs.service.job_backend", return_value=_atomic()
    ), patch("jobs.service.enqueue", return_value=({"id": uuid4()}, True)):
        output = service.send_order(
            org_id=org_id, actor_id=actor_id, order_id=order["id"],
            confirmed=True, role="OWNER",
        )

    assert output["status"] == "SENT"
    assert output["mail"] is None
    # Vidrios emite DOC-02.
    assert output["document_job"]["document_type"] == "DOC-02"


def test_send_order_pdf_job_failure_never_breaks_transition() -> None:
    org_id, actor_id, order = uuid4(), uuid4(), _order()
    reads = iter([order, _sent_row(order)])

    with patch(
        "purchasing.service.one", side_effect=lambda *a, **k: next(reads)
    ), patch("purchasing.service.documentary_backend", return_value=_atomic()), patch(
        "purchasing.service.transaction"
    ), patch(
        "mail.service.deliver_order_sent", return_value={"status": "SENT"}
    ), patch(
        "jobs.service.job_backend", return_value=_atomic()
    ), patch("jobs.service.enqueue", side_effect=RuntimeError("cola caída")):
        output = service.send_order(
            org_id=org_id, actor_id=actor_id, order_id=order["id"],
            confirmed=True, role="WORKSHOP_MANAGER",
        )

    assert output["status"] == "SENT"
    assert output["document_job"] is None


def test_send_order_requires_explicit_confirmation() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.send_order(
            org_id=uuid4(), actor_id=uuid4(), order_id=uuid4(), confirmed=False
        )
    assert error.value.code == "order_send_confirmation_required"


def test_send_order_sent_is_idempotent() -> None:
    order = _order(status="SENT")
    with patch("purchasing.service.one", return_value=order), patch(
        "purchasing.service.documentary_backend", return_value=_atomic()
    ):
        output = service.send_order(
            org_id=uuid4(), actor_id=uuid4(), order_id=order["id"],
            confirmed=True, role="OWNER",
        )
    assert output["status"] == "SENT"
    assert "mail" not in output
