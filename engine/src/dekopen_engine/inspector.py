"""Pure workshop verification of exact engine facts and explicit observations."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
import re

from dekopen_engine.hardware import NoCompatibleHardwareKit
from dekopen_engine.inspection_models import (
    AddBottomDrainHole, DiffPreconditions, Fixability, InspectionMode, InspectorConfig,
    InspectorConfigurationError, InspectorDiff, InspectorFinding, InspectorInput, InspectorResult,
    InspectorRuleId, InspectorSeverity, InspectorTarget, RuleEvaluation, RuleEvaluationStatus,
    WorkshopAnnotations,
)
from dekopen_engine.models import BayOpeningType, RailType

_D = Decimal
_PASS = RuleEvaluationStatus.PASS
_FAIL = RuleEvaluationStatus.FAIL
_NA = RuleEvaluationStatus.NOT_APPLICABLE
_MISSING = RuleEvaluationStatus.MISSING_INPUT
_YELLOW_RULES = {"R02", "R07", "R08", "R13"}
_BLOCKED_RULES = {"R01", "R05", "R09", "R12", "R14"}
_MESSAGES = {
    "R01": ("Carga de la hoja", "La hoja supera la carga admitida por el herraje.",
            "La hoja puede descolgarse.", "Revisar un kit autorizado de mayor capacidad o dividir el vano."),
    "R02": ("Proporción de la hoja", "La proporción de la hoja está fuera del rango recomendado.",
            "Puede dificultar la apertura y el cierre.", "Revisar la distribución y la proporción recomendada."),
    "R03": ("Dimensiones de la hoja", "La hoja está fuera de los límites del sistema y su herraje.",
            "El conjunto puede funcionar incorrectamente.", "Redimensionar dentro de los límites autorizados."),
    "R04": ("Composición del vidrio", "El área del vidrio supera el límite de su composición.",
            "Existe riesgo de rotura del vidrio.", "Consultar una composición de vidrio autorizada."),
    "R05": ("Refuerzo del travesaño", "El refuerzo no alcanza la exigencia estructural indicada.",
            "La resistencia al viento no está verificada.", "Solicitar revisión estructural del travesaño y su refuerzo."),
    "R06": ("Retención del relleno", "No hay junquillo compatible con el espesor del relleno.",
            "El vidrio o panel no puede sujetarse correctamente.", "Elegir un relleno compatible con la matriz del sistema."),
    "R07": ("Desagües inferiores", "El vano necesita un desagüe inferior adicional.",
            "Puede acumularse agua en el marco.", "Completar los desagües inferiores del vano."),
    "R08": ("Puntos de cierre", "Hay demasiada separación entre puntos de cierre.",
            "El sellado puede quedar incompleto.", "Revisar la distribución de cerraderos con el taller."),
    "R09": ("Dilatación del conjunto", "El tramo continuo necesita un acople de dilatación.",
            "La dilatación puede deformar el conjunto.", "Revisar la división del tramo y el acople autorizado."),
    "R10": ("Escuadra del marco", "Las diagonales medidas están fuera de tolerancia.",
            "El marco puede estar fuera de escuadra.", "Revisar físicamente el marco y volver a medir."),
    "R11": ("Holgura de cámara", "La holgura declarada del sistema está fuera de tolerancia.",
            "Puede impedir el correcto cierre de la hoja.", "Revisar la autoridad de holgura; el solape no la sustituye."),
    "R12": ("Refuerzo de corredera triple", "El refuerzo de la corredera triple es insuficiente.",
            "Puede deformarse el conjunto.", "Solicitar un refuerzo estructural autorizado."),
    "R13": ("Compases de la proyectante", "La hoja alta necesita dos compases.",
            "La hoja puede quedar sin soporte suficiente.", "Revisar un kit autorizado con los compases necesarios."),
    "R14": ("Carros de monoriel", "Los carros no cumplen la cantidad o capacidad exigida.",
            "Los carros pueden sobrecargarse.", "Revisar un kit monoriel autorizado de capacidad suficiente."),
}


def _drain_diff(target: InspectorTarget, width: Decimal, holes: list[Decimal]) -> InspectorDiff:
    center = width / _D("2")
    payload = json.dumps({"target": target.model_dump(), "width": str(width),
                          "holes": [str(x) for x in holes]}, sort_keys=True, separators=(",", ":"))
    return InspectorDiff(
        diff_id=sha256(payload.encode("utf-8")).hexdigest(), target=target,
        preconditions=DiffPreconditions(opening_width_mm=width, bottom_drain_holes_mm=holes),
        operations=[AddBottomDrainHole(target=target, old_value=holes,
                                      new_value=sorted([*holes, center]))],
    )


def _glass_class(spec: str | None) -> str | None:
    if spec is None:
        return None
    parts = spec.strip().split("-")
    def pane(text: str) -> Decimal | None:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:mm)?(?:\s+.*)?", text)
        return _D(match.group(1)) if match else None
    if len(parts) == 1 and pane(parts[0]) == _D("4"):
        return "MONOLITHIC_4"
    if len(parts) == 3 and pane(parts[0]) == _D("4") and pane(parts[2]) == _D("4"):
        return "DVH_4_ANY_4"
    return None


def inspect(data: InspectorInput, config: InspectorConfig) -> InspectorResult:
    if config.R02.min_ratio > config.R02.max_ratio or config.R03.min_width_mm > config.R03.max_width_mm:
        raise InspectorConfigurationError("Inverted rule limits")
    evaluations: list[RuleEvaluation] = []
    findings: list[InspectorFinding] = []
    annotations: dict[tuple[str, str | None], WorkshopAnnotations] = {}
    for supplied in data.annotations:
        key = (supplied.bay_id, supplied.leaf_id)
        if key in annotations:
            raise ValueError("Duplicate annotation target")
        annotations[key] = supplied
    structural = {item.target_id: item for item in data.structural_inputs}
    if len(structural) != len(data.structural_inputs):
        raise ValueError("Duplicate structural target")

    def record(rule: str, result: RuleEvaluationStatus, bay: str | None = None,
               leaf: str | None = None, *, diff: InspectorDiff | None = None,
               diagnosis: str | None = None) -> None:
        rule_id = InspectorRuleId(rule)
        evaluations.append(RuleEvaluation(rule_id=rule_id, status=result, bay_id=bay, leaf_id=leaf))
        if result not in (_FAIL, _MISSING):
            return
        title, default_diagnosis, risk, recommendation = _MESSAGES[rule]
        if result is _MISSING and diagnosis is None:
            diagnosis = f"Faltan datos de taller para verificar: {title.lower()}."
        findings.append(InspectorFinding(
            rule_id=rule_id, severity=(InspectorSeverity.YELLOW if rule in _YELLOW_RULES
                                    else InspectorSeverity.RED), title=title,
            diagnosis=diagnosis or default_diagnosis, risk=risk, recommendation=recommendation,
            fixability=(Fixability.AUTO_FIXABLE if diff else
                        Fixability.BLOCKED_MISSING_AUTHORITY if rule in _BLOCKED_RULES
                        or (rule == "R04" and result is _MISSING)
                        else Fixability.SUGGESTION_ONLY), bay_id=bay, leaf_id=leaf, fix=diff,
        ))

    for leaf in data.computation.leaves:
        bay, leaf_id = leaf.bay_id, leaf.leaf_id
        kit = leaf.selected_kit
        weight = leaf.exact_weight
        candidates = [c for c in leaf.candidates if c.opening_match and c.rail_match]
        if kit is None and not candidates:
            raise NoCompatibleHardwareKit("No applicable hardware candidate for inspection")
        if kit is not None and weight is not None:
            record("R01", _MISSING if weight.total_weight_kg is None else
                   _FAIL if weight.total_weight_kg > kit.max_leaf_weight_kg else _PASS, bay, leaf_id)
        else:
            dimensional = [c for c in candidates if c.width_match and c.height_match]
            record("R01", (_FAIL if dimensional and all(c.weight_match is False for c in dimensional)
                           else _MISSING), bay, leaf_id)
        w, h = leaf.finished_width_mm, leaf.finished_height_mm
        if w <= 0 or h <= 0:
            raise ValueError("Nonpositive finished leaf facts")
        ratio = h / w
        record("R02", _FAIL if ratio < config.R02.min_ratio or ratio > config.R02.max_ratio else _PASS,
               bay, leaf_id)
        kits = [kit] if kit is not None else [c.kit for c in candidates]
        inside = any(max(config.R03.min_width_mm, k.min_leaf_width_mm) <= w <=
                     min(config.R03.max_width_mm, k.max_leaf_width_mm)
                     and k.min_leaf_height_mm <= h <= min(config.R03.max_height_mm, k.max_leaf_height_mm)
                     for k in kits)
        record("R03", _PASS if inside else _FAIL, bay, leaf_id)
        annotation = annotations.get((bay, leaf_id))
        points = None if annotation is None else annotation.closing_points_perimeter_mm
        perimeter = _D("2") * (w + h)
        if points is None or len(points) < 2:
            record("R08", _MISSING, bay, leaf_id)
        else:
            if any(p >= perimeter for p in points):
                raise ValueError("Closing point is outside the leaf perimeter")
            ordered = sorted(points)
            gaps = [right - left for left, right in zip(ordered, ordered[1:])]
            gaps.append(perimeter - ordered[-1] + ordered[0])
            record("R08", _FAIL if max(gaps) > config.R08.max_spacing_mm else _PASS, bay, leaf_id)
        clearance = data.chamber_clearance_mm
        record("R11", _MISSING if clearance is None else _FAIL if
               abs(clearance - config.R11.expected_mm) > config.R11.tolerance_mm else _PASS, bay, leaf_id)
        if leaf.opening_type is BayOpeningType.SLIDING_3L:
            opening = next((o for o in data.computation.openings if o.bay_id == bay), None)
            ix = data.reinforcement_ix_by_target.get(bay)
            state = (_MISSING if opening is None else _NA if opening.width_mm <= config.R12.width_trigger_mm
                     else _MISSING if ix is None else _FAIL if ix < config.R12.minimum_ix_cm4 else _PASS)
            record("R12", state, bay, leaf_id)
        if leaf.opening_type is BayOpeningType.AWNING:
            state = (_PASS if h <= config.R13.height_trigger_mm else _MISSING if kit is None else
                     _FAIL if kit.stay_arms_qty < config.R13.required_stay_arms else _PASS)
            record("R13", state, bay, leaf_id)
        if leaf.rail_type is RailType.MONO:
            state = (_MISSING if weight is None or weight.total_weight_kg is None else _PASS if
                     weight.total_weight_kg <= config.R14.weight_trigger_kg else
                     _MISSING if kit is None or kit.carriage_capacity_kg is None else
                     _FAIL if kit.carriages_qty < config.R14.required_carriages or
                     kit.carriage_capacity_kg < config.R14.minimum_capacity_kg else _PASS)
            record("R14", state, bay, leaf_id)

    for infill in data.computation.infills:
        if infill.kind == "PANEL":
            record("R04", _NA, infill.bay_id, infill.leaf_id)
        else:
            glass_class = _glass_class(infill.glass_spec)
            limit = (config.R04.monolithic_4_max_area_m2 if glass_class == "MONOLITHIC_4" else
                     config.R04.dvh_4_any_4_max_area_m2 if glass_class == "DVH_4_ANY_4" else None)
            record("R04", _MISSING if limit is None else _FAIL if infill.exact_area_m2 > limit
                   else _PASS, infill.bay_id, infill.leaf_id)
        record("R06", _PASS if infill.bead_supported else _FAIL, infill.bay_id, infill.leaf_id)
    for span in data.computation.spans:
        source = structural.get(span.target_id)
        ix = data.reinforcement_ix_by_target.get(span.target_id)
        if span.span_mm <= config.R05.span_trigger_mm:
            record("R05", _NA, span.target_id)
        elif (source is None or source.required_ix_cm4 is None or not source.structural_basis
              or not source.structural_basis.strip() or ix is None):
            record("R05", _MISSING, span.target_id,
                   diagnosis=("Falta la exigencia estructural de viento para verificar este travesaño."
                              if source is None or source.required_ix_cm4 is None or
                              not source.structural_basis or not source.structural_basis.strip()
                              else "Falta la inercia del refuerzo para verificar este travesaño."))
        else:
            record("R05", _FAIL if ix < source.required_ix_cm4 else _PASS, span.target_id)
    for opening in data.computation.openings:
        annotation = annotations.get((opening.bay_id, None))
        holes = None if annotation is None else annotation.bottom_drain_holes_mm
        if holes is not None and any(p > opening.width_mm for p in holes):
            raise ValueError(f"Drain is outside its opening (bay {opening.bay_id})")
        if opening.width_mm <= config.R07.width_trigger_mm:
            record("R07", _PASS, opening.bay_id)
        elif holes is None:
            record("R07", _MISSING, opening.bay_id)
        elif len(holes) >= config.R07.required_bottom_drains:
            record("R07", _PASS, opening.bay_id)
        else:
            center = opening.width_mm / _D("2")
            fix = (_drain_diff(InspectorTarget(bay_id=opening.bay_id), opening.width_mm, holes)
                   if config.R07.required_bottom_drains == 3 and len(holes) == 2
                   and center not in holes and 0 < center < opening.width_mm else None)
            record("R07", _FAIL, opening.bay_id, diff=fix)
        if (annotation is None or annotation.continuous_width_mm is None or
                annotation.finish_class is None or annotation.has_coupler is None):
            record("R09", _MISSING, opening.bay_id)
        else:
            limit = config.R09.white_limit_mm if annotation.finish_class == "WHITE" else config.R09.foiled_limit_mm
            record("R09", _FAIL if annotation.continuous_width_mm > limit and not annotation.has_coupler
                   else _PASS, opening.bay_id)
        if data.mode is InspectionMode.DESIGN:
            record("R10", _NA, opening.bay_id)
        elif annotation is None or annotation.measured_d1_mm is None or annotation.measured_d2_mm is None:
            record("R10", _MISSING, opening.bay_id)
        else:
            record("R10", _FAIL if abs(annotation.measured_d1_mm - annotation.measured_d2_mm) >
                   config.R10.tolerance_mm else _PASS, opening.bay_id)
    for rule in InspectorRuleId:
        if not any(e.rule_id is rule for e in evaluations):
            record(rule.value, _NA)
    evaluations.sort(key=lambda e: (e.rule_id.value, e.bay_id or "", e.leaf_id or ""))
    findings.sort(key=lambda f: (f.rule_id.value, f.bay_id or "", f.leaf_id or ""))
    red = any(f.severity is InspectorSeverity.RED for f in findings)
    return InspectorResult(status="RED" if red else "YELLOW" if findings else "GREEN",
                           production_allowed=not red, evaluations=evaluations, findings=findings,
                           source_calculation_hash=data.source_calculation_hash)


def apply_inspector_diff(
    annotations: list[WorkshopAnnotations], diff: InspectorDiff, opening_width_mm: Decimal,
) -> list[WorkshopAnnotations]:
    """Validate a single allowed operation before returning a new local draft."""
    if len(diff.operations) != 1 or diff.preconditions.opening_width_mm != opening_width_mm:
        raise ValueError("Stale or invalid correction")
    matches = [i for i, item in enumerate(annotations)
               if (item.bay_id, item.leaf_id) == (diff.target.bay_id, diff.target.leaf_id)]
    if len(matches) != 1:
        raise ValueError("Correction target is missing or ambiguous")
    index = matches[0]
    old = annotations[index].bottom_drain_holes_mm
    operation = diff.operations[0]
    center = opening_width_mm / _D("2")
    if (old is None or len(old) != 2 or center in old or
            old != diff.preconditions.bottom_drain_holes_mm or old != operation.old_value or
            operation.target != diff.target or operation.new_value != sorted([*old, center])):
        raise ValueError("Correction preconditions no longer hold")
    draft = [a.model_copy(deep=True) for a in annotations]
    draft[index] = draft[index].model_copy(update={"bottom_drain_holes_mm": operation.new_value[:]})
    return draft
