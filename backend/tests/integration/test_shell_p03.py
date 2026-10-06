"""P03 e2e — búsqueda global por código humano (encargo §criterios).

La promesa del shell: escribir un código legible — proyecto `P-`, orden de
compra `OC-`/`PO-`, OT `OT-`, retazo — o el nombre de un cliente resuelve a
la entidad, bajo el contexto RLS del miembro igual que la vista lo llama.

Los retazos no mintean un código `RT-` propio: su identidad legible es el
rack, el material, la nota de etiqueta y el SKU del artículo origen; la
búsqueda los encuentra por cualquiera de esos campos.
"""

from uuid import UUID

import pytest
from django.db import transaction

from documents.repository import one
from search.service import search
from tests.integration.test_shot09_documentary import (
    as_user,
    documentary_tenant as documentary_tenant,
)

pytestmark = pytest.mark.rls_integration

_PROJECT_CODE = "P-000012"
_PO_CODE = "OC-000003"
_OT_CODE = "OT-P-000005-REV-A-03"
_REMNANT_TAG = "RT-000045"
_CLIENT_NAME = "Inmobiliaria Alerce"


@pytest.fixture
def search_seed(documentary_tenant):
    """Un proyecto, dos órdenes (OC de proveedor + OT de taller), un retazo
    etiquetado y un cliente — solo lo que la búsqueda tiene que encontrar."""
    org, other, users, other_user = documentary_tenant
    with transaction.atomic():
        project_id = UUID(
            str(
                one(
                    "INSERT INTO public.projects(org_id,code,name,client_name,created_by)"
                    " VALUES(%s,%s,%s,%s,%s) RETURNING id",
                    [
                        org,
                        _PROJECT_CODE,
                        "Edificio Prat",
                        _CLIENT_NAME,
                        users["OWNER"],
                    ],
                )["id"]
            )
        )
        for order_type, code, status in (
            ("SUPPLIER_PROFILE_PO", _PO_CODE, "SENT"),
            ("WORKSHOP_OT", _OT_CODE, "IN_PROGRESS"),
        ):
            one(
                "INSERT INTO public.orders(org_id,project_id,order_type,order_code,"
                "status,payload_json) VALUES(%s,%s,%s::order_type,%s,%s::order_status,'{}')"
                " RETURNING id",
                [org, project_id, order_type, code, status],
            )
        one(
            "INSERT INTO public.inventory_remnants(org_id,kind,sheet_workshop_sku,"
            "width_mm,height_mm,rack_location,notes)"
            " VALUES(%s,'SHEET','VIDRIO-BASE',600,400,'V-02',%s) RETURNING id",
            [org, f"Retazo vidrio float — etiqueta {_REMNANT_TAG} (fixture)"],
        )
        one(
            "INSERT INTO public.clients(org_id,name,rut,created_by)"
            " VALUES(%s,%s,%s,%s) RETURNING id",
            [org, _CLIENT_NAME, "76.111.222-3", users["OWNER"]],
        )
        # Filas gemelas del OTRO tenant con el mismo texto: nunca deben salir
        # en la búsqueda del fixture aunque el patrón coincida.
        one(
            "INSERT INTO public.projects(org_id,code,name,created_by)"
            " VALUES(%s,%s,%s,%s) RETURNING id",
            [other, _PROJECT_CODE, "Edificio Prat (otra org)", other_user],
        )
        one(
            "INSERT INTO public.inventory_remnants(org_id,kind,sheet_workshop_sku,"
            "width_mm,height_mm,notes) VALUES(%s,'SHEET','GL-EXTERNO',600,400,%s)"
            " RETURNING id",
            [other, f"Retazo ajeno — etiqueta {_REMNANT_TAG}"],
        )
        yield org, other, users


def test_search_finds_every_human_code(search_seed):
    """El criterio literal del encargo: cada código de la lista resuelve a
    su grupo, y el cliente se encuentra por nombre."""
    org, _, users = search_seed
    with as_user(users["ESTIMATOR"]):
        cases = {
            _PROJECT_CODE: ("projects", _PROJECT_CODE),
            _PO_CODE: ("orders", _PO_CODE),
            _REMNANT_TAG: ("remnants", "Retazo"),
            _OT_CODE: ("orders", _OT_CODE),
            "Alerce": ("clients", _CLIENT_NAME),
        }
        for needle, (group, expected) in cases.items():
            results = search(org, needle)["results"]
            assert any(
                item["group"] == group and expected in str(item["title"])
                for item in results
            ), (needle, [str(item["title"]) for item in results])


def test_search_stays_inside_the_tenant(search_seed):
    """Mismo texto en dos tenants: el miembro solo ve lo suyo — el filtro
    de org corre además del contexto RLS que levanta ``as_user``. Los
    retazos del otro tenant llevan un SKU distinto para que cualquier
    mezcla sea detectable."""
    org, other, users = search_seed
    with as_user(users["ESTIMATOR"]):
        mine = search(org, _REMNANT_TAG)["results"]
        mine_projects = search(org, "Prat")["results"]
        # El usuario no pertenece a `other`: aunque consulte ese org
        # explícito, nunca debe aparecer una fila del fixture local.
        cross = search(other, _REMNANT_TAG)["results"]
    assert any(
        item["group"] == "remnants" and "VIDRIO-BASE" in str(item["title"])
        for item in mine
    )
    assert all("GL-EXTERNO" not in str(item["title"]) for item in mine)
    assert all("otra org" not in str(item["title"]) for item in mine_projects)
    assert any(
        item["title"] == f"{_PROJECT_CODE} · Edificio Prat"
        for item in mine_projects
    )
    assert all("VIDRIO-BASE" not in str(item["title"]) for item in cross)


def test_installer_never_sees_commercial_groups(search_seed):
    """El mismo rol que ve la OT en Hoy no puede listar clientes ni
    retazos de inventario por búsqueda — el grupo se recorta antes de
    devolver."""
    org, _, users = search_seed
    with as_user(users["INSTALLER"]):
        for needle in ("Alerce", _REMNANT_TAG):
            results = search(org, needle, role="INSTALLER")["results"]
            assert all(
                item["group"] not in {"clients", "remnants", "inventory"}
                for item in results
            )
        # Pero sí encuentra la OT que va a instalar.
        ot = search(org, _OT_CODE, role="INSTALLER")["results"]
        assert any(
            item["group"] == "orders" and _OT_CODE in str(item["title"])
            for item in ot
        )
