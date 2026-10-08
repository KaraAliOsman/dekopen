#!/usr/bin/env python3
"""Documented synthetic fixtures for DEKOPEN local development.

Creates one realistic Chilean fabricator org — "Ventanas del Sur SpA" —
with one account per role, commercial prerequisites (pricing rules + a
cost list covering every reference-catalog purchase SKU), six clients
with valid modulo-11 RUTs, and ten projects covering the whole product
breadth and the full lifecycle:

  P-BORRADOR    Casa El Roble — draft, positions only
  P-COTIZADO    Edificio Carrera — priced, QUOTED, nothing sealed
  P-ENVIADO     Casa Pérez — quote link live (plus a revoked sibling)
  P-APROBADO    Local Prat — portal-approved, anticipo paid, REV-B link
                (leaves a superseded "reemplazada" link behind)
  P-PORTAL      Casa Molina — second-revision seal, approved link:
                carries the capture-visible reemplazada + aprobada tokens
  P-CONJUNTOS   Ampliación Vergara — bow + conjunto acoplado; seals
                quote-only by design (production_allowed stays false)
  P-VITRINA     12-position mix (fijo, abatible, oscilobatiente, corredera
                2 hojas, corredera O/X/X/O, proyectante, puerta, mampara
                fija+proyectante, extras, posición alternativa),
                released to the workshop
  P-DESPACHADO  released order dispatched
  P-INSTALADO   released order installed
  P-RECHAZADO   client declined the quote
  P-CAMBIOS     client asked for changes (portal CHANGES_REQUESTED)
  P-USD         quote priced in USD (portal hides the payment CTA)
  P-EXPIRADA    sealed quote past its validity (portal shows "expirada")
  P-ESCALA      100 positions, priced (scale surface for lists/canvas)

A second org — "Cristales del Norte Ltda." — exists to prove tenant
isolation; the OWNER account is a member of both orgs so the org selector
is a real screen, and org B carries its own client + draft project.

Everything written here is DEMONSTRATION data — it feeds the DEMO_60
reference family, whose fabrication authority is intentionally
incomplete. Fabrication-enabled catalogs need real manufacturer data;
this fixture never fabricates authority. Projects are marked
"DEMO FIXTURE" in notes_internal.

Usage (stack running: `make test-db`'s supabase + Django + Vite):
    SUPABASE_SERVICE_ROLE_KEY=... python scripts/dev_fixture.py

Env: SUPABASE_URL (default http://127.0.0.1:25321),
     SUPABASE_SERVICE_ROLE_KEY (required), DJANGO_URL (default :8000),
     DATABASE_URL (default local supabase db — pricing writes are
     audit-gated for REST and use the privileged maintenance path),
     FIXTURE_STATE (default .fixture-state.json — machine-readable
     summary for the ux:capture harness).
Idempotent: deterministic ids upserted on every run.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import struct
import sys
import time
import uuid
import zlib
from datetime import date, timedelta
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

STATE_PATH = os.environ.get("FIXTURE_STATE", ".fixture-state.json")

NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://dekopen.local/dev-fixture")
ORG_ID = str(uuid.uuid5(NS, "org"))
ORG_NAME = "Ventanas del Sur SpA"
ORG_B_ID = str(uuid.uuid5(NS, "org-b"))
ORG_B_NAME = "Cristales del Norte Ltda."

ACCOUNTS = [
    ("owner", "demo-owner@fixture.dekopen.local", "OWNER"),
    ("estimator", "demo-estimator@fixture.dekopen.local", "ESTIMATOR"),
    ("manager", "demo-manager@fixture.dekopen.local", "WORKSHOP_MANAGER"),
    ("operator", "demo-operator@fixture.dekopen.local", "OPERATOR"),
    ("installer", "demo-installer@fixture.dekopen.local", "INSTALLER"),
    ("multi", "demo-multi@fixture.dekopen.local", "ESTIMATOR"),
]
PASSWORD = "Demo-Fixture-2026!"

SVC = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation",
}

DEMO_60 = "3067da09-3119-5ad0-a1d5-498cd2dfd753"
# The sliding family sibling (D01): sliding typologies only compute against
# a SLIDING-family system — the casement demo series refuses them.
CORREDERA_60 = "f9398347-bd56-555c-b9d3-81b3d6b4af1a"
DEMO_MARK = "DEMO FIXTURE — datos sintéticos, no fabricar"


def _transient_http(path: str, response: httpx.Response) -> bool:
    # Kong/PostgREST hiccup under the local stack (PGRST301 during brief
    # JWT-decoder blips) and container restarts: retry, never abort.
    if response.status_code >= 500 or response.status_code == 401:
        return True
    return False


def rest(path: str, rows: list[dict]) -> list[dict]:
    response = httpx.Response(500)
    for attempt in range(12):
        try:
            response = httpx.post(
                f"{SUPA}/rest/v1/{path}", headers=SVC, json=rows, timeout=15
            )
        except (httpx.ConnectError, httpx.ReadError):
            response = httpx.Response(502)
        if response.status_code < 300:
            return response.json() if response.text else []
        if _transient_http(path, response):
            time.sleep(min(8.0, 0.5 * (attempt + 1)))
            continue
        break
    sys.exit(f"POST {path} -> {response.status_code}: {response.text[:400]}")


def sql(statement: str, params: tuple | None = None) -> None:
    # Pricing/audit-gated tables reject actorless REST writes; direct SQL
    # (session_user postgres) is the audited privileged-maintenance path.
    with psycopg.connect(DB, autocommit=True) as connection:
        connection.execute(statement, params)


def sql_rows(statement: str, params: tuple | None = None) -> list[tuple]:
    with psycopg.connect(DB, autocommit=True) as connection:
        return list(connection.execute(statement, params).fetchall())


def query(path: str) -> list[dict]:
    response = httpx.Response(500)
    for attempt in range(12):
        try:
            response = httpx.get(
                f"{SUPA}/rest/v1/{path}", headers=SVC, timeout=30
            )
        except (httpx.ConnectError, httpx.ReadError):
            response = httpx.Response(502)
        if response.status_code < 300:
            return response.json()
        if _transient_http(path, response):
            time.sleep(min(8.0, 0.5 * (attempt + 1)))
            continue
        break
    sys.exit(f"GET {path} -> {response.status_code}: {response.text[:400]}")


def auth_admin(method: str, path: str, body: dict | None = None) -> httpx.Response:
    # GoTrue's admin endpoints return a spurious bad_jwt 403 in bursts on
    # this build (a misconfigured client spams malformed Bearer tokens and
    # poisons the auth state).  Ride the burst out: retry for ~2 minutes.
    for attempt in range(20):
        response = httpx.request(
            method,
            f"{SUPA}/auth/v1{path}",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
            json=body,
            timeout=15,
        )
        if response.status_code != 403 or attempt == 19:
            return response
        time.sleep(min(6.0, 0.5 * (attempt + 1)))
    return response


def all_users() -> dict[str, dict]:
    """Existing auth users — read straight from Postgres because GoTrue's
    admin listing is the endpoint that flaky bad_jwt bursts hit."""
    return {
        email: {"id": str(uid), "email": email}
        for uid, email in sql_rows("SELECT id, email FROM auth.users")
    }


def ensure_user(existing_users: dict[str, dict], email: str) -> str:
    existing = existing_users.get(email)
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
    for attempt in range(8):
        response = httpx.post(
            f"{SUPA}/auth/v1/token?grant_type=password",
            headers={"apikey": SERVICE_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": PASSWORD},
            timeout=15,
        )
        if response.status_code < 300:
            return response.json()["access_token"]
        if response.status_code != 403 or attempt == 7:
            sys.exit(
                f"login {email}: {response.status_code} {response.text[:300]}"
            )
        time.sleep(min(6.0, 0.5 * (attempt + 1)))
    raise AssertionError("unreachable")


def api(
    token: str,
    method: str,
    path: str,
    payload: dict | None = None,
    org_id: str = ORG_ID,
    tolerate: tuple[int, ...] = (),
) -> dict:
    response = httpx.request(
        method,
        f"{DJANGO}/api/v1{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": org_id,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    if response.status_code >= 300 and response.status_code not in tolerate:
        sys.exit(
            f"{method} {path} -> {response.status_code}: {response.text[:500]}"
        )
    return response.json() if response.text else {}


def public_api(method: str, path: str, payload: dict | None = None) -> dict:
    """Unauthenticated surface — the customer portal."""
    response = httpx.request(
        method, f"{DJANGO}/api/v1{path}", json=payload, timeout=30
    )
    if response.status_code >= 300:
        sys.exit(
            f"{method} {path} -> {response.status_code}: {response.text[:500]}"
        )
    return response.json()


def rut_check_digit(number: int) -> str:
    """Módulo 11 — the check digit that makes a Chilean RUT valid."""
    total = 0
    factor = 2
    for digit in reversed(str(number)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    return {10: "K", 11: "0"}.get(remainder, str(remainder))


def make_rut(number: int) -> str:
    body = f"{number:,}".replace(",", ".")
    return f"{body}-{rut_check_digit(number)}"


def tiny_png(width: int = 240, height: int = 72) -> bytes:
    """A minimal deterministic PNG logo — graphite bar + teal accent,
    drawn with stdlib zlib so the fixture has zero imaging deps."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    graphite = (43, 49, 57)
    teal = (0, 137, 123)
    paper = (255, 255, 255)
    rows_raw = b""
    for y in range(height):
        rows_raw += b"\x00"
        for x in range(width):
            if x < 56:
                rgb = teal if 20 <= y < 52 else paper
            elif 68 <= x < width - 8 and 24 <= y < 48:
                rgb = graphite
            else:
                rgb = paper
            rows_raw += bytes(rgb)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows_raw))
        + chunk(b"IEND", b"")
    )


def upload_logo(token: str, org_id: str) -> None:
    content = tiny_png()
    response = httpx.put(
        f"{DJANGO}/api/v1/organization/branding/logo/",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": org_id,
        },
        files={"file": ("logo.png", content, "image/png")},
        timeout=30,
    )
    if response.status_code >= 300:
        sys.exit(
            f"branding logo -> {response.status_code}: {response.text[:300]}"
        )


# ---------------------------------------------------------------- designs

GLASS = {
    "glass_thickness_mm": "24.00",
    "glass_spec": "4-16-4 Float Incoloro",
    "glass_article_sku": "VIDRIO-BASE",
}


def design(width: str, height: str, tree: dict, system_id: str = DEMO_60) -> dict:
    return {
        "system_id": system_id,
        "nominal_width_mm": width,
        "nominal_height_mm": height,
        "color": "WHITE",
        "parametric_tree": tree,
    }


def fixed(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {"id": uid, "type": "BAY", "opening_type": "FIXED", **GLASS},
    )


def turn(width: str, height: str, uid: str = "m1", side: str = "RIGHT") -> dict:
    return design(
        width, height,
        {
            "id": uid, "type": "BAY",
            "opening_type": f"TURN_{side}", **GLASS,
        },
    )


