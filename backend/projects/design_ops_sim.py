"""Simulación de árbol paramétrico para el validador de ops (IA2).

El aplicador REAL es el frontend (`intentEditing.ts` / `productEditing.ts`) —
este módulo replica sus semánticas en Python solo para que el validador
resuelva referencias de hoja/división, simule el efecto de las ops
estructurales y detecte propuestas imposibles ANTES de que lleguen al
cliente. Si una semántica diverge, la fuente es el frontend: cualquier fix
allí exige el mismo cambio aquí.

Convenciones de coordenadas (engine/geometry.py + intentEditing.ts):

- ``split_offset_mm`` del split raíz del módulo se mide desde el borde del
  módulo (origen local 0). Splits anidados se miden desde el origen de la
  región de su bahía padre.
- Para SPLIT_V el eje es horizontal (ancho); SPLIT_H el eje es vertical
  (alto), medido desde el borde superior.
- La región de una bahía descuenta las caras del marco y las medias caras
  de los postes ancestrales — `region()` es el port de
  `baySpanOnAxis` de productEditing.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

SPLIT_TYPES = {"SPLIT_V", "SPLIT_H"}

# Espejo de handedness — el port de MIRRORED_OPENING + mirrorOpeningSpec +
# mirrorLeaves de intentEditing.ts.
_MIRRORED_OPENING = {
    "TURN_LEFT": "TURN_RIGHT",
    "TURN_RIGHT": "TURN_LEFT",
    "TILT_TURN_LEFT": "TILT_TURN_RIGHT",
    "TILT_TURN_RIGHT": "TILT_TURN_LEFT",
}
_MIRROR_SIDE = {"LEFT": "RIGHT", "RIGHT": "LEFT"}

# Aperturas que identifican puerta — en esas hojas split_bay se rehúsa
# (igual que splitModuleBay rechaza DOOR_ENTRY / DOOR:* specs).
_DOOR_KEYS = frozenset({"DOOR_ENTRY"})

# Aperturas correderas para set_travel / set_sliding_layout.
_SLIDING_KEYS = frozenset({"SLIDING", "SLIDING_2L", "SLIDING_3L", "SLIDING_4L"})

_SLIDING_PANEL_COUNTS = {"SLIDING_2L": 2, "SLIDING_3L": 3, "SLIDING_4L": 4}


def _num(value: Any) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


# ---------------------------------------------------------------------------
# Navegación del árbol simulado (dicts puros — la forma wire del IntentNode)
# ---------------------------------------------------------------------------


def clone_tree(tree: dict[str, Any] | None) -> dict[str, Any]:
    return deepcopy(tree) if isinstance(tree, dict) else {}


def unwrap(tree: dict[str, Any]) -> dict[str, Any]:
    """La envoltura ROOT es transparente (misma regla que el motor y el
    frontend): las ops actúan sobre el nodo hijo real."""
    if tree.get("type") == "ROOT":
        children = tree.get("children") or []
        if len(children) == 1 and isinstance(children[0], dict):
            return children[0]
    return tree


def walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            nodes.extend(walk(child))
    return nodes


def bays(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Hojas BAY del árbol en orden de declaración (izquierda→derecha /
    arriba→abajo siguiendo el orden de children de cada split)."""
    return [node for node in walk(unwrap(tree)) if node.get("type") == "BAY"]


