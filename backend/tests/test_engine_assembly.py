from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from backend.tests.factories import (
    SYSTEM_ID,
)
from backend.tests.test_engine_api import configure_api
from dekopen_engine.models import (
    EffectiveProfileArticle,
    MaterialType,
    ProfileRole,
)
from engine_api.adapter import (
    InvalidEngineRequest,
    parse_product_model,
)
from engine_api.repository import SystemParamsRepository

COUPLER_ARTICLE = EffectiveProfileArticle(
    sku="ACOPLE-60",
    role=ProfileRole.COUPLER,
    material=MaterialType.PVC,
    face_width_mm=Decimal("40.00"),
    welding_loss_mm=Decimal("0.00"),
    reinforcement_gap_mm=Decimal("0.00"),
    weight_kg_m=Decimal("0.9000"),
    steel_weight_kg_m=None,
    reinforcement_sku=None,
)


def configure_assembly_api(
    client: APIClient,
    monkeypatch: pytest.MonkeyPatch,
    couplers: dict[str, EffectiveProfileArticle] | None = None,
) -> None:
    configure_api(client, monkeypatch)
    monkeypatch.setattr(
        SystemParamsRepository,
        "load_coupler_articles",
        lambda self, system_id, active_org_id: couplers or {},
    )


def bow_product(angle: str = "15", coupler_sku: str | None = None) -> dict[str, object]:
    def module(index: int) -> dict[str, object]:
        return {
            "id": f"m{index}",
            "width_mm": "700.00",
            "height_mm": "1400.00",
            "tree": {
                "id": f"m{index}",
                "type": "BAY",
                "opening_type": "FIXED",
                "glass_thickness_mm": "4.00",
                "glass_spec": "4",
            },
        }

    return {
        "version": "product-v2",
        "assembly": {
            "modules": [module(1), module(2), module(3)],
            "couplings": [
                {"id": "c1", "angle_deg": angle, "coupler_profile_sku": coupler_sku},
                {"id": "c2", "angle_deg": angle, "coupler_profile_sku": coupler_sku},
            ],
        },
    }


def bow_request(product: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "system_id": str(SYSTEM_ID),
        "nominal_width_mm": "2100.00",
        "nominal_height_mm": "1400.00",
        "color": "WHITE",
        "product": product or bow_product(),
    }


class TestAssemblyParse:
    def test_rejects_wrong_version(self) -> None:
        with pytest.raises(InvalidEngineRequest):
            parse_product_model({"version": "product-v3", "assembly": {}})

    def test_rejects_unknown_module_fields(self) -> None:
        product = bow_product()
        product["assembly"]["modules"][0]["surprise"] = True
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_duplicate_module_ids(self) -> None:
        product = bow_product()
        product["assembly"]["modules"][1]["id"] = "m1"
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_duplicate_coupling_ids(self) -> None:
        product = bow_product()
        product["assembly"]["couplings"][1]["id"] = "c1"
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_pipe_in_module_and_coupling_ids(self) -> None:
        product = bow_product()
        product["assembly"]["modules"][0]["id"] = "left|upper"
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)
        product = bow_product()
        product["assembly"]["couplings"][0]["id"] = "c|1"
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_non_string_decimals(self) -> None:
        product = bow_product()
        product["assembly"]["modules"][0]["width_mm"] = 700
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_parses_explicit_connection_endpoints(self) -> None:
        product = bow_product()
        product["assembly"]["couplings"] = [
            {
                "id": "s1",
                "kind": "STACKED",
                "modules": ["m1", "m2"],
                "edges": ["top", "bottom"],
                "coupler_profile_sku": "ACOPLE-60",
            }
        ]
        model = parse_product_model(product)
        coupling = model.assembly.couplings[0]
        assert coupling.kind.value == "STACKED"
        assert coupling.modules == ["m1", "m2"]
        assert [edge.value for edge in coupling.edges] == ["top", "bottom"]

    @pytest.mark.parametrize(
        "field,value",
        [
            ("kind", "SPIRAL"),
            ("modules", ["m1"]),
            ("modules", "m1,m2"),
            ("edges", ["top"]),
            ("edges", ["top", "diagonal"]),
        ],
    )
    def test_rejects_malformed_connection_fields(
        self, field: str, value: object
    ) -> None:
        product = bow_product()
        coupling = product["assembly"]["couplings"][0]
        coupling[field] = value
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)


