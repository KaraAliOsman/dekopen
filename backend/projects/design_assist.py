"""Design assist: natural-language intent → validated typed product ops.

The provider never touches the product — it proposes index-based operations;
this service validates every one against the actual assembly (index bounds,
enum and range checks) before the response exists. Rejected ops are reported,
never silently dropped: low-confidence intent must not mutate a position."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from ai_gateway import service as gateway
from authentication.errors import contract_error
from engine_api.repository import SystemParamsRepository
from pricing.repository import rows

CAPABILITY = "design_assist"

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

# The ops contract the provider must emit — sent as the system prompt so any
# OpenAI-compatible model produces exactly this document shape. Every op the
# model returns is validated server-side against the live product before it
# reaches the client, so the prompt constrains intent, never trust.
DESIGN_ASSIST_SYSTEM = """Eres el asistente de diseño de DEKOPEN, un editor profesional de ventanas y puertas de aluminio/PVC.

Recibes un JSON con:
- "prompt": la intención del usuario en lenguaje natural (español chileno).
- "product": el conjunto actual — "modules" (unidades) y "couplings" (uniones entre unidades), índices 0-based.
- "ops_contract": la lista de operaciones permitidas.
- "catalog": los SKU y espesores que existen en el catálogo del cliente.

Respondes SOLO un JSON: {"ops": [...], "notes": "resumen breve en español"}.

Operaciones:
- set_module_count {count}: redefine la cantidad de unidades (reparte el ancho).
- add_unit {side}: agrega una unidad, side "left"|"right".
- remove_unit {module}: elimina la unidad en ese índice.
- set_module_width {module, width_mm}: ancho de una unidad en mm.
- set_total_width {width_mm}: ancho total, reparte proporcional.
- set_height {height_mm}: alto de todas las unidades.
- equalize_widths: anchos iguales.
- equalize_angles: ángulos iguales entre uniones.
- set_coupling_angle {coupling, angle_deg}: ángulo de una unión (0 = recto).
- set_opening {module, opening}: apertura — FIXED, TURN_LEFT, TURN_RIGHT, TILT_TURN_LEFT, TILT_TURN_RIGHT, SLIDING_2L, AWNING, DOOR_ENTRY.
- set_glass {module, sku}: vidrio del catálogo.
- set_glass_thickness {module, mm}: espesor del catálogo.
- set_panel {module, sku|null}: panel del catálogo, null lo quita.
- duplicate_module {module}: duplica una unidad sobre su borde libre (derecho o izquierdo) unida INLINE.
- insert_module {coupling}: inserta una unidad dentro de una unión INLINE — la divide en dos uniones.
- remove_coupling {coupling}: desconecta una unión — las unidades quedan pero separadas.
- set_coupling_kind {coupling, kind}: tipo de unión — INLINE solo en bordes laterales (left/right); STACKED|TEE|CORNER solo en bordes top/bottom.
- add_stacked_unit {module}: agrega una unidad apilada encima (fijo superior / transom) unida STACKED por el borde top.

