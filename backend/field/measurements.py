"""Medición en obra (P23 sobre D07).

El instalador graba el vano a 3 puntos desde el celular. La resolución del
número de fabricación sigue siendo del motor (`resolve_fabrication`, la
misma entrada que el editor) — el backend solo persiste la evidencia en
``site_measurements`` y aplica el registro D07 sobre la posición vía
``private.apply_site_measurement``, la función definer que escribe solo
las columnas de medición (INSTALLER no está en la política comercial de
``project_positions``).

Estados de aplicación:

* ``APPLIED`` — la posición quedó SITE_RECTIFIED en la revisión abierta.
* ``REVISION_CREATED`` — la revisión emitida no era editable y el
  estimador/caller con rol comercial abrió el sucesor; la medición aplicó
  sobre él.
* ``RECORDED`` — no hay revisión editable (proyecto cotizado/aprobado con
  producción viva, o el caller no puede escribir comercialmente): la
  medición queda como evidencia enlazada para el estimador.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from uuid import UUID

from django.db import DatabaseError, transaction

from authentication.errors import contract_error
from documents.repository import DocumentaryError, documentary_backend, one, rows
from projects.measurement import (
    _vano_record_payload,
    resolve_measurement_preview,
)
from projects.service import start_successor
from pricing.service import decoded

from .evidence import validated_photos

logger = logging.getLogger(__name__)


def _sqlstate(error: DatabaseError) -> str | None:
    return getattr(error.__cause__, "sqlstate", None)


def list_measurements(*, org_id: UUID, position_id: UUID) -> list[dict]:
    with documentary_backend():
        found = rows(
            "SELECT * FROM public.site_measurements "
            "WHERE org_id=%s AND position_id=%s ORDER BY created_at DESC",
            [str(org_id), str(position_id)],
        )
    return [measurement_public(row) for row in found]


def measurement_public(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "position_id": str(row["position_id"]),
        "operation_key": row["operation_key"],
        "rough_opening_input": decoded(row["rough_opening_input"]),
        "mounting_rule_id": (
            str(row["mounting_rule_id"]) if row["mounting_rule_id"] else None
        ),
        "notes": row["notes"],
        "photos": decoded(row["photos"]) or [],
        "previous_input": (
            decoded(row["previous_input"]) if row["previous_input"] else None
        ),
        "resolution": decoded(row["resolution"]) if row["resolution"] else None,
        "applied_state": row["applied_state"],
        "applied_revision_code": row["applied_revision_code"],
        "measured_by": str(row["measured_by"]) if row["measured_by"] else None,
        "taken_at": row["taken_at"].isoformat(),
        "created_at": row["created_at"].isoformat(),
    }


def submit_measurement(
    *,
    org_id: UUID,
    position_id: UUID,
    actor_id: UUID,
    operation_key: str,
    vano: dict | None,
    mounting_rule_id: UUID | None,
    notes: str | None,
    photos: list | None,
    order_id: UUID | None = None,
) -> dict:
    """Graba la medición de terreno. Idempotente por (org_id,
    operation_key): el reintento de la cola offline devuelve la fila
    original sin duplicar aplicación."""
    operation_key = (operation_key or "").strip()
    if not operation_key:
        raise contract_error(
            400, "operation_key_required", "La operación de terreno necesita su clave."
        )
    photo_entries = validated_photos(org_id=org_id, raw=photos)
    vano_payload = _vano_record_payload(vano)
    if vano_payload is None and mounting_rule_id is None:
        raise contract_error(
            400, "measurement_empty", "La medición necesita el vano o la regla de montaje."
        )
    with transaction.atomic(), documentary_backend():
        replay = rows(
            "SELECT * FROM public.site_measurements "
            "WHERE org_id=%s AND operation_key=%s",
            [str(org_id), operation_key],
        )
        if replay:
            return {
                "measurement": measurement_public(replay[0]),
                "replayed": True,
            }
        position = rows(
            """
            SELECT id, project_id, system_id, width_mm, height_mm,
                   rough_opening_input, mounting_rule_id, fabrication_lock,
                   measurement_state
            FROM public.project_positions
            WHERE id = %s AND org_id = %s
            """,
            [str(position_id), str(org_id)],
        )
        if not position:
            raise DocumentaryError("position_not_found")
        position = position[0]
        if order_id is not None:
            bound = rows(
                "SELECT id FROM public.orders WHERE id=%s AND org_id=%s "
                "AND order_type='WORKSHOP_OT' "
                "AND payload_json->>'position_id'=%s",
                [str(order_id), str(org_id), str(position_id)],
            )
            if not bound:
                raise contract_error(
                    400,
                    "position_order_mismatch",
                    "La posición medida no pertenece a esta OT.",
                )
        previous = {
            "rough_opening_input": position["rough_opening_input"],
            "mounting_rule_id": (
                str(position["mounting_rule_id"])
                if position["mounting_rule_id"] else None
            ),
            "fabrication_lock": position["fabrication_lock"],
            "measurement_state": position["measurement_state"],
        }
        # El motor resuelve antes de tocar la posición — igual que el
        # preview del editor. Un vano incoherente no se guarda.
        resolution = None
        if vano_payload is not None and mounting_rule_id is not None:
            preview = resolve_measurement_preview(
                org_id,
                system_id=position["system_id"],
                vano_payload=vano_payload,
                mounting_rule_id=mounting_rule_id,
                lock_payload=None,
                position_width_mm=Decimal(str(position["width_mm"])),
                position_height_mm=Decimal(str(position["height_mm"])),
            )
            resolution = preview["resolution"]

        applied_state = "RECORDED"
        applied_revision_code = None
        project = one(
            "SELECT id, status::text AS status, current_revision "
            "FROM public.projects WHERE id=%s AND org_id=%s",
            [str(position["project_id"]), str(org_id)],
            "project_not_found",
        )
        sealed = rows(
            "SELECT id FROM public.project_versions "
            "WHERE org_id=%s AND project_id=%s AND revision_code=%s",
            [str(org_id), str(project["id"]), str(project["current_revision"])],
        )
        draft_open = str(project["status"]) == "DRAFT" and not sealed
        revision_code = None
        if not draft_open:
            # La medición pide revisión: con rol comercial el sucesor se
            # abre aquí mismo (successor_in_production / permisos → el
            # registro queda como evidencia para el estimador). El atomic
            # interno aísla el fallo para que la transacción siga viva.
            try:
                with transaction.atomic():
                    successor = start_successor(org_id, project["id"])
                if successor.get("successor_created"):
                    revision_code = successor["current_revision"]
                    draft_open = True
            except Exception:
                logger.warning(
                    "Site measurement successor attempt failed (project %s)",
                    project["id"],
                )
                revision_code = None
        if draft_open:
            # El vano ausente nunca borra el registro: regla sola solo
            # recalibra el montaje.
            effective_vano = (
                vano_payload
                if vano_payload is not None
                else decoded(position["rough_opening_input"])
            )
            try:
                with transaction.atomic():
                    result = rows(
                        "SELECT private.apply_site_measurement(%s,%s,%s::jsonb,%s) AS out",
                        [
                            str(org_id),
                            str(position_id),
                            json.dumps(effective_vano),
                            str(mounting_rule_id) if mounting_rule_id else None,
                        ],
                    )
                out = result[0]["out"]
                if isinstance(out, str):
                    out = json.loads(out)
                applied_state = (
                    "REVISION_CREATED" if revision_code else "APPLIED"
                )
                applied_revision_code = revision_code
            except DatabaseError as error:
                if _sqlstate(error) != "42501":
                    raise
                applied_state = "RECORDED"
        # Orden ligada a la posición (la OT que instaló o instalará): el
        # evento va a su línea de tiempo para que el jefe lo vea sin abrir
        # el proyecto.
        order = rows(
            """
            SELECT id, order_code FROM public.orders
            WHERE org_id=%s AND order_type='WORKSHOP_OT'
              AND payload_json->>'position_id' = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            [str(org_id), str(position_id)],
        )
        row = one(
            """
            INSERT INTO public.site_measurements
                (org_id, project_id, position_id, operation_key,
                 rough_opening_input, mounting_rule_id, notes, photos,
                 previous_input, resolution, applied_state,
                 applied_revision_code, measured_by, taken_at)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,NOW())
            RETURNING *
            """,
            [
                str(org_id),
                str(position["project_id"]),
                str(position_id),
                operation_key,
                json.dumps(vano_payload) if vano_payload else "{}",
                str(mounting_rule_id) if mounting_rule_id else None,
                (notes or "").strip() or None,
                json.dumps(photo_entries),
                json.dumps(previous),
                json.dumps(resolution) if resolution else None,
                applied_state,
                applied_revision_code,
                str(actor_id),
            ],
            "site_measurement_rejected",
        )
        if order:
            rows(
                """
                INSERT INTO public.production_step_events
                    (org_id, order_id, event, actor_id, payload)
                VALUES (%s,%s,'WO_SITE_MEASURED',%s,%s::jsonb) RETURNING id
                """,
                [
                    str(org_id),
                    str(order[0]["id"]),
                    str(actor_id),
                    json.dumps(
                        {
                            "order_code": order[0]["order_code"],
                            "position_id": str(position_id),
                            "applied_state": applied_state,
                            "revision": applied_revision_code,
                        }
                    ),
                ],
            )
    return {"measurement": measurement_public(row), "replayed": False}
