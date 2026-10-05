"""Registro único de operaciones del editor y del proyecto (IA2 §1).

La UI (comandos del editor), la IA (ops del asistente y del agente) y la API
validan contra ESTE vocabulario — cada op declara nombre, esquema de
parámetros, alcance, banderas de lote y la descripción en español que el
prompt sirve al modelo. El esquema JSON se exporta en OpenAPI y el contrato
TypeScript se genera desde aquí (`scripts/gen_ops_contract.py`): si una
vista del contrato diverge del registro, es un bug del generador, nunca una
versión paralela.

Scope de una op:

- ``product`` — muta el ProductJson del canvas; la aplicación la ejecuta el
  registry de comandos del frontend (`applyDesignOps`), que es la MISMA
  función que un clic del usuario.
- ``position`` — muta campos de la fila `project_positions` (sistema,
  acabado, ubicación, cantidad); el asistente la valida y el cliente la
  aplica por el canal de posición (save/update) — nunca dentro del producto.
- ``project`` — actúa sobre posiciones del proyecto (crear, duplicar,
  quitar, actualizar); el agente la valida como propuesta y la persona la
  confirma — el frontend la ejecuta por los endpoints reales de posiciones.

`numeric=True` en un parámetro exige que el valor sea citable: un número
literal del pedido del usuario, un número del contexto u observaciones, o
una derivación aritmética de esos ("20 cm más ancha"). Los números
inventados se rechazan en validación, no se redondean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Modelo del registro
# ---------------------------------------------------------------------------

_PARAM_KINDS = frozenset(
    {"mm", "deg", "int", "string", "enum", "sku", "ref", "uuid", "bool"}
)
_SCOPES = frozenset({"product", "position", "project"})
_REF_KINDS = frozenset({"module", "coupling", "bay", "divider", "position"})


@dataclass(frozen=True)
class OpParam:
    """Un parámetro de op: nombre, tipo de wire y cómo se valida."""

    name: str
    kind: str
    required: bool = True
    enum: tuple[str, ...] = ()
    # numeric=True → el valor debe ser un número citable (ver docstring del
    # módulo). kind="int" también valida entero positivo acotado.
    numeric: bool = False
    # ref: qué entidad del resumen resuelve el campo ("module", "coupling",
    # "bay", "divider", "position"). Vacío = no es una referencia.
    ref: str = ""
    # allow_wildcard: el campo acepta "*" (solo refs en ops batchable).
    allow_wildcard: bool = False
    # nullable: el campo puede ser null explícito (p.ej. quitar el panel).
    nullable: bool = False
    # catalog: nombre del bloque del catálogo que acota el valor
    # ("openings", "glass", "panel", "mullions", "systems", "finishes").
    catalog: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _PARAM_KINDS:
            raise ValueError(f"param kind desconocido: {self.kind}")
        if self.ref and self.ref not in _REF_KINDS:
            raise ValueError(f"ref desconocida: {self.ref}")
        if self.enum and self.kind != "enum":
            raise ValueError("enum solo aplica a kind='enum'")


@dataclass(frozen=True)
class Op:
    """Una operación tipada del contrato."""

    name: str
    description: str
    scope: str = "product"
    params: tuple[OpParam, ...] = ()
    # batchable: el agente puede repetirla en lote por posición (batch_ops).
    # Las estructurales (agregar/quitar módulos/uniones/divisiones) nunca se
    # lotean — repetir una geometría distinta es alucinar, no un atajo.
    batchable: bool = False
    structural: bool = False
    examples: tuple[dict, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.scope not in _SCOPES:
            raise ValueError(f"scope desconocido: {self.scope}")
        if self.structural and self.batchable:
            raise ValueError(f"{self.name}: una op estructural no es batchable")


# ---------------------------------------------------------------------------
# Parámetros compartidos
# ---------------------------------------------------------------------------

_MODULE = OpParam(
    "module", "ref", ref="module",
    description="ref del módulo del producto (product.modules[].ref)",
)
_BAY = OpParam(
    "bay", "ref", required=False, ref="bay",
    description="ref de la hoja/bahía dentro del módulo; omitir = todas o la principal",
)
_COUPLING = OpParam(
    "coupling", "ref", ref="coupling",
    description="ref de la unión (acople) entre módulos",
)
_POSITION = OpParam(
    "position_id", "ref", ref="position",
    description="id de la posición del proyecto (visible en el contexto)",
)


# ---------------------------------------------------------------------------
# Ops de producto (el canvas las aplica con applyDesignOps)
# ---------------------------------------------------------------------------

PRODUCT_OPS: tuple[Op, ...] = (
    Op(
        "set_module_count",
        "Reconfigurar el conjunto a N módulos iguales acoplados en línea",
        params=(
            OpParam("count", "int", numeric=True, description="1..12"),
        ),
        examples=({"op": "set_module_count", "count": 2},),
    ),
    Op(
        "add_unit",
        "Agregar una unidad al extremo (izquierda o derecha) del conjunto",
        structural=True,
        params=(
            OpParam("side", "enum", enum=("left", "right")),
        ),
        examples=({"op": "add_unit", "side": "right"},),
    ),
    Op(
        "remove_unit",
        "Quitar un módulo del conjunto (sella la junta que quedaba libre)",
        structural=True,
        params=(_MODULE,),
    ),
    Op(
        "duplicate_module",
        "Duplicar un módulo pegado a su derecha (misma especificación)",
        structural=True,
        params=(_MODULE,),
    ),
    Op(
        "add_stacked_unit",
        "Apilar una unidad encima de un módulo (banderola sobre puerta/ventana)",
        structural=True,
        params=(
            _MODULE,
            OpParam(
                "height_mm", "mm", required=False, numeric=True,
                description="alto de la unidad superior; omitir usa el default del editor",
            ),
        ),
    ),
    Op(
        "insert_module",
        "Insertar un módulo en medio de dos unidades acopladas (sobre su unión)",
        structural=True,
        params=(_COUPLING,),
    ),
    Op(
        "remove_coupling",
        "Separar una unión: el conjunto se divide en dos subconjuntos",
        structural=True,
        params=(_COUPLING,),
    ),
    Op(
        "set_coupling_kind",
        "Cambiar el tipo de unión (INLINE en línea, STACKED apilado, TEE en T, CORNER en esquina)",
        params=(
            _COUPLING,
            OpParam("kind", "enum", enum=("INLINE", "STACKED", "TEE", "CORNER")),
        ),
        batchable=True,
    ),
    Op(
        "set_module_width",
        "Fijar el ancho de un módulo (los demás conservan su medida)",
        params=(
            _MODULE,
            OpParam("width_mm", "mm", numeric=True),
        ),
        batchable=True,
        examples=({"op": "set_module_width", "module": "m1", "width_mm": "900"},),
    ),
    Op(
        "set_total_width",
        "Escalar todos los anchos para que el conjunto mida el total pedido",
        params=(
            OpParam("width_mm", "mm", numeric=True),
        ),
        batchable=True,
    ),
    Op(
        "set_height",
        "Fijar el alto de todos los módulos del conjunto",
        params=(
            OpParam("height_mm", "mm", numeric=True),
        ),
        batchable=True,
    ),
    Op(
        "equalize_widths",
        "Igualar el ancho de todos los módulos del conjunto",
        batchable=True,
    ),
    Op(
        "equalize_angles",
        "Igualar los ángulos de todas las uniones (reparte el giro total)",
        batchable=True,
    ),
    Op(
        "set_coupling_angle",
        "Fijar el ángulo de una unión (esquina/bow); redondeo a 0,1°",
        params=(
            _COUPLING,
            OpParam("angle_deg", "deg", numeric=True),
        ),
        batchable=True,
    ),
    Op(
        "split_bay",
        "Dividir una hoja de un módulo con montante (axis V) o travesaño (axis H). "
        "offset_mm se mide desde el borde inicial del vano según 'from' "
        "(START=izquierda/arriba, END=derecha/abajo, CENTER=centrado); "
        "parts=N divide la hoja en N partes iguales (el número debe venir del "
        "pedido — 'en tres hojas' declara 3); "
        "mullion_sku puede omitirse si el catálogo tiene un único perfil para ese eje",
        structural=True,
        params=(
            _MODULE,
            _BAY,
            OpParam("axis", "enum", enum=("V", "H")),
            OpParam(
                "offset_mm", "mm", required=False, numeric=True,
                description="posición del eje del montante/travesaño; omitir = centrar",
            ),
            OpParam(
                "from", "enum", required=False, enum=("START", "END", "CENTER"),
                description="desde dónde se mide offset_mm (default START)",
            ),
            OpParam(
                "parts", "int", required=False, numeric=True,
                description="N partes iguales (2..8) — sustituye offset_mm; "
                "el count debe estar declarado en el pedido",
            ),
            OpParam(
                "mullion_sku", "sku", required=False, catalog="mullions",
                description="SKU del poste/travesaño; por defecto el del catálogo para el eje",
            ),
        ),
        examples=(
            {"op": "split_bay", "module": "m1", "axis": "V", "offset_mm": "750"},
            {"op": "split_bay", "module": "m1", "bay": "m1/b2", "axis": "H", "from": "CENTER"},
            {"op": "split_bay", "module": "m1", "axis": "V", "parts": 3},
        ),
    ),
    Op(
        "equalize_bays",
        "Igualar las hojas de un módulo (reparte el vano entre las divisiones)",
        params=(_MODULE,),
        batchable=True,
    ),
    Op(
        "set_bay_size",
        "Fijar la medida de una hoja dentro de su división (ancho con axis V, "
        "alto con axis H); la hoja vecina absorbe la diferencia. En un módulo "
        "de una sola hoja equivale a cambiar su ancho/alto",
        params=(
            _MODULE,
            OpParam("bay", "ref", required=True, ref="bay"),
            OpParam("mm", "mm", numeric=True),
            OpParam(
                "axis", "enum", required=False, enum=("V", "H"),
                description="omitir usa el eje de la división padre",
            ),
        ),
        batchable=True,
    ),
    Op(
        "move_divider",
        "Mover un montante/travesaño existente a otro offset del vano",
        params=(
            _MODULE,
            OpParam("divider", "ref", required=True, ref="divider"),
            OpParam("offset_mm", "mm", numeric=True),
        ),
        batchable=True,
    ),
    Op(
        "remove_divider",
        "Quitar un montante/travesaño: sus dos hojas se fusionan (keep_bay "
        "elige cuál sobrevive; por defecto la primera)",
        structural=True,
        params=(
            _MODULE,
            OpParam("divider", "ref", required=True, ref="divider"),
            OpParam(
                "keep_bay", "ref", required=False, ref="bay",
                description="hoja que conserva su especificación al fusionar",
            ),
        ),
    ),
    Op(
        "remove_bay",
        "Eliminar una hoja de un módulo dividido (la hoja vecina ocupa el vano)",
        structural=True,
        params=(
            _MODULE,
            OpParam("bay", "ref", required=True, ref="bay"),
        ),
    ),
    Op(
        "set_opening",
        "Cambiar la apertura de las hojas del módulo — o solo de una hoja si "
        "se pasa 'bay'. El valor es una key de catalog.openings (las "
        "aperturas que el sistema admite) — nunca un nombre libre",
        params=(
            _MODULE,
            _BAY,
            OpParam("opening", "string", catalog="openings"),
        ),
        batchable=True,
        examples=(
            {"op": "set_opening", "module": "m1", "opening": "TILT_TURN_LEFT"},
            {"op": "set_opening", "module": "m1", "bay": "m1/b2", "opening": "FIXED"},
        ),
    ),
    Op(
        "flip_handing",
        "Espejar la hoja: manilla al lado opuesto (TURN↔, TILT_TURN↔, "
        "hoja primaria de corredera, dirección de puerta)",
        params=(_MODULE, _BAY),
        batchable=True,
    ),
    Op(
        "set_handle_height",
        "Fijar la altura de la manilla (mm) sobre una hoja. Solo si el dato "
        "es inequívoco; si la referencia es ambigua (¿desde el vano? ¿desde el "
        "piso?) pregunta con clarify en vez de operar",
        params=(
            _MODULE,
            _BAY,
            OpParam("mm", "mm", numeric=True, description="altura de la manilla"),
        ),
        batchable=True,
    ),
    Op(
        "set_sliding_layout",
        "Fijar la configuración de corredera (preset SLIDING_2L/3L/4L o "
        "'layout' completo) sobre una hoja corredera",
        params=(
            _MODULE,
            _BAY,
            OpParam(
                "preset", "enum", required=False,
                enum=("SLIDING_2L", "SLIDING_3L", "SLIDING_4L"),
            ),
            OpParam(
                "primary_index", "int", required=False,
                description="índice de la hoja que corre primero (0-based)",
            ),
        ),
        batchable=True,
    ),
    Op(
        "set_travel",
        "Cambiar qué hoja de la corredera es la que corre (panel móvil↔fijo)",
        params=(
            _MODULE,
            _BAY,
            OpParam("slot", "int", description="posición del panel (0-based)"),
            OpParam("kind", "enum", enum=("MOVING", "FIXED")),
        ),
        batchable=True,
    ),
    Op(
        "set_glass",
        "Cambiar el vidrio de las hojas del módulo — o de una hoja con 'bay'. "
        "sku es el SKU de catálogo (catalog.glass_skus); 'recipe' permite "
        "pedir por receta declarada (catalog.glass_recipes, p.ej. '4-12-4')",
        params=(
            _MODULE,
            _BAY,
            OpParam("sku", "sku", required=False, catalog="glass"),
            OpParam(
                "recipe", "string", required=False, catalog="glass",
                description="receta declarada del vidrio cuando no hay SKU a mano",
            ),
        ),
        batchable=True,
    ),
    Op(
        "set_glass_thickness",
        "Cambiar el espesor de acristalamiento (mm) — debe estar en "
        "catalog.thicknesses para que el sistema lo acristale",
        params=(
            _MODULE,
            _BAY,
            OpParam("mm", "mm", numeric=True, catalog="thicknesses"),
        ),
        batchable=True,
    ),
    Op(
        "set_panel",
        "Poner o quitar el panel sándwich de las hojas (sku=null lo quita)",
        params=(
            _MODULE,
            _BAY,
            OpParam("sku", "sku", catalog="panel", nullable=True),
        ),
        batchable=True,
    ),
)


# ---------------------------------------------------------------------------
# Ops de posición (se aplican por el canal de posición, no por el producto)
# ---------------------------------------------------------------------------

POSITION_OPS: tuple[Op, ...] = (
    Op(
        "set_system",
        "Cambiar la serie del diseño (catalog.systems lista las elegibles; "
        "cambiar de material/familia puede invalidar la tipología)",
        scope="position",
        params=(
            OpParam("system_id", "uuid", catalog="systems"),
        ),
    ),
    Op(
        "set_finish",
        "Cambiar el acabado/color de la posición (catalog.finishes)",
        scope="position",
        params=(
            OpParam("color", "string", catalog="finishes"),
        ),
    ),
    Op(
        "set_location",
        "Asignar la etiqueta de ubicación de la posición (Dormitorio, Baño…)",
        scope="position",
        params=(
            OpParam("location", "string", description="texto libre, máx. 100"),
        ),
    ),
    Op(
        "set_quantity",
        "Cambiar la cantidad de unidades de la posición",
        scope="position",
        params=(
            OpParam("count", "int", numeric=True, description="1..9999"),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Ops de proyecto (propuestas del agente; la persona confirma y el frontend
# ejecuta por los endpoints reales de posiciones)
# ---------------------------------------------------------------------------

PROJECT_OPS: tuple[Op, ...] = (
    Op(
        "add_position",
        "Crear una posición nueva en el proyecto con dimensiones y apertura "
        "iniciales (borrador que la persona revisa en la superficie real)",
        scope="project",
        params=(
            OpParam("width_mm", "mm", numeric=True),
            OpParam("height_mm", "mm", numeric=True),
            OpParam("location", "string", required=False),
            OpParam("opening", "string", required=False, catalog="openings"),
            OpParam("system_id", "uuid", required=False, catalog="systems"),
            OpParam("quantity", "int", required=False, numeric=True),
        ),
    ),
    Op(
        "duplicate_position",
        "Duplicar una posición existente (mismo diseño, nuevo índice)",
        scope="project",
        params=(
            _POSITION,
            OpParam("count", "int", required=False, numeric=True),
        ),
    ),
    Op(
        "remove_position",
        "Eliminar una posición del proyecto",
        scope="project",
        params=(_POSITION,),
    ),
    Op(
        "update_position",
        "Actualizar campos de una posición: ubicación, cantidad, sistema o "
        "acabado (cada campo opcional, al menos uno requerido)",
        scope="project",
        params=(
            _POSITION,
            OpParam("location", "string", required=False),
            OpParam("quantity", "int", required=False, numeric=True),
            OpParam("system_id", "uuid", required=False, catalog="systems"),
            OpParam("finish", "string", required=False, catalog="finishes"),
        ),
    ),
)


OPS: tuple[Op, ...] = PRODUCT_OPS + POSITION_OPS + PROJECT_OPS
OP_INDEX: dict[str, Op] = {op.name: op for op in OPS}


def op_for(name: Any) -> Op | None:
    return OP_INDEX.get(name) if isinstance(name, str) else None


def product_ops() -> tuple[Op, ...]:
    return PRODUCT_OPS


def position_ops() -> tuple[Op, ...]:
    return POSITION_OPS


def project_ops() -> tuple[Op, ...]:
    return PROJECT_OPS


def batchable_ops() -> frozenset[str]:
    return frozenset(op.name for op in OPS if op.batchable)


# ---------------------------------------------------------------------------
# Descripción para el modelo (sección "ops" del system prompt)
# ---------------------------------------------------------------------------


def _param_signature(op: Op) -> str:
    """Firma compacta para el prompt: {campo} obligatorio, [campo] opcional."""
    parts = []
    for param in op.params:
        token = param.name
        if param.enum:
            token = f"{param.name}:{'|'.join(param.enum)}"
        elif param.kind == "mm":
            token = param.name
        parts.append(token if param.required else f"[{token}]")
    return f"{op.name} {{{', '.join(parts)}}}"


def ops_contract() -> dict[str, list[str]]:
    """Las firmas agrupadas por scope — el payload "ops_contract" que los
    prompts incluyen literalmente (firma + descripción vienen del registro,
    así el modelo y el validador nunca divergen)."""
    return {
        scope: [
            f"{_param_signature(op)} — {op.description}" for op in OPS if op.scope == scope
        ]
        for scope in ("product", "position", "project")
    }


def ops_prompt_block(*, scopes: Iterable[str] = ("product",)) -> str:
    """La sección del system prompt que documenta las ops de los scopes
    pedidos — texto derivado del registro, con ejemplos del registro."""
    lines: list[str] = []
    for scope in scopes:
        for op in OPS:
            if op.scope != scope:
                continue
            lines.append(f"  {_param_signature(op)} — {op.description}")
            for example in op.examples[:1]:
                lines.append(f"    ej: {example}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON Schema (exportado en OpenAPI vía el endpoint /ai/ops-contract/)
# ---------------------------------------------------------------------------

_JSON_KIND = {
    "mm": "string",  # la convención del contrato: decimales como string
    "deg": "string",
    "int": "integer",
    "string": "string",
    "enum": "string",
    "sku": "string",
    "ref": "string",
    "uuid": "string",
    "bool": "boolean",
}


def ops_json_schema() -> dict:
    """JSON Schema del contrato completo — también es la fuente de
    `opsContract.generated.ts`. Incluye per-op su esquema de objeto."""
    ops_schema: dict[str, Any] = {}
    for op in OPS:
        properties: dict[str, Any] = {"op": {"const": op.name}}
        required = ["op"]
        for param in op.params:
            schema: dict[str, Any] = {"type": _JSON_KIND[param.kind]}
            if param.enum:
                schema["enum"] = list(param.enum)
            if param.nullable:
                schema = {"anyOf": [schema, {"type": "null"}]}
            if param.kind in ("mm", "deg"):
                schema["description"] = "número decimal como string (mm)"
            if param.description:
                schema["description"] = (
                    f"{schema.get('description', '')} {param.description}".strip()
                )
            properties[param.name] = schema
            if param.required:
                required.append(param.name)
        ops_schema[op.name] = {
            "type": "object",
            "required": required,
            "additionalProperties": False,
            "properties": properties,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "DekopenDesignOps",
        "version": 2,
        "ops": ops_schema,
    }


def contract_document() -> dict:
    """El documento servido por GET /ai/ops-contract/ — metadatos por op que
    el cliente y la documentación consumen sin parsear el prompt."""
    return {
        "version": 2,
        "scopes": sorted(_SCOPES),
        "ops": [
            {
                "name": op.name,
                "scope": op.scope,
                "batchable": op.batchable,
                "structural": op.structural,
                "description": op.description,
                "params": [
                    {
                        "name": param.name,
                        "kind": param.kind,
                        "required": param.required,
                        "enum": list(param.enum),
                        "numeric": param.numeric,
                        "ref": param.ref,
                        "allow_wildcard": param.allow_wildcard,
                        "nullable": param.nullable,
                        "catalog": param.catalog,
                        "description": param.description,
                    }
                    for param in op.params
                ],
                "examples": list(op.examples),
            }
            for op in OPS
        ],
        "schema": ops_json_schema(),
    }


__all__ = [
    "OPS",
    "OP_INDEX",
    "Op",
    "OpParam",
    "PRODUCT_OPS",
    "POSITION_OPS",
    "PROJECT_OPS",
    "batchable_ops",
    "contract_document",
    "op_for",
    "ops_contract",
    "ops_json_schema",
    "ops_prompt_block",
    "position_ops",
    "product_ops",
    "project_ops",
]
