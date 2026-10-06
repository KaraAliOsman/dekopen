"""CNC workspace service — authority validation, machine profiles, staleness."""

from __future__ import annotations

from decimal import Decimal
import json
from unittest.mock import patch
from uuid import uuid4

import pytest

from documents.repository import DocumentaryError
from production import cnc


def test_create_tool_rejects_unknown_kind() -> None:
    with pytest.raises(DocumentaryError) as exc:
        cnc.create_tool(
            org_id=uuid4(),
            actor_id=uuid4(),
            data={"code": "T-1", "name": "Fresa", "kind": "LASER"},
        )
    assert exc.value.code == "cnc_tool_invalid"


def test_create_tool_rejects_unknown_compatible_kind() -> None:
    with pytest.raises(DocumentaryError) as exc:
        cnc.create_tool(
            org_id=uuid4(),
            actor_id=uuid4(),
            data={
                "code": "T-1",
                "name": "Broca",
                "kind": "DRILL_BIT",
                "compatible_kinds": ["HANDLE_PREP", "TELEPORT"],
            },
        )
    assert exc.value.code == "cnc_tool_kind_invalid"


def test_clamp_zones_validate_shape() -> None:
    with pytest.raises(DocumentaryError) as exc:
        cnc._clamp_zones([{"start_mm": "500", "end_mm": "100"}])
    assert exc.value.code == "cnc_clamp_zones_invalid"
    zones = cnc._clamp_zones(
        [{"start_mm": "500", "end_mm": "1100", "label": "Mordaza B"}]
    )
    assert zones == [
        {"start_mm": "500", "end_mm": "1100", "label": "Mordaza B"}
    ]


def test_tool_ids_must_exist_in_org() -> None:
    missing = str(uuid4())
    with patch(
        "production.cnc.rows", return_value=[]
    ), pytest.raises(DocumentaryError) as exc:
        cnc._tool_ids([missing], org_id=uuid4())
    assert exc.value.code == "cnc_tool_not_in_org"


def test_machine_profile_maps_declared_authority() -> None:
    tool_id = uuid4()
    tools_by_id = {
        str(tool_id): {
            "id": tool_id,
            "code": "DR-8",
            "name": "Broca 8",
            "kind": "DRILL_BIT",
            "diameter_mm": Decimal("8"),
            "working_length_mm": Decimal("40"),
            "max_depth_mm": Decimal("30"),
            "compatible_kinds": ["DRILL", "HANDLE_PREP"],
            "active": True,
        }
    }
    machine_row = {
        "id": uuid4(),
        "code": "SBZ-01",
        "name": "Centro",
        "manufacturer": "Elumatec",
        "model": "SBZ 122",
        "controller_family": "NEUTRAL",
        "coordinate_systems": ["MEMBER_PLAN"],
        "supported_kinds": ["DRILL", "HANDLE_PREP"],
        "supported_faces": ["INSIDE_FACE", "OUTSIDE_FACE"],
        "max_member_length_mm": Decimal("3500"),
        "safe_margin_mm": Decimal("25"),
        "clamp_zones": [
            {"start_mm": "500", "end_mm": "900", "label": "Mordaza A"}
        ],
        "tool_ids": [str(tool_id)],
        "postprocessor_id": "neutral-ops-v1",
        "postprocessor_version": "1",
        "units": "mm",
        "encoding": "utf-8",
        "active": True,
    }
    profile = cnc._machine_profile(machine_row, tools_by_id)
    assert profile.machine_id == "SBZ-01"
    assert len(profile.tools) == 1
    tool = profile.tools[0]
    assert tool.tool_id == "DR-8"
    assert tool.max_depth_mm == Decimal("30")
    assert profile.max_member_length_mm == Decimal("3500")
    assert profile.clamp_zones[0].label == "Mordaza A"
    assert profile.safe_margin_mm == Decimal("25")


def test_machine_profile_skips_phantom_magazine_entries() -> None:
    """A tool row that vanished (deleted) cannot become an invented tool —
    it is dropped from the magazine and validation reports the blocker."""
    machine_row = {
        "id": uuid4(),
        "code": "SBZ-01",
        "name": "Centro",
        "manufacturer": "",
        "model": "",
        "controller_family": "NEUTRAL",
        "coordinate_systems": ["MEMBER_PLAN"],
        "supported_kinds": None,
        "supported_faces": None,
        "max_member_length_mm": None,
        "safe_margin_mm": None,
        "clamp_zones": [],
        "tool_ids": [str(uuid4())],
        "postprocessor_id": "neutral-ops-v1",
        "postprocessor_version": "1",
        "units": "mm",
        "encoding": "utf-8",
        "active": True,
    }
    profile = cnc._machine_profile(machine_row, {})
    assert profile.tools == []


