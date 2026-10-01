"""Catalog readiness — explicit level ladder, never a compressed percentage.

Levels (each reports state + exact blockers + the authority that is missing +
what is affected + why it matters + the action that resolves it):

- ``DESIGN_VALID`` — the system's technical catalog loads: a design can be
  expressed and validated by the engine.
- ``QUOTE_READY`` — design-valid plus purchase authorities: a price can be
  computed honestly (legacy WHITE_FIXED_CATALOG scope).
- ``MANUFACTURING_INCOMPLETE`` — a state, not a level: fabrication values,
  manufacturing policies or pending catalog reviews are missing.
- ``PRODUCTION_READY`` — manufacturing complete plus a resolvable, versioned
  process authority and active work centers for its required stations.
- ``CNC_READY`` — production-ready plus a declared operation→station map
  covering every machine operation the system can emit.
"""

from typing import Any

from dekopen_engine.models import MaterialType, ProfileRole
from documents.repository import (
    DocumentaryError, load_manufacturing_policies, load_purchase_authorities,
)
from engine_api.cutting_repository import CuttingRepository, MissingStockAuthority, AmbiguousStockAuthority
from engine_api.inspection_repository import InspectorRepository
from engine_api.repository import SystemParamsRepository, SystemNotFound, UnsupportedCatalogContract
from pricing.repository import rows
from production.service import _STEP_CODE_FOR_CENTER, _load_profile_for

_CENTER_KIND_FOR_STEP = {step: kind for kind, step in _STEP_CODE_FOR_CENTER.items()}


def _blocker(code: str, missing: str, affected: str, why: str, action: str) -> dict:
    return {
        "code": code,
        "missing_authority": missing,
        "affected": affected,
        "why": why,
        "action": action,
    }


