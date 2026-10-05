from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

import pytest

from dekopen_engine import ProfileRole, SystemParams
from dekopen_engine.snapshot import calculation_hash, calculation_response, canonical_json
from engine.scripts.regenerate_golden import SNAPSHOT, check_snapshot, generated_bytes, golden_request, golden_result
from engine.tests.test_shot06_core import assert_role, exact_weight_for_leaf

D = Decimal


def test_golden_composite_is_distinct_from_g3(demo_60_params: SystemParams) -> None:
    result = golden_result()
    assert_role(result, ProfileRole.FRAME, [("1506", 2), ("1406", 2)], [("1470", 2), ("1370", 2)])
    assert_role(result, ProfileRole.MULLION_V, [("1280", 1)], [("1270", 1)])
    # The 672 mm horizontal stays bare under the white-member rule (≥ 1000 mm).
    assert_role(result, ProfileRole.SASH, [("672", 2), ("1302", 2)], [("1266", 2)])
    assert_role(result, ProfileRole.GLAZING_BEAD, [("689", 2), ("1319", 2), ("555", 2), ("1185", 2)], [])
    assert [(p.width_mm, p.height_mm, p.area_m2, p.weight_kg) for p in result.glasses] == [
        (D("680"), D("1310"), D("0.8908"), D("17.82")),
        (D("546"), D("1176"), D("0.6421"), D("12.84")),
    ]
    exact = exact_weight_for_leaf(result, demo_60_params, "bay_2")
    assert (exact.pvc_weight_kg, exact.steel_weight_kg, exact.infill_weight_kg, exact.total_weight_kg) == (
        D("4.7376"), D("4.3044"), D("12.841920"), D("24.383920"),
    )
    assert result.leaf_weights[0].total_weight_kg == D("24.38")
    assert result.hardware_items[0].kit_sku == "KIT-TILT-TURN"
    assert result.panels == []


def test_hash_preimage_is_canonical_and_has_no_self_hash() -> None:
    request = {"dimension_mm": D("12.00"), "name": "Compás"}
    response = {"weight_kg": D("2.50"), "items": ["L1", "L2"]}
    expected_preimage = '{"request":{"dimension_mm":"12.00","name":"Compás"},"response_without_calculation_hash":{"items":["L1","L2"],"weight_kg":"2.50"}}'.encode()
    actual = calculation_hash(request, response)
    assert actual == "sha256:" + hashlib.sha256(expected_preimage).hexdigest()
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", actual)
    assert calculation_hash(dict(reversed(list(request.items()))), response) == actual
    assert calculation_hash(request, {**response, "calculation_hash": "excluded"}) == actual
    assert calculation_hash({**request, "dimension_mm": D("12.01")}, response) != actual
    assert calculation_hash(request, {**response, "weight_kg": D("2.51")}) != actual
    assert calculation_hash(request, {**response, "items": ["L2", "L1"]}) != actual
    assert canonical_json(request) == '{"dimension_mm":"12.00","name":"Compás"}'.encode()


def test_golden_byte_check_never_writes_and_detects_one_byte_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import engine.scripts.regenerate_golden as generator
    assert check_snapshot()
    original = SNAPSHOT.read_bytes()
    assert original == generated_bytes() == generated_bytes()
    assert original.endswith(b"\n") and not original.endswith(b"\n\n") and b"\r" not in original
    mutation = bytearray(original)
    mutation[original.index(b'"1500.00"') + 1] = ord("2")
    target = tmp_path / "mutated.json"
    target.write_bytes(mutation)
    before = target.stat().st_mtime_ns
    assert not check_snapshot(target)
    monkeypatch.setattr(generator, "SNAPSHOT", target)
    monkeypatch.setattr(sys, "argv", ["regenerate_golden", "--check"])
    with pytest.raises(SystemExit, match="Golden byte drift"):
        generator.main()
    assert target.read_bytes() == mutation and target.stat().st_mtime_ns == before
    assert SNAPSHOT.read_bytes() == original


@pytest.mark.parametrize("value", [0.1, Decimal("NaN"), {"width_mm": Decimal("1.005")}])
def test_canonical_serialization_rejects_approximation(value: object) -> None:
    with pytest.raises(ValueError):
        canonical_json(value)


def test_snapshot_request_identity_and_response_contract() -> None:
    request = golden_request()
    assert request["system_id"] == "3067da09-3119-5ad0-a1d5-498cd2dfd753"
    response = calculation_response(request, golden_result())
    # D05: finish identity + declared surcharge rows ride on the BOM.
    assert set(response) == {"calculation_hash", "profile_cuts", "reinforcements", "glasses", "panels", "hardware_items", "leaf_weights", "fittings", "finish_key", "finish_label", "finish_class", "color_surcharges"}
    assert json.loads(generated_bytes()) == {"request": request, "response": response}
    changed = deepcopy(request)
    changed["color"] = "CHANGED-HASH-INPUT"
    assert calculation_response(changed, golden_result())["calculation_hash"] != response["calculation_hash"]
