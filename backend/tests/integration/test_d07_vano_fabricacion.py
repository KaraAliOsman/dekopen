"""D07 del vano a la fabricación — estados de medida, gate de liberación y
revisión con su Δ.

Ejercita el camino real contra PostgreSQL: la posición guarda el registro
del vano con su regla de montaje, la confirmación sella la medida para
producción, el freeze se niega a liberar una OT sin medidas confirmadas y
una rectificación posterior a la emisión genera una revisión que compara
con Δ.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from authentication.errors import ContractAPIException
from authentication.tenancy import Membership, TenantContext
from documents.repository import DocumentaryError, documentary_backend, one, write
from documents.service import compare_versions, save_documentary_inputs
from pricing.repository import commercial_backend, json_text
from pricing.service import apply_operation, decoded, preview
from production.service import release_production
from projects import measurement, service as projects_service
from dekopen_engine.snapshot import calculation_response
from engine_api.adapter import calculate_from_api
from engine_api.repository import SystemParamsRepository
from tests.integration.test_shot09_documentary import (
    _freeze,
    _seed_project,
    as_user,
    documentary_tenant,  # noqa: F401 — pytest resuelve el fixture por nombre
)

pytestmark = pytest.mark.rls_integration
D = Decimal


def _tenant(org: UUID, role: str) -> TenantContext:
    membership = Membership(organization_id=org, organization_name="Fixture", role=role)
    return TenantContext(active_organization=membership, memberships=(membership,))


def _rule_id(user: UUID, system_code: str = "EN_VANO") -> UUID:
    # Las lecturas directas corren bajo el rol de servicio con claims:
    # pricing_backend tiene el grant de tabla y su policy exige auth.uid().
    with as_user(user), commercial_backend():
        row = one(
            """
            SELECT r.id FROM public.mounting_rules r
            JOIN public.profile_systems s ON s.id = r.system_id
            WHERE s.code = 'DEMO_60' AND r.code = %s AND r.org_id IS NULL
            """,
            [system_code],
        )
    return UUID(str(row["id"]))


def _vano(
    org: UUID, project_id: UUID, position_id: UUID, user: UUID, *,
    confirm: bool = False,
) -> None:
    """Registra el vano con su regla en la posición, como lo haría save_position.
    El proyecto del fixture ya está cotizado: el guard comercial exige el rol
    de servicio, el mismo bajo el que corre la escritura real."""
    rule_id = _rule_id(user)
    with as_user(user), commercial_backend():
        _write_vano(org, position_id, rule_id=rule_id, confirmed=confirm)
    if confirm:
        with as_user(user):
            measurement.confirm_measurement(
                org, project_id, position_id, user, confirmed=True,
            )


def _write_vano(org: UUID, position_id: UUID, *, rule_id: UUID, confirmed: bool) -> None:
    write(
        """
        UPDATE public.project_positions
        SET rough_opening_input = %s::jsonb,
            mounting_rule_id = %s,
            measurement_state = %s,
            updated_at = clock_timestamp()
        WHERE id = %s AND org_id = %s
        """,
        [
            json_text({
                "width_points_mm": ["1520.00", "1518.00", "1522.00"],
                "height_points_mm": ["1220.00"],
                "wall_type": "MASONRY",
            }),
            str(rule_id),
            "SITE_RECTIFIED" if confirmed else "CLIENT_DECLARED",
            str(position_id),
            str(org),
        ],
    )


def _owner_of(user: UUID, project_id: UUID) -> UUID:
    with as_user(user), commercial_backend():
        row = one(
            "SELECT created_by FROM public.projects WHERE id=%s", [str(project_id)]
        )
    return UUID(str(row["created_by"]))


def _measurement(user: UUID, position_id: UUID) -> dict[str, object]:
    with as_user(user), commercial_backend():
        row = one(
            "SELECT * FROM public.project_positions WHERE id=%s", [str(position_id)]
        )
    return row


def _refresh_documentary_inputs(
    org: UUID, owner: UUID, project_id: UUID, position_id: UUID,
    width_mm: Decimal, height_mm: Decimal,
) -> None:
    """Vuelve a capturar los inputs documentales con el hash de la cota nueva —
    lo que haría la UI tras rectificar (el freeze exige identidad fresca)."""
    with as_user(owner), documentary_backend():
        stored = one(
            "SELECT manufacturing_placement_policy_id,handle_requirement_policy_id,"
            "reinforcement_cut_policy_id,workshop_annotations::text,structural_inputs::text,"
            "glass_polishing::text,handle_intents::text,accessory_schedule::text,"
            "legacy_handle_migration_confirmed "
            "FROM public.position_documentary_inputs "
            "WHERE position_id=%s AND project_id=%s AND org_id=%s",
            [str(position_id), str(project_id), str(org)],
        )
        system = one(
            "SELECT system_id, parametric_tree::text, color_interior "
            "FROM public.project_positions WHERE id=%s", [str(position_id)]
        )
    system_id = UUID(str(system["system_id"]))
    tree = json.loads(system["parametric_tree"])
    with as_user(owner):
        params = SystemParamsRepository().load_visible(system_id, org)
        result = calculate_from_api(
            parametric_tree=tree,
            nominal_width_mm=width_mm,
            nominal_height_mm=height_mm,
            color=system["color_interior"],
            params=params,
        )
        identity = calculation_response(
            {
                "system_id": str(system_id),
                "parametric_tree": tree,
                "nominal_width_mm": width_mm,
                "nominal_height_mm": height_mm,
                "color": system["color_interior"],
            },
            result,
        )["calculation_hash"]
        annotations = json.loads(stored["workshop_annotations"] or "[]")
        for note in annotations:
            if note.get("continuous_width_mm") is not None:
                note["continuous_width_mm"] = str(width_mm)
        save_documentary_inputs(
            org_id=org,
            actor_id=owner,
            project_id=project_id,
            data={
                "payment_terms": "50% anticipo, 50% contra entrega",
                "quotation_valid_until": date(2030, 12, 31),
                "positions": [{
                    "position_id": position_id,
                    "calculation_hash": identity,
                    "location_tag": "FACHADA-NORTE",
                    "manufacturing_placement_policy_id": stored[
                        "manufacturing_placement_policy_id"
                    ],
                    "handle_requirement_policy_id": stored[
                        "handle_requirement_policy_id"
                    ],
                    "reinforcement_cut_policy_id": stored[
                        "reinforcement_cut_policy_id"
                    ],
                    "workshop_annotations": annotations,
                    "structural_inputs": json.loads(stored["structural_inputs"] or "[]"),
                    "glass_polishing": json.loads(stored["glass_polishing"] or "[]"),
                    "handle_intents": json.loads(stored["handle_intents"] or "[]"),
                    "accessory_schedule": json.loads(
                        stored["accessory_schedule"]
                    ) if stored["accessory_schedule"] else {
                        "schema_version": 1,
                        "coverage": "NONE_REQUIRED",
                        "items": [],
                    },
                    "legacy_handle_migration_confirmed": bool(
                        stored["legacy_handle_migration_confirmed"]
                    ),
                }],
            },
        )


def test_confirm_measurement_stamps_and_unconfirm_resets(documentary_tenant) -> None:  # noqa: F811 — fixture inyectada
    org, _, users, _ = documentary_tenant
    project_id, position_id, _ = _seed_project(org, users["OWNER"])
    _vano(org, project_id, position_id, users["OWNER"])

    with as_user(users["OWNER"]):
        measurement.confirm_measurement(
            org, project_id, position_id, users["OWNER"], confirmed=True
        )
    row = _measurement(users["OWNER"], position_id)
    assert row["measurement_state"] == "CONFIRMED"
    assert row["measurement_confirmed_at"] is not None
    assert row["measurement_confirmed_by"] == users["OWNER"]

    with as_user(users["OWNER"]):
        measurement.confirm_measurement(
            org, project_id, position_id, users["OWNER"], confirmed=False
        )
    row = _measurement(users["OWNER"], position_id)
    assert row["measurement_state"] == "SITE_RECTIFIED"
    assert row["measurement_confirmed_at"] is None
    assert row["measurement_confirmed_by"] is None


def test_unconfirmed_measurement_freezes_but_blocks_release(documentary_tenant) -> None:  # noqa: F811 — fixture inyectada
    """La cotización puede sellarse con medidas sin confirmar — es cotización —
    pero release_production no libera la OT (gate del encargo)."""
    org, _, users, _ = documentary_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    _vano(org, project_id, position_id, users["OWNER"])

    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    assert frozen["created"] is True
    with as_user(users["OWNER"]), documentary_backend():
        version = one(
            "SELECT production_allowed, snapshot_json FROM public.project_versions WHERE id=%s",
            [frozen["id"]],
        )
    assert version["production_allowed"] is False
    snapshot = version["snapshot_json"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    position = snapshot["positions"][0]
    sealed = position["measurement"]
    assert sealed["state"] == "CLIENT_DECLARED"
    assert sealed["resolution"]["fabrication_source"] == "DERIVED"
    # Vano mínimo 1518 (−10/side en EN_VANO) → fabricación 1498.
    assert sealed["resolution"]["fabrication_width_mm"] == "1498.00"
    assert sealed["resolution"]["fabrication_height_mm"] == "1200.00"
    # El gate actúa en dos capas: la bandera sellada
    # (production_allowed=False → version_not_releasable) y, debajo, el
    # chequeo sobre el bloque de medida sellado (measurement_not_confirmed)
    # por si una versión llegara a liberarse con la bandera mal marcada.
    with pytest.raises(DocumentaryError) as blocked:
        with as_user(users["OWNER"]):
            release_production(
                org_id=org, version_id=UUID(frozen["id"]), actor_id=users["OWNER"]
            )
    assert str(blocked.value) in {
        "version_not_releasable", "measurement_not_confirmed"
    }


def test_confirmed_measurement_releases_and_seals_breakdown(documentary_tenant) -> None:  # noqa: F811 — fixture inyectada
    org, _, users, _ = documentary_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    _vano(org, project_id, position_id, users["OWNER"], confirm=True)

    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    with as_user(users["OWNER"]), documentary_backend():
        version = one(
            "SELECT production_allowed, snapshot_json FROM public.project_versions WHERE id=%s",
            [frozen["id"]],
        )
    assert version["production_allowed"] is True
    snapshot = version["snapshot_json"]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    sealed = snapshot["positions"][0]["measurement"]
    assert sealed["state"] == "CONFIRMED"
    assert sealed["confirmed_at"] is not None
    assert sealed["confirmed_by"] == str(users["OWNER"])
    breakdown = sealed["resolution"]["breakdown"]
    assert any(item["side"] == "top" for item in breakdown)
    # El gate interno pasa — la OT se crea.
    with as_user(users["OWNER"]):
        orders = release_production(
            org_id=org, version_id=UUID(frozen["id"]), actor_id=users["OWNER"]
        )
    assert orders["created"] is True or len(orders.get("orders") or []) >= 1


def _price(org: UUID, owner: UUID, project_id: UUID) -> UUID:
    """Vuelve a correr preview+apply para la revisión sucesora: las reglas de
    precio del fixture siguen vigentes en la org."""
    with as_user(owner), commercial_backend():
        operation = preview(org, _tenant(org, "OWNER"), {
            "project_id": project_id,
            "pricing_mode": "COST_PLUS_MARGIN",
            "currency": "CLP",
            "effective_date": date(2026, 9, 10),
            "context_code": "DEFAULT",
            "discount_pct": D("0"),
            "target_margin": D("0.35"),
            "segment": "RETAIL",
            "confirmed": False,
            "reason": "D07 reprice successor",
            "_actor_id": owner,
        })
        apply_operation(
            org, owner, "OWNER", UUID(operation["id"]), "D07 successor apply", False
        )
    return UUID(operation["id"])


def test_rectification_after_emission_reopens_as_revision_with_delta(
    documentary_tenant,  # noqa: F811 — fixture inyectada
) -> None:
    """Rectificada en obra después de la emisión: una revisión nueva sella el
    antes/después y compare devuelve el Δ de precio junto al cambio de medida."""
    org, _, users, _ = documentary_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    _vano(org, project_id, position_id, users["OWNER"], confirm=True)
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    assert frozen["created"] is True

    # REV-B: la rectificación en obra cambia el vano y la fabricación por el
    # flujo real del editor — save_position recalcula el BOM con el motor,
    # marca la medida como rectificada y limpia el sello de confirmación.
    with as_user(users["OWNER"]):
        projects_service.start_successor(org, project_id)
    current = _measurement(users["OWNER"], position_id)
    with as_user(users["OWNER"]):
        projects_service.save_position(
            org, project_id,
            {
                "expected_updated_at": current["updated_at"],
                "location_tag": current["location_tag"],
                "quantity": current["quantity"],
                "design": {
                    "system_id": UUID(str(current["system_id"])),
                    "parametric_tree": decoded(current["parametric_tree"]),
                    "nominal_width_mm": D("1300.00"),
                    "nominal_height_mm": D("1100.00"),
                    "color": current["color_interior"],
                },
                "measurement": {
                    "vano": {
                        "width_points_mm": [D("1320.00")],
                        "height_points_mm": [D("1120.00")],
                        "wall_type": "MASONRY",
                    },
                    "mounting_rule_id": UUID(str(current["mounting_rule_id"])),
                    "fabrication_lock": None,
                },
            },
            position_id=position_id,
        )
    _refresh_documentary_inputs(
        org, users["OWNER"], project_id, position_id, D("1300.00"), D("1100.00")
    )
    with as_user(users["OWNER"]):
        measurement.confirm_measurement(
            org, project_id, position_id, users["OWNER"], confirmed=True
        )
    # Se re-cotiza y se sella REV-B con las medidas rectificadas.
    operation_b = _price(org, users["OWNER"], project_id)
    frozen_b = _freeze(org, users["OWNER"], project_id, operation_b)
    assert frozen_b["revision_code"] == "REV-B"

    with as_user(users["OWNER"]):
        comparison = compare_versions(
            org_id=org, project_id=project_id, base_code="REV-A", head_code="REV-B"
        )
    summary = comparison["summary"]
    assert summary["price_gross_delta"] is not None
    entry = next(
        e for e in comparison["positions"] if e["position_index"] == 1
    )
    assert entry["change"] == "CHANGED"
    fields = {c["field"] for c in entry["changes"]}
    assert "width_mm" in fields
    assert "manufacturing" in fields  # firma documental: vano/estado cambió
    assert entry["before"]["measurement_state"] == "CONFIRMED"
    assert entry["after"]["measurement_state"] == "CONFIRMED"
    assert "1320" in json.dumps(entry["after"]["rough_opening_input"])


def test_save_position_writes_measurement_record(documentary_tenant) -> None:  # noqa: F811 — fixture inyectada
    """El guardado real del editor persiste el bloque measurement en columnas."""
    org, _, users, _ = documentary_tenant
    project_id, position_id, operation_id = _seed_project(org, users["OWNER"])
    row = _measurement(users["OWNER"], position_id)
    data = {
        "design": {"nominal_width_mm": D("1000.00"), "nominal_height_mm": D("1000.00")},
        "measurement": {
            "vano": {
                "width_points_mm": [D("1520.00")],
                "height_points_mm": [D("1220.00")],
                "wall_type": "MASONRY",
            },
            "mounting_rule_id": _rule_id(users["OWNER"]),
            "fabrication_lock": None,
        },
    }
    with as_user(users["OWNER"]):
        fields = measurement.measurement_fields_for_save(
            org, data=data, current=row, system_id=row["system_id"]
        )
    assert fields["measurement_state"] == "SITE_RECTIFIED"
    assert fields["mounting_rule_id"] == str(_rule_id(users["OWNER"]))
    assert fields["rough_opening_input"]["width_points_mm"] == ["1520.00"]

    # Sin cambios en evidencia ni cotas, un guardado posterior conserva CONFIRMED.
    row["measurement_state"] = "CONFIRMED"
    row["measurement_confirmed_at"] = "now()"
    row["measurement_confirmed_by"] = str(users["OWNER"])
    row["rough_opening_input"] = fields["rough_opening_input"]
    row["fabrication_lock"] = None
    row["mounting_rule_id"] = fields["mounting_rule_id"]
    with as_user(users["OWNER"]):
        keep = measurement.measurement_fields_for_save(
            org, data={"design": data["design"]}, current=row, system_id=row["system_id"]
        )
    assert keep["measurement_state"] == "CONFIRMED"

    # Cambio de cotas con evidencia intacta → rectificada, sello limpiado.
    changed_dims = {
        "design": {"nominal_width_mm": D("1100.00"), "nominal_height_mm": D("1000.00")}
    }
    with as_user(users["OWNER"]):
        reset = measurement.measurement_fields_for_save(
            org, data=changed_dims, current=row, system_id=row["system_id"]
        )
    assert reset["measurement_state"] == "SITE_RECTIFIED"
    assert reset["measurement_confirmed_at"] is None


def test_measurement_preview_endpoint_semantics(documentary_tenant) -> None:  # noqa: F811 — fixture inyectada
    """El preview del editor resuelve vía motor: desglose y avisos sin persistir."""
    org, _, users, _ = documentary_tenant
    with as_user(users["OWNER"]):
        out = measurement.resolve_measurement_preview(
        org,
        system_id=_demo_system_id(users["OWNER"]),
        vano_payload={
            "width_points_mm": ["1520.00", "1500.00", "1502.00"],
            "height_points_mm": ["1220.00"],
            "wall_type": "PARTITION",
        },
        mounting_rule_id=_rule_id(users["OWNER"]),
        lock_payload=None,
        position_width_mm=D("1480.00"),
        position_height_mm=D("1200.00"),
    )
    resolution = out["resolution"]
    assert resolution["fabrication_width_mm"] == "1480.00"
    assert resolution["used_width_mm"] == "1500.00"
    codes = {w["code"] for w in resolution["warnings"]}
    assert "VANO_WIDTH_SPREAD" in codes
    # PARTITION tiene nota de muro en la regla EN_VANO sembrada.
    assert any(w["code"] == "WALL_NOTE" for w in resolution["warnings"])

    with pytest.raises(ContractAPIException) as missing, as_user(users["OWNER"]):
        measurement.resolve_measurement_preview(
            org,
            system_id=_demo_system_id(users["OWNER"]),
            vano_payload={"width_points_mm": ["1520.00"], "height_points_mm": ["1220.00"]},
            mounting_rule_id=None,
            lock_payload=None,
            position_width_mm=None,
            position_height_mm=None,
        )
    assert missing.value.contract_code == "mounting_rule_required"


def _demo_system_id(user: UUID) -> UUID:
    with as_user(user), commercial_backend():
        row = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")
    return UUID(str(row["id"]))
