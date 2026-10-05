"""Transport normalization and deterministic call into the pure engine."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from dekopen_engine import (
    BayLeaf,
    BayOpeningType,
    ColorCombinationError,
    ColorSelection,
    CoupledAssembly,
    CouplingDef,
    EffectiveProfileArticle,
    EngineResult,
    HingeSide,
    LeafRole,
    NodeType,
    Opening,
    OpeningDirection,
    OpeningMovement,
    ParametricNode,
    ProductEvaluation,
    ProductModel,
    ProductModule,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SystemParams,
    UnitKind,
    calculate_geometry,
    evaluate_product,
    resolve_color_selection,
)
from dekopen_engine.contour import Contour
from dekopen_engine.glass_composition import composition_from_dict
from dekopen_engine.models import GlassOptions, PlanPoint
from dekopen_engine.product import (
    ConnectionKind,
    EdgeSide,
    FramelessFitting,
    FramelessFittingKind,
    FramelessSpec,
    FramelessSupport,
    FramelessSupportKind,
    elevation_envelope as elevation_envelope,
)


class InvalidEngineRequest(ValueError):
    pass


class UnsupportedEngineContract(ValueError):
    pass


_NODE_FIELDS = {
    "id",
    "type",
    "width_mm",
    "height_mm",
    "split_offset_mm",
    "mullion_profile_sku",
    "children",
    "opening_type",
    "glass_thickness_mm",
    "glass_spec",
    "glass_composition",
    "glass_options",
    "glass_article_sku",
    "panel_article_sku",
    "hardware_set_sku",
    "handle_height_mm",
    "handle_model_sku",
    "handle_color_sku",
    "hardware_option_skus",
    "door_handedness",
    "sliding_layout",
    # D03 — the opening spec is the new source of truth; opening_type
    # stays accepted for one version.
    "opening",
    "leaves",
    "unit_kind",
}
_DECIMAL_NODE_FIELDS = {
    "width_mm",
    "height_mm",
    "split_offset_mm",
    "glass_thickness_mm",
    "handle_height_mm",
}


def _decimal_string(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise InvalidEngineRequest(f"{field_name} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise InvalidEngineRequest(f"{field_name} must be a decimal string") from error
    if not number.is_finite():
        raise InvalidEngineRequest(f"{field_name} must be finite")
    return number


def parse_parametric_node(payload: object) -> ParametricNode:
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise InvalidEngineRequest("parametric_tree must be an object")
    raw = cast(dict[str, object], payload)
    unexpected = set(raw) - _NODE_FIELDS
    if unexpected:
        raise InvalidEngineRequest("parametric_tree contains unsupported fields")
    if not isinstance(raw.get("id"), str) or not isinstance(raw.get("type"), str):
        raise InvalidEngineRequest("Every node requires string id and type")

    values: dict[str, object] = {"id": raw["id"]}
    try:
        values["type"] = NodeType(cast(str, raw["type"]))
        if "opening_type" in raw and raw["opening_type"] is not None:
            if not isinstance(raw["opening_type"], str):
                raise InvalidEngineRequest("opening_type must be a string")
            values["opening_type"] = BayOpeningType(cast(str, raw["opening_type"]))
    except ValueError as error:
        raise InvalidEngineRequest("Unsupported node or opening type") from error

    for field_name in _DECIMAL_NODE_FIELDS:
        if field_name in raw and raw[field_name] is not None:
            values[field_name] = _decimal_string(raw[field_name], field_name)
    for field_name in (
        "mullion_profile_sku",
        "glass_spec",
        "glass_article_sku",
        "panel_article_sku",
        "hardware_set_sku",
        "handle_model_sku",
        "handle_color_sku",
    ):
        if field_name in raw and raw[field_name] is not None:
            if not isinstance(raw[field_name], str):
                raise InvalidEngineRequest(f"{field_name} must be a string")
            values[field_name] = raw[field_name]

    if "hardware_option_skus" in raw and raw["hardware_option_skus"] is not None:
        option_skus = raw["hardware_option_skus"]
        if not isinstance(option_skus, list) or not all(
            isinstance(sku, str) for sku in option_skus
        ):
            raise InvalidEngineRequest(
                "hardware_option_skus must be an array of strings"
            )
        values["hardware_option_skus"] = list(option_skus)

    if "sliding_layout" in raw and raw["sliding_layout"] is not None:
        values["sliding_layout"] = _parse_sliding_layout(raw["sliding_layout"])

    if "glass_composition" in raw and raw["glass_composition"] is not None:
        if not isinstance(raw["glass_composition"], dict):
            raise InvalidEngineRequest("glass_composition must be an object")
        try:
            values["glass_composition"] = composition_from_dict(
                cast(dict[str, object], raw["glass_composition"])
            )
        except (ValueError, TypeError, KeyError) as error:
            raise InvalidEngineRequest("Invalid glass_composition") from error

    if "glass_options" in raw and raw["glass_options"] is not None:
        if not isinstance(raw["glass_options"], dict):
            raise InvalidEngineRequest("glass_options must be an object")
        try:
            values["glass_options"] = GlassOptions(
                **cast(dict[str, object], raw["glass_options"])
            )
        except (ValueError, TypeError) as error:
            raise InvalidEngineRequest("Invalid glass_options") from error

    if "opening" in raw and raw["opening"] is not None:
        values["opening"] = _parse_opening(raw["opening"])
    # An empty leaf list is the unset form — pydantic serializes the
    # default as [], so the wire contract treats it as absent.
    if raw.get("leaves"):
        values["leaves"] = _parse_leaves(raw["leaves"])
    if "unit_kind" in raw and raw["unit_kind"] is not None:
        if not isinstance(raw["unit_kind"], str):
            raise InvalidEngineRequest("unit_kind must be a string")
        try:
            values["unit_kind"] = UnitKind(cast(str, raw["unit_kind"]))
        except ValueError as error:
            raise InvalidEngineRequest(
                "unit_kind must be WINDOW or DOOR"
            ) from error

    if "door_handedness" in raw and raw["door_handedness"] is not None:
        if raw["door_handedness"] not in ("LEFT", "RIGHT"):
            raise InvalidEngineRequest("door_handedness must be LEFT or RIGHT")
        values["door_handedness"] = raw["door_handedness"]

    children = raw.get("children", [])
    if not isinstance(children, list):
        raise InvalidEngineRequest("children must be an array")
    values["children"] = [parse_parametric_node(child) for child in children]
    try:
        return ParametricNode(**values)
    except ValueError as error:
        raise InvalidEngineRequest("Invalid parametric_tree") from error


_OPENING_FIELDS = {"movement", "hinge_side", "direction", "leaf_role", "fixed_in_sash"}
_LEAF_FIELDS = {"slot", "opening"}


def _parse_opening(payload: object) -> Opening:
    """Deserialize a leaf's kinematics (D03): movement × hinge × direction
    × role; the engine's own validators reject incoherent combinations."""
    raw = _require_dict(payload, "opening")
    unexpected = set(raw) - _OPENING_FIELDS
    if unexpected:
        raise InvalidEngineRequest(
            f"opening contains unsupported fields: {sorted(unexpected)}"
        )
    values: dict[str, object] = {}
    movement_raw = _require_str(raw.get("movement"), "opening.movement")
    try:
        values["movement"] = OpeningMovement(movement_raw)
    except ValueError as error:
        raise InvalidEngineRequest(
            "opening.movement must be one of "
            + ", ".join(member.value for member in OpeningMovement)
        ) from error
    for field_name, enum in (
        ("hinge_side", HingeSide),
        ("direction", OpeningDirection),
        ("leaf_role", LeafRole),
    ):
        if field_name in raw and raw[field_name] is not None:
            text = _require_str(raw[field_name], f"opening.{field_name}")
            try:
                values[field_name] = enum(text)
            except ValueError as error:
                raise InvalidEngineRequest(
                    f"opening.{field_name} must be one of "
                    + ", ".join(member.value for member in enum)
                ) from error
    if raw.get("fixed_in_sash") is not None:
        if not isinstance(raw["fixed_in_sash"], bool):
            raise InvalidEngineRequest("opening.fixed_in_sash must be a boolean")
        values["fixed_in_sash"] = raw["fixed_in_sash"]
    try:
        return Opening(**values)
    except ValueError as error:
        raise InvalidEngineRequest(f"invalid opening: {error}") from error


