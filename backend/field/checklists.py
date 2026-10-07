"""Checklist de instalación por posición (P23).

Cinco gestos — instalada, nivelada, sellada, regulada, limpia — más fotos
con contexto. La fila es una por (orden, unidad): la misma pantalla sube
una y otra vez desde la cola offline; ``operation_key`` deduplica y el
upsert por (order_id, unit_index) hace la edición idempotente.
"""

from __future__ import annotations

import json
from uuid import UUID

from django.db import transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one, rows
from pricing.service import decoded

from .evidence import validated_photos

_ITEMS = ("installed", "leveled", "sealed", "adjusted", "clean")


def check_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "order_id": str(row["order_id"]),
        "unit_index": row["unit_index"],
        "items": decoded(row["items"]),
        "notes": row["notes"],
        "photos": decoded(row["photos"]) or [],
        "checked_by": str(row["checked_by"]) if row["checked_by"] else None,
        "checked_at": row["checked_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


def list_checks(*, org_id: UUID, order_id: UUID) -> list[dict]:
    with documentary_backend():
        found = rows(
            "SELECT * FROM public.installation_checks "
            "WHERE org_id=%s AND order_id=%s ORDER BY unit_index NULLS FIRST",
            [str(org_id), str(order_id)],
        )
    return [check_public(row) for row in found]


def save_check(
    *,
    org_id: UUID,
    order_id: UUID,
    actor_id: UUID,
    unit_index: int | None,
    items: dict,
    notes: str | None,
    photos: list | None,
    operation_key: str,
) -> dict:
    operation_key = (operation_key or "").strip()
    if not operation_key:
        raise contract_error(
            400, "operation_key_required", "La operación de terreno necesita su clave."
        )
    normalized = {key: bool((items or {}).get(key)) for key in _ITEMS}
    if len(set(items or {})) > len(_ITEMS) or any(k not in _ITEMS for k in (items or {})):
        raise contract_error(
            400, "checklist_items_invalid", "Los ítems del checklist no son válidos."
        )
    photo_entries = validated_photos(org_id=org_id, raw=photos)
    with transaction.atomic(), documentary_backend():
        replay = rows(
            "SELECT * FROM public.installation_checks "
            "WHERE org_id=%s AND operation_key=%s",
            [str(org_id), operation_key],
        )
        if replay:
            return {"check": check_public(replay[0]), "replayed": True}
        order = rows(
            """
            SELECT id, order_code, status::text AS status,
                   payload_json::text AS payload_json
            FROM public.orders
            WHERE id = %s AND org_id = %s AND order_type = 'WORKSHOP_OT'
            FOR UPDATE
            """,
            [str(order_id), str(org_id)],
        )
        if not order:
            raise DocumentaryError("work_order_not_found")
        order = order[0]
        if unit_index is not None:
            payload = order["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            manifest = _manifest_units(payload)
            if int(unit_index) not in manifest:
                raise contract_error(
                    400, "checklist_unit_invalid", "La unidad no pertenece a la OT."
                )
        previous = rows(
            "SELECT items FROM public.installation_checks "
            "WHERE org_id=%s AND order_id=%s AND unit_index IS NOT DISTINCT FROM %s",
            [str(org_id), str(order_id), unit_index],
        )
        was_complete = bool(
            previous
            and all(
                bool((decoded(previous[0]["items"]) or {}).get(key))
                for key in _ITEMS
            )
        )
        row = one(
            """
            INSERT INTO public.installation_checks
                (org_id, order_id, unit_index, items, notes, photos,
                 operation_key, checked_by, checked_at)
            VALUES (%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s,NOW())
            ON CONFLICT (org_id, order_id, unit_index) NULLS NOT DISTINCT
            DO UPDATE SET
                items=EXCLUDED.items, notes=EXCLUDED.notes,
                photos=EXCLUDED.photos, checked_by=EXCLUDED.checked_by,
                checked_at=NOW(), updated_at=NOW()
            RETURNING *
            """,
            [
                str(org_id),
                str(order_id),
                unit_index,
                json.dumps(normalized),
                (notes or "").strip() or None,
                json.dumps(photo_entries),
                operation_key,
                str(actor_id),
            ],
            "installation_check_rejected",
        )
        # El evento marca la primera vez que la posición quedó completa —
        # reenviar el mismo checklist no duplica la línea de tiempo.
        if all(normalized.values()) and not was_complete:
            rows(
                """
                INSERT INTO public.production_step_events
                    (org_id, order_id, event, actor_id, payload)
                VALUES (%s,%s,'WO_INSTALL_CHECKED',%s,%s::jsonb) RETURNING id
                """,
                [
                    str(org_id),
                    str(order_id),
                    str(actor_id),
                    json.dumps(
                        {
                            "order_code": order["order_code"],
                            "unit_index": unit_index,
                            "items": normalized,
                        }
                    ),
                ],
            )
    return {"check": check_public(row), "replayed": False}


def _manifest_units(payload) -> set[int]:
    from .service import _manifest_units as manifest

    return manifest(payload)
