"""Design assist: natural-language intent → validated typed ops.

The provider never touches the product — it proposes operations against the
single ops registry (`ops_registry.py`); this service validates every one
against the actual assembly (bounds, enums, catalog membership, bay/divider
refs, simulación estructural) before the response exists. Rejected ops are
reported, never silently dropped: low-confidence intent must not mutate a
position. Ops de posición (system/finish/location/quantity) se validan
contra la fila y se devuelven con scope "position" para que el cliente las
aplique por el canal de posición — nunca dentro del producto.

El contrato lo publica `contract_document()` (OpenAPI + TS generado): la UI,
la IA y la API comparten exactamente el mismo vocabulario."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from ai_gateway import service as gateway
from ai_gateway.context import _system_opening_options
from authentication.errors import contract_error
from engine_api.repository import SystemParamsRepository
from pricing.repository import rows

from . import design_ops_sim as sim
from .design_prompt import design_assist_system
from .ops_registry import ops_contract

CAPABILITY = "design_assist"

# Conjunto canónico de aperturas — design_alternatives lo importa como la
# lista cerrada pre-D03; el validador de ops usa las capacidades vivas del
# sistema (catalog["opening_keys"]), este nombre queda para compatibilidad.
OPENINGS = {
    "FIXED",
    "TURN_LEFT",
    "TURN_RIGHT",
    "TILT_TURN_LEFT",
    "TILT_TURN_RIGHT",
    "SLIDING_2L",
    "AWNING",
    "DOOR_ENTRY",
}

MAX_MODULE_COUNT = 12
MAX_OPS = 50
# Cuántas opciones admite una aclaración — más de 4 chips no es una
# aclaración, es un formulario.
MAX_CLARIFY_OPTIONS = 4

# Refs sintéticas que el validador resuelve y el cliente recrea por orden de
# aplicación — mismo patrón que added_m{}/added_c{}.
_ADDED_BAY_RE = re.compile(r"^added_b(\d+)$")
_ADDED_DIVIDER_RE = re.compile(r"^added_d(\d+)$")


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _in_range(value: Any, low: Decimal, high: Decimal) -> bool:
    parsed = _number(value)
    return parsed is not None and low <= parsed <= high


def _ref(raw: Any, prefix: str, index: int) -> str:
    """Stable domain id for a wire entity — the module/coupling id the client
    assigned, falling back to a positional m{n}/c{n} when absent (legacy
    payloads without ids still resolve)."""
    if isinstance(raw, dict) and isinstance(raw.get("id"), str) and raw["id"].strip():
        return str(raw["id"].strip())
    return f"{prefix}{index + 1}"


def _module_tree(module: Any) -> dict[str, Any] | None:
    """The parametric tree of a wire module — dict or absent (the client
    always sends it; a persisted bare IntentNode arrives wrapped)."""
    if isinstance(module, dict) and isinstance(module.get("tree"), dict):
        return module["tree"]
    return None


def _bay_summary(node: dict[str, Any]) -> dict[str, Any]:
    """La proyección de una hoja para el modelo y el validador — id real,
    apertura efectiva y spec de infill para refs legibles por el prompt."""
    return {
        "ref": node.get("id"),
        "opening_type": sim.opening_of(node),
        "glass_article_sku": node.get("glass_article_sku"),
        "glass_spec": node.get("glass_spec"),
        "glass_thickness_mm": node.get("glass_thickness_mm"),
        "panel_article_sku": node.get("panel_article_sku"),
        "handle_height_mm": node.get("handle_height_mm"),
        "door_handedness": node.get("door_handedness"),
    }


def _normalize_product(
    product: Any, *, width_mm: Any = None, height_mm: Any = None
) -> tuple[list[Any], list[Any]] | None:
    """Normaliza las cuatro formas que un producto toma en la superficie:

    - wire del canvas ``{modules: [...], couplings: [...]}``;
    - persistido producto-v2 ``{version: 'product-v2', assembly: {...}}``;
    - diseño de unidad única ``{parametric_tree, nominal_width_mm, ...}``;
    - IntentNode persistido pelado ``{type: 'BAY'|'SPLIT_V'|'SPLIT_H'|'ROOT'}``
      (el árbol que la fila de posición guarda en parametric_tree — la causa
      raíz 2 del baseline IA1: el resumen rechazaba esta forma y el agente
      contestaba unsupported_product en todos los casos J).

    Devuelve (modules_raw, couplings_raw) o None."""
    if not isinstance(product, dict):
        return None
    modules_raw = product.get("modules")
    couplings_raw = product.get("couplings")
    if isinstance(modules_raw, list):
        return modules_raw, couplings_raw if isinstance(couplings_raw, list) else []
    assembly = product.get("assembly")
    if isinstance(assembly, dict) and isinstance(assembly.get("modules"), list):
        couplings = assembly.get("couplings")
        return assembly["modules"], couplings if isinstance(couplings, list) else []
    tree = product.get("parametric_tree")
    if not isinstance(tree, dict) and product.get("type") in (
        "BAY",
        "SPLIT_V",
        "SPLIT_H",
        "ROOT",
    ):
        tree = product
    if not isinstance(tree, dict):
        return None
    module_width = (
        product.get("width_mm")
        or product.get("nominal_width_mm")
        or width_mm
    )
    module_height = (
        product.get("height_mm")
        or product.get("nominal_height_mm")
        or height_mm
    )
    if _number(module_width) is None or _number(module_height) is None:
        return None
    return (
        [
            {
                "id": tree.get("id") if isinstance(tree.get("id"), str) else None,
                "width_mm": module_width,
                "height_mm": module_height,
                "tree": tree,
            }
        ],
        [],
    )


def _summary(
    product: Any, *, width_mm: Any = None, height_mm: Any = None
) -> dict[str, Any] | None:
    """The client-submitted (or persisted) product surface — the same
    modules and couplings the returned ops will be applied against, so
    bounds are derived here and can never drift against a stale copy.
    Ops address entities by stable `ref` (the client's own id), never by
    position: removing a module mid-sequence keeps the survivors' refs
    honest, the coupling endpoints expose the assembly graph — which module
    edge meets which —, and each module carries its bays/splits with refs
    so bay-level ops can address a leaf."""
    normalized = _normalize_product(product, width_mm=width_mm, height_mm=height_mm)
    if normalized is None:
        return None
    modules_raw, couplings_raw = normalized
    if not 1 <= len(modules_raw) <= MAX_MODULE_COUNT or len(couplings_raw) > MAX_MODULE_COUNT:
        return None
    module_refs = [_ref(module, "m", index) for index, module in enumerate(modules_raw)]
    ref_by_id = {
        str(module["id"]).strip(): ref
        for module, ref in zip(modules_raw, module_refs)
        if isinstance(module, dict) and isinstance(module.get("id"), str) and module["id"].strip()
    }
    modules: list[dict[str, Any]] = []
    for index, (ref, module) in enumerate(zip(module_refs, modules_raw)):
        tree = _module_tree(module)
        bays = sim.bays(tree) if tree is not None else []
        divisions = sim.divisions(tree) if tree is not None else []
        modules.append(
            {
                "ref": ref,
                "index": index,
                "width_mm": module.get("width_mm") if isinstance(module, dict) else None,
                "height_mm": module.get("height_mm") if isinstance(module, dict) else None,
                "shape": (
                    "CONTOUR"
                    if isinstance(module, dict) and isinstance(module.get("contour"), dict)
                    else "RECT"
                ),
                "frameless": bool(
                    isinstance(module, dict) and isinstance(module.get("frameless"), dict)
                ),
                "bays": [_bay_summary(node) for node in bays],
                "splits": [
                    {
                        "ref": node.get("id"),
                        "type": node.get("type"),
                        "offset_mm": node.get("split_offset_mm"),
                        "mullion_profile_sku": node.get("mullion_profile_sku"),
                    }
                    for node in divisions
                ],
                # El árbol crudo queda fuera del payload del modelo; vive en
                # la vista del validador (`tree` nunca se serializa al LLM).
                "tree": tree,
            }
        )
    return {
        "modules": modules,
        "couplings": [
            {
                "ref": _ref(coupling, "c", index),
                "index": index,
                "angle_deg": coupling.get("angle_deg") if isinstance(coupling, dict) else None,
                "kind": (coupling.get("kind") or "INLINE") if isinstance(coupling, dict) else None,
                "modules": (
                    [ref_by_id.get(str(mid), str(mid)) for mid in coupling["modules"]]
                    if isinstance(coupling, dict)
                    and isinstance(coupling.get("modules"), list)
                    else None
                ),
                "edges": coupling.get("edges") if isinstance(coupling, dict) else None,
            }
            for index, coupling in enumerate(couplings_raw)
        ],
    }


def _catalog(system_id: UUID, org_id: UUID) -> dict[str, Any]:
    """The selected system's authoritative material surface — a SKU is a
    catalog identifier, never free text, so proposed glass, panels,
    thicknesses, openings and mullions must resolve against the same
    options the estimator sees. La familia del sistema sale de su propia
    fila en profile_systems — las capacidades D03 se leen por system_id.
    load_visible scopes to the org: a system the tenant cannot see is the
    same 404 the design-options surface returns."""
    repository = SystemParamsRepository()
    params = repository.load_visible(system_id, org_id)
    glass_rows = rows(
        "SELECT DISTINCT ON (technical_sku) technical_sku, glass_spec "
        "FROM public.glass_purchase_mappings "
        "WHERE system_id=%s AND (org_id=%s OR org_id IS NULL) "
        "ORDER BY technical_sku, org_id NULLS LAST, version DESC",
        [system_id, org_id],
    )
    # Members: las caras declaradas de cada rol — la misma fuente que el
    # canvas (options endpoint) usa para acotar offsets de divisiones.
    articles = params.effective_profile_articles or {}
    members: dict[str, Decimal | None] = {
        "frame_mm": None,
        "sash_mm": None,
        "mullion_v_mm": None,
        "mullion_h_mm": None,
        "threshold_mm": None,
    }
    role_key = {
        "frame_mm": "FRAME",
        "sash_mm": "SASH",
        "mullion_v_mm": "MULLION_V",
        "mullion_h_mm": "MULLION_H",
        "threshold_mm": "THRESHOLD",
    }
    mullions: dict[str, dict[str, Any]] = {}
    for key, role in role_key.items():
        article = articles.get(role)
        if article is None:
            continue
        members[key] = article.face_width_mm
        if role in ("MULLION_V", "MULLION_H"):
            mullions[f"SPLIT_{role[-1]}"] = {
                "sku": article.sku,
                "face_mm": article.face_width_mm,
            }
    # Series elegibles de la organización (para set_system / add_position).
    system_rows = rows(
        "SELECT id, code, system_family, material FROM public.profile_systems "
        "WHERE (org_id=%s OR org_id IS NULL) AND is_active ORDER BY code LIMIT 20",
        [org_id],
    )
    # Aperturas del sistema: las capacidades declaradas D03 (o el default
    # de la familia) — claves reales de spec_options_from_capabilities.
    openings = _system_opening_options(
        org_id,
        {
            "system_uuid": system_id,
            "system_family": next(
                (
                    item["system_family"]
                    for item in system_rows
                    if str(item["id"]) == str(system_id)
                ),
                "ALUMINIUM",
            ),
        },
    )
    # Regla de altura de manilla de la familia (D04) — acota set_handle_height.
    handle_rule = None
    for family in params.hardware_families.values():
        if family.handle_height_rule:
            handle_rule = {
                "rule": family.handle_height_rule,
                "min_mm": family.handle_height_min_mm,
                "max_mm": family.handle_height_max_mm,
                "default_mm": family.handle_height_default_mm,
            }
            break
    return {
        "glass_skus": {item["technical_sku"] for item in glass_rows},
        # A SKU carries its composition recipe — "4-16-4", never the bead
        # slot number. Absent recipes resolve downstream as monolithic.
        "glass_recipes": {
            item["technical_sku"]: (item.get("glass_spec") or "").strip() or None
            for item in glass_rows
        },
        "panel_skus": set(params.available_panel_rules),
        "thicknesses": set(params.glazing_bead_rules),
        "openings": openings,
        # Keys D03 y alias legacy — el validador acepta ambas formas (el
        # glosario del prompt enseña TILT_TURN_LEFT y el catálogo ofrece
        # PRIMARY:TILT_TURN:LEFT:INWARD; el frontend resuelve las dos).
        "opening_keys": {
            str(option["key"])
            for option in openings
            if isinstance(option.get("key"), str)
        }
        | {
            str(option["legacy"])
            for option in openings
            if isinstance(option.get("legacy"), str)
        },
        "mullions": mullions,
        "members": members,
        "finishes": set(params.finishes or ("WHITE",)),
        "handle_rule": handle_rule,
        "systems": {
            str(item["id"]): {
                "code": item["code"],
                "system_family": item["system_family"],
                "material": item.get("material"),
            }
            for item in system_rows
        },
    }


_NUMBER_WORDS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
}
# '-' signs a number only when its left context is not a number or a unit:
# 'ángulo -30' declares -30 while '30-20', '30 -20', '30 mm - 20 mm' and
# '30° - 20°' all keep both endpoints positive.
_UNITS = {
    "mm",
    "milimetro",
    "milimetros",
    "milímetro",
    "milímetros",
    "cm",
    "m",
    "mt",
    "mts",
    "metro",
    "metros",
    "grado",
    "grados",
}
_LEFT_TOKEN_RE = re.compile(r"°|\d[\d.,]*|[\wáéíóúñü]+", re.IGNORECASE)
_MEASURE_RE = re.compile(
    r"(?<![\d.,])(-?\d+(?:[.,]\d+)*)\s*(mm|mil[ií]metros?|cm|metros?|mts?|m)\b",
    re.IGNORECASE,
)
_BARE_NUMBER_RE = re.compile(r"(?<![\d.,])-?\d+(?:[.,]\d+)*")
_WORD_NUMBER_RE = re.compile(
    r"\b(uno?|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)\b",
    re.IGNORECASE,
)


def _parse_number(token: str) -> Decimal | None:
    """Chilean-locale number: '.' groups thousands (2.400 → 2400), ',' is the
    decimal mark (2,4 → 2.4). A lone '.' with three trailing digits reads as
    thousands so '2.400' means 2400, matching how users write medidas."""
    try:
        if "." in token and "," in token:
            normalized = token.replace(".", "").replace(",", ".")
        elif token.count(".") == 1 and len(token.rsplit(".", 1)[1]) == 3:
            normalized = token.replace(".", "")
        else:
            normalized = token.replace(",", ".")
        value = Decimal(normalized)
    except ArithmeticError:
        return None
    return value if value.is_finite() else None


def _unary_minus(text: str, start: int) -> bool:
    """Whether the '-' before `start` signs the number rather than separating
    a range or subtraction. The dash is binary only when it directly follows
    a number, degree mark or unit (whitespace aside): '30 -20', '30mm-20mm',
    '30° - 20°' stay positive, while 'ángulo -30' and '30°; -20°' — where a
    clause delimiter sits between — keep the sign."""
    left = None
    left_end = None
    for token in _LEFT_TOKEN_RE.finditer(text[:start]):
        # Chilean numbers can carry a trailing '.' or ',' (2.400, 2,4) — but a
        # token ending in punctuation is the number plus a delimiter: trim it
        # so '30, -20' sees the comma as the clause break it is.
        left = token.group(0).rstrip(".,;:")
        left_end = token.start() + len(left)
    if left is None or not left:
        return True
    if text[left_end:start].strip():
        # A delimiter (semicolon, slash, comma, conjunction) starts a new
        # clause — the minus signs what follows it.
        return True
    if left == "°" or left.lower() in _UNITS:
        return False
    return not left[0].isdigit()


def _declared_values(prompt: str) -> set[Decimal]:
    """Every number the user actually wrote — the grounding set numeric ops
    must cite. The model proposes structure; it may never introduce a
    measurement the request did not contain. Unit-suffixed measures normalize
    to mm, bare numbers count literally, number words cover counts."""
    values: set[Decimal] = set()
    for match in _MEASURE_RE.finditer(prompt):
        token = match.group(1)
        if token.startswith("-") and not _unary_minus(prompt, match.start(1)):
            token = token[1:]
        number = _parse_number(token)
        if number is None:
            continue
        unit = match.group(2).lower()
        if unit == "cm":
            factor = Decimal(10)
        elif unit.startswith("mm") or unit.startswith("mil"):
            factor = Decimal(1)
        else:  # m, mt, mts, metro, metros
            factor = Decimal(1000)
        values.add(number * factor)
    # Unit-suffixed spans are consumed by the first pass — their raw tokens
    # must not re-enter the set unconverted ('240 cm' declares 2400mm, not 240).
    scan = _MEASURE_RE.sub("", prompt)
    for match in _BARE_NUMBER_RE.finditer(scan):
        token = match.group(0)
        if token.startswith("-") and not _unary_minus(scan, match.start()):
            token = token[1:]
        number = _parse_number(token)
        if number is not None:
            values.add(number)
    for word in _WORD_NUMBER_RE.findall(prompt):
        values.add(Decimal(_NUMBER_WORDS[word.lower()]))
    return values


def _context_numbers(summary: dict[str, Any], catalog: dict[str, Any]) -> set[Decimal]:
    """Números del contexto que una op puede citar: medidas del producto
    (anchos, altos, offsets de divisiones, alturas de manilla) y datos del
    catálogo (espesores declarados, caras de perfiles). Un número del
    contexto es verdad del diseño — el modelo puede referenciarlo ("el
    mismo ancho que el módulo de la izquierda")."""
    values: set[Decimal] = set()

    def _collect(value: Any) -> None:
        parsed = _number(value)
        if parsed is not None:
            values.add(parsed)

    for module in summary.get("modules") or []:
        if not isinstance(module, dict):
            continue
        _collect(module.get("width_mm"))
        _collect(module.get("height_mm"))
        for split in module.get("splits") or []:
            _collect(split.get("offset_mm"))
        for bay in module.get("bays") or []:
            _collect(bay.get("handle_height_mm"))
            _collect(bay.get("glass_thickness_mm"))
    for coupling in summary.get("couplings") or []:
        _collect(coupling.get("angle_deg"))
    for thickness in catalog.get("thicknesses") or ():
        _collect(thickness)
    for member in (catalog.get("members") or {}).values():
        _collect(member)
    for spec in (catalog.get("mullions") or {}).values():
        _collect(spec.get("face_mm"))
    handle_rule = catalog.get("handle_rule")
    if isinstance(handle_rule, dict):
        for key in ("min_mm", "max_mm", "default_mm"):
            _collect(handle_rule.get(key))
    return values


def _citable_values(
    declared: set[Decimal], context: set[Decimal]
) -> set[Decimal]:
    """El conjunto que una op numérica puede citar: lo que el usuario
    declaró, los números del contexto, y derivaciones aritméticas
    inequívocas de ellos (suma, resta, mitad, doble). "Rechazar un número
    derivado correcto es un bug" — el motor calcula, la IA cita."""
    base = declared | context
    values = set(base)
    for a in declared:
        for b in context:
            values.add(a + b)
            diff = a - b
            values.add(diff if diff >= 0 else -diff)
        for scale in (Decimal(2), Decimal(3), Decimal(4)):
            values.add(a * scale)
    for b in context:
        for scale in (Decimal(2), Decimal(3), Decimal(4)):
            values.add(b * scale)
            values.add(b / scale)
    # Pares contexto↔contexto solo en suma/resta (un ancho total derivado
    # de la suma de anchos del conjunto, un sobrante como diferencia).
    context_list = sorted(context)
    for i, a in enumerate(context_list):
        for b in context_list[i + 1 :]:
            values.add(a + b)
            values.add(b - a)
    return values


def _validate_ops(
    ops: Any,
    summary: dict[str, Any],
    catalog: dict[str, Any],
    declared: set[Decimal],
    declared_strict: set[Decimal] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate each op against a simulated assembly that evolves in op order —
    structural ops mutate the ref sets every later op is checked against, so
    a proposal can never address a module that stopped existing or grow the
    assembly past MAX_MODULE_COUNT. Ops address entities by stable domain
    ref — the client-assigned id — or by a legacy positional index; the wire
    always echoes the canonical ref back so the applier resolves identity,
    not position."""
    module_refs = [str(module["ref"]) for module in summary["modules"]]
    coupling_refs = [str(coupling["ref"]) for coupling in summary["couplings"]]
    module_info = {str(module["ref"]): module for module in summary["modules"]}
    # Which module edges couplings already claim — where a duplicate may land
    # and which kinds a joint may take. Legacy couplings without endpoints are
    # the linear chain i↔i+1 on right/left.
    used_edges: dict[str, set[str]] = {}
    for index, coupling in enumerate(summary["couplings"]):
        members, edges = coupling.get("modules"), coupling.get("edges")
        if (
            isinstance(members, list)
            and isinstance(edges, list)
            and len(members) == len(edges) == 2
        ):
            for member, edge in zip(members, edges):
                if isinstance(member, str) and isinstance(edge, str):
                    used_edges.setdefault(member, set()).add(edge)
        elif index + 1 < len(module_refs):
            used_edges.setdefault(module_refs[index], set()).add("right")
            used_edges.setdefault(module_refs[index + 1], set()).add("left")
    # Members hanging at the "bottom" edge of a STACKED coupling — the
    # front chain end resolves over roots first, exactly as the client's
    # isStackedMember does.
    stacked_members: set[str] = set()
    for coupling in summary["couplings"]:
        members, edges = coupling.get("modules"), coupling.get("edges")
        if (
            (coupling.get("kind") or "INLINE") == "STACKED"
            and isinstance(members, list)
            and isinstance(edges, list)
            and len(members) == len(edges) == 2
        ):
            for member, edge in zip(members, edges):
                if edge == "bottom" and isinstance(member, str):
                    stacked_members.add(member)
    # The simulated coupling graph — modules/edges/kind per coupling ref,
    # seeded from the summary (legacy rows without endpoints resolve to the
    # linear chain) and evolved by every structural op so remove_unit,
    # insert_module and kind changes see the graph the client would build,
    # not declaration-order neighbors.
    sim_couplings: dict[str, dict[str, Any]] = {}
    for index, coupling in enumerate(summary["couplings"]):
        c_ref = str(coupling["ref"])
        members, edges = coupling.get("modules"), coupling.get("edges")
        if (
            isinstance(members, list)
            and isinstance(edges, list)
            and len(members) == len(edges) == 2
        ):
            sim_couplings[c_ref] = {
                "modules": [str(member) for member in members],
                "edges": list(edges),
                "kind": coupling.get("kind") or "INLINE",
            }
        else:
            sim_couplings[c_ref] = {
                "modules": module_refs[index : index + 2]
                if index + 1 < len(module_refs)
                else [],
                "edges": ["right", "left"],
                "kind": "INLINE",
            }
    # Árboles simulados por módulo — el validador los clona y muta con las
    # ops de hoja/división (misma semántica que intentEditing en el
    # frontend) para que las referencias posteriores vean la estructura
    # evolucionada.
    sim_modules: dict[str, dict[str, Any]] = {}
    for module in summary["modules"]:
        tree = module.get("tree")
        sim_modules[str(module["ref"])] = {
            "tree": sim.clone_tree(tree) if isinstance(tree, dict) else None,
            "width_mm": _number(module.get("width_mm")),
            "height_mm": _number(module.get("height_mm")),
        }
    state: dict[str, Any] = {
        # Copied: structural ops mutate these lists while positional
        # addresses resolve against the ORIGINAL `module_refs`/`coupling_refs`
        # — sharing the object would corrupt the positional map.
        "module_refs": list(module_refs),
        "coupling_refs": list(coupling_refs),
        "used_edges": used_edges,
        "stacked_members": stacked_members,
        "sim_couplings": sim_couplings,
        "sim_modules": sim_modules,
        "added": {"m": 0, "c": 0, "b": 0, "d": 0},
        # Refs sintéticas en orden de acuñación — added_b{n}/added_d{n} del
        # wire resuelven la hoja/división creada por la n-ésima split_bay.
        "added_bays": [],
        "added_dividers": [],
    }

    def _add_ref(prefix: str) -> str:
        state["added"][prefix] += 1
        return f"added_{prefix}{state['added'][prefix]}"

    _OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}

    def _claim(ref: str, edge: str) -> None:
        if ref in state["module_refs"]:
            state["used_edges"].setdefault(ref, set()).add(edge)

    def _free(member: Any, edge: Any) -> None:
        if isinstance(member, str) and isinstance(edge, str) and member in state["used_edges"]:
            state["used_edges"][member].discard(edge)

    def _add_coupling(
        members: list[str], edges: list[Any], kind: str = "INLINE"
    ) -> str:
        """Mint a simulated joint: register its ref, claim each member edge,
        and fold stacked membership for a STACKED "bottom" endpoint."""
        ref = _add_ref("c")
        state["sim_couplings"][ref] = {
            "modules": list(members),
            "edges": list(edges),
            "kind": kind,
        }
        for member, edge in zip(members, edges):
            _claim(member, edge)
            if kind == "STACKED" and edge == "bottom" and isinstance(member, str):
                state["stacked_members"].add(member)
        return ref

    def _drop_coupling(ref: str) -> None:
        """Remove a simulated joint: free the edges it claimed on live
        members and drop its stacked member, exactly as the client's
        coupling removal heals the graph."""
        info = state["sim_couplings"].pop(ref, None)
        if info is None:
            return
        for member, edge in zip(info["modules"], info["edges"]):
            _free(member, edge)
            if info.get("kind") == "STACKED" and edge == "bottom" and isinstance(member, str):
                state["stacked_members"].discard(member)

    def _chain_end(side: str) -> str | None:
        """The declaration-extreme module whose `side` edge is free — the
        same end the client appends to: roots win over stacked members."""
        candidates: list[str] = [
            ref for ref in state["module_refs"]
            if side not in state["used_edges"].get(ref, set())
        ]
        if not candidates:
            return None
        roots = [ref for ref in candidates if ref not in state["stacked_members"]]
        preferred = roots if roots else candidates
        return str(preferred[-1] if side == "right" else preferred[0])

    def _coupling_edges(info: dict[str, Any] | None) -> list[Any] | None:
        edges = info.get("edges") if isinstance(info, dict) else None
        return edges if isinstance(edges, list) else None

    def _coupling_state(ref: str) -> dict[str, Any] | None:
        """The live coupling record — simulated joints shadow the summary's
        declaration so ops after a structural edit see the evolved graph."""
        return sim_couplings.get(ref)

    def _seam_endpoints(ref: str) -> tuple[str | None, str | None, str | None, str | None]:
        """(left_ref, left_edge, right_ref, right_edge) the seam joins —
        'left' claims the right edge of the left member. Live sim state
        only: a seam the client couldn't open never resolves endpoints."""
        info = _coupling_state(ref)
        if info is None:
            return None, None, None, None
        left_ref = right_ref = left_edge = right_edge = None
        for member, edge in zip(info["modules"], info["edges"]):
            if edge == "right":
                left_ref, left_edge = member, edge
            elif edge == "left":
                right_ref, right_edge = member, edge
        return (
            left_ref if left_ref in state["module_refs"] else None,
            left_edge,
            right_ref if right_ref in state["module_refs"] else None,
            right_edge,
        )

    def module_ref(value: Any) -> str | None:
        if value is None and len(state["module_refs"]) == 1:
            # Un solo módulo: "divídela"/"pon un travesaño" no necesita
            # direccionar — la única hoja posible es el objetivo.
            return state["module_refs"][0]
        if isinstance(value, str) and value in state["module_refs"]:
            return value
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(module_refs)
        ):
            # Positional addresses name the ORIGINAL summary order; a member
            # removed earlier in the sequence can't be addressed any more.
            ref = module_refs[value]
            return ref if ref in state["module_refs"] else None
        return None

    def coupling_ref(value: Any) -> str | None:
        # String ids resolve against the LIVE joint set — a joint dropped by
        # remove_unit/remove_coupling is gone, not silently re-aimed.
        if isinstance(value, str) and value in state["coupling_refs"]:
            return value
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(coupling_refs)
        ):
            # Positional addresses name the summary order; the ref must still
            # be live, exactly like the module path above.
            ref = coupling_refs[value]
            return ref if ref in state["coupling_refs"] else None
        return None

    def _module_sim(ref: str) -> dict[str, Any] | None:
        return state["sim_modules"].get(ref)

    def _module_bays(ref: str) -> list[dict[str, Any]]:
        module = _module_sim(ref)
        if module is None or not isinstance(module.get("tree"), dict):
            return []
        return sim.bays(module["tree"])

    def bay_ref(mod_ref: str, value: Any) -> str | None:
        """Resolve a bay ref inside a module's LIVE sim tree: real node id,
        composite 'modId/bayId', positional index into the module's current
        bays, or 'added_b{n}' for a bay minted by a previous split_bay."""
        module = _module_sim(mod_ref)
        if module is None or not isinstance(module.get("tree"), dict):
            return None
        bays_now = sim.bays(module["tree"])
        if isinstance(value, str):
            token = value.strip()
            if "/" in token:
                # Composite 'modId/bayId' — el módulo ya viene por el op; la
                # cola se resuelve como id de hoja.
                token = token.rsplit("/", 1)[-1]
            if token.startswith("added_b"):
                match = _ADDED_BAY_RE.match(token)
                index = int(match.group(1)) - 1 if match else -1
                if 0 <= index < len(state["added_bays"]):
                    return state["added_bays"][index]
                return None
            for bay in bays_now:
                if bay.get("id") == token:
                    return str(bay["id"])
            return None
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(bays_now)
        ):
            bay = bays_now[value]
            return str(bay["id"]) if isinstance(bay.get("id"), str) else None
        return None

    def bay_node(mod_ref: str, bay_id: str) -> dict[str, Any] | None:
        module = _module_sim(mod_ref)
        if module is None or not isinstance(module.get("tree"), dict):
            return None
        node = sim.find_in_module(module["tree"], bay_id)
        return node if isinstance(node, dict) and node.get("type") == "BAY" else None

    def divider_ref(mod_ref: str, value: Any) -> str | None:
        """Same rules as bay_ref for split nodes ('added_d{n}' for minted)."""
        module = _module_sim(mod_ref)
        if module is None or not isinstance(module.get("tree"), dict):
            return None
        divisions_now = sim.divisions(module["tree"])
        if isinstance(value, str):
            token = value.strip().rsplit("/", 1)[-1]
            if token.startswith("added_d"):
                match = _ADDED_DIVIDER_RE.match(token)
                index = int(match.group(1)) - 1 if match else -1
                if 0 <= index < len(state["added_dividers"]):
                    return state["added_dividers"][index]
                return None
            for node in divisions_now:
                if node.get("id") == token:
                    return str(node["id"])
            return None
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value < len(divisions_now)
        ):
            node = divisions_now[value]
            return str(node["id"]) if isinstance(node.get("id"), str) else None
        return None

    def _members(module: dict[str, Any]) -> dict[str, Any]:
        return catalog.get("members") or {}

    def _glass_sku(item: dict[str, Any]) -> str | None:
        """set_glass resuelve SKU directo o receta declarada (catalog
        glass_recipes) — el wire siempre lleva el SKU canónico."""
        sku = item.get("sku")
        if isinstance(sku, str) and sku in catalog["glass_skus"]:
            return sku
        recipe = item.get("recipe")
        if isinstance(recipe, str):
            normalized = recipe.strip()
            matches = [
                candidate
                for candidate, spec in catalog.get("glass_recipes", {}).items()
                if spec == normalized
            ]
            if len(matches) == 1:
                return matches[0]
        return None

    declared_openings = catalog.get("opening_keys")

    def _opening_key(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        if value.startswith("DOOR:"):
            return True
        # Sin claves D03 en el catálogo cae al dominio legacy — ROTATE y
        # amigos nunca son una apertura válida.
        return value in (declared_openings if declared_openings is not None else OPENINGS)

    def _opening_set(op_item: dict[str, Any], name: str) -> str | None:
        opening = op_item.get("opening")
        return opening if _opening_key(opening) else None

    def reject(item: Any, reason: str) -> dict[str, Any]:
        return {"op": item.get("op") if isinstance(item, dict) else None, "reason": reason}

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    if not isinstance(ops, list):
        return [], [{"op": None, "reason": "formato_invalido"}]
    for item in ops[:MAX_OPS]:
        if not isinstance(item, dict) or not isinstance(item.get("op"), str):
            rejected.append(reject(item, "formato_invalido"))
            continue
        name = item["op"]
        if name == "set_module_count":
            if not (
                isinstance(item.get("count"), int)
                and not isinstance(item["count"], bool)
                and Decimal(item["count"]) in declared
            ):
                rejected.append(reject(item, "cantidad_no_declarada"))
            elif 1 <= item["count"] <= MAX_MODULE_COUNT:
                accepted.append({"op": name, "count": item["count"]})
                while len(state["module_refs"]) < item["count"]:
                    # The client's addAdjacentUnit appends at the free right
                    # chain end — a graph fact, never the declaration tail
                    # (a stacked member can sit last). Re-walk each round:
                    # the member just added becomes the new end. No free end
                    # → the client stalls, so the sim stops the same way.
                    tail = _chain_end("right")
                    if tail is None:
                        break
                    new_ref = _add_ref("m")
                    module_info[new_ref] = dict(
                        module_info.get(tail, {"shape": "RECT", "frameless": False})
                    )
                    state["sim_modules"][new_ref] = {
                        "tree": sim.clone_tree(
                            state["sim_modules"].get(tail, {}).get("tree")
                        ),
                        "width_mm": state["sim_modules"].get(tail, {}).get("width_mm"),
                        "height_mm": state["sim_modules"].get(tail, {}).get("height_mm"),
                    }
                    state["module_refs"].append(new_ref)
                    state["coupling_refs"].append(
                        _add_coupling([tail, new_ref], ["right", "left"])
                    )
                for dropped in state["module_refs"][item["count"] :]:
                    for c_ref in list(state["coupling_refs"]):
                        info = state["sim_couplings"].get(c_ref)
                        if info is not None and dropped in info["modules"]:
                            state["coupling_refs"].remove(c_ref)
                            _drop_coupling(c_ref)
                    state["used_edges"].pop(dropped, None)
                    state["sim_modules"].pop(dropped, None)
                del state["module_refs"][item["count"] :]
                state["stacked_members"].intersection_update(state["module_refs"])
            else:
                rejected.append(reject(item, "cantidad_invalida"))
        elif name == "add_unit":
            if (
                item.get("side") in ("left", "right")
                and len(state["module_refs"]) < MAX_MODULE_COUNT
            ):
                # The seam joins the free chain end's outer edge to the new
                # member's inner edge — the end is a graph fact (a trailing
                # stacked member is not the chain end), never the list
                # tail. Resolve before inserting so the new member can't
                # nominate itself as the end. No free end → the client is a
                # no-op, so the op must be refused here too.
                end = _chain_end(item["side"])
                if end is None:
                    rejected.append(reject(item, "sin_borde_libre"))
                    continue
                accepted.append({"op": name, "side": item["side"], "ref": _add_ref("m")})
                new_ref = accepted[-1]["ref"]
                # The client's addAdjacentUnit clones the chain-end member —
                # contour/frameless come with it, so a stacked or seam-insert
                # op on the clone must meet the same shape gates here.
                module_info[new_ref] = dict(
                    module_info.get(end, {"shape": "RECT", "frameless": False})
                )
                state["sim_modules"][new_ref] = {
                    "tree": sim.clone_tree(
                        state["sim_modules"].get(end, {}).get("tree")
                    ),
                    "width_mm": state["sim_modules"].get(end, {}).get("width_mm"),
                    "height_mm": state["sim_modules"].get(end, {}).get("height_mm"),
                }
                if item["side"] == "left":
                    state["module_refs"].insert(0, new_ref)
                    if end is not None:
                        state["coupling_refs"].insert(
                            0, _add_coupling([new_ref, end], ["right", "left"])
                        )
                else:
                    state["module_refs"].append(new_ref)
                    if end is not None:
                        state["coupling_refs"].append(
                            _add_coupling([end, new_ref], ["right", "left"])
                        )
            else:
                rejected.append(reject(item, "lado_invalido"))
        elif name == "remove_unit":
            ref = module_ref(item.get("module"))
            if ref is not None and len(state["module_refs"]) > 1:
                accepted.append({"op": name, "module": ref})
                # Incident joints by live sim state — never declaration
                # order: a stacked graph's couplings don't sit beside their
                # module in the coupling list.
                incident: list[tuple[int, str, dict[str, Any]]] = []
                for index, c_ref in enumerate(state["coupling_refs"]):
                    info = state["sim_couplings"].get(c_ref)
                    if info is not None and ref in info["modules"]:
                        incident.append((index, c_ref, info))
                # The client reuses the EARLIER incident joint's id for the
                # relink — keep that ref live so follow-up ops can address
                # the repaired seam; only the later joint is discarded now.
                relink_candidate = len(incident) == 2 and all(
                    info.get("kind") == "INLINE" for _, _, info in incident
                )
                keep_ref = (
                    min(incident, key=lambda entry: entry[0])[1]
                    if relink_candidate
                    else None
                )
                for _, c_ref, info in reversed(incident):
                    # Free the edges the dropped joint claimed on the
                    # SURVIVORS; the removed member's own edges vanish with it.
                    for member, edge in zip(info["modules"], info["edges"]):
                        if member != ref:
                            _free(member, edge)
                        if (
                            info.get("kind") == "STACKED"
                            and edge == "bottom"
                            and member != ref
                            and isinstance(member, str)
                        ):
                            state["stacked_members"].discard(member)
                    if c_ref != keep_ref:
                        state["coupling_refs"].remove(c_ref)
                    state["sim_couplings"].pop(c_ref, None)
                state["module_refs"].pop(state["module_refs"].index(ref))
                state["used_edges"].pop(ref, None)
                state["sim_modules"].pop(ref, None)
                state["stacked_members"].discard(ref)
                # The client's one honest repair: exactly two INLINE
                # incident joints between two distinct rectangular
                # survivors whose exposed edges are free and not already
                # joined — they relink INLINE under the earlier joint's id.
                # Every other topology only removes; inventing a joint
                # fabricates structure.
                if relink_candidate:
                    survivors: list[tuple[str, Any]] = []
                    for _, _, info in incident:
                        if len(info["modules"]) == 2:
                            # The survivor is the OTHER member of the pair.
                            pos = 1 if info["modules"][0] == ref else 0
                            survivors.append(
                                (info["modules"][pos], info["edges"][pos])
                            )
                    joinable = False
                    if len(survivors) == 2:
                        (a_ref, a_edge), (b_ref, b_edge) = survivors
                        joined = any(
                            a_ref in other["modules"] and b_ref in other["modules"]
                            for other in state["sim_couplings"].values()
                        )
                        joinable = (
                            a_ref != b_ref
                            and a_ref in state["module_refs"]
                            and b_ref in state["module_refs"]
                            and not joined
                            and module_info.get(a_ref, {}).get("shape", "RECT")
                            == "RECT"
                            and module_info.get(b_ref, {}).get("shape", "RECT")
                            == "RECT"
                            and not module_info.get(a_ref, {}).get("frameless")
                            and not module_info.get(b_ref, {}).get("frameless")
                            and a_edge not in state["used_edges"].get(a_ref, set())
                            and b_edge not in state["used_edges"].get(b_ref, set())
                        )
                    if joinable and keep_ref is not None:
                        # The surviving joint keeps the earlier ref and the
                        # clients' left→right declaration order.
                        order = {
                            m_ref: index
                            for index, m_ref in enumerate(state["module_refs"])
                        }
                        (join_left, join_left_edge), (join_right, join_right_edge) = sorted(
                            [(a_ref, a_edge), (b_ref, b_edge)],
                            key=lambda entry: order.get(entry[0], -1),
                        )
                        state["sim_couplings"][keep_ref] = {
                            "modules": [join_left, join_right],
                            "edges": [join_left_edge, join_right_edge],
                            "kind": "INLINE",
                        }
                        _claim(join_left, join_left_edge)
                        _claim(join_right, join_right_edge)
                    elif keep_ref is not None and keep_ref in state["coupling_refs"]:
                        # No repair — the kept ref really is dropped.
                        state["coupling_refs"].remove(keep_ref)
            else:
                rejected.append(reject(item, "modulo_invalido"))
        elif name == "duplicate_module":
            ref = module_ref(item.get("module"))
            if ref is None:
                rejected.append(reject(item, "modulo_invalido"))
            elif len(state["module_refs"]) >= MAX_MODULE_COUNT:
                rejected.append(reject(item, "limite_unidades"))
            else:
                claimed = state["used_edges"].get(ref, set())
                side = (
                    "right"
                    if "right" not in claimed
                    else "left"
                    if "left" not in claimed
                    else None
                )
                if side is None:
                    rejected.append(reject(item, "sin_borde_libre"))
                else:
                    new_module = _add_ref("m")
                    module_info[new_module] = dict(module_info.get(ref, {"shape": "RECT"}))
                    state["sim_modules"][new_module] = {
                        "tree": sim.clone_tree(
                            state["sim_modules"].get(ref, {}).get("tree")
                        ),
                        "width_mm": state["sim_modules"].get(ref, {}).get("width_mm"),
                        "height_mm": state["sim_modules"].get(ref, {}).get("height_mm"),
                    }
                    position = state["module_refs"].index(ref)
                    state["module_refs"].insert(
                        position + 1 if side == "right" else position, new_module
                    )
                    state["coupling_refs"].append(
                        _add_coupling([ref, new_module], [side, _OPPOSITE[side]])
                    )
                    accepted.append({"op": name, "module": ref})
        elif name == "insert_module":
            ref = coupling_ref(item.get("coupling"))
            info = _coupling_state(ref) if ref else None
            if ref is None or info is None or info.get("kind") != "INLINE":
                rejected.append(reject(item, "union_invalida"))
            elif len(state["module_refs"]) >= MAX_MODULE_COUNT:
                rejected.append(reject(item, "limite_unidades"))
            else:
                left_ref, left_edge, right_ref, right_edge = _seam_endpoints(ref)
                straight = (
                    left_ref is not None
                    and right_ref is not None
                    and module_info.get(left_ref, {}).get("shape", "RECT") == "RECT"
                    and not module_info.get(left_ref, {}).get("frameless")
                    and module_info.get(right_ref, {}).get("shape", "RECT") == "RECT"
                    and not module_info.get(right_ref, {}).get("frameless")
                )
                if not straight:
                    rejected.append(reject(item, "miembro_no_recto"))
                else:
                    assert left_ref is not None and right_ref is not None
                    new_module = _add_ref("m")
                    # The inserted member inherits its left neighbor's
                    # structure — the client clones it the same way. The
                    # declaration slot is the client contract: insertModuleBetween
                    # splices the member immediately BEFORE the seam's right
                    # endpoint, so a seam spanning non-adjacent declarations
                    # lands here, not after the left one.
                    module_info[new_module] = dict(
                        module_info.get(left_ref, {"shape": "RECT"})
                    )
                    state["sim_modules"][new_module] = {
                        "tree": sim.clone_tree(
                            state["sim_modules"].get(left_ref, {}).get("tree")
                        ),
                        "width_mm": state["sim_modules"].get(left_ref, {}).get("width_mm"),
                        "height_mm": state["sim_modules"].get(left_ref, {}).get("height_mm"),
                    }
                    state["module_refs"].insert(
                        state["module_refs"].index(right_ref), new_module
                    )
                    # The seam's coupling ref survives as the first joint
                    # (left↔new); the second joint mints a fresh ref and
                    # splices in IMMEDIATELY after the seam — the client's
                    # splice at the resolved index, so removals later keep
                    # the same "earlier incident joint" on both sides.
                    seam_left = left_edge or "right"
                    seam_right = right_edge or "left"
                    info["modules"] = [left_ref, new_module]
                    info["edges"] = [seam_left, _OPPOSITE[seam_left]]
                    _claim(new_module, _OPPOSITE[seam_left])
                    state["coupling_refs"].insert(
                        state["coupling_refs"].index(ref) + 1,
                        _add_coupling(
                            [new_module, right_ref],
                            [_OPPOSITE[seam_right], seam_right],
                        ),
                    )
                    accepted.append({"op": name, "coupling": ref})
        elif name == "remove_coupling":
            ref = coupling_ref(item.get("coupling"))
            if ref is None:
                rejected.append(reject(item, "union_invalida"))
            else:
                state["coupling_refs"].remove(ref)
                _drop_coupling(ref)
                accepted.append({"op": name, "coupling": ref})
        elif name == "set_coupling_kind":
            ref = coupling_ref(item.get("coupling"))
            info = _coupling_state(ref) if ref else None
            edges = _coupling_edges(info)
            horizontal = edges is None or all(edge in ("left", "right") for edge in edges)
            allowed = {"INLINE"} if horizontal else {"STACKED", "TEE", "CORNER"}
            if ref is None or info is None or item.get("kind") not in allowed:
                rejected.append(reject(item, "tipo_invalido"))
            else:
                # Kind changes re-derive stacked membership: only a STACKED
                # coupling's "bottom" endpoint is a stacked member.
                for member, edge in zip(info["modules"], info["edges"]):
                    if edge == "bottom" and isinstance(member, str):
                        if item["kind"] == "STACKED":
                            state["stacked_members"].add(member)
                        else:
                            state["stacked_members"].discard(member)
                info["kind"] = item["kind"]
                accepted.append({"op": name, "coupling": ref, "kind": item["kind"]})
        elif name == "add_stacked_unit":
            ref = module_ref(item.get("module"))
            info = module_info.get(ref) if ref else None
            if (
                ref is None
                or info is None
                or info.get("shape") != "RECT"
                or info.get("frameless")
                or "top" in state["used_edges"].get(ref, set())
                or len(state["module_refs"]) >= MAX_MODULE_COUNT
            ):
                rejected.append(reject(item, "modulo_invalido"))
            else:
                # The stacked member is a real module — it joins the ref
                # set so capacity, removals and chain-end picks see it
                # (stacked_members keeps it out of chain-end candidates).
                stacked_ref = _add_ref("m")
                module_info[stacked_ref] = {"shape": "RECT", "frameless": False}
                base_tree = state["sim_modules"].get(ref, {}).get("tree")
                state["sim_modules"][stacked_ref] = {
                    "tree": sim.clone_tree(base_tree),
                    "width_mm": state["sim_modules"].get(ref, {}).get("width_mm"),
                    "height_mm": _number(item.get("height_mm")) or Decimal("600"),
                }
                state["module_refs"].append(stacked_ref)
                state["coupling_refs"].append(
                    _add_coupling([ref, stacked_ref], ["top", "bottom"], kind="STACKED")
                )
                accepted.append({"op": name, "module": ref})
        elif name == "set_module_width":
            ref = module_ref(item.get("module"))
            if _number(item.get("width_mm")) not in declared:
                rejected.append(reject(item, "ancho_no_declarado"))
            elif ref is not None and _in_range(
                item.get("width_mm"), Decimal("150"), Decimal("6000")
            ):
                width = str(_number(item["width_mm"]))
                state["sim_modules"][ref]["width_mm"] = _number(item["width_mm"])
                accepted.append(
                    {
                        "op": name,
                        "module": ref,
                        "width_mm": width,
                    }
                )
            else:
                rejected.append(reject(item, "ancho_invalido"))
        elif name == "set_total_width":
            if _number(item.get("width_mm")) not in declared:
                rejected.append(reject(item, "ancho_no_declarado"))
            elif _in_range(
                item.get("width_mm"),
                Decimal("150") * len(state["module_refs"]),
                Decimal("30000"),
            ):
                # La sim escala cada módulo proporcional (igual que
                # setTotalWidth del cliente).
                widths = [
                    state["sim_modules"].get(r, {}).get("width_mm")
                    for r in state["module_refs"]
                ]
                total = sum((w for w in widths if w), Decimal(0)) or None
                target = _number(item["width_mm"])
                if total and target and total > 0:
                    scale = target / total
                    for r in state["module_refs"]:
                        w = state["sim_modules"].get(r, {}).get("width_mm")
                        if w:
                            state["sim_modules"][r]["width_mm"] = w * scale
                accepted.append({"op": name, "width_mm": str(target)})
            else:
                rejected.append(reject(item, "ancho_invalido"))
        elif name == "set_height":
            if _number(item.get("height_mm")) not in declared:
                rejected.append(reject(item, "alto_no_declarado"))
            elif _in_range(item.get("height_mm"), Decimal("200"), Decimal("4000")):
                for r in state["module_refs"]:
                    if r in state["sim_modules"]:
                        state["sim_modules"][r]["height_mm"] = _number(item["height_mm"])
                accepted.append({"op": name, "height_mm": str(_number(item["height_mm"]))})
            else:
                rejected.append(reject(item, "alto_invalido"))
        elif name == "equalize_widths":
            accepted.append({"op": name})
        elif name == "equalize_angles":
            accepted.append({"op": name})
        elif name == "set_coupling_angle":
            ref = coupling_ref(item.get("coupling"))
            if _number(item.get("angle_deg")) not in declared:
                rejected.append(reject(item, "angulo_no_declarado"))
            elif ref is not None and _in_range(
                item.get("angle_deg"), Decimal("-90"), Decimal("90")
            ):
                accepted.append(
                    {
                        "op": name,
                        "coupling": ref,
                        "angle_deg": str(_number(item["angle_deg"])),
                    }
                )
            else:
                rejected.append(reject(item, "angulo_invalido"))
        elif name == "set_opening":
            ref = module_ref(item.get("module"))
            opening = _opening_set(item, name)
            if ref is None or opening is None:
                rejected.append(reject(item, "apertura_invalida"))
                continue
            if "bay" in item:
                bay = bay_ref(ref, item.get("bay"))
                node = bay_node(ref, bay) if bay else None
                if node is None:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                sim.apply_opening(node, opening)
                accepted.append(
                    {"op": name, "module": ref, "bay": bay, "opening": opening}
                )
            else:
                for node in _module_bays(ref):
                    sim.apply_opening(node, opening)
                accepted.append({"op": name, "module": ref, "opening": opening})
        elif name == "set_glass_thickness":
            ref = module_ref(item.get("module"))
            if _number(item.get("mm")) not in declared:
                rejected.append(reject(item, "espesor_no_declarado"))
                continue
            if not (ref is not None and _number(item.get("mm")) in catalog["thicknesses"]):
                rejected.append(reject(item, "espesor_invalido"))
                continue
            mm = str(_number(item["mm"]))
            if "bay" in item:
                bay = bay_ref(ref, item.get("bay"))
                node = bay_node(ref, bay) if bay else None
                if node is None:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                node["glass_thickness_mm"] = mm
                accepted.append({"op": name, "module": ref, "bay": bay, "mm": mm})
            else:
                for node in _module_bays(ref):
                    node["glass_thickness_mm"] = mm
                accepted.append({"op": name, "module": ref, "mm": mm})
        elif name == "set_glass":
            ref = module_ref(item.get("module"))
            sku = _glass_sku(item)
            if ref is None or sku is None:
                rejected.append(reject(item, "vidrio_invalido"))
                continue
            if "bay" in item:
                bay = bay_ref(ref, item.get("bay"))
                node = bay_node(ref, bay) if bay else None
                if node is None:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                node["glass_article_sku"] = sku
                accepted.append({"op": name, "module": ref, "bay": bay, "sku": sku})
            else:
                for node in _module_bays(ref):
                    node["glass_article_sku"] = sku
                accepted.append({"op": name, "module": ref, "sku": sku})
        elif name == "set_panel":
            ref = module_ref(item.get("module"))
            if not (
                ref is not None
                and (item.get("sku") is None or item["sku"] in catalog["panel_skus"])
            ):
                rejected.append(reject(item, "panel_invalido"))
                continue
            if "bay" in item:
                bay = bay_ref(ref, item.get("bay"))
                node = bay_node(ref, bay) if bay else None
                if node is None:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                node["panel_article_sku"] = item.get("sku")
                accepted.append(
                    {"op": name, "module": ref, "bay": bay, "sku": item.get("sku")}
                )
            else:
                for node in _module_bays(ref):
                    node["panel_article_sku"] = item.get("sku")
                accepted.append({"op": name, "module": ref, "sku": item.get("sku")})
        elif name == "split_bay":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            axis = item.get("axis")
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            if axis not in ("V", "H"):
                rejected.append(reject(item, "eje_invalido"))
                continue
            bays_now = sim.bays(module["tree"])
            if not bays_now:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            bay = (
                bay_ref(ref, item["bay"]) if "bay" in item else bays_now[0].get("id")
            )
            if not isinstance(bay, str) or bay_node(ref, bay) is None:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            mullions = catalog.get("mullions") or {}
            spec = mullions.get(f"SPLIT_{axis}")
            mullion_sku = item.get("mullion_sku")
            if isinstance(mullion_sku, str):
                if spec is not None and mullion_sku != spec["sku"]:
                    rejected.append(reject(item, "poste_invalido"))
                    continue
            elif spec is not None:
                mullion_sku = spec["sku"]
            else:
                rejected.append(reject(item, "poste_invalido"))
                continue
            module_span = (
                module.get("width_mm") if axis == "V" else module.get("height_mm")
            )

            def _region(target_bay: str):
                return sim.region(
                    module["tree"], target_bay, vertical=axis == "V",
                    module_span_mm=module_span, members=_members(module),
                )

            def _mint_split(target_bay: str, offset: Decimal) -> bool:
                """Aplica UN split y registra el resultado. Devuelve False si
                la división fue inválida (la op ya quedó en rejected)."""
                state["added"]["d"] += 1
                state["added"]["b"] += 1
                split_id = f"added_d{state['added']['d']}"
                second_id = f"added_b{state['added']['b']}"
                if (
                    sim.apply_split(
                        module, target_bay,
                        axis=axis, offset_mm=offset, mullion_sku=mullion_sku,
                        split_id=split_id, second_bay_id=second_id,
                    )
                    is None
                ):
                    state["added"]["d"] -= 1
                    state["added"]["b"] -= 1
                    return False
                state["added_dividers"].append(split_id)
                state["added_bays"].append(second_id)
                accepted.append(
                    {
                        "op": name,
                        "module": ref,
                        "bay": target_bay,
                        "axis": axis,
                        "offset_mm": str(offset),
                        "mullion_sku": mullion_sku,
                        # El cliente acuña los ids reales; estas refs sintéticas
                        # sólo sirven para direccionar dentro de la misma secuencia.
                        "new_divider": split_id,
                        "new_bay": second_id,
                    }
                )
                return True

            parts_raw = item.get("parts")
            if parts_raw is not None:
                # División en N partes iguales — "en tres hojas iguales".
                # El N es un número y debe venir declarado por el pedido;
                # los offsets los calcula el motor (nunca el modelo).
                parts = item.get("parts")
                if not isinstance(parts, int) or isinstance(parts, bool):
                    rejected.append(reject(item, "partes_invalidas"))
                    continue
                # El conteo es una decisión semántica, no una medida: exige
                # el número declarado por el pedido, no cualquier citable
                # (un 3 derivado de 6/2 no autoriza "tres hojas").
                declared_counts = (
                    declared_strict if declared_strict is not None else declared
                )
                if Decimal(parts) not in declared_counts:
                    rejected.append(reject(item, "partes_no_declaradas"))
                    continue
                if not 2 <= parts <= 8:
                    rejected.append(reject(item, "partes_invalidas"))
                    continue
                current_bay = bay
                ok = True
                for cut in range(1, parts):
                    reg = _region(current_bay)
                    if reg is None or reg["span_mm"] <= 0:
                        rejected.append(reject(item, "region_invalida"))
                        ok = False
                        break
                    # Cada corte rebanada un ancho = span_restante/(n-k+1)
                    # del frente de la región que sigue creciendo a la derecha.
                    # El split raíz guarda coordenada absoluta de módulo
                    # (centerline); los splits profundos, local de región —
                    # la misma convención del reducer del frontend.
                    local = reg["span_mm"] / Decimal(parts - cut + 1)
                    offset = reg["origin_mm"] + local if reg["is_top"] else local
                    if not _mint_split(current_bay, offset):
                        rejected.append(reject(item, "division_invalida"))
                        ok = False
                        break
                    current_bay = state["added_bays"][-1]
                if not ok:
                    continue
                continue
            reg = _region(bay)
            if reg is None or reg["span_mm"] <= 0:
                rejected.append(reject(item, "region_invalida"))
                continue
            base = module_span if reg["is_top"] else reg["span_mm"]
            direction = item.get("from") or "START"
            raw_offset = _number(item.get("offset_mm"))
            if direction == "CENTER" or raw_offset is None:
                offset = base / 2
            elif raw_offset not in declared:
                rejected.append(reject(item, "offset_no_declarado"))
                continue
            elif direction == "END":
                offset = base - raw_offset
            elif direction == "START":
                offset = raw_offset
            else:
                rejected.append(reject(item, "origen_invalido"))
                continue
            if not (offset is not None and Decimal("0") < offset < base):
                rejected.append(reject(item, "offset_invalido"))
                continue
            if not _mint_split(bay, offset):
                rejected.append(reject(item, "division_invalida"))
                continue
        elif name == "equalize_bays":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
            elif not sim.divisions(module["tree"]):
                rejected.append(reject(item, "sin_divisiones"))
            elif sim.apply_equalize(module, members=_members(module)) is None:
                rejected.append(reject(item, "division_invalida"))
            else:
                accepted.append({"op": name, "module": ref})
        elif name == "set_bay_size":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            bay = bay_ref(ref, item.get("bay"))
            if bay is None:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            target = _number(item.get("mm"))
            if target is None or target not in declared:
                rejected.append(reject(item, "medida_no_declarada"))
                continue
            axis = item.get("axis")
            if axis is not None and axis not in ("V", "H"):
                rejected.append(reject(item, "eje_invalido"))
                continue
            result = sim.resize_bay(
                module, bay, axis=axis, mm=target, members=_members(module)
            )
            if isinstance(result, str):
                rejected.append(reject(item, result))
                continue
            if result is None:
                rejected.append(reject(item, "medida_invalida"))
                continue
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    "bay": bay,
                    "mm": str(target),
                    **({"axis": axis} if axis else {}),
                }
            )
        elif name == "move_divider":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            divider = divider_ref(ref, item.get("divider"))
            if divider is None:
                rejected.append(reject(item, "division_invalida"))
                continue
            offset = _number(item.get("offset_mm"))
            if offset is None or offset not in declared or offset <= 0:
                rejected.append(reject(item, "offset_no_declarado"))
                continue
            if (
                sim.apply_move_divider(module, divider, offset) is None
            ):
                rejected.append(reject(item, "division_invalida"))
                continue
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    "divider": divider,
                    "offset_mm": str(offset),
                }
            )
        elif name == "remove_divider":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            divider = divider_ref(ref, item.get("divider"))
            keep = (
                bay_ref(ref, item["keep_bay"]) if "keep_bay" in item else None
            )
            if divider is None or ("keep_bay" in item and keep is None):
                rejected.append(reject(item, "division_invalida"))
                continue
            if sim.apply_remove_divider(module, divider, keep_bay_id=keep) is None:
                rejected.append(reject(item, "division_anidada"))
                continue
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    "divider": divider,
                    **({"keep_bay": keep} if keep else {}),
                }
            )
        elif name == "remove_bay":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            bay = bay_ref(ref, item.get("bay"))
            if bay is None:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            if sim.apply_remove_bay(module, bay) is None:
                rejected.append(reject(item, "division_anidada"))
                continue
            accepted.append({"op": name, "module": ref, "bay": bay})
        elif name == "flip_handing":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            bays_now = _module_bays(ref)
            targets = (
                [bay_node(ref, bay_ref(ref, item["bay"]))]
                if "bay" in item
                else bays_now
            )
            if any(node is None for node in targets) or not targets:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            flipped_any = False
            for node in targets:
                flipped = sim.flip_bay(node)
                if flipped is not None:
                    node.update(flipped)
                    flipped_any = True
            if not flipped_any:
                rejected.append(reject(item, "apertura_sin_lado"))
                continue
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    **(
                        {"bay": bay_ref(ref, item["bay"])}
                        if "bay" in item
                        else {}
                    ),
                }
            )
        elif name == "set_handle_height":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            target = _number(item.get("mm"))
            if target is None or target not in declared:
                rejected.append(reject(item, "altura_no_declarada"))
                continue
            rule = catalog.get("handle_rule")
            if isinstance(rule, dict):
                lo = _number(rule.get("min_mm"))
                hi = _number(rule.get("max_mm"))
                if lo is not None and hi is not None and not (lo <= target <= hi):
                    rejected.append(reject(item, "altura_fuera_de_rango"))
                    continue
            bays_now = _module_bays(ref)
            if "bay" in item:
                bay = bay_ref(ref, item["bay"])
                node = bay_node(ref, bay) if bay else None
                if node is None:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                node["handle_height_mm"] = str(target)
                accepted.append(
                    {"op": name, "module": ref, "bay": bay, "mm": str(target)}
                )
            else:
                if not bays_now:
                    rejected.append(reject(item, "hoja_invalida"))
                    continue
                for node in bays_now:
                    node["handle_height_mm"] = str(target)
                accepted.append({"op": name, "module": ref, "mm": str(target)})
        elif name == "set_sliding_layout":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            bays_now = _module_bays(ref)
            targets = (
                [bay_node(ref, bay_ref(ref, item["bay"]))]
                if "bay" in item
                else bays_now
            )
            if any(node is None for node in targets) or not targets:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            preset = item.get("preset")
            primary = item.get("primary_index")
            if preset is not None and preset not in (
                "SLIDING_2L", "SLIDING_3L", "SLIDING_4L"
            ):
                rejected.append(reject(item, "layout_invalido"))
                continue
            ok = True
            for node in targets:
                if not sim.is_sliding(node):
                    ok = False
                    break
            if not ok:
                rejected.append(reject(item, "no_corredera"))
                continue
            for node in targets:
                if isinstance(preset, str):
                    sim.apply_opening(node, preset)
                if isinstance(primary, int) and not isinstance(primary, bool):
                    layout = node.get("sliding_layout") or {}
                    panels = sim.sliding_panels(node) or 2
                    if 0 <= primary < panels:
                        layout["primary_index"] = primary
                        node["sliding_layout"] = layout
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    **(
                        {"bay": bay_ref(ref, item["bay"])} if "bay" in item else {}
                    ),
                    **({"preset": preset} if isinstance(preset, str) else {}),
                    **(
                        {"primary_index": primary}
                        if isinstance(primary, int) and not isinstance(primary, bool)
                        else {}
                    ),
                }
            )
        elif name == "set_travel":
            ref = module_ref(item.get("module"))
            module = _module_sim(ref) if ref else None
            slot = item.get("slot")
            kind = item.get("kind")
            if module is None or not isinstance(module.get("tree"), dict):
                rejected.append(reject(item, "modulo_invalido"))
                continue
            bays_now = _module_bays(ref)
            targets = (
                [bay_node(ref, bay_ref(ref, item["bay"]))]
                if "bay" in item
                else bays_now
            )
            if any(node is None for node in targets) or not targets:
                rejected.append(reject(item, "hoja_invalida"))
                continue
            if (
                not isinstance(slot, int)
                or isinstance(slot, bool)
                or kind not in ("MOVING", "FIXED")
            ):
                rejected.append(reject(item, "panel_invalido"))
                continue
            ok = all(
                node is not None
                and sim.is_sliding(node)
                and slot < (sim.sliding_panels(node) or 0)
                for node in targets
            )
            if not ok:
                rejected.append(reject(item, "panel_invalido"))
                continue
            for node in targets:
                layout = dict(node.get("sliding_layout") or {"panels": []})
                panels = layout.get("panels")
                if isinstance(panels, list) and len(panels) > slot:
                    panels = [dict(panel) for panel in panels]
                    panels[slot]["kind"] = kind
                    layout["panels"] = panels
                layout.setdefault("primary_index", 0)
                node["sliding_layout"] = layout
            accepted.append(
                {
                    "op": name,
                    "module": ref,
                    "slot": slot,
                    "kind": kind,
                    **(
                        {"bay": bay_ref(ref, item["bay"])} if "bay" in item else {}
                    ),
                }
            )
        # --- ops de posición: se validan contra el catálogo de la fila ---
        elif name == "set_system":
            system_id = item.get("system_id")
            if isinstance(system_id, str) and system_id in catalog.get("systems", {}):
                accepted.append({"op": name, "scope": "position", "system_id": system_id})
            else:
                rejected.append(reject(item, "sistema_invalido"))
        elif name == "set_finish":
            color = item.get("color")
            if isinstance(color, str) and color in catalog.get("finishes", set()):
                accepted.append({"op": name, "scope": "position", "color": color})
            else:
                rejected.append(reject(item, "acabado_invalido"))
        elif name == "set_location":
            location = item.get("location")
            if isinstance(location, str) and location.strip() and len(location) <= 100:
                accepted.append(
                    {"op": name, "scope": "position", "location": location.strip()}
                )
            else:
                rejected.append(reject(item, "ubicacion_invalida"))
        elif name == "set_quantity":
            count = item.get("count")
            if (
                isinstance(count, int)
                and not isinstance(count, bool)
                and Decimal(count) in declared
                and 1 <= count <= 9999
            ):
                accepted.append({"op": name, "scope": "position", "count": count})
            else:
                rejected.append(reject(item, "cantidad_invalida"))
        elif name in ("add_position", "duplicate_position", "remove_position", "update_position"):
            outcome = _project_op(
                item, declared=declared, opening_keys=catalog.get("opening_keys")
            )
            if outcome is None:
                rejected.append(reject(item, "parametros_invalidos"))
            else:
                accepted.append(outcome)
        else:
            rejected.append(reject(item, "operacion_desconocida"))
    for item in ops[MAX_OPS:]:
        rejected.append(reject(item, "limite_operaciones"))
    return accepted, rejected, _simulation(state)


