"""P18 — cumplimiento térmico OGUC 4.1.10 sobre la pila real.

Los veredictos salen del motor con las autoridades declaradas: VERIFIED
(sello técnico) permite COMPLIES; DECLARED que cumple queda en
INSUFFICIENT_DATA; DEMO nunca afirma cumplimiento — la regla de honestidad
del encargo se prueba aquí contra Postgres real, no con mocks.
"""

from decimal import Decimal as D
from uuid import uuid4

import pytest

from authentication.rls import catalog_backend
from backend.tests.integration.catalog_fixture import copy_fixed_catalog
from backend.tests.integration.test_shot09_documentary import (
    as_user,
    documentary_tenant as documentary_tenant,
)
from pricing.repository import json_text, one
from projects import thermal

pytestmark = pytest.mark.rls_integration

_TREE = {
    "id": "B1",
    "type": "BAY",
    "opening_type": "FIXED",
    "glass_spec": "4-16-4 Float Incoloro",
    "glass_thickness_mm": "24.00",
    "glass_article_sku": "VIDRIO-BASE",
}


def _seed_project(org, owner, system_id, *, zone="E", orientation="N", wall_areas=None):
    project_id = one(
        "INSERT INTO public.projects(org_id,code,name,client_name,client_rut,"
        "thermal_zone,thermal_use,thermal_wall_areas,created_by) "
        "VALUES(%s,%s,%s,%s,%s,%s,'RESIDENTIAL',%s::jsonb,%s) RETURNING id",
        [
            org,
            f"P-{uuid4().hex[:8]}",
            "Térmico",
            "Cliente Térmico",
            "2-7",
            zone,
            json_text(wall_areas or {}),
            owner,
        ],
    )["id"]
    position_id = one(
        "INSERT INTO public.project_positions(org_id,project_id,position_index,"
        "location_tag,quantity,typology,system_id,width_mm,height_mm,"
        "color_interior,color_exterior,parametric_tree,bom_snapshot,"
        "thermal_orientation) "
        "VALUES(%s,%s,1,'Fachada',1,'FIXED',%s,2400,1800,'WHITE','WHITE',"
        "%s::jsonb,'{}'::jsonb,%s) RETURNING id",
        [org, project_id, system_id, json_text(_TREE), orientation],
    )["id"]
    return project_id, position_id


def _write_thermal(org, system_id, user, *, verified=True):
    """Autoridades térmicas declaradas: Ψ del separador, Uf por grupo, Ug del
    vidrio (system_id NULL = aplica a todo sistema de la org) e informe de
    ensayo. ``verified`` estampa el sello técnico — exige rol revisor."""
    stamp_at = user if verified else None
    with as_user(user), catalog_backend():
        one(
            "INSERT INTO public.glazing_spacers(id,org_id,code,name,"
            "psi_w_m_k,data_provenance,technical_reviewed_at,"
            "technical_reviewed_by) VALUES(%s,%s,'ALUMINIUM','Separador "
            "aluminio','0.06','MANUAL',%s,%s) RETURNING id",
            [
                uuid4(),
                org,
                "2024-03-12T00:00:00Z" if verified else None,
                str(stamp_at) if stamp_at else None,
            ],
        )
        one(
            "INSERT INTO public.system_frame_uf(id,org_id,system_id,"
            "member_group,uf_w_m2k,source_ref,data_provenance,"
            "technical_reviewed_at,technical_reviewed_by) "
            "VALUES(%s,%s,%s,'ALL','1.4','Informe UF-2024/01',"
            "'MANUAL',%s,%s) RETURNING id",
            [
                uuid4(),
                org,
                system_id,
                "2024-03-12T00:00:00Z" if verified else None,
                str(stamp_at) if stamp_at else None,
            ],
        )
        one(
            "INSERT INTO public.system_performance_tests(id,org_id,"
            "system_id,air_class,water_class,wind_class,report_ref,"
            "laboratory,tested_on,tested_width_mm,tested_height_mm,"
            "data_provenance,technical_reviewed_at,"
            "technical_reviewed_by) VALUES(%s,%s,%s,3,'E750','C3',"
            "'INF-2024/118','IDIEM','2024-03-12',2500,2500,"
            "'MANUAL',%s,%s) RETURNING id",
            [
                uuid4(),
                org,
                system_id,
                "2024-03-12T00:00:00Z" if verified else None,
                str(stamp_at) if stamp_at else None,
            ],
        )
        one(
            "INSERT INTO public.glass_products(id,org_id,system_id,sku,"
            "commercial_name,notation,composition,ug_w_m2k,g_value,"
            "min_billable_area_m2,data_provenance,technical_reviewed_at,"
            "technical_reviewed_by) VALUES(%s,%s,NULL,'VIDRIO-BASE',"
            "'Termopanel 4-16-4','4-16-4 Float Incoloro',"
            '\'{"layers":[{"type":"lamina","panes":["4"],'
            '"interlayer":null,"tint":"CLEAR","treatment":null,'
            '"coating":null,"coating_face":null,"supplier_sku":null},'
            '{"type":"chamber","width_mm":"16","gas":"AIR",'
            '"spacer":"ALUMINIUM","sealant":null},'
            '{"type":"lamina","panes":["4"],"interlayer":null,'
            '"tint":"CLEAR","treatment":null,"coating":null,'
            '"coating_face":null,"supplier_sku":null}]}\'::jsonb,'
            "'1.100','0.700','0.30','MANUAL',%s,%s) RETURNING id",
            [
                uuid4(),
                org,
                "2024-03-12T00:00:00Z" if verified else None,
                str(stamp_at) if stamp_at else None,
            ],
        )