def tilt_turn(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {
            "id": uid,
            "type": "SPLIT_V",
            "split_offset_mm": str(Decimal(width) / 2),
            "mullion_profile_sku": "POSTE-V",
            "children": [
                {"id": f"{uid}-a", "type": "BAY", "opening_type": "FIXED", **GLASS},
                {
                    "id": f"{uid}-b", "type": "BAY",
                    "opening_type": "TILT_TURN_RIGHT", **GLASS,
                },
            ],
        },
    )


def tilt_turn_single(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {
            "id": uid, "type": "BAY",
            "opening_type": "TILT_TURN_RIGHT", **GLASS,
        },
    )


def sliding_2l(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height, system_id=CORREDERA_60,
        tree={
            "id": uid, "type": "BAY",
            "opening_type": "SLIDING_2L", **GLASS,
        },
    )


def sliding_oxoxo(width: str, height: str, uid: str = "m1") -> dict:
    """Corredera O/X/X/O — four slots on two rails, fixed-leaf bookends."""
    return design(
        width, height, system_id=CORREDERA_60,
        tree={
            "id": uid, "type": "BAY",
            "opening_type": "SLIDING", **GLASS,
            "sliding_layout": {
                "tracks": 2,
                "panels": [
                    {"slot": "1", "kind": "FIXED", "track": None},
                    {"slot": "2", "kind": "MOVING", "track": 0},
                    {"slot": "3", "kind": "MOVING", "track": 1},
                    {"slot": "4", "kind": "FIXED", "track": None},
                ],
            },
        },
    )


def awning(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {"id": uid, "type": "BAY", "opening_type": "AWNING", **GLASS},
    )


def door(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {
            "id": uid, "type": "BAY",
            "opening_type": "DOOR_ENTRY",
            "door_handedness": "RIGHT",
            "panel_article_sku": "PANEL-SANDWICH-DEMO-24",
            **GLASS,
        },
    )