Reglas:
- Solo ops de ops_contract; solo SKU y espesores del catalog; nada de valores inventados.
- Direcciona cada módulo y unión por su "ref" (id estable del dominio), nunca por posición: el grafo muestra qué borde de qué módulo une cada unión ("modules": [refA, refB], "edges"). Para un módulo aún inexistente creado por add_unit en esta misma secuencia usa la ref "added_m1", "added_m2"... (y "added_c1"... para uniones nuevas).
- Las medidas numéricas (count, width_mm, height_mm, angle_deg, mm) solo pueden citar números que el usuario escribió en "prompt"; si el usuario no declaró una medida, no la inventes — explícalo en "notes".
- Si la intención es ambigua, propón menos ops y explícalo en "notes"; nunca adivines medidas que el usuario no pidió.
- Sin texto fuera del JSON."""


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


def _summary(product: Any) -> dict[str, Any] | None:
    """The client-submitted product surface — the same modules and couplings
    the returned ops will be applied against, so bounds are derived here and
    can never drift against a stale persisted copy. Ops address entities by
    their stable `ref` (the client's own id), not by position: removing a
    module mid-sequence keeps the survivors' refs honest, and the coupling
    endpoints expose the assembly graph — which module edge meets which —
    rather than a bare index into a list."""
    if not isinstance(product, dict):
        return None
    modules_raw = product.get("modules")
    if not isinstance(modules_raw, list) or not 1 <= len(modules_raw) <= MAX_MODULE_COUNT:
        return None
    couplings_raw = product.get("couplings") or []
    if not isinstance(couplings_raw, list) or len(couplings_raw) > MAX_MODULE_COUNT:
        return None
    module_refs = [_ref(module, "m", index) for index, module in enumerate(modules_raw)]
    ref_by_id = {
        str(module["id"]).strip(): ref
        for module, ref in zip(modules_raw, module_refs)
        if isinstance(module, dict) and isinstance(module.get("id"), str) and module["id"].strip()
    }
    return {
        "modules": [
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
            }
            for index, (ref, module) in enumerate(zip(module_refs, modules_raw))
        ],
        "couplings": [
            {
                "ref": _ref(coupling, "c", index),
                "index": index,
                "angle_deg": coupling.get("angle_deg") if isinstance(coupling, dict) else None,
                "kind": (coupling.get("kind") or "INLINE") if isinstance(coupling, dict) else None,
                # Graph endpoints as module refs — 'c2 joins m1.right ↔ m2.left'
                # reads structurally; an absent pair is the legacy chain i↔i+1.
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
    catalog identifier, never free text, so proposed glass, panels and
    thicknesses must resolve against the same options the estimator sees.
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


def _validate_ops(
    ops: Any, summary: dict[str, Any], catalog: dict[str, Any], declared: set[Decimal]
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
    state: dict[str, Any] = {
        # Copied: structural ops mutate these lists while positional
        # addresses resolve against the ORIGINAL `module_refs`/`coupling_refs`
        # — sharing the object would corrupt the positional map.
        "module_refs": list(module_refs),
        "coupling_refs": list(coupling_refs),
        "used_edges": used_edges,
        "stacked_members": stacked_members,
        "sim_couplings": sim_couplings,
        "added": {"m": 0, "c": 0},
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
                accepted.append(
                    {
                        "op": name,
                        "module": ref,
                        "width_mm": str(_number(item["width_mm"])),
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
                accepted.append({"op": name, "width_mm": str(_number(item["width_mm"]))})
            else:
                rejected.append(reject(item, "ancho_invalido"))
        elif name == "set_height":
            if _number(item.get("height_mm")) not in declared:
                rejected.append(reject(item, "alto_no_declarado"))
            elif _in_range(item.get("height_mm"), Decimal("200"), Decimal("4000")):
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
            if ref is not None and item.get("opening") in OPENINGS:
                accepted.append(
                    {
                        "op": name,
                        "module": ref,
                        "opening": item["opening"],
                    }
                )
            else:
                rejected.append(reject(item, "apertura_invalida"))
        elif name == "set_glass_thickness":
            ref = module_ref(item.get("module"))
            if _number(item.get("mm")) not in declared:
                rejected.append(reject(item, "espesor_no_declarado"))
            elif ref is not None and _number(item.get("mm")) in catalog["thicknesses"]:
                accepted.append(
                    {
                        "op": name,
                        "module": ref,
                        "mm": str(_number(item["mm"])),
                    }
                )
            else:
                rejected.append(reject(item, "espesor_invalido"))
        elif name == "set_glass":
            ref = module_ref(item.get("module"))
            if ref is not None and item.get("sku") in catalog["glass_skus"]:
                accepted.append({"op": name, "module": ref, "sku": item["sku"]})
            else:
                rejected.append(reject(item, "vidrio_invalido"))
        elif name == "set_panel":
            ref = module_ref(item.get("module"))
            if ref is not None and (
                item.get("sku") is None or item["sku"] in catalog["panel_skus"]
            ):
                accepted.append({"op": name, "module": ref, "sku": item.get("sku")})
            else:
                rejected.append(reject(item, "panel_invalido"))
        else:
            rejected.append(reject(item, "operacion_desconocida"))
    for item in ops[MAX_OPS:]:
        rejected.append(reject(item, "limite_operaciones"))
    return accepted, rejected


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
    summary = _summary(product)
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
            "system": DESIGN_ASSIST_SYSTEM,
            "json_output": True,
        },
        input_payload={
            "prompt": prompt,
            "position_id": str(position["id"]),
            "system_id": str(system_id),
            "product": summary,
            "ops_contract": sorted(
                {
                    "add_stacked_unit",
                    "add_unit",
                    "duplicate_module",
                    "equalize_angles",
                    "equalize_widths",
                    "insert_module",
                    "remove_coupling",
                    "remove_unit",
                    "set_coupling_angle",
                    "set_coupling_kind",
                    "set_glass",
                    "set_glass_thickness",
                    "set_height",
                    "set_module_count",
                    "set_module_width",
                    "set_opening",
                    "set_panel",
                    "set_total_width",
                }
            ),
            "catalog": {
                "glass_skus": sorted(catalog["glass_skus"]),
                "panel_skus": sorted(catalog["panel_skus"]),
                "glazing_thicknesses": [
                    str(thickness) for thickness in sorted(catalog["thicknesses"])
                ],
            },
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
    ops, rejected = _validate_ops(document.get("ops"), summary, catalog, _declared_values(prompt))
    return {
        "audit_id": envelope["audit_id"],
        "model": envelope["model"],
        "credits_debited": envelope["credits_debited"],
        "ops": ops,
        "rejected": rejected,
        "notes": document.get("notes") if isinstance(document.get("notes"), str) else None,
    }