class TestAssemblyEndpoint:
    def test_bow_without_couplers_is_manufacturing_incomplete(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        response = client.post(
            "/api/v1/engine/assembly/calculate/", bow_request(), format="json"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "MANUFACTURING_INCOMPLETE"
        codes = {issue["code"] for issue in payload["issues"]}
        assert codes == {"coupler_profile_missing"}
        assert len(payload["plan"]["modules"]) == 3
        assert len(payload["plan"]["couplings"]) == 2
        assert len(payload["plan"]["front_chain"]) == 4
        assert len(payload["modules"]) == 3
        assert payload["bom"] is not None
        assert any(
            cut["sku"] == "MARCO" for cut in payload["bom"]["profile_cuts"]
        )
        assert payload["calculation_hash"].startswith("sha256:")

    def test_bow_with_catalog_couplers_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client, monkeypatch, couplers={"ACOPLE-60": COUPLER_ARTICLE}
        )
        request = bow_request(bow_product(coupler_sku="ACOPLE-60"))
        response = client.post(
            "/api/v1/engine/assembly/calculate/", request, format="json"
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "VALID"
        assert payload["issues"] == []
        coupler_cuts = [
            cut
            for cut in payload["bom"]["profile_cuts"]
            if cut["role"] == "COUPLER"
        ]
        assert [cut["length_mm"] for cut in coupler_cuts] == [
            "1400.00",
            "1400.00",
        ]

    def test_each_catalog_coupler_sku_is_selectable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        second = COUPLER_ARTICLE.model_copy(
            update={"sku": "CP-15", "face_width_mm": Decimal("50.00")}
        )
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": COUPLER_ARTICLE, "CP-15": second},
        )
        product = bow_product(coupler_sku="ACOPLE-60")
        product["assembly"]["couplings"][1]["coupler_profile_sku"] = "CP-15"
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(product),
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "VALID"
        coupler_cuts = [
            cut
            for cut in response.json()["bom"]["profile_cuts"]
            if cut["role"] == "COUPLER"
        ]
        assert {cut["sku"] for cut in coupler_cuts} == {"ACOPLE-60", "CP-15"}

    def test_fold_back_geometry_returns_invalid_status_not_http_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(bow_product(angle="95")),
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "INVALID"

    def test_nominal_dimensions_must_match_product_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        for field, value in (
            ("nominal_width_mm", "2200.00"),
            ("nominal_height_mm", "1500.00"),
        ):
            response = client.post(
                "/api/v1/engine/assembly/calculate/",
                {**bow_request(), field: value},
                format="json",
            )
            assert response.status_code == 400

    def test_malformed_product_is_400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request({"version": "product-v2"}),
            format="json",
        )
        assert response.status_code == 400


def contour_product(
    vertices: list[tuple[str, str]],
    bulges: list[str | None],
    width: str = "2400.00",
    height: str = "1400.00",
) -> dict[str, object]:
    return {
        "version": "product-v2",
        "assembly": {
            "modules": [
                {
                    "id": "m1",
                    "width_mm": width,
                    "height_mm": height,
                    "contour": {
                        "vertices": [
                            {"x_mm": x, "y_mm": y} for x, y in vertices
                        ],
                        "bulges": bulges,
                    },
                    "tree": {
                        "id": "m1",
                        "type": "BAY",
                        "opening_type": "FIXED",
                        "glass_thickness_mm": "4.00",
                        "glass_spec": "4",
                    },
                }
            ],
            "couplings": [],
        },
    }