def _parse_leaves(payload: object) -> list[BayLeaf]:
    if not isinstance(payload, list) or not payload:
        raise InvalidEngineRequest("leaves must be a non-empty array")
    leaves: list[BayLeaf] = []
    for index, item in enumerate(payload):
        raw = _require_dict(item, f"leaves[{index}]")
        unexpected = set(raw) - _LEAF_FIELDS
        if unexpected:
            raise InvalidEngineRequest(
                f"leaves[{index}] contains unsupported fields: "
                f"{sorted(unexpected)}"
            )
        leaves.append(
            BayLeaf(
                slot=_require_str(raw.get("slot"), f"leaves[{index}].slot"),
                opening=_parse_opening(raw.get("opening")),
            )
        )
    return leaves


def _parse_sliding_layout(payload: object) -> SlidingLayout:
    """Deserialize a node's declared sliding topology: rail count plus the
    ordered panels with their kind/track."""
    raw = _require_dict(payload, "sliding_layout")
    unexpected = set(raw) - {"tracks", "panels"}
    if unexpected:
        raise InvalidEngineRequest(
            f"sliding_layout contains unsupported fields: {sorted(unexpected)}"
        )
    if not isinstance(raw.get("tracks"), int) or isinstance(raw.get("tracks"), bool):
        raise InvalidEngineRequest("sliding_layout.tracks must be an integer")
    panels = raw.get("panels")
    if not isinstance(panels, list) or not panels:
        raise InvalidEngineRequest("sliding_layout.panels must be a non-empty array")
    parsed_panels: list[SlidingPanel] = []
    for index, panel in enumerate(panels):
        panel_raw = _require_dict(panel, f"sliding_layout.panels[{index}]")
        unexpected_panel = set(panel_raw) - {"slot", "kind", "track"}
        if unexpected_panel:
            raise InvalidEngineRequest(
                "sliding_layout.panels contains unsupported fields: "
                f"{sorted(unexpected_panel)}"
            )
        if not isinstance(panel_raw.get("slot"), str):
            raise InvalidEngineRequest("sliding_layout.panels[].slot must be a string")
        try:
            kind = SlidingPanelKind(cast(str, panel_raw.get("kind")))
        except ValueError as error:
            raise InvalidEngineRequest(
                "sliding_layout.panels[].kind must be MOVING or FIXED"
            ) from error
        track = panel_raw.get("track")
        if track is not None and (
            not isinstance(track, int) or isinstance(track, bool)
        ):
            raise InvalidEngineRequest("sliding_layout.panels[].track must be an integer or null")
        parsed_panels.append(
            SlidingPanel(slot=panel_raw["slot"], kind=kind, track=track)
        )
    return SlidingLayout(tracks=raw["tracks"], panels=parsed_panels)


