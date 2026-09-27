"""Unit tests for the production service + views."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from documents.repository import DocumentaryError
from production import service, views as production_views


@contextmanager
def _atomic():
    yield


def _tenant(role: str, org_id):
    return SimpleNamespace(
        active_organization=SimpleNamespace(organization_id=org_id, role=role)
    )


def _client_with_scope(monkeypatch, role: str):
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        assert role in allowed
        yield token, _tenant(role, org_id), org_id

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    return client, token, org_id


def _version_row(snapshot: dict) -> dict:
    return {
        "id": uuid4(),
        "project_id": uuid4(),
        "revision_code": "REV-A",
        "snapshot_json": snapshot,
        "production_allowed": True,
    }


_POSITION_ID = str(uuid4())
_SNAPSHOT = {
    "positions": [
        {
            "id": _POSITION_ID,
            "system_id": str(uuid4()),
            # The authority the version sealed under — release consumes this
            # verbatim; a later catalog/profile edit can never re-route it.
            "process_facts": {
                "system": {
                    "material": "PVC",
                    "end_milling_overlap_mm": "0.00",
                    "process_profile_id": None,
                },
                "profile": {
                    "id": "11111111-2222-3333-4444-555555555555",
                    "code": "PVC_WELDED",
                    "version": 1,
                    "joining_method": "WELD",
                    "stations": [
                        {"code": "CUT", "when": "auto"},
                        {"code": "MACHINING", "when": "auto"},
                        {"code": "WELD", "when": "required"},
                        {"code": "CLEAN", "when": "required"},
                        {"code": "SASH_ASSEMBLE", "when": "auto"},
                        {"code": "HARDWARE", "when": "auto"},
                        {"code": "GLAZE", "when": "auto"},
                        {"code": "QC", "when": "required"},
                        {"code": "PACK", "when": "required"},
                    ],
                    "operation_station_map": {"END_MACHINING": "MACHINING", "SAW_CUT": "CUT"},
                },
                "resolved_via": "material_default",
            },
        }
    ],
    "bom": [
        {
            "position_id": _POSITION_ID,
            "quantity": 1,
            "engine_result": {
                "profile_cuts": [{"sku": "MARCO", "role": "SASH", "length_mm": "900"}],
                "reinforcements": [],
                "glasses": [{"width_mm": "800", "height_mm": "600"}],
                "panels": [],
                "hardware_items": [{"sku": "KIT-1"}],
            },
        }
    ]
}


def _profile(
    code: str,
    stations: list[dict[str, str]],
    *,
    operation_station_map: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "id": "11111111-2222-3333-4444-555555555555",
        "code": code,
        "version": 1,
        "joining_method": "WELD" if "WELD" in [s["code"] for s in stations] else "NONE",
        "stations": stations,
        "operation_station_map": operation_station_map or {},
    }


def test_routing_skips_cut_and_glaze_without_materials() -> None:
    routing = service._routing({"glasses": [], "panels": [], "profile_cuts": [], "reinforcements": []}, profile=None)
    assert routing == ["ASSEMBLE", "QC", "PACK"]
    routing = service._routing(
        {"profile_cuts": [{"sku": "x"}], "glasses": [{"a": 1}], "panels": []},
        profile=None,
    )
    assert routing == ["CUT", "ASSEMBLE", "GLAZE", "QC", "PACK"]


def test_routing_follows_the_declared_profile_stations() -> None:
    engine = {
        "profile_cuts": [{"sku": "x", "role": "SASH"}],
        "glasses": [{"a": 1}],
        "panels": [],
        "reinforcements": [],
        "hardware_items": [{"sku": "h"}],
    }
    pvc = _profile("PVC_WELDED", [
        {"code": "CUT", "when": "auto"},
        {"code": "MACHINING", "when": "auto"},
        {"code": "WELD", "when": "required"},
        {"code": "CLEAN", "when": "required"},
        {"code": "SASH_ASSEMBLE", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ])
    assert service._routing(engine, profile=pvc) == [
        "CUT", "WELD", "CLEAN", "SASH_ASSEMBLE", "HARDWARE", "GLAZE", "QC", "PACK"
    ]
    assert service._routing(engine, profile=pvc, end_milling_overlap_mm="1.50") == [
        "CUT", "MACHINING", "WELD", "CLEAN", "SASH_ASSEMBLE", "HARDWARE", "GLAZE", "QC", "PACK"
    ]
    alu = _profile("ALU_CRIMPED", [
        {"code": "CUT", "when": "auto"},
        {"code": "MACHINING", "when": "required"},
        {"code": "CRIMP", "when": "required"},
        {"code": "SASH_ASSEMBLE", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ])
    assert service._routing(engine, profile=alu) == [
        "CUT", "MACHINING", "CRIMP", "SASH_ASSEMBLE", "HARDWARE", "GLAZE", "QC", "PACK"
    ]
    # A fixed window has no sash to assemble and no hardware to mount — the
    # stations follow the sealed result under the declared template.
    fixed = {
        "profile_cuts": [{"sku": "x", "role": "FRAME"}],
        "glasses": [{"a": 1}],
        "panels": [],
        "reinforcements": [],
        "hardware_items": [],
    }
    assert service._routing(fixed, profile=pvc) == [
        "CUT", "WELD", "CLEAN", "GLAZE", "QC", "PACK"
    ]
    assert service._routing(fixed, profile=alu) == [
        "CUT", "MACHINING", "CRIMP", "GLAZE", "QC", "PACK"
    ]


def test_frameless_profile_never_acquires_joining_stations() -> None:
    """The pane is the product: FRAMELESS_GLASS has no WELD/CRIMP in its
    template regardless of the associated system's material family."""
    frameless_profile = _profile("FRAMELESS_GLASS", [
        {"code": "CUT", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ])
    engine = {
        "profile_cuts": [{"sku": "CANAL", "role": "CHANNEL"}],
        "glasses": [{"a": 1}],
        "panels": [],
        "reinforcements": [],
        "fittings": [{"sku": "CLAMP-1"}],
    }
    routing = service._routing(engine, profile=frameless_profile)
    assert "WELD" not in routing
    assert "CRIMP" not in routing
    assert routing == ["CUT", "HARDWARE", "GLAZE", "QC", "PACK"]


def test_mixed_assembly_merges_frameless_into_the_declared_profile() -> None:
    """A framed unit + a frameless pane in one position: the declared
    profile keeps its joining authority while the pane contributes the
    stations/op mappings only frameless work produces."""
    alu = _profile("ALU_CRIMPED", [
        {"code": "CUT", "when": "auto"},
        {"code": "MACHINING", "when": "required"},
        {"code": "CRIMP", "when": "required"},
        {"code": "SASH_ASSEMBLE", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ], operation_station_map={
        "SAW_CUT": "CUT", "END_MACHINING": "MACHINING",
        "HANDLE_PREP": "MACHINING", "DRAINAGE": "MACHINING",
    })
    frameless = _profile("FRAMELESS_GLASS", [
        {"code": "CUT", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ], operation_station_map={"SAW_CUT": "CUT", "HANDLE_PREP": "HARDWARE"})
    frameless["optional_operations"] = ["HANDLE_PREP"]

    merged = service._merge_frameless(alu, frameless)
    codes = [s["code"] for s in merged["stations"]]
    assert "CRIMP" in codes and "HARDWARE" in codes
    # A pane is never machined: its prep ops land on the fitting station.
    assert merged["operation_station_map"]["HANDLE_PREP"] == "HARDWARE"
    assert merged["operation_station_map"]["END_MACHINING"] == "MACHINING"
    assert "HANDLE_PREP" in merged["optional_operations"]


def test_mixed_resolution_keeps_joining_and_routes_pane_ops() -> None:
    alu = _profile("ALU_CRIMPED", [
        {"code": "CUT", "when": "auto"},
        {"code": "CRIMP", "when": "required"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ], operation_station_map={"SAW_CUT": "CUT", "HANDLE_PREP": "MACHINING"})
    frameless = _profile("FRAMELESS_GLASS", [
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
    ], operation_station_map={"HANDLE_PREP": "HARDWARE"})
    frameless["optional_operations"] = ["HANDLE_PREP"]

    def fake_load(org_id, **kwargs):
        if kwargs.get("product_kind") == "FRAMELESS":
            return frameless, "product_kind"
        if kwargs.get("material") == "ALUMINIUM":
            return alu, "material_default"
        return None, None

    # Framed sash + frameless channel pane in the same sealed result.
    engine = {
        "profile_cuts": [
            {"sku": "MARCO", "role": "FRAME"},
            {"sku": "CANAL", "role": "CHANNEL"},
        ],
        "glasses": [{"a": 1, "exposed_edges": [0]}],
        "panels": [],
        "fittings": [{"sku": "CLAMP-1"}],
        "hardware_items": [{"sku": "h"}],
    }
    with patch("production.service._load_profile_for", side_effect=fake_load):
        profile, via = service._resolve_process_profile(
            uuid4(), engine, {"material": "ALUMINIUM"}
        )
    assert via == "material_default_mixed"
    assert profile["operation_station_map"]["HANDLE_PREP"] == "HARDWARE"


def test_handle_ops_land_on_the_profile_declared_station() -> None:
    frameless = _profile("FRAMELESS_GLASS", [
        {"code": "CUT", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ], operation_station_map={"SAW_CUT": "CUT", "HANDLE_PREP": "HARDWARE"})
    engine = {
        "profile_cuts": [{"sku": "CANAL", "role": "CHANNEL"}],
        "glasses": [{"a": 1}],
        "panels": [],
        "fittings": [{"sku": "CLAMP-1"}],
    }
    routing = service._routing(engine, profile=frameless, has_handles=True)
    assert "HARDWARE" in routing
    assert "MACHINING" not in routing
    # And a profile that maps prep to the mill still lands MACHINING.
    pvc = _profile("PVC_WELDED", [
        {"code": "CUT", "when": "auto"},
        {"code": "MACHINING", "when": "auto"},
        {"code": "WELD", "when": "required"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ], operation_station_map={"SAW_CUT": "CUT", "HANDLE_PREP": "MACHINING"})
    framed = {"profile_cuts": [{"sku": "x", "role": "SASH"}], "glasses": [{"a": 1}]}
    assert service._routing(framed, profile=pvc, has_handles=True) == [
        "CUT", "MACHINING", "WELD", "QC", "PACK"
    ]


def test_process_authority_freezes_the_declared_map() -> None:
    authority = service._process_authority(
        _profile(
            "ALU_CRIMPED", [],
            operation_station_map={"END_MACHINING": "MACHINING", "HANDLE_PREP": "HARDWARE"},
        ),
        "material_default",
    )
    assert authority["code"] == "ALU_CRIMPED"
    assert authority["version"] == 1
    assert authority["resolved_via"] == "material_default"
    assert authority["operation_station_map"]["HANDLE_PREP"] == "HARDWARE"
    assert service._process_authority(None, None)["resolved_via"] == "fallback"


def test_release_rejects_not_allowed_version() -> None:
    version = _version_row({"bom": []})
    version["production_allowed"] = False
    with patch("production.service.one", return_value=version), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch("production.service.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            service.release_production(org_id=uuid4(), version_id=uuid4(), actor_id=uuid4())
    assert error.value.code == "version_not_releasable"


def test_release_creates_work_order_with_steps() -> None:
    snapshot = {
        "positions": [
            {
                "id": _POSITION_ID,
                "system_id": str(uuid4()),
                "process_facts": _SNAPSHOT["positions"][0]["process_facts"],
            }
        ],
        "bom": _SNAPSHOT["bom"],
    }
    version = _version_row(snapshot)
    order_id = uuid4()
    inserted_rows = []

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "INSERT INTO public.orders" in query:
            return [{"id": order_id}]
        if "FROM public.orders" in query and "GROUP BY" in query:
            return [
                {
                    "id": order_id,
                    "order_code": "OT-REV-A-01",
                    "order_type": "WORKSHOP_OT",
                    "status": "RELEASED",
                    "payload_json": service._work_order_payload(_SNAPSHOT["bom"][0]),
                    "project_version_id": version["id"],
                    "created_at": "2026-09-23T00:00:00Z",
                    "steps_total": 5,
                    "steps_done": 0,
                }
            ]
        inserted_rows.append(query)
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        output = service.release_production(
            org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
        )
    assert output["released"] == 1 and output["created"] == 1
    step_inserts = [q for q in inserted_rows if "production_steps" in q]
    # The sealed PVC_WELDED profile routes: CUT WELD CLEAN SASH_ASSEMBLE
    # HARDWARE GLAZE QC PACK (MACHINING has no work in this BOM).
    assert len(step_inserts) == 8
    event_inserts = [q for q in inserted_rows if "production_step_events" in q]
    assert len(event_inserts) == 1


_PVC_PROFILE_ROW = {
    "id": "11111111-2222-3333-4444-555555555555",
    "org_id": None,
    "code": "PVC_WELDED",
    "version": 1,
    "joining_method": "WELD",
    "stations": [
        {"code": "CUT", "when": "auto"},
        {"code": "MACHINING", "when": "auto"},
        {"code": "WELD", "when": "required"},
        {"code": "CLEAN", "when": "required"},
        {"code": "SASH_ASSEMBLE", "when": "auto"},
        {"code": "HARDWARE", "when": "auto"},
        {"code": "GLAZE", "when": "auto"},
        {"code": "QC", "when": "required"},
        {"code": "PACK", "when": "required"},
    ],
    "operation_station_map": {"END_MACHINING": "MACHINING", "SAW_CUT": "CUT"},
}


def test_release_routes_steps_by_declared_process_profile() -> None:
    version = _version_row(_SNAPSHOT)
    order_id = uuid4()
    inserted_rows = []

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "FROM public.profile_systems" in query:
            return [
                {
                    "id": _SNAPSHOT["positions"][0]["system_id"],
                    "material": "PVC",
                    "end_milling_overlap_mm": "0.00",
                    "process_profile_id": None,
                }
            ]
        if "FROM public.manufacturing_process_profiles" in query:
            return [_PVC_PROFILE_ROW]
        if "INSERT INTO public.orders" in query:
            return [{"id": order_id}]
        if "FROM public.orders" in query and "GROUP BY" in query:
            return [
                {
                    "id": order_id,
                    "order_code": "OT-REV-A-01",
                    "order_type": "WORKSHOP_OT",
                    "status": "RELEASED",
                    "payload_json": service._work_order_payload(
                        _SNAPSHOT["bom"][0],
                        system_facts={"material": "PVC", "end_milling_overlap_mm": "0.00"},
                    ),
                    "project_version_id": version["id"],
                    "created_at": "2026-09-23T00:00:00Z",
                    "steps_total": 8,
                    "steps_done": 0,
                }
            ]
        inserted_rows.append(query)
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        output = service.release_production(
            org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
        )
    assert output["released"] == 1 and output["created"] == 1
    step_inserts = [q for q in inserted_rows if "production_steps" in q]
    assert len(step_inserts) == 8  # CUT WELD CLEAN SASH_ASSEMBLE HARDWARE GLAZE QC PACK


def test_release_freezes_process_authority_into_the_payload() -> None:
    version = _version_row(_SNAPSHOT)
    order_id = uuid4()
    payloads: list[dict[str, object]] = []

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "FROM public.profile_systems" in query:
            return [
                {
                    "id": _SNAPSHOT["positions"][0]["system_id"],
                    "material": "PVC",
                    "end_milling_overlap_mm": "0.00",
                    "process_profile_id": None,
                }
            ]
        if "FROM public.manufacturing_process_profiles" in query:
            return [_PVC_PROFILE_ROW]
        if "INSERT INTO public.orders" in query:
            return [{"id": order_id}]
        if "FROM public.orders" in query and "GROUP BY" in query:
            return [{"id": order_id, "order_code": "OT", "order_type": "WORKSHOP_OT",
                     "status": "RELEASED", "payload_json": {},
                     "project_version_id": version["id"], "created_at": "x",
                     "steps_total": 0, "steps_done": 0}]
        return []

    original = service._work_order_payload

    def capture(*args, **kwargs):
        payload = original(*args, **kwargs)
        payloads.append(payload)
        return payload

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ), patch("production.service._work_order_payload", side_effect=capture):
        service.release_production(
            org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
        )
    authority = payloads[0]["process_authority"]
    assert authority["code"] == "PVC_WELDED"
    assert authority["version"] == 1
    assert authority["resolved_via"] == "material_default"
    assert authority["operation_station_map"]["END_MACHINING"] == "MACHINING"


def test_release_without_process_authority_is_refused() -> None:
    """Versions sealed without a bound process profile carry
    resolved_via='generic_fallback' — release must refuse rather than ship
    an invented routing (review CAT-04). The remedy is re-sealing the
    position under a catalog with real process authority."""
    snapshot = {
        "positions": [{"id": _POSITION_ID, "system_id": str(uuid4())}],
        "bom": [dict(_SNAPSHOT["bom"][0])],
    }
    version = _version_row(snapshot)

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "revision_code" in query:
            return [{"code": version["revision_code"]}]
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.release_production(
                org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
            )
    assert error.value.code == "production_process_unresolved"


def test_release_replay_returns_existing() -> None:
    version = _version_row(_SNAPSHOT)
    existing_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        if "SELECT id FROM public.orders" in query:
            return {"id": existing_id}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "INSERT INTO public.orders" in query:
            return []  # conflict → no row
        if "GROUP BY" in query:
            return [
                {
                    "id": existing_id,
                    "order_code": "OT-REV-A-01",
                    "order_type": "WORKSHOP_OT",
                    "status": "RELEASED",
                    "payload_json": {"position_id": _SNAPSHOT["bom"][0]["position_id"]},
                    "project_version_id": version["id"],
                    "created_at": "2026-09-23T00:00:00Z",
                    "steps_total": 5,
                    "steps_done": 2,
                }
            ]
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        output = service.release_production(
            org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
        )
    assert output["released"] == 1 and output["created"] == 0


def _transition_fakes(step: dict, order_status: str):
    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": order_status}
        if "sequence < %s" in query:
            return {"remaining": 0}
        if "FOR UPDATE OF s" in query:
            return step
        raise AssertionError(query)

    return fake_one


def _step_row(**overrides) -> dict:
    base = {
        "id": uuid4(),
        "order_id": uuid4(),
        "status": "READY",
        "sequence": 1,
        "code": "CUT",
        "label": "x",
        "work_center_id": None,
        "started_at": None,
        "finished_at": None,
        "actor_id": None,
        "note": None,
    }
    base.update(overrides)
    return base


def test_transition_step_rejects_invalid_state() -> None:
    step = _step_row(status="DONE")
    fake_one = _transition_fakes(step, "IN_PROGRESS")

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch("production.service.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "step_transition_invalid"


def test_transition_step_completed_order_blocked() -> None:
    step = _step_row()
    fake_one = _transition_fakes(step, "COMPLETED")

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch("production.service.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_order_completed"


def test_start_from_blocked_step_is_rejected() -> None:
    step = _step_row(status="BLOCKED")
    fake_one = _transition_fakes(step, "IN_PROGRESS")

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch("production.service.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "step_transition_invalid"


def test_unassigned_step_refuses_progress_until_a_center_exists() -> None:
    # A step released while its center was inactive must not silently start —
    # the payload blocker is the shop's to-do, not decoration.
    step = _step_row(status="READY", code="CUT")
    fake_one = _transition_fakes(step, "IN_PROGRESS")

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_center_unassigned"


def test_start_refused_while_an_earlier_step_is_open() -> None:
    # Routing is sequential: GLAZE may not start while CUT is still open —
    # the stepper is a sequence, not a checklist.
    step = _step_row(status="READY", code="GLAZE", sequence=2)

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        if "sequence < %s" in query:
            return {"remaining": 1}
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "step_sequence_blocked"


def test_unassigned_step_adopts_a_later_activated_center() -> None:
    step = _step_row(status="READY", code="CUT")
    center = {"id": uuid4(), "code": "SAW-1", "name": "Saw"}
    updates: list[str] = []

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "FOR UPDATE OF s" in query:
            return step
        if "sequence < %s" in query:
            return {"remaining": 0}
        if "SELECT status::text" in query:
            return {"status": "IN_PROGRESS"}
        if "FROM public.production_steps s" in query:
            return {**step, "status": "IN_PROGRESS", "work_center_id": center["id"],
                    "work_center_code": center["code"], "work_center_name": center["name"]}
        if "FROM public.production_steps" in query:
            return {"total": 2, "done": 0, "blocked": 0, "in_progress": 1}
        if "UPDATE public.orders" in query or "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        raise AssertionError(query)

    def fake_rows(query, params=(), code=None):
        if "FROM public.work_centers" in query:
            return [center]
        updates.append(query)
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        service.transition_step(
            org_id=uuid4(), step_id=step["id"], action="START",
            actor_id=uuid4(), note=None,
        )
    assert step["work_center_id"] == center["id"]
    # The step is assigned and the payload blocker cleared.
    assert any("SET work_center_id" in query for query in updates)
    assert any("jsonb_set" in query for query in updates)


def test_pending_remake_step_refuses_progress_without_a_center() -> None:
    # Remake steps are copied unassigned as PENDING — the same gate must hold.
    step = _step_row(status="PENDING", code="CUT")
    fake_one = _transition_fakes(step, "IN_PROGRESS")

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="START",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_center_unassigned"


def test_note_action_requires_text() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.transition_step(
            org_id=uuid4(), step_id=uuid4(), action="NOTE",
            actor_id=uuid4(), note="   ",
        )
    assert error.value.code == "step_note_required"


def _qc_fakes(step: dict):
    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "FROM public.orders" in query and "FOR UPDATE" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        if "status::text AS status" in query:
            return {"status": "IN_PROGRESS"}
        if "COUNT(*)" in query and "production_steps" in query:
            return {"total": 3, "done": 0, "blocked": 0, "in_progress": 1}
        if "UPDATE public.orders SET status" in query:
            return {"status": "IN_PROGRESS"}
        if "FROM public.production_steps s" in query:
            return step
        raise AssertionError(query)

    return fake_one


def test_qc_check_records_structured_event() -> None:
    step = _step_row(status="IN_PROGRESS", code="QC")
    inserted = []

    def fake_rows(query, params=()):
        if "INSERT INTO public.production_step_events" in query:
            inserted.append(params)
        return []

    with patch("production.service.one", side_effect=_qc_fakes(step)), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        output = service.transition_step(
            org_id=uuid4(), step_id=step["id"], action="QC_CHECK",
            actor_id=uuid4(), note=None,
            qc_check={
                "check": "Medida total", "expected": "1200mm",
                "actual": "1201mm", "item_code": "M-01", "result": "PASS",
            },
        )
    assert output["step"]["status"] == "IN_PROGRESS"
    assert len(inserted) == 1
    params = inserted[0]
    assert params[3] == "QC_CHECK"
    payload = json.loads(params[5])
    assert payload["qc_check"]["check"] == "Medida total"
    assert payload["qc_check"]["actual"] == "1201mm"
    assert payload["qc_check"]["item_code"] == "M-01"
    assert payload["qc_check"]["result"] == "PASS"


def test_qc_check_rejected_on_non_qc_step() -> None:
    step = _step_row(status="IN_PROGRESS", code="CUT")

    with patch("production.service.one", side_effect=_qc_fakes(step)), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="QC_CHECK",
                actor_id=uuid4(), note=None,
                qc_check={"check": "x", "result": "PASS"},
            )
    assert error.value.code == "step_transition_invalid"


def test_qc_check_requires_payload() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.transition_step(
            org_id=uuid4(), step_id=uuid4(), action="QC_CHECK",
            actor_id=uuid4(), note=None,
        )
    assert error.value.code == "qc_check_required"


def test_qc_check_requires_valid_result() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.transition_step(
            org_id=uuid4(), step_id=uuid4(), action="QC_CHECK",
            actor_id=uuid4(), note=None,
            qc_check={"check": "Medida", "result": "MAYBE"},
        )
    assert error.value.code == "qc_check_result_invalid"


def test_qc_check_not_allowed_with_other_actions() -> None:
    with pytest.raises(DocumentaryError) as error:
        service.transition_step(
            org_id=uuid4(), step_id=uuid4(), action="START",
            actor_id=uuid4(), note=None,
            qc_check={"check": "Medida", "result": "PASS"},
        )
    assert error.value.code == "step_transition_invalid"


def test_hold_event_only_appended_once() -> None:
    captured = []

    def fake_one(query, params=(), code=None):
        if "SELECT status::text" in query:
            return {"status": "HOLD"}
        if "production_steps" in query:
            return {"total": 2, "done": 0, "blocked": 1, "in_progress": 0}
        if "UPDATE public.orders" in query:
            return {"status": "HOLD"}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        captured.append(query)
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ):
        status = service._refresh_order_status(
            org_id=uuid4(), order_id=uuid4(), actor_id=uuid4()
        )
    assert status == "HOLD"
    assert not any("WO_HOLD" in query for query in captured)


def test_hold_event_appended_on_transition_into_hold() -> None:
    captured = []

    def fake_one(query, params=(), code=None):
        if "SELECT status::text" in query:
            return {"status": "IN_PROGRESS"}
        if "production_steps" in query:
            return {"total": 2, "done": 0, "blocked": 1, "in_progress": 0}
        if "UPDATE public.orders" in query:
            return {"status": "HOLD"}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        captured.append(query)
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ):
        service._refresh_order_status(
            org_id=uuid4(), order_id=uuid4(), actor_id=uuid4()
        )
    assert any("WO_HOLD" in query for query in captured)


def test_order_code_scopes_to_project() -> None:
    snapshot = {
        "project": {"code": "PRO-77"},
        "bom": _SNAPSHOT["bom"],
    }
    version = _version_row(snapshot)
    seen = {}

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return version
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "INSERT INTO public.orders" in query:
            seen["order_code"] = params[2]
            return [{"id": uuid4()}]
        if "GROUP BY" in query:
            return []
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service._ensure_work_centers", return_value=({}, set())
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        service.release_production(
            org_id=uuid4(), version_id=version["id"], actor_id=uuid4()
        )
    assert seen["order_code"] == "OT-PRO-77-REV-A-01"


def test_work_center_upsert_reports_created() -> None:
    row = {
        "id": uuid4(), "code": "X", "name": "x", "kind": "CUT",
        "display_order": 0, "active": True, "created": False,
    }
    with patch("production.service.one", return_value=row), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch("production.service.documentary_backend", side_effect=_atomic):
        center, created = service.create_work_center(
            org_id=uuid4(), code="X", name="x", kind="CUT", display_order=0
        )
    assert created is False
    assert center["code"] == "X"


def test_release_post_forwards_scope(monkeypatch) -> None:
    client, token, org_id = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    seen = {}

    def fake_release(**kwargs):
        seen.update(kwargs)
        return {"version_id": kwargs["version_id"], "released": 1, "created": 1, "orders": []}

    monkeypatch.setattr(service, "release_production", fake_release)
    version_id = uuid4()
    response = client.post(f"/api/v1/production/versions/{version_id}/release/")
    assert response.status_code == 201
    assert seen["actor_id"] == token.user_id
    assert seen["org_id"] == org_id


def test_release_denies_estimator(monkeypatch) -> None:
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        from authentication.errors import contract_error

        if "ESTIMATOR" in allowed and len(allowed) > 1:
            yield token, _tenant("ESTIMATOR", org_id), org_id
        else:
            raise contract_error(403, "documentary_permission_denied", "denied")
            yield

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    response = client.post(f"/api/v1/production/versions/{uuid4()}/release/")
    assert response.status_code == 403


def test_orders_list_allows_installer(monkeypatch) -> None:
    client, _, _ = _client_with_scope(monkeypatch, "INSTALLER")
    monkeypatch.setattr(
        service, "list_production_orders", lambda *, org_id: {"orders": []}
    )
    response = client.get("/api/v1/production/orders/")
    assert response.status_code == 200


def test_step_transition_denies_installer(monkeypatch) -> None:
    org_id = uuid4()
    token = SimpleNamespace(user_id=uuid4(), claims={}, aal="aal1")

    @contextmanager
    def fake_scope(request, allowed):
        from authentication.errors import contract_error

        if "INSTALLER" in allowed:
            yield token, _tenant("INSTALLER", org_id), org_id
        else:
            raise contract_error(403, "documentary_permission_denied", "denied")
            yield

    monkeypatch.setattr(production_views, "documentary_scope", fake_scope)
    client = APIClient()
    client.force_authenticate(user=SimpleNamespace(is_authenticated=True), token=object())
    response = client.post(
        f"/api/v1/production/steps/{uuid4()}/transition/",
        {"action": "START"},
        format="json",
    )
    assert response.status_code == 403


def test_delivery_confirm_payment_denies_installer(monkeypatch) -> None:
    client, _, _ = _client_with_scope(monkeypatch, "INSTALLER")
    response = client.post(
        f"/api/v1/production/orders/{uuid4()}/delivery/confirm/",
        {
            "receiver_name": "Cliente",
            "signature_png": "aGVsbG8=",
            "payment": {"amount": "1500000", "method": "CASH"},
        },
        format="json",
    )
    assert response.status_code == 403


def test_delivery_confirm_payment_allows_estimator(monkeypatch) -> None:
    client, token, _ = _client_with_scope(monkeypatch, "ESTIMATOR")

    def fake_confirm(**kwargs):
        return {"id": uuid4()}

    monkeypatch.setattr(
        "production.views.confirm_delivery", fake_confirm
    )
    monkeypatch.setattr(
        service, "get_delivery", lambda *, org_id, order_id: {"delivery": {}}
    )
    response = client.post(
        f"/api/v1/production/orders/{uuid4()}/delivery/confirm/",
        {
            "receiver_name": "Cliente",
            "signature_png": "aGVsbG8=",
            "payment": {"amount": "1500000", "method": "CASH"},
        },
        format="json",
    )
    assert response.status_code == 201


def test_step_transition_forwards_action(monkeypatch) -> None:
    client, token, _ = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    seen = {}

    def fake_transition(**kwargs):
        seen.update(kwargs)
        return {"step": {}, "order_status": "IN_PROGRESS"}

    monkeypatch.setattr(service, "transition_step", fake_transition)
    response = client.post(
        f"/api/v1/production/steps/{uuid4()}/transition/",
        {"action": "START", "note": "voy"},
        format="json",
    )
    assert response.status_code == 200
    assert seen["action"] == "START"
    assert seen["actor_id"] == token.user_id


def test_optimize_work_order_builds_bar_plan_and_event() -> None:
    from decimal import Decimal

    from dekopen_engine.cutting import (
        CutBar, CutMaterial, CutOptimizationResult, CuttingProfile,
        PurchaseLine, StockRule,
    )

    order_id = uuid4()
    payload = {
        "position_id": str(uuid4()),
        "system_id": str(uuid4()),
        "quantity": 2,
        "materials": {
            "profile_cuts": [
                {
                    "qty": 2, "sku": "MARCO", "role": "FRAME",
                    "material": "PVC", "length_mm": "900.00",
                    "angle_left": "45.0", "angle_right": "45.0",
                }
            ],
            "reinforcements": [], "glasses": [], "panels": [], "hardware_items": [],
        },
    }
    seen = {}

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT-P-REV-A-01",
                "status": "RELEASED", "payload_json": payload,
            }
        if "snapshot_json" in query:
            return {"snapshot_json": {"positions": [], "manufacturing": []}}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "inventory_items" in query:
            return []
        seen.setdefault("writes", []).append(query)
        return []

    stock = StockRule(
        stock_authority_id="S1", workshop_sku="MARCO",
        commercial_sku="P-MARCO-60", manufacturer_name="DEMO",
        supplier_name=None, purchase_unit="BAR",
        material=CutMaterial.PVC, color="BLANCO",
        stock_length_mm=Decimal("6000"),
    )
    authorities = SimpleNamespace(
        stocks=[stock], reinforcement_skus={}, inertias={},
    )
    profile = CuttingProfile(
        id="CP1", code="SAW01", kerf_mm=Decimal("5"),
        head_trim_mm=Decimal("10"), tail_trim_mm=Decimal("10"),
    )
    cut_result = CutOptimizationResult(
        workshop_cut_plan=[CutBar(
            bar_index=1, commercial_sku="P-MARCO-60",
            material=CutMaterial.PVC, color="BLANCO",
            stock_length_mm=Decimal("6000"),
            head_trim_mm=Decimal("10"), tail_trim_mm=Decimal("10"),
            kerf_mm=Decimal("5"), cuts=[],
            kerf_total_mm=Decimal("0"),
            productive_length_mm=Decimal("0"),
            process_consumed_mm=Decimal("0"),
            remainder_mm=Decimal("3000"),
            waste_mm=Decimal("0"),
            yield_pct=Decimal("50"), waste_pct=Decimal("50"),
        )],
        purchase_list=[PurchaseLine(
            commercial_sku="P-MARCO-60", manufacturer="DEMO",
            supplier=None, stock_length_mm=Decimal("6000"),
            material=CutMaterial.PVC, color="BLANCO",
            unit="BAR", qty_bars=1,
        )],
    )

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", return_value=_atomic()), patch(
        "production.service.documentary_backend", return_value=_atomic()
    ), patch(
        "production.service.CuttingRepository"
    ) as repo, patch(
        "production.service.optimize_cut", return_value=cut_result
    ) as cut, patch("production.service.remnants_service") as rem, patch(
        "production.service.production_stock"
    ) as stock:
        rem.bar_remnants_for_authorities.return_value = []
        rem.sheet_remnants_for_sku.return_value = []
        rem.release_reservations.return_value = 0
        stock.release_for_order.return_value = 0
        stock.bar_stock_needs.return_value = []
        stock.unit_stock_needs.return_value = ([], [])
        stock.reserve_for_order.return_value = []
        repo.return_value.for_result.return_value = authorities
        repo.return_value.cutting_profile.return_value = profile
        output = service.optimize_work_order(
            org_id=uuid4(), order_id=order_id, actor_id=uuid4(), color="BLANCO",
        )
    assert output["optimization"]["color"] == "BLANCO"
    assert output["optimization"]["units"] == 2
    pieces_arg = cut.call_args[0][0]
    assert len(pieces_arg) == 4  # qty 2 per unit x 2 units
    assert len({p.unit_index for p in pieces_arg}) == 4  # unique per-unit identity
    writes = seen["writes"]
    assert any("payload_json" in q for q in writes)
    assert any("WO_OPTIMIZED" in q for q in writes)


def test_optimize_routes_shaped_glass_to_unnested() -> None:
    from decimal import Decimal

    from dekopen_engine.cutting import (
        CutOptimizationResult, CuttingProfile,
    )

    order_id = uuid4()
    shape = [
        {"x_mm": "0.00", "y_mm": "0.00"},
        {"x_mm": "2296.22", "y_mm": "0.00"},
        {"x_mm": "2096.22", "y_mm": "1310.00"},
        {"x_mm": "200.00", "y_mm": "1310.00"},
    ]
    payload = {
        "position_id": str(uuid4()),
        "system_id": str(uuid4()),
        "quantity": 1,
        "materials": {
            "profile_cuts": [], "reinforcements": [],
            "glasses": [
                {
                    "bay_id": "B1", "leaf_id": None,
                    "width_mm": "2296.22", "height_mm": "1310.00",
                    "shape": shape,
                    "area_m2": "2.62", "weight_kg": "13.10",
                    "thickness_net_mm": "4.00",
                    "glass_spec": "4", "article_sku": "V4",
                }
            ],
            "panels": [], "hardware_items": [],
        },
    }

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT-P-REV-A-01",
                "status": "RELEASED", "payload_json": payload,
            }
        if "snapshot_json" in query:
            return {"snapshot_json": {"positions": [], "manufacturing": []}}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        return []

    profile = CuttingProfile(
        id="CP1", code="SAW01", kerf_mm=Decimal("5"),
        head_trim_mm=Decimal("10"), tail_trim_mm=Decimal("10"),
    )
    cut_result = CutOptimizationResult(workshop_cut_plan=[], purchase_list=[])
    authorities = SimpleNamespace(stocks=[], reinforcement_skus={}, inertias={})

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", return_value=_atomic()), patch(
        "production.service.documentary_backend", return_value=_atomic()
    ), patch(
        "production.service.CuttingRepository"
    ) as repo, patch(
        "production.service.optimize_cut", return_value=cut_result
    ), patch("production.service.remnants_service") as rem, patch(
        "production.service.production_stock"
    ) as stock:
        rem.bar_remnants_for_authorities.return_value = []
        rem.sheet_remnants_for_sku.return_value = []
        rem.release_reservations.return_value = 0
        stock.release_for_order.return_value = 0
        stock.bar_stock_needs.return_value = []
        stock.unit_stock_needs.return_value = ([], [])
        stock.reserve_for_order.return_value = []
        repo.return_value.for_result.return_value = authorities
        repo.return_value.cutting_profile.return_value = profile
        output = service.optimize_work_order(
            org_id=uuid4(), order_id=order_id, actor_id=uuid4(), color="BLANCO",
        )
    optimization = output["optimization"]
    assert optimization["sheets"] == []
    assert len(optimization["unnested"]) == 1
    flagged = optimization["unnested"][0]
    assert flagged["kind"] == "GLASS"
    assert flagged["reason"] == "shaped_glass_outline"
    assert flagged["shape"] == shape


def test_pick_sheet_rule_prefers_smallest_fitting() -> None:
    from decimal import Decimal

    rules = _sheet_rules_fake(
        [("BIG", "3000", "2000"), ("MID", "2000", "1500"), ("SML", "1200", "900")]
    )
    picked = service._pick_sheet_rule(rules, Decimal("1100"), Decimal("800"))
    assert picked is not None and picked.workshop_sku == "SML"
    rotated = service._pick_sheet_rule(rules, Decimal("800"), Decimal("1300"))
    assert rotated is not None and rotated.workshop_sku == "MID"
    too_big = service._pick_sheet_rule(rules, Decimal("4000"), Decimal("500"))
    assert too_big is not None and too_big.workshop_sku == "BIG"  # largest fallback
    assert service._pick_sheet_rule([], Decimal("10"), Decimal("10")) is None


def _sheet_rules_fake(rows_spec):
    from decimal import Decimal

    from dekopen_engine.nesting import SheetRule

    return [
        SheetRule(
            workshop_sku=sku, purchasing_sku=sku,
            sheet_width_mm=Decimal(w), sheet_height_mm=Decimal(h),
        )
        for sku, w, h in sorted(rows_spec, key=lambda r: Decimal(r[1]) * Decimal(r[2]))
    ]


def test_release_seals_system_from_snapshot_positions() -> None:
    seen = {}

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return _version_row(_SNAPSHOT)
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "INSERT INTO public.orders" in query:
            seen["payload"] = params[3]
            return [{"id": uuid4()}]
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service._ensure_work_centers", return_value=({}, set())
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        service.release_production(
            org_id=uuid4(), version_id=uuid4(), actor_id=uuid4()
        )
    assert json.loads(seen["payload"])["system_id"] == _SNAPSHOT["positions"][0]["system_id"]


def test_release_seals_glass_polishing_from_snapshot_positions() -> None:
    polishing = [
        {
            "bay_id": "bay_1",
            "leaf_id": None,
            "edges": {"top": True, "right": True, "bottom": False, "left": False},
        }
    ]
    snapshot = {
        "positions": [
            {
                "id": _POSITION_ID,
                "system_id": str(uuid4()),
                "glass_polishing": polishing,
                "process_facts": _SNAPSHOT["positions"][0]["process_facts"],
            }
        ],
        "bom": _SNAPSHOT["bom"],
    }
    seen = {}

    def fake_one(query, params=(), code=None):
        if "project_versions" in query:
            return _version_row(snapshot)
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "INSERT INTO public.orders" in query:
            seen["payload"] = params[3]
            return [{"id": uuid4()}]
        return []

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service._ensure_work_centers", return_value=({}, set())
    ), patch(
        "production.service.production_stock.coverage_for_version", return_value={"shortages": 0}
    ):
        service.release_production(
            org_id=uuid4(), version_id=uuid4(), actor_id=uuid4()
        )
    assert json.loads(seen["payload"])["glass_polishing"] == polishing


def test_optimize_rejects_completed_order() -> None:
    order_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT", "status": "COMPLETED",
                "payload_json": {},
            }
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.transaction.atomic", return_value=_atomic()
    ), patch("production.service.documentary_backend", return_value=_atomic()):
        with pytest.raises(DocumentaryError) as error:
            service.optimize_work_order(
                org_id=uuid4(), order_id=order_id, actor_id=uuid4(), color="BLANCO",
            )
    assert error.value.code == "work_order_completed"


