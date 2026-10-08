"""Textos «¿Cómo se calcula?» — espejo literal de docs/analytics/metricas.md.

Cada cifra del panel enlaza a su definición: fórmula, fuente y período. Si
una definición cambia, cambian el documento y este módulo en el mismo
commit."""

from __future__ import annotations

# metric key -> {title, formula, source, period}
DEFINITIONS: dict[str, dict[str, str]] = {
    "conversion_pct": {
        "title": "Tasa de conversión",
        "formula": "100 × aprobadas / (aprobadas + rechazadas), sobre la "
        "cohorte de revisiones emitidas en el período. Pendientes y «pide "
        "cambios» no entran al denominador hasta que el cliente decide.",
        "source": "project_versions.emitted_at × customer_approvals.status",
        "period": "fecha de emisión dentro del período",
    },
    "avg_decision_days": {
        "title": "Tiempo medio emisión → decisión",
        "formula": "Promedio de decided_at − emitted_at en días, sólo sobre "
        "revisiones decididas (APPROVED/DECLINED).",
        "source": "project_versions × customer_approvals.decided_at",
        "period": "emisiones del período que ya decidió el cliente",
    },
    "pipeline_net": {
        "title": "Monto en pipeline",
        "formula": "Suma del neto sellado (pricing.result.project_net) de "
        "revisiones emitidas en el período aún pendientes: PENDIENTE, "
        "EN_CAMBIOS o VENCIDA según expires_at.",
        "source": "project_versions.snapshot_json → pricing.result",
        "period": "emisión en período, sin decisión al corte",
    },
    "real_margin_pct": {
        "title": "Margen real vs. cotizado",
        "formula": "Cotizado: 100 × (project_net − deal_cost_net) / "
        "project_net de la revisión aprobada. Real: 100 × (project_net − "
        "costo_real) / project_net, con costo_real = consumos de inventario "
        "valorizados a precio OC (respaldo lista de costos) + retazos a "
        "precio por mm/mm² + horas de estación × tarifa horaria + remakes. "
        "Sólo obras con toda su producción terminada.",
        "source": "snapshot_json.pricing × inventory_movements × "
        "production_steps",
        "period": "obras aprobadas (decided_at) en el período",
    },
    "deviation_pp": {
        "title": "Desviación del margen (pp)",
        "formula": "margen_real_pct − margen_cotizado_pct, promediado sobre "
        "las obras terminadas del período.",
        "source": "mismas fuentes del margen real",
        "period": "obras aprobadas y terminadas en el período",
    },
    "merma_real_mm": {
        "title": "Merma real (barras)",
        "formula": "mm consumidos − mm productivos − mm de retazos "
        "devueltos + mm desechados. Consumidos: barras del plan acreditadas "
        "por el ledger (cantidad × largo del plan) + retazos consumidos. Una "
        "barra sin largo en el plan deja la OT «sin medir» y sale del "
        "agregado — nunca suma cero.",
        "source": "inventory_movements × optimization.bars del payload",
        "period": "OT que consumieron o terminaron en el período",
    },
    "merma_plan_mm": {
        "title": "Merma plan (barras)",
        "formula": "Σ process_waste_mm declarado por el optimizador en cada "
        "OT (kerf + refilados + colas no reutilizables).",
        "source": "orders.payload_json → optimization.bars.metrics",
        "period": "OT que reportan en el período",
    },
    "aprovechamiento_pct": {
        "title": "Aprovechamiento de barras",
        "formula": "100 × mm productivos / mm consumidos, por OT y en "
        "agregado (Σ productivo / Σ consumido).",
        "source": "optimization.bars.metrics.productive_length_mm × ledger",
        "period": "OT que reportan en el período",
    },
    "station_times": {
        "title": "Tiempos por estación",
        "formula": "Promedio y mediana de finished_at − started_at de los "
        "pasos DONE, por código de estación.",
        "source": "production_steps.started_at/finished_at",
        "period": "pasos terminados en el período",
    },
    "ot_punctuality": {
        "title": "OT a tiempo",
        "formula": "WO_COMPLETED::date ≤ MIN(deliveries.scheduled_date) → "
        "A_TIEMPO; mayor → ATRASADA; sin entrega agendada → SIN_PLAZO "
        "(listadas aparte, fuera de la tasa).",
        "source": "production_step_events × deliveries",
        "period": "OT completadas en el período",
    },
    "deliveries_on_time_pct": {
        "title": "Entregas a tiempo",
        "formula": "Entregadas (evento WO_DELIVERY_DELIVERED o updated_at "
        "si quedó DELIVERED sin evento) en fecha ≤ scheduled_date, sobre "
        "entregadas + atrasadas. Fallidas y pendientes se listan aparte.",
        "source": "deliveries × production_step_events",
        "period": "scheduled_date dentro del período",
    },
    "incidents": {
        "title": "Incidencias de obra",
        "formula": "Reportadas en el período, por tipo "
        "(DAMAGE/WRONG_MEASURE/MISSING/ADJUSTMENT) y por tipología de la "
        "unidad afectada (OT → position → typology); abiertas a la fecha.",
        "source": "site_incidents × orders.payload_json → position_id",
        "period": "reported_at dentro del período",
    },
    "warranties": {
        "title": "Garantías",
        "formula": "Tickets WARRANTY abiertos (OPEN|SCHEDULED|IN_PROGRESS) "
        "a la fecha, creados en el período, y con warranty_until venciendo "
        "en 60 días.",
        "source": "service_tickets",
        "period": "abiertas hoy; creadas en el período",
    },
    "margin_causes": {
        "title": "Causas de la diferencia de margen",
        "formula": "Descomposición por obra: material (consumo real menos "
        "material cotizado), remake (material + horas de las OT remake × "
        "tarifa), horas (mano de obra real menos la cotizada), descarte "
        "(SCRAP valorizado) y descuento (rebaja aplicada en la cotización). "
        "El costo de instalación se declara no medido.",
        "source": "inventory_movements × production_steps × pricing "
        "input_snapshot",
        "period": "revisión aprobada vigente de la obra",
    },
}