# Ops de scope "project" — propuestas sobre la lista de posiciones que el
# cliente ejecuta por los endpoints reales de posiciones. No tocan el
# producto simulado; validan forma + grounding (números declarados, ids con
# formato de uuid) y salen etiquetadas para que el cliente las separe de las
# ops de producto.
_PROJECT_OP_NAMES = frozenset(
    ("add_position", "duplicate_position", "remove_position", "update_position")
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _project_op(
    item: dict[str, Any],
    *,
    declared: set[Decimal],
    opening_keys: set[str] | None = None,
) -> dict[str, Any] | None:
    """Valida una op de proyecto. Devuelve el wire op aceptado (con scope)
    o None si algún parámetro no cuadra."""
    name = item.get("op")
    out: dict[str, Any] = {"op": name, "scope": "project"}

    def position_id() -> bool:
        value = item.get("position_id")
        if isinstance(value, str) and _UUID_RE.match(value):
            out["position_id"] = value
            return True
        return False

    def quantity(key: str = "quantity") -> bool:
        value = item.get(key)
        if value is None:
            return True
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and Decimal(value) in declared
            and 1 <= value <= 9999
        ):
            out[key] = value
            return True
        return False

    if name == "add_position":
        width = _number(item.get("width_mm"))
        height = _number(item.get("height_mm"))
        if (
            width is None
            or height is None
            or width not in declared
            or height not in declared
            or not (Decimal("100") <= width <= Decimal("30000"))
            or not (Decimal("100") <= height <= Decimal("30000"))
        ):
            return None
        out["width_mm"] = str(width)
        out["height_mm"] = str(height)
        location = item.get("location")
        if location is not None:
            if not isinstance(location, str) or not location.strip() or len(location) > 100:
                return None
            out["location"] = location.strip()
        opening = item.get("opening")
        if opening is not None:
            if not isinstance(opening, str):
                return None
            if opening_keys and opening not in opening_keys:
                return None
            out["opening"] = opening
        system_id = item.get("system_id")
        if system_id is not None:
            if not isinstance(system_id, str) or not _UUID_RE.match(system_id):
                return None
            out["system_id"] = system_id
        if not quantity():
            return None
        return out
    if name == "duplicate_position":
        if not position_id():
            return None
        count = item.get("count")
        if count is not None:
            if not (
                isinstance(count, int)
                and not isinstance(count, bool)
                and Decimal(count) in declared
                and 1 <= count <= 50
            ):
                return None
            out["count"] = count
        return out
    if name == "remove_position":
        return out if position_id() else None
    if name == "update_position":
        if not position_id():
            return None
        fields = 0
        location = item.get("location")
        if location is not None:
            if not isinstance(location, str) or not location.strip() or len(location) > 100:
                return None
            out["location"] = location.strip()
            fields += 1
        if quantity():
            if "quantity" in out:
                fields += 1
        elif item.get("quantity") is not None:
            return None
        system_id = item.get("system_id")
        if system_id is not None:
            if not isinstance(system_id, str) or not _UUID_RE.match(system_id):
                return None
            out["system_id"] = system_id
            fields += 1
        finish = item.get("finish")
        if finish is not None:
            if not isinstance(finish, str) or not finish.strip() or len(finish) > 50:
                return None
            out["finish"] = finish.strip()
            fields += 1
        return out if fields else None
    return None


