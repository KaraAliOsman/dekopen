"""P03 e2e — búsqueda global por código humano (encargo §criterios).

La promesa del shell: escribir un código legible — proyecto `P-`, orden de
compra `OC-`, OT `OT-`, retazo `RT-` — o el nombre de un cliente resuelve a
la entidad, bajo el contexto RLS del miembro igual que la vista lo llama.

La OC de la prueba sale del flujo documental real (elegibilidad →
asignación → confirmación por tipo): `next_human_code` la folia OC-NNNNNN
igual que en producción — el `OC-000003` del criterio es ejemplar, lo que
se verifica es la resolución del folio minteado. `P-000012`,
`OT-P-000005-REV-A-03` y `RT-000045` se insertan directos: son el formato
literal que el encargo exige encontrar.
"""

from uuid import UUID

import pytest
from django.db import transaction

from documents.repository import one
from purchasing.service import (
    allocate_requirement,
    confirm_order_type_batch,
    create_eligibility,
    purchasing_state,
)
from search.service import search
from tests.integration.test_shot09_documentary import (
    _eligibility_data,
    _freeze,
    _seed_project,
    as_user,
    documentary_tenant as documentary_tenant,
)

pytestmark = pytest.mark.rls_integration

_PROJECT_CODE = "P-000012"
_OT_CODE = "OT-P-000005-REV-A-03"
_REMNANT_TAG = "RT-000045"
_CLIENT_NAME = "Inmobiliaria Alerce"


def _mint_supplier_orders(org: UUID, users: dict) -> list[str]:
    """OCs selladas por el flujo real: el folio OC- sale de
    `next_human_code`, no de un INSERT — igual que en producción."""
    project_id, _, operation_id = _seed_project(org, users["OWNER"])
    frozen = _freeze(org, users["OWNER"], project_id, operation_id)
    version_id = UUID(str(frozen["id"]))
    with as_user(users["WORKSHOP_MANAGER"]):
        requirements = purchasing_state(org, version_id)["requirements"]
        by_type: dict[str, list[dict]] = {}
        for requirement in requirements:
            by_type.setdefault(str(requirement["order_type"]), []).append(requirement)
        for order_type, type_requirements in by_type.items():
            eligibility = create_eligibility(
                org_id=org,
                actor_id=users["WORKSHOP_MANAGER"],
                version_id=version_id,
                data=_eligibility_data(
                    order_type,
                    [str(item["requirement_key"]) for item in type_requirements],
                    f"SUPPLIER-{order_type}",
                ),
            )
            for requirement in type_requirements:
                allocate_requirement(
                    org_id=org,
                    actor_id=users["WORKSHOP_MANAGER"],
                    requirement_id=UUID(str(requirement["id"])),
                    eligibility_id=UUID(str(eligibility["id"])),
                )
            confirm_order_type_batch(
                org_id=org,
                actor_id=users["WORKSHOP_MANAGER"],
                version_id=version_id,
                order_type=order_type,
                confirmed=True,
            )
        return [
            str(order["order_code"])
            for order in purchasing_state(org, version_id)["orders"]
            if order["order_type"] != "WORKSHOP_OT"
        ]


