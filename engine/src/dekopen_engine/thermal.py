"""P18 — desempeño térmico: Uw por ISO 10077-1 y cumplimiento OGUC 4.1.10.

El motor es la única fuente de números: el Uw sale de la geometría que el
propio motor ya resolvió (Ag por pieza de vidrio, Af como resto del hueco,
lg como perímetro vidriado) y de valores de catálogo DECLARADOS con su
sello de procedencia — jamás calculados ni inventados.

Contrato de autoridad (cada entrada térmica lo respeta):
- VERIFIED: fila con ``technical_reviewed_at`` (un revisor técnico la
  firmó). Sólo entradas verificadas sostienen un veredicto «Cumple».
- DECLARED: el valor existe pero nadie lo certificó. Un valor declarado
  que incumple la exigencia produce «No cumple» (la declaración misma
  falla); uno que la cumple no basta para afirmar cumplimiento.
- DEMO: ``SEED_SYNTHETIC`` o catálogo de demostración — nunca sostiene
  un veredicto de cumplimiento en ninguna dirección.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from dekopen_engine.engine_base import EngineModel
from dekopen_engine.glass_composition import SpacerKind
from dekopen_engine.models import (
    EngineResult,
    GlassPiece,
    PieceOrigin,
    PlanPoint,
    ProfileCut,
    ProfileRole,
    SystemParams,
)
from dekopen_engine.oguc_4110 import (
    AIR_CLASS_MIN,
    EQUIPMENT_WINDOW_U_MAX,
    ROOF_WINDOW_U_MAX,
    ROOF_WINDOW_ZONES,
    window_max_pct,
)

Q_U = Decimal("0.01")      # Uw se publica a 2 decimales (formato «1,40»)
Q_M2 = Decimal("0.0001")   # áreas y largos en m/m² a 4 decimales


# ─── Entradas declaradas con procedencia ───────────────────────────────────

MEMBER_GROUPS = ("ALL", "FRAME", "SASH", "MULLION", "COUPLER", "THRESHOLD")

# Rol de perfil → grupo Uf declarado por el fabricante. Los miembros del
# contorno no declarado se ponderan como FRAME (son zona de marco).
GROUP_OF_ROLE: dict[ProfileRole, str] = {
    ProfileRole.FRAME: "FRAME",
    ProfileRole.FRAME_EXTENSION: "FRAME",
    ProfileRole.SILL: "FRAME",
    ProfileRole.SKIRT: "FRAME",
    ProfileRole.CHANNEL: "FRAME",
    ProfileRole.RAIL: "FRAME",
    ProfileRole.COVER_TRIM: "FRAME",
    ProfileRole.GLAZING_BEAD: "FRAME",
    ProfileRole.ADDITIONAL: "FRAME",
    ProfileRole.SASH: "SASH",
    ProfileRole.DOOR_SASH: "SASH",
    ProfileRole.SLIDING_SASH: "SASH",
    ProfileRole.INTERLOCK: "SASH",
    ProfileRole.INVERSOR: "SASH",
    ProfileRole.MULLION_V: "MULLION",
    ProfileRole.MULLION_H: "MULLION",
    ProfileRole.COUPLER: "COUPLER",
    ProfileRole.THRESHOLD: "THRESHOLD",
}

ORIENTATIONS = ("N", "OP", "S", "OGT", "ROOF")
THERMAL_USES = ("RESIDENTIAL", "EQUIPMENT")


class SpacerPsiInput(EngineModel):
    """Ψg declarado para un tipo de separador (fila ``glazing_spacers``)."""

    code: str
    name: str | None = None
    psi_w_m_k: Decimal | None = None
    provenance: str = "MANUAL"
    verified: bool = False


class FrameUfInput(EngineModel):
    """Uf declarado por el fabricante para un grupo de miembro."""

    member_group: str
    uf_w_m2k: Decimal
    provenance: str = "MANUAL"
    verified: bool = False
    source: str | None = None


class PerformanceTestInput(EngineModel):
    """Informe de ensayo del sistema con sus clases y alcance."""

    air_class: int | None = None
    water_class: str | None = None
    wind_class: str | None = None
    report_ref: str | None = None
    laboratory: str | None = None
    tested_on: str | None = None
    tested_width_mm: Decimal | None = None
    tested_height_mm: Decimal | None = None
    typology_scope: str | None = None
    provenance: str = "MANUAL"
    verified: bool = False


class ThermalCatalogInput(EngineModel):
    """Autoridad térmica resuelta por el backend para un sistema."""

    frame_uf: dict[str, FrameUfInput] = {}
    spacers: dict[str, SpacerPsiInput] = {}
    tests: list[PerformanceTestInput] = []
    demo: bool = False


class ThermalModuleInput(EngineModel):
    """Un módulo evaluado con la superficie de su hueco (m²).

    ``area_m2`` es el área nominal del módulo (ancho × alto o el polígono
    exacto del contorno): el backend la calcula junto al envelope porque la
    geometría de contorno tiene bulges que un rectángulo no describe.
    """

    result: EngineResult
    area_m2: Decimal


# ─── Salidas ───────────────────────────────────────────────────────────────

AuthorityLevel = Literal["VERIFIED", "DECLARED", "DEMO"]


class ThermalMissing(EngineModel):
    """Un insumo que faltó para calcular — siempre con qué y dónde."""

    code: str  # GLASS_PRODUCT | UG | UF | PSI | PANEL_U | AIR_CLASS | ZONE | ORIENTATION | WALL_AREA | U_BEYOND_TABLE | UNVERIFIED | DEMO | TEST_SCOPE | PANEL_UNKNOWN
    detail: str | None = None


class PaneThermal(EngineModel):
    bay_id: str
    leaf_id: str | None = None
    article_sku: str | None = None
    area_m2: Decimal
    perimeter_m: Decimal
    ug_w_m2k: Decimal | None = None
    ug_authority: AuthorityLevel | None = None
    psi_w_m_k: Decimal | None = None
    spacer_code: str | None = None
    psi_authority: AuthorityLevel | None = None


class FrameZoneThermal(EngineModel):
    member_group: str
    area_m2: Decimal
    uf_w_m2k: Decimal | None = None
    authority: AuthorityLevel | None = None
    source: str | None = None


class UwComputation(EngineModel):
    """Desglose completo del Uw — el «¿de dónde sale?» de la posición."""

    status: Literal["OK", "UNKNOWN"]
    uw_w_m2k: Decimal | None = None
    ag_m2: Decimal
    af_m2: Decimal
    lg_m: Decimal
    numerator_w_m_k: Decimal | None = None
    panes: list[PaneThermal] = []
    frame: list[FrameZoneThermal] = []
    missing: list[ThermalMissing] = []
    authority: AuthorityLevel | None = None


class ThermalCause(EngineModel):
    code: str
    detail: str | None = None


class ResolvedClasses(EngineModel):
    """La clase ensayada aplicable a la posición, con su informe."""

    air_class: int | None = None
    water_class: str | None = None
    wind_class: str | None = None
    report_ref: str | None = None
    laboratory: str | None = None
    tested_on: str | None = None
    tested_width_mm: Decimal | None = None
    tested_height_mm: Decimal | None = None
    authority: AuthorityLevel | None = None
    scope_exceeded: bool = False


class PositionThermalResult(EngineModel):
    """Uw + clases + veredicto de una posición frente a su zona térmica."""

    uw: UwComputation
    classes: ResolvedClasses | None = None
    verdict: Literal["COMPLIES", "FAILS", "INSUFFICIENT_DATA", "NO_REQUIREMENT"]
    causes: list[ThermalCause] = []
    air_class_required: int | None = None
    roof_u_max: Decimal | None = None
    u_max: Decimal | None = None
    window_pct_max: int | None = None


class OrientationCompliance(EngineModel):
    orientation: str
    window_area_m2: Decimal
    wall_area_m2: Decimal | None = None
    actual_pct: Decimal | None = None
    allowed_pct: int | None = None
    verdict: Literal["COMPLIES", "FAILS", "INSUFFICIENT_DATA", "NO_REQUIREMENT"]
    causes: list[ThermalCause] = []


# ─── Autoridad ─────────────────────────────────────────────────────────────

def _level(provenance: str | None, verified: bool, demo: bool) -> AuthorityLevel:
    if demo or provenance == "SEED_SYNTHETIC":
        return "DEMO"
    return "VERIFIED" if verified else "DECLARED"


def _worst(levels: list[AuthorityLevel | None]) -> AuthorityLevel | None:
    present = {level for level in levels if level is not None}
    if not present:
        return None
    if "DEMO" in present:
        return "DEMO"
    if "DECLARED" in present:
        return "DECLARED"
    return "VERIFIED"


# ─── Geometría del hueco ───────────────────────────────────────────────────

def _perimeter_m(width_mm: Decimal, height_mm: Decimal) -> Decimal:
    return (Decimal(2) * (width_mm + height_mm) / Decimal("1000")).quantize(Q_M2)


def _shape_perimeter_m(shape: list[PlanPoint]) -> Decimal:
    if len(shape) < 2:
        return Decimal("0")
    total = Decimal("0")
    for index, point in enumerate(shape):
        nxt = shape[(index + 1) % len(shape)]
        total += ((nxt.x_mm - point.x_mm) ** 2 + (nxt.y_mm - point.y_mm) ** 2).sqrt()
    return (total / Decimal("1000")).quantize(Q_M2)


def _member_group_areas(
    cuts: list[ProfileCut],
    face_widths: dict[str, Decimal],
) -> dict[str, Decimal]:
    """Área proyectada por grupo de miembro (m²) a partir de los cortes.

    ``largo × ancho de cara × qty`` por corte; los cortes sin ancho de cara
    conocido se omiten de la ponderación (su área sigue dentro de Af).
    """
    areas: dict[str, Decimal] = {}
    for cut in cuts:
        if cut.origin is PieceOrigin.EXTRA:
            continue
        face = face_widths.get(cut.sku)
        if face is None:
            continue
        group = GROUP_OF_ROLE.get(cut.role, "FRAME")
        areas[group] = areas.get(group, Decimal("0")) + (
            cut.length_mm * face * Decimal(cut.qty) / Decimal("1e6")
        )
    return areas


def _coupler_area_m2(
    cuts: list[ProfileCut],
    face_widths: dict[str, Decimal],
) -> Decimal:
    """Superficie proyectada de los acopladores del conjunto (m²) — es
    zona de marco y suma al denominador del complejo."""
    total = Decimal("0")
    for cut in cuts:
        if cut.role is not ProfileRole.COUPLER:
            continue
        face = face_widths.get(cut.sku)
        if face is not None:
            total += cut.length_mm * face * Decimal(cut.qty) / Decimal("1e6")
    return total


def _pane_spacer_code(piece: GlassPiece) -> str | None:
    """El separador del paquete: varios chambers con distinto separador se
    resuelven por el código dominante (aluminio si hay mezcla — la peor Ψ
    típica) conservando honestidad conservadora."""
    if piece.composition is None:
        return None
    codes = [str(chamber.spacer.value) for chamber in piece.composition.chambers]
    if not codes:
        return None
    unique = set(codes)
    if len(unique) == 1:
        return codes[0]
    # Mezcla: la Ψ mayor declarada manda; si ninguna está declarada el
    # faltante se reporta para el primer código.
    return SpacerKind.ALUMINIUM.value if SpacerKind.ALUMINIUM.value in unique else codes[0]


# ─── Uw ────────────────────────────────────────────────────────────────────

def compute_uw(
    *,
    modules: list[ThermalModuleInput],
    params: SystemParams,
    catalog: ThermalCatalogInput,
    coupler_cuts: list[ProfileCut] | None = None,
    face_widths: dict[str, Decimal] | None = None,
) -> UwComputation:
    """Uw = (Ag·Ug + Af·Uf + lg·Ψg) / (Ag + Af) por ISO 10077-1.

    Ag y lg salen de las piezas de vidrio del resultado; Af es el resto del
    hueco (superficie nominal menos vidrio) más la superficie proyectada de
    acopladores del conjunto. Cualquier insumo declarado ausente deja el
    resultado en UNKNOWN con la lista de faltantes — nunca un número al
    vuelo.
    """
    widths = dict(face_widths or {})
    for sku, article in params.effective_profile_articles.items():
        widths.setdefault(sku, article.face_width_mm)

    demo = catalog.demo
    panes: list[PaneThermal] = []
    missing: list[ThermalMissing] = []
    frame_area = Decimal("0")
    glass_area = Decimal("0")
    glass_perimeter = Decimal("0")
    has_panel = False

    for module in modules:
        result = module.result
        module_glass = Decimal("0")
        module_panels = Decimal("0")
        for panel in result.panels:
            module_panels += panel.area_m2
        if module_panels > 0:
            has_panel = True
        for piece in result.glasses:
            module_glass += piece.area_m2
            perimeter = (
                _shape_perimeter_m(piece.shape)
                if piece.shape
                else _perimeter_m(piece.width_mm, piece.height_mm)
            )
            pane = PaneThermal(
                bay_id=piece.bay_id,
                leaf_id=piece.leaf_id,
                article_sku=piece.article_sku,
                area_m2=piece.area_m2,
                perimeter_m=perimeter,
            )
            product = (
                params.glass_products.get(piece.article_sku)
                if piece.article_sku
                else None
            )
            if product is None:
                missing.append(ThermalMissing(
                    code="GLASS_PRODUCT",
                    detail=piece.article_sku or piece.glass_spec or piece.bay_id,
                ))
            else:
                pane.ug_authority = _level(
                    getattr(product, "data_provenance", None),
                    getattr(product, "verified", False),
                    demo,
                )
                if product.ug_w_m2k is None:
                    missing.append(ThermalMissing(code="UG", detail=product.sku))
                else:
                    pane.ug_w_m2k = product.ug_w_m2k
            spacer_code = _pane_spacer_code(piece)
            if spacer_code is not None:
                pane.spacer_code = spacer_code
                spacer = catalog.spacers.get(spacer_code)
                if spacer is None or spacer.psi_w_m_k is None:
                    missing.append(ThermalMissing(code="PSI", detail=spacer_code))
                else:
                    pane.psi_w_m_k = spacer.psi_w_m_k
                    pane.psi_authority = _level(spacer.provenance, spacer.verified, demo)
            panes.append(pane)
            glass_perimeter += perimeter
        glass_area += module_glass
        # Af del módulo = hueco − vidrio − paneles (paneles no son zona de
        # marco; su U opaca no está modelada → faltante explícito).
        frame_area += max(module.area_m2 - module_glass - module_panels, Decimal("0"))
    coupler_cuts = coupler_cuts or []
    coupler_area = _coupler_area_m2(coupler_cuts, widths)

    # Ponderación de Af por grupo: el área proyectada de cada grupo sobre el
    # total proyectado reparte el Af real del hueco.
    member_areas: dict[str, Decimal] = {}
    for module in modules:
        for group, area in _member_group_areas(
            module.result.profile_cuts, widths
        ).items():
            member_areas[group] = member_areas.get(group, Decimal("0")) + area
    member_areas["COUPLER"] = member_areas.get("COUPLER", Decimal("0")) + coupler_area
    projected_total = sum(member_areas.values())

    af_total = frame_area + coupler_area
    frame_zones: list[FrameZoneThermal] = []

    groups = [group for group in MEMBER_GROUPS if group != "ALL" and member_areas.get(group)]
    if not groups and projected_total == 0 and af_total > 0:
        # Sin cortes resolubles (p.ej. módulo frameless no aplica: af=0 ya):
        # una sola zona FRAME para declarar el Uf del sistema.
        groups = ["FRAME"]
        member_areas["FRAME"] = af_total
        projected_total = af_total
    for group in groups:
        share = (
            af_total * member_areas.get(group, Decimal("0")) / projected_total
            if projected_total > 0
            else Decimal("0")
        )
        zone = FrameZoneThermal(member_group=group, area_m2=share.quantize(Q_M2))
        entry = catalog.frame_uf.get(group) or catalog.frame_uf.get("ALL")
        if entry is None:
            missing.append(ThermalMissing(code="UF", detail=group))
        else:
            zone.uf_w_m2k = entry.uf_w_m2k
            zone.authority = _level(entry.provenance, entry.verified, demo)
            zone.source = entry.source
        frame_zones.append(zone)

    if has_panel:
        missing.append(ThermalMissing(code="PANEL_U"))

    if missing:
        return UwComputation(
            status="UNKNOWN",
            ag_m2=glass_area.quantize(Q_M2),
            af_m2=af_total.quantize(Q_M2),
            lg_m=glass_perimeter.quantize(Q_M2),
            panes=panes,
            frame=frame_zones,
            missing=missing,
            authority=_worst(
                [pane.ug_authority for pane in panes]
                + [pane.psi_authority for pane in panes]
                + [zone.authority for zone in frame_zones]
            ),
        )

    term_glass = sum(
        (pane.area_m2 * (pane.ug_w_m2k or Decimal("0")) for pane in panes),
        Decimal("0"),
    )
    term_frame = sum(
        (zone.area_m2 * (zone.uf_w_m2k or Decimal("0")) for zone in frame_zones),
        Decimal("0"),
    )
    term_edge = sum(
        (pane.perimeter_m * (pane.psi_w_m_k or Decimal("0")) for pane in panes),
        Decimal("0"),
    )
    numerator = term_glass + term_frame + term_edge
    denominator = glass_area + af_total
    uw = (
        (numerator / denominator).quantize(Q_U, rounding=ROUND_HALF_UP)
        if denominator > 0
        else None
    )
    return UwComputation(
        status="OK" if uw is not None else "UNKNOWN",
        uw_w_m2k=uw,
        ag_m2=glass_area.quantize(Q_M2),
        af_m2=af_total.quantize(Q_M2),
        lg_m=glass_perimeter.quantize(Q_M2),
        numerator_w_m_k=numerator,
        panes=panes,
        frame=frame_zones,
        missing=missing,
        authority=_worst(
            [pane.ug_authority for pane in panes]
            + [pane.psi_authority for pane in panes]
            + [zone.authority for zone in frame_zones]
        ),
    )


# ─── Clases ensayadas ──────────────────────────────────────────────────────

def resolve_classes(
    catalog: ThermalCatalogInput,
    *,
    typology: str | None,
    width_mm: Decimal,
    height_mm: Decimal,
) -> ResolvedClasses | None:
    """Informe aplicable: primero el que declare la familia de la posición,
    luego el de alcance general; dentro de cada grupo, el más reciente."""
    if not catalog.tests:
        return None
    scoped = [row for row in catalog.tests if row.typology_scope]
    generic = [row for row in catalog.tests if not row.typology_scope]
    pool = (
        [row for row in scoped if row.typology_scope == typology] or generic or scoped
    )
    chosen = sorted(pool, key=lambda row: row.tested_on or "", reverse=True)[0]
    exceeded = (
        chosen.tested_width_mm is not None
        and chosen.tested_height_mm is not None
        and (width_mm > chosen.tested_width_mm or height_mm > chosen.tested_height_mm)
    )
    return ResolvedClasses(
        air_class=chosen.air_class,
        water_class=chosen.water_class,
        wind_class=chosen.wind_class,
        report_ref=chosen.report_ref,
        laboratory=chosen.laboratory,
        tested_on=chosen.tested_on,
        tested_width_mm=chosen.tested_width_mm,
        tested_height_mm=chosen.tested_height_mm,
        authority=_level(chosen.provenance, chosen.verified, catalog.demo),
        scope_exceeded=exceeded,
    )


# ─── Cumplimiento por posición ─────────────────────────────────────────────

def _verdict_for_declared(
    *,
    fails: bool,
    authority: AuthorityLevel | None,
) -> str:
    """Regla de honestidad: un valor declarado que incumple produce FAILS;
    cumplir exige VERIFIED; DEMO nunca veredicta."""
    if authority == "DEMO":
        return "INSUFFICIENT_DATA"
    if fails:
        return "FAILS"
    if authority == "VERIFIED":
        return "COMPLIES"
    return "INSUFFICIENT_DATA"


def position_compliance(
    *,
    uw: UwComputation,
    classes: ResolvedClasses | None,
    zone: str | None,
    use: str,
    orientation: str | None,
) -> PositionThermalResult:
    """Veredicto de la posición: permeabilidad al aire + U del complejo.

    En residencial la exigencia de U se prueba por orientación con el % de
    paramentos (panel del proyecto); aquí se exige además que el Uw quepa
    en la tabla (≤5,8 W/m²K) o, en techumbre, el límite 3,6 de las zonas
    B–I. En equipamiento el límite es directo (Tabla 12).
    """
    causes: list[ThermalCause] = []
    if not zone:
        return PositionThermalResult(
            uw=uw, classes=classes,
            verdict="INSUFFICIENT_DATA",
            causes=[ThermalCause(code="ZONE_MISSING")],
        )

    required_air = AIR_CLASS_MIN.get(zone)
    air_verdict = "NO_REQUIREMENT"
    if required_air is not None:
        if classes is None or classes.air_class is None:
            air_verdict = "INSUFFICIENT_DATA"
            causes.append(ThermalCause(code="AIR_CLASS_MISSING"))
        elif classes.scope_exceeded:
            air_verdict = "INSUFFICIENT_DATA"
            causes.append(ThermalCause(
                code="TEST_SCOPE_EXCEEDED",
                detail="La clase ensayada cubre ejemplares menores que esta posición.",
            ))
        else:
            air_verdict = _verdict_for_declared(
                fails=classes.air_class < required_air,
                authority=classes.authority,
            )
            if air_verdict == "INSUFFICIENT_DATA" and classes.authority == "DECLARED":
                causes.append(ThermalCause(code="AIR_CLASS_UNVERIFIED"))
            elif classes.authority == "DEMO":
                causes.append(ThermalCause(code="DEMO_DATA"))

    u_verdict = "NO_REQUIREMENT"
    u_max: Decimal | None = None
    pct_max: int | None = None
    roof_max: Decimal | None = None
    if use == "EQUIPMENT":
        u_max = EQUIPMENT_WINDOW_U_MAX.get(zone)
        if u_max is not None:
            if uw.status != "OK" or uw.uw_w_m2k is None:
                u_verdict = "INSUFFICIENT_DATA"
                causes.append(ThermalCause(code="UW_UNKNOWN"))
            else:
                u_verdict = _verdict_for_declared(
                    fails=uw.uw_w_m2k > u_max,
                    authority=uw.authority,
                )
                if u_verdict == "INSUFFICIENT_DATA":
                    causes.append(ThermalCause(
                        code="DEMO_DATA" if uw.authority == "DEMO" else "UW_UNVERIFIED"))
    elif orientation == "ROOF":
        if zone in ROOF_WINDOW_ZONES:
            roof_max = ROOF_WINDOW_U_MAX
            if uw.status != "OK" or uw.uw_w_m2k is None:
                u_verdict = "INSUFFICIENT_DATA"
                causes.append(ThermalCause(code="UW_UNKNOWN"))
            else:
                u_verdict = _verdict_for_declared(
                    fails=uw.uw_w_m2k > roof_max,
                    authority=uw.authority,
                )
                if u_verdict == "INSUFFICIENT_DATA":
                    causes.append(ThermalCause(
                        code="DEMO_DATA" if uw.authority == "DEMO" else "UW_UNVERIFIED"))
    else:
        if orientation is None:
            u_verdict = "INSUFFICIENT_DATA"
            causes.append(ThermalCause(code="ORIENTATION_MISSING"))
        elif uw.status != "OK" or uw.uw_w_m2k is None:
            u_verdict = "INSUFFICIENT_DATA"
            causes.append(ThermalCause(code="UW_UNKNOWN"))
        else:
            pct_max = window_max_pct(zone, orientation, uw.uw_w_m2k)
            if pct_max is None:
                # Declarado o verificado: superar 5,8 W/m²K no tiene
                # columna en la Tabla 3 — el complejo no cumple por %.
                if uw.authority == "DEMO":
                    u_verdict = "INSUFFICIENT_DATA"
                    causes.append(ThermalCause(code="DEMO_DATA"))
                else:
                    u_verdict = "FAILS"
                    causes.append(ThermalCause(code="U_BEYOND_TABLE"))
            else:
                u_verdict = _verdict_for_declared(fails=False, authority=uw.authority)
                if u_verdict == "INSUFFICIENT_DATA" and uw.authority != "DEMO":
                    causes.append(ThermalCause(code="UW_UNVERIFIED"))
                elif uw.authority == "DEMO":
                    causes.append(ThermalCause(code="DEMO_DATA"))

    order = {"FAILS": 3, "INSUFFICIENT_DATA": 2, "COMPLIES": 1, "NO_REQUIREMENT": 0}
    verdict = max(
        (air_verdict, u_verdict), key=lambda item: order[item]
    )
    if verdict == "NO_REQUIREMENT":
        verdict = "COMPLIES"
    return PositionThermalResult(
        uw=uw,
        classes=classes,
        verdict=verdict,  # type: ignore[arg-type]
        causes=causes,
        air_class_required=required_air,
        roof_u_max=roof_max,
        u_max=u_max,
        window_pct_max=pct_max,
    )


def orientation_compliance(
    *,
    zone: str,
    orientation: str,
    window_area_m2: Decimal,
    wall_area_m2: Decimal | None,
    max_uw: Decimal | None,
    max_uw_authority: AuthorityLevel | None,
) -> OrientationCompliance:
    """% de ventanas por orientación (Tabla 3, uso residencial).

    La exigencia toma la columna de la ventana de MAYOR U de la
    orientación; el % real necesita la superficie de paramentos que sólo
    el usuario puede declarar."""
    if orientation == "ROOF":
        return OrientationCompliance(
            orientation=orientation,
            window_area_m2=window_area_m2,
            verdict="NO_REQUIREMENT",
        )
    if max_uw is None:
        return OrientationCompliance(
            orientation=orientation,
            window_area_m2=window_area_m2,
            verdict="INSUFFICIENT_DATA",
            causes=[ThermalCause(code="UW_UNKNOWN")],
        )
    allowed = window_max_pct(zone, orientation, max_uw)
    if allowed is None:
        return OrientationCompliance(
            orientation=orientation,
            window_area_m2=window_area_m2,
            allowed_pct=None,
            verdict="INSUFFICIENT_DATA" if max_uw_authority == "DEMO" else "FAILS",
            causes=[ThermalCause(code="U_BEYOND_TABLE")],
        )
    if wall_area_m2 is None or wall_area_m2 <= 0:
        return OrientationCompliance(
            orientation=orientation,
            window_area_m2=window_area_m2,
            allowed_pct=allowed,
            verdict="INSUFFICIENT_DATA",
            causes=[ThermalCause(code="WALL_AREA_MISSING")],
        )
    actual = (window_area_m2 / wall_area_m2 * Decimal("100")).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    fails = actual > allowed
    verdict = _verdict_for_declared(fails=fails, authority=max_uw_authority)
    causes: list[ThermalCause] = []
    if verdict == "INSUFFICIENT_DATA":
        causes.append(ThermalCause(
            code="DEMO_DATA" if max_uw_authority == "DEMO" else "UW_UNVERIFIED"))
    return OrientationCompliance(
        orientation=orientation,
        window_area_m2=window_area_m2,
        wall_area_m2=wall_area_m2,
        actual_pct=actual,
        allowed_pct=allowed,
        verdict=verdict,  # type: ignore[arg-type]
        causes=causes,
    )