def _validate_project_ops(
    ops: Any, *, declared: set[Decimal], opening_keys: set[str] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Valida ops cuando no hay producto (surface=project u otras): sólo las
    de scope project pasan; el resto se rechaza como product_absent — el
    paso "ops" con posición sigue exigiendo el producto vivo."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    items = ops if isinstance(ops, list) else []
    for item in items[:MAX_OPS]:
        if not isinstance(item, dict):
            continue
        name = item.get("op")
        if name in _PROJECT_OP_NAMES:
            outcome = _project_op(item, declared=declared, opening_keys=opening_keys)
            if outcome is None:
                rejected.append({"op": name, "reason": "parametros_invalidos"})
            else:
                accepted.append(outcome)
        else:
            rejected.append({"op": name, "reason": "product_absent"})
    for item in items[MAX_OPS:]:
        rejected.append({"op": item.get("op"), "reason": "limite_operaciones"})
    return accepted, rejected


def _simulation(state: dict[str, Any]) -> dict[str, Any]:
    """La proyección estructural post-ops — la vista previa de "Aplicar"
    (IA2 §4): módulos con medidas simuladas, hojas con su apertura y
    divisiones con su offset, uniones con su tipo. El cliente la muestra
    antes de ejecutar; la aplicación real corre las mismas ops sobre el
    producto — nunca una copia serializada de este sim."""
    modules: list[dict[str, Any]] = []
    for ref in state["module_refs"]:
        module = state["sim_modules"].get(ref) or {}
        tree = module.get("tree")
        modules.append(
            {
                "ref": ref,
                "width_mm": str(module["width_mm"]) if module.get("width_mm") else None,
                "height_mm": str(module["height_mm"]) if module.get("height_mm") else None,
                "bays": (
                    [_bay_summary(node) for node in sim.bays(tree)]
                    if isinstance(tree, dict)
                    else []
                ),
                "splits": (
                    [
                        {
                            "ref": node.get("id"),
                            "type": node.get("type"),
                            "offset_mm": node.get("split_offset_mm"),
                            "mullion_profile_sku": node.get("mullion_profile_sku"),
                        }
                        for node in sim.divisions(tree)
                    ]
                    if isinstance(tree, dict)
                    else []
                ),
            }
        )
    return {
        "modules": modules,
        "couplings": [
            {"ref": ref, "kind": info.get("kind"), "modules": info.get("modules")}
            for ref, info in state["sim_couplings"].items()
        ],
    }


def _model_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """La vista del producto que ve el modelo — refs, medidas, hojas y
    divisiones, sin el árbol crudo (demasiado verboso para el payload)."""
    return {
        "modules": [
            {key: value for key, value in module.items() if key != "tree"}
            for module in summary["modules"]
        ],
        "couplings": summary["couplings"],
    }


def _catalog_payload(catalog: dict[str, Any]) -> dict[str, Any]:
    """La vista del catálogo que ve el modelo — aperturas con nombre,
    postes por eje con su cara (para offset START/END), series elegibles."""
    return {
        "glass_skus": sorted(catalog.get("glass_skus") or []),
        "glass_recipes": {
            sku: spec
            for sku, spec in sorted((catalog.get("glass_recipes") or {}).items())
        },
        "panel_skus": sorted(catalog.get("panel_skus") or []),
        "glazing_thicknesses": [
            str(thickness)
            for thickness in sorted(catalog.get("thicknesses") or [])
        ],
        "openings": catalog.get("openings") or {},
        "mullions": {
            axis: {"sku": spec["sku"], "face_mm": str(spec["face_mm"])}
            for axis, spec in sorted((catalog.get("mullions") or {}).items())
        },
        "finishes": sorted(catalog.get("finishes") or []),
        "systems": [
            {"id": system_id, **info}
            for system_id, info in sorted((catalog.get("systems") or {}).items())
        ],
        "handle_rule": catalog.get("handle_rule"),
    }


def _clarify(document: dict[str, Any]) -> dict[str, Any] | None:
    """La aclaración tipada del documento (IA2 §3): una sola pregunta con
    opciones reales para que la UI las muestre como chips. Inválida = null
    (la respuesta cae a notes, como antes)."""
    raw = document.get("clarify")
    if not isinstance(raw, dict):
        return None
    question = raw.get("question")
    if not isinstance(question, str) or not question.strip():
        return None
    options: list[dict[str, str]] = []
    for option in (raw.get("options") or [])[:MAX_CLARIFY_OPTIONS]:
        if isinstance(option, str) and option.strip():
            options.append({"value": option.strip(), "label": option.strip()})
        elif (
            isinstance(option, dict)
            and isinstance(option.get("value"), str)
            and option["value"].strip()
        ):
            options.append(
                {
                    "value": option["value"].strip(),
                    "label": str(option.get("label") or option["value"]).strip(),
                }
            )
    return {"question": question.strip(), "options": options}


def assist(
    *,
    org_id: UUID,
    user_id: UUID,
    position: dict[str, Any],
    product: Any,
    prompt: str,
    operation_key: str,
    system_id: UUID,
) -> dict[str, Any]:
    summary = _summary(
        product,
        width_mm=position.get("width_mm"),
        height_mm=position.get("height_mm"),
    )
    if summary is None:
        raise contract_error(
            400,
            "design_assist_product_invalid",
            "El producto del asistente no tiene una estructura válida.",
        )
    catalog = _catalog(system_id, org_id)
    envelope = gateway.invoke(
        org_id=org_id,
        user_id=user_id,
        capability=CAPABILITY,
        operation_key=operation_key,
        tool_name="design_assist",
        # Transport controls ride in provider_options — they are server-side
        # config, not client input, so they never touch the audited payload or
        # its replay hash (a prompt edit must not break idempotent retries).
        provider_options={
            "system": design_assist_system(),
            "json_output": True,
        },
        input_payload={
            "prompt": prompt,
            "position_id": str(position["id"]),
            "system_id": str(system_id),
            "product": _model_summary(summary),
            "ops_contract": ops_contract(),
            "catalog": _catalog_payload(catalog),
        },
    )
    try:
        document = json.loads(envelope["output"])
    except (json.JSONDecodeError, TypeError):
        raise contract_error(
            502,
            "design_assist_bad_output",
            "El asistente devolvió una respuesta inválida.",
        ) from None
    if not isinstance(document, dict):
        raise contract_error(
            502,
            "design_assist_bad_output",
            "El asistente devolvió una respuesta inválida.",
        )
    citable = _citable_values(
        _declared_values(prompt), _context_numbers(summary, catalog)
    )
    ops, rejected, simulation = _validate_ops(
        document.get("ops"),
        summary,
        catalog,
        citable,
        declared_strict=_declared_values(prompt),
    )
    return {
        "audit_id": envelope["audit_id"],
        "model": envelope["model"],
        "credits_debited": envelope["credits_debited"],
        "ops": ops,
        "rejected": rejected,
        "notes": document.get("notes") if isinstance(document.get("notes"), str) else None,
        "clarify": _clarify(document),
        "simulation": simulation,
    }