def test_program_no_uses_physical_codes() -> None:
    no = cnc._program_no(
        order_code="OT-0001", member_label="M-07",
        machine_code="SBZ-01", seq=2,
    )
    assert no == "OT-0001-M07-SBZ-01-02"


# --- P14: honest emitters, declared-not-emitted gaps, authority audit ---


def _machine_row(**over) -> dict:
    base = {
        "id": uuid4(),
        "code": "SBZ-01",
        "name": "Centro",
        "manufacturer": "",
        "model": "",
        "controller_family": "NEUTRAL",
        "coordinate_systems": ["MEMBER_PLAN"],
        "supported_kinds": ["HANDLE_PREP", "DRILL", "LOCK_PREP"],
        "supported_faces": None,
        "max_member_length_mm": None,
        "safe_margin_mm": None,
        "clamp_zones": [],
        "tool_ids": [],
        "postprocessor_id": "neutral-ops-v1",
        "postprocessor_version": "1",
        "units": "mm",
        "encoding": "utf-8",
        "active": True,
        "machine_type": "MACHINING_CENTER",
        "axes_count": 3,
        "travel_x_mm": None,
        "travel_y_mm": None,
        "travel_z_mm": None,
    }
    base.update(over)
    return base


def _op(kind: str, host: str = "m1", host_kind: str = "MEMBER"):
    """Minimal op stand-in — _declared_gaps only reads .kind/.host_kind/.host."""
    class _Op:
        pass
    op = _Op()
    op.kind = type("K", (), {"value": kind})()
    op.host_kind = host_kind
    op.host = host
    return op


def _bundle(**over) -> dict:
    base = {
        "ops": [],
        "order": {"id": str(uuid4()), "order_code": "OT-1"},
        "version_snapshot": {"positions": []},
        "position_id": None,
        "payload": {},
    }
    base.update(over)
    return base


def test_postprocessor_registry_blocks_unimplemented_emitter() -> None:
    assert cnc._postprocessor("neutral-ops-v1") is not None
    assert cnc._postprocessor("gcode-fanuc-9000") is None
    assert cnc._postprocessor(None) is not None  # default is the neutral one


def test_machine_type_and_axes_validation() -> None:
    assert cnc._machine_type(None) == "MACHINING_CENTER"
    assert cnc._machine_type("COPY_ROUTER") == "COPY_ROUTER"
    with pytest.raises(DocumentaryError):
        cnc._machine_type("LASER")
    assert cnc._axes_count(None) is None
    assert cnc._axes_count("3") == 3
    with pytest.raises(DocumentaryError):
        cnc._axes_count("9")


def test_declared_gaps_surface_annotations_and_hardware() -> None:
    bundle = _bundle(
        ops=[_op("SAW_CUT", host="bar-1", host_kind="BAR")],
        version_snapshot={
            "positions": [
                {
                    "position_id": "P1",
                    "bay_id": "b1",
                    "leaf_id": "l1",
                    "workshop_annotations": [
                        {"bay_id": "b1", "leaf_id": "l1",
                         "bottom_drain_holes_mm": "4"}
                    ],
                    "handle_intents": [{"u_mm": "100"}],
                }
            ]
        },
        payload={
            "hardware_machining": [
                {"bay_id": "b1", "leaf_id": "l1", "kit_sku": "KIT-X",
                 "kind": "HINGE_PREP", "status": "DECLARED_NOT_EMITTED"},
                {"bay_id": "b1", "leaf_id": "l1", "kit_sku": "KIT-X",
                 "kind": "LOCK_PREP", "status": "EMITTED", "u_mm": "55"},
            ]
        },
    )
    gaps = cnc._declared_gaps(bundle)
    by_kind = {gap["kind"]: gap for gap in gaps}
    assert set(by_kind) == {"DRAINAGE", "HANDLE_PREP", "HINGE_PREP"}
    assert by_kind["DRAINAGE"]["source"] == "workshop_annotations.bottom_drain_holes_mm"
    assert by_kind["DRAINAGE"]["cause"] == "no_rule"
    assert by_kind["HANDLE_PREP"]["source"] == "handle_intents"
    # hardware declaration without coordinates → honest "no_coordinates"
    assert by_kind["HINGE_PREP"]["cause"] == "no_coordinates"
    assert by_kind["HINGE_PREP"]["kit_sku"] == "KIT-X"
    # EMITTED declarations are not gaps
    assert "LOCK_PREP" not in by_kind
    # Every gap carries a stable id
    assert all(gap["gap_id"] for gap in gaps)