def test_optimize_rejects_replan_after_consumed_step() -> None:
    # A DONE material-consuming step already settled its reservations —
    # replanning would strand the fresh holds forever (no second DONE
    # transition can consume them).
    order_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT", "status": "IN_PRODUCTION",
                "payload_json": {},
            }
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "production_steps" in query:
            return [{"code": "CUT", "status": "DONE"}]
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch(
        "production.service.transaction.atomic", return_value=_atomic()
    ), patch("production.service.documentary_backend", return_value=_atomic()):
        with pytest.raises(DocumentaryError) as error:
            service.optimize_work_order(
                org_id=uuid4(), order_id=order_id, actor_id=uuid4(),
                color="BLANCO",
            )
    assert error.value.code == "work_order_replan_after_consumption"


def test_optimize_rejects_replan_while_consuming_step_in_progress() -> None:
    # An IN_PROGRESS consuming step is physically cutting plan A — replanning
    # mid-cut would silently restock its claims under a different plan.
    order_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT", "status": "IN_PRODUCTION",
                "payload_json": {},
            }
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "production_steps" in query:
            return [{"code": "GLAZE", "status": "IN_PROGRESS"}]
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch(
        "production.service.transaction.atomic", return_value=_atomic()
    ), patch("production.service.documentary_backend", return_value=_atomic()):
        with pytest.raises(DocumentaryError) as error:
            service.optimize_work_order(
                org_id=uuid4(), order_id=order_id, actor_id=uuid4(),
                color="BLANCO",
            )
    assert error.value.code == "work_order_replan_step_in_progress"