class TestContourEndpoint:
    def test_trapezoid_evaluates_and_serializes_canonically(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        product = contour_product(
            [("0", "0"), ("2400", "0"), ("2200", "1400"), ("200", "1400")],
            [None, None, None, None],
        )
        request = bow_request(product)
        request["nominal_width_mm"] = "2400.00"
        request["nominal_height_mm"] = "1400.00"
        response = client.post(
            "/api/v1/engine/assembly/calculate/", request, format="json"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "VALID"
        frame = sorted(
            cut["angle_left"]
            for cut in payload["bom"]["profile_cuts"]
            if cut["role"] == "FRAME"
        )
        # Miter angles ride the canonical 0.1° contract — not raw precision.
        assert frame[0] == "40.9"
        glass = payload["bom"]["glasses"][0]
        assert glass["shape"] is not None
        assert glass["area_m2"] > "0"

    def test_arch_serializes_bent_members_canonically(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        product = contour_product(
            [("0", "0"), ("2400", "0"), ("2400", "1400"), ("0", "1400")],
            [None, None, "300.00", None],
        )
        request = bow_request(product)
        request["nominal_width_mm"] = "2400.00"
        request["nominal_height_mm"] = "1400.00"
        response = client.post(
            "/api/v1/engine/assembly/calculate/", request, format="json"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "MANUFACTURING_INCOMPLETE"
        codes = {issue["code"] for issue in payload["issues"]}
        assert "member_bending_required" in codes
        bent = [
            cut
            for cut in payload["bom"]["profile_cuts"]
            if cut.get("sagitta_mm") is not None
        ]
        assert bent and all(
            len(cut["sagitta_mm"].split(".")[-1]) <= 2 for cut in bent
        )

    def test_rect_contour_glass_stays_nestable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(client, monkeypatch)
        product = contour_product(
            [("0", "0"), ("1200", "0"), ("1200", "800"), ("0", "800")],
            [None, None, None, None],
            width="1200.00",
            height="800.00",
        )
        request = bow_request(product)
        request["nominal_width_mm"] = "1200.00"
        request["nominal_height_mm"] = "800.00"
        response = client.post(
            "/api/v1/engine/assembly/calculate/", request, format="json"
        )
        assert response.status_code == 200
        glass = response.json()["bom"]["glasses"][0]
        assert glass["shape"] is None


def sliding_product(layout: dict[str, object]) -> dict[str, object]:
    return {
        "version": "product-v2",
        "assembly": {
            "modules": [
                {
                    "id": "m1",
                    "width_mm": "1600.00",
                    "height_mm": "1400.00",
                    "tree": {
                        "id": "m1",
                        "type": "BAY",
                        "opening_type": "SLIDING_2L",
                        "glass_thickness_mm": "4.00",
                        "glass_spec": "4",
                        "sliding_layout": layout,
                    },
                },
            ],
            "couplings": [],
        },
    }


class TestSlidingLayoutParse:
    """P05 — the adapter accepts declared travel + primary_index (the IA2
    writer side already emits primary_index; P05 adds per-panel travel)."""

    def test_parses_travel_and_primary_index(self) -> None:
        product = sliding_product(
            {
                "tracks": 2,
                "primary_index": 1,
                "panels": [
                    {"slot": "S1", "kind": "MOVING", "track": 0, "travel": "RIGHT"},
                    {"slot": "S2", "kind": "MOVING", "track": 1, "travel": "LEFT"},
                ],
            }
        )
        parsed = parse_product_model(product)
        layout = parsed.assembly.modules[0].tree.sliding_layout
        assert layout is not None
        assert layout.primary_index == 1
        assert layout.panels[0].travel.value == "RIGHT"
        assert layout.panels[1].travel.value == "LEFT"

    def test_parses_layout_without_travel(self) -> None:
        product = sliding_product(
            {
                "tracks": 2,
                "panels": [
                    {"slot": "S1", "kind": "MOVING", "track": 0},
                    {"slot": "S2", "kind": "MOVING", "track": 1},
                ],
            }
        )
        parsed = parse_product_model(product)
        layout = parsed.assembly.modules[0].tree.sliding_layout
        assert layout is not None
        assert layout.panels[0].travel is None

    def test_rejects_unknown_travel(self) -> None:
        product = sliding_product(
            {
                "tracks": 2,
                "panels": [
                    {"slot": "S1", "kind": "MOVING", "track": 0, "travel": "UP"},
                ],
            }
        )
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_fixed_panel_with_travel(self) -> None:
        product = sliding_product(
            {
                "tracks": 2,
                "panels": [
                    {"slot": "O1", "kind": "FIXED", "track": None, "travel": "LEFT"},
                ],
            }
        )
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)

    def test_rejects_non_integer_primary_index(self) -> None:
        product = sliding_product(
            {
                "tracks": 2,
                "primary_index": "first",
                "panels": [
                    {"slot": "S1", "kind": "MOVING", "track": 0},
                    {"slot": "S2", "kind": "MOVING", "track": 1},
                ],
            }
        )
        with pytest.raises(InvalidEngineRequest):
            parse_product_model(product)


def envelope_coupler(min_deg: str | None, max_deg: str | None) -> EffectiveProfileArticle:
    """P06 fixture: a catalog coupler with a declared angle envelope (or an
    undeclared one when both bounds are None — the UNKNOWN state)."""
    return COUPLER_ARTICLE.model_copy(
        update={
            "coupler_angle_min_deg": Decimal(min_deg) if min_deg is not None else None,
            "coupler_angle_max_deg": Decimal(max_deg) if max_deg is not None else None,
        }
    )


class TestCouplerAngleEnvelope:
    """P06 — the catalog, not the engine code, declares which joint angles a
    coupler can close. The check compares over |angle_deg| (a mirrored mount
    serves the ± case) and only fires when the envelope is declared."""

    def test_declared_envelope_in_range_is_clean(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": envelope_coupler("0", "60")},
        )
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(bow_product(angle="22.5", coupler_sku="ACOPLE-60")),
            format="json",
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "VALID"
        assert payload["issues"] == []

    def test_declared_envelope_out_of_range_flags_the_joint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": envelope_coupler("0", "60")},
        )
        product = bow_product(angle="89", coupler_sku="ACOPLE-60")
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(product),
            format="json",
        )
        assert response.status_code == 200
        payload = response.json()
        angle_issues = [
            issue
            for issue in payload["issues"]
            if issue["code"] == "coupler_angle_incompatible"
        ]
        # Both joints share the same coupler and the same angle — both flag.
        assert [issue["target"] for issue in angle_issues] == [
            "coupling:c1",
            "coupling:c2",
        ]
        assert angle_issues[0]["severity"] == "warning"
        params = angle_issues[0]["params"]
        assert params["sku"] == "ACOPLE-60"
        assert Decimal(params["angle_deg"]) == Decimal("89")
        assert Decimal(params["min_deg"]) == Decimal("0")
        assert Decimal(params["max_deg"]) == Decimal("60")

    def test_envelope_compares_over_absolute_angle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": envelope_coupler("85", "95")},
        )
        for sign in ("90", "-90"):
            product = bow_product(angle=sign, coupler_sku="ACOPLE-60")
            response = client.post(
                "/api/v1/engine/assembly/calculate/",
                bow_request(product),
                format="json",
            )
            assert response.status_code == 200
            assert not any(
                issue["code"] == "coupler_angle_incompatible"
                for issue in response.json()["issues"]
            ), sign

    def test_undeclared_envelope_stays_unknown_not_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": envelope_coupler(None, None)},
        )
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(bow_product(angle="45", coupler_sku="ACOPLE-60")),
            format="json",
        )
        assert response.status_code == 200
        assert not any(
            issue["code"] == "coupler_angle_incompatible"
            for issue in response.json()["issues"]
        )

    def test_envelope_boundary_is_inclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = APIClient()
        configure_assembly_api(
            client,
            monkeypatch,
            couplers={"ACOPLE-60": envelope_coupler("60", "120")},
        )
        response = client.post(
            "/api/v1/engine/assembly/calculate/",
            bow_request(bow_product(angle="60", coupler_sku="ACOPLE-60")),
            format="json",
        )
        assert response.status_code == 200
        assert not any(
            issue["code"] == "coupler_angle_incompatible"
            for issue in response.json()["issues"]
        )
