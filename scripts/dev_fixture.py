#!/usr/bin/env python3
"""Documented realistic DEMO fixtures for DEKOPEN local development.

Creates two demo orgs, one account per role in the primary org, commercial
prerequisites (pricing rules + a cost list covering every reference-catalog
purchase SKU), six clients, and projects that exercise the product breadth.

  VIVIENDA  — a house: several positions, one priced-and-emitted path capable
  OBRA      — a larger works order: more positions, quantities > 1
  INCOMPLETA — a position saved but deliberately left unpriced (draft flow)

Everything written here is DEMONSTRATION data — it feeds the DEMO_60 reference
family, whose fabrication authority is intentionally incomplete (quote-only).
Fabrication-enabled catalogs need real manufacturer data; this fixture never
fabricates authority.

Usage (stack running: `make test-db`'s supabase + Django + Vite):
    SUPABASE_SERVICE_ROLE_KEY=... python scripts/dev_fixture.py

Env: SUPABASE_URL (default http://127.0.0.1:25321),
     SUPABASE_SERVICE_ROLE_KEY (required), DJANGO_URL (default :8000),
     DATABASE_URL (default local supabase db — pricing writes are
     audit-gated for REST and use the privileged maintenance path).
Idempotent: deterministic ids upserted on every run.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from decimal import Decimal

import httpx
import psycopg

SUPA = os.environ.get("SUPABASE_URL", "http://127.0.0.1:25321").rstrip("/")
DJANGO = os.environ.get("DJANGO_URL", "http://127.0.0.1:8000").rstrip("/")
DB = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:25322/postgres"
)
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SERVICE_KEY:
    sys.exit("SUPABASE_SERVICE_ROLE_KEY is required (supabase status -o env)")

NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://dekopen.local/dev-fixture")
ORG_ID = str(uuid.uuid5(NS, "org"))
ORG_NAME = "Ventanas del Sur SpA"
ORG_B_ID = str(uuid.uuid5(NS, "org-secondary"))
ORG_B_NAME = "Cristales Bio Bio Ltda."

ACCOUNTS = [
    ("owner", "demo-owner@fixture.dekopen.local", "OWNER"),
    ("estimator", "demo-estimator@fixture.dekopen.local", "ESTIMATOR"),
    ("manager", "demo-manager@fixture.dekopen.local", "WORKSHOP_MANAGER"),
    ("operator", "demo-operator@fixture.dekopen.local", "OPERATOR"),
    ("installer", "demo-installer@fixture.dekopen.local", "INSTALLER"),
]
PASSWORD = "Demo-Fixture-2026!"

SVC = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation",
}

DEMO_60 = "3067da09-3119-5ad0-a1d5-498cd2dfd753"


def rest(path: str, rows: list[dict]) -> list[dict]:
    response = httpx.post(
        f"{SUPA}/rest/v1/{path}", headers=SVC, json=rows, timeout=15
    )
    if response.status_code >= 300:
        sys.exit(f"POST {path} -> {response.status_code}: {response.text[:400]}")
    return response.json() if response.text else []


def sql(statement: str, params: tuple | None = None) -> None:
    # Pricing/audit-gated tables reject actorless REST writes; direct SQL
    # (session_user postgres) is the audited privileged-maintenance path.
    with psycopg.connect(DB, autocommit=True) as connection:
        connection.execute(statement, params)


def query(path: str) -> list[dict]:
    response = httpx.get(f"{SUPA}/rest/v1/{path}", headers=SVC, timeout=15)
    if response.status_code >= 300:
        sys.exit(f"GET {path} -> {response.status_code}: {response.text[:400]}")
    return response.json()


def auth_admin(method: str, path: str, body: dict | None = None) -> httpx.Response:
    # GoTrue's admin endpoints sporadically return a spurious bad_jwt 403 on
    # this build; retry a few times before surfacing.
    for attempt in range(4):
        response = httpx.request(
            method,
            f"{SUPA}/auth/v1{path}",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            json=body,
            timeout=15,
        )
        if response.status_code != 403 or attempt == 3:
            return response
    return response


def user_by_email(email: str) -> dict | None:
    response = auth_admin("GET", "/admin/users")
    if response.status_code != 200:
        sys.exit(
            f"admin users -> {response.status_code}: {response.text[:200]}"
        )
    data = response.json()
    users = data.get("users", data) if isinstance(data, dict) else data
    if not isinstance(users, list):
        return None
    return next(
        (u for u in users if isinstance(u, dict) and u.get("email") == email),
        None,
    )


def ensure_user(key: str, email: str) -> str:
    existing = user_by_email(email)
    if existing:
        return existing["id"]
    response = auth_admin(
        "POST",
        "/admin/users",
        {
            "email": email,
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"fixture": "dekopen-demo"},
        },
    )
    if response.status_code >= 300:
        sys.exit(f"create user {email}: {response.status_code} {response.text[:300]}")
    return response.json()["id"]


def login(email: str) -> str:
    response = httpx.post(
        f"{SUPA}/auth/v1/token?grant_type=password",
        headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": PASSWORD},
        timeout=15,
    )
    if response.status_code >= 300:
        sys.exit(f"login {email}: {response.status_code} {response.text[:300]}")
    return response.json()["access_token"]


def api(token: str, method: str, path: str, payload: dict | None = None) -> dict:
    response = httpx.request(
        method,
        f"{DJANGO}/api/v1{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": ORG_ID,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code >= 300:
        sys.exit(
            f"{method} {path} -> {response.status_code}: {response.text[:500]}"
        )
    return response.json()


def design(width: str, height: str, tree: dict) -> dict:
    return {
        "system_id": DEMO_60,
        "nominal_width_mm": width,
        "nominal_height_mm": height,
        "color": "WHITE",
        "parametric_tree": tree,
    }


def fixed(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width,
        height,
        {
            "id": uid,
            "type": "BAY",
            "opening_type": "FIXED",
            "glass_thickness_mm": "24.00",
            "glass_spec": "4-16-4 Float Incoloro",
            "glass_article_sku": "VIDRIO-BASE",
        },
    )


def tilt_turn(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width,
        height,
        {
            "id": uid,
            "type": "SPLIT_V",
            "split_offset_mm": str(Decimal(width) / 2),
            "mullion_profile_sku": "POSTE-V",
            "children": [
                {
                    "id": f"{uid}-a",
                    "type": "BAY",
                    "opening_type": "FIXED",
                    "glass_thickness_mm": "24.00",
                    "glass_spec": "4-16-4 Float Incoloro",
                    "glass_article_sku": "VIDRIO-BASE",
                },
                {
                    "id": f"{uid}-b",
                    "type": "BAY",
                    "opening_type": "TILT_TURN_RIGHT",
                    "glass_thickness_mm": "24.00",
                    "glass_spec": "4-16-4 Float Incoloro",
                    "glass_article_sku": "VIDRIO-BASE",
                },
            ],
        },
    )


def bay(width: str, height: str, opening: str, uid: str = "m1") -> dict:
    return design(
        width,
        height,
        {
            "id": uid,
            "type": "BAY",
            "opening_type": opening,
            "glass_thickness_mm": "24.00",
            "glass_spec": "4-16-4 Float Incoloro",
            "glass_article_sku": "VIDRIO-BASE",
        },
    )


def main() -> None:
    users = {key: ensure_user(key, email) for key, email, _ in ACCOUNTS}

    rest(
        "tenancy_organizations",
        [
            {
                "id": ORG_ID,
                "name": ORG_NAME,
                "commercial_name": ORG_NAME,
                "tax_id": "76.543.210-3",
                "giro": "Fabricacion e instalacion de ventanas de PVC y aluminio",
                "brand_address": "Paicavi 1250, Concepcion",
                "brand_phone": "+56 41 255 0198",
                "brand_email": "contacto@ventanasdelsur.example",
                "brand_logo_key": "fixture/ventanas-del-sur.svg",
                "brand_logo_sha256": "0" * 64,
                "country": "CL",
                "currency": "CLP",
                "subscription_active": True,
            },
            {
                "id": ORG_B_ID,
                "name": ORG_B_NAME,
                "commercial_name": ORG_B_NAME,
                "tax_id": "77.123.456-9",
                "giro": "Comercializacion de cristales y termopaneles",
                "brand_address": "Los Carrera 840, Talcahuano",
                "brand_phone": "+56 41 233 4411",
                "brand_email": "operaciones@cristalesbiobio.example",
                "brand_logo_key": "fixture/cristales-bio-bio.svg",
                "brand_logo_sha256": "1" * 64,
                "country": "CL",
                "currency": "CLP",
                "subscription_active": True,
            }
        ],
    )
    rest(
        "tenancy_memberships",
        [
            {
                "id": str(uuid.uuid5(NS, f"membership-{key}")),
                "org_id": ORG_ID,
                "user_id": users[key],
                "role": role,
                "is_active": True,
            }
            for key, _, role in ACCOUNTS
        ]
        + [
            {
                "id": str(uuid.uuid5(NS, "membership-secondary-owner")),
                "org_id": ORG_B_ID,
                "user_id": users["owner"],
                "role": "OWNER",
                "is_active": True,
            }
        ],
    )

    rules_id = str(uuid.uuid5(NS, "pricing-rules"))
    sql(
        "INSERT INTO public.pricing_rules(id,org_id,pricing_mode,"
        "default_margin_pct,tax_rate_pct,waste_factor_pct,"
        "labor_rate_per_m2,installation_rate_per_m2) "
        "VALUES(%s,%s,'COST_PLUS_MARGIN',0.35,0.19,0.08,15000,12000) "
        "ON CONFLICT (id) DO NOTHING",
        (rules_id, ORG_ID),
    )
    cost_list_id = str(uuid.uuid5(NS, "cost-list"))
    sql(
        "INSERT INTO public.cost_lists(id,org_id,supplier_name,currency,"
        "valid_from,is_active) "
        "VALUES(%s,%s,'Proveedor de referencia (fixture)','CLP','2026-01-01',TRUE) "
        "ON CONFLICT (id) DO NOTHING",
        (cost_list_id, ORG_ID),
    )

    skus: dict[tuple[str, str], str] = {}
    for row in query(
        "profile_purchase_mappings?select=commercial_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["commercial_sku"], row["purchase_unit"])] = "PROFILE"
    for row in query(
        "reinforcement_articles?select=commercial_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["commercial_sku"], row["purchase_unit"])] = "STEEL"
    for row in query(
        "hardware_purchase_mappings?select=purchasing_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["purchasing_sku"], row["purchase_unit"])] = "KIT"
    for row in query("hardware_kits?select=sku&org_id=is.null"):
        skus[(row["sku"], "KIT")] = "KIT"
    for row in query(
        "glass_purchase_mappings?select=purchasing_sku,technical_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["purchasing_sku"], row["purchase_unit"])] = "GLASS"
        skus[(row["technical_sku"], "M2")] = "GLASS"
    for row in query(
        "panel_purchase_authorities?select=purchasing_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["purchasing_sku"], row["purchase_unit"])] = "PANEL"
    for row in query("infill_articles?select=sku&org_id=is.null"):
        skus[(row["sku"], "M2")] = "PANEL"
    for row in query(
        "fitting_purchase_mappings?select=purchasing_sku,technical_sku,purchase_unit&org_id=is.null"
    ):
        skus[(row["purchasing_sku"], row["purchase_unit"])] = "FITTING"
        skus[(row["technical_sku"], "EA")] = "FITTING"

    with psycopg.connect(DB, autocommit=True) as connection:
        for (sku, unit), item_type in sorted(skus.items()):
            connection.execute(
                "INSERT INTO public.cost_list_items(id,org_id,cost_list_id,sku,"
                "unit,item_type,unit_cost,description) "
                "VALUES(%s,%s,%s,%s,%s,'FIXTURE',100.00,'DEMO FIXTURE cost') "
                "ON CONFLICT (cost_list_id,sku) DO NOTHING",
                (str(uuid.uuid5(NS, f"cost-{sku}-{unit}")), ORG_ID, cost_list_id, sku, unit),
            )

        # Stock so the optimizer can cover a cut plan: bar SKUs keyed by their
        # physical stock identity, unit SKUs unvarianted (same seeding as the
        # golden-path integration test).
        bar_identities: list[str] = []
        for table, column in (
            ("profile_purchase_mappings", "commercial_sku"),
            ("reinforcement_articles", "commercial_sku"),
        ):
            for row in query(
                f"{table}?select={column},physical_stock_identity&org_id=is.null"
            ):
                if row.get("physical_stock_identity"):
                    bar_identities.append(
                        f"{row[column]}::{row['physical_stock_identity']}"
                    )
        unit_identities = sorted(sku for (sku, _) in skus)
        for identity in sorted({*bar_identities, *unit_identities}):
            sku, _, variant = identity.partition("::")
            item_id = str(uuid.uuid5(NS, f"stock-{identity}"))
            connection.execute(
                "INSERT INTO public.inventory_items(id,org_id,sku,name,category,"
                "unit,variant_key) VALUES(%s,%s,%s,%s,'FIXTURE','EA',%s) "
                "ON CONFLICT (org_id,sku,variant_key) DO NOTHING",
                (item_id, ORG_ID, sku, f"Fixture {sku}"[:200], variant),
            )
            existing = connection.execute(
                "SELECT 1 FROM public.inventory_movements WHERE org_id=%s "
                "AND item_id=%s AND movement_type='RECEIPT' LIMIT 1",
                (ORG_ID, item_id),
            ).fetchone()
            if not existing:
                connection.execute(
                    "INSERT INTO public.inventory_movements(org_id,item_id,"
                    "movement_type,quantity,note,actor_id) "
                    "VALUES(%s,%s,'RECEIPT',500,'fixture stock',%s)",
                    (ORG_ID, item_id, users["owner"]),
                )

    estimator = login(ACCOUNTS[1][1])

    clients = [
        (
            "Maria Paz Rojas",
            "15.678.901-1",
            "maria.rojas@example.cl",
            "+56 9 6123 4500",
            "Los Notros 1840, San Pedro de la Paz",
            "Persona natural",
            "San Pedro de la Paz",
        ),
        (
            "Constructora Rio Claro SpA",
            "76.456.789-7",
            "obras@rioclaro.example.cl",
            "+56 41 266 7788",
            "Ongolmo 533, Concepcion",
            "Construccion de edificios",
            "Concepcion",
        ),
        (
            "Inversiones Lomas Ltda.",
            "96.543.210-8",
            "administracion@lomas.example.cl",
            "+56 41 244 6611",
            "Camino a Chiguayante 3210, Chiguayante",
            "Inmobiliaria",
            "Chiguayante",
        ),
        (
            "Colegio Valle Andino",
            "76.987.654-5",
            "mantencion@valleandino.example.cl",
            "+56 41 231 5544",
            "Av. Collao 980, Concepcion",
            "Servicios educacionales",
            "Concepcion",
        ),
        (
            "Jorge Andres Vidal",
            "18.456.789-K",
            "jvidal@example.cl",
            "+56 9 7345 2281",
            "Pasaje Maiten 402, Hualpen",
            "Persona natural",
            "Hualpen",
        ),
        (
            "Clinica Puerto Sur SpA",
            "77.888.999-4",
            "infraestructura@puertosur.example.cl",
            "+56 41 287 4400",
            "Barros Arana 1220, Concepcion",
            "Servicios de salud",
            "Concepcion",
        ),
    ]
    client_ids = {}
    for name, rut, email, phone, address, giro, comuna in clients:
        cid = str(uuid.uuid5(NS, f"client-{rut}"))
        rest(
            "clients",
            [
                {
                    "id": cid,
                    "org_id": ORG_ID,
                    "name": name,
                    "rut": rut,
                    "email": email,
                    "phone": phone,
                    "address": address,
                    "giro": giro,
                    "comuna": comuna,
                    "is_active": True,
                    "created_by": users["owner"],
                }
            ],
        )
        client_ids[name] = cid

    existing_projects = api(estimator, "GET", "/projects/").get("items", [])

    def project(slug: str, name: str, client: str, address: str) -> dict:
        display_name = f"{name} [{slug}]"
        found = next((p for p in existing_projects if p["name"] == display_name), None)
        if found:
            return found
        created = api(
            estimator,
            "POST",
            "/projects/",
            {
                "name": display_name,
                "client_id": client_ids[client],
                "client_name": client,
                "delivery_address": address,
                "notes_internal": f"DEMO FIXTURE {slug} — datos sintéticos, no fabricar",
            },
        )
        existing_projects.append(created)
        return created

    def position(project_id: str, loc: str, tree: dict, qty: int) -> None:
        rows_list = query(
            "project_positions?select=id,location_tag,parametric_tree"
            f"&project_id=eq.{project_id}"
        )
        existing = next(
            (r for r in rows_list if r.get("location_tag") == loc), None
        )
        if existing:
            stored = existing.get("parametric_tree") or {}
            if '"glass_article_sku"' not in json.dumps(stored):
                # Positions from an earlier fixture run predate the glass-SKU
                # requirement — rewrite them through the same update surface.
                detail = api(
                    estimator, "GET", f"/positions/{existing['id']}/"
                )
                api(
                    estimator,
                    "PUT",
                    f"/positions/{existing['id']}/",
                    {
                        "location_tag": loc,
                        "quantity": qty,
                        "design": {
                            "system_id": tree["system_id"],
                            "nominal_width_mm": tree["nominal_width_mm"],
                            "nominal_height_mm": tree["nominal_height_mm"],
                            "color": tree["color"],
                            "parametric_tree": tree["parametric_tree"],
                        },
                        "expected_updated_at": detail["updated_at"],
                    },
                )
            return
        api(
            estimator,
            "POST",
            f"/projects/{project_id}/positions/",
            {"location_tag": loc, "quantity": qty, "design": tree},
        )

    vivienda = project(
        "CASA_LOMAS",
        "Vivienda demo — casa (fixture)",
        "Maria Paz Rojas",
        "Av. Demostración 100, Santiago",
    )
    for loc, tree, qty in [
        ("Dormitorio principal", tilt_turn("1600", "1200", "vd1"), 2),
        ("Baño", fixed("600", "800", "vb1"), 1),
        ("Living", tilt_turn("2400", "1500", "vl1"), 1),
        ("Cocina", fixed("1200", "900", "vc1"), 1),
        ("Logia", bay("900", "900", "TURN_LEFT", "lg1"), 1),
        ("Estar segundo piso", bay("1800", "1200", "SLIDING_2L", "es1"), 1),
        ("Dormitorio norte", bay("1400", "1100", "TILT_TURN_LEFT", "dn1"), 1),
        ("Pasillo", fixed("700", "1400", "ps1"), 1),
        ("Acceso terraza", bay("900", "2100", "TURN_RIGHT", "pt1"), 1),
        ("Bow comedor modulo 1", fixed("900", "1300", "bw1"), 1),
        ("Bow comedor modulo 2", fixed("900", "1300", "bw2"), 1),
        ("Conjunto acoplado escritorio", tilt_turn("2200", "1300", "ac1"), 1),
    ]:
        position(vivienda["id"], loc, tree, qty)

    obra = project(
        "TORRE_BARROS",
        "Obra grande demo — edificio (fixture)",
        "Constructora Rio Claro SpA",
        "Barros Arana 1445, Concepcion",
    )
    for i in range(1, 101):
        position(
            obra["id"],
            f"Piso {(i - 1) // 10 + 1} eje {((i - 1) % 10) + 1}",
            tilt_turn("1800", "1400", f"ob{i}"),
            1,
        )

    incompleta = project(
        "INCOMPLETA",
        "Proyecto incompleto (fixture)",
        "Colegio Valle Andino",
        "Av. Collao 980, Concepcion",
    )
    position(
        incompleta["id"], "Pendiente de cotizar", fixed("900", "600", "inc1"), 1
    )

    aprobado = project(
        "APROBADO",
        "Clinica Puerto Sur - anticipo recibido DEMO",
        "Clinica Puerto Sur SpA",
        "Barros Arana 1220, Concepcion",
    )
    position(aprobado["id"], "Box consulta", tilt_turn("1500", "1200", "ap1"), 8)

    produccion = project(
        "PRODUCCION",
        "Condominio Los Raulies - en produccion DEMO",
        "Inversiones Lomas Ltda.",
        "Camino a Chiguayante 3210, Chiguayante",
    )
    position(
        produccion["id"],
        "Torre A vano tipo",
        bay("1600", "1300", "SLIDING_2L", "pr1"),
        18,
    )

    despachado = project(
        "DESPACHADO",
        "Casa Jorge Vidal - despachado DEMO",
        "Jorge Andres Vidal",
        "Pasaje Maiten 402, Hualpen",
    )
    position(despachado["id"], "Fachada principal", fixed("1800", "1200", "dp1"), 3)

    instalado = project(
        "INSTALADO",
        "Reposicion oficinas Rio Claro - instalado DEMO",
        "Constructora Rio Claro SpA",
        "Ongolmo 533, Concepcion",
    )
    position(instalado["id"], "Sala reuniones", tilt_turn("2000", "1400", "in1"), 2)

    rechazado = project(
        "RECHAZADO",
        "Presupuesto local comercial - rechazado DEMO",
        "Maria Paz Rojas",
        "Anibal Pinto 650, Concepcion",
    )
    position(rechazado["id"], "Vitrina", fixed("2400", "2100", "rj1"), 1)

    print(f"org {ORG_ID} ({ORG_NAME})")
    print(f"org {ORG_B_ID} ({ORG_B_NAME})")
    for key, email, role in ACCOUNTS:
        print(f"  {role:18} {email}  / {PASSWORD}")
    print(f"  clients: {list(client_ids)}")
    print(f"  projects: vivienda={vivienda['id']} obra={obra['id']} incompleta={incompleta['id']}")
    print(f"  cost items: {len(skus)} SKUs covered")
    print("DEMO FIXTURE — datos sintéticos de referencia (DEMO_60).")


def mark_project_phases(projects: dict[str, str]) -> None:
    status_by_phase = {
        "borrador": "DRAFT",
        "cotizado": "QUOTED",
        "enviado": "QUOTED",
        "aprobado con anticipo": "APPROVED",
        "en produccion": "IN_PRODUCTION",
        "despachado": "COMPLETED",
        "instalado": "COMPLETED",
        "rechazado": "CANCELLED",
    }
    for phase, project_id in projects.items():
        sql(
            "UPDATE public.projects SET status=%s, notes_internal="
            "regexp_replace(COALESCE(notes_internal,''), "
            "E'\\nFase fixture P00: .*', '', 'g') || %s WHERE id=%s",
            (status_by_phase[phase], f"\nFase fixture P00: {phase}.", project_id),
        )


def stage(estimator: str, users: dict[str, str], *projects: dict) -> None:
    """Walk each fixture project through quote → freeze → release → optimize.

    Idempotent: re-checks current state at every step so reruns only fill
    what is missing. Same HTTP surface the UI drives.
    """
    today = "2026-09-28"

    def save_inputs(project_id: str) -> None:
        prepared = api(
            estimator, "GET", f"/documents/projects/{project_id}/inputs/"
        )
        positions = []
        for p in prepared["positions"]:
            handle_intents = [
                {
                    "schema_version": 1,
                    "bay_id": req["bay_id"],
                    "leaf_id": req.get("leaf_id"),
                    "handle_domain_slot": req["handle_domain_slot"],
                    "requested_height_mm": "1050",
                    "vertical_reference": "OUTER_BOTTOM",
                }
                for policy in p.get("handle_requirements", [])
                for req in policy.get("requirements", [])
            ]
            positions.append(
                {
                    "position_id": p["position_id"],
                    "calculation_hash": p["calculation_hash"],
                    "location_tag": p["location_tag"] or "POS",
                    "manufacturing_placement_policy_id": p[
                        "manufacturing_placement_policy_id"
                    ],
                    "handle_requirement_policy_id": p[
                        "handle_requirement_policy_id"
                    ],
                    "reinforcement_cut_policy_id": p["reinforcement_cut_policy_id"],
                    "workshop_annotations": p.get("workshop_suggestions", []),
                    "structural_inputs": p.get("structural_inputs", []),
                    "glass_polishing": p.get("polishing_suggestions", []),
                    "handle_intents": handle_intents,
                    "accessory_schedule": {
                        "schema_version": 1,
                        "coverage": "NONE_REQUIRED",
                        "items": [],
                    },
                    "legacy_handle_migration_confirmed": False,
                }
            )
        api(
            estimator,
            "PUT",
            f"/documents/projects/{project_id}/inputs/",
            {
                "payment_terms": "50% anticipo, 50% contra entrega",
                "quotation_valid_until": "2026-10-14",
                "positions": positions,
            },
        )

    def applied_operation(project_id: str) -> dict:
        detail = api(estimator, "GET", f"/projects/{project_id}/")
        if detail.get("pricing_current") and detail.get(
            "current_pricing_operation_id"
        ):
            return {"id": detail["current_pricing_operation_id"]}
        save_inputs(project_id)
        operation = api(
            estimator,
            "POST",
            "/pricing/preview/",
            {
                "project_id": project_id,
                "pricing_mode": "COST_PLUS_MARGIN",
                "context_code": "DEFAULT",
                "currency": "CLP",
                "effective_date": today,
                "discount_pct": "0",
                "target_margin": "0.35",
                "segment": "RETAIL",
                "reason": "fixture pricing",
            },
        )
        api(
            estimator,
            "POST",
            f"/pricing/operations/{operation['id']}/apply/",
            {"reason": "fixture apply", "confirmed": True},
        )
        return operation

    wm = login("demo-manager@fixture.dekopen.local")
    api(wm, "POST", "/production/work-centers/seed-defaults/")

    for index, proj in enumerate(projects):
        project_id = proj["id"]
        operation = applied_operation(project_id)
        frozen = api(
            estimator,
            "POST",
            f"/documents/projects/{project_id}/freeze/",
            {
                "pricing_operation_id": operation["id"],
                "confirmed": True,
            },
        )
        version_id = frozen["id"]
        api(
            estimator,
            "POST",
            "/documents/artifacts/",
            {
                "document_type": "DOC-01",
                "format": "PDF",
                "project_version_id": version_id,
            },
        )
        if index > 0 or not frozen.get("production_allowed"):
            continue
        released = api(
            wm, "POST", f"/production/versions/{version_id}/release/"
        )
        for order in released.get("orders", []):
            api(
                wm,
                "POST",
                f"/production/orders/{order['id']}/optimize/",
                {"color": "WHITE"},
            )
            # Cut pack is a production artifact, not a documentary order doc.
            pack = httpx.get(
                f"{DJANGO}/api/v1/production/orders/{order['id']}/cut-pack/",
                headers={
                    "Authorization": f"Bearer {wm}",
                    "X-Organization-ID": ORG_ID,
                },
                timeout=60,
            )
            pack.raise_for_status()
            print(
                f"  cut-pack {order['order_code']}: "
                f"{len(pack.content)} bytes"
            )


if __name__ == "__main__":
    main()
