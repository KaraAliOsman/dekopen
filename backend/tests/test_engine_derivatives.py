"""Derived HTTP boundary, strict calculation regression and real pure corrections."""

from contextlib import nullcontext
from decimal import Decimal as D
import json

import pytest
from rest_framework.test import APIClient

from backend.tests.factories import demo_60_params
from backend.tests.test_engine_api import configure_api, g1_request
from dekopen_engine.inspection_models import InspectorConfig, WorkshopAnnotations, InspectorDiff
from dekopen_engine.inspector import apply_inspector_diff
from engine.tests.test_inspector import config as config
from engine.tests.test_shot06_core import core_node
import engine_api.derivative_views
from engine_api.inspection_repository import InspectorAuthorities, InspectorRepository
from engine_api.repository import SystemParamsRepository


def client_with_inspector(monkeypatch: pytest.MonkeyPatch, config: InspectorConfig) -> APIClient:
    client = APIClient()
    configure_api(client, monkeypatch)
    monkeypatch.setattr(engine_api.derivative_views, "authenticated_rls_context", lambda claims: nullcontext())
    monkeypatch.setattr(InspectorRepository, "load", lambda self, system, org: InspectorAuthorities(config, D("12")))
    return client


def test_r07_http_fix_changes_observations_not_calculation(monkeypatch: pytest.MonkeyPatch,
                                                         config: InspectorConfig) -> None:
    client = client_with_inspector(monkeypatch, config)
    technical = g1_request()
    annotation = {"bay_id": "g1", "bottom_drain_holes_mm": ["100.00", "900.00"],
                  "continuous_width_mm": "1000.00", "finish_class": "WHITE", "has_coupler": False}
    request = {**technical, "annotations": [annotation]}
    before = client.post("/api/v1/engine/calculate/", technical, format="json")
    response = client.post("/api/v1/engine/inspect/", request, format="json")
    assert response.status_code == 200
    assert response.data["status"] == "YELLOW" and response.data["production_allowed"]
    assert response.data["source_calculation_hash"] == before.data["calculation_hash"]
    fix = response.data["findings"][0]["fix"]
    parsed = InspectorDiff.model_validate_json(json.dumps(fix))
    # Pydantic's JSON entry point converts exact decimal strings without binary arithmetic.
    observations = [WorkshopAnnotations.model_validate_json(json.dumps(annotation))]
    applied = apply_inspector_diff(observations, parsed, D("1000"))
    after = client.post("/api/v1/engine/inspect/", {**technical,
                        "annotations": [item.model_dump(mode="json") for item in applied]}, format="json")
    assert after.status_code == 200 and after.data["status"] == "GREEN"
    assert after.data["source_calculation_hash"] == before.data["calculation_hash"]
    assert client.post("/api/v1/engine/calculate/", technical, format="json").data == before.data


def test_r06_preflight_does_not_make_invalid_calculate_successful(monkeypatch: pytest.MonkeyPatch,
                                                               config: InspectorConfig) -> None:
    client = client_with_inspector(monkeypatch, config)
    request = g1_request()
    request["parametric_tree"]["glass_thickness_mm"] = "25.00"
    assert client.post("/api/v1/engine/calculate/", request, format="json").status_code == 400
    response = client.post("/api/v1/engine/inspect/", request, format="json")
    assert response.status_code == 200
    assert response.data["source_calculation_hash"] is None
    assert any(f["rule_id"] == "R06" and f["severity"] == "RED" for f in response.data["findings"])


@pytest.mark.parametrize("updates,rule", [({"max_leaf_weight_kg": D("20.00")}, "R01"),
                                         ({"max_leaf_width_mm": D("1")}, "R03")])
def test_hardware_diagnostic_http_preserves_strict_error(monkeypatch: pytest.MonkeyPatch,
    config: InspectorConfig, updates: dict[str, object], rule: str) -> None:
    client = client_with_inspector(monkeypatch, config)
    params = demo_60_params()
    kit = next(k for k in params.available_hardware_kits if k.sku == "KIT-AWNING-16")
    changed = params.model_copy(update={"available_hardware_kits": [kit.model_copy(update=updates)]})
    monkeypatch.setattr(SystemParamsRepository, "load_visible", lambda self, system, org: changed)
    node = core_node("G6")
    request = {**g1_request(), "parametric_tree": node.model_dump(mode="json", exclude_none=True),
               "nominal_width_mm": str(node.width_mm), "nominal_height_mm": str(node.height_mm)}
    assert client.post("/api/v1/engine/calculate/", request, format="json").status_code == 400
    response = client.post("/api/v1/engine/inspect/", request, format="json")
    assert response.status_code == 200 and response.data["source_calculation_hash"] is None
    assert any(f["rule_id"] == rule for f in response.data["findings"])


@pytest.mark.parametrize("endpoint", ["inspect", "optimize-cut"])
def test_derived_endpoints_require_auth_and_reject_forged_cuts(monkeypatch: pytest.MonkeyPatch,
    config: InspectorConfig, endpoint: str) -> None:
    path = f"/api/v1/engine/{endpoint}/"
    assert APIClient().post(path, g1_request(), format="json").status_code == 401
    client = client_with_inspector(monkeypatch, config)
    response = client.post(path, {**g1_request(), "cuts": [{"length_mm": "1"}]}, format="json")
    assert response.status_code == 400
    assert "Revisa" in response.data["error"]["detail"]