def test_optimize_rejects_color_contradicting_sealed_payload() -> None:
    # The sealed color is authoritative — optimizing a FOILED order against
    # WHITE stock variants would cut the wrong finish.
    order_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT", "status": "IN_PRODUCTION",
                "payload_json": {"color": "FOILED"},
            }
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "production_steps" in query:
            return []
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch(
        "production.service.transaction.atomic", return_value=_atomic()
    ), patch("production.service.documentary_backend", return_value=_atomic()):
        with pytest.raises(DocumentaryError) as error:
            service.optimize_work_order(
                org_id=uuid4(), order_id=order_id, actor_id=uuid4(),
                color="WHITE",
            )
    assert error.value.code == "optimize_color_mismatch"


def test_complete_step_rejects_material_shortage() -> None:
    # A consuming step cannot complete while the plan is short material —
    # settling only the reserved part would let the order reach completion
    # with pieces nobody can physically make. (Assigned center: the
    # unassigned-step gate is exercised by its own test.)
    step = _step_row(status="IN_PROGRESS", code="CUT", work_center_id=uuid4())
    payload = json.dumps({
        "optimization": {
            "stock_reservations": [
                {"kind": "BAR", "sku": "COM-X", "reserved": "0",
                 "short": "2", "consumed_at": None},
            ],
            "bars": {"unplaced": [{"piece_id": "p1"}]},
            "unnested": [],
        }
    })

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "SELECT payload_json FROM public.orders" in query:
            return {"payload_json": payload}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.remnants_service.consume_order_remnants",
        return_value=0,
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="COMPLETE",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_order_material_shortage"


