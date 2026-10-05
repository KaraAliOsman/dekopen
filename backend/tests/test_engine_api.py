from __future__ import annotations

from contextlib import nullcontext

import pytest
from rest_framework.test import APIClient

import engine_api.views
from authentication.tenancy import MembershipRepository
from backend.tests.factories import (
    ORG_A_ID,
    SYSTEM_ID,
    authenticated_identity,
    demo_60_params,
    membership,
)
from dekopen_engine import SystemFamily
from engine_api.repository import (
    SystemNotFound,
    SystemParamsRepository,
    VisibleProfileSystem,
)


def configure_api(
    client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, token = authenticated_identity()
    client.force_authenticate(user=user, token=token)
    monkeypatch.setattr(
        engine_api.views,
        "authenticated_rls_context",
        lambda claims: nullcontext(),
    )
    monkeypatch.setattr(
        MembershipRepository,
        "list_active_for_user",
        lambda self, user_id: (membership(),),
    )
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_visible",
        lambda self, system_id, active_org_id: demo_60_params(),
    )


def g1_request() -> dict[str, object]:
    return {
        "system_id": str(SYSTEM_ID),
        "nominal_width_mm": "1000.00",
        "nominal_height_mm": "1000.00",
        "color": "WHITE",
        "parametric_tree": {
            "id": "g1",
            "type": "BAY",
            "opening_type": "FIXED",
            "glass_thickness_mm": "4.00",
            "glass_spec": "4",
        },
    }


def g4_request() -> dict[str, object]:
    return {
        "system_id": str(SYSTEM_ID),
        "nominal_width_mm": "1800.00",
        "nominal_height_mm": "1500.00",
        "color": "WHITE",
        "parametric_tree": {
            "id": "g4",
            "type": "SPLIT_V",
            "split_offset_mm": "900.00",
            "mullion_profile_sku": "POSTE-V",
            "children": [
                {
                    "id": "bay_fixed",
                    "type": "BAY",
                    "opening_type": "FIXED",
                    "glass_thickness_mm": "24.00",
                    "glass_spec": "4-16-4 Float Incoloro",
                },
                {
                    "id": "bay_ob",
                    "type": "BAY",
                    "opening_type": "TILT_TURN_RIGHT",
                    "glass_thickness_mm": "20.00",
                    "glass_spec": "4-12-4 Float Incoloro",
                },
            ],
        },
    }


def test_g1_through_adapter_matches_engine_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    response = client.post("/api/v1/engine/calculate/", g1_request(), format="json")

    assert response.status_code == 200
    payload = response.json()
    assert {cut["length_mm"] for cut in payload["profile_cuts"] if cut["role"] == "FRAME"} == {
        "1006.00"
    }
    assert payload["glasses"][0]["width_mm"] == "910.00"
    assert payload["glasses"][0]["height_mm"] == "910.00"
    assert payload["hardware_items"] == []
    assert payload["calculation_hash"].startswith("sha256:")
    assert "inspector" not in payload


def test_g4_compound_through_adapter_matches_engine_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    response = client.post("/api/v1/engine/calculate/", g4_request(), format="json")

    assert response.status_code == 200
    payload = response.json()
    mullion = next(cut for cut in payload["profile_cuts"] if cut["role"] == "MULLION_V")
    assert mullion["length_mm"] == "1380.00"
    glasses = {piece["bay_id"]: piece for piece in payload["glasses"]}
    assert glasses["bay_fixed"]["width_mm"] == "830.00"
    assert glasses["bay_ob"]["width_mm"] == "696.00"


def test_deferred_opening_returns_422(monkeypatch: pytest.MonkeyPatch) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    payload = g1_request()
    payload["parametric_tree"]["opening_type"] = "DOOR_DOUBLE"

    response = client.post("/api/v1/engine/calculate/", payload, format="json")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_engine_contract"


def test_inaccessible_system_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_visible",
        lambda self, system_id, active_org_id: (_ for _ in ()).throw(SystemNotFound()),
    )
    response = client.post("/api/v1/engine/calculate/", g1_request(), format="json")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "system_not_found"


def test_api_dimensions_must_be_decimal_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    payload = g1_request()
    payload["nominal_width_mm"] = 1000.0
    response = client.post("/api/v1/engine/calculate/", payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_engine_systems_requires_bearer() -> None:
    response = APIClient().get("/api/v1/engine/systems/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_engine_systems_returns_only_the_minimal_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = APIClient()
    configure_api(client, monkeypatch)
    monkeypatch.setattr(
        SystemParamsRepository,
        "list_visible",
        lambda self, active_org_id: (
            VisibleProfileSystem(
                id=SYSTEM_ID,
                code="DEMO_60",
                name="Sistema Demo 60mm PVC",
                is_demo=True,
                system_family=SystemFamily.CASEMENT,
            ),
        ),
    )

    monkeypatch.setattr("catalogs.readiness.catalog_readiness",
        lambda *_: {"quote_ready": False, "reasons": ["manufacturing"]})
    response = client.get("/api/v1/engine/systems/")

    assert response.status_code == 200
    assert response.json() == {
        "systems": [
            {
                "id": str(SYSTEM_ID),
                "code": "DEMO_60",
                "name": "Sistema Demo 60mm PVC",
                "is_demo": True,
                "system_family": "CASEMENT",
                "allowed_openings": [
                    "AWNING", "DOOR_DOUBLE", "DOOR_ENTRY", "FIXED",
                    "TILT_TURN_LEFT", "TILT_TURN_RIGHT",
                    "TURN_LEFT", "TURN_RIGHT",
                ],
                "typology_limits": [],
                "quote_ready": False,
                "readiness_reasons": ["manufacturing"],
            }
        ]
    }


def test_engine_systems_enforces_owner_aal2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = APIClient()
    user, token = authenticated_identity(aal="aal1")
    client.force_authenticate(user=user, token=token)
    monkeypatch.setattr(engine_api.views, "authenticated_rls_context", lambda claims: nullcontext())
    monkeypatch.setattr(
        MembershipRepository,
        "list_active_for_user",
        lambda self, user_id: (membership(ORG_A_ID, role="OWNER"),),
    )
    monkeypatch.setattr(SystemParamsRepository, "list_visible", lambda self, active_org_id: ())

    response = client.get("/api/v1/engine/systems/")

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "mfa_required",
        "detail": "OWNER requires aal2",
        "required_aal": "aal2",
    }


def test_layout_api_binds_to_same_calculation_and_tenant(monkeypatch):
    client = APIClient()
    configure_api(client, monkeypatch)
    request = g1_request()
    response = client.post("/api/v1/engine/layout/", request, format="json")
    calculated = client.post("/api/v1/engine/calculate/", request, format="json")
    assert response.status_code == 200
    assert response.json()["calculation_hash"] == calculated.json()["calculation_hash"]
    assert response.json()["nodes"][0]["horizontal"]["half"] == "500.00"
    request["color"] = "NOT_A_DECLARED_FINISH"
    response = client.post("/api/v1/engine/layout/", request, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