def parse_contour(payload: object) -> Contour | None:
    """Deserialize a module contour: vertices + one signed sagitta per edge."""
    if payload is None:
        return None
    raw = _require_dict(payload, "module.contour")
    unexpected = set(raw) - {"vertices", "bulges"}
    if unexpected:
        raise InvalidEngineRequest(
            f"module.contour contains unsupported fields: {sorted(unexpected)}"
        )
    raw_vertices = raw.get("vertices")
    raw_bulges = raw.get("bulges")
    if not isinstance(raw_vertices, list) or not raw_vertices:
        raise InvalidEngineRequest("contour.vertices must be a non-empty array")
    if not isinstance(raw_bulges, list) or len(raw_bulges) != len(raw_vertices):
        raise InvalidEngineRequest("contour.bulges must match vertices one per edge")
    vertices: list[PlanPoint] = []
    for point in raw_vertices:
        vertex = _require_dict(point, "contour.vertices[]")
        unexpected = set(vertex) - {"x_mm", "y_mm"}
        if unexpected:
            raise InvalidEngineRequest("contour vertices carry only x_mm/y_mm")
        vertices.append(
            PlanPoint(
                x_mm=_decimal_string(vertex.get("x_mm"), "contour x_mm"),
                y_mm=_decimal_string(vertex.get("y_mm"), "contour y_mm"),
            )
        )
    bulges: list[Decimal | None] = [
        None if bulge is None else _decimal_string(bulge, "contour bulge")
        for bulge in raw_bulges
    ]
    try:
        return Contour(vertices=vertices, bulges=bulges)
    except ValueError as error:
        raise InvalidEngineRequest("Invalid module contour") from error