def test_complete_cut_rejects_released_remnant() -> None:
    # An operator unreserved a drop the plan still claims — completing CUT
    # would settle stock another order may already have taken.
    step = _step_row(status="IN_PROGRESS", code="CUT", work_center_id=uuid4())
    payload = json.dumps({
        "optimization": {
            "remnants": {
                "consumed": [{"id": str(uuid4()), "kind": "BAR"}],
            },
            "stock_reservations": [],
        }
    })

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "SELECT payload_json FROM public.orders" in query:
            return {"payload_json": payload}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), patch(
        "production.service.remnants_service.consume_order_remnants",
        return_value=0,
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="COMPLETE",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_order_remnant_released"


def test_complete_step_rejects_missing_plan() -> None:
    # A consuming step needs the optimization record at all: an order that
    # was never optimized carries no material accounting, so completion
    # would silently skip every reservation and shortage check.
    step = _step_row(status="IN_PROGRESS", code="ASSEMBLE")
    payload = json.dumps({"position_id": "p-1"})

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "SELECT payload_json FROM public.orders" in query:
            return {"payload_json": payload}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="COMPLETE",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_order_plan_missing"


def test_complete_step_rejects_invalidated_plan() -> None:
    # A plan that lost its claimed stock (e.g. a remnant released back to the
    # pool) can no longer prove pieces fit real material — completing would
    # settle reservations for stock that was never re-reserved. The order
    # must re-optimize first.
    step = _step_row(status="IN_PROGRESS", code="ASSEMBLE")
    payload = json.dumps({
        "position_id": "p-1",
        "optimization": {"invalidated": True, "stock_reservations": []},
    })

    def fake_one(query, params=(), code=None):
        if "SELECT order_id FROM public.production_steps" in query:
            return {"order_id": step["order_id"]}
        if "SELECT payload_json FROM public.orders" in query:
            return {"payload_json": payload}
        if "FROM public.orders" in query:
            return {"id": step["order_id"], "status": "IN_PROGRESS"}
        if "FOR UPDATE OF s" in query:
            return step
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=lambda *a, **k: []
    ), patch(
        "production.service.transaction.atomic", side_effect=_atomic
    ), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError) as error:
            service.transition_step(
                org_id=uuid4(), step_id=step["id"], action="COMPLETE",
                actor_id=uuid4(), note=None,
            )
    assert error.value.code == "work_order_plan_stale"