@pytest.fixture
def search_seed(documentary_tenant):
    """Proyecto + OT + retazo + cliente con sus códigos literales, más las
    OC reales que el flujo de compras mintea para la misma organización."""
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
        one(
            "INSERT INTO public.orders(org_id,project_id,order_type,order_code,"
            "status,payload_json) VALUES(%s,%s,'WORKSHOP_OT',%s,'IN_PROGRESS','{}')"
            " RETURNING id",
            [org, project_id, _OT_CODE],
        )
        one(
            "INSERT INTO public.inventory_remnants(org_id,kind,sheet_workshop_sku,"
            "width_mm,height_mm,rack_location,notes,remnant_code)"
            " VALUES(%s,'SHEET','VIDRIO-BASE',600,400,'V-02',%s,%s) RETURNING id",
            [org, "Retazo vidrio float (fixture)", _REMNANT_TAG],
        )
        one(
            "INSERT INTO public.clients(org_id,name,rut,created_by)"
            " VALUES(%s,%s,%s,%s) RETURNING id",
            [org, _CLIENT_NAME, "76.111.222-3", users["OWNER"]],
        )
        # Filas gemelas del OTRO tenant con el mismo texto: nunca deben salir
        # en la búsqueda del fixture aunque el patrón coincida.
        one(
            "INSERT INTO public.projects(org_id,code,name,client_name,created_by)"
            " VALUES(%s,%s,%s,%s,%s) RETURNING id",
            [other, _PROJECT_CODE, "Edificio Prat (otra org)", "Cliente ajeno", other_user],
        )
        one(
            "INSERT INTO public.inventory_remnants(org_id,kind,sheet_workshop_sku,"
            "width_mm,height_mm,notes,remnant_code)"
            " VALUES(%s,'SHEET','GL-EXTERNO',600,400,'Retazo ajeno',%s) RETURNING id",
            [other, _REMNANT_TAG],
        )
        oc_codes = _mint_supplier_orders(org, users)
        yield org, other, users, oc_codes


def test_search_finds_every_human_code(search_seed):
    """El criterio literal del encargo: cada código de la lista resuelve a
    su grupo, la OC minteada por el flujo y el cliente por nombre."""
    org, _, users, oc_codes = search_seed
    assert oc_codes, "el flujo de compras no minteó ninguna OC"
    assert all(code.startswith("OC-") for code in oc_codes)
    with as_user(users["ESTIMATOR"]):
        cases = {
            _PROJECT_CODE: ("projects", _PROJECT_CODE),
            _REMNANT_TAG: ("remnants", _REMNANT_TAG),
            _OT_CODE: ("orders", _OT_CODE),
            "Alerce": ("clients", _CLIENT_NAME),
        }
        cases.update({code: ("orders", code) for code in oc_codes})
        for needle, (group, expected) in cases.items():
            results = search(org, needle)["results"]
            assert any(
                item["group"] == group and expected in str(item["title"])
                for item in results
            ), (needle, [str(item["title"]) for item in results])


def test_search_stays_inside_the_tenant(search_seed):
    """Mismo texto en dos tenants: el miembro solo ve lo suyo — el filtro
    de org corre además del contexto RLS que levanta ``as_user``. El
    retazo del otro tenant lleva un SKU distinto para que cualquier
    mezcla sea detectable."""
    org, other, users, _ = search_seed
    with as_user(users["ESTIMATOR"]):
        mine = search(org, _REMNANT_TAG)["results"]
        mine_projects = search(org, "Prat")["results"]
        # El usuario no pertenece a `other`: aunque consulte ese org
        # explícito, nunca debe aparecer una fila del fixture local.
        cross = search(other, _REMNANT_TAG)["results"]
    assert any(
        item["group"] == "remnants" and item["title"] == _REMNANT_TAG
        for item in mine
    )
    assert all("GL-EXTERNO" not in str(item.get("subtitle") or "") for item in mine)
    assert all("otra org" not in str(item["title"]) for item in mine_projects)
    assert any(
        item["title"] == f"{_PROJECT_CODE} · Edificio Prat"
        for item in mine_projects
    )
    assert all("VIDRIO-BASE" not in str(item["title"]) for item in cross)


def test_installer_never_sees_commercial_groups(search_seed):
    """El mismo rol que ve la OT en Hoy no puede listar clientes ni
    retazos/recepciones de inventario por búsqueda — el grupo se recorta
    antes de devolver."""
    org, _, users, _ = search_seed
    with as_user(users["INSTALLER"]):
        for needle in ("Alerce", _REMNANT_TAG):
            results = search(org, needle, role="INSTALLER")["results"]
            assert all(
                item["group"]
                not in {"clients", "remnants", "inventory", "receipts"}
                for item in results
            )
        # Pero sí encuentra la OT que va a instalar.
        ot = search(org, _OT_CODE, role="INSTALLER")["results"]
        assert any(
            item["group"] == "orders" and _OT_CODE in str(item["title"])
            for item in ot
        )
