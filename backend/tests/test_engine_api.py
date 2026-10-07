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
from dekopen_engine.openings import (
    default_capabilities_for_family,
    spec_options_from_capabilities,
)
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
    # A movement declared on the spec axis whose fabrication D08 owns
    # still surfaces the deferred-opening contract.
    del payload["parametric_tree"]["opening_type"]
    payload["parametric_tree"]["opening"] = {"movement": "PIVOT_V"}

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
                # D03: the systems list advertises the concrete opening
                # compositions the system's capabilities admit.
                "opening_options": spec_options_from_capabilities(
                    default_capabilities_for_family(SystemFamily.CASEMENT)
                ),
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
    # D05: an undeclared finish is a colour-combination failure carrying
    # the engine's structured reason — more precise than validation_error.
    assert response.json()["error"]["code"] == "color_combination_invalid"
    assert response.json()["error"]["reason"] == "color_not_declared"


def test_repository_loads_glass_products_rules_and_limits(monkeypatch):
    """D02 loaders: product rows (system-scoped first), per-product
    surcharges, safety rules and type limits — parsed into engine models."""
    from decimal import Decimal
    from uuid import uuid4

    from engine_api import repository as repo_module

    product_id = uuid4()
    product_row = (
        "VID-T", "Templado 6",
        '{"layers":[{"type":"lamina","panes":["6"],"interlayer":null,'
        '"tint":"CLEAR","treatment":"TEMPERED","coating":null,'
        '"coating_face":null,"supplier_sku":null}]}',
        "B", "1.400", "0.630", "80.00", "15.00", "0.50", False,
        product_id, 3, "MANUFACTURER", True,
    )
    surcharge_row = (str(product_id), "TEMPERED", "M2", "5500", "Recargo templado", "CLP")
    rule_row = (
        "GLASS-SAFETY-DOOR", "Paño vidriado en puerta", "usa vidrio de seguridad",
        None, None, None, True, None, "SAFETY_GLASS", "WARNING",
        "NCh 135/2 — sintético", True,
    )
    limit_row = (
        "GLASS-LIMIT-TEMPERED-EXACT-CUT", "TEMPERED", None, None, None, "3200",
        None, None, None, True, "WARNING", "sintético", True,
    )

    class FakeCursor:
        def __init__(self):
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            if "FROM public.glass_products" in sql:
                self._rows = [product_row]
            elif "FROM public.glass_product_surcharges" in sql:
                self._rows = [surcharge_row]
            elif "FROM public.glass_safety_rules" in sql:
                self._rows = [rule_row]
            elif "FROM public.glass_type_limits" in sql:
                self._rows = [limit_row]
            else:
                self._rows = []

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return self._rows[0] if self._rows else None

    cursor = FakeCursor()
    monkeypatch.setattr(
        repo_module.connection, "cursor", lambda: cursor
    )
    repo = repo_module.SystemParamsRepository()
    org_id = uuid4()
    products = repo._load_glass_products(uuid4(), org_id)
    product = products["VID-T"]
    assert product.safety_class == "B"
    assert product.ug_w_m2k == Decimal("1.400")
    assert product.min_area_m2 == Decimal("0.50")
    assert product.price_tier == 3
    assert product.data_provenance == "MANUFACTURER"
    assert product.verified is True
    assert product.composition is not None
    assert product.surcharges[0].kind == "TEMPERED"
    assert product.surcharges[0].amount == Decimal("5500")
    assert product.surcharges[0].currency == "CLP"
    rules = repo._load_glass_safety_rules(org_id)
    assert rules[0].code == "GLASS-SAFETY-DOOR"
    assert rules[0].required_safety == "SAFETY_GLASS"
    assert rules[0].severity == "WARNING"
    assert rules[0].source_ref.startswith("NCh 135")
    limits = repo._load_glass_type_limits(org_id)
    assert limits[0].requires_exact_cut is True
    assert limits[0].max_side_mm == Decimal("3200")


def test_repository_glass_product_with_broken_composition_stays_unknown(monkeypatch):
    """An unparsable stored composition keeps composition=None — the product
    is selectable but derived numbers report unknown instead of guessing."""
    from uuid import uuid4

    from engine_api import repository as repo_module

    class FakeCursor:
        def __init__(self):
            self._rows = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=()):
            if "FROM public.glass_products" in sql:
                self._rows = [
                    ("VID-X", "Exótico", '{"layers":[{"type":"weird"}]}',
                     None, None, None, None, None, None, True, uuid4(), None,
                     None, False),
                ]
            else:
                self._rows = []

        def fetchall(self):
            return self._rows

    cursor = FakeCursor()
    monkeypatch.setattr(repo_module.connection, "cursor", lambda: cursor)
    repo = repo_module.SystemParamsRepository()
    products = repo._load_glass_products(uuid4(), uuid4())
    assert products["VID-X"].composition is None
    assert products["VID-X"].review_pending is True
    assert products["VID-X"].price_tier is None