def test_optimize_sheet_piece_ids_unique_per_unit() -> None:
    # quantity>1 must not label two physical panes with the same piece_id —
    # a label resolves to exactly one unit in the trace.
    from decimal import Decimal

    from dekopen_engine.cutting import (
        CutOptimizationResult, CuttingProfile,
    )
    from dekopen_engine.nesting import (
        NestPlacement, SheetLayout, SheetNestingResult,
    )

    order_id = uuid4()
    payload = {
        "position_id": str(uuid4()),
        "system_id": str(uuid4()),
        "quantity": 2,
        "materials": {
            "profile_cuts": [], "reinforcements": [],
            "glasses": [
                {
                    "bay_id": "B1", "leaf_id": "L1",
                    "width_mm": "1100.00", "height_mm": "900.00",
                    "area_m2": "0.99", "weight_kg": "4.95",
                    "thickness_net_mm": "4.00",
                    "glass_spec": "4", "article_sku": "V4",
                }
            ],
            "panels": [], "hardware_items": [],
        },
    }

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT-P-REV-A-01",
                "status": "RELEASED", "payload_json": payload,
            }
        if "snapshot_json" in query:
            return {"snapshot_json": {"positions": [], "manufacturing": []}}
        raise AssertionError(query)

    def fake_rows(query, params=()):
        return []

    profile = CuttingProfile(
        id="CP1", code="SAW01", kerf_mm=Decimal("5"),
        head_trim_mm=Decimal("10"), tail_trim_mm=Decimal("10"),
    )
    cut_result = CutOptimizationResult(workshop_cut_plan=[], purchase_list=[])
    authorities = SimpleNamespace(stocks=[], reinforcement_skus={}, inertias={})
    rule = _sheet_rules_fake([("V4SHEET", "3210", "2250")])[0]

    def fake_nest(pieces, _rule, remnants=()):
        return SheetNestingResult(
            layouts=[SheetLayout(
                sheet_index=1, purchasing_sku=rule.purchasing_sku,
                sheet_width_mm=rule.sheet_width_mm,
                sheet_height_mm=rule.sheet_height_mm,
                placements=[
                    NestPlacement(
                        **piece.model_dump(), sequence=i + 1,
                        x_mm=Decimal("0"), y_mm=Decimal(i * 910),
                    )
                    for i, piece in enumerate(pieces)
                ],
                productive_area_mm2=Decimal("1980000"),
                waste_area_mm2=Decimal("5242500"),
                yield_pct=Decimal("27.41"),
            )],
            purchase_list=[], unplaced=[],
        )

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch("production.service.transaction.atomic", return_value=_atomic()), patch(
        "production.service.documentary_backend", return_value=_atomic()
    ), patch(
        "production.service.CuttingRepository"
    ) as repo, patch(
        "production.service.optimize_cut", return_value=cut_result
    ), patch(
        "production.service._sheet_rules",
        return_value={
            "by_sku": {},
            "by_thickness": {},
            # The piece's article_sku is the substrate key — a sheet that
            # declares glass_sku V4 hosts it; same-thickness sheets of other
            # substrates never do.
            "by_glass": {"V4": [rule]},
        },
    ), patch("production.service.nest_rects", side_effect=fake_nest), patch(
        "production.service.remnants_service"
    ) as rem, patch(
        "production.service.production_stock"
    ) as stock:
        rem.bar_remnants_for_authorities.return_value = []
        rem.sheet_remnants_for_sku.return_value = []
        rem.release_reservations.return_value = 0
        stock.release_for_order.return_value = 0
        stock.bar_stock_needs.return_value = []
        stock.unit_stock_needs.return_value = ([], [])
        stock.reserve_for_order.return_value = []
        repo.return_value.for_result.return_value = authorities
        repo.return_value.cutting_profile.return_value = profile
        output = service.optimize_work_order(
            org_id=uuid4(), order_id=order_id, actor_id=uuid4(), color="BLANCO",
        )
    placements = output["optimization"]["sheets"][0]["placements"]
    piece_ids = {placement["piece_id"] for placement in placements}
    assert len(piece_ids) == 2
    assert piece_ids == {"V-01-01", "V-01-02"}


def test_optimize_requires_color() -> None:
    # No sealed color on the payload and none supplied — nothing authoritative
    # to optimize against.
    order_id = uuid4()

    def fake_one(query, params=(), code=None):
        if "FOR UPDATE" in query:
            return {
                "id": order_id, "order_code": "OT", "status": "RELEASED",
                "payload_json": {},
            }
        raise AssertionError(query)

    def fake_rows(query, params=()):
        if "production_steps" in query:
            return []
        raise AssertionError(query)

    with patch("production.service.one", side_effect=fake_one), patch(
        "production.service.rows", side_effect=fake_rows
    ), patch(
        "production.service.transaction.atomic", return_value=_atomic()
    ), patch("production.service.documentary_backend", return_value=_atomic()):
        with pytest.raises(DocumentaryError) as error:
            service.optimize_work_order(
                org_id=uuid4(), order_id=order_id, actor_id=uuid4(), color="  ",
            )
    assert error.value.code == "optimize_color_required"


def test_optimize_post_forwards_scope(monkeypatch) -> None:
    client, token, org_id = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")
    seen = {}

    def fake_optimize(**kwargs):
        seen.update(kwargs)
        return {"order_id": str(kwargs["order_id"]), "order_code": "OT", "optimization": {}}

    monkeypatch.setattr(service, "optimize_work_order", fake_optimize)
    order_id = uuid4()
    response = client.post(
        f"/api/v1/production/orders/{order_id}/optimize/",
        {"color": "BLANCO"}, format="json",
    )
    assert response.status_code == 200
    assert seen["actor_id"] == token.user_id
    assert seen["color"] == "BLANCO"


def test_optimize_post_rejects_blank_color(monkeypatch) -> None:
    # Blank color passes the serializer (sealed payload color can fill it) and
    # the service decides — an unsealed order with nothing supplied 422s.
    client, _, _ = _client_with_scope(monkeypatch, "WORKSHOP_MANAGER")

    def fake_optimize(**kwargs):
        raise DocumentaryError("optimize_color_required")

    monkeypatch.setattr(service, "optimize_work_order", fake_optimize)
    response = client.post(
        f"/api/v1/production/orders/{uuid4()}/optimize/",
        {"color": " "}, format="json",
    )
    assert response.status_code == 422






def test_qc_fail_blocks_step_and_holds_order(monkeypatch) -> None:
    org_id, step_id, order_id = uuid4(), uuid4(), uuid4()

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "from public.production_steps" in lowered and "for update" in lowered:
            return {
                "id": str(step_id),
                "org_id": str(org_id),
                "order_id": str(order_id),
                "sequence": 5,
                "code": "QC",
                "label": "Control de calidad",
                "status": "IN_PROGRESS",
                "work_center_id": str(uuid4()),
                "work_center_code": "QC",
                "started_at": "2026-09-23T00:00:00+00:00",
                "finished_at": None,
                "actor_id": None,
                "note": None,
            }
        if "from public.orders" in lowered and "for update" in lowered:
            return {
                "id": str(order_id),
                "status": "RELEASED",
                "order_type": "WORKSHOP_OT",
                "payload_json": {},
            }
        if "order_id from public.production_steps" in lowered:
            return {"order_id": str(order_id)}
        if "from public.production_steps" in lowered:
            return {
                "id": str(step_id),
                "sequence": 5,
                "code": "QC",
                "label": "Control de calidad",
                "status": "BLOCKED",
                "work_center_id": None,
                "work_center_code": "QC",
                "started_at": "2026-09-23T00:00:00+00:00",
                "finished_at": None,
                "actor_id": None,
                "note": "rotura en esmerilado",
            }
        raise AssertionError(f"unexpected one(): {lowered}")

    writes: list[tuple[str, object]] = []

    def fake_rows(sql_text: str, params: object = ()) -> list[dict]:
        lowered = " ".join(sql_text.lower().split())
        writes.append((lowered, params))
        return [{"id": str(step_id)}] if "returning" in lowered else []

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr("production.service._refresh_order_status", lambda **kw: "HOLD")
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        result = service.transition_step(
            org_id=org_id,
            step_id=step_id,
            action="COMPLETE",
            actor_id=uuid4(),
            note="rotura en esmerilado",
            qc_result="FAIL",
        )
    step_update = next(
        p2 for s2, p2 in writes if "update public.production_steps" in s2
    )
    assert step_update["status"] == "BLOCKED"
    event_insert = next(
        p2 for s2, p2 in writes if "insert into public.production_step_events" in s2
    )
    assert event_insert[3] == "QC_FAILED"
    assert result["order_status"] == "HOLD"
    assert result["step"]["status"] == "BLOCKED"


def test_qc_result_rejected_on_non_qc_step(monkeypatch) -> None:
    org_id, step_id, order_id = uuid4(), uuid4(), uuid4()

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "order_id from public.production_steps" in lowered:
            return {"order_id": str(order_id)}
        if "from public.orders" in lowered:
            return {"id": str(order_id), "status": "RELEASED"}
        if "from public.production_steps" in lowered:
            return {
                "id": str(step_id),
                "org_id": str(org_id),
                "order_id": str(order_id),
                "sequence": 2,
                "code": "ASSEMBLE",
                "label": "Ensamble",
                "status": "IN_PROGRESS",
                "work_center_id": None,
                "work_center_code": "ASSEMBLY",
                "started_at": None,
                "finished_at": None,
                "actor_id": None,
                "note": None,
            }
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="step_transition_invalid"):
        service.transition_step(
            org_id=org_id,
            step_id=step_id,
            action="COMPLETE",
            actor_id=uuid4(),
            note=None,
            qc_result="FAIL",
        )


def test_create_remake_clones_order_and_steps(monkeypatch) -> None:
    org_id, order_id, version_id, remake_id = uuid4(), uuid4(), uuid4(), uuid4()
    writes: list[tuple[str, list]] = []
    detail_calls: list[str] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-P-AAA-01",
                "status": "HOLD",
                "project_id": str(uuid4()),
                "project_version_id": str(version_id),
                "payload_json": {
                    "position_id": str(_POSITION_ID),
                    "quantity": 1,
                    "materials": {"profile_cuts": [{"a": 1}]},
                    "optimization": {"stale": True},
                },
            }
        if "count(*)" in lowered:
            return {"n": 1}
        if "insert into public.orders" in lowered:
            writes.append((lowered, list(params)))
            return {"id": str(remake_id), "order_code": "OT-P-AAA-01-RM-02"}
        raise AssertionError(f"unexpected one(): {lowered}")

    def fake_rows(sql_text: str, params: object = ()) -> list[dict]:
        lowered = " ".join(sql_text.lower().split())
        writes.append((lowered, list(params)))
        return [{"id": str(remake_id)}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.get_work_order",
        lambda **kw: detail_calls.append(str(kw["order_id"])) or {"id": str(kw["order_id"])},
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        result = service.create_remake(
            org_id=org_id, order_id=order_id, actor_id=uuid4(), note="rehacer por QC"
        )
    order_insert = next(p2 for s2, p2 in writes if "insert into public.orders" in s2)
    payload = json.loads(order_insert[3])
    assert "optimization" not in payload
    assert payload["remake_of"] == str(order_id)
    assert order_insert[2] == "OT-P-AAA-01-RM-02"
    steps_copy = next(
        s2 for s2, _ in writes if "insert into public.production_steps" in s2 and "select" in s2
    )
    assert "from public.production_steps" in steps_copy
    assert any("wo_remade" in s2 for s2, _ in writes)
    assert detail_calls and result["id"] == str(remake_id)


def test_create_remake_requires_hold(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": str(order_id),
            "order_code": "OT-P-AAA-01",
            "status": "RELEASED",
            "payload_json": {},
        },
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="remake_requires_hold"):
        service.create_remake(org_id=org_id, order_id=order_id, actor_id=uuid4())