def test_gap_machine_checks_name_the_cause() -> None:
    tool_id = uuid4()
    tools = {
        str(tool_id): {
            "id": tool_id, "active": True,
            "compatible_kinds": ["DRAINAGE"],
        }
    }
    capable = _machine_row(
        code="M-OK", tool_ids=[str(tool_id)],
        supported_kinds=["DRILL", "DRAINAGE"],
    )
    wrong_kind = _machine_row(
        code="M-NOKIND", supported_kinds=["DRILL"], tool_ids=[str(tool_id)]
    )
    no_tool = _machine_row(
        code="M-NOTOOL", supported_kinds=["DRAINAGE"], tool_ids=[]
    )
    no_emitter = _machine_row(
        code="M-NOEMIT", supported_kinds=["DRAINAGE"],
        tool_ids=[str(tool_id)], postprocessor_id="vendor-x"
    )
    machines = [capable, wrong_kind, no_tool, no_emitter]
    gap = {
        "kind": "DRAINAGE", "op_kind": "DRAINAGE", "cause": "no_rule",
        "source": "workshop_annotations.bottom_drain_holes_mm",
    }
    cnc._gap_machine_checks([gap], machines, tools)
    checks = {c["machine_code"]: c for c in gap["machines"]}
    assert checks["M-OK"]["can_run"] is True
    assert checks["M-NOKIND"]["cause"] == "unsupported_kind"
    assert checks["M-NOTOOL"]["cause"] == "no_tool"
    assert checks["M-NOEMIT"]["cause"] == "emitter_not_implemented"
    # An OTHER hardware declaration can't be assessed against a kind
    gap_other = {"kind": "OTHER", "op_kind": None, "cause": "no_coordinates"}
    cnc._gap_machine_checks([gap_other], machines, tools)
    assert all(
        c["cause"] in {"unassessable", "emitter_not_implemented"}
        for c in gap_other["machines"]
    )


def test_authority_action_naming() -> None:
    assert cnc._authority_action(None, {"active": True}) == "created"
    assert cnc._authority_action({"active": True}, {"active": False}) == "deactivated"
    assert cnc._authority_action({"active": False}, {"active": True}) == "reactivated"
    assert cnc._authority_action({"active": True}, {"active": True}) == "updated"


def test_program_compare_diffs_operations() -> None:
    base_id, other_id = uuid4(), uuid4()
    op_a = {"operation_id": "op1", "kind": "DRILL", "u_mm": "100",
            "coordinate_system": "MEMBER_PLAN", "face": "OUTSIDE_FACE"}
    op_b = {"operation_id": "op2", "kind": "SLOT", "u_mm": "200"}
    op_changed_old = {"operation_id": "op3", "kind": "DRILL", "u_mm": "50"}
    op_changed_new = {"operation_id": "op3", "kind": "DRILL", "u_mm": "75"}

    def _program_row(pid, ops):
        return {
            "id": str(pid), "program_no": f"P-{str(pid)[:4]}",
            "member_id": "m1", "member_label": "M-01",
            "operation_count": len(ops), "verdict": "PASS",
            "fingerprint": "f" * 64, "files": json.dumps(
                {"operations.json": json.dumps({"operations": ops})}
            ),
            "created_at": "2026-01-01", "machine_id": str(uuid4()),
        }

    fake_rows = [
        _program_row(base_id, [op_a, op_changed_old]),
        _program_row(other_id, [op_b, op_changed_new]),
    ]
    with patch("production.cnc.rows", return_value=fake_rows):
        diff = cnc.program_compare(
            org_id=uuid4(), program_id=base_id, other_id=other_id
        )
    assert diff["counts"]["added"] == 1
    assert diff["counts"]["removed"] == 1
    assert diff["counts"]["changed"] == 1
    assert diff["added"][0]["operation_id"] == "op2"
    assert diff["changed"][0]["fields"]["u_mm"] == {"from": "50", "to": "75"}