def split_h_fixed_awning(width: str, height: str, uid: str = "m1") -> dict:
    return design(
        width, height,
        {
            "id": uid,
            "type": "SPLIT_H",
            "split_offset_mm": str(Decimal(height) * 2 // 3),
            "mullion_profile_sku": "POSTE-H",
            "children": [
                {"id": f"{uid}-a", "type": "BAY", "opening_type": "FIXED", **GLASS},
                {
                    "id": f"{uid}-b", "type": "BAY",
                    "opening_type": "AWNING", **GLASS,
                },
            ],
        },
    )


def shopfront(width: str, height: str, uid: str = "m1") -> dict:
    """Vitrina de local: dos postes verticales parten el paño en tres paños
    fijos — la solución real para vidrios que superan el límite de la
    composición (R04)."""
    third = Decimal(width) // 3

    def pane(tag: str) -> dict:
        return {"id": f"{uid}-{tag}", "type": "BAY", "opening_type": "FIXED", **GLASS}
    return design(
        width, height,
        {
            "id": uid,
            "type": "SPLIT_V",
            "split_offset_mm": str(third),
            "mullion_profile_sku": "POSTE-V",
            "children": [
                pane("a"),
                {
                    "id": f"{uid}-b",
                    "type": "SPLIT_V",
                    "split_offset_mm": str(third),
                    "mullion_profile_sku": "POSTE-V",
                    "children": [pane("b1"), pane("b2")],
                },
            ],
        },
    )


def _bay(uid: str, opening: str, **extra) -> dict:
    return {"id": uid, "type": "BAY", "opening_type": opening, **GLASS, **extra}


def bow3(width: str, height: str, uid: str = "bow") -> dict:
    """Bow de 3 módulos — product-v2 assembly, 25° couplings."""
    w = str(Decimal(width) / 3)
    return {
        "system_id": DEMO_60,
        "nominal_width_mm": width,
        "nominal_height_mm": height,
        "color": "WHITE",
        "parametric_tree": {
            "version": "product-v2",
            "assembly": {
                "modules": [
                    {
                        "id": f"{uid}-m1",
                        "width_mm": w,
                        "height_mm": height,
                        "tree": _bay(f"{uid}-m1", "FIXED"),
                    },
                    {
                        "id": f"{uid}-m2",
                        "width_mm": w,
                        "height_mm": height,
                        "tree": _bay(f"{uid}-m2", "TILT_TURN_RIGHT"),
                    },
                    {
                        "id": f"{uid}-m3",
                        "width_mm": w,
                        "height_mm": height,
                        "tree": _bay(f"{uid}-m3", "FIXED"),
                    },
                ],
                "couplings": [
                    {
                        "id": f"{uid}-c1",
                        "angle_deg": "25.00",
                        "coupler_profile_sku": "COPLE-60",
                    },
                    {
                        "id": f"{uid}-c2",
                        "angle_deg": "25.00",
                        "coupler_profile_sku": "COPLE-60",
                    },
                ],
            },
        },
    }


def acoplado(width: str, height: str, uid: str = "aco") -> dict:
    """Conjunto acoplado — corredera + fijo at 0° on one coupler."""
    w = str(Decimal(width) / 2)
    return {
        "system_id": CORREDERA_60,
        "nominal_width_mm": width,
        "nominal_height_mm": height,
        "color": "WHITE",
        "parametric_tree": {
            "version": "product-v2",
            "assembly": {
                "modules": [
                    {
                        "id": f"{uid}-m1",
                        "width_mm": w,
                        "height_mm": height,
                        "tree": _bay(f"{uid}-m1", "SLIDING_2L"),
                    },
                    {
                        "id": f"{uid}-m2",
                        "width_mm": w,
                        "height_mm": height,
                        "tree": _bay(f"{uid}-m2", "FIXED"),
                    },
                ],
                "couplings": [
                    {
                        "id": f"{uid}-c1",
                        "angle_deg": "0.00",
                        "coupler_profile_sku": "COPLE-CORR",
                    },
                ],
            },
        },
    }


# Extras declared on vitrina positions — real accessory lines that land in
# the hardware purchase order so extras are visible end to end.
EXTRA_ITEMS = [
    {
        "obligation_id": "fixture-vierteaguas",
        "obligation_kind": "INSTALLATION_ACCESSORY",
        "technical_sku": "VIERTEAGUAS-D60",
        "purchasing_sku": "VIERTEAGUAS-D60",
        "manufacturer_name": "Ventanas del Sur (taller)",
        "order_type": "SUPPLIER_HARDWARE_PO",
        "quantity_per_position_unit": 1,
        "description": "Vierteaguas exterior perfilado 60 mm",
    },
    {
        "obligation_id": "fixture-cierrapuertas",
        "obligation_kind": "INSTALLATION_ACCESSORY",
        "technical_sku": "CIERRAPUERTAS-AEREO",
        "purchasing_sku": "CIERRAPUERTAS-AEREO",
        "manufacturer_name": "Proveedor herrajes fixture",
        "order_type": "SUPPLIER_HARDWARE_PO",
        "quantity_per_position_unit": 1,
        "description": "Cierrapuertas aéreo con retención",
    },
]


def main() -> None:
    existing_users = all_users()
    users = {
        key: ensure_user(existing_users, email) for key, email, _ in ACCOUNTS
    }

    # --- organizations -------------------------------------------------
    rest(
        "tenancy_organizations",
        [
            {
                "id": ORG_ID,
                "name": ORG_NAME,
                "tax_id": make_rut(76885400),
                "country": "CL",
                "currency": "CLP",
                "subscription_active": True,
            },
            {
                "id": ORG_B_ID,
                "name": ORG_B_NAME,
                "tax_id": make_rut(77890123),
                "country": "CL",
                "currency": "CLP",
                "subscription_active": True,
            },
        ],
    )
    memberships = [
        {
            "id": str(uuid.uuid5(NS, f"membership-{key}")),
            "org_id": ORG_ID,
            "user_id": users[key],
            "role": role,
            "is_active": True,
        }
        for key, _, role in ACCOUNTS
    ]
    # Org B: the multi-org account belongs to both — org selection is a
    # real step — and the owner can inspect the second tenant for
    # isolation checks.
    memberships += [
        {
            "id": str(uuid.uuid5(NS, "membership-multi-b")),
            "org_id": ORG_B_ID,
            "user_id": users["multi"],
            "role": "ESTIMATOR",
            "is_active": True,
        },
        {
            "id": str(uuid.uuid5(NS, "membership-owner-b")),
            "org_id": ORG_B_ID,
            "user_id": users["owner"],
            "role": "OWNER",
            "is_active": True,
        },
    ]
    rest("tenancy_memberships", memberships)

    estimator = login(ACCOUNTS[1][1])
    wm = login(ACCOUNTS[2][1])
    owner_b = login(ACCOUNTS[5][1])

    # Branding — the identity every emitted document carries.
    api(
        estimator,
        "PUT",
        "/organization/branding/",
        {
            "commercial_name": "Ventanas del Sur SpA",
            "brand_address": "Av. Paicaví 3280, Concepción",
            "brand_phone": "+56 41 234 5678",
            "brand_email": "contacto@ventanasdelsur.cl",
            "giro": "Fabricación e instalación de ventanas y puertas de PVC y aluminio",
        },
        tolerate=(400, 422),
    )
    api(
        estimator,
        "PUT",
        "/organization/branding/",
        {
            "brand_address": "Av. Paicaví 3280, Concepción",
            "brand_phone": "+56 41 234 5678",
            "brand_email": "contacto@ventanasdelsur.cl",
        },
    )
    upload_logo(estimator, ORG_ID)

    # --- commercial prerequisites --------------------------------------
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
    # Fixture-declared extras ride the same pricing/stock coverage.
    for item in EXTRA_ITEMS:
        skus[(item["purchasing_sku"], "EA")] = "FITTING"

    with psycopg.connect(DB, autocommit=True) as connection:
        for (sku, unit), item_type in sorted(skus.items()):
            connection.execute(
                "INSERT INTO public.cost_list_items(id,org_id,cost_list_id,sku,"
                "unit,item_type,unit_cost,description) "
                "VALUES(%s,%s,%s,%s,%s,'FIXTURE',100.00,'DEMO FIXTURE cost') "
                "ON CONFLICT (cost_list_id, sku) DO NOTHING",
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
        # Fastening fittings are bulk consumables: the sealed BOM emits
        # aggregated REINFORCEMENT_SCREW counts that run into the hundreds per
        # project — 500 units covers kits and glass, not screws.
        fitting_skus = {sku for (sku, _), kind in skus.items() if kind == "FITTING"}
        for identity in sorted({*bar_identities, *unit_identities}):
            sku, _, variant = identity.partition("::")
            receipt_qty = 50000 if sku in fitting_skus else 500
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
                    "VALUES(%s,%s,'RECEIPT',%s,'fixture stock',%s)",
                    (ORG_ID, item_id, receipt_qty, users["owner"]),
                )

    api(wm, "POST", "/production/work-centers/seed-defaults/")

    # --- clients ---------------------------------------------------------
    clients = [
        ("María José Fernández Roa", make_rut(13579246), "mjfernandez@correo.cl"),
        ("Constructora Bío Bío S.A.", make_rut(96543210), "obras@constructorabiobio.cl"),
        ("Inmobiliaria Los Alerces Ltda.", make_rut(78123456), "contacto@losalerces.cl"),
        ("Juan Carlos Muñoz Vera", make_rut(11222333), "jcmunoz@correo.cl"),
        ("Colegio San Patricio", make_rut(65432109), "rectoria@sanpatricio.cl"),
        ("Ilustre Municipalidad de Chiguayante", make_rut(69120500), "adquisiciones@chiguayante.cl"),
    ]
    client_ids = {}
    for name, rut, email in clients:
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
                    "is_active": True,
                    "created_by": users["owner"],
                }
            ],
        )
        client_ids[name] = cid

    client_ruts = {name: rut for name, rut, _email in clients}
    rest(
        "clients",
        [
            {
                "id": str(uuid.uuid5(NS, "client-org-b")),
                "org_id": ORG_B_ID,
                "name": "Hotel Patagonia Norte S.A.",
                "rut": make_rut(77332211),
                "email": "mantencion@hotelpatagonia.cl",
                "is_active": True,
                "created_by": users["multi"],
            }
        ],
    )

    # --- projects --------------------------------------------------------
    existing_projects = api(estimator, "GET", "/projects/").get("items", [])

    def project(slug: str, name: str, client: str, address: str) -> dict:
        found = next((p for p in existing_projects if p["name"] == name), None)
        if found:
            return found
        created = api(
            estimator,
            "POST",
            "/projects/",
            {
                "name": name,
                "client_id": client_ids[client],
                "client_name": client,
                "client_rut": client_ruts[client],
                "delivery_address": address,
                "notes_internal": f"{DEMO_MARK} [{slug}]",
            },
        )
        existing_projects.append(created)
        return created

    project_status: dict[str, str] = {}

    def editable(project_id: str) -> bool:
        if project_id not in project_status:
            detail = api(estimator, "GET", f"/projects/{project_id}/")
            project_status[project_id] = str(detail.get("status") or "DRAFT")
        return project_status[project_id] in ("DRAFT", "QUOTED")

    def position(
        project_id: str,
        loc: str,
        design_payload: dict,
        qty: int,
        is_option: bool = False,
    ) -> None:
        rows_list = query(
            "project_positions?select=id,location_tag,parametric_tree,"
            "width_mm,height_mm,is_option"
            f"&project_id=eq.{project_id}"
        )
        existing = next(
            (r for r in rows_list if r.get("location_tag") == loc), None
        )
        if existing:
            if not editable(project_id):
                return
            stored = json.dumps(existing.get("parametric_tree") or {}, sort_keys=True)
            wanted = json.dumps(design_payload.get("parametric_tree") or {}, sort_keys=True)
            same_dims = (
                str(existing.get("width_mm"))[:7].rstrip("0").rstrip(".")
                == design_payload["nominal_width_mm"]
                and str(existing.get("height_mm"))[:7].rstrip("0").rstrip(".")
                == design_payload["nominal_height_mm"]
            )
            if (
                stored == wanted
                and same_dims
                and bool(existing.get("is_option")) == is_option
                and '"glass_article_sku"' in stored
            ):
                return
            detail = api(
                estimator, "GET", f"/positions/{existing['id']}/",
                tolerate=(404, 409),
            )
            if not detail.get("updated_at"):
                return
            status = api(
                estimator,
                "PUT",
                f"/positions/{existing['id']}/",
                {
                    "location_tag": loc,
                    "quantity": qty,
                    "is_option": is_option,
                    "design": design_payload,
                    "expected_updated_at": detail["updated_at"],
                },
                tolerate=(409,),
            )
            if (status.get("error") or {}).get("code") == "commercial_revision_required":
                # Precio ya aplicado sobre el diseño anterior: el flujo real
                # es reset-pricing y luego reeditar (la recotización corre
                # después en priced_operation).
                current = api(estimator, "GET", f"/projects/{project_id}/")
                op_id = current.get("current_pricing_operation_id")
                if op_id and current.get("status") == "DRAFT":
                    api(
                        estimator,
                        "POST",
                        f"/projects/{project_id}/reset-pricing/",
                        {
                            "expected_operation_id": op_id,
                            "reason": "fixture: actualización de diseño",
                            "confirmed": True,
                        },
                    )
                    detail = api(estimator, "GET", f"/positions/{existing['id']}/")
                    api(
                        estimator,
                        "PUT",
                        f"/positions/{existing['id']}/",
                        {
                            "location_tag": loc,
                            "quantity": qty,
                            "is_option": is_option,
                            "design": design_payload,
                            "expected_updated_at": detail["updated_at"],
                        },
                    )
            return
        api(
            estimator,
            "POST",
            f"/projects/{project_id}/positions/",
            {
                "location_tag": loc,
                "quantity": qty,
                "is_option": is_option,
                "design": design_payload,
            },
        )

    def prune_positions(project_id: str, keep_tags: set[str]) -> None:
        """Delete fixture positions no longer in the recipe — draft rows only."""
        if not editable(project_id):
            return
        for row in query(
            "project_positions?select=id,location_tag"
            f"&project_id=eq.{project_id}"
        ):
            if row.get("location_tag") in keep_tags:
                continue
            detail = api(
                estimator, "GET", f"/positions/{row['id']}/", tolerate=(404,)
            )
            if not detail.get("updated_at"):
                continue
            httpx.request(
                "DELETE",
                f"{DJANGO}/api/v1/positions/{row['id']}/",
                params={"expected_updated_at": detail["updated_at"]},
                headers={
                    "Authorization": f"Bearer {estimator}",
                    "X-Organization-ID": ORG_ID,
                },
                timeout=30,
            )

    def set_positions(
        proj: dict,
        entries: list[tuple[str, dict, int]],
        options: set[str] | None = None,
    ) -> None:
        option_locs = options or set()
        keep = {loc for loc, _, _ in entries}
        for loc, tree, qty in entries:
            position(proj["id"], loc, tree, qty, is_option=loc in option_locs)
        prune_positions(proj["id"], keep)

    FER = "María José Fernández Roa"
    CBB = "Constructora Bío Bío S.A."
    ILA = "Inmobiliaria Los Alerces Ltda."
    JMV = "Juan Carlos Muñoz Vera"
    CSP = "Colegio San Patricio"
    MCH = "Ilustre Municipalidad de Chiguayante"

    # Stale fixture projects from older recipe versions (e.g. the sealed
    # vitrina that still carried assemblies — quote-only, unreleasable) and
    # probe residue. Sealed versions are evidence-immutable, so the cleanup
    # runs under replica role (trigger-suppressed) like every local reset.
    with psycopg.connect(DB, autocommit=True) as conn:
        conn.execute("SET session_replication_role = 'replica'")
        conn.execute(
            "DELETE FROM public.project_versions WHERE org_id=%s AND project_id IN "
            "(SELECT id FROM public.projects WHERE org_id=%s AND name LIKE %s)",
            (ORG_ID, ORG_ID, "%vitrina 12 posiciones%"),
        )
        conn.execute(
            "DELETE FROM public.projects WHERE org_id=%s AND "
            "(name LIKE %s OR name LIKE %s)",
            (ORG_ID, "%vitrina 12 posiciones%", "%probe%"),
        )

    p_borrador = project(
        "P-BORRADOR", "Casa El Roble — Los Ángeles", FER, "Villa Los Robles 1140, Los Ángeles"
    )
    set_positions(
        p_borrador,
        [
            ("Dormitorio principal", tilt_turn("1600", "1200", "br1"), 2),
            ("Baño", fixed("600", "800", "br2"), 1),
            ("Living", tilt_turn("2400", "1500", "br3"), 1),
            ("Cocina", fixed("1200", "900", "br4"), 1),
        ],
    )

    p_cotizado = project(
        "P-COTIZADO", "Edificio Carrera 1145 — Concepción", CBB, "Av. Carrera 1145, Concepción"
    )
    set_positions(
        p_cotizado,
        [
            ("Depto 101 — living", tilt_turn("2200", "1400", "ct1"), 1),
            ("Depto 101 — dormitorio", tilt_turn("1600", "1200", "ct2"), 2),
            ("Depto 102 — living", sliding_2l("2400", "1400", "ct3"), 1),
            ("Depto 102 — dormitorio", tilt_turn("1600", "1200", "ct4"), 2),
            ("Hall acceso", fixed("1400", "2200", "ct5"), 1),
        ],
    )

    p_enviado = project(
        "P-ENVIADO", "Casa Pérez — Chiguayante", JMV, "Pasaje Las Hortensias 45, Chiguayante"
    )
    set_positions(
        p_enviado,
        [
            ("Dormitorio 1", tilt_turn("1600", "1200", "en1"), 1),
            ("Dormitorio 2", tilt_turn("1600", "1200", "en2"), 1),
            ("Living-comedor", sliding_2l("2800", "1600", "en3"), 1),
            ("Baño", awning("800", "600", "en4"), 2),
        ],
    )

    p_aprobado = project(
        "P-APROBADO", "Local Comercial Prat 120 — Concepción", ILA, "Av. Prat 120, Concepción"
    )
    set_positions(
        p_aprobado,
        [
            ("Vitrina frontal", shopfront("3000", "2200", "ap1"), 1),
            ("Puerta acceso", door("900", "2100", "ap2"), 1),
            ("Ventana oficina", tilt_turn("1800", "1200", "ap3"), 1),
            ("Baño", awning("800", "600", "ap4"), 1),
        ],
    )

    # Conjuntos (bow / acoplado): sellan quote-only por diseño — el motor
    # no proyecta compras por módulo todavía, así que production_allowed
    # queda en falso honestamente. Viven en su propio proyecto para no
    # bloquear la liberación de la vitrina.
    p_conjuntos = project(
        "P-CONJUNTOS", "Ampliación Vergara — bow y acoplado", FER,
        "Av. Los Carrera 550, Concepción",
    )
    set_positions(
        p_conjuntos,
        [
            ("Bow hall", bow3("2700", "1500", "cj1"), 1),
            ("Conjunto acoplado cocina", acoplado("2400", "1400", "cj2"), 1),
        ],
    )

    # Proyecto porta-tokens: el par de links reemplazada/aprobada del
    # portal con tokens vigentes en .fixture-state.json.
    p_portal = project(
        "P-PORTAL", "Casa Molina — cotización revisada y aprobada", FER,
        "Calle Colo Colo 1420, Concepción",
    )
    set_positions(
        p_portal,
        [
            ("Ventanal living", tilt_turn("2200", "1400", "pt1"), 1),
            ("Ventana dormitorio", turn("1200", "1400", "pt2"), 1),
        ],
    )

    p_vitrina = project(
        "P-VITRINA", "Casa Ríos — vitrina de 12 posiciones", CSP, "Camino a Penco 2234, San Pedro de la Paz"
    )
    set_positions(
        p_vitrina,
        [
            ("V01 Fijo living", fixed("1800", "1400", "v01"), 1),
            ("V02 Abatible dormitorio", turn("1200", "1400", "v02"), 1),
            ("V03 Oscilobatiente dormitorio 2", tilt_turn_single("1100", "1400", "v03"), 1),
            ("V04 Corredera 2 hojas terraza", sliding_2l("2600", "1600", "v04"), 1),
            ("V05 Corredera O/X/X/O quincho", sliding_oxoxo("3600", "1600", "v05"), 1),
            ("V06 Proyectante baño", awning("800", "600", "v06"), 1),
            ("V07 Puerta principal", door("1000", "2200", "v07"), 1),
            ("V08 Ventana cocina sobre mesada", turn("1000", "900", "v08"), 1),
            ("V09 Fijo escalera", fixed("800", "1800", "v09"), 1),
            ("V10 Mampara fija + proyectante", split_h_fixed_awning("1100", "1800", "v10"), 1),
            ("V11 Ventanal doble oscilobatiente", tilt_turn("2800", "1600", "v11"), 1),
            # Alternativa REAL (is_option): mismo vano que V02 resuelto con
            # corredera — se dibuja y se precifica pero no entra al total.
            ("V12 Alternativa corredera (vano V02)", sliding_2l("1200", "1400", "v12"), 1),
        ],
        options={"V12 Alternativa corredera (vano V02)"},
    )

    p_despachado = project(
        "P-DESPACHADO", "Vivienda Camino Penco km 8", MCH, "Camino Penco km 8, Penco"
    )
    set_positions(
        p_despachado,
        [
            ("Living", sliding_2l("2600", "1600", "dp1"), 1),
            ("Dormitorio", tilt_turn("1500", "1200", "dp2"), 1),
            ("Baño", awning("800", "600", "dp3"), 1),
        ],
    )

    p_instalado = project(
        "P-INSTALADO", "Departamentos Lirquén — Penco", ILA, "Calle Lirquén 801, Penco"
    )
    set_positions(
        p_instalado,
        [
            ("Depto A — living", tilt_turn("2000", "1400", "in1"), 1),
            ("Depto A — dormitorio", tilt_turn("1400", "1200", "in2"), 1),
            ("Baño compartido", awning("800", "600", "in3"), 1),
        ],
    )

    p_rechazado = project(
        "P-RECHAZADO", "Remodelación San Pedro — oficinas", JMV, "Av. San Pedro 312, San Pedro de la Paz"
    )
    set_positions(
        p_rechazado,
        [
            ("Oficina 1", tilt_turn("1600", "1200", "rj1"), 1),
            ("Oficina 2", turn("1200", "1200", "rj2"), 1),
        ],
    )

    p_cambios = project(
        "P-CAMBIOS", "Dúplex Los Aromos — con observaciones", FER, "Los Aromos 1280, Concepción"
    )
    set_positions(
        p_cambios,
        [
            ("Ventanal acceso", sliding_2l("2400", "1500", "cm1"), 1),
            ("Ventana dormitorio", tilt_turn("1400", "1200", "cm2"), 1),
        ],
    )

    p_usd = project(
        "P-USD", "Bodega exportadora — cotización en dólares", ILA, "Ruta 160 km 4, Coronel"
    )
    set_positions(
        p_usd,
        [
            ("Ventana oficina", tilt_turn("1800", "1200", "us1"), 2),
        ],
    )

    p_expirada = project(
        "P-EXPIRADA", "Cotización exprés — plazo vencido", FER, "Pasaje El Boldo 77, Hualpén"
    )
    set_positions(
        p_expirada,
        [
            ("Ventana dormitorio", tilt_turn("1400", "1200", "ex1"), 1),
        ],
    )

    p_escala = project(
        "P-ESCALA", "Torre Escala — 100 posiciones", CBB, "Av. O'Higgins 900, Concepción"
    )
    scale_entries = []
    for i in range(1, 101):
        floor = (i - 1) // 10 + 1
        unit = (i - 1) % 10 + 1
        kind = i % 4
        if kind == 0:
            tree = fixed("1000", "1200", f"es{i}")
        elif kind == 1:
            tree = tilt_turn("1600", "1200", f"es{i}")
        elif kind == 2:
            tree = sliding_2l("2000", "1400", f"es{i}")
        else:
            tree = awning("800", "600", f"es{i}")
        scale_entries.append((f"Piso {floor} unidad {unit}", tree, 1))
    set_positions(p_escala, scale_entries)

    # Org B minimal data — one draft project so tenant isolation is checkable.
    orgb_projects = api(owner_b, "GET", "/projects/", org_id=ORG_B_ID).get("items", [])
    if not orgb_projects:
        orgb_client = next(
            (c for c in query(f"clients?select=id&org_id=eq.{ORG_B_ID}")),
            None,
        )
        api(
            owner_b,
            "POST",
            "/projects/",
            {
                "name": "Hotel Patagonia — temporada 2027",
                "client_id": orgb_client["id"] if orgb_client else None,
                "client_name": "Hotel Patagonia Norte S.A.",
                "delivery_address": "Costanera 1500, Puerto Varas",
                "notes_internal": f"{DEMO_MARK} [ORG-B] — aislado de Ventanas del Sur",
            },
            org_id=ORG_B_ID,
        )

    state = {
        "org_id": ORG_ID,
        "org_name": ORG_NAME,
        "org_b_id": ORG_B_ID,
        "org_b_name": ORG_B_NAME,
        "system_id": DEMO_60,
        "password": PASSWORD,
        "accounts": {
            key: {"email": email, "role": role}
            for key, email, role in ACCOUNTS
        },
        "projects": {},
        "portal": {},
        "orders": {},
    }
    # Tokens and order ids survive only in the state file — merging the
    # previous run's data is what makes the mint guards below idempotent.
    # Also preserves keys the harness writes back (e.g. the TOTP vault).
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as handle:
                persisted = json.load(handle)
            for key in ("portal", "orders"):
                if isinstance(persisted.get(key), dict):
                    state[key].update(persisted[key])
            for key, value in persisted.items():
                if key not in state:
                    state[key] = value
        except (OSError, json.JSONDecodeError):
            pass
    for slug, proj in [
        ("borrador", p_borrador), ("cotizado", p_cotizado),
        ("enviado", p_enviado), ("aprobado", p_aprobado),
        ("conjuntos", p_conjuntos), ("portal", p_portal),
        ("vitrina", p_vitrina), ("despachado", p_despachado),
        ("instalado", p_instalado), ("rechazado", p_rechazado),
        ("cambios", p_cambios), ("usd", p_usd),
        ("expirada", p_expirada), ("escala", p_escala),
    ]:
        state["projects"][slug] = {"id": proj["id"], "name": proj["name"]}
    vitrina_positions = query(
        "project_positions?select=id,location_tag"
        f"&project_id=eq.{p_vitrina['id']}&order=location_tag"
    )
    state["vitrina_position_ids"] = {
        row["location_tag"]: row["id"] for row in vitrina_positions
    }

    stage(estimator, wm, users, {
        "cotizado": p_cotizado,
        "enviado": p_enviado,
        "aprobado": p_aprobado,
        "conjuntos": p_conjuntos,
        "portal": p_portal,
        "vitrina": p_vitrina,
        "despachado": p_despachado,
        "instalado": p_instalado,
        "rechazado": p_rechazado,
        "cambios": p_cambios,
        "usd": p_usd,
        "expirada": p_expirada,
        "escala": p_escala,
    }, state)

    with open(STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)

    print(f"org {ORG_ID} ({ORG_NAME})")
    print(f"org B {ORG_B_ID} ({ORG_B_NAME}) — isolation tenant")
    for key, email, role in ACCOUNTS:
        print(f"  {role:18} {email}  / {PASSWORD}")
    print(f"  clients: {list(client_ids)}")
    print(
        "  projects: " + ", ".join(
            f"{slug}={proj['id']}" for slug, proj in state["projects"].items()
        )
    )
    print(f"  cost items: {len(skus)} SKUs covered")
    print(f"  state file: {STATE_PATH}")
    print("DEMO FIXTURE — datos sintéticos de referencia (DEMO_60).")