def test_p18_complies_with_verified_authorities(documentary_tenant):
    """Zona E, orientación N, aire clase 3 ≥ 2 y Uw ≤ 5,8: con todo VERIFIED
    el panel veredicta COMPLIES."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    # 4,32 m² de vano sobre 10 m² de paramento N = 43,2 % ≤ 85 % (Tabla 3).
    project_id, _ = _seed_project(org, users["OWNER"], system_id, wall_areas={"N": "10.0"})
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=True)
    with as_user(users["OWNER"]):
        panel = thermal.project_thermal(org, project_id)
    assert panel["verdict"] == "COMPLIES"
    row = panel["positions"][0]
    assert row["thermal"]["verdict"] == "COMPLIES"
    uw = row["thermal"]["uw"]
    assert uw["status"] == "OK"
    assert D(uw["uw_w_m2k"]) > D("0")
    assert uw["authority"] == "VERIFIED"
    assert row["thermal"]["classes"]["air_class"] == 3
    assert row["thermal"]["classes"]["authority"] == "VERIFIED"


def test_p18_declared_only_never_complies(documentary_tenant):
    """Los mismos valores sin sello técnico: Uw calcula, pero el veredicto
    queda INSUFFICIENT_DATA — cumplir exige datos certificados."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    project_id, _ = _seed_project(org, users["OWNER"], system_id)
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=False)
    with as_user(users["OWNER"]):
        panel = thermal.project_thermal(org, project_id)
    row = panel["positions"][0]
    assert row["thermal"]["verdict"] == "INSUFFICIENT_DATA"
    assert row["thermal"]["uw"]["status"] == "OK"


def test_p18_demo_system_never_verdicts(documentary_tenant):
    """DEMO_60 (is_demo) con datos idénticos: el contrato de autoridad
    impide que un catálogo de muestra veredicta cumplimiento."""
    org, _, users, _ = documentary_tenant
    system_id = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")["id"]
    project_id, _ = _seed_project(org, users["OWNER"], system_id)
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=True)
    with as_user(users["OWNER"]):
        panel = thermal.project_thermal(org, project_id)
    assert panel["positions"][0]["thermal"]["verdict"] == "INSUFFICIENT_DATA"