def divisions(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [node for node in walk(unwrap(tree)) if node.get("type") in SPLIT_TYPES]


def find(tree: dict[str, Any], node_id: Any) -> dict[str, Any] | None:
    if not isinstance(node_id, str):
        return None
    for node in walk(tree):
        if node.get("id") == node_id:
            return node
    return None


def find_in_module(tree: dict[str, Any], node_id: Any) -> dict[str, Any] | None:
    return find(unwrap(tree), node_id)


def _path_to(node: dict[str, Any], node_id: str) -> list[tuple[dict[str, Any], int]] | None:
    """Camino raíz→nodo como (padre, índice del hijo) — port de pathTo de
    baySpanOnAxis para la geometría de regiones."""
    if node.get("id") == node_id:
        return []
    for index, child in enumerate(node.get("children") or []):
        if isinstance(child, dict):
            rest = _path_to(child, node_id)
            if rest is not None:
                return [(node, index)] + rest
    return None


def parent_split(tree: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    path = _path_to(unwrap(tree), node_id)
    if not path:
        return None
    parent, _index = path[-1]
    return parent if parent.get("type") in SPLIT_TYPES else None


def replace(tree: dict[str, Any], node_id: str, new_node: dict[str, Any]) -> dict[str, Any]:
    """Sustituye un nodo in place (el árbol simulado es mutable — cada op lo
    clona antes de mutar). Devuelve la raíz desempaquetada."""
    if tree.get("id") == node_id:
        # Raíz misma — el caller la reemplaza en el contenedor.
        raise ValueError("root_replace")
    children = tree.get("children") or []
    for index, child in enumerate(children):
        if not isinstance(child, dict):
            continue
        if child.get("id") == node_id:
            children[index] = new_node
            return tree
        try:
            replace(child, node_id, new_node)
            return tree
        except ValueError:
            continue
    raise ValueError("node_missing")


# ---------------------------------------------------------------------------
# Geometría de regiones — port de baySpanOnAxis (productEditing.ts)
# ---------------------------------------------------------------------------


def region(
    tree: dict[str, Any],
    bay_id: str,
    *,
    vertical: bool,
    module_span_mm: Any,
    members: dict[str, Any],
) -> dict[str, Any] | None:
    """La extensión del vano de una bahía sobre un eje, igual que la calcula
    `baySpanOnAxis` en el frontend: la raíz llena el hueco del marco y cada
    split ancestro del mismo eje descuenta media cara de poste a cada lado.

    Devuelve {span_mm, origin_mm, is_top} en las coordenadas del split más
    externo del eje (módulo si la bahía es la raíz): ``origin_mm`` es el
    borde inicial de la región en esas coordenadas, para que el offset
    absoluto se derive con ``origin + local``.
    """
    root = unwrap(tree)
    path = _path_to(root, bay_id)
    if path is None:
        return None
    span = _num(module_span_mm)
    if span is None or span <= 0:
        return None
    frame_face = _num(members.get("frame_mm")) or Decimal("0")
    axis_mullion = _num(
        members.get("mullion_v_mm" if vertical else "mullion_h_mm")
    )
    mullion_half = None if axis_mullion is None else axis_mullion / 2
    lo = frame_face
    hi = span - frame_face if span - frame_face > frame_face else frame_face
    for node, index in path:
        if node.get("type") not in SPLIT_TYPES:
            continue
        if (node["type"] == "SPLIT_V") != vertical:
            continue
        offset = _num(node.get("split_offset_mm"))
        if offset is None or offset <= 0:
            continue
        if mullion_half is None:
            return None
        centerline = offset if node is root else lo + offset
        if index == 0:
            hi = min(hi, centerline - mullion_half)
        else:
            lo = max(lo, centerline + mullion_half)
    return {
        "span_mm": max(hi - lo, Decimal("0")),
        "origin_mm": lo,
        "is_top": not path,
    }


# ---------------------------------------------------------------------------
# Espejo de aperturas — port de mirrorOpeningSpec/mirrorLeaves
# ---------------------------------------------------------------------------


def _mirror_spec(spec: Any) -> Any:
    if not isinstance(spec, dict):
        return spec
    mirrored = dict(spec)
    hinge = mirrored.get("hinge_side")
    if isinstance(hinge, str) and hinge in _MIRROR_SIDE:
        mirrored["hinge_side"] = _MIRROR_SIDE[hinge]
    return mirrored


_FLIP_TRAVEL = {"LEFT": "RIGHT", "RIGHT": "LEFT"}

# Presets corredera del engine (geometry._SLIDING_PRESETS) en forma de
# dict: cada hoja móvil declara su travel desde P05 — mitad izquierda va
# a la derecha, mitad derecha a la izquierda.
_SLIDING_PRESET_LAYOUTS: dict[str, dict[str, Any]] = {
    "SLIDING_2L": {
        "tracks": 2,
        "panels": [
            {"slot": "P1", "kind": "MOVING", "track": 0, "travel": "RIGHT"},
            {"slot": "P2", "kind": "MOVING", "track": 1, "travel": "LEFT"},
        ],
    },
    "SLIDING_3L": {
        "tracks": 2,
        "panels": [
            {"slot": "P1", "kind": "MOVING", "track": 0, "travel": "RIGHT"},
            {"slot": "P2", "kind": "MOVING", "track": 1, "travel": "RIGHT"},
            {"slot": "P3", "kind": "MOVING", "track": 0, "travel": "LEFT"},
        ],
    },
    "SLIDING_4L": {
        "tracks": 2,
        "panels": [
            {"slot": "P1", "kind": "MOVING", "track": 0, "travel": "RIGHT"},
            {"slot": "P2", "kind": "MOVING", "track": 1, "travel": "RIGHT"},
            {"slot": "P3", "kind": "MOVING", "track": 0, "travel": "LEFT"},
            {"slot": "P4", "kind": "MOVING", "track": 1, "travel": "LEFT"},
        ],
    },
}


def _mirror_layout(layout: dict[str, Any]) -> dict[str, Any]:
    """Espejo de una corredera: los extremos se intercambian (los paneles
    recorren de derecha a izquierda) y cada travel declarado invierte su
    sentido; el riel no cambia (la vista exterior/interior es la misma)."""
    mirrored = deepcopy(layout)
    panels = mirrored.get("panels")
    if isinstance(panels, list) and panels:
        mirrored["panels"] = [
            {
                **panel,
                "travel": _FLIP_TRAVEL.get(panel.get("travel"), panel.get("travel")),
            }
            if isinstance(panel, dict)
            else panel
            for panel in reversed(panels)
        ]
        primary = layout.get("primary_index")
        if isinstance(primary, int) and not isinstance(primary, bool):
            mirrored["primary_index"] = len(panels) - 1 - primary
    return mirrored


def mirror_bay(node: dict[str, Any]) -> dict[str, Any]:
    """La segunda hoja de un split vertical: bisagras y hojas espejadas para
    que las manillas se junten en el poste (misma regla del frontend)."""
    mirrored = deepcopy(node)
    opening_type = mirrored.get("opening_type")
    if isinstance(opening_type, str):
        mirrored["opening_type"] = _MIRRORED_OPENING.get(opening_type, opening_type)
    if isinstance(mirrored.get("opening"), dict):
        mirrored["opening"] = _mirror_spec(mirrored["opening"])
    if isinstance(mirrored.get("sliding_layout"), dict):
        mirrored["sliding_layout"] = _mirror_layout(mirrored["sliding_layout"])
    if isinstance(mirrored.get("leaves"), list):
        def _slot(leaf: dict[str, Any]) -> dict[str, Any]:
            slot = leaf.get("slot")
            remapped = {"L1": "L2", "L2": "L1"}.get(slot, slot)
            return {
                **leaf,
                "slot": remapped,
                "opening": _mirror_spec(leaf.get("opening")),
            }
        mirrored["leaves"] = sorted(
            (_slot(leaf) for leaf in mirrored["leaves"] if isinstance(leaf, dict)),
            key=lambda leaf: str(leaf.get("slot")),
        )
    handedness = mirrored.get("door_handedness")
    if isinstance(handedness, str) and handedness in _MIRROR_SIDE:
        mirrored["door_handedness"] = _MIRROR_SIDE[handedness]
    return mirrored


def flip_bay(node: dict[str, Any]) -> dict[str, Any] | None:
    """Espejo explícito de una hoja (flip_handing). None cuando la hoja no
    tiene handedness que espejar (fija/proyectante)."""
    flipped = deepcopy(node)
    changed = False
    opening_type = flipped.get("opening_type")
    if isinstance(opening_type, str) and opening_type in _MIRRORED_OPENING:
        flipped["opening_type"] = _MIRRORED_OPENING[opening_type]
        changed = True
    elif isinstance(opening_type, str) and opening_type in _SLIDING_KEYS:
        # Corredera: la hoja primaria invierte (primer panel ↔ último) y
        # cada travel declarado invierte su sentido — mismo espejo que
        # flipBay del frontend.
        layout = flipped.get("sliding_layout")
        if isinstance(layout, dict) and isinstance(layout.get("panels"), list):
            flipped["sliding_layout"] = _mirror_layout(layout)
            changed = True
        else:
            preset = _SLIDING_PRESET_LAYOUTS.get(opening_type)
            if preset is not None:
                # Sin layout explícito el espejo materializa el preset
                # espejado (primary_index 0 → último slot).
                mirrored = _mirror_layout(preset)
                if "primary_index" not in mirrored:
                    mirrored["primary_index"] = len(mirrored["panels"]) - 1
                flipped["sliding_layout"] = mirrored
                changed = True
    if isinstance(flipped.get("opening"), dict):
        spec = flipped["opening"]
        mirrored = _mirror_spec(spec)
        if mirrored != spec:
            flipped["opening"] = mirrored
            changed = True
    if isinstance(flipped.get("leaves"), list):
        leaves = flipped["leaves"]
        mirrored = mirror_bay({"leaves": leaves})["leaves"]
        if mirrored != leaves:
            flipped["leaves"] = mirrored
            changed = True
    handedness = flipped.get("door_handedness")
    if isinstance(handedness, str) and handedness in _MIRROR_SIDE:
        flipped["door_handedness"] = _MIRROR_SIDE[handedness]
        changed = True
    return flipped if changed else None


def opening_of(node: dict[str, Any]) -> str:
    """La apertura efectiva del nodo: opening_type, o la key del spec cuando
    la bahía declara apertura por spec (D03). 'DOOR:*' y '*:LEFT|RIGHT' de
    specs se representan por su primer token significativo."""
    opening_type = node.get("opening_type")
    if isinstance(opening_type, str) and opening_type:
        return opening_type
    spec = node.get("opening")
    if isinstance(spec, dict) and isinstance(spec.get("key"), str):
        return spec["key"]
    leaves = node.get("leaves")
    if isinstance(leaves, list) and leaves:
        keys = []
        for leaf in leaves:
            if isinstance(leaf, dict):
                sub = leaf.get("opening")
                keys.append(sub.get("key") if isinstance(sub, dict) else None)
        if all(isinstance(k, str) for k in keys):
            body = "|".join(keys)
            unit = node.get("unit_kind")
            return f"DOOR:{body}" if unit == "DOOR" else body
    return "FIXED"


def is_door(node: dict[str, Any]) -> bool:
    key = opening_of(node)
    return key in _DOOR_KEYS or key.startswith("DOOR:")


def is_sliding(node: dict[str, Any]) -> bool:
    return opening_of(node) in _SLIDING_KEYS


def sliding_panels(node: dict[str, Any]) -> int | None:
    """Número de paneles declarado por la apertura corredera."""
    layout = node.get("sliding_layout")
    if isinstance(layout, dict):
        for key in ("panels", "tracks"):
            if isinstance(layout.get(key), list):
                return len(layout[key])
    return _SLIDING_PANEL_COUNTS.get(opening_of(node))


# ---------------------------------------------------------------------------
# Mutaciones — ports de intentEditing/productEditing sobre el árbol simulado
# ---------------------------------------------------------------------------


def apply_split(
    module: dict[str, Any],
    bay_id: str,
    *,
    axis: str,
    offset_mm: Any,
    mullion_sku: str,
    split_id: str,
    second_bay_id: str,
) -> dict[str, Any] | None:
    """Port de splitBay: la bahía queda como primer hijo (misma id y spec);
    la segunda es su espejo vertical. Devuelve el árbol mutado o None."""
    tree = clone_tree(module.get("tree"))
    if not isinstance(tree, dict) or not tree:
        tree = {"id": "root", "type": "BAY"}
    root = unwrap(tree)
    bay = find(root, bay_id)
    if bay is None or is_door(bay):
        return None
    offset = _num(offset_mm)
    if offset is None or offset <= 0 or axis not in ("V", "H"):
        return None
    if find(root, split_id) is not None or find(root, second_bay_id) is not None:
        return None
    first = deepcopy(bay)
    for key in ("width_mm", "height_mm"):
        first.pop(key, None)
    if first.get("sliding_layout"):
        first.pop("sliding_layout")
        if first.get("opening_type") == "SLIDING":
            first["opening_type"] = "SLIDING_2L"
    unit_kind = first.pop("unit_kind", None)
    second = mirror_bay(first) if axis == "V" else deepcopy(first)
    second["id"] = second_bay_id
    split = {
        "id": split_id,
        "type": f"SPLIT_{axis}",
        "split_offset_mm": str(offset),
        "mullion_profile_sku": mullion_sku,
        "children": [first, second],
    }
    if unit_kind is not None:
        split["unit_kind"] = unit_kind
    if root is bay:
        tree = split
    else:
        try:
            replace(root, bay_id, split)
        except ValueError:
            return None
    module["tree"] = tree
    return tree


def apply_remove_divider(
    module: dict[str, Any],
    divider_id: str,
    *,
    keep_bay_id: str | None,
) -> dict[str, Any] | None:
    """Port de removeDivision: solo cuando ambos hijos son BAY."""
    tree = clone_tree(module.get("tree")) or {}
    root = unwrap(tree)
    node = find(root, divider_id)
    if node is None or node.get("type") not in SPLIT_TYPES:
        return None
    children = node.get("children") or []
    if len(children) != 2 or not all(c.get("type") == "BAY" for c in children):
        return None
    merged = None
    if isinstance(keep_bay_id, str):
        merged = next((c for c in children if c.get("id") == keep_bay_id), None)
        if merged is None:
            return None
    merged = merged or children[0]
    if root is node:
        module["tree"] = deepcopy(merged)
    else:
        try:
            replace(root, divider_id, deepcopy(merged))
        except ValueError:
            return None
        module["tree"] = tree
    return module["tree"]


def apply_remove_bay(module: dict[str, Any], bay_id: str) -> dict[str, Any] | None:
    """Port de removeModuleBay: colapsa el split padre con el hermano."""
    parent = parent_split(module.get("tree") or {}, bay_id)
    if parent is None:
        return None
    children = parent.get("children") or []
    sibling = next((c for c in children if c.get("id") != bay_id), None)
    if sibling is None:
        return None
    return apply_remove_divider(module, parent["id"], keep_bay_id=sibling.get("id"))


def apply_move_divider(
    module: dict[str, Any], divider_id: str, offset_mm: Any
) -> dict[str, Any] | None:
    tree = clone_tree(module.get("tree")) or {}
    root = unwrap(tree)
    node = find(root, divider_id)
    offset = _num(offset_mm)
    if node is None or node.get("type") not in SPLIT_TYPES or offset is None or offset <= 0:
        return None
    node["split_offset_mm"] = str(offset)
    module["tree"] = tree
    return tree


def apply_equalize(module: dict[str, Any], *, members: dict[str, Any]) -> dict[str, Any] | None:
    """Reparto igualitario de las divisiones de un módulo: cada cadena de
    splits del mismo eje deja las hojas con igual vano libre (la misma
    semántica que equalizeModuleBays del frontend).

    Una "cadena" es un split más los splits hijos de su mismo tipo siguiendo
    ramas por las que la cadena continúa (divisiones paralelas del mismo
    vano); las subcadenas anidadas se resuelven en su propia región."""
    tree = clone_tree(module.get("tree")) or {}
    root = unwrap(tree)
    width = _num(module.get("width_mm"))
    height = _num(module.get("height_mm"))
    mullion_face = {
        "SPLIT_V": _num(members.get("mullion_v_mm")) or Decimal("0"),
        "SPLIT_H": _num(members.get("mullion_h_mm")) or Decimal("0"),
    }

    def _has_same_axis_ancestor(node: dict[str, Any]) -> bool:
        path = _path_to(root, node["id"]) or []
        return any(parent.get("type") == node["type"] for parent, _ in path)

    def _chain(node: dict[str, Any]) -> list[dict[str, Any]]:
        chain = [node]
        current = node
        while True:
            nxt = next(
                (
                    child
                    for child in current.get("children") or []
                    if isinstance(child, dict) and child.get("type") == node["type"]
                ),
                None,
            )
            if nxt is None:
                return chain
            chain.append(nxt)
            current = nxt

    for node in walk(root):
        if node.get("type") not in SPLIT_TYPES or _has_same_axis_ancestor(node):
            continue
        chain = _chain(node)
        vertical = node["type"] == "SPLIT_V"
        module_span = width if vertical else height
        if module_span is None or module_span <= 0:
            return None
        mullion = mullion_face[node["type"]]
        # La región del eje que la cadena reparte es la del split raíz.
        reg = region(tree, node["id"], vertical=vertical,
                     module_span_mm=module_span, members=members)
        if reg is None or reg["span_mm"] <= 0:
            return None
        lo = reg["origin_mm"]
        span = reg["span_mm"]
        count = len(chain)
        share = (span - count * mullion) / (count + 1)
        if share <= 0:
            return None
        for slot, split in enumerate(chain):
            centerline = lo + (slot + 1) * share + (slot + 1) * mullion - mullion / 2
            # El offset almacenado se mide en las coordenadas de la región
            # del propio split: 0 para el split raíz del módulo, lo de su
            # región padre para los anidados.
            if _path_to(root, split["id"]) == []:
                origin = Decimal("0")
            else:
                own = region(
                    tree, split["id"], vertical=vertical,
                    module_span_mm=module_span, members=members,
                )
                if own is None:
                    return None
                origin = own["origin_mm"]
            offset = centerline - origin
            if offset <= 0:
                return None
            split["split_offset_mm"] = str(offset)
    module["tree"] = tree
    return tree


def resize_bay(
    module: dict[str, Any],
    bay_id: str,
    *,
    axis: str | None,
    mm: Any,
    members: dict[str, Any],
) -> dict[str, Any] | str | None:
    """Fija el vano libre de una hoja moviendo la división que la acota en
    el eje pedido. Devuelve el árbol mutado, un motivo de rechazo (str) o
    None si no aplica. Reglas iguales que resizeModuleBay del frontend:

    - Un módulo de una sola hoja se redimensiona entero (ancho/alto).
    - Si la hoja no tiene antecesor en ese eje, no hay divisor que mover.
    - El split que la acota se mueve en coordenadas de su propia región.
    """
    tree = clone_tree(module.get("tree")) or {}
    root = unwrap(tree)
    bay = find(root, bay_id)
    target = _num(mm)
    if bay is None or target is None or target <= 0:
        return "hoja_invalida"
    if axis is None:
        parent = parent_split(tree, bay_id)
        axis = "V" if (parent or {}).get("type") == "SPLIT_V" else "H" if parent else None
        if axis is None:
            # Módulo de una sola hoja: el vano ES el módulo — ajustar la
            # medida visible del módulo en el ancho (la lectura natural de
            # "la hoja de 450" cuando no hay divisiones).
            if _num(module.get("width_mm")) is None:
                return "hoja_invalida"
            module["width_mm"] = str(target)
            module["tree"] = tree
            return tree
    module_span = _num(module.get("width_mm")) if axis == "V" else _num(module.get("height_mm"))
    if module_span is None or module_span <= 0:
        return "hoja_invalida"
    vertical = axis == "V"
    reg = region(tree, bay_id, vertical=vertical, module_span_mm=module_span, members=members)
    if reg is None or reg["span_mm"] <= 0 or target >= reg["span_mm"]:
        return "medida_invalida"
    path = _path_to(root, bay_id) or []
    # El antecesor del mismo eje más cercano que acota la hoja: si la hoja
    # es primer hijo la acota por arriba; si es segundo, por abajo.
    bound = None
    for parent, index in reversed(path):
        if parent.get("type") not in SPLIT_TYPES:
            continue
        if (parent["type"] == "SPLIT_V") != vertical:
            continue
        bound = (parent, index)
        break
    if bound is None:
        # La hoja cruza el módulo entero en este eje: ajustar el vano es
        # ajustar la medida del módulo en ese eje (lo que el usuario ve).
        key = "width_mm" if vertical else "height_mm"
        module[key] = str(target)
        module["tree"] = tree
        return tree
    parent, index = bound
    mullion_face = _num(
        members.get("mullion_v_mm" if vertical else "mullion_h_mm")
    ) or Decimal("0")
    half = mullion_face / 2
    if index == 0:
        centerline = reg["origin_mm"] + target + half
    else:
        centerline = reg["origin_mm"] + reg["span_mm"] - target - half
    if _path_to(root, parent["id"]) == []:
        origin = Decimal("0")
    else:
        own = region(
            tree, parent["id"], vertical=vertical,
            module_span_mm=module_span, members=members,
        )
        if own is None:
            return "medida_invalida"
        origin = own["origin_mm"]
    offset = centerline - origin
    if offset <= 0:
        return "medida_invalida"
    parent["split_offset_mm"] = str(offset)
    module["tree"] = tree
    return tree


def apply_opening(node: dict[str, Any], opening: str) -> None:
    """Port reducido de changeOpening sobre el sim: la apertura enum es lo
    que la sim proyecta; los specs D03 pasan como key y el frontend resuelve
    el OPTION_SPEC real."""
    node["opening_type"] = opening
    for key in ("opening", "leaves", "handle_model_sku", "handle_color_sku",
                "hardware_option_skus"):
        node.pop(key, None)
    if opening == "DOOR_ENTRY":
        node.setdefault("door_handedness", "LEFT")
    else:
        node.pop("door_handedness", None)


def set_field(node: dict[str, Any], field: str, value: Any) -> None:
    if value is None:
        node.pop(field, None)
    else:
        node[field] = value


__all__ = [
    "SPLIT_TYPES",
    "apply_equalize",
    "apply_move_divider",
    "apply_opening",
    "apply_remove_bay",
    "apply_remove_divider",
    "apply_split",
    "bays",
    "clone_tree",
    "divisions",
    "find",
    "find_in_module",
    "flip_bay",
    "is_door",
    "is_sliding",
    "mirror_bay",
    "opening_of",
    "parent_split",
    "region",
    "set_field",
    "sliding_panels",
    "unwrap",
    "walk",
]
