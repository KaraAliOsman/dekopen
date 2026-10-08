"""P18 — evaluación térmica OGUC art. 4.1.10 por proyecto y posición.

El motor es la única fuente de números: aquí sólo se cargan los insumos
declarados del catálogo (con su procedencia) y se traduce la salida del
motor a la API. Sin dato certificado no hay afirmación de cumplimiento —
los veredictos que devuelve el motor ya lo garantizan.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from dekopen_engine.contour import contour_area
from dekopen_engine.models import PieceOrigin, ProfileRole
from dekopen_engine.thermal import (
    FrameUfInput,
    PerformanceTestInput,
    PositionThermalResult,
    SpacerPsiInput,
    ThermalCatalogInput,
    ThermalMissing,
    ThermalModuleInput,
    UwComputation,
    compute_uw,
    orientation_compliance,
    position_compliance,
    resolve_classes,
)
from engine_api.adapter import (
    calculate_from_api,
    evaluate_assembly_from_api,
    is_product_tree,
    parse_product_model,
)
from engine_api.repository import SystemParamsRepository
from pricing.repository import rows
from pricing.service import decoded
from projects.service import POSITION_COLUMNS, missing

_M2_PER_MM2 = Decimal("1e-6")


def _catalog_for(org_id: UUID, system_id: UUID) -> ThermalCatalogInput:
    """Autoridades térmicas del sistema: filas del taller sombrean las
    globales del mismo sistema; los separadores son un registro compartido
    (NULL org = global, el de la org manda)."""
    demo = rows(
        "SELECT is_demo FROM public.profile_systems WHERE id=%s AND "
        "(org_id=%s OR (org_id IS NULL AND is_global))",
        [system_id, org_id],
    )
    spacers = {
        row["code"]: SpacerPsiInput(
            code=row["code"],
            name=row["name"],
            psi_w_m_k=Decimal(str(row["psi_w_m_k"])),
            provenance=row["data_provenance"],
            verified=row["technical_reviewed_at"] is not None,
        )
        for row in rows(
            "SELECT DISTINCT ON (code) code, name, psi_w_m_k, "
            "data_provenance, technical_reviewed_at "
            "FROM public.glazing_spacers WHERE is_active "
            "AND (org_id=%s OR org_id IS NULL) "
            "ORDER BY code, org_id NULLS LAST",
            [org_id],
        )
    }
    frame_uf = {
        row["member_group"]: FrameUfInput(
            member_group=row["member_group"],
            uf_w_m2k=Decimal(str(row["uf_w_m2k"])),
            provenance=row["data_provenance"],
            verified=row["technical_reviewed_at"] is not None,
            source=row["source_ref"],
        )
        for row in rows(
            "SELECT DISTINCT ON (member_group) member_group, uf_w_m2k, "
            "source_ref, data_provenance, technical_reviewed_at "
            "FROM public.system_frame_uf WHERE is_active AND system_id=%s "
            "AND (org_id=%s OR org_id IS NULL) "
            "ORDER BY member_group, org_id NULLS LAST",
            [system_id, org_id],
        )
    }
    tests = [
        PerformanceTestInput(
            air_class=row["air_class"],
            water_class=row["water_class"],
            wind_class=row["wind_class"],
            report_ref=row["report_ref"],
            laboratory=row["laboratory"],
            tested_on=str(row["tested_on"]) if row["tested_on"] else None,
            tested_width_mm=(
                Decimal(str(row["tested_width_mm"]))
                if row["tested_width_mm"] is not None
                else None
            ),
            tested_height_mm=(
                Decimal(str(row["tested_height_mm"]))
                if row["tested_height_mm"] is not None
                else None
            ),
            typology_scope=row["typology_scope"],
            provenance=row["data_provenance"],
            verified=row["technical_reviewed_at"] is not None,
        )
        for row in rows(
            "SELECT air_class, water_class, wind_class, report_ref, "
            "laboratory, tested_on, tested_width_mm, tested_height_mm, "
            "typology_scope, data_provenance, technical_reviewed_at "
            "FROM public.system_performance_tests "
            "WHERE is_active AND system_id=%s AND (org_id=%s OR org_id IS NULL)",
            [system_id, org_id],
        )
    ]
    return ThermalCatalogInput(
        frame_uf=frame_uf,
        spacers=spacers,
        tests=tests,
        demo=bool(demo and demo[0]["is_demo"]),
    )


def _face_widths(params, coupler_articles) -> dict[str, Decimal]:
    widths = {
        sku: article.face_width_mm
        for sku, article in params.effective_profile_articles.items()
        if article.face_width_mm is not None
    }
    for sku, article in (coupler_articles or {}).items():
        if article.face_width_mm is not None:
            widths.setdefault(sku, article.face_width_mm)
    return widths


def _module_area_m2(module) -> Decimal:
    """Superficie del hueco del módulo: polígono exacto con bulges cuando el
    módulo tiene contorno, rectángulo nominal si no."""
    if module.contour is not None:
        return (
            contour_area(module.contour.vertices, module.contour.bulges)
            * _M2_PER_MM2
        )
    return module.width_mm * module.height_mm * _M2_PER_MM2


def _unevaluated(reason: str) -> UwComputation:
    return UwComputation(
        status="UNKNOWN",
        ag_m2=Decimal("0"),
        af_m2=Decimal("0"),
        lg_m=Decimal("0"),
        missing=[ThermalMissing(code="DESIGN_INVALID", detail=reason)],
    )


def position_thermal(
    *,
    org_id: UUID,
    position: dict,
    zone: str | None,
    use: str,
    orientation: str | None,
) -> tuple[PositionThermalResult, Decimal]:
    """Uw + clases + veredicto de una posición. Devuelve además la
    superficie del complejo (m²) para el % por orientación del panel."""
    repository = SystemParamsRepository()
    params = repository.load_visible(position["system_id"], org_id)
    coupler_articles = repository.load_coupler_articles(
        position["system_id"], org_id
    )
    catalog = _catalog_for(org_id, position["system_id"])
    tree = decoded(position["parametric_tree"])
    modules: list[ThermalModuleInput] = []
    coupler_cuts = []
    surface_m2 = Decimal("0")
    invalid_reason = None
    try:
        if is_product_tree(tree):
            model = parse_product_model(tree)
            evaluation = evaluate_assembly_from_api(
                product=model,
                color=position["color_interior"],
                color_exterior=position["color_exterior"],
                params=params,
                coupler_articles=coupler_articles,
            )
            if (
                evaluation.status.value != "VALID"
                or evaluation.bom is None
                or any(module.result is None for module in evaluation.modules)
            ):
                invalid_reason = "El diseño no evalúa completo."
            else:
                by_id = {module.id: module for module in model.assembly.modules}
                for module_eval in evaluation.modules:
                    module = by_id.get(module_eval.module_id)
                    if module is None or module_eval.result is None:
                        continue
                    area = _module_area_m2(module)
                    surface_m2 += area
                    modules.append(
                        ThermalModuleInput(result=module_eval.result, area_m2=area)
                    )
                coupler_cuts = [
                    cut
                    for cut in evaluation.bom.profile_cuts
                    if cut.role is ProfileRole.COUPLER
                    and cut.origin is PieceOrigin.PRODUCT
                ]
        else:
            result = calculate_from_api(
                parametric_tree=tree,
                nominal_width_mm=Decimal(str(position["width_mm"])),
                nominal_height_mm=Decimal(str(position["height_mm"])),
                color=position["color_interior"],
                color_exterior=position["color_exterior"],
                params=params,
            )
            surface_m2 = (
                Decimal(str(position["width_mm"]))
                * Decimal(str(position["height_mm"]))
                * _M2_PER_MM2
            )
            modules = [ThermalModuleInput(result=result, area_m2=surface_m2)]
    except Exception:  # noqa: BLE001 — cualquier invalidez = SIN DATOS
        invalid_reason = "El diseño no evalúa completo."

    if invalid_reason is not None or not modules:
        uw = _unevaluated(invalid_reason or "Sin módulos evaluables.")
    else:
        uw = compute_uw(
            modules=modules,
            params=params,
            catalog=catalog,
            coupler_cuts=coupler_cuts,
            face_widths=_face_widths(params, coupler_articles),
        )
        # La superficie del complejo para la Tabla 3 incluye los acopladores.
        surface_m2 = uw.ag_m2 + uw.af_m2 + sum(
            piece.area_m2
            for module in modules
            for piece in module.result.panels
        )
    classes = resolve_classes(
        catalog,
        typology=position.get("typology"),
        width_mm=Decimal(str(position["width_mm"])),
        height_mm=Decimal(str(position["height_mm"])),
    )
    return (
        position_compliance(
            uw=uw, classes=classes, zone=zone, use=use, orientation=orientation
        ),
        surface_m2,
    )


def project_thermal(org_id: UUID, project_id: UUID) -> dict:
    """Panel de cumplimiento del proyecto: una fila por posición y una por
    orientación con paramentos. El veredicto del proyecto es el peor."""
    project = rows(
        "SELECT id, code, thermal_zone, thermal_use, thermal_wall_areas "
        "FROM public.projects WHERE id=%s AND org_id=%s",
        [project_id, org_id],
    )
    if not project:
        missing()
    project = project[0]
    wall_areas = decoded(project["thermal_wall_areas"]) or {}
    zone = project["thermal_zone"]
    use = project["thermal_use"] or "RESIDENTIAL"

    positions = rows(
        f"SELECT {','.join(POSITION_COLUMNS)} "
        "FROM public.project_positions "
        "WHERE org_id=%s AND project_id=%s ORDER BY position_index",
        [org_id, project_id],
    )

    evaluated = []
    for position in positions:
        verdict, surface = position_thermal(
            org_id=org_id,
            position=position,
            zone=zone,
            use=use,
            orientation=position["thermal_orientation"],
        )
        evaluated.append(
            {
                "id": position["id"],
                "position_index": position["position_index"],
                "location_tag": position["location_tag"],
                "quantity": position["quantity"],
                "typology": position["typology"],
                "thermal_orientation": position["thermal_orientation"],
                "width_mm": str(position["width_mm"]),
                "height_mm": str(position["height_mm"]),
                "surface_m2": surface,
                "result": verdict,
            }
        )

    # % por orientación (residencial): agrega las posiciones por su
    # orientación declarada — la columna de U del límite es la de la ventana
    # de mayor U (texto oficial, letra b).
    orientations = []
    if use == "RESIDENTIAL" and zone:
        buckets: dict[str, list[dict]] = {}
        for item in evaluated:
            orientation = item["thermal_orientation"]
            if orientation in ("N", "OP", "S", "OGT"):
                buckets.setdefault(orientation, []).append(item)
        for orientation, items in buckets.items():
            total = sum(
                item["surface_m2"] * Decimal(item["quantity"]) for item in items
            )
            worst = max(
                (
                    item["result"].uw
                    for item in items
                    if item["result"].uw.status == "OK"
                ),
                key=lambda uw: uw.uw_w_m2k,
                default=None,
            )
            wall = wall_areas.get(orientation)
            orientations.append(
                orientation_compliance(
                    zone=zone,
                    orientation=orientation,
                    window_area_m2=total,
                    wall_area_m2=(
                        Decimal(str(wall)) if wall is not None else None
                    ),
                    max_uw=worst.uw_w_m2k if worst else None,
                    max_uw_authority=worst.authority if worst else None,
                )
            )

    order = {
        "FAILS": 3,
        "INSUFFICIENT_DATA": 2,
        "COMPLIES": 1,
        "NO_REQUIREMENT": 0,
    }
    verdicts = [item["result"].verdict for item in evaluated]
    verdicts += [out.verdict for out in orientations]
    overall = max(verdicts, key=lambda item: order[item], default="NO_REQUIREMENT")
    return {
        "project_id": str(project_id),
        "thermal_zone": zone,
        "thermal_use": use,
        "thermal_wall_areas": wall_areas,
        "positions": [
            {
                key: value
                for key, value in item.items()
                if key != "result"
            }
            | {
                "thermal": _public_result(item["result"]),
            }
            for item in evaluated
        ],
        "orientations": [
            _public_out(out) for out in orientations
        ],
        "verdict": overall,
    }


def _public_result(result: PositionThermalResult) -> dict:
    """Salida del motor → payload de API (Decimal en string canónico)."""
    return _canonical(result.model_dump())


def _public_out(result) -> dict:
    return _canonical(result.model_dump())


def _canonical(value: dict) -> dict:
    from dekopen_engine.snapshot import _json_value

    return _json_value(value)


# ─── §8 — alternativa más barata que sí cumple ─────────────────────────────


def _swap_glass(tree, glass_sku: str):
    """Devuelve el árbol con ``glass_article_sku`` reemplazado en todo BAY."""
    def walk(node):
        changed = dict(node)
        if changed.get("type") == "BAY" or changed.get("opening_type"):
            changed["glass_article_sku"] = glass_sku
        children = changed.get("children") or []
        changed["children"] = [walk(child) for child in children]
        return changed

    import copy

    new_tree = copy.deepcopy(tree)
    if isinstance(new_tree, dict) and new_tree.get("version") == "product-v2":
        for module in new_tree.get("assembly", {}).get("modules", []):
            module["tree"] = walk(module.get("tree", {}))
        return new_tree
    return walk(new_tree)


def _evaluate_tree_uw(
    *,
    org_id,
    tree,
    system_id,
    width_mm,
    height_mm,
    color,
    color_exterior,
):
    """Re-evalúa un árbol candidato y devuelve (UwComputation, área)."""
    repository = SystemParamsRepository()
    params = repository.load_visible(system_id, org_id)
    coupler_articles = repository.load_coupler_articles(system_id, org_id)
    catalog = _catalog_for(org_id, system_id)
    if is_product_tree(tree):
        model = parse_product_model(tree)
        evaluation = evaluate_assembly_from_api(
            product=model,
            color=color,
            color_exterior=color_exterior,
            params=params,
            coupler_articles=coupler_articles,
        )
        if (
            evaluation.status.value != "VALID"
            or evaluation.bom is None
            or any(module.result is None for module in evaluation.modules)
        ):
            raise ValueError("candidato inválido")
        by_id = {module.id: module for module in model.assembly.modules}
        modules = [
            ThermalModuleInput(
                result=module_eval.result,
                area_m2=_module_area_m2(by_id[module_eval.module_id]),
            )
            for module_eval in evaluation.modules
            if module_eval.result is not None and module_eval.module_id in by_id
        ]
        coupler_cuts = [
            cut
            for cut in evaluation.bom.profile_cuts
            if cut.role is ProfileRole.COUPLER and cut.origin is PieceOrigin.PRODUCT
        ]
    else:
        result = calculate_from_api(
            parametric_tree=tree,
            nominal_width_mm=Decimal(str(width_mm)),
            nominal_height_mm=Decimal(str(height_mm)),
            color=color,
            color_exterior=color_exterior,
            params=params,
        )
        modules = [
            ThermalModuleInput(
                result=result,
                area_m2=Decimal(str(width_mm))
                * Decimal(str(height_mm))
                * _M2_PER_MM2,
            )
        ]
        coupler_cuts = []
    uw = compute_uw(
        modules=modules,
        params=params,
        catalog=catalog,
        coupler_cuts=coupler_cuts,
        face_widths=_face_widths(params, coupler_articles),
    )
    return uw, catalog


def thermal_alternatives(
    *,
    org_id: UUID,
    position_id: UUID,
    price_lookup,
) -> dict:
    """§8: ante un complejo que no cumple, propone la alternativa más
    barata que sí cumple (otro vidrio u otro sistema del catálogo) con el
    Δ de precio real — position_cost sobre el diseño propuesto.

    ``price_lookup(position_dict, system_id, tree) -> neto Decimal|None``
    inyecta el precio del candidato para no acoplar el servicio a pricing.
    """
    position = rows(
        f"SELECT {','.join(POSITION_COLUMNS)} "
        "FROM public.project_positions WHERE id=%s AND org_id=%s",
        [position_id, org_id],
    )
    if not position:
        missing()
    position = position[0]
    project = rows(
        "SELECT id, thermal_zone, thermal_use FROM public.projects "
        "WHERE id=%s AND org_id=%s",
        [position["project_id"], org_id],
    )
    if not project:
        missing()
    zone = project[0]["thermal_zone"]
    use = project[0]["thermal_use"] or "RESIDENTIAL"
    orientation = position["thermal_orientation"]
    tree = decoded(position["parametric_tree"])

    current_verdict, _ = position_thermal(
        org_id=org_id,
        position=position,
        zone=zone,
        use=use,
        orientation=orientation,
    )

    candidates: list[dict] = []

    # 1) Otro vidrio del catálogo con Ug declarado más bajo.
    repository = SystemParamsRepository()
    params = repository.load_visible(position["system_id"], org_id)
    current_ugs = [
        pane.ug_w_m2k
        for pane in current_verdict.uw.panes
        if pane.ug_w_m2k is not None
    ]
    worst_ug = max(current_ugs) if current_ugs else None
    for product in params.glass_products.values():
        if product.ug_w_m2k is None or product.sku == "":
            continue
        if worst_ug is not None and product.ug_w_m2k >= worst_ug:
            continue
        try:
            proposal_tree = _swap_glass(tree, product.sku)
            uw, catalog = _evaluate_tree_uw(
                org_id=org_id,
                tree=proposal_tree,
                system_id=position["system_id"],
                width_mm=position["width_mm"],
                height_mm=position["height_mm"],
                color=position["color_interior"],
                color_exterior=position["color_exterior"],
            )
            classes = resolve_classes(
                catalog,
                typology=position["typology"],
                width_mm=Decimal(str(position["width_mm"])),
                height_mm=Decimal(str(position["height_mm"])),
            )
            verdict = position_compliance(
                uw=uw, classes=classes, zone=zone, use=use, orientation=orientation
            )
        except Exception:  # noqa: BLE001 — candidato no fabricable
            continue
        if verdict.verdict != "COMPLIES":
            continue
        delta = price_lookup(
            position, position["system_id"], proposal_tree
        )
        candidates.append(
            {
                "kind": "GLASS",
                "label": product.name or product.sku,
                "glass_sku": product.sku,
                "uw_w_m2k": str(uw.uw_w_m2k) if uw.uw_w_m2k else None,
                "price_delta_net": str(delta) if delta is not None else None,
            }
        )

    # 2) Otro sistema del catálogo con el mismo árbol — evalúa y veredicta.
    for system in rows(
        "SELECT id, name, code FROM public.profile_systems "
        "WHERE is_active AND id <> %s AND "
        "(org_id=%s OR (org_id IS NULL AND is_global))",
        [position["system_id"], org_id],
    ):
        try:
            uw, catalog = _evaluate_tree_uw(
                org_id=org_id,
                tree=tree,
                system_id=system["id"],
                width_mm=position["width_mm"],
                height_mm=position["height_mm"],
                color=position["color_interior"],
                color_exterior=position["color_exterior"],
            )
            classes = resolve_classes(
                catalog,
                typology=position["typology"],
                width_mm=Decimal(str(position["width_mm"])),
                height_mm=Decimal(str(position["height_mm"])),
            )
            verdict = position_compliance(
                uw=uw, classes=classes, zone=zone, use=use, orientation=orientation
            )
        except Exception:  # noqa: BLE001
            continue
        if verdict.verdict != "COMPLIES":
            continue
        delta = price_lookup(position, system["id"], tree)
        candidates.append(
            {
                "kind": "SYSTEM",
                "label": f'{system["code"]} — {system["name"]}',
                "system_id": str(system["id"]),
                "uw_w_m2k": str(uw.uw_w_m2k) if uw.uw_w_m2k else None,
                "price_delta_net": str(delta) if delta is not None else None,
            }
        )

    candidates.sort(
        key=lambda item: (
            Decimal(item["price_delta_net"])
            if item["price_delta_net"] is not None
            else Decimal("1e18")
        )
    )
    return {
        "position_id": str(position_id),
        "current": _public_result(current_verdict),
        "alternatives": candidates[:3],
    }


def thermal_annex(org_id: UUID, project_id: UUID) -> list[dict]:
    """Anexo técnico del DOC-01: por posición, el Uw y las clases de
    prestación — SOLO cuando provienen de datos verificados (el revisor
    técnico selló el certificado). Lo declarado-sin-revisar y lo DEMO no
    entran: un documento emitido al cliente jamás afirma cumplimiento
    sobre evidencia que no es autoritativa.
    """
    payload = project_thermal(org_id, project_id)
    annex: list[dict] = []
    for item in payload["positions"]:
        thermal = item.get("thermal") or {}
        uw = thermal.get("uw") or {}
        classes = thermal.get("classes") or {}
        entry: dict = {
            "position_index": item["position_index"],
            "location_tag": item["location_tag"],
            "quantity": item["quantity"],
        }
        if uw.get("status") == "OK" and uw.get("authority") == "VERIFIED":
            entry["uw_w_m2k"] = uw["uw_w_m2k"]
        if classes.get("authority") == "VERIFIED":
            entry["air_class"] = classes.get("air_class")
            entry["water_class"] = classes.get("water_class")
            entry["wind_class"] = classes.get("wind_class")
            entry["report_ref"] = classes.get("report_ref")
            entry["laboratory"] = classes.get("laboratory")
            entry["tested_on"] = classes.get("tested_on")
        if "uw_w_m2k" in entry or "air_class" in entry:
            annex.append(entry)
    return annex