def test_export_cnc_files_writes_deterministic_csv(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    optimization = {
        "bars": {
            "workshop_cut_plan": [
                {
                    "bar_index": 1,
                    "commercial_sku": "MARCO-60",
                    "stock_length_mm": "6500",
                    "cuts": [
                        {"piece_id": "M-02", "length_mm": "1200", "sequence": 1,
                         "angle_left": "45.0", "angle_right": "45.0",
                         "unit_index": 1, "bay_id": "b1", "leaf_id": None,
                         "source_position_id": str(_POSITION_ID)},
                        {"piece_id": "M-01", "length_mm": "1500", "sequence": 2,
                         "angle_left": "90.0", "angle_right": "45.0",
                         "unit_index": 1, "bay_id": "b1", "leaf_id": None,
                         "source_position_id": str(_POSITION_ID)},
                    ],
                }
            ]
        },
        "sheets": [
            {
                "sheet_index": 2,
                "purchasing_sku": "GLASS-4",
                "sheet_width_mm": "3210",
                "sheet_height_mm": "2250",
                "placements": [
                    {"piece_id": "V-01", "x_mm": "100", "y_mm": "50",
                     "width_mm": "800", "height_mm": "600", "rotated": False,
                     "unit_index": 1, "bay_id": "b1", "leaf_id": "l1"}
                ],
            },
            {
                "sheet_index": 1,
                "purchasing_sku": "GLASS-4",
                "sheet_width_mm": "3210",
                "sheet_height_mm": "2250",
                "placements": [],
            },
        ],
    }
    writes: list[tuple[str, list]] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-P-AAA-01",
                "status": "IN_PROGRESS",
                "payload_json": {"optimization": optimization},
            }
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr(
        "production.service.rows",
        lambda sql_text, params=(): writes.append(
            (" ".join(sql_text.lower().split()), list(params))
        ) or [{"id": str(order_id)}],
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.export_cnc_files(org_id=org_id, order_id=order_id, actor_id=uuid4())
    update = next(p2 for s2, p2 in writes if "update public.orders" in s2)
    stored = json.loads(update[0])["cnc_export"]
    assert sorted(out["files"]) == ["bars.csv", "sheets.csv"]
    bars_csv = stored["files"]["bars.csv"]
    lines = bars_csv.strip().split("\n")
    assert lines[0].startswith("bar_index,")
    assert "M-02" in lines[1] and "M-01" in lines[2]  # stored cut sequence
    assert lines[1].split(",")[3] == "1"  # sequence_in_bar column
    assert "45.0" in lines[1] and "90.0" in lines[2]  # saw angles exported
    assert stored["schema"] == "work_order_cnc_export_v2"
    assert stored["optimization_fingerprint"]
    sheets_csv = stored["files"]["sheets.csv"]
    assert "GLASS-4" in sheets_csv and "V-01" in sheets_csv
    assert any("wo_cnc_exported" in s2 for s2, _ in writes)


def test_export_cnc_requires_optimization(monkeypatch) -> None:
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": "o",
            "order_code": "OT",
            "status": "RELEASED",
            "payload_json": {},
        },
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="cnc_requires_optimization"):
        service.export_cnc_files(org_id=uuid4(), order_id=uuid4(), actor_id=uuid4())


def test_export_dxf_files_writes_deterministic_geometry(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    optimization = {
        "bars": {
            "workshop_cut_plan": [
                {
                    "bar_index": 1,
                    "commercial_sku": "MARCO-60",
                    "stock_length_mm": "6500",
                    "head_trim_mm": "15",
                    "tail_trim_mm": "20",
                    "kerf_mm": "4",
                    "cuts": [
                        {"piece_id": "M-02", "length_mm": "1200", "sequence": 1,
                         "unit_index": 1,
                         "angle_left": "45.0", "angle_right": "45.0"},
                        {"piece_id": "M-01", "length_mm": "1500", "sequence": 2,
                         "unit_index": 2,
                         "angle_left": "90.0", "angle_right": "45.0"},
                    ],
                }
            ]
        },
        "sheets": [
            {
                "sheet_index": 1,
                "purchasing_sku": "GLASS-4",
                "sheet_width_mm": "3210",
                "sheet_height_mm": "2250",
                "placements": [
                    {"piece_id": "V-01", "x_mm": "100", "y_mm": "50",
                     "width_mm": "800", "height_mm": "600", "unit_index": 2,
                     "rotated": False}
                ],
            },
        ],
    }
    writes: list[tuple[str, list]] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-P-AAA-01",
                "status": "IN_PROGRESS",
                "payload_json": {"optimization": optimization},
                "project_version_id": str(uuid4()),
            }
        if "project_versions" in lowered:
            return {"snapshot_json": {}}
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr(
        "production.service.rows",
        lambda sql_text, params=(): writes.append(
            (" ".join(sql_text.lower().split()), list(params))
        ) or [{"id": str(order_id)}],
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.export_dxf_files(org_id=org_id, order_id=order_id, actor_id=uuid4())
    update = next(p2 for s2, p2 in writes if "update public.orders" in s2)
    stored = json.loads(update[0])["dxf_export"]
    assert sorted(out["files"]) == ["bars.dxf", "sheet_1.dxf"]
    sheet = stored["files"]["sheet_1.dxf"]
    assert sheet.startswith("0\nSECTION\n2\nHEADER") and sheet.endswith("0\nEOF\n")
    # ASCII-only labels (AC1015-era DXF) and AcDb subclass markers.
    assert "AC1015" in sheet and "V-01-U2 800x600" in sheet
    assert "100\nAcDbPolyline" in sheet and "100\nAcDbText" in sheet
    bars = stored["files"]["bars.dxf"]
    assert "M-02-U1 1200 45.0/45.0" in bars and "MARCO-60" in bars
    assert "100\nAcDbLine" in bars
    # Saw consumption matches optimize_cut: head trim once (mark at 15),
    # then each piece length + one kerf → piece ends at 1215 and 2719.
    for mark_x in ("10\n15\n20", "10\n1215\n20", "10\n2719\n20"):
        assert f"AcDbLine\n{mark_x}" in bars
    assert "10\n1200\n20" not in bars
    assert stored["schema"] == "work_order_dxf_export_v1"
    assert stored["optimization_fingerprint"]
    assert any("wo_dxf_exported" in s2 for s2, _ in writes)


def _ops_snapshot() -> dict:
    return {
        "manufacturing": [
            {
                "position_id": "pos-1",
                "position_index": 1,
                "repetition_index": 1,
                "nominal_width_mm": "1000",
                "nominal_height_mm": "1200",
                "placement_policy_id": "pp",
                "placement_policy_version": 1,
                "handle_policy_id": "hp",
                "handle_policy_version": 1,
                "reinforcement_policy_id": "rp",
                "reinforcement_policy_version": 1,
                "members": [],
                "reinforcements": [],
                "leaves": [],
                "infills": [],
                "handles": [],
                "relationships": [],
            }
        ]
    }


def _ops_optimization() -> dict:
    return {
        "bars": {
            "plan_seed": "seed-1",
            "workshop_cut_plan": [
                {
                    "bar_index": 1,
                    "commercial_sku": "MARCO-60",
                    "material": "PVC",
                    "color": "blanco",
                    "stock_length_mm": "6000",
                    "head_trim_mm": "10",
                    "tail_trim_mm": "10",
                    "kerf_mm": "5",
                    "cuts": [
                        {
                            "piece_id": "M-01",
                            "source_kind": "PROFILE",
                            "workshop_sku": "MARCO-60",
                            "material": "PVC",
                            "color": "blanco",
                            "length_mm": "2000",
                            "role": "FRAME",
                            "unit_index": 1,
                            "sequence": 1,
                            "angle_left": "90.0",
                            "angle_right": "45.0",
                        },
                        {
                            "piece_id": "M-02",
                            "source_kind": "PROFILE",
                            "workshop_sku": "MARCO-60",
                            "material": "PVC",
                            "color": "blanco",
                            "length_mm": "1500",
                            "role": "FRAME",
                            "unit_index": 1,
                            "sequence": 2,
                            "angle_left": "45.0",
                            "angle_right": "90.0",
                        },
                    ],
                    "kerf_total_mm": "15",
                    "productive_length_mm": "3500",
                    "process_consumed_mm": "3525",
                    "remainder_mm": "2455",
                    "waste_mm": "25",
                    "yield_pct": "58.33",
                    "waste_pct": "0.42",
                }
            ],
        }
    }


def test_export_operations_seals_machine_neutral_document(monkeypatch) -> None:
    org_id, order_id, version_id = uuid4(), uuid4(), uuid4()
    optimization = _ops_optimization()
    calls = iter(
        [
            {
                "id": str(order_id),
                "order_code": "OT-OPS-01",
                "status": "IN_PROGRESS",
                "payload_json": {"optimization": optimization, "position_id": "pos-1"},
                "project_version_id": str(version_id),
            },
            {"snapshot_json": _ops_snapshot()},
        ]
    )
    monkeypatch.setattr(
        "production.service.one", lambda *_a, **_k: next(calls)
    )
    writes: list[tuple[str, list]] = []
    monkeypatch.setattr(
        "production.service.rows",
        lambda sql_text, params=(): writes.append(
            (" ".join(sql_text.lower().split()), list(params))
        ) or [{"id": str(order_id)}],
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.export_operations(
            org_id=org_id, order_id=order_id, actor_id=uuid4()
        )
    assert sorted(out["files"]) == ["operations.csv", "operations.json"]
    update = next(p for s, p in writes if "update public.orders" in s)
    stored = json.loads(update[0])["operations_export"]
    assert stored["schema"] == "work_order_ops_export_v1"
    assert stored["machine"]["machine_id"] == "machine-neutral-v1"
    # head trim + two interior cuts + tail trim = 4 saw operations
    assert stored["operation_count"] == 4
    assert stored["counts_by_kind"] == {"SAW_CUT": 4}
    assert stored["source_fingerprint"]
    assert any("wo_ops_exported" in s for s, _ in writes)


def test_export_operations_requires_optimization(monkeypatch) -> None:
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": "o",
            "order_code": "OT",
            "status": "RELEASED",
            "payload_json": {},
            "project_version_id": "v",
        },
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="operations_requires_optimization"):
        service.export_operations(org_id=uuid4(), order_id=uuid4(), actor_id=uuid4())


def test_export_dxf_requires_optimization(monkeypatch) -> None:
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": "o",
            "order_code": "OT",
            "status": "RELEASED",
            "payload_json": {},
        },
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="dxf_requires_optimization"):
        service.export_dxf_files(org_id=uuid4(), order_id=uuid4(), actor_id=uuid4())


def test_packing_manifest_builds_units_and_records(monkeypatch) -> None:
    org_id, order_id, actor_id = uuid4(), uuid4(), uuid4()
    events: list[list] = []
    payload = {
        "position_id": str(_POSITION_ID),
        "quantity": 2,
        "materials": {
            "profile_cuts": [{"a": 1, "qty": 3}, {"b": 2, "qty": 2}],
            "glasses": [{"g": 1}],
        },
    }

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-1",
                "status": "IN_PROGRESS",
                "payload_json": payload,
            }
        raise AssertionError(f"unexpected one(): {lowered}")

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "insert into public.production_step_events" in lowered:
            events.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        output = service.generate_packing_manifest(
            org_id=org_id, order_id=order_id, actor_id=actor_id
        )
    units = output["packing"]["units"]
    assert [u["unit_index"] for u in units] == [1, 2]
    assert units[0]["label_code"] == "OT-1-U01"
    # grouped rows count their qty, not one per row
    assert units[0]["profiles"] == 5 and units[0]["glasses"] == 1
    assert units[0]["panels"] == 0 and units[0]["hardware"] == 0
    assert "'wo_packed'" in events[0][0]