def catalog_readiness(system_id, org_id) -> dict[str, Any]:
    design_b: list[dict] = []
    quote_b: list[dict] = []
    mfg_b: list[dict] = []
    prod_b: list[dict] = []
    cnc_b: list[dict] = []

    params = None
    try:
        params = SystemParamsRepository().load_visible(system_id, org_id)
        if (
            params.material not in (MaterialType.PVC, MaterialType.ALUMINIUM)
            or not params.glazing_bead_rules
        ):
            design_b.append(_blocker(
                "technical_catalog", "serie, marco y junquillos compatibles",
                str(system_id),
                "sin serie completa el motor no puede construir el producto",
                "completar la ficha técnica del sistema"))
    except (SystemNotFound, UnsupportedCatalogContract, ValueError):
        design_b.append(_blocker(
            "technical_catalog", "serie, marco y junquillos compatibles",
            str(system_id),
            "sin serie completa el motor no puede construir el producto",
            "completar la ficha técnica del sistema"))
    try:
        InspectorRepository().load(system_id, org_id)
    except (ValueError, UnsupportedCatalogContract):
        design_b.append(_blocker(
            "inspection", "parámetros de inspección del sistema",
            str(system_id),
            "la geometría máxima/mínima no es verificable sin inspección declarada",
            "completar los parámetros de inspección"))

    policies = []
    for table in ("manufacturing_placement_policies", "handle_requirement_policies",
                  "reinforcement_cut_policies"):
        values = rows(f"SELECT id FROM public.{table} WHERE system_id=%s "
                      "AND (org_id IS NULL OR org_id=%s) ORDER BY version DESC,id",
                      [system_id, org_id])
        policies.append(values[0]["id"] if values else None)
    if None in policies:
        mfg_b.append(_blocker(
            "manufacturing", "políticas de fabricación (posición, manilla, refuerzo)",
            str(system_id),
            "sin políticas el taller no puede derivar mecanizados ni herrajes",
            "completar las políticas de fabricación del sistema"))
    else:
        try:
            load_manufacturing_policies(system_id=system_id, org_id=org_id,
                placement_id=policies[0], handle_id=policies[1], reinforcement_id=policies[2])
        except (DocumentaryError, ValueError):
            mfg_b.append(_blocker(
                "manufacturing", "políticas de fabricación (posición, manilla, refuerzo)",
                str(system_id),
                "sin políticas el taller no puede derivar mecanizados ni herrajes",
                "completar las políticas de fabricación del sistema"))

    if params is not None:
        # Fabrication authorities the geometry actually consumes — mirror
        # the engine's own role/operation rules so UNKNOWN surfaces here, not
        # mid-calculation, without blocking catalogs whose gaps never reach a
        # calculation:
        # * rebate_depth_mm / end_milling_overlap_mm are consumed by every
        #   glazed bay and every mullion — NULL means the system cannot prove
        #   its fabrication geometry (the engine raises instead of inventing).
        # * PVC: every welded-cut member needs weld loss + reinforcement gap —
        #   all effective roles except THRESHOLD (appended unwelded).
        # * Profile and steel mass feed leaf weight — there is no fallback
        #   anymore, so the effective SASH needs both when it is reinforced.
        # * A hardware kit with no declared mass makes weight-based
        #   certification undecidable.
        # * Couplers load outside effective articles; any reinforced coupler
        #   runs reinforcement_cut_length regardless of material.
        fabrication_missing: list[str] = []
        if params.rebate_depth_mm is None:
            fabrication_missing.append("rebate_depth_mm")
        if params.end_milling_overlap_mm is None:
            fabrication_missing.append("end_milling_overlap_mm")
        if params.material is MaterialType.PVC:
            fabrication_missing += [
                article.sku
                for role, article in params.effective_profile_articles.items()
                if role is not ProfileRole.THRESHOLD
                and (article.welding_loss_mm is None or article.reinforcement_gap_mm is None)
            ]
        sash = params.effective_profile_articles.get(ProfileRole.SASH)
        if sash is not None and (
            sash.weight_kg_m is None
            or (bool(sash.reinforcement_sku) and sash.steel_weight_kg_m is None)
        ):
            fabrication_missing.append(sash.sku)
        fabrication_missing += [
            kit.sku for kit in params.available_hardware_kits if kit.weight_kg is None
        ]
        if not fabrication_missing:
            try:
                couplers = SystemParamsRepository().load_coupler_articles(system_id, org_id)
                fabrication_missing = [
                    article.sku
                    for article in couplers.values()
                    if bool(article.reinforcement_sku)
                    and (article.welding_loss_mm is None or article.reinforcement_gap_mm is None)
                ]
            except (ValueError, UnsupportedCatalogContract):
                fabrication_missing = ["coupler_articles"]
        if fabrication_missing:
            mfg_b.append(_blocker(
                "fabrication", "autoridad de fabricación (soldadura, refuerzo, masa)",
                ", ".join(sorted(set(fabrication_missing))[:8]),
                "sin datos de fabricación el taller recibiría valores inventados",
                "declarar soldadura, refuerzo y masa en los artículos afectados"))
        # Production authority must not ride on values nobody ever verified:
        # LEGACY_UNVERIFIED rows and rows whose technical values changed after
        # their last review (review_pending) need a human review first —
        # review() clears both gates. Two scoping rules (review CAT-09):
        # * org-owned rows only — global catalog data is platform-managed,
        #   members can neither write nor review it, so flagging it would be
        #   a permanent unfixable blocker for every tenant;
        # * kits bound to THIS system only — the engine loads kits strictly
        #   by system_id, so an unbound kit is dead weight it can't consume
        #   and shouldn't gate readiness.
        if rows(
            "SELECT 1 FROM public.profile_systems WHERE id=%s"
            " AND org_id=%s"
            " AND (data_provenance='LEGACY_UNVERIFIED' OR review_pending)"
            " UNION ALL"
            " SELECT 1 FROM public.profile_articles WHERE system_id=%s"
            " AND org_id=%s"
            " AND (data_provenance='LEGACY_UNVERIFIED' OR review_pending)"
            " UNION ALL"
            " SELECT 1 FROM public.infill_articles WHERE system_id=%s"
            " AND org_id=%s"
            " AND (data_provenance='LEGACY_UNVERIFIED' OR review_pending)"
            " UNION ALL"
            " SELECT 1 FROM public.hardware_kits WHERE system_id=%s"
            " AND org_id=%s"
            " AND (data_provenance='LEGACY_UNVERIFIED' OR review_pending)"
            " UNION ALL"
            " SELECT 1 FROM public.glazing_bead_matrix WHERE system_id=%s"
            " AND org_id=%s"
            " AND (data_provenance='LEGACY_UNVERIFIED' OR review_pending)"
            " LIMIT 1",
            [system_id, org_id, system_id, org_id,
             system_id, org_id, system_id, org_id, system_id, org_id],
        ):
            mfg_b.append(_blocker(
                "catalog_review", "revisión técnica humana de datos heredados",
                str(system_id),
                "datos heredados sin verificar no pueden alimentar producción",
                "revisar y aprobar los datos técnicos heredados del sistema"))
        purchase_code = None
        try:
            # The probe mirrors freeze's authority consumption at catalog
            # level (review CAT-03): every active article sku the system can
            # emit as a member — not just frame+beads — every reinforcement
            # those articles reference, every hardware kit bound to the
            # system, and every active panel sku. Glass/fittings stay
            # roster-level: positions pick strictly from the mapping tables,
            # so the catalog-level duty is that every declared sku resolves
            # unambiguously (load_purchase_authorities raises on duplicates).
            catalogued = rows(
                "SELECT sku, reinforcement_sku, role::text FROM public.profile_articles "
                "WHERE system_id=%s "
                "AND (org_id IS NULL OR org_id=%s)",
                [system_id, org_id],
            )
            steels: set[str] = set()
            if params.material is MaterialType.PVC:
                # A welded PVC member always needs its steel resolved —
                # including default SKU resolution. Mechanically jointed
                # systems do not, and neither do unwelded roles (threshold
                # is appended, beads clip, channels seat frameless panes).
                # Positions check FOILED at freeze when the face colors
                # require it; the catalog baseline is WHITE.
                for article in catalogued:
                    if article["role"] in ("THRESHOLD", "GLAZING_BEAD", "CHANNEL"):
                        continue
                    stock, _ = CuttingRepository().reinforcement_stock(
                        system_id, org_id, article["sku"],
                        article["reinforcement_sku"], "WHITE")
                    steels.add(stock.workshop_sku)
            glass = rows("SELECT technical_sku FROM public.glass_purchase_mappings "
                         "WHERE system_id=%s AND (org_id IS NULL OR org_id=%s)", [system_id, org_id])
            if not glass:
                raise DocumentaryError("glass_purchase_mapping_required")
            load_purchase_authorities(system_id=system_id, org_id=org_id, color="WHITE",
                profile_skus={article["sku"] for article in catalogued},
                reinforcement_skus=steels,
                glass_skus={row["technical_sku"] for row in glass},
                hardware_skus={kit.sku for kit in params.available_hardware_kits},
                panel_skus={
                    row["sku"] for row in rows(
                        "SELECT sku FROM public.infill_articles WHERE system_id=%s"
                        " AND is_active AND (org_id IS NULL OR org_id=%s)",
                        [system_id, org_id],
                    )
                },
                fitting_skus={
                    row["technical_sku"] for row in rows(
                        "SELECT technical_sku FROM public.fitting_purchase_mappings"
                        " WHERE system_id=%s AND (org_id IS NULL OR org_id=%s)",
                        [system_id, org_id],
                    )
                })
        except DocumentaryError as error:
            purchase_code = str(error.code)
        except (MissingStockAuthority, AmbiguousStockAuthority, ValueError):
            purchase_code = "stock_authority"
        if purchase_code:
            quote_b.append(_blocker(
                "purchase", f"referencia de compra/suministro ({purchase_code})",
                str(system_id),
                "sin referencias de suministro no hay precio honesto",
                "completar las referencias de compra de los materiales"))

    # ── Production level: declared process authority + work centers ──
    # The catalog resolves profiles exactly like production does, minus the
    # sealed product: system-bound → material default → GENERIC_LEGACY.
    profile = None
    process_via = None
    if params is not None:
        bound = rows(
            "SELECT process_profile_id::text FROM public.profile_systems WHERE id=%s",
            [system_id],
        )
        if bound and bound[0].get("process_profile_id"):
            profile, process_via = _load_profile_for(org_id, profile_id=bound[0]["process_profile_id"])
        if profile is None:
            material = params.material.value if params.material else None
            if material:
                profile, process_via = _load_profile_for(org_id, material=material)
        if profile is None:
            profile, via = _load_profile_for(org_id, code="GENERIC_LEGACY")
            process_via = "generic_fallback" if profile else via
    if params is not None and (profile is None or process_via == "generic_fallback"):
        prod_b.append(_blocker(
            "process_profile", "perfil de proceso declarado",
            str(system_id),
            "sin autoridad de proceso versionada la ruta cae al genérico — ninguna unión real está garantizada",
            "vincular un perfil de proceso al sistema"))

    stations = (profile or {}).get("stations") or []
    station_map = (profile or {}).get("operation_station_map") or {}
    station_codes = {s["code"] for s in stations}
    required = [s["code"] for s in stations if s.get("when") == "required"]

    # Ops the system can actually emit decide which 'auto' stations carry
    # work: an inactive center on any of them strands the step at release
    # (centers are never silently reactivated).
    potential_ops = {"SAW_CUT"}
    if params is not None and any(
        role in params.effective_profile_articles
        for role in (ProfileRole.MULLION_V, ProfileRole.MULLION_H)
    ):
        potential_ops.add("END_MACHINING")
    if params is not None and rows(
        "SELECT 1 FROM public.handle_requirement_policies WHERE system_id=%s"
        " AND (org_id IS NULL OR org_id=%s) LIMIT 1",
        [system_id, org_id],
    ):
        potential_ops.add("HANDLE_PREP")
    emit_stations = {
        str(station_map[op]) for op in potential_ops
        if op in station_map and station_map[op] in station_codes
    }
    # Routing emits auto stations from the sealed result — at catalog level the
    # proxies are the system's declared catalog: glass/panels → GLAZE, hardware
    # or fittings or handle prep → HARDWARE, sash articles → SASH_ASSEMBLE,
    # profile cuts → CUT, and the generic assembly station always emits.
    emitted: set[str] = set()
    if params is not None:
        if params.effective_profile_articles:
            emitted.add("CUT")
        if params.effective_profile_articles.get(ProfileRole.SASH) is not None:
            emitted.add("SASH_ASSEMBLE")
        if (
            params.available_hardware_kits
            or "HANDLE_PREP" in potential_ops
            or rows(
                "SELECT 1 FROM public.fitting_purchase_mappings WHERE system_id=%s"
                " AND (org_id IS NULL OR org_id=%s) LIMIT 1",
                [system_id, org_id],
            )
        ):
            emitted.add("HARDWARE")
        if rows(
            "SELECT 1 FROM public.glass_purchase_mappings WHERE system_id=%s"
            " AND (org_id IS NULL OR org_id=%s) LIMIT 1",
            [system_id, org_id],
        ) or rows(
            "SELECT 1 FROM public.infill_articles WHERE system_id=%s"
            " AND (org_id IS NULL OR org_id=%s) LIMIT 1",
            [system_id, org_id],
        ):
            emitted.add("GLAZE")
        emitted.add("ASSEMBLE")
    needed = sorted(set(required) | emit_stations | (emitted & station_codes))
    if profile is not None and needed:
        centers = rows(
            "SELECT kind FROM public.work_centers WHERE org_id=%s AND active",
            [org_id],
        )
        have = {row["kind"] for row in centers}
        missing = sorted(
            s for s in needed
            if s in _CENTER_KIND_FOR_STEP and _CENTER_KIND_FOR_STEP[s] not in have
        )
        if missing:
            prod_b.append(_blocker(
                "work_centers", "centros de trabajo activos",
                ", ".join(missing),
                "una estación requerida o con trabajo emitible sin centro no puede recibir pasos",
                "crear los centros de trabajo de las estaciones faltantes"))

    # ── CNC level: every machine op the system can emit maps to a station ──
    if profile is not None and params is not None:
        unmapped = sorted(
            op for op in potential_ops
            if op not in station_map or station_map[op] not in station_codes
        )
        if unmapped:
            cnc_b.append(_blocker(
                "station_map", "mapeo operación → estación",
                ", ".join(unmapped),
                "una operación de máquina sin estación declarada cae al fallback de UI",
                "declarar la estación de cada operación en el perfil de proceso"))

    # quote_ready keeps its legacy contract — the WHITE_FIXED_CATALOG gate is
    # design + purchase + manufacturing authority; the new production/CNC
    # levels report above it without tightening the existing gate.
    reasons = [b["code"] for b in design_b + quote_b + mfg_b]
    return {
        "quote_ready": not reasons,
        "scope": "WHITE_FIXED_CATALOG",
        "reasons": reasons,
        "levels": [
            {"level": "DESIGN_VALID", "ok": not design_b, "blockers": design_b},
            {"level": "QUOTE_READY", "ok": not (design_b + quote_b + mfg_b),
             "blockers": design_b + quote_b + mfg_b},
            {"level": "MANUFACTURING_INCOMPLETE",
             "state": "INCOMPLETE" if mfg_b else "COMPLETE",
             "blockers": mfg_b},
            {"level": "PRODUCTION_READY",
             "ok": not (design_b + quote_b + mfg_b + prod_b),
             "blockers": design_b + quote_b + mfg_b + prod_b},
            {"level": "CNC_READY",
             "ok": not (design_b + quote_b + mfg_b + prod_b + cnc_b),
             "blockers": design_b + quote_b + mfg_b + prod_b + cnc_b},
        ],
        "process_via": process_via,
    }