def test_same_input_produces_same_program_fingerprint() -> None:
    """Misma entrada → mismo hash de programa, dos veces."""
    from production import service

    machine_row = _machine_row()
    profile_a = cnc._machine_profile(machine_row, {})
    profile_b = cnc._machine_profile(dict(machine_row), {})
    fp_a = cnc._machine_fingerprint(profile_a)
    fp_b = cnc._machine_fingerprint(profile_b)
    assert fp_a == fp_b
    plan_fp = service._ops_source_fingerprint(
        {"bars": {"plan_seed": "s1", "workshop_cut_plan": []}},
        [{"unit": "u1"}],
    )
    plan_fp_again = service._ops_source_fingerprint(
        {"bars": {"plan_seed": "s1", "workshop_cut_plan": []}},
        [{"unit": "u1"}],
    )
    assert plan_fp == plan_fp_again
    assert cnc._program_input(plan_fp, fp_a) == cnc._program_input(plan_fp, fp_b)


def _scope_client(monkeypatch, role: str):
    """Replica of test_production._client_with_scope for CNC endpoints."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from rest_framework.test import APIClient

    from production import views as production_views

    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        assert role in allowed
        tenant = SimpleNamespace(
            active_organization=SimpleNamespace(
                organization_id=org_id, role=role
            )
        )
        yield token, tenant, org_id

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(
        user=SimpleNamespace(is_authenticated=True), token=object()
    )
    return client, token, org_id


def test_machine_crud_denied_for_estimator(monkeypatch) -> None:
    org_id = uuid4()
    from contextlib import contextmanager
    from types import SimpleNamespace

    from authentication.errors import contract_error
    from production import views as production_views
    from rest_framework.test import APIClient

    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        if "ESTIMATOR" in allowed:
            tenant = SimpleNamespace(
                active_organization=SimpleNamespace(
                    organization_id=org_id, role="ESTIMATOR"
                )
            )
            yield token, tenant, org_id
        else:
            raise contract_error(403, "documentary_permission_denied", "denied")

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(
        user=SimpleNamespace(is_authenticated=True), token=object()
    )
    assert client.post(
        "/api/v1/production/cnc/machines/",
        {"code": "M-1", "name": "Router"},
        format="json",
    ).status_code == 403
    assert client.post(
        "/api/v1/production/cnc/tools/",
        {"code": "T-1", "name": "Broca", "kind": "DRILL_BIT"},
        format="json",
    ).status_code == 403
    assert client.patch(
        f"/api/v1/production/cnc/machines/{uuid4()}/",
        {"name": "Otro"},
        format="json",
    ).status_code == 403
    assert client.patch(
        f"/api/v1/production/cnc/tools/{uuid4()}/",
        {"name": "Otra"},
        format="json",
    ).status_code == 403


def test_machine_crud_allows_workshop_manager(monkeypatch) -> None:
    client, token, org_id = _scope_client(monkeypatch, "WORKSHOP_MANAGER")
    seen = {}

    def fake_create(*, org_id, actor_id, data):
        seen.update(org_id=org_id, actor_id=actor_id, data=data)
        return {"id": uuid4(), "code": data["code"], "name": data["name"]}

    monkeypatch.setattr(cnc, "create_machine", fake_create)
    response = client.post(
        "/api/v1/production/cnc/machines/",
        {
            "code": "CNC-02",
            "name": "Router",
            "machine_type": "ROUTER",
            "axes_count": "3",
        },
        format="json",
    )
    assert response.status_code == 201
    assert seen["org_id"] == org_id
    assert seen["actor_id"] == token.user_id
    assert seen["data"]["machine_type"] == "ROUTER"


def test_machine_create_maps_invalid_to_400(monkeypatch) -> None:
    client, _, _ = _scope_client(monkeypatch, "WORKSHOP_MANAGER")

    def fake_create(**kwargs):
        raise DocumentaryError("cnc_machine_invalid")

    monkeypatch.setattr(cnc, "create_machine", fake_create)
    response = client.post(
        "/api/v1/production/cnc/machines/",
        {"code": "CNC-X", "name": "x", "machine_type": "LASER"},
        format="json",
    )
    # DocumentaryError maps to the contract's 422 — the client gets the
    # Spanish detail, not a stack trace.
    assert response.status_code == 422