def test_dispatch_requires_completed_and_is_idempotent(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    updates: list[list] = []
    statuses = iter(["IN_PROGRESS"])

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        return {
            "id": str(order_id),
            "order_code": "OT-1",
            "status": next(statuses, "IN_PROGRESS"),
            "payload_json": {},
        }

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [{"id": "ok"}])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ), pytest.raises(DocumentaryError, match="dispatch_requires_completed"):
        service.dispatch_work_order(org_id=org_id, order_id=order_id, actor_id=uuid4())

    # Completed path updates status and emits the event; replay returns detail.
    captured_status: dict[str, dict] = {"row": {"status": "COMPLETED"}}
    project_id = uuid4()
    note_calls: list[dict] = []

    def fake_one_completed(sql_text: str, params: list, code: str = "not_found") -> dict:
        return {
            "id": str(order_id),
            "order_code": "OT-1",
            "status": captured_status["row"]["status"],
            "payload_json": {"packing": {"units": [{"code": "U-1"}]}},
            "project_id": str(project_id),
        }

    def fake_rows_dispatch(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "update public.orders set status" in lowered:
            captured_status["row"]["status"] = "DISPATCHED"
        if "insert into public.production_step_events" in lowered:
            updates.append((lowered, list(params)))
        return [{"id": "ok"}]

    def fake_issue(**kwargs):
        note_calls.append(kwargs)
        return {"note_code": "GD-0001"}

    monkeypatch.setattr("production.service.one", fake_one_completed)
    monkeypatch.setattr("production.service.rows", fake_rows_dispatch)
    monkeypatch.setattr("production.service.issue_dispatch_note", fake_issue)
    monkeypatch.setattr(
        "production.service.project_row", lambda *a, **k: {"code": "P-1"}
    )
    monkeypatch.setattr(
        "production.service.get_work_order",
        lambda **kw: {"order": {"status": captured_status["row"]["status"]}},
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        service.dispatch_work_order(
            org_id=org_id, order_id=order_id, actor_id=uuid4(), note="Camión 12"
        )
        assert captured_status["row"]["status"] == "DISPATCHED"
        out2 = service.dispatch_work_order(org_id=org_id, order_id=order_id, actor_id=uuid4())
    assert "'wo_dispatched'" in updates[0][0]
    assert len(note_calls) == 1
    assert str(note_calls[0]["order"]["project_id"]) == str(project_id)
    event_payload = json.loads(updates[0][1][3])
    assert event_payload["dispatch_note"] == "GD-0001"
    assert out2["order"]["status"] == "DISPATCHED"


def test_dispatch_note_void_reverts_order_and_records_event(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    captured_status: dict[str, dict] = {"row": {"status": "DISPATCHED"}}
    calls: list[tuple[str, list]] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-1",
                "status": captured_status["row"]["status"],
                "payload_json": {},
                "project_id": str(uuid4()),
            }
        return {
            "id": str(uuid4()),
            "note_code": "GD-0001",
        }

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "from public.deliveries" in lowered or "from public.project_dtes" in lowered:
            return []
        if "update public.orders set status" in lowered:
            captured_status["row"]["status"] = "COMPLETED"
        if "insert into public.production_step_events" in lowered:
            calls.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.get_work_order",
        lambda **kw: {"order": {"status": captured_status["row"]["status"]}},
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="dispatch_note_void_reason_required"):
            service.void_dispatch_note(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), reason=" "
            )
        out = service.void_dispatch_note(
            org_id=org_id,
            order_id=order_id,
            actor_id=uuid4(),
            reason="Dirección equivocada",
        )
    assert captured_status["row"]["status"] == "COMPLETED"
    assert out["order"]["status"] == "COMPLETED"
    assert "'wo_dispatch_voided'" in calls[0][0]
    payload = json.loads(calls[0][1][3])
    assert payload["note_code"] == "GD-0001"
    assert payload["reason"] == "Dirección equivocada"


def test_dispatch_note_void_refuses_stamped_or_delivered(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    guard: dict[str, bool] = {"delivery": True, "dte": False}

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-1",
                "status": "DISPATCHED",
                "payload_json": {},
            }
        return {"id": str(uuid4()), "note_code": "GD-0001"}

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "from public.deliveries" in lowered:
            return [{"id": "d1"}] if guard["delivery"] else []
        if "from public.project_dtes" in lowered:
            return [{"id": "t1"}] if guard["dte"] else []
        return [{"id": "ok"}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(
            DocumentaryError, match="dispatch_note_void_delivery_exists"
        ):
            service.void_dispatch_note(
                org_id=org_id,
                order_id=order_id,
                actor_id=uuid4(),
                reason="Anular",
            )
        guard["delivery"] = False
        guard["dte"] = True
        with pytest.raises(DocumentaryError, match="dispatch_note_void_stamped"):
            service.void_dispatch_note(
                org_id=org_id,
                order_id=order_id,
                actor_id=uuid4(),
                reason="Anular",
            )


def test_remake_code_embeds_id_fragment_for_long_sources(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    source_code = "OT-" + "A" * 47  # exactly 50 chars
    captured: list[list] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": source_code,
                "status": "HOLD",
                "project_id": str(uuid4()),
                "project_version_id": str(uuid4()),
                "payload_json": {"position_id": str(_POSITION_ID)},
            }
        if "count(*)" in lowered:
            return {"n": 0}
        if "insert into public.orders" in lowered:
            captured.append(list(params))
            return {"id": str(uuid4()), "order_code": params[2]}
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [])
    monkeypatch.setattr("production.service.get_work_order", lambda **kw: {"id": "x"})
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        service.create_remake(org_id=org_id, order_id=order_id, actor_id=uuid4())
    code = captured[0][2]
    assert len(code) <= 50
    assert code.endswith("-RM-01")
    marker = str(order_id).replace("-", "").upper()
    assert marker in code
    # distinct sources keep distinct codes even with identical prefixes
    other_id = uuid4()
    other_marker = str(other_id).replace("-", "").upper()
    assert code != f"{source_code[:50-len('-RM-01')-33]}-{other_marker}-RM-01"


def test_reinforcement_angles_flow_into_bars_csv() -> None:
    # The sealed manufacturing facts are the only authority for steel end
    # angles: PVC mitred 45/45 -> square-cut steel 90/90.
    snapshot = {
        "manufacturing": [
            {
                "position_id": "pos-1",
                "members": [
                    {
                        "member_id": "m1",
                        "identity": {"role": "FRAME"},
                        "bay_id": "b1",
                        "leaf_id": None,
                        "workshop_sku": "MARCO-60",
                    }
                ],
                "reinforcements": [
                    {
                        "parent_member_id": "m1",
                        "workshop_sku": "ACERO-35",
                        "cut_length_mm": "880.00",
                        "angle_left": "90.0",
                        "angle_right": "90.0",
                    }
                ],
            }
        ]
    }
    angle_map = service._reinforcement_angle_map(snapshot, "pos-1")
    assert angle_map == {("ACERO-35", "880.00", "FRAME", "b1", None): ("90.0", "90.0")}

    # Conflicting facts on the same key mark it ambiguous (None).
    snapshot["manufacturing"][0]["reinforcements"].append(
        {
            "parent_member_id": "m1",
            "workshop_sku": "ACERO-35",
            "cut_length_mm": "880.00",
            "angle_left": "45.0",
            "angle_right": "45.0",
        }
    )
    assert service._reinforcement_angle_map(snapshot, "pos-1")[
        ("ACERO-35", "880.00", "FRAME", "b1", None)
    ] is None


def test_bars_csv_rejects_reinforcement_without_angles() -> None:
    optimization = {
        "bars": {
            "workshop_cut_plan": [
                {
                    "bar_index": 1,
                    "commercial_sku": "ACERO-35",
                    "stock_length_mm": "6500",
                    "cuts": [
                        {
                            "piece_id": "R-01",
                            "source_kind": "REINFORCEMENT",
                            "length_mm": "880",
                            "sequence": 1,
                        }
                    ],
                }
            ]
        }
    }
    with pytest.raises(DocumentaryError, match="cnc_incomplete_cut_angles"):
        service._cnc_bars_csv(optimization)



def test_packing_labels_keep_suffix_on_long_order_code(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    long_code = "OT-" + "B" * 47
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": str(order_id),
            "order_code": long_code,
            "status": "IN_PROGRESS",
            "payload_json": {"quantity": 2, "materials": {}},
        },
    )
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [{"id": "ok"}])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        output = service.generate_packing_manifest(
            org_id=org_id, order_id=order_id, actor_id=uuid4()
        )
    labels = [u["label_code"] for u in output["packing"]["units"]]
    assert labels[0].endswith("-U01") and labels[1].endswith("-U02")
    assert len(set(labels)) == 2 and all(len(label) <= 50 for label in labels)


def test_remake_drops_source_packing(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    captured: list[list] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "for update" in lowered:
            return {
                "id": str(order_id),
                "order_code": "OT-1",
                "status": "HOLD",
                "project_id": str(uuid4()),
                "project_version_id": str(uuid4()),
                "payload_json": {
                    "position_id": str(_POSITION_ID),
                    "packing": {"units": [{"label_code": "OT-1-U01"}]},
                },
            }
        if "count(*)" in lowered:
            return {"n": 0}
        if "insert into public.orders" in lowered:
            captured.append(list(params))
            return {"id": str(uuid4()), "order_code": params[2]}
        raise AssertionError(f"unexpected one(): {lowered}")

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [{"id": "ok"}])
    monkeypatch.setattr("production.service.get_work_order", lambda **kw: {"id": "x"})
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        service.create_remake(org_id=org_id, order_id=order_id, actor_id=uuid4())
    assert "packing" not in json.loads(captured[0][3])



