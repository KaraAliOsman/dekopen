"""Proyección estructural del producto para la comparación por resultado.

Convierte un ProductJson (`version: product-v2`, con `assembly.modules[]` y
`assembly.couplings[]`) en una forma evaluable: medidas exactas en mm, las
bahías en orden de lectura con su apertura/vidrio/panel, las divisiones del
árbol de intención y los acoples entre módulos. Es la misma información que
el contrato exige comparar ("medidas exactas en mm, aperturas, SKU de vidrio")
y nada del texto del modelo.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _mm(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _walk(node: Any, bays: list, splits: list) -> None:
    """DFS por el árbol de intención. ROOT con un solo hijo transparenta
    (es la envoltura convencional del editor, igual que en productEditing);
    las hojas BAY quedan en orden de lectura izquierda→derecha / arriba→abajo
    porque ese es el orden de children del modelo."""
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "ROOT":
        children = node.get("children") or []
        # Un ROOT de un solo hijo es solo envoltura (productEditing hace lo
        # mismo al aplicar aperturas/materiales).
        if len(children) == 1:
            _walk(children[0], bays, splits)
            return
        for child in children:
            _walk(child, bays, splits)
        return
    if node_type in ("SPLIT_V", "SPLIT_H"):
        splits.append(
            {
                "type": node_type,
                "offset_mm": _mm(node.get("split_offset_mm")),
                "mullion_sku": node.get("mullion_profile_sku"),
            }
        )
        for child in node.get("children") or []:
            _walk(child, bays, splits)
        return
    if node_type == "BAY":
        layout = node.get("sliding_layout")
        bays.append(
            {
                "opening_type": node.get("opening_type"),
                "glass_article_sku": node.get("glass_article_sku"),
                "glass_spec": node.get("glass_spec"),
                "glass_thickness_mm": _mm(node.get("glass_thickness_mm")),
                "panel_article_sku": node.get("panel_article_sku"),
                "door_handedness": node.get("door_handedness"),
                # IA2 — campos que las nuevas ops escriben: altura de
                # manilla y preset corredera (set_travel/set_sliding_layout).
                "handle_height_mm": _mm(node.get("handle_height_mm")),
                "sliding_preset": layout.get("preset")
                if isinstance(layout, dict)
                else None,
                "sliding_primary_index": layout.get("primary_index")
                if isinstance(layout, dict)
                else None,
            }
        )
        return
    # Nodos desconocidos se recorren por si traen hijos (defensivo).
    for child in node.get("children") or []:
        _walk(child, bays, splits)


def project_product(product: Any) -> dict[str, Any] | None:
    """ProductJson → proyección evaluable. Devuelve None si no es un
    producto-v2 legible (el caller lo reporta como caso no evaluable)."""
    if not isinstance(product, dict):
        return None
    assembly = product.get("assembly")
    if not isinstance(assembly, dict):
        return None
    modules = []
    for module in assembly.get("modules") or []:
        if not isinstance(module, dict):
            continue
        bays: list = []
        splits: list = []
        _walk(module.get("tree"), bays, splits)
        modules.append(
            {
                "id": module.get("id"),
                "width_mm": _mm(module.get("width_mm")),
                "height_mm": _mm(module.get("height_mm")),
                "bays": bays,
                "splits": splits,
            }
        )
    couplings = [
        {
            "id": coupling.get("id"),
            "angle_deg": _mm(coupling.get("angle_deg")),
            "kind": coupling.get("kind"),
            "modules": coupling.get("modules"),
            "edges": coupling.get("edges"),
        }
        for coupling in assembly.get("couplings") or []
        if isinstance(coupling, dict)
    ]
    widths = [m["width_mm"] for m in modules if m["width_mm"] is not None]
    heights = [m["height_mm"] for m in modules if m["height_mm"] is not None]
    return {
        "module_count": len(modules),
        "total_width_mm": sum(widths) if len(widths) == len(modules) and modules else None,
        "height_mm": heights[0] if heights and len(set(heights)) == 1 else heights or None,
        "modules": modules,
        "couplings": couplings,
        "bay_openings": [bay["opening_type"] for m in modules for bay in m["bays"]],
    }


def dec(value: Any) -> Decimal | None:
    return _mm(value)