# ------------------------------------------------------------------ stage


def stage(
    estimator: str,
    wm: str,
    users: dict[str, str],
    projects: dict[str, dict],
    state: dict,
) -> None:
    """Walk each fixture project through its lifecycle step.

    Idempotent: re-checks current state at every step so reruns only fill
    what is missing. Same HTTP surface the UI drives.
    """
    today = date.today().isoformat()

    def save_inputs(project_id: str, valid_until: str | None = None) -> None:
        prepared = api(
            estimator, "GET", f"/documents/projects/{project_id}/inputs/"
        )
        positions = []
        extras_by_tag = {
            "V04 Corredera 2 hojas terraza": [EXTRA_ITEMS[0]],
            "V07 Puerta principal": [EXTRA_ITEMS[0], EXTRA_ITEMS[1]],
        }
        for p in prepared["positions"]:
            def pick(options, current):
                if current:
                    return current
                if not options:
                    raise RuntimeError("no policy options for position")
                return options[0]["id"]

            placement_id = pick(
                p.get("placement_options") or [],
                p.get("manufacturing_placement_policy_id"),
            )
            handle_id = pick(
                p.get("handle_options") or [],
                p.get("handle_requirement_policy_id"),
            )
            reinforcement_id = pick(
                p.get("reinforcement_options") or [],
                p.get("reinforcement_cut_policy_id"),
            )

            # Merge workshop suggestions: one record per (bay, leaf); fill
            # missing drains/closing points so R07/R08 can pass.
            merged: dict[tuple, dict] = {}
            for ann in p.get("workshop_suggestions") or []:
                key = (ann.get("bay_id"), ann.get("leaf_id"))
                row = merged.setdefault(key, dict(ann))
                for k, v in ann.items():
                    if v not in (None, [], {}, "") and not row.get(k):
                        row[k] = v
            for row in merged.values():
                width = float(row.get("continuous_width_mm") or 0)
                drains = row.get("bottom_drain_holes_mm")
                if width <= 0 and drains:
                    # derive a bound from the largest declared coordinate
                    width = max(float(h) for h in drains) + 1.0
                if drains in (None, [], {}):
                    row["bottom_drain_holes_mm"] = None if width <= 800 else [
                        f"{width * i / 4:.2f}" for i in (1, 2, 3)
                    ]
                else:
                    clamped = sorted({float(h) for h in drains if 0 <= float(h) <= width})
                    if not clamped and width > 800:
                        clamped = [width * i / 4 for i in (1, 2, 3)]
                    row["bottom_drain_holes_mm"] = (
                        [f"{h:.2f}" for h in clamped] if clamped else None
                    )
                if row.get("closing_points_perimeter_mm") in (None, [], {}) and row.get("leaf_id") is not None:
                    row["closing_points_perimeter_mm"] = [
                        "0.00",
                        "700.00",
                        "1400.00",
                        "2100.00",
                        "2800.00",
                        "3500.00",
                    ]
                if not row.get("finish_class"):
                    row["finish_class"] = "WHITE"
                if row.get("has_coupler") is None:
                    row["has_coupler"] = False
            annotations = list(merged.values())

            handle_intents = []
            for policy in p.get("handle_requirements") or []:
                if str(policy.get("policy_id")) != str(handle_id):
                    continue
                for req in policy.get("requirements") or []:
                    refs = req.get("permitted_vertical_references") or [
                        "OUTER_BOTTOM"
                    ]
                    if (
                        req.get("host_member_side") == "BOTTOM"
                        and "LEAF_BOTTOM" in refs
                    ):
                        # Awning/proyectante: la manilla va en el travesaño
                        # inferior de la hoja — 1050 desde arriba cae fuera
                        # de la banda de montaje en hojas cortas.
                        reference, suggested = "LEAF_BOTTOM", "40.00"
                    else:
                        reference = (
                            "OUTER_BOTTOM"
                            if "OUTER_BOTTOM" in refs
                            else refs[0]
                        )
                        suggested = (
                            req.get("suggested_height_mm")
                            or req.get("requested_height_mm")
                            or "1050"
                        )
                        # Vano bajo (ventana sobre mesada): la altura
                        # estándar ~1050 puede quedar sobre la hoja — baja
                        # la manilla al centro de la hoja declarada.
                        outer_h = float(req.get("outer_height_mm") or 0)
                        rect = next(
                            (
                                r
                                for r in req.get("leaf_rects") or []
                                if str(r.get("placement_policy_id"))
                                == str(placement_id)
                            ),
                            (req.get("leaf_rects") or [None])[0],
                        )
                        if (
                            reference == "OUTER_BOTTOM"
                            and rect is not None
                            and outer_h > 0
                            and float(suggested)
                            > outer_h
                            - float(rect["leaf_top_from_outer_top_mm"])
                        ):
                            suggested = (
                                f"{outer_h - (float(rect['leaf_top_from_outer_top_mm']) + float(rect['leaf_height_mm']) / 2):.2f}"
                            )
                    handle_intents.append(
                        {
                            "schema_version": 1,
                            "bay_id": req["bay_id"],
                            "leaf_id": req.get("leaf_id"),
                            "handle_domain_slot": req["handle_domain_slot"],
                            "requested_height_mm": str(suggested),
                            "vertical_reference": reference,
                        }
                    )

            extras = extras_by_tag.get(p.get("location_tag") or "")
            positions.append(
                {
                    "position_id": p["position_id"],
                    "calculation_hash": p["calculation_hash"],
                    "location_tag": p["location_tag"] or "POS",
                    "manufacturing_placement_policy_id": placement_id,
                    "handle_requirement_policy_id": handle_id,
                    "reinforcement_cut_policy_id": reinforcement_id,
                    "workshop_annotations": annotations,
                    "structural_inputs": p.get("structural_inputs", []),
                    "glass_polishing": p.get("polishing_suggestions")
                    or p.get("glass_polishing")
                    or [],
                    "handle_intents": handle_intents,
                    "accessory_schedule": {
                        "schema_version": 1,
                        "coverage": "DECLARED" if extras else "NONE_REQUIRED",
                        "items": extras or [],
                    },
                    "legacy_handle_migration_confirmed": True,
                }
            )
        api(
            estimator,
            "PUT",
            f"/documents/projects/{project_id}/inputs/",
            {
                "payment_terms": "50% anticipo, 50% contra entrega",
                "quotation_valid_until": valid_until or str(
                    date.today() + timedelta(days=30)
                ),
                "doc_terms": {
                    "plazo_entrega": "15 días hábiles desde la aprobación",
                    "instalacion": "Instalación en obra incluida; andamios a cargo del cliente",
                    "exclusiones": "No incluye terminaciones de albañilería ni sellos perimetrales",
                    "garantia": "10 años perfiles, 5 años herrajes y vidrios",
                },
                "positions": positions,
            },
        )

    def priced_operation(
        project_id: str,
        valid_until: str | None = None,
        currency: str = "CLP",
    ) -> dict | None:
        detail = api(estimator, "GET", f"/projects/{project_id}/")
        # Inputs are only writable while the project stays in DRAFT — a
        # sealed revision makes them immutable, so reruns skip the PUT.
        if detail.get("status") == "DRAFT" and not detail.get("versions"):
            save_inputs(project_id, valid_until=valid_until)
        if detail.get("pricing_current") and detail.get(
            "current_pricing_operation_id"
        ):
            return {"id": detail["current_pricing_operation_id"]}
        operation = api(
            estimator,
            "POST",
            "/pricing/preview/",
            {
                "project_id": project_id,
                "pricing_mode": "COST_PLUS_MARGIN",
                "context_code": "DEFAULT",
                "currency": currency,
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

    def current_version(project_id: str) -> dict | None:
        detail = api(estimator, "GET", f"/projects/{project_id}/")
        items = detail.get("versions") or []
        return items[-1] if items else None

    def freeze(project_id: str, operation_id: str) -> dict | None:
        existing = current_version(project_id)
        if existing:
            # A sealed revision already exists — every fixture project
            # freezes once (P-APROBADO emits REV-B via an explicit call).
            return existing
        result = api(
            estimator,
            "POST",
            f"/documents/projects/{project_id}/freeze/",
            {"pricing_operation_id": operation_id, "confirmed": True},
            tolerate=(422,),
        )
        code = (result.get("error") or {}).get("code")
        if code != "applied_pricing_technical_binding_drift":
            if not result.get("id"):
                sys.exit(
                    f"freeze {project_id} -> {json.dumps(result)[:400]}"
                )
            return result
        # Snapshots/priced BOM went stale against the current designs —
        # the real recovery is reset-pricing, re-save the positions (fresh
        # bom_snapshot), re-apply pricing and freeze again.
        api(
            estimator,
            "POST",
            f"/projects/{project_id}/reset-pricing/",
            {
                "expected_operation_id": operation_id,
                "reason": "fixture: rebind pricing after drift",
                "confirmed": True,
            },
        )
        for row in query(
            f"project_positions?select=id&project_id=eq.{project_id}"
        ):
            det = api(estimator, "GET", f"/positions/{row['id']}/")
            api(
                estimator,
                "PUT",
                f"/positions/{row['id']}/",
                {
                    "location_tag": det.get("location_tag") or "POS",
                    "quantity": det["quantity"],
                    "design": det["design"],
                    "expected_updated_at": det["updated_at"],
                },
            )
        op = priced_operation(project_id)
        if not op:
            return None
        result = api(
            estimator,
            "POST",
            f"/documents/projects/{project_id}/freeze/",
            {"pricing_operation_id": op["id"], "confirmed": True},
        )
        return result if result.get("id") else None

    def successor_freeze(project_id: str) -> dict | None:
        # Sellar REV-B exige la sucesora real: abrir la revisión siguiente
        # (DRAFT), repreciarla y congelarla — congelar la misma operación
        # dos veces solo re-lee la REV-A existente.
        current = api(estimator, "GET", f"/projects/{project_id}/")
        api(
            estimator,
            "POST",
            f"/projects/{project_id}/successor/",
            {
                "expected_current_revision": current["current_revision"],
                "confirmed": True,
            },
            tolerate=(409,),
        )
        op = priced_operation(project_id)
        if not op:
            return None
        result = api(
            estimator,
            "POST",
            f"/documents/projects/{project_id}/freeze/",
            {"pricing_operation_id": op["id"], "confirmed": True},
            tolerate=(409,),
        )
        return result if result.get("id") else None

    def emit_doc01(version_id: str) -> None:
        api(
            estimator,
            "POST",
            "/documents/artifacts/",
            {
                "document_type": "DOC-01",
                "format": "PDF",
                "project_version_id": version_id,
            },
            tolerate=(409,),
        )

    def share_link(project_id: str) -> dict:
        return api(
            estimator, "POST", f"/projects/{project_id}/quote-link/"
        )

    def mint_portal_token(project_id: str, version_id: str) -> str:
        """Mint directo del enlace de portal (misma forma que el endpoint).

        Solo para proyectos que ya no admiten share (p.ej. la vitrina ya
        liberada a taller): el token vive solo aquí y en el state file.
        """
        token = secrets.token_hex(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        previous = query(
            "customer_approvals?select=created_by"
            f"&org_id=eq.{ORG_ID}&limit=1"
        )
        created_by = previous[0]["created_by"] if previous else None
        if not created_by:
            created_by = query(
                f"memberships?select=id&org_id=eq.{ORG_ID}&limit=1"
            )[0]["id"]
        sql(
            "INSERT INTO public.customer_approvals(id,org_id,project_id,"
            "project_version_id,token_hash,status,expires_at,created_by,"
            "channel) VALUES(%s,%s,%s,%s,%s,'PENDING',"
            "now()+interval '30 days',%s,'EMAIL')",
            (
                str(uuid.uuid5(NS, f"vitrina-link-{digest[:16]}")),
                ORG_ID,
                project_id,
                version_id,
                digest,
                created_by,
            ),
        )
        return token

    def persist_state() -> None:
        # Los tokens solo existen aquí — si el run muere antes del volcado
        # final quedan huérfanos. Persiste tras cada cambio de `state`.
        with open(STATE_PATH, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)

    def stored_token_live(slug: str) -> bool:
        # El .fixture-state.json sobrevive a un wipe de la base (el gate
        # corre db reset): el token solo vale si su hash existe de verdad.
        stored = state["portal"].get(slug)
        if not stored:
            return False
        digest = hashlib.sha256(stored.encode()).hexdigest()
        return bool(
            query(
                "customer_approvals?select=id"
                f"&token_hash=eq.{digest}&limit=1"
            )
        )

    def stored_token_anchor(slug: str) -> tuple[str, str] | None:
        # (project_id, revision_code) del enlace guardado — None si el
        # token no existe en la base. Detecta enlaces que quedaron en la
        # revisión equivocada tras un re-seal o apuntando a otro proyecto.
        stored = state["portal"].get(slug)
        if not stored:
            return None
        digest = hashlib.sha256(stored.encode()).hexdigest()
        approval = query(
            "customer_approvals?select=project_id,project_version_id"
            f"&token_hash=eq.{digest}&limit=1"
        )
        if not approval:
            return None
        version = query(
            "project_versions?select=revision_code"
            f"&id=eq.{approval[0]['project_version_id']}&limit=1"
        )
        if not version:
            return None
        return str(approval[0]["project_id"]), version[0]["revision_code"]

    def stored_token_status(slug: str) -> str | None:
        # Estado del link guardado (PENDING/APPROVED/…) o None si el
        # token no existe — un mint interrumpido antes del decide deja
        # el ancla correcta pero el link sin decidir.
        stored = state["portal"].get(slug)
        if not stored:
            return None
        digest = hashlib.sha256(stored.encode()).hexdigest()
        approval = query(
            "customer_approvals?select=status"
            f"&token_hash=eq.{digest}&limit=1"
        )
        return approval[0]["status"] if approval else None

    def approvals(project_id: str) -> list[dict]:
        out = api(
            estimator, "GET", f"/projects/{project_id}/quote-link/",
            tolerate=(404,),
        )
        return out if isinstance(out, list) else out.get("items", [])

    def portal_decide(
        token: str, decision: str, by: str, note: str, rut: str | None = None
    ) -> None:
        # La aprobación exige evidencia: RUT válido + checkbox literal de
        # aceptación. Cambios/rechazo solo piden nombre (+ comentario).
        payload: dict = {
            "decision": decision,
            "decided_by": by,
            "note": note,
        }
        if decision == "APPROVED":
            payload["decided_rut"] = rut or make_rut(13579246)
            payload["accepted"] = True
        public_api("POST", f"/portal/quotes/{token}/decide/", payload)

    def released_orders(version_id: str) -> list[dict]:
        released = api(
            wm, "POST", f"/production/versions/{version_id}/release/",
            tolerate=(409,),
        )
        if released.get("orders"):
            return released["orders"]
        # Already released — list existing workshop orders for the org.
        listed = api(
            wm, "GET", "/production/orders/?order_type=WORKSHOP_OT&page_size=50"
        )
        items = listed.get("items", [])
        return [
            order for order in items
            if str(order.get("project_version_id")) == str(version_id)
        ]

    def order_detail(order_id: str) -> dict:
        return api(wm, "GET", f"/production/orders/{order_id}/")

    def drive_steps(
        order_id: str,
        *,
        until_qc: bool = False,
        qc_fail: bool = False,
        block_first: bool = False,
        through_all: bool = False,
    ) -> None:
        detail = order_detail(order_id)
        steps = sorted(
            detail.get("steps") or [],
            key=lambda s: int(s.get("sequence") or 0),
        )
        for index, step in enumerate(steps):
            status = str(step.get("status") or "")
            code = str(step.get("code") or "")
            is_qc = code == "QC" or "qc" in code.lower()
            if block_first and index == 0:
                if status in ("PENDING", "READY", "IN_PROGRESS"):
                    api(
                        wm,
                        "POST",
                        f"/production/steps/{step['id']}/transition/",
                        {
                            "action": "BLOCK",
                            "note": "Falta perfil MARCO-60 blanco — compra en curso (OC fixture)",
                        },
                        tolerate=(409,),
                    )
                return
            if until_qc and not qc_fail and (
                is_qc or index >= len(steps) - 2
            ):
                break
            if status not in ("READY", "PENDING", "IN_PROGRESS"):
                continue
            if status != "IN_PROGRESS":
                started = api(
                    wm,
                    "POST",
                    f"/production/steps/{step['id']}/transition/",
                    {"action": "START"},
                    tolerate=(409, 422),
                )
                if (started.get("error") or {}).get("code") in (
                    _TERMINAL_ORDER_CODES
                ):
                    return  # terminal order on rerun — nothing left to drive
            complete: dict = {"action": "COMPLETE"}
            if is_qc:
                complete["qc_result"] = "FAIL" if qc_fail else "PASS"
                if qc_fail:
                    # La OT remake lee qc_item/note del payload sellado.
                    complete["qc_item"] = "SASH"
                    complete["note"] = "Soldadura abierta en esquina — remake ordenado"
            done = api(
                wm,
                "POST",
                f"/production/steps/{step['id']}/transition/",
                complete,
                tolerate=(409, 422),
            )
            if (done.get("error") or {}).get("code") == "step_ops_incomplete":
                # Member-op stations carry per-operation evidence: declare
                # every machining op the sealed routing assigns here.
                trace = api(wm, "GET", f"/production/orders/{order_id}/trace/")
                complete["ops_done"] = [
                    op["operation_id"]
                    for op in (trace.get("operations") or {}).get("items") or []
                    if op.get("host_kind") == "MEMBER" and op.get("station") == code
                ]
                api(
                    wm,
                    "POST",
                    f"/production/steps/{step['id']}/transition/",
                    complete,
                    tolerate=(409,),
                )
            if qc_fail and is_qc:
                return
        if not through_all:
            return

    def optimize_and_pack(order_id: str) -> None:
        result = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/optimize/",
            {"color": "WHITE"},
            tolerate=(409, 422),
        )
        code = (result.get("error") or {}).get("code")
        if code in (
            "work_order_replan_after_consumption",
            "work_order_dispatched",
            "work_order_installed",
            "work_order_completed",
        ):
            return  # rerun: the plan already consumed/shipped — leave it
        if code and code != "work_order_already_optimized":
            sys.exit(f"optimize {order_id} -> {json.dumps(result)[:300]}")

    # Terminal-order codes a rerun can legitimately hit — the order already
    # reached that state in an earlier pass; skipping is the idempotent path.
    _TERMINAL_ORDER_CODES = {
        "work_order_replan_after_consumption",
        "work_order_dispatched",
        "work_order_installed",
        "dispatch_requires_completed",
        "step_transition_invalid",
        "delivery_transition_invalid",
        "installation_requires_delivered",
        "delivery_requires_completed",
    }

    def _skip_on_terminal(order_id: str, label: str, result: dict) -> bool:
        code = (result.get("error") or {}).get("code")
        if not code or code == "work_order_already_optimized":
            return False
        if code in _TERMINAL_ORDER_CODES:
            return True
        sys.exit(f"{label} {order_id} -> {json.dumps(result)[:300]}")

    def pack_manifest(order_id: str) -> None:
        result = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/packing/",
            tolerate=(409, 422),
        )
        _skip_on_terminal(order_id, "packing", result)

    def dispatch(order_id: str) -> None:
        result = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/dispatch/",
            {"note": "Despacho programado fixture"},
            tolerate=(409, 422),
        )
        _skip_on_terminal(order_id, "dispatch", result)

    # 1×1 PNG, structurally valid (IHDR+IDAT+IEND CRCs) — stands in for the
    # receiver's on-glass signature the POD seal requires.
    _POD_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    def deliver(order_id: str, address: str, contact: str, installer: str) -> None:
        """SCHEDULED → ON_ROUTE → DELIVERED: the only path to a delivered
        order — install refuses anything short of a sealed POD."""
        scheduled = api(
            wm,
            "PUT",
            f"/production/orders/{order_id}/delivery/",
            {
                "scheduled_date": str(date.today()),
                "time_window": "AM",
                "address": address,
                "contact_name": contact,
                "installer_name": installer,
            },
            tolerate=(409, 422),
        )
        if _skip_on_terminal(order_id, "delivery-schedule", scheduled):
            return
        transitioned = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/delivery/transition/",
            {"status": "ON_ROUTE"},
            tolerate=(409, 422),
        )
        if _skip_on_terminal(order_id, "delivery-transition", transitioned):
            return
        result = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/delivery/confirm/",
            {
                "receiver_name": contact,
                "signature_png": _POD_PNG_B64,
            },
            tolerate=(409, 422),
        )
        _skip_on_terminal(order_id, "delivery-confirm", result)

    def install(order_id: str) -> None:
        result = api(
            wm,
            "POST",
            f"/production/orders/{order_id}/install/",
            {"note": "Instalación confirmada en terreno"},
            tolerate=(409, 422),
        )
        _skip_on_terminal(order_id, "install", result)

    # ---- P-COTIZADO: priced only -------------------------------------
    priced_operation(projects["cotizado"]["id"])

    # ---- P-PORTAL: revisada + aprobada (tokens recuperables) -----------
    # El token solo existe en la respuesta de emisión: este proyecto porta
    # el par reemplazada/aprobada con tokens siempre vigentes en state.
    # La existencia de REV-B es invariante del proyecto, no del state file:
    # si la base se borró hay que re-sellar la sucesora aunque el state
    # todavía tenga tokens.
    portal_id = projects["portal"]["id"]
    portal_detail = api(estimator, "GET", f"/projects/{portal_id}/")
    if len(portal_detail.get("versions") or []) < 2:
        op = priced_operation(portal_id)
        if op:
            frozen_a = freeze(portal_id, op["id"])
            if frozen_a:
                emit_doc01(frozen_a["id"])
                superseded = share_link(portal_id)
                frozen_b = successor_freeze(portal_id)
                if frozen_b and frozen_b.get("id"):
                    emit_doc01(frozen_b["id"])
                    state["portal"]["reemplazada"] = superseded["token"]
                    persist_state()
                    live = share_link(portal_id)
                    state["portal"]["aprobada"] = live["token"]
                    persist_state()
                    portal_decide(
                        live["token"],
                        "APPROVED",
                        "Marcela Molina Contreras",
                        "Aprobada la segunda revisión con vidrio templado.",
                    )
    else:
        # Reparación: `reemplazada` debe apuntar a la revisión vieja y
        # `aprobada` a la vigente — tokens stale (o minteados sobre la
        # revisión equivocada por corridas viejas) se re-mintan.
        portal_rev = portal_detail["current_revision"]
        anchor = stored_token_anchor("reemplazada")
        if anchor is None or anchor[0] != portal_id or anchor[1] == portal_rev:
            old = query(
                "project_versions?select=id"
                f"&project_id=eq.{portal_id}"
                f"&revision_code=neq.{portal_rev}&limit=1"
            )
            if old:
                state["portal"]["reemplazada"] = mint_portal_token(
                    portal_id, old[0]["id"]
                )
                persist_state()
        if stored_token_anchor("aprobada") != (
            portal_id,
            portal_rev,
        ) or stored_token_status("aprobada") != "APPROVED":
            current = query(
                "project_versions?select=id"
                f"&project_id=eq.{portal_id}"
                f"&revision_code=eq.{portal_rev}&limit=1"
            )
            if current:
                token = mint_portal_token(portal_id, current[0]["id"])
                state["portal"]["aprobada"] = token
                persist_state()
                portal_decide(
                    token,
                    "APPROVED",
                    "Marcela Molina Contreras",
                    "Aprobada la segunda revisión con vidrio templado.",
                )

    # ---- P-ENVIADO: sealed + live link (+ revoked sibling) -------------
    op = priced_operation(projects["enviado"]["id"])
    if op:
        frozen = freeze(projects["enviado"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            links = approvals(projects["enviado"]["id"])
            # El .fixture-state.json puede sobrevivir a un wipe de la base
            # (supabase stop --no-backup): las marcas solo se respetan si
            # la fila existe de verdad en customer_approvals.
            if state["portal"].get("revocada") and not any(
                link.get("status") == "REVOKED" for link in links
            ):
                del state["portal"]["revocada"]
            if state["portal"].get("vigente") and not any(
                link.get("status") == "PENDING" for link in links
            ):
                del state["portal"]["vigente"]
            if not state["portal"].get("revocada"):
                # Un link revocado deja historial — el portal muestra su
                # estado explícito al cliente que lo abra. Se emite y se
                # revoca una sola vez por fixture (token no recuperable).
                doomed = share_link(projects["enviado"]["id"])
                doom_id = next(
                    (
                        link["id"]
                        for link in approvals(projects["enviado"]["id"])
                        if link.get("status") == "PENDING"
                    ),
                    None,
                )
                if doom_id:
                    api(
                        estimator,
                        "POST",
                        f"/projects/{projects['enviado']['id']}/quote-links/"
                        f"{doom_id}/revoke/",
                        tolerate=(404, 409),
                    )
                    state["portal"]["revocada"] = doomed["token"]
                    persist_state()
            links = approvals(projects["enviado"]["id"])
            if not state["portal"].get("vigente"):
                # Siempre un único link vigente: el token solo existe en la
                # respuesta de emisión — si el state se perdió pero quedaron
                # links PENDING, se revocan y se emite uno recuperable.
                for link in links:
                    if link.get("status") == "PENDING":
                        api(
                            estimator,
                            "POST",
                            f"/projects/{projects['enviado']['id']}/quote-links/"
                            f"{link['id']}/revoke/",
                            tolerate=(404, 409),
                        )
                live = share_link(projects["enviado"]["id"])
                state["portal"]["vigente"] = live["token"]
                persist_state()

    # ---- P-APROBADO: superseded link + approved REV-B + anticipo -------
    op = priced_operation(projects["aprobado"]["id"])
    if op:
        existing_links = approvals(projects["aprobado"]["id"])
        decided = [link for link in existing_links if link.get("status") != "PENDING"]
        if not decided:
            frozen_a = freeze(projects["aprobado"]["id"], op["id"])
            emit_doc01(frozen_a["id"])
            # Enlace de REV-A: quedará revocado/reemplazado al re-sellar —
            # no se guarda token (el `reemplazada` del estado vive en
            # P-PORTAL/Casa Molina; aquí solo importa la evidencia).
            share_link(projects["aprobado"]["id"])
            # Re-seal: REV-B makes L1 the replaced revision.
            frozen_b = successor_freeze(projects["aprobado"]["id"])
            if frozen_b and frozen_b.get("id"):
                emit_doc01(frozen_b["id"])
            live = share_link(projects["aprobado"]["id"])
            # `aprobada` es exclusivo del proyecto P-PORTAL (Casa Molina):
            # este link queda como `parcial` — aprobado con anticipo
            # pagado, el estado "Abonado parcial" del portal.
            state["portal"]["parcial"] = live["token"]
            persist_state()
            portal_decide(
                live["token"],
                "APPROVED",
                "Daniela Reyes (Inmobiliaria Los Alerces)",
                "Aprobamos con la condición de entrega en 30 días.",
            )
        payments = api(
            estimator, "GET", f"/projects/{projects['aprobado']['id']}/payments/"
        )
        gross = payments.get("quote_total_gross")
        if gross and not payments.get("payments"):
            anticipo = (Decimal(str(gross)) / 2).quantize(Decimal("1"))
            api(
                estimator,
                "POST",
                f"/projects/{projects['aprobado']['id']}/payments/",
                {
                    "operation_key": f"fixture-anticipo-{projects['aprobado']['id']}",
                    "kind": "ANTICIPO",
                    "amount": str(anticipo),
                    "method": "TRANSFER",
                    "reference": "Transferencia BCI 004512",
                    "note": "Anticipo 50% — aprobación portal",
                },
            )

    # ---- P-CONJUNTOS: sealed quote-only (assemblies) --------------------
    op = priced_operation(projects["conjuntos"]["id"])
    if op:
        frozen = freeze(projects["conjuntos"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])

    # ---- P-VITRINA: sealed + released ----------------------------------
    op = priced_operation(projects["vitrina"]["id"])
    vitrina_orders: list[dict] = []
    if op:
        frozen = freeze(projects["vitrina"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            state["vitrina_version_id"] = frozen["id"]
            # Link de la vitrina ANTES de liberar (share exige QUOTED):
            # la página pública del portal necesita un proyecto de 12
            # posiciones para probar que la suma de líneas iguala el total.
            if not stored_token_live("vitrina"):
                for link in approvals(projects["vitrina"]["id"]):
                    if link.get("status") == "PENDING":
                        api(
                            estimator,
                            "POST",
                            f"/projects/{projects['vitrina']['id']}/quote-links/"
                            f"{link['id']}/revoke/",
                            tolerate=(404, 409),
                        )
                detail = api(
                    estimator, "GET", f"/projects/{projects['vitrina']['id']}/"
                )
                if detail.get("status") in ("QUOTED", "APPROVED"):
                    live = share_link(projects["vitrina"]["id"])
                    state["portal"]["vitrina"] = live["token"]
                    persist_state()
                else:
                    # Ya liberada a taller en un run previo que murió sin
                    # persistir el token — mint directo igual que el
                    # endpoint (hash sha256 del token).
                    state["portal"]["vitrina"] = mint_portal_token(
                        projects["vitrina"]["id"], frozen["id"]
                    )
                persist_state()
            vitrina_orders = released_orders(frozen["id"])
            for order in vitrina_orders:
                optimize_and_pack(order["id"])

    # ---- P-DESPACHADO / P-INSTALADO: full workshop arc ------------------
    despachado_orders: list[dict] = []
    op = priced_operation(projects["despachado"]["id"])
    if op:
        frozen = freeze(projects["despachado"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            despachado_orders = released_orders(frozen["id"])
            for order in despachado_orders:
                optimize_and_pack(order["id"])
                drive_steps(order["id"], until_qc=True)
                detail = order_detail(order["id"])
                qc_steps = [
                    s for s in detail.get("steps") or []
                    if str(s.get("code") or "") == "QC"
                ]
                for step in qc_steps:
                    if str(step.get("status")) in ("READY", "PENDING", "IN_PROGRESS"):
                        api(
                            wm,
                            "POST",
                            f"/production/steps/{step['id']}/transition/",
                            {"action": "START"},
                            tolerate=(409,),
                        )
                        api(
                            wm,
                            "POST",
                            f"/production/steps/{step['id']}/transition/",
                            {"action": "COMPLETE", "qc_result": "PASS"},
                            tolerate=(409,),
                        )
                # PACK es paso operativo: el manifiesto no lo completa.
                drive_steps(order["id"], through_all=True)
                pack_manifest(order["id"])
                dispatch(order["id"])
    if despachado_orders:
        state["orders"]["despachada"] = despachado_orders[0]["id"]

    instalado_orders: list[dict] = []
    op = priced_operation(projects["instalado"]["id"])
    if op:
        frozen = freeze(projects["instalado"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            instalado_orders = released_orders(frozen["id"])
            for order in instalado_orders:
                optimize_and_pack(order["id"])
                drive_steps(order["id"], through_all=True)
                pack_manifest(order["id"])
                dispatch(order["id"])
                deliver(
                    order["id"],
                    "Calle Lirquén 801, Penco",
                    "Inmobiliaria Los Alerces — recepción obra",
                    "Cuadrilla instalación A (fixture)",
                )
                install(order["id"])
    if instalado_orders:
        state["orders"]["instalada"] = instalado_orders[0]["id"]

    # ---- Vitrina OT pool: liberada / en producción / bloqueada / QC
    # fallido / remake / embalada ---------------------------------------
    pool = [o for o in vitrina_orders]
    pool.sort(key=lambda o: str(o.get("order_code") or o["id"]))
    if pool:
        state["orders"]["liberada"] = pool[0]["id"]
    if len(pool) > 1:
        drive_steps(pool[1]["id"], until_qc=True)
        state["orders"]["en_produccion"] = pool[1]["id"]
    if len(pool) > 2:
        drive_steps(pool[2]["id"], block_first=True)
        state["orders"]["bloqueada_faltante"] = pool[2]["id"]
    if len(pool) > 3:
        drive_steps(pool[3]["id"], until_qc=True, qc_fail=True)
        state["orders"]["qc_fallido"] = pool[3]["id"]
    if len(pool) > 4 and not state["orders"].get("remake"):
        # El remake nace de la orden que falló QC — el backend solo admite
        # re-fabricar órdenes bloqueadas o con falla registrada.
        remake = api(
            wm,
            "POST",
            f"/production/orders/{pool[3]['id']}/remake/",
            {"note": "Remake: perfil dañado en armado (fixture)"},
            tolerate=(409, 422),
        )
        if _skip_on_terminal(pool[3]["id"], "remake", remake) or remake.get(
            "error"
        ):
            # Rerun: the remake order already exists — recover its id.
            children = query(
                "orders?select=id&order_type=eq.WORKSHOP_OT"
                "&payload_json->>remake_reason=not.is.null&limit=1"
                f"&project_id=eq.{projects['vitrina']['id']}"
            )
            remake = {"order": children[0]} if children else {}
        state["orders"]["remake"] = (remake.get("order") or remake).get(
            "id", pool[3]["id"]
        )
    if len(pool) > 5:
        drive_steps(pool[5]["id"], through_all=True)
        pack_manifest(pool[5]["id"])
        state["orders"]["embalada"] = pool[5]["id"]
    state["orders"]["vitrina_all"] = [o["id"] for o in pool]

    # ---- P-ESCALA: released so the board carries ~100 live OTs -----------
    # La prueba de escala necesita la superficie real: ~100 tarjetas en el
    # tablero y una OT navegable. Se libera todo el proyecto y se optimiza
    # la primera OT para que las pestañas Corte/Mecanizado tengan datos.
    escala_orders: list[dict] = []
    op = priced_operation(projects["escala"]["id"])
    if op:
        frozen = freeze(projects["escala"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            escala_orders = released_orders(frozen["id"])
    if escala_orders:
        escala_orders.sort(key=lambda o: str(o.get("order_code") or o["id"]))
        state["orders"]["escala"] = escala_orders[0]["id"]
        state["orders"]["escala_all"] = [o["id"] for o in escala_orders]
        optimize_and_pack(escala_orders[0]["id"])

    # ---- Purchasing on the vitrina version -----------------------------
    # Purchasing writes son rol OWNER/WORKSHOP_MANAGER — el estimador solo lee.
    purchasing(wm, state.get("vitrina_version_id"))

    # ---- Retazos --------------------------------------------------------
    remnants(wm)

    # ---- P-RECHAZADO: client declined ----------------------------------
    op = priced_operation(projects["rechazado"]["id"])
    if op:
        frozen = freeze(projects["rechazado"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            links = approvals(projects["rechazado"]["id"])
            declined = [
                link for link in links
                if link.get("decision") == "DECLINED"
                or link.get("status") == "DECLINED"
            ]
            if not declined:
                for link in links:
                    if link.get("status") == "PENDING":
                        api(
                            estimator,
                            "POST",
                            f"/projects/{projects['rechazado']['id']}/quote-links/"
                            f"{link['id']}/revoke/",
                            tolerate=(404, 409),
                        )
                fresh = share_link(projects["rechazado"]["id"])
                portal_decide(
                    fresh["token"],
                    "DECLINED",
                    "Juan Carlos Muñoz Vera",
                    "El presupuesto supera lo previsto; no avanzamos.",
                )
                state["portal"]["rechazada"] = fresh["token"]
                persist_state()

    # ---- P-CAMBIOS: client asked for changes ---------------------------
    op = priced_operation(projects["cambios"]["id"])
    if op:
        frozen = freeze(projects["cambios"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            links = approvals(projects["cambios"]["id"])
            decided = [
                link for link in links if link.get("status") == "CHANGES_REQUESTED"
            ]
            if not decided:
                # El token solo existe en la respuesta de emisión: un
                # PENDING huérfano se revoca y se emite uno recuperable.
                for link in links:
                    if link.get("status") == "PENDING":
                        api(
                            estimator,
                            "POST",
                            f"/projects/{projects['cambios']['id']}/quote-links/"
                            f"{link['id']}/revoke/",
                            tolerate=(404, 409),
                        )
                token = share_link(projects["cambios"]["id"]).get("token")
                if token:
                    portal_decide(
                        token,
                        "CHANGES_REQUESTED",
                        "María José Fernández Roa",
                        "Cambiar el ventanal del acceso a oscilobatiente "
                        "y revisar el vidrio del dormitorio.",
                    )
                    state["portal"]["cambios"] = token
                    persist_state()

    # ---- P-USD: cotización en dólares — sin CTA de pago ----------------
    # La autoría comercial solo emite en la moneda de la org (CLP): la
    # mano de obra siempre se convierte CLP→trato y los snapshots FX solo
    # cubren USD→CLP, así que una previsualización currency='USD' no es
    # alcanzable. Para exponer el estado honesto "moneda no soportada" el
    # snapshot sellado se re-etiqueta USD y se re-hashea con la misma
    # función canónica — la cadena de evidencia queda intacta.
    op = priced_operation(projects["usd"]["id"])
    if op:
        frozen = freeze(projects["usd"]["id"], op["id"])
        if frozen:
            from dekopen_engine.documentary_canonical import (
                documentary_sha256_v1,
            )

            with psycopg.connect(DB, autocommit=True) as connection:
                connection.execute(
                    "SET session_replication_role = 'replica'"
                )
                (snapshot_text,) = connection.execute(
                    "SELECT snapshot_json::text FROM public.project_versions"
                    " WHERE id=%s",
                    (frozen["id"],),
                ).fetchone()
                snapshot = json.loads(snapshot_text)
                project_snapshot = snapshot.get("project")
                if project_snapshot.get("currency") != "USD":
                    project_snapshot["currency"] = "USD"
                    connection.execute(
                        "UPDATE public.project_versions SET snapshot_json=%s::jsonb,"
                        " snapshot_sha256=%s WHERE id=%s",
                        (
                            json.dumps(snapshot),
                            documentary_sha256_v1(snapshot),
                            frozen["id"],
                        ),
                    )
            emit_doc01(frozen["id"])
            if not stored_token_live("usd"):
                for link in approvals(projects["usd"]["id"]):
                    if link.get("status") == "PENDING":
                        api(
                            estimator,
                            "POST",
                            f"/projects/{projects['usd']['id']}/quote-links/"
                            f"{link['id']}/revoke/",
                            tolerate=(404, 409),
                        )
                live = share_link(projects["usd"]["id"])
                state["portal"]["usd"] = live["token"]
                persist_state()

    # ---- P-EXPIRADA: sealed quote past validity -------------------------
    yesterday = str(date.today() - timedelta(days=1))
    op = priced_operation(projects["expirada"]["id"], valid_until=yesterday)
    if op:
        frozen = freeze(projects["expirada"]["id"], op["id"])
        if frozen:
            emit_doc01(frozen["id"])
            links = approvals(projects["expirada"]["id"])
            if not links or not state["portal"].get("expirada"):
                live = share_link(projects["expirada"]["id"])
                state["portal"]["expirada"] = live["token"]
                persist_state()

    # ---- P-ESCALA: priced only ------------------------------------------
    priced_operation(projects["escala"]["id"])


def purchasing(token: str, version_id: str | None) -> None:
    """Eligibility → allocation → confirm → send → partial receipt."""
    if not version_id:
        return
    state_out = api(
        token, "GET", f"/purchasing/versions/{version_id}/", tolerate=(404,)
    )
    requirements = state_out.get("requirements") or []
    eligibilities = state_out.get("eligibilities") or []
    orders = state_out.get("orders") or []
    if not requirements:
        return
    by_type: dict[str, list[dict]] = {}
    for req in requirements:
        by_type.setdefault(str(req["order_type"]), []).append(req)
    supplier_names = {
        "SUPPLIER_PROFILE_PO": ("PVC-ANDINA", "PVC Andina S.A."),
        "SUPPLIER_GLASS_PO": ("VIDRIOS-BIO", "Vidrios Bío Bío Ltda."),
        "SUPPLIER_HARDWARE_PO": ("HERR-MAQUAL", "Herrajes Maqual SpA"),
        "SUPPLIER_PANEL_PO": ("PANEL-SUR", "Paneles del Sur Ltda."),
    }
    for order_type, reqs in by_type.items():
        identity, name = supplier_names.get(
            order_type, ("PROV-GEN", "Proveedor General Ltda.")
        )
        existing_el = next(
            (
                el
                for el in eligibilities
                if str(el.get("supplier_identity")) == identity
                and str(el.get("order_type")) == order_type
            ),
            None,
        )
        if existing_el:
            eligibility_id = existing_el["id"]
        else:
            created = api(
                token,
                "POST",
                f"/purchasing/versions/{version_id}/eligibilities/",
                {
                    "order_type": order_type,
                    "supplier_identity": identity,
                    "supplier_name": name,
                    "supplier_details": {
                        "email": "ventas@proveedor.fixture.cl",
                        "phone": "+56 41 555 0100",
                    },
                    "eligible_requirement_keys": sorted(
                        str(r["requirement_key"]) for r in reqs
                    ),
                    "evidence": {
                        "basis": "Lista de precios vigente + historial de cumplimiento (fixture)",
                    },
                    "version": 1,
                    "confirmed": True,
                },
                tolerate=(409,),
            )
            eligibility_id = created.get("id") or (
                existing_el and existing_el["id"]
            )
            if not eligibility_id:
                refreshed = api(
                    token, "GET", f"/purchasing/versions/{version_id}/"
                )
                existing_el = next(
                    (
                        el
                        for el in refreshed.get("eligibilities") or []
                        if str(el.get("supplier_identity")) == identity
                        and str(el.get("order_type")) == order_type
                    ),
                    None,
                )
                eligibility_id = existing_el and existing_el["id"]
        if not eligibility_id:
            continue
        for req in reqs:
            api(
                token,
                "PUT",
                f"/purchasing/requirements/{req['id']}/allocation/",
                {"supplier_eligibility_id": eligibility_id},
                tolerate=(409,),
            )
        api(
            token,
            "POST",
            f"/purchasing/versions/{version_id}/confirm/",
            {"order_type": order_type, "confirmed": True},
            tolerate=(409,),
        )

    refreshed = api(token, "GET", f"/purchasing/versions/{version_id}/")
    orders = refreshed.get("orders") or orders or []
    sent_orders: list[str] = []
    for order in orders:
        order_id = order["id"]
        status = str(order.get("status") or "")
        if status in ("DRAFT", "PENDING", "READY"):
            api(
                token,
                "POST",
                f"/purchasing/orders/{order_id}/send/",
                {
                    "confirmed": True,
                    "expected_at": str(date.today() + timedelta(days=14)),
                    "sent_to": "ventas@proveedor.fixture.cl",
                },
                tolerate=(409,),
            )
            status = "SENT"
        if status in ("SENT", "PARTIALLY_RECEIVED"):
            sent_orders.append(order_id)
    # Partial reception on the first sent order — leaves the rest SENT.
    if sent_orders:
        order_id = sent_orders[0]
        receiving = api(
            token,
            "GET",
            f"/inventory/orders/{order_id}/receiving/",
            tolerate=(404,),
        )
        lines = receiving.get("lines") or []
        receipt_lines = []
        for line in lines:
            outstanding = Decimal(str(line.get("outstanding_qty") or 0))
            if outstanding <= 0:
                continue
            received = (outstanding / 2).quantize(Decimal("0.01"))
            if received <= 0:
                received = outstanding
            receipt_lines.append(
                {
                    "order_line_id": line["id"],
                    "received_qty": str(received),
                    "rack_location": "B-12",
                    "note": "Recepción parcial fixture",
                }
            )
            if len(receipt_lines) >= 3:
                break
        if receipt_lines:
            api(
                token,
                "POST",
                f"/inventory/orders/{order_id}/receipts/",
                {
                    "receipt_key": f"fixture-partial-{order_id}",
                    "note": "Llegó la mitad del pedido — resto próxima semana",
                    "lines": receipt_lines,
                },
                tolerate=(409,),
            )


def remnants(token: str) -> None:
    authorities = api(token, "GET", "/inventory/bar-authorities/", tolerate=(404,))
    rows = authorities.get("authorities") or []
    existing = api(token, "GET", "/inventory/remnants/", tolerate=(404,))
    have = existing.get("remnants") or []
    wanted = [
        ("BAR", "Marco perimetral — retazo útil", "2 100", None, None, "A-03"),
        ("BAR", "Hoja corredera — retazo de sobra", "1 450", None, None, "A-03"),
        ("BAR", "Travesaño — retazo corto", "780", None, None, "B-01"),
    ]
    if len(have) >= 3:
        return
    for index, (kind, note, length, width, height, rack) in enumerate(wanted):
        if index < len(have):
            continue
        if kind == "BAR" and rows:
            authority = rows[index % len(rows)]
            api(
                token,
                "POST",
                "/inventory/remnants/",
                {
                    "kind": "BAR",
                    "stock_authority_id": authority["id"],
                    "length_mm": length.replace(" ", ""),
                    "rack_location": rack,
                    "notes": f"{note} (fixture)",
                },
                tolerate=(409, 422),
            )
        else:
            api(
                token,
                "POST",
                "/inventory/remnants/",
                {
                    "kind": "SHEET",
                    "sheet_workshop_sku": "VIDRIO-BASE",
                    "width_mm": "600",
                    "height_mm": "400",
                    "rack_location": "V-02",
                    "notes": "Retazo vidrio float 4mm (fixture)",
                },
                tolerate=(409, 422),
            )


if __name__ == "__main__":
    main()