def test_packing_labels_render_qr_per_unit(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    order = {
        "id": order_id,
        "order_code": "OT-LBL-1",
        "status": "COMPLETED",
        "payload_json": json.dumps(
            {
                "packing": {
                    "units": [
                        {
                            "unit_index": 1,
                            "label_code": "OT-LBL-1-U01",
                            "profiles": 6,
                            "reinforcements": 4,
                            "glasses": 2,
                            "panels": 0,
                            "hardware": 8,
                        }
                    ]
                }
            }
        ),
    }
    monkeypatch.setattr(service, "one", lambda *a, **k: order)
    monkeypatch.setattr(service, "documentary_backend", _atomic)
    monkeypatch.setattr(service.transaction, "atomic", _atomic)
    out = service.packing_labels(org_id=org_id, order_id=order_id)

    assert len(out["labels"]) == 1
    label = out["labels"][0]
    assert label["pieces"] == 20
    assert label["qr_payload"] == "DEKOPEN|OT-LBL-1|OT-LBL-1-U01|20"
    assert label["qr_svg"].startswith("<svg") and "path" in label["qr_svg"]


def test_packing_labels_require_manifest(monkeypatch) -> None:
    order = {
        "id": uuid4(),
        "order_code": "OT-LBL-2",
        "status": "IN_PROGRESS",
        "payload_json": json.dumps({}),
    }
    monkeypatch.setattr(service, "one", lambda *a, **k: order)
    monkeypatch.setattr(service, "documentary_backend", _atomic)
    monkeypatch.setattr(service.transaction, "atomic", _atomic)
    with pytest.raises(DocumentaryError, match="packing_required"):
        service.packing_labels(org_id=uuid4(), order_id=uuid4())


def test_installation_requires_dispatched_and_is_idempotent(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    statuses = iter(["IN_PROGRESS", "DISPATCHED", "INSTALLED"])
    captured: dict[str, str] = {}
    events: list[tuple[str, list]] = []

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        return {
            "id": str(order_id),
            "order_code": "OT-1",
            "status": captured.get("status") or next(statuses),
            "payload_json": {},
        }

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "from public.deliveries" in lowered:
            return [{"status": "DELIVERED"}]
        if "from public.delivery_confirmations" in lowered:
            return [{"id": "ce-1"}]
        if "update public.orders set status" in lowered:
            captured["status"] = "INSTALLED"
        if "insert into public.production_step_events" in lowered:
            events.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.get_work_order",
        lambda **kw: {"order": {"status": captured.get("status", "?")}},
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="installation_requires_dispatched"):
            service.confirm_installation(
                org_id=org_id, order_id=order_id, actor_id=uuid4()
            )
        service.confirm_installation(
            org_id=org_id, order_id=order_id, actor_id=uuid4(), note="Obra Norte"
        )
        # replay on INSTALLED returns the order without writing again
        out = service.confirm_installation(
            org_id=org_id, order_id=order_id, actor_id=uuid4()
        )
    assert "'wo_installed'" in events[0][0]
    assert len(events) == 1
    assert out["order"]["status"] == "INSTALLED"



def test_dispatched_order_rejects_mutation_actions(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    order = {
        "id": str(order_id),
        "order_code": "OT-1",
        "status": "DISPATCHED",
        "payload_json": {"optimization": {"bars": {"workshop_cut_plan": []}}},
    }
    monkeypatch.setattr("production.service.one", lambda *_a, **_k: order)
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="work_order_dispatched"):
            service.export_cnc_files(
                org_id=org_id, order_id=order_id, actor_id=uuid4()
            )
        with pytest.raises(DocumentaryError, match="work_order_dispatched"):
            service.optimize_work_order(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), color="BLANCO"
            )


def test_delivery_schedule_upserts_and_records_event(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    events: list[tuple[str, list]] = []
    delivery_row = {
        "id": uuid4(), "org_id": org_id, "order_id": order_id,
        "order_code": "OT-1", "scheduled_date": "2026-09-25",
        "time_window": "PM", "address": "Av. Norte 100",
        "contact_name": None, "contact_phone": None,
        "installer_name": "Cuadrilla 2", "notes": None,
        "status": "SCHEDULED", "scheduled_by": uuid4(),
        "created_at": __import__("datetime").datetime(2026, 9, 23),
        "updated_at": __import__("datetime").datetime(2026, 9, 23),
    }

    def fake_one(sql_text: str, params: list, code: str = "not_found") -> dict:
        lowered = " ".join(sql_text.lower().split())
        if "insert into public.deliveries" in lowered:
            return dict(delivery_row)
        return {"id": str(order_id), "order_code": "OT-1", "status": "COMPLETED"}

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "left join public.deliveries d" in lowered:
            return [dict(delivery_row)]
        if "from public.deliveries" in lowered:
            return []
        if "insert into public.production_step_events" in lowered:
            events.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr("production.service.one", fake_one)
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr("production.confirmations.rows", lambda *_a, **_k: [])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.schedule_delivery(
            org_id=org_id, order_id=order_id, actor_id=uuid4(),
            scheduled_date="2026-09-25", time_window="pm",
            address="  Av. Norte 100 ", installer_name="Cuadrilla 2",
        )
    delivery = out["delivery"]
    assert delivery["status"] == "SCHEDULED"
    assert delivery["time_window"] == "PM"
    assert "wo_delivery_scheduled" in events[0][0]


def test_delivery_schedule_replay_adds_no_duplicate_event(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    events: list[tuple[str, list]] = []
    stored = {
        "id": uuid4(), "org_id": org_id, "order_id": order_id,
        "order_code": "OT-1", "scheduled_date": date(2026, 9, 25),
        "time_window": "PM", "address": "Av. Norte 100",
        "contact_name": None, "contact_phone": None,
        "installer_name": "Cuadrilla 2", "notes": None,
        "status": "SCHEDULED", "scheduled_by": uuid4(),
        "created_at": datetime(2026, 9, 23), "updated_at": datetime(2026, 9, 23),
    }

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "left join public.deliveries d" in lowered or "from public.deliveries" in lowered:
            return [dict(stored)]
        if "insert into public.production_step_events" in lowered:
            events.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {"id": str(order_id), "order_code": "OT-1", "status": "DISPATCHED"},
    )
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr("production.confirmations.rows", lambda *_a, **_k: [])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.schedule_delivery(
            org_id=org_id, order_id=order_id, actor_id=uuid4(),
            scheduled_date="2026-09-25", time_window="PM",
            address="Av. Norte 100", installer_name="Cuadrilla 2",
        )
    assert events == []
    assert out["delivery"]["status"] == "SCHEDULED"


def test_installation_requires_delivered_delivery(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {
            "id": str(order_id), "order_code": "OT-1",
            "status": "DISPATCHED", "payload_json": {},
        },
    )
    monkeypatch.setattr(
        "production.service.rows",
        lambda *_a, **_k: [{"status": "ON_ROUTE"}],
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="installation_requires_delivered"):
            service.confirm_installation(org_id=org_id, order_id=order_id, actor_id=uuid4())


def test_delivery_transition_rejected_after_installation(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {"id": str(order_id), "order_code": "OT-1", "status": "INSTALLED"},
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="order_already_installed"):
            service.transition_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="FAILED"
            )


def test_get_delivery_rejects_unknown_order(monkeypatch) -> None:
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [])
    with patch("production.service.documentary_backend", side_effect=_atomic):
        with pytest.raises(DocumentaryError, match="work_order_not_found"):
            service.get_delivery(org_id=uuid4(), order_id=uuid4())


def test_delivery_schedule_guards_order_state_and_inputs(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "production.service.one",
        lambda *_a, **_k: {"id": str(order_id), "order_code": "OT-1", "status": "RELEASED"},
    )
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [])
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="delivery_requires_completed"):
            service.schedule_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(),
                scheduled_date="2026-09-25", time_window="AM", address="X 1",
            )
        with pytest.raises(DocumentaryError, match="delivery_window_invalid"):
            service.schedule_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(),
                scheduled_date="2026-09-25", time_window="NOCHE", address="X 1",
            )
        with pytest.raises(DocumentaryError, match="delivery_address_required"):
            service.schedule_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(),
                scheduled_date="2026-09-25", time_window="AM", address="  ",
            )
        with pytest.raises(DocumentaryError, match="delivery_date_invalid"):
            service.schedule_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(),
                scheduled_date="ayer", time_window="AM", address="X 1",
            )


def test_delivery_transition_requires_dispatched_order(monkeypatch) -> None:
    """ON_ROUTE needs the order DISPATCHED; DELIVERED needs ON_ROUTE first."""
    org_id, order_id = uuid4(), uuid4()
    order = {"id": str(order_id), "order_code": "OT-1", "status": "COMPLETED"}
    delivery = {"id": uuid4(), "status": "SCHEDULED"}

    monkeypatch.setattr(
        "production.service.one",
        lambda sql_text, params, code="nf": order if "orders" in sql_text else dict(delivery),
    )
    monkeypatch.setattr("production.service.rows", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "production.service.get_delivery", lambda **kw: {"delivery": {"status": delivery["status"]}}
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        with pytest.raises(DocumentaryError, match="delivery_requires_dispatched"):
            service.transition_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="ON_ROUTE"
            )
        # DELIVERED is not a manual transition — only confirm_delivery (the
        # sealed-POD path) may stamp it.
        with pytest.raises(DocumentaryError, match="delivery_transition_invalid"):
            service.transition_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="DELIVERED"
            )
        with pytest.raises(DocumentaryError, match="delivery_transition_invalid"):
            service.transition_delivery(
                org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="SCHEDULED"
            )


def test_delivery_transition_fails_and_replays(monkeypatch) -> None:
    org_id, order_id = uuid4(), uuid4()
    order = {"id": str(order_id), "order_code": "OT-1", "status": "DISPATCHED"}
    delivery = {"id": uuid4(), "status": "ON_ROUTE"}
    events: list[tuple[str, list]] = []

    def fake_rows(sql_text: str, params: list) -> list:
        lowered = " ".join(sql_text.lower().split())
        if "update public.deliveries set status" in lowered:
            delivery["status"] = params[0]
        if "insert into public.production_step_events" in lowered:
            events.append((lowered, list(params)))
        return [{"id": "ok"}]

    monkeypatch.setattr(
        "production.service.one",
        lambda sql_text, params, code="nf": order if "orders" in sql_text else dict(delivery),
    )
    monkeypatch.setattr("production.service.rows", fake_rows)
    monkeypatch.setattr(
        "production.service.get_delivery", lambda **kw: {"delivery": {"status": delivery["status"]}}
    )
    with patch("production.service.transaction.atomic", side_effect=_atomic), patch(
        "production.service.documentary_backend", side_effect=_atomic
    ):
        out = service.transition_delivery(
            org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="FAILED"
        )
        replay = service.transition_delivery(
            org_id=org_id, order_id=order_id, actor_id=uuid4(), to_status="FAILED"
        )
    assert out["delivery"]["status"] == "FAILED"
    assert replay["delivery"]["status"] == "FAILED"
    assert len(events) == 1 and events[0][1][2] == "WO_DELIVERY_FAILED"


def test_prep_lists_approved_versions_without_orders(monkeypatch) -> None:
    version_id, project_id = uuid4(), uuid4()
    seen = {}

    def fake_rows(query, params=()):
        seen["query"] = query
        return [
            {
                "id": version_id,
                "project_id": project_id,
                "revision_code": "REV-A",
                "project_code": "PRJ-1",
                "positions": 3,
            }
        ]

    monkeypatch.setattr(service, "rows", fake_rows)
    monkeypatch.setattr(service, "documentary_backend", _atomic)
    output = service.production_prep(org_id=uuid4())
    assert "production_allowed" in seen["query"]
    assert "NOT EXISTS" in seen["query"]
    assert output["versions"] == [
        {
            "version_id": str(version_id),
            "project_id": str(project_id),
            "project_code": "PRJ-1",
            "revision_code": "REV-A",
            "positions": 3,
        }
    ]


def test_public_order_surfaces_workflow_flags() -> None:
    order = {
        "id": uuid4(),
        "order_code": "OT-1",
        "order_type": "WORKSHOP_OT",
        "status": "COMPLETED",
        "payload_json": json.dumps(
            {
                "position_id": "p1",
                "packing": {"units": []},
                "optimization": {
                    "stock_reservations": [
                        {"short": "0.00"},
                        {"short": "12.50"},
                    ]
                },
            }
        ),
        "project_version_id": None,
        "created_at": "2026-09-23T00:00:00Z",
        "steps_total": 5,
        "steps_done": 5,
        "next_step_code": "GLAZE",
        "has_dispatch_note": False,
    }
    output = service._public_order(order)
    assert output["next_step"] == {"code": "GLAZE", "label": service._STEP_LABELS["GLAZE"]}
    assert output["dispatch_ready"] is True
    assert output["shortage"] == 1

    order["has_dispatch_note"] = True
    output = service._public_order(order)
    assert output["dispatch_ready"] is False

    order["payload_json"] = json.dumps({"prep": {"shortages": 2}})
    output = service._public_order(order)
    # The prep count is version scope, never the order's own — it surfaces
    # under version_shortage while shortage stays the order's reservations.
    assert output["shortage"] == 0
    assert output["version_shortage"] == 2