_SUPPORT_FIELDS = {"kind", "edge", "article_sku", "qty"}
_FITTING_FIELDS = {"kind", "sku", "qty"}
_FRAMELESS_FIELDS = {"supports", "fittings", "exposed_edges"}


def _parse_edge_side(value: object, label: str) -> EdgeSide:
    text = _require_str(value, label)
    try:
        return EdgeSide(text)
    except ValueError as error:
        raise InvalidEngineRequest(f"{label} must be a side (left/right/top/bottom)") from error


def _positive_qty(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvalidEngineRequest(f"{label} must be a positive integer")
    return value


def parse_frameless(payload: object) -> FramelessSpec | None:
    """Deserialize a glass-only module spec (mandate §14): declared supports,
    fittings and exposed edges — all validated enum/field whitelists."""
    if payload is None:
        return None
    raw = _require_dict(payload, "module.frameless")
    unexpected = set(raw) - _FRAMELESS_FIELDS
    if unexpected:
        raise InvalidEngineRequest(
            f"module.frameless contains unsupported fields: {sorted(unexpected)}"
        )

    supports: list[FramelessSupport] = []
    for item in raw.get("supports") or []:
        support = _require_dict(item, "frameless.supports[]")
        unexpected = set(support) - _SUPPORT_FIELDS
        if unexpected:
            raise InvalidEngineRequest(
                f"frameless support contains unsupported fields: {sorted(unexpected)}"
            )
        kind_raw = _require_str(support.get("kind"), "frameless.support.kind")
        try:
            kind = FramelessSupportKind(kind_raw)
        except ValueError as error:
            raise InvalidEngineRequest(
                "frameless support kind must be CHANNEL or CLAMPS"
            ) from error
        supports.append(
            FramelessSupport(
                kind=kind,
                edge=_parse_edge_side(support.get("edge"), "frameless.support.edge"),
                article_sku=_require_str(
                    support.get("article_sku"), "frameless.support.article_sku"
                ),
                qty=_positive_qty(support.get("qty", 1), "frameless.support.qty"),
            )
        )

    fittings: list[FramelessFitting] = []
    for item in raw.get("fittings") or []:
        fitting = _require_dict(item, "frameless.fittings[]")
        unexpected = set(fitting) - _FITTING_FIELDS
        if unexpected:
            raise InvalidEngineRequest(
                f"frameless fitting contains unsupported fields: {sorted(unexpected)}"
            )
        kind_raw = _require_str(fitting.get("kind"), "frameless.fitting.kind")
        try:
            kind = FramelessFittingKind(kind_raw)
        except ValueError as error:
            raise InvalidEngineRequest(
                "frameless fitting kind must be one of "
                + ", ".join(k.value for k in FramelessFittingKind)
            ) from error
        fittings.append(
            FramelessFitting(
                kind=kind,
                sku=_require_str(fitting.get("sku"), "frameless.fitting.sku"),
                qty=_positive_qty(fitting.get("qty", 1), "frameless.fitting.qty"),
            )
        )

    raw_edges = raw.get("exposed_edges")
    exposed_edges = None
    if raw_edges is not None:
        if not isinstance(raw_edges, list) or not raw_edges:
            raise InvalidEngineRequest(
                "frameless.exposed_edges must be a non-empty array of sides"
            )
        exposed_edges = [
            _parse_edge_side(edge, "frameless.exposed_edges[]") for edge in raw_edges
        ]

    try:
        return FramelessSpec(
            supports=supports, fittings=fittings, exposed_edges=exposed_edges
        )
    except ValueError as error:
        raise InvalidEngineRequest("Invalid module frameless spec") from error


class InvalidColorCombination(InvalidEngineRequest):
    """A rejected finish pair — the engine's declared reason (es-CL) is
    user-facing: it names the faces and the rule, so it flows to the API
    error detail under its own contract code, never a generic validation."""

    def __init__(self, detail: str, *, reason: str) -> None:
        super().__init__(detail)
        self.reason = reason


def color_selection_from_api(
    *,
    color: str,
    color_exterior: str | None,
    params: SystemParams,
) -> ColorSelection:
    """The requested finish pair validated against the declared catalog (D05).

    ``color`` is the interior face; ``color_exterior`` defaults to it when
    absent — a request without the field behaves exactly like the pre-D05
    single-finish contract. Every impossible combination surfaces the
    engine's declared reason, never a silent coercion.
    """
    try:
        return resolve_color_selection(
            params,
            interior_code=color,
            exterior_code=color_exterior or color,
        )
    except ColorCombinationError as error:
        raise InvalidColorCombination(str(error), reason=error.code) from error


def normalized_root_from_api(
    *,
    parametric_tree: object,
    nominal_width_mm: Decimal,
    nominal_height_mm: Decimal,
    color: str,
    color_exterior: str | None = None,
    params: SystemParams,
) -> ParametricNode:
    color_selection_from_api(
        color=color, color_exterior=color_exterior, params=params
    )

    root = parse_parametric_node(parametric_tree)
    if root.width_mm is not None and root.width_mm != nominal_width_mm:
        raise InvalidEngineRequest("nominal_width_mm conflicts with parametric_tree")
    if root.height_mm is not None and root.height_mm != nominal_height_mm:
        raise InvalidEngineRequest("nominal_height_mm conflicts with parametric_tree")
    root = root.model_copy(
        update={"width_mm": nominal_width_mm, "height_mm": nominal_height_mm}
    )
    return root


def calculate_from_api(
    *, parametric_tree: object, nominal_width_mm: Decimal, nominal_height_mm: Decimal,
    color: str, color_exterior: str | None = None, params: SystemParams,
) -> EngineResult:
    selection = color_selection_from_api(
        color=color, color_exterior=color_exterior, params=params
    )
    root = normalized_root_from_api(
        parametric_tree=parametric_tree, nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm, color=color,
        color_exterior=color_exterior, params=params,
    )
    try:
        return calculate_geometry(root, params, color_selection=selection)
    except NotImplementedError as error:
        raise UnsupportedEngineContract(str(error)) from error
    except ValueError as error:
        raise InvalidEngineRequest(str(error)) from error


_PRODUCT_FIELDS = {"version", "assembly"}
_ASSEMBLY_FIELDS = {"modules", "couplings"}
_MODULE_FIELDS = {
    "id", "width_mm", "height_mm", "tree", "contour", "frameless",
}
_COUPLING_FIELDS = {
    "id",
    "angle_deg",
    "coupler_profile_sku",
    "kind",
    "modules",
    "edges",
}


def _require_dict(payload: object, field_name: str) -> dict[str, object]:
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise InvalidEngineRequest(f"{field_name} must be an object")
    return cast(dict[str, object], payload)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidEngineRequest(f"{field_name} must be a string")
    return value


def parse_product_model(payload: object) -> ProductModel:
    raw = _require_dict(payload, "product")
    unexpected = set(raw) - _PRODUCT_FIELDS
    if unexpected:
        raise InvalidEngineRequest(
            f"product contains unsupported fields: {sorted(unexpected)}"
        )
    if raw.get("version") != "product-v2":
        raise InvalidEngineRequest("product.version must be 'product-v2'")

    assembly = _require_dict(raw.get("assembly"), "product.assembly")
    unexpected = set(assembly) - _ASSEMBLY_FIELDS
    if unexpected:
        raise InvalidEngineRequest(
            f"product.assembly contains unsupported fields: {sorted(unexpected)}"
        )
    raw_modules = assembly.get("modules")
    raw_couplers = assembly.get("couplings", [])
    if not isinstance(raw_modules, list) or not raw_modules:
        raise InvalidEngineRequest("product.assembly.modules must be a non-empty array")
    if not isinstance(raw_couplers, list):
        raise InvalidEngineRequest("product.assembly.couplings must be an array")

    modules: list[ProductModule] = []
    seen_ids: set[str] = set()
    for item in raw_modules:
        module = _require_dict(item, "module")
        unexpected = set(module) - _MODULE_FIELDS
        if unexpected:
            raise InvalidEngineRequest(
                f"module contains unsupported fields: {sorted(unexpected)}"
            )
        module_id = _require_str(module.get("id"), "module.id")
        if "|" in module_id:
            raise InvalidEngineRequest(
                "module ids cannot contain '|' (reserved as BOM key separator)"
            )
        if module_id in seen_ids:
            raise InvalidEngineRequest("module ids must be unique")
        seen_ids.add(module_id)
        width_mm = _decimal_string(module.get("width_mm"), "module.width_mm")
        height_mm = _decimal_string(
            module.get("height_mm"), "module.height_mm"
        )
        contour = parse_contour(module.get("contour"))
        if contour is not None:
            xs = [vertex.x_mm for vertex in contour.vertices]
            ys = [vertex.y_mm for vertex in contour.vertices]
            # The contour is module-local: its vertex bounding box IS the
            # nominal footprint (arc apexes may overshoot it). A mismatched
            # or translated bbox would conflict with plan layout and labels.
            if (
                min(xs) != Decimal("0")
                or min(ys) != Decimal("0")
                or max(xs) - min(xs) != width_mm
                or max(ys) - min(ys) != height_mm
            ):
                raise InvalidEngineRequest(
                    "contour vertices must be zero-based and bound "
                    "module.width_mm x module.height_mm"
                )
        modules.append(
            ProductModule(
                id=module_id,
                width_mm=width_mm,
                height_mm=height_mm,
                contour=contour,
                frameless=parse_frameless(module.get("frameless")),
                tree=parse_parametric_node(module.get("tree")),
            )
        )

    couplings: list[CouplingDef] = []
    seen_coupling_ids: set[str] = set()
    for item in raw_couplers:
        coupling = _require_dict(item, "coupling")
        unexpected = set(coupling) - _COUPLING_FIELDS
        if unexpected:
            raise InvalidEngineRequest(
                f"coupling contains unsupported fields: {sorted(unexpected)}"
            )
        sku = coupling.get("coupler_profile_sku")
        if sku is not None and not isinstance(sku, str):
            raise InvalidEngineRequest("coupler_profile_sku must be a string")
        coupling_id = _require_str(coupling.get("id"), "coupling.id")
        if "|" in coupling_id:
            raise InvalidEngineRequest(
                "coupling ids cannot contain '|' (reserved as BOM key separator)"
            )
        if coupling_id in seen_coupling_ids:
            raise InvalidEngineRequest("coupling ids must be unique")
        seen_coupling_ids.add(coupling_id)
        kind_raw = coupling.get("kind")
        if kind_raw is not None and kind_raw not in ConnectionKind._value2member_map_:
            raise InvalidEngineRequest(
                "coupling.kind must be one of "
                + ", ".join(member.value for member in ConnectionKind)
            )
        modules_raw = coupling.get("modules")
        if modules_raw is not None:
            if (
                not isinstance(modules_raw, list)
                or len(modules_raw) != 2
                or not all(isinstance(m, str) for m in modules_raw)
            ):
                raise InvalidEngineRequest(
                    "coupling.modules must be an array of two module ids"
                )
        edges_raw = coupling.get("edges")
        if edges_raw is not None:
            if (
                not isinstance(edges_raw, list)
                or len(edges_raw) != 2
                or any(e not in EdgeSide._value2member_map_ for e in edges_raw)
            ):
                raise InvalidEngineRequest(
                    "coupling.edges must be two sides from "
                    + ", ".join(side.value for side in EdgeSide)
                )
        couplings.append(
            CouplingDef(
                id=coupling_id,
                angle_deg=_decimal_string(
                    coupling.get("angle_deg") if "angle_deg" in coupling else "0",
                    "coupling.angle_deg",
                ),
                coupler_profile_sku=cast(str | None, sku),
                kind=(
                    ConnectionKind(kind_raw)
                    if kind_raw is not None
                    else ConnectionKind.INLINE
                ),
                modules=cast(list[str] | None, modules_raw),
                edges=cast(
                    list[EdgeSide] | None,
                    [EdgeSide(e) for e in edges_raw]
                    if edges_raw is not None
                    else None,
                ),
            )
        )

    try:
        return ProductModel(
            version=cast(Literal["product-v2"], "product-v2"),
            assembly=CoupledAssembly(modules=modules, couplings=couplings),
        )
    except ValueError as error:
        raise InvalidEngineRequest("Invalid product model") from error


def evaluate_assembly_from_api(
    *,
    product: object,
    color: str,
    color_exterior: str | None = None,
    params: SystemParams,
    coupler_articles: dict[str, EffectiveProfileArticle] | None = None,
) -> ProductEvaluation:
    selection = color_selection_from_api(
        color=color, color_exterior=color_exterior, params=params
    )
    model = (
        product
        if isinstance(product, ProductModel)
        else parse_product_model(product)
    )
    return evaluate_product(
        model,
        params,
        coupler_articles=coupler_articles,
        color_selection=selection,
    )


def is_product_tree(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("version") == "product-v2"
    )


def engine_result_from_api(
    *,
    tree: object,
    color: str,
    color_exterior: str | None = None,
    params: SystemParams,
    nominal_width_mm: Decimal | None = None,
    nominal_height_mm: Decimal | None = None,
    coupler_articles: dict[str, EffectiveProfileArticle] | None = None,
) -> EngineResult:
    """Persisted-design evaluator shared by saving, pricing, and documentary checks.

    Classic trees evaluate directly; product-v2 assemblies must evaluate VALID —
    a partial BOM is never authoritative downstream.
    """
    if is_product_tree(tree):
        evaluation = evaluate_assembly_from_api(
            product=tree,
            color=color,
            color_exterior=color_exterior,
            params=params,
            coupler_articles=coupler_articles or {},
        )
        if evaluation.status.value != "VALID" or evaluation.bom is None:
            raise UnsupportedEngineContract(
                "assembly is not manufacturing-complete"
            )
        return evaluation.bom
    if nominal_width_mm is None or nominal_height_mm is None:
        raise InvalidEngineRequest("classic designs require nominal dimensions")
    return calculate_from_api(
        parametric_tree=tree,
        nominal_width_mm=nominal_width_mm,
        nominal_height_mm=nominal_height_mm,
        color=color,
        color_exterior=color_exterior,
        params=params,
    )
