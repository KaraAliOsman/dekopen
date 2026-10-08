"""Analítica de decisión (P24): conversión, margen real vs. cotizado, merma,
tiempos de estación e instalación/postventa.

Las cifras las calculan las funciones ``private.analytics_*`` (SECURITY
DEFINER, org verificada por claims JWT, jamás agregadas entre orgs) — la SQL
versionada que ``docs/analytics/metricas.md`` documenta métrica a métrica. Este
módulo es la envoltura delgada: período, forma de salida y CSV."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from authentication.errors import contract_error
from analytics.definitions import DEFINITIONS
from documents.repository import rows

CL = ZoneInfo("America/Santiago")

READER_ROLES = ("OWNER", "WORKSHOP_MANAGER")

EXPORTABLE = (
    "quotes",
    "obras",
    "ots",
    "steps",
    "remakes",
    "deliveries",
    "incidents",
    "warranties",
)

_SECTION_SQL = {
    "sales": "SELECT private.analytics_sales(%s::uuid,%s::date,%s::date) AS v",
    "margins": "SELECT private.analytics_margins(%s::uuid,%s::date,%s::date) AS v",
    "production": "SELECT private.analytics_production(%s::uuid,%s::date,%s::date) AS v",
    "field": "SELECT private.analytics_field(%s::uuid,%s::date,%s::date) AS v",
}


def period_from(query) -> tuple[date, date]:
    """desde/hasta en días calendario America/Santiago (inclusivos). Sin
    parámetros: últimos 30 días terminando hoy — la ventana por defecto del
    panel (decisión registrada en docs/decisions/valores-por-defecto.md)."""
    hasta_raw = (query.get("hasta") or "").strip()
    desde_raw = (query.get("desde") or "").strip()
    hasta = (
        _parse_day(hasta_raw)
        if hasta_raw
        else date.today()
    )
    desde = _parse_day(desde_raw) if desde_raw else hasta - timedelta(days=30)
    if desde > hasta:
        raise contract_error(
            400,
            "analytics_period_invalid",
            "El período empieza después de que termina.",
        )
    return desde, hasta


def _parse_day(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise contract_error(
            400,
            "analytics_period_invalid",
            "El período debe venir como AAAA-MM-DD.",
        )


def overview(org_id: UUID, desde: date, hasta: date) -> dict[str, Any]:
    """Las cuatro secciones en un viaje — dentro del scope autenticado el rol
    ya es ``authenticated`` y las claims JWT están activas, así que la guardia
    interna de cada función valida membresía y permiso financiero."""
    out: dict[str, Any] = {}
    for key, sql in _SECTION_SQL.items():
        out[key] = _jsonb(rows(sql, [str(org_id), desde, hasta])[0]["v"])
    return {
        "schema": "dekopen.analytics.overview.v1",
        "period": {"desde": str(desde), "hasta": str(hasta)},
        "definitions": DEFINITIONS,
        **out,
    }


def margin_breakdown(org_id: UUID, project_id: UUID) -> dict[str, Any]:
    found = rows(
        "SELECT private.analytics_margin_breakdown(%s::uuid,%s::uuid) AS v",
        [str(org_id), str(project_id)],
    )
    return _jsonb(found[0]["v"])


def export_csv(
    org_id: UUID, metric: str, desde: date, hasta: date
) -> tuple[str, str]:
    """Detalle de la métrica como CSV. Las filas son las mismas que muestra el
    drill-down de la página — exportar nunca inventa una cifra distinta."""
    if metric not in EXPORTABLE:
        raise contract_error(
            400,
            "analytics_metric_unknown",
            "Esa métrica no tiene detalle exportable.",
        )
    data = _jsonb(
        rows(
            "SELECT private.analytics_export_rows(%s::uuid,%s,%s::date,%s::date) AS v",
            [str(org_id), metric, desde, hasta],
        )[0]["v"]
    )
    items = data if isinstance(data, list) else []
    columns: list[str] = []
    for item in items:
        for key in item:
            if key not in columns:
                columns.append(key)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for item in items:
        writer.writerow([_csv_value(item.get(col)) for col in columns])
    filename = f"dekopen-analitica-{metric}-{desde}-a-{hasta}.csv"
    return filename, buffer.getvalue()


def _jsonb(value: Any) -> Any:
    """psycopg entrega JSONB como ``str`` — el contrato HTTP es objeto."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value