def test_p18_missing_inputs_stay_unknown(documentary_tenant):
    """Sin Uf ni Ug declarados: Uw UNKNOWN con los faltantes listados y el
    veredicto INSUFFICIENT_DATA — nunca un número al vuelo."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    project_id, _ = _seed_project(org, users["OWNER"], system_id)
    with as_user(users["OWNER"]):
        panel = thermal.project_thermal(org, project_id)
    row = panel["positions"][0]
    assert row["thermal"]["uw"]["status"] == "UNKNOWN"
    codes = {item["code"] for item in row["thermal"]["uw"]["missing"]}
    assert "UF" in codes
    assert row["thermal"]["verdict"] == "INSUFFICIENT_DATA"


def test_p18_orientation_pct_gate(documentary_tenant):
    """% de paramentos por orientación: sin superficie declarada el gate es
    WALL_AREA_MISSING; declarada, compara contra la Tabla 3."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    project_id, _ = _seed_project(org, users["OWNER"], system_id)
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=True)
    with as_user(users["OWNER"]):
        without = thermal.project_thermal(org, project_id)
        assert without["orientations"]
        north = next(item for item in without["orientations"] if item["orientation"] == "N")
        assert north["verdict"] == "INSUFFICIENT_DATA"
        assert "WALL_AREA_MISSING" in {cause["code"] for cause in north["causes"]}
        # 5 m² de paramento con 4,32 m² de ventana = 86,4 % > toda Tabla 3
        # zona E/Norte (máx. 62 %).
        one(
            "UPDATE public.projects SET thermal_wall_areas=%s::jsonb WHERE id=%s RETURNING id",
            ['{"N": "5.0"}', project_id],
        )
        with_wall = thermal.project_thermal(org, project_id)
        north = next(item for item in with_wall["orientations"] if item["orientation"] == "N")
        assert north["verdict"] == "FAILS"


def test_p18_no_zone_no_verdict(documentary_tenant):
    """Proyecto sin zona declarada: la posición evalúa Uw pero el veredicto
    es INSUFFICIENT_DATA por ZONE ausente — la zona es elección del usuario."""
    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    project_id, _ = _seed_project(org, users["OWNER"], system_id, zone=None)
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=True)
    with as_user(users["OWNER"]):
        panel = thermal.project_thermal(org, project_id)
    assert panel["positions"][0]["thermal"]["verdict"] == "INSUFFICIENT_DATA"
    assert panel["orientations"] == []


def test_p18_alternatives_survive_pricing_denial(documentary_tenant):
    """RLS: ESTIMATOR no lee ``pricing_rules`` — el §8 devuelve las
    alternativas con Δ «Sin dato» en lugar de tumbar la vista con un 422."""
    from projects.views import _thermal_price_lookup

    org, _, users, _ = documentary_tenant
    system_id = copy_fixed_catalog(org)
    _, position_id = _seed_project(org, users["OWNER"], system_id, wall_areas={"N": "20.0"})
    _write_thermal(org, system_id, users["WORKSHOP_MANAGER"], verified=True)
    with catalog_backend():
        one(
            "UPDATE public.glass_products SET ug_w_m2k='5.500' "
            "WHERE org_id=%s AND sku='VIDRIO-BASE' RETURNING id",
            [org],
        )
        one(
            "INSERT INTO public.glass_products(id,org_id,system_id,sku,"
            "commercial_name,notation,composition,ug_w_m2k,g_value,"
            "min_billable_area_m2,data_provenance,technical_reviewed_at,"
            "technical_reviewed_by) VALUES(%s,%s,NULL,'VIDRIO-ALT',"
            "'Termopanel DVH 4-16-4','4-16-4 DVH',"
            '\'{"layers":[{"type":"lamina","panes":["4"],'
            '"interlayer":null,"tint":"CLEAR","treatment":null,'
            '"coating":null,"coating_face":null,"supplier_sku":null},'
            '{"type":"chamber","width_mm":"16","gas":"AIR",'
            '"spacer":"ALUMINIUM","sealant":null},'
            '{"type":"lamina","panes":["4"],"interlayer":null,'
            '"tint":"CLEAR","treatment":null,"coating":null,'
            '"coating_face":null,"supplier_sku":null}]}\'::jsonb,'
            "'0.600','0.600','0.30','MANUAL','2024-03-12T00:00:00Z',%s)"
            " RETURNING id",
            [uuid4(), org, str(users["WORKSHOP_MANAGER"])],
        )
    with as_user(users["ESTIMATOR"]):
        payload = thermal.thermal_alternatives(
            org_id=org,
            position_id=position_id,
            price_lookup=_thermal_price_lookup(org),
        )
    assert payload["alternatives"], "se esperaba el candidato VIDRIO-ALT"
    assert all(item["price_delta_net"] is None for item in payload["alternatives"])
