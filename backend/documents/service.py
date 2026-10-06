"""Atomic APPLIED-pricing freeze into immutable documentary revisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import ceil
from typing import Mapping, TypeVar
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import connection

from dekopen_engine.cutting import MissingStockAuthority
from dekopen_engine.documentary_canonical import (
    DOCUMENTARY_CANONICAL_VERSION,
    bom_hash_v1,
    documentary_canonical_json_v1,
    numeric_collapsed,
    same_documentary_value,
    snapshot_sha256_v1,
)
from dekopen_engine.geometry import GeometryComputation, compute_geometry
from dekopen_engine.inspection_models import (
    InspectionMode,
    InspectorConfig,
    InspectorInput,
    InspectorResult,
    InspectorSeverity,
    RuleEvaluationStatus,
)
from dekopen_engine.inspector import inspect
from dekopen_engine.manufacturing import (
    HandleIntentV1,
    HandleRequirementPolicyV1,
    ManufacturingFactsV1,
    ManufacturingPlacementPolicyV1,
    VerticalReference,
    project_manufacturing_facts_v1,
)
from dekopen_engine.manufacturing_trace import (
    GeometryManufacturingTraceV1,
    PlacementDomain,
    SemanticLeafTraceV1,
)
from dekopen_engine.finishes import (
    ColorCombinationError,
    resolve_color,
    resolve_color_selection,
)
from dekopen_engine.models import BayOpeningType, EngineResult
from dekopen_engine.openings import leaf_policy_opening_candidates
from dekopen_engine.product import (
    contour_module_computation,
    frameless_module_computation,
)
from dekopen_engine.purchasing import (
    FittingSelectionV1,
    HardwareSelectionV1,
    PositionPurchaseInputV1,
    project_purchase_requirements_v1,
)
from dekopen_engine.snapshot import calculation_hash, result_payload
from engine_api.adapter import (
    evaluate_assembly_from_api,
    normalized_root_from_api,
    parse_product_model,
)
from engine_api.cutting_repository import CuttingRepository, steel_color_map
from engine_api.inspection_repository import InspectorAuthorities, InspectorRepository
from engine_api.repository import SystemParamsRepository
from pricing.repository import commercial_backend
from production.service import process_facts_snapshot
from projects.measurement import resolve_position_measurement

from documents.repository import (
    DocumentaryError,
    PurchaseAuthorities,
    _handle_policy,
    _placement_policy,
    accessory_schedule,
    decoded,
    documentary_backend,
    glass_polishing,
    handle_intents,
    json_text,
    load_manufacturing_policies,
    load_purchase_authorities,
    one,
    rows,
    structural_inputs,
    workshop_annotations,
)

D = Decimal
T = TypeVar("T")


def _json_object(value: object, code: str) -> dict[str, object]:
    parsed = decoded(value)
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise DocumentaryError(code)
    return parsed


def _json_array(value: object, code: str) -> list[object]:
    parsed = decoded(value)
    if not isinstance(parsed, list):
        raise DocumentaryError(code)
    return parsed


def _indexed_amounts(value: object, code: str) -> dict[int, Decimal]:
    if not isinstance(value, list):
        raise DocumentaryError(code)
    result: dict[int, Decimal] = {}
    try:
        for pair in value:
            if not isinstance(pair, list) or len(pair) != 2:
                raise DocumentaryError(code)
            index = int(pair[0])
            if index in result:
                raise DocumentaryError(code)
            result[index] = D(str(pair[1]))
    except (TypeError, ValueError) as error:
        if isinstance(error, DocumentaryError):
            raise
        raise DocumentaryError(code) from error
    return result


def _stored_money(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _pricing_state_matches(
    project: dict[str, object], positions: list[dict[str, object]],
    request: dict[str, object], snapshot: dict[str, object], result: dict[str, object],
) -> None:
    costs = _indexed_amounts(snapshot.get("cost_lines"), "invalid_applied_pricing_snapshot")
    prices = _indexed_amounts(result.get("lines"), "invalid_applied_pricing_result")
    indexes = {int(position["position_index"]) for position in positions}
    if set(costs) != indexes or set(prices) != indexes:
        raise DocumentaryError("applied_pricing_binding_mismatch")
    discount = D(str(request.get("discount_pct")))
    for position in positions:
        index = int(position["position_index"])
        if (
            D(str(position["cost_net"])) != _stored_money(costs[index])
            or D(str(position["price_net"])) != _stored_money(prices[index])
            or D(str(position["discount_pct"])) != discount
        ):
            raise DocumentaryError("applied_pricing_binding_mismatch")
    expected_cost = _stored_money(sum(costs.values(), D("0")))
    expected_net = _stored_money(D(str(result.get("project_net"))))
    expected_tax = _stored_money(D(str(result.get("project_tax"))))
    expected_gross = _stored_money(D(str(result.get("project_gross"))))
    if (
        D(str(project["total_cost_net"])) != expected_cost
        or D(str(project["total_price_net"])) != expected_net
        or D(str(project["total_price_tax"])) != expected_tax
        or D(str(project["total_price_gross"])) != expected_gross
    ):
        raise DocumentaryError("applied_pricing_binding_mismatch")


def _module_scoped(
    items: list[T], module_id: str | None, *id_fields: str
) -> list[T]:
    """Items whose ids are namespaced "<module_id>|<id>" belong to one module;
    feed each module's classic computation only its own, prefix stripped."""
    if module_id is None:
        return items
    prefix = f"{module_id}|"
    scoped: list[T] = []
    for item in items:
        anchor = getattr(item, id_fields[0], None)
        if not isinstance(anchor, str) or not anchor.startswith(prefix):
            continue
        updates = {}
        for field in id_fields:
            value = getattr(item, field, None)
            updates[field] = (
                value[len(prefix):]
                if isinstance(value, str) and value.startswith(prefix)
                else value
            )
        scoped.append(item.model_copy(update=updates))
    return scoped


def _opening_trace_key(leaf) -> str:
    """The leaf's emitted opening key — an enum member on the legacy path,
    a canonical string on the spec path (D03)."""
    opening = leaf.opening_type
    return str(opening.value) if isinstance(opening, BayOpeningType) else str(opening)


def _handle_rules_for_leaf(
    slots: list,
    leaf,
) -> list:
    """Mirror of the engine's handle-rule matching (policy slot → leaf):
    opening_type + leaf_slot filter, then the door-handedness pin — a rule
    carrying leaf_handedness applies only to leaves whose declared
    handedness matches, and pinned rules win over wildcards when both
    match. Keeping the predicate in one place keeps the preparation UI and
    the freeze-time projection agreeing on which intents are required."""
    candidates = leaf_policy_opening_candidates(_opening_trace_key(leaf))
    matching = [
        rule
        for rule in slots
        if str(rule.opening_type) in candidates
        and (rule.leaf_slot is None or rule.leaf_slot == leaf.leaf_slot)
        and (rule.leaf_handedness is None or rule.leaf_handedness == leaf.door_handedness)
    ]
    if leaf.door_handedness is not None:
        # Pinned rules win per domain slot only — a wildcard rule for a
        # slot with no pinned entry must still match.
        pinned_slots = {
            rule.handle_domain_slot
            for rule in matching
            if rule.leaf_handedness == leaf.door_handedness
        }
        matching = [
            rule
            for rule in matching
            if rule.leaf_handedness is not None
            or rule.handle_domain_slot not in pinned_slots
        ]
    return matching


def _missing_handle_intents(
    trace: GeometryManufacturingTraceV1,
    handle_policy: HandleRequirementPolicyV1,
    intents: list[HandleIntentV1],
) -> bool:
    available = {
        (item.bay_id, item.leaf_id, item.handle_domain_slot) for item in intents
    }
    door_rules_exist = any(
        str(rule.opening_type).startswith("DOOR") for rule in handle_policy.slots
    )
    for leaf in trace.leaves:
        if (
            door_rules_exist
            and _opening_trace_key(leaf).startswith("DOOR")
            and leaf.door_handedness is None
        ):
            # A door without declared handedness is incomplete — the
            # policy cannot legally mount its handle (pinned rules don't
            # match, and there is no wildcard to guess with).
            return True
        for rule in _handle_rules_for_leaf(handle_policy.slots, leaf):
            if (
                leaf.bay_id,
                leaf.leaf_id,
                rule.handle_domain_slot,
            ) not in available:
                return True
    return False


def _leaf_rects(
    leaf: SemanticLeafTraceV1,
    placement_authorities: list[tuple[str, ManufacturingPlacementPolicyV1]],
) -> list[dict[str, object]]:
    """Resolved leaf rectangle per placement option. The entered intent
    height is measured from the selected vertical reference; transforming the
    leaf-top mounting bounds into the input's own units requires the leaf's
    position inside the outer rectangle — which only the placement policy
    resolves for sliding leaves."""
    rects: list[dict[str, object]] = []
    for policy_id, policy in placement_authorities:
        if leaf.placement_domain is PlacementDomain.DIRECT:
            rect = leaf.direct_rect
            if rect is None:
                continue
            y_mm, height_mm = rect.y_mm, rect.height_mm
        else:
            offset = policy.sliding_leaf_offsets.get(leaf.leaf_slot)
            if offset is None:
                continue
            y_mm = leaf.reference_rect.y_mm + offset.y_mm
            height_mm = leaf.finished_height_mm
        rects.append(
            {
                "placement_policy_id": policy_id,
                "leaf_top_from_outer_top_mm": str(y_mm),
                "leaf_height_mm": str(height_mm),
            }
        )
    return rects


def _handle_policy_requirements(
    trace_leaves: list[dict[str, object]],
    handle_policy: HandleRequirementPolicyV1,
    placement_authorities: list[tuple[str, ManufacturingPlacementPolicyV1]],
) -> list[dict[str, object]]:
    """Leaf-matched handle requirements of a policy for the preparation UI:
    the editor needs to know which (bay, leaf) pairs need an intent and the
    policy bounds that govern it before a position can freeze completely."""
    requirements: list[dict[str, object]] = []
    door_rules = [
        rule
        for rule in handle_policy.slots
        if str(rule.opening_type).startswith("DOOR")
    ]
    for item in trace_leaves:
        leaf = item["leaf"]
        if (
            door_rules
            and _opening_trace_key(leaf).startswith("DOOR")
            and leaf.door_handedness is None
        ):
            # The door leaf needs handedness before any height intent can
            # land — surface that as an explicit row (no host side) instead
            # of letting the leaf look requirement-free and then failing
            # at freeze.
            requirements.append(
                {
                    "bay_id": item["bay_id"],
                    "leaf_id": item["leaf_id"],
                    "leaf_label": item["leaf_label"],
                    "opening_type": _opening_trace_key(leaf),
                    "handle_domain_slot": door_rules[0].handle_domain_slot,
                    "host_member_side": None,
                    "requires_handedness": True,
                    "outer_height_mm": str(item["nominal_height_mm"]),
                    "mounting_min_from_leaf_top_mm": str(
                        min(rule.mounting_min_from_leaf_top_mm for rule in door_rules)
                    ),
                    "mounting_max_from_leaf_top_mm": str(
                        max(rule.mounting_max_from_leaf_top_mm for rule in door_rules)
                    ),
                    "permitted_vertical_references": sorted(
                        {
                            reference.value
                            for rule in door_rules
                            for reference in rule.permitted_vertical_references
                        }
                    ),
                    "leaf_rects": _leaf_rects(leaf, placement_authorities),
                }
            )
            continue
        for rule in _handle_rules_for_leaf(handle_policy.slots, leaf):
            requirements.append(
                {
                    "bay_id": item["bay_id"],
                    "leaf_id": item["leaf_id"],
                    "leaf_label": item["leaf_label"],
                    "opening_type": _opening_trace_key(leaf),
                    "handle_domain_slot": rule.handle_domain_slot,
                    "host_member_side": rule.host_member_side.value,
                    "requires_handedness": False,
                    "outer_height_mm": str(item["nominal_height_mm"]),
                    "mounting_min_from_leaf_top_mm": str(
                        rule.mounting_min_from_leaf_top_mm
                    ),
                    "mounting_max_from_leaf_top_mm": str(
                        rule.mounting_max_from_leaf_top_mm
                    ),
                    "permitted_vertical_references": [
                        reference.value
                        for reference in rule.permitted_vertical_references
                    ],
                    "leaf_rects": _leaf_rects(leaf, placement_authorities),
                }
            )
    return requirements


def _synthesized_handle_intents(
    module_tree: object,
    trace: GeometryManufacturingTraceV1,
    intents: list[HandleIntentV1],
) -> list[HandleIntentV1]:
    """A bay's `handle_height_mm` is the editor's declared handle datum,
    measured up from the product's sill line — it IS product intent, not a
    legacy flag, so the freeze synthesizes the same intent the preparation
    UI would produce: one PRIMARY intent per leaf of that bay that does not
    already carry an explicit one. Explicit intents always win."""
    declared: dict[str, Decimal] = {}
    stack = [module_tree]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        value = node.get("handle_height_mm")
        if value is not None and isinstance(node.get("id"), str):
            try:
                declared[str(node["id"])] = Decimal(str(value))
            except InvalidOperation:
                pass
        children = node.get("children")
        if isinstance(children, list):
            stack.extend(children)
    if not declared:
        return intents
    covered = {
        (item.bay_id, item.leaf_id, item.handle_domain_slot) for item in intents
    }
    merged = list(intents)
    for leaf in trace.leaves:
        height = declared.get(leaf.bay_id)
        if height is None or (leaf.bay_id, leaf.leaf_id, "PRIMARY") in covered:
            continue
        merged.append(HandleIntentV1(
            bay_id=leaf.bay_id,
            leaf_id=leaf.leaf_id,
            handle_domain_slot="PRIMARY",
            requested_height_mm=height,
            vertical_reference=VerticalReference.OUTER_BOTTOM,
        ))
    return merged


# Scale-free numeric collapse lives in
# `dekopen_engine.documentary_canonical` — the live-vs-frozen compare in
# projects.service applies the same normalization, so a canonical "16.00"
# BOM and a raw "16" dump of the same measurement never read as drift.
_numeric_collapsed = numeric_collapsed


def _same_documentary_value(left: object, right: object) -> bool:
    return same_documentary_value(left, right)


# Output-additive BOM keys: lists/fields the engine emits that a sealed
# snapshot may predate. D05 adds the finish identity + declared surcharges;
# D06 adds the measured extras sublines.
_BOM_ADDITIVE_KEYS = frozenset(
    {"fittings", "finish_key", "finish_label", "finish_class", "color_surcharges", "extra_lines"}
)
_PIECE_ADDITIVE_KEYS = {
    # Output-additive metadata the model gained after BOMs were already
    # sealed — dropping them when a stored snapshot lacks them keeps old
    # positions comparable; when the snapshot carries them they stay
    # compared, so a real value change still reads as drift.
    "glasses": frozenset(
        {
            "glass_spec",
            "article_sku",
            "thickness_net_mm",
            "weight_kg",
            "shape",
            "area_m2",
            "exposed_edges",
        }
    ),
    "profile_cuts": frozenset({"sagitta_mm", "origin"}),
    "reinforcements": frozenset({"sagitta_mm"}),
    # D06: accessory cut/fitting pieces carry origin=EXTRA so the cut plan
    # and OT BOM can tell them apart — sealed pre-D06 BOMs never had it.
    "fittings": frozenset({"origin"}),
    # D04: resolved class label, sellable selections and declared machining
    # ride the emitted item — snapshots sealed before them must not flag.
    "hardware_items": frozenset(
        {
            "class_label",
            "handle_model_sku",
            "handle_model_name",
            "handle_color_sku",
            "handle_color_name",
            "option_skus",
            "option_names",
            "handle_height_mm",
            "cost_clp",
            "weight_kg",
            "price_delta_clp",
            "price_deltas",
            "machining",
        }
    ),
}

# Contents-level additive keys (D04): the emitted component line carries the
# resolved expansion plus its declared rules — `category` set the precedent.
_HARDWARE_CONTENTS_ADDITIVE = frozenset(
    {
        "category",
        "qty_rule",
        "cut_rule",
        "weight_kg",
        "cost_clp",
        "machining",
        "length_mm",
        "option_sku",
    }
)


def _drop_bom_keys(
    payload: Mapping[str, object],
    bom_keys: frozenset[str],
    piece_keys: Mapping[str, frozenset[str]],
    nested_keys: Mapping[str, tuple[str, frozenset[str]]] | None = None,
) -> dict[str, object]:
    """Payload with the given additive keys removed at BOM level and per
    piece-list item — the preimage a stored identity hash was computed on.
    ``nested_keys`` maps a piece list to ``(inner_list, keys)`` so additive
    fields one level deeper (e.g. component rows inside hardware contents)
    can be stripped the same way."""
    bom = {key: value for key, value in payload.items() if key not in bom_keys}
    for piece_list, keys in piece_keys.items():
        items = bom.get(piece_list)
        if not isinstance(items, list):
            continue
        bom = {
            **bom,
            piece_list: [
                {
                    key: value
                    for key, value in item.items()
                    if key not in keys
                }
                if isinstance(item, dict)
                else item
                for item in items
            ],
        }
    for piece_list, (inner_list, keys) in (nested_keys or {}).items():
        items = bom.get(piece_list)
        if not isinstance(items, list):
            continue
        bom = {
            **bom,
            piece_list: [
                {
                    **item,
                    inner_list: [
                        {
                            key: value
                            for key, value in component.items()
                            if key not in keys
                        }
                        if isinstance(component, dict)
                        else component
                        for component in item[inner_list]
                    ],
                }
                if isinstance(item, dict) and isinstance(item.get(inner_list), list)
                else item
                for item in items
            ],
        }
    return bom


def _calculation_identity_hashes(
    request: Mapping[str, object], result: EngineResult, *,
    legacy_request: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Current plus prior-era hashes for one engine result. Documentary
    inputs seal ``hash(request, payload-at-save-time)`` — every era that
    appended output fields (frameless fittings/exposed edges, contour
    shape/sagitta, glass spec/article) must project the current payload back
    to that era's preimage or positions sealed then can never freeze again."""
    payload = result_payload(result)
    # D06 era: emitted extras before `extra_lines` existed and pieces
    # before `origin` marked EXTRA accessories.
    era_d06 = _drop_bom_keys(
        payload,
        frozenset({"extra_lines"}),
        {
            "profile_cuts": frozenset({"origin"}),
            "fittings": frozenset({"origin"}),
        },
    )
    # D05 era: positions sealed before the finish identity + color
    # surcharges existed never carried them — project back so their
    # stored hash still validates.
    era_d05 = _drop_bom_keys(
        era_d06,
        frozenset(
            {"finish_key", "finish_label", "finish_class", "color_surcharges"}
        ),
        {},
    )
    # D04 era: emitted hardware items before the class/selection/expansion
    # fields existed. Projects the current payload back, then era9 drops
    # `contents.category` on top as before.
    era_d04 = _drop_bom_keys(
        era_d05,
        frozenset(),
        {"hardware_items": _PIECE_ADDITIVE_KEYS["hardware_items"]},
        {"hardware_items": ("contents", _HARDWARE_CONTENTS_ADDITIVE)},
    )
    era9 = _drop_bom_keys(
        era_d04,
        frozenset(),
        {},
        {"hardware_items": ("contents", frozenset({"category"}))},
    )
    era94 = _drop_bom_keys(
        era9, frozenset({"fittings"}), {"glasses": frozenset({"exposed_edges"})}
    )
    era92 = _drop_bom_keys(
        era94,
        frozenset(),
        {
            "glasses": frozenset({"shape"}),
            "profile_cuts": frozenset({"sagitta_mm"}),
            "reinforcements": frozenset({"sagitta_mm"}),
        },
    )
    era86 = _drop_bom_keys(
        era92,
        frozenset(),
        {"glasses": frozenset({"glass_spec", "article_sku"})},
    )
    # D05: positions sealed before per-face colors hashed the binary
    # request {"color": "WHITE"|"FOILED"}. When the canonical request
    # differs (real catalog codes or an explicit bicolor exterior), the
    # legacy form stays a valid alternative preimage.
    requests = [request]
    if isinstance(legacy_request, Mapping) and legacy_request != request:
        requests.append(legacy_request)
    return tuple(
        calculation_hash(req, payload_era)
        for req in requests
        for payload_era in (payload, era_d06, era_d05, era_d04, era9, era94, era92, era86)
    )


def _piece_identity(item: Mapping[str, object]) -> tuple[object, ...]:
    # Numeric fields collapse scale-free ("1500.00" == "1500"): the stored
    # snapshot serializes canonical 2dp while the priced one rides the raw
    # model_dump, and a missed identity match would drop additive keys on
    # only one side — reading as binding drift that isn't there.
    return tuple(
        numeric_collapsed(value)
        for value in (
            item.get("bay_id"),
            item.get("leaf_id"),
            item.get("role"),
            item.get("sku") or item.get("parent_profile_sku"),
            item.get("length_mm"),
            item.get("width_mm"),
            item.get("height_mm"),
            item.get("angle_left"),
            item.get("angle_right"),
            item.get("qty"),
        )
    )


def _without_additive_bom_fields(bom: object, reference: object = None) -> object:
    # glass_spec/article_sku and friends are output-additive metadata derived
    # from the same inputs; the authoritative values are sealed in
    # computation.infills. BOMs persisted before the fields existed must not
    # read as drift. With `reference` (the older stored/priced snapshot) a key
    # is dropped only when that snapshot lacks it or carries null — a non-null
    # value in the snapshot stays on both sides, so real drift still flags.
    # Both sides of a comparison are normalized against the same snapshot.
    if not isinstance(bom, dict):
        return bom
    ref = reference if isinstance(reference, dict) else None
    bom = {
        key: value
        for key, value in bom.items()
        if key not in _BOM_ADDITIVE_KEYS or (ref is not None and ref.get(key) is not None)
    }
    for piece_list, keys in _PIECE_ADDITIVE_KEYS.items():
        items = bom.get(piece_list)
        if not isinstance(items, list):
            continue
        ref_items: dict[tuple[object, ...], Mapping[str, object]] = {}
        if ref is not None and isinstance(ref.get(piece_list), list):
            ref_items = {
                _piece_identity(item): item
                for item in ref[piece_list]
                if isinstance(item, dict)
            }
        bom = {
            **bom,
            piece_list: [
                {
                    key: value
                    for key, value in item.items()
                    if key not in keys
                    or ref_items.get(_piece_identity(item), {}).get(key) is not None
                }
                if isinstance(item, dict)
                else item
                for item in items
            ],
        }
    return _without_component_category(bom, ref)


def _without_component_category(bom: object, ref: object) -> object:
    # `category` on hardware contents is additive (§9): a snapshot sealed
    # before it existed must not read the declared kind as drift — and D04
    # adds the resolved-expansion keys to the same rule (qty_rule, cut_rule,
    # unit mass/cost, cut length, option provenance, machining). Contents
    # match their snapshot counterparts by (sku, name, qty, unit); the
    # hardware item itself matches by (bay, leaf, kit_sku, qty).
    if not isinstance(bom, dict):
        return bom
    items = bom.get("hardware_items")
    if not isinstance(items, list):
        return bom
    ref_items: dict[tuple[object, ...], Mapping[str, object]] = {}
    if isinstance(ref, dict) and isinstance(ref.get("hardware_items"), list):
        ref_items = {
            (
                item.get("bay_id"),
                item.get("leaf_id"),
                item.get("kit_sku"),
                item.get("qty"),
            ): item
            for item in ref["hardware_items"]
            if isinstance(item, dict)
        }

    def ref_has_key(
        key: str, item: Mapping[str, object], component: Mapping[str, object]
    ) -> bool:
        ref_item = ref_items.get(
            (item.get("bay_id"), item.get("leaf_id"), item.get("kit_sku"), item.get("qty"))
        )
        if not isinstance(ref_item, dict) or not isinstance(ref_item.get("contents"), list):
            return False
        identity = (
            component.get("sku"),
            component.get("name"),
            component.get("qty"),
            component.get("unit"),
        )
        return any(
            isinstance(other, dict)
            and (other.get("sku"), other.get("name"), other.get("qty"), other.get("unit"))
            == identity
            and other.get(key) is not None
            for other in ref_item["contents"]
        )

    return {
        **bom,
        "hardware_items": [
            {
                **item,
                "contents": [
                    {
                        key: value
                        for key, value in component.items()
                        if key not in _HARDWARE_CONTENTS_ADDITIVE
                        or ref_has_key(key, item, component)
                    }
                    if isinstance(component, dict)
                    else component
                    for component in item["contents"]
                ],
            }
            if isinstance(item, dict) and isinstance(item.get("contents"), list)
            else item
            for item in items
        ],
    }


def _unique_by(items: list[T], attribute: str, code: str) -> list[T]:
    result: dict[str, T] = {}
    for item in items:
        identity = str(getattr(item, attribute))
        previous = result.get(identity)
        if previous is not None and previous != item:
            raise DocumentaryError(code)
        result[identity] = item
    return [result[key] for key in sorted(result)]


def _color_option_detail(option) -> dict[str, object]:
    """D05: the resolved finish's sealed render record — what the doc and
    portal color the faces with, and what the buyer reads on the quote."""
    return {
        "code": option.code,
        "name": option.name,
        "kind": option.kind.value,
        "manufacturer_code": option.manufacturer_code,
        "render_color": option.render_color,
        "render_texture": option.render_texture,
        "dark": option.dark,
    }


def _documentary_calculation_requests(
    *, system_id: object, tree: dict[str, object], width_mm: Decimal,
    height_mm: Decimal, color_interior: str, color_exterior: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """D05: canonical request preimage + the binary-era request a legacy
    position sealed. The canonical form carries the interior code and the
    exterior code only when it differs — exactly what the design pipeline
    hashes on write/read."""
    request: dict[str, object] = {
        "system_id": str(system_id),
        "parametric_tree": tree,
        "nominal_width_mm": width_mm,
        "nominal_height_mm": height_mm,
        "color": color_interior,
    }
    if color_exterior != color_interior:
        request["color_exterior"] = color_exterior
    legacy = {
        key: value for key, value in request.items() if key != "color_exterior"
    }
    legacy["color"] = (
        "WHITE" if color_interior == "WHITE" and color_exterior == "WHITE"
        else "FOILED"
    )
    return request, legacy


def _position_calculations(
    *,
    tree: dict[str, object],
    width_mm: Decimal,
    height_mm: Decimal,
    color: str,
    color_exterior: str | None = None,
    params: object,
    system_id: UUID,
    org_id: UUID,
) -> tuple[list[tuple[str | None, GeometryComputation, dict[str, object]]], EngineResult]:
    """Classic per-module geometry+trace for one persisted position.

    Returns (calculations, result): classic positions compute once with a
    ``None`` module id; product-v2 assemblies evaluate for the BOM and each
    module recomputes on its own tree, the ``module.id`` becoming the
    ``"<module_id>|<id>"`` namespace used by the persisted BOM.
    """
    calculations: list[tuple[str | None, GeometryComputation, dict[str, object]]] = []
    is_assembly = isinstance(tree, dict) and tree.get("version") == "product-v2"
    # D05: the persisted interior/exterior codes resolve once here — the
    # combination rules (bicolor, faces, pair) are the engine's, and an
    # invalid pair must not freeze into documentary authority.
    try:
        color_selection = resolve_color_selection(
            params, interior_code=color, exterior_code=color_exterior or color
        )
    except ColorCombinationError as error:
        raise DocumentaryError(error.code, detail=str(error)) from error
    coupler_articles = (
        SystemParamsRepository().load_coupler_articles(system_id, org_id)
        if is_assembly
        else {}
    )
    if is_assembly:
        product = parse_product_model(tree)
        evaluation = evaluate_assembly_from_api(
            product=product,
            color=color,
            color_exterior=color_exterior,
            params=params,
            coupler_articles=coupler_articles,
        )
        if evaluation.status.value != "VALID" or evaluation.bom is None:
            raise DocumentaryError("documentary_geometry_incomplete")
        result = evaluation.bom
        module_specs = [(module.id, module) for module in product.assembly.modules]
    else:
        result = None
        module_specs = [(None, None)]
    for module_id, module in module_specs:
        if module is not None and module.contour is not None:
            computation, _contour_issues = contour_module_computation(
                module, params, color_selection=color_selection
            )
            if computation is None:
                raise DocumentaryError("documentary_geometry_incomplete")
        elif module is not None and module.frameless is not None:
            computation, _frameless_issues = frameless_module_computation(
                module, coupler_articles=coupler_articles
            )
            if computation is None:
                raise DocumentaryError("documentary_geometry_incomplete")
        else:
            module_root = normalized_root_from_api(
                parametric_tree=(
                    module.tree.model_dump(mode="json") if module is not None else tree
                ),
                nominal_width_mm=module.width_mm if module is not None else width_mm,
                nominal_height_mm=(
                    module.height_mm if module is not None else height_mm
                ),
                color=color,
                color_exterior=color_exterior,
                params=params,
            )
            computation = compute_geometry(
                module_root, params, diagnostic=True, color_selection=color_selection
            )
        if computation.result is None or computation.manufacturing_trace is None:
            raise DocumentaryError("documentary_geometry_incomplete")
        module_tree = module.tree.model_dump(mode="json") if module is not None else tree
        calculations.append((module_id, computation, module_tree))
        if not is_assembly:
            result = computation.result
    if result is None:
        raise DocumentaryError("documentary_geometry_incomplete")
    return calculations, result


def _valid_targets(
    calculations: list[tuple[str | None, GeometryComputation, dict[str, object]]],
) -> tuple[
    set[str],
    set[tuple[str, str | None]],
    set[str],
    set[tuple[str, str | None]],
]:
    """Valid bays, (bay, leaf) pairs, span ids and glass targets for a
    position, namespaced ``<module_id>|<id>`` exactly like the assembly BOM."""
    bays: set[str] = set()
    leaves: set[tuple[str, str | None]] = set()
    spans: set[str] = set()
    glass: set[tuple[str, str | None]] = set()
    for module_id, computation, _ in calculations:
        bays |= {
            f"{module_id}|{opening.bay_id}" if module_id else opening.bay_id
            for opening in computation.openings
        }
        leaves |= {
            (
                f"{module_id}|{leaf.bay_id}" if module_id else leaf.bay_id,
                f"{module_id}|{leaf.leaf_id}"
                if module_id and leaf.leaf_id is not None
                else leaf.leaf_id,
            )
            for leaf in computation.leaves
        }
        spans |= {
            f"{module_id}|{span.target_id}" if module_id else span.target_id
            for span in computation.spans
        }
        trace = computation.manufacturing_trace
        glass |= {
            (
                f"{module_id}|{infill.bay_id}" if module_id else infill.bay_id,
                f"{module_id}|{infill.leaf_id}"
                if module_id and infill.leaf_id is not None
                else infill.leaf_id,
            )
            for infill in (trace.infills if trace else [])
            if infill.kind == "GLASS"
        }
    return bays, leaves, spans, glass


def _workshop_targets(
    calculations: list[tuple[str | None, GeometryComputation, dict[str, object]]],
    trace_leaves: list[dict[str, object]],
) -> dict[str, object]:
    """Ordered annotation/purchase targets for the emission-prep editors —
    ids namespaced ``<module_id>|<id>`` exactly like the saved inputs."""
    leaf_labels = {
        (item["bay_id"], item["leaf_id"]): str(item["leaf_label"]) for item in trace_leaves
    }
    bays: list[dict[str, object]] = []
    leaves: list[dict[str, object]] = []
    spans: list[dict[str, object]] = []
    glass: list[dict[str, object]] = []
    for module_index, (module_id, computation, _) in enumerate(calculations, 1):
        prefix = f"{module_id}|" if module_id else ""
        unit = f"Unidad {module_index} · " if module_id else ""
        for index, opening in enumerate(computation.openings, 1):
            bays.append({
                "bay_id": f"{prefix}{opening.bay_id}",
                "label": f"{unit}Vano {index}",
                "width_mm": opening.width_mm,
            })
        for index, leaf in enumerate(computation.leaves, 1):
            leaf_id = (
                f"{prefix}{leaf.leaf_id}"
                if module_id and leaf.leaf_id is not None
                else leaf.leaf_id
            )
            leaves.append({
                "bay_id": f"{prefix}{leaf.bay_id}",
                "leaf_id": leaf_id,
                "leaf_label": leaf_labels.get(
                    (f"{prefix}{leaf.bay_id}", leaf_id), f"{unit}Hoja {index}"
                ),
            })
        for index, span in enumerate(computation.spans, 1):
            spans.append({
                "target_id": f"{prefix}{span.target_id}",
                "label": f"{unit}Travesaño {index}",
                "span_mm": span.span_mm,
            })
        trace = computation.manufacturing_trace
        glass_count = 0
        for infill in trace.infills if trace else []:
            if infill.kind != "GLASS":
                continue
            glass_count += 1
            bay_key = f"{prefix}{infill.bay_id}"
            leaf_key = (
                f"{prefix}{infill.leaf_id}"
                if module_id and infill.leaf_id is not None
                else infill.leaf_id
            )
            glass.append({
                "bay_id": bay_key,
                "leaf_id": leaf_key,
                "label": leaf_labels.get((bay_key, leaf_key), f"{unit}Vidrio {glass_count}"),
            })
    return {"bays": bays, "leaves": leaves, "spans": spans, "glass": glass}


def _seed_workshop_defaults(
    calculations: list[tuple[str | None, GeometryComputation, dict[str, object]]],
    existing: list[dict[str, object]],
    config: InspectorConfig,
) -> list[dict[str, object]]:
    """Prefill what the workshop would otherwise have to type for every emit:
    evenly spaced drains (R07), closing points within R08 spacing, the real
    opening as continuous width, WHITE finish, no coupler. The estimator sees
    and edits them — nothing is sealed silently — while true authorities
    (structural inertia, measured QC) stay unset."""
    keyed = {
        (str(item["bay_id"]), item.get("leaf_id"))
        for item in existing
        if isinstance(item, dict)
    }
    seeded: list[dict[str, object]] = []
    seeded_bay_rows: dict[str, dict[str, object]] = {}
    for module_id, computation, _ in calculations:
        prefix = f"{module_id}|" if module_id else ""
        for opening in computation.openings:
            bay_key = f"{prefix}{opening.bay_id}"
            if (bay_key, None) in keyed:
                continue
            drains: list[str] | None = None
            if opening.width_mm > config.R07.width_trigger_mm:
                count = int(config.R07.required_bottom_drains)
                drains = [
                    str((opening.width_mm * (index + 1) / (count + 1)).quantize(D("0.01")))
                    for index in range(count)
                ]
            bay_row: dict[str, object] = {
                "bay_id": bay_key,
                "leaf_id": None,
                "bottom_drain_holes_mm": drains,
                "closing_points_perimeter_mm": None,
                "continuous_width_mm": str(opening.width_mm.quantize(D("0.01"))),
                "finish_class": "WHITE",
                "has_coupler": False,
            }
            seeded.append(bay_row)
            seeded_bay_rows[bay_key] = bay_row
        for leaf in computation.leaves:
            bay_key = f"{prefix}{leaf.bay_id}"
            leaf_key = (
                f"{prefix}{leaf.leaf_id}"
                if module_id and leaf.leaf_id is not None
                else leaf.leaf_id
            )
            if (bay_key, leaf_key) in keyed:
                continue
            perimeter = (leaf.finished_width_mm + leaf.finished_height_mm) * 2
            count = max(2, ceil(perimeter / config.R08.max_spacing_mm))
            closing_points = [
                str((perimeter * index / count).quantize(D("0.01")))
                for index in range(count)
            ]
            if leaf_key is None:
                # A leaf with no leaf identity shares the bay-level target;
                # a second (bay, None) row would collide with it at freeze.
                bay_row = seeded_bay_rows.get(bay_key)
                if bay_row is not None and (
                    bay_row["closing_points_perimeter_mm"] is None
                ):
                    bay_row["closing_points_perimeter_mm"] = closing_points
                continue
            seeded.append({
                "bay_id": bay_key,
                "leaf_id": leaf_key,
                "bottom_drain_holes_mm": None,
                "closing_points_perimeter_mm": closing_points,
                "continuous_width_mm": None,
                "finish_class": None,
                "has_coupler": None,
            })
    return [*existing, *seeded]


def _seed_polishing_defaults(
    glass_targets: set[tuple[str, str | None]],
    existing: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Every glass piece gets a declared 'no polished edges' row unless the
    operator already chose something — declared coverage, not missing data."""
    keyed = {
        (str(item["bay_id"]), item.get("leaf_id"))
        for item in existing
        if isinstance(item, dict)
    }
    seeded = [
        {
            "schema_version": 1,
            "bay_id": bay_key,
            "leaf_id": leaf_key,
            "edges": {"top": False, "right": False, "bottom": False, "left": False},
        }
        for bay_key, leaf_key in sorted(glass_targets)
        if (bay_key, leaf_key) not in keyed
    ]
    return [*existing, *seeded]


def _measurement_evidence(org_id: UUID, position: dict[str, object]) -> dict[str, object]:
    """D07 sealed measurement block: vano record + applied rule + engine
    resolution as the estimator saw them at seal time. Everything here is
    JSON-safe for the snapshot (datetimes to ISO strings)."""
    evidence = resolve_position_measurement(org_id, position)
    confirmed_at = evidence.get("confirmed_at")
    if isinstance(confirmed_at, datetime):
        evidence["confirmed_at"] = confirmed_at.isoformat()
    return evidence


def _position_rows(project_id: UUID, org_id: UUID) -> list[dict[str, object]]:
    return rows(
        "SELECT position.*,input.id AS documentary_input_id,"
        "input.manufacturing_placement_policy_id,input.handle_requirement_policy_id,"
        "input.reinforcement_cut_policy_id,input.workshop_annotations::text,"
        "input.structural_inputs::text,input.glass_polishing::text,"
        "input.handle_intents::text,input.accessory_schedule::text,"
        "input.legacy_handle_migration_confirmed,input.calculation_hash AS documentary_calculation_hash,"
        "system.name AS system_name, system.is_demo AS system_is_demo, "
        "(SELECT json_agg(json_build_object("
        " 'opening_type', lim.opening_type,"
        " 'min_leaf_width_mm', lim.min_leaf_width_mm,"
        " 'max_leaf_width_mm', lim.max_leaf_width_mm,"
        " 'min_leaf_height_mm', lim.min_leaf_height_mm,"
        " 'max_leaf_height_mm', lim.max_leaf_height_mm,"
        " 'max_leaf_weight_kg', lim.max_leaf_weight_kg,"
        " 'max_aspect_ratio', lim.max_aspect_ratio,"
        " 'data_provenance', lim.data_provenance)) "
        "FROM public.system_typology_limits lim "
        "WHERE lim.system_id=position.system_id "
        "AND (lim.org_id IS NULL OR lim.org_id=position.org_id))::text "
        "AS system_limits "
        "FROM public.project_positions position "
        "JOIN public.position_documentary_inputs input "
        "ON input.position_id=position.id AND input.project_id=position.project_id "
        "AND input.org_id=position.org_id "
        "JOIN public.profile_systems system ON system.id=position.system_id "
        "WHERE position.project_id=%s AND position.org_id=%s "
        "ORDER BY position.position_index",
        [project_id, org_id],
    )


def _technical_bom(snapshot: dict[str, object]) -> dict[str, object]:
    values = snapshot.get("positions")
    if not isinstance(values, list):
        raise DocumentaryError("invalid_applied_pricing_snapshot")
    result: dict[str, object] = {}
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("position_id"), str):
            raise DocumentaryError("invalid_applied_pricing_snapshot")
        position_id = value["position_id"]
        if position_id in result or "bom" not in value:
            raise DocumentaryError("invalid_applied_pricing_snapshot")
        result[position_id] = value["bom"]
    return result


def _collect_purchase_authorities(
    existing: PurchaseAuthorities | None, following: PurchaseAuthorities
) -> PurchaseAuthorities:
    prior = existing or PurchaseAuthorities([], [], [], [], [])
    return PurchaseAuthorities(
        _unique_by(prior.stock_bindings + following.stock_bindings, "binding_id",
                   "physical_stock_authority_conflict"),
        _unique_by(prior.glass_mappings + following.glass_mappings, "authority_id",
                   "glass_purchase_authority_conflict"),
        _unique_by(prior.hardware_mappings + following.hardware_mappings, "authority_id",
                   "hardware_purchase_authority_conflict"),
        _unique_by(prior.panel_authorities + following.panel_authorities, "authority_id",
                   "panel_purchase_authority_conflict"),
        _unique_by(prior.fitting_mappings + following.fitting_mappings, "authority_id",
                   "fitting_purchase_authority_conflict"),
    )


def freeze_revision_a(
    *, org_id: UUID, actor_id: UUID, project_id: UUID,
    pricing_operation_id: UUID, confirmed: bool,
    allow_incomplete_workshop: bool = False,
) -> dict[str, object]:
    if not confirmed:
        raise DocumentaryError("documentary_freeze_confirmation_required")
    with commercial_backend():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM public.projects WHERE id=%s AND org_id=%s FOR UPDATE",
                [project_id, org_id],
            )
            cursor.execute(
                "SELECT id FROM public.pricing_operations "
                "WHERE id=%s AND project_id=%s AND org_id=%s FOR UPDATE",
                [pricing_operation_id, project_id, org_id],
            )
            cursor.execute(
                "SELECT id FROM public.project_positions "
                "WHERE project_id=%s AND org_id=%s ORDER BY position_index FOR UPDATE",
                [project_id, org_id],
            )
    with documentary_backend():
        project = one(
            "SELECT * FROM public.projects WHERE org_id=%s AND id=%s",
            [org_id, project_id],
            "project_not_found",
        )
        revision = str(project["current_revision"])
        existing = rows(
            "SELECT id,pricing_operation_id,revision_code,bom_hash,snapshot_sha256,"
            "production_allowed,documentary_complete,emitted_at "
            "FROM public.project_versions WHERE project_id=%s AND org_id=%s "
            "AND revision_code=%s",
            [project_id, org_id, revision],
        )
        if existing:
            if len(existing) != 1 or str(existing[0]["pricing_operation_id"]) != str(
                pricing_operation_id
            ):
                raise DocumentaryError("revision_already_sealed")
            return {
                **{key: (str(value) if isinstance(value, UUID) else value)
                   for key, value in existing[0].items()},
                "pricing_operation_id": str(pricing_operation_id),
                "created": False,
            }
        if project["status"] != "DRAFT":
            raise DocumentaryError("revision_not_available")
        operation = one(
            "SELECT id,org_id,project_id,requested_by,request::text,input_snapshot::text,"
            "result::text,source_revision,revision_code,state,approved_by,approved_at,reason,created_at "
            "FROM public.pricing_operations WHERE id=%s AND org_id=%s AND project_id=%s",
            [pricing_operation_id, org_id, project_id],
            "pricing_operation_not_found",
        )
        if operation["state"] != "APPLIED" or str(
            operation["revision_code"] or "REV-A"
        ) != revision:
            raise DocumentaryError("applied_pricing_authority_required")
        if project["pricing_reset_at"] is not None and (
            operation["approved_at"] is None or operation["approved_at"] <= project["pricing_reset_at"]
        ):
            raise DocumentaryError("applied_pricing_authority_required")
        project_input = one(
            "SELECT * FROM public.project_documentary_inputs "
            "WHERE project_id=%s AND org_id=%s",
            [project_id, org_id],
            "project_documentary_inputs_required",
        )
        positions = _position_rows(project_id, org_id)
        if not positions:
            raise DocumentaryError("position_documentary_inputs_required")
        request = _json_object(operation["request"], "invalid_applied_pricing_request")
        pricing_snapshot = _json_object(
            operation["input_snapshot"], "invalid_applied_pricing_snapshot"
        )
        pricing_result = _json_object(operation["result"], "invalid_applied_pricing_result")
        _pricing_state_matches(project, positions, request, pricing_snapshot, pricing_result)
        priced_bom = _technical_bom(pricing_snapshot)

        position_inputs: list[dict[str, object]] = []
        bom: list[dict[str, object]] = []
        manufacturing: list[object] = []
        inspector_evidence: list[dict[str, object]] = []
        purchase_positions: list[PositionPurchaseInputV1] = []
        purchase_authorities: PurchaseAuthorities | None = None
        documentary_complete = True
        production_allowed = True
        stock_repository = CuttingRepository()
        # Process authority is frozen into the sealed position: release must
        # route under the profile and system facts that existed at seal — a
        # later catalog or profile edit can never re-route sealed evidence.
        position_system_ids = [
            str(position["system_id"]) for position in positions if position.get("system_id")
        ]
        system_facts_by_id = {
            str(row["id"]): row
            for row in rows(
                """
                SELECT id::text, material::text, end_milling_overlap_mm,
                       process_profile_id::text
                FROM public.profile_systems
                WHERE id = ANY(%s::uuid[])
                """,
                [position_system_ids],
            )
        } if position_system_ids else {}
        for position in positions:
            position_id = str(position["id"])
            tree = _json_object(position["parametric_tree"], "invalid_parametric_tree")
            is_assembly = isinstance(tree, dict) and tree.get("version") == "product-v2"
            color_interior = str(position["color_interior"])
            color_exterior = str(position["color_exterior"] or color_interior)
            system_id = UUID(str(position["system_id"]))
            params = SystemParamsRepository().load_visible(system_id, org_id)
            calculations, result = _position_calculations(
                tree=tree,
                width_mm=D(str(position["width_mm"])),
                height_mm=D(str(position["height_mm"])),
                color=color_interior,
                color_exterior=color_exterior,
                params=params,
                system_id=system_id,
                org_id=org_id,
            )
            # The finish key the position's bars are stocked under — a
            # plain code or the bicolor "EXT/INT" key; pre-D05 results
            # fall back to the binary domain they sealed.
            stock_color = result.finish_key or (
                "WHITE"
                if color_interior == "WHITE" and color_exterior == "WHITE"
                else "FOILED"
            )
            current_bom = result.model_dump(mode="json")
            stored_bom = _json_object(position["bom_snapshot"], "invalid_stored_bom")
            stored_bom.pop("calculation_hash", None)
            priced_ref = priced_bom.get(position_id)
            if not _same_documentary_value(
                _without_additive_bom_fields(current_bom, stored_bom),
                _without_additive_bom_fields(stored_bom, stored_bom),
            ) or not isinstance(priced_ref, dict) or not _same_documentary_value(
                _without_additive_bom_fields(current_bom, priced_ref),
                _without_additive_bom_fields(priced_ref, priced_ref),
            ):
                raise DocumentaryError("applied_pricing_technical_binding_drift")

            process_facts = process_facts_snapshot(
                org_id=org_id,
                engine_result=current_bom,
                system_facts=system_facts_by_id.get(str(system_id)),
            )
            annotations = workshop_annotations(position["workshop_annotations"])
            structural = structural_inputs(position["structural_inputs"])
            targets = {
                (f"{module_id}|{opening.bay_id}" if module_id else opening.bay_id, None)
                for module_id, computation, _ in calculations
                for opening in computation.openings
            } | {
                (
                    f"{module_id}|{leaf.bay_id}" if module_id else leaf.bay_id,
                    f"{module_id}|{leaf.leaf_id}" if module_id else leaf.leaf_id,
                )
                for module_id, computation, _ in calculations
                for leaf in computation.leaves
            }
            if any((item.bay_id, item.leaf_id) not in targets for item in annotations):
                raise DocumentaryError("workshop_annotation_target_invalid")
            spans = {
                f"{module_id}|{span.target_id}" if module_id else span.target_id
                for module_id, computation, _ in calculations
                for span in computation.spans
            }
            if any(item.target_id not in spans for item in structural):
                raise DocumentaryError("structural_input_target_invalid")
            # Foiled positions exist now — annotations on one may carry the
            # FOILED machining class; a WHITE design can never claim it.
            finish_class = result.finish_class or (
                "WHITE"
                if color_interior == "WHITE" and color_exterior == "WHITE"
                else "NON_WHITE"
            )
            if finish_class == "WHITE" and any(
                item.finish_class not in (None, "WHITE") for item in annotations
            ):
                raise DocumentaryError("unsupported_documentary_color")

            inspector_authorities = InspectorRepository().load(system_id, org_id)
            cutting = stock_repository.for_result(
                result, system_id, org_id, stock_color
            )
            calculation_request, legacy_request = _documentary_calculation_requests(
                system_id=system_id, tree=tree,
                width_mm=D(str(position["width_mm"])),
                height_mm=D(str(position["height_mm"])),
                color_interior=color_interior, color_exterior=color_exterior,
            )
            identity_hashes = _calculation_identity_hashes(
                calculation_request, result, legacy_request=legacy_request
            )
            source_hash = identity_hashes[0]
            stored_identity = position["documentary_calculation_hash"]
            if stored_identity not in identity_hashes:
                raise DocumentaryError("documentary_calculation_identity_stale")
            inspections: list[tuple[str | None, InspectorResult, bool, bool]] = []
            has_failures = False
            position_production_allowed = True
            position_complete = True
            for module_id, computation, _ in calculations:
                inertias: dict[str, Decimal | None] = {}
                for span in computation.spans:
                    try:
                        _, inertia = stock_repository.reinforcement_stock(
                            system_id, org_id, span.parent_profile_sku
                        )
                    except MissingStockAuthority:
                        inertia = None
                    inertias[span.target_id] = inertia
                try:
                    inspection = inspect(InspectorInput(
                        computation=computation,
                        chamber_clearance_mm=inspector_authorities.chamber_clearance_mm,
                        annotations=_module_scoped(annotations, module_id, "bay_id", "leaf_id"),
                        structural_inputs=_module_scoped(structural, module_id, "target_id"),
                        reinforcement_ix_by_target=inertias,
                        mode=InspectionMode.DESIGN,
                        source_calculation_hash=str(source_hash),
                    ), inspector_authorities.config)
                except ValueError as error:
                    # Inspector violations carry no position identity; without
                    # it the estimator must binary-search the vano list.
                    raise ValueError(
                        f"Vano «{position.get('name') or position.get('position_index')}»: {error}"
                    ) from error
                module_allowed = inspection.production_allowed
                module_complete = not any(
                    evaluation.status is RuleEvaluationStatus.MISSING_INPUT
                    for evaluation in inspection.evaluations
                )
                inspections.append(
                    (module_id, inspection, module_complete, module_allowed)
                )
                # Only RED-severity failures block unconditionally — a
                # YELLOW finding is a warning the inspector itself classifies
                # as production-allowed, so blocking on it made a healthy
                # freeze fail invisibly (review WB3).
                red_rules = {
                    finding.rule_id
                    for finding in inspection.findings
                    if finding.severity is InspectorSeverity.RED
                }
                has_failures = has_failures or any(
                    evaluation.status is RuleEvaluationStatus.FAIL
                    and evaluation.rule_id in red_rules
                    for evaluation in inspection.evaluations
                )
                position_production_allowed = (
                    position_production_allowed and module_allowed
                )
                position_complete = position_complete and module_complete
            is_red = not position_production_allowed or any(
                inspection.status == "RED" for _, inspection, _, _ in inspections
            )
            if has_failures or (is_red and not allow_incomplete_workshop):
                # Serialize the blocking rules — a bare "inspector_red_blocks"
                # left the emission form unable to say WHAT failed (review WB2).
                failures = [
                    {
                        "rule": str(finding.rule_id.value),
                        "severity": str(finding.severity.value),
                        "title": finding.title,
                        "diagnosis": finding.diagnosis,
                        "recommendation": finding.recommendation,
                        "module_id": module_id,
                        "bay_id": finding.bay_id,
                        "leaf_id": finding.leaf_id,
                    }
                    for module_id, inspection, _, _ in inspections
                    for finding in inspection.findings
                    if finding.severity is InspectorSeverity.RED
                ]
                raise DocumentaryError(
                    "inspector_red_blocks_documentary_freeze",
                    detail="Una regla del inspector bloquea el congelamiento documental.",
                    extra={"inspector_failures": failures},
                )
            if position["measurement_state"] != "CONFIRMED" and (
                position["rough_opening_input"] is not None
                or position["mounting_rule_id"] is not None
                or position["fabrication_lock"] is not None
            ):
                # D07: la OT no se libera con medidas sin confirmar — la
                # revisión sella como cotización; producción exige una
                # revisión con cada posición medida confirmada. Una
                # posición sin registro de vano no arrastra el gate.
                position_production_allowed = False
            production_allowed = production_allowed and position_production_allowed
            documentary_complete = documentary_complete and position_complete

            policies = load_manufacturing_policies(
                system_id=system_id,
                org_id=org_id,
                placement_id=UUID(str(position["manufacturing_placement_policy_id"])),
                handle_id=UUID(str(position["handle_requirement_policy_id"])),
                reinforcement_id=UUID(str(position["reinforcement_cut_policy_id"])),
            )
            intents = handle_intents(position["handle_intents"])
            quantity = int(position["quantity"])
            unit_models: list[tuple[str | None, ManufacturingFactsV1]] = []
            for module_id, computation, module_tree in calculations:
                scoped_intents = _synthesized_handle_intents(
                    module_tree,
                    computation.manufacturing_trace,
                    _module_scoped(intents, module_id, "bay_id", "leaf_id"),
                )
                if is_assembly and _missing_handle_intents(
                    computation.manufacturing_trace,
                    policies.handles,
                    scoped_intents,
                ):
                    # Quote-only assemblies seal incomplete: a module whose
                    # handle intents were never saved is not projected rather
                    # than blocking the commercial freeze.
                    continue
                for repetition in range(1, quantity + 1):
                    unit_models.append((
                        module_id,
                        project_manufacturing_facts_v1(
                            trace=computation.manufacturing_trace,
                            position_id=position_id,
                            position_index=int(position["position_index"]),
                            repetition_index=repetition,
                            placement_policy=policies.placement,
                            handle_policy=policies.handles,
                            reinforcement_policy=policies.reinforcement,
                            handle_intents=scoped_intents,
                            resolved_reinforcement_skus=cutting.reinforcement_skus,

                            module_id=module_id,
                        ),
                    ))
            units = [unit for _, unit in unit_models]
            hardware = [HardwareSelectionV1(
                repetition_index=repetition,
                bay_id=item.bay_id,
                leaf_id=item.leaf_id,
                technical_kit_sku=item.kit_sku,
                name=item.name,
                quantity=item.qty,
                contents=item.contents,
            ) for repetition in range(1, quantity + 1) for item in result.hardware_items]
            fittings = [FittingSelectionV1(
                repetition_index=repetition,
                bay_id=item.bay_id,
                leaf_id=item.leaf_id,
                technical_sku=item.sku,
                kind=item.kind,
                quantity=item.qty,
            ) for repetition in range(1, quantity + 1) for item in result.fittings]
            polishing = glass_polishing(position["glass_polishing"])
            glass_targets = {
                (
                    f"{module_id}|{infill.bay_id}" if module_id else infill.bay_id,
                    f"{module_id}|{infill.leaf_id}"
                    if module_id and infill.leaf_id is not None
                    else infill.leaf_id,
                )
                for module_id, unit in unit_models
                for infill in unit.infills
                if infill.kind == "GLASS"
            }
            accessories = (
                accessory_schedule(position["accessory_schedule"], str(position["documentary_input_id"]))
                if position["accessory_schedule"] is not None else None
            )
            purchase_complete = (
                {(item.bay_id, item.leaf_id) for item in polishing} == glass_targets
                and accessories is not None
            )
            if is_assembly:
                # Per-module purchase projection is not yet defined for
                # assemblies: they freeze honestly as quote-only, never
                # faking production completeness.
                purchase_complete = False
            if not purchase_complete:
                if not allow_incomplete_workshop:
                    raise DocumentaryError("purchase_authority_incomplete")
                position_production_allowed = False
                position_complete = False
                production_allowed = False
                documentary_complete = False
            location_tag = str(position["location_tag"] or "")
            if purchase_complete:
                purchase_positions.append(PositionPurchaseInputV1(
                    position_id=position_id,
                    position_index=int(position["position_index"]),
                    system_id=str(system_id),
                    quantity=quantity,
                    color=stock_color,
                    steel_colors=steel_color_map(cutting.stocks),
                    location_tag=location_tag,
                    manufacturing_units=units,
                    hardware=hardware,
                    fittings=fittings,
                    glass_polishing=polishing,
                    accessory_schedule=accessories,
                ))
            # Module units cover every profile SKU the freeze needs: assembly
            # coupler cuts are quote-level BOM evidence, not purchase evidence.
            profile_skus = {member.workshop_sku for unit in units for member in unit.members}
            reinforcement_skus = {
                item.workshop_sku for unit in units for item in unit.reinforcements
            }
            glass_skus = {
                infill.technical_sku for unit in units for infill in unit.infills
                if infill.kind == "GLASS"
            }
            panel_skus = {
                infill.technical_sku for unit in units for infill in unit.infills
                if infill.kind == "PANEL"
            }
            following = load_purchase_authorities(
                system_id=system_id,
                org_id=org_id,
                color=stock_color,
                reinforcement_colors=steel_color_map(cutting.stocks),
                profile_skus=profile_skus,
                reinforcement_skus=reinforcement_skus,
                glass_skus=glass_skus,
                hardware_skus={item.technical_kit_sku for item in hardware},
                panel_skus=panel_skus,
                fitting_skus={item.technical_sku for item in fittings},
            )
            purchase_authorities = _collect_purchase_authorities(
                purchase_authorities, following
            )
            position_inputs.append({
                "id": position_id,
                "position_index": int(position["position_index"]),
                "quantity": quantity,
                "typology": str(position["typology"]),
                "system_id": system_id,
                "width_mm": D(str(position["width_mm"])),
                "height_mm": D(str(position["height_mm"])),
                "color_interior": color_interior,
                "color_exterior": color_exterior,
                "finish_key": stock_color,
                "finish": result.finish_label,
                "color_interior_detail": _color_option_detail(
                    resolve_color(params, color_interior)
                ),
                "color_exterior_detail": _color_option_detail(
                    resolve_color(params, color_exterior)
                ),
                "location_tag": location_tag,
                "system_name": str(position["system_name"]),
                "system_is_demo": bool(position.get("system_is_demo")),
                "system_limits": json.loads(
                    position["system_limits"], parse_float=Decimal
                )
                if position.get("system_limits") else [],
                "price_net": D(str(position["price_net"])),
                "discount_pct": str(position["discount_pct"]),
                "rough_opening_input": position["rough_opening_input"],
                "mounting_rule_id": (
                    None if position["mounting_rule_id"] is None
                    else str(position["mounting_rule_id"])
                ),
                "fabrication_lock": position["fabrication_lock"],
                "measurement_state": str(position["measurement_state"]),
                "measurement_confirmed_at": (
                    None if position["measurement_confirmed_at"] is None
                    else position["measurement_confirmed_at"].isoformat()
                ),
                "measurement_confirmed_by": (
                    None if position["measurement_confirmed_by"] is None
                    else str(position["measurement_confirmed_by"])
                ),
                # D07 sealed measurement evidence: the vano record, the rule
                # applied and the engine resolution — the exact desglose the
                # estimator saw at seal time.
                "measurement": _measurement_evidence(org_id, position),
                "parametric_tree": tree,
                "workshop_annotations": [item.model_dump(mode="python") for item in annotations],
                "structural_inputs": [item.model_dump(mode="python") for item in structural],
                "glass_polishing": [item.model_dump(mode="python") for item in polishing],
                "handle_intents": [item.model_dump(mode="python") for item in intents],
                "accessory_schedule": accessories.model_dump(mode="python") if accessories else None,
                "calculation_hash": source_hash,
                "manufacturing_policies": {
                    "placement": policies.placement.model_dump(mode="python"),
                    "handles": policies.handles.model_dump(mode="python"),
                    "reinforcement": policies.reinforcement.model_dump(mode="python"),
                },
                "legacy_handle_migration_confirmed": bool(
                    position["legacy_handle_migration_confirmed"]
                ),
                "process_facts": process_facts,
            })
            bom.append({
                "position_id": position_id,
                "quantity": quantity,
                "engine_result": current_bom,
                "calculation_hash": source_hash,
            })
            manufacturing.extend(
                {
                    **unit.model_dump(mode="python"),
                    **({"module_id": module_id} if module_id else {}),
                }
                for module_id, unit in unit_models
            )
            for module_id, inspection, module_complete, module_allowed in inspections:
                inspector_evidence.append({
                    "position_id": position_id,
                    **({"module_id": module_id} if module_id else {}),
                    "mode": "DESIGN",
                    "result": inspection.model_dump(mode="python"),
                    "config": inspector_authorities.config.model_dump(mode="python"),
                    "chamber_clearance_mm": inspector_authorities.chamber_clearance_mm,
                    "documentary_complete": module_complete,
                    "production_allowed": module_allowed,
                })

        if purchase_authorities is None:
            raise DocumentaryError("purchase_authorities_required")
        purchase = project_purchase_requirements_v1(
            positions=purchase_positions,
            stock_bindings=purchase_authorities.stock_bindings,
            glass_mappings=purchase_authorities.glass_mappings,
            hardware_mappings=purchase_authorities.hardware_mappings,
            panel_authorities=purchase_authorities.panel_authorities,
            fitting_mappings=purchase_authorities.fitting_mappings,
        ) if len(purchase_positions) == len(positions) else None
        bom_hash = bom_hash_v1(
            project_id=project_id, revision=revision, positions=position_inputs, bom=bom
        )
        organization = one(
            "SELECT name, tax_id, commercial_name, giro, brand_address,"
            " brand_phone, brand_email, brand_logo_key, brand_logo_sha256,"
            " brand_color, doc_dekopen_credit, extras_display"
            " FROM public.tenancy_organizations WHERE id = %s",
            [str(org_id)],
            "organization_not_found",
        )
        sealed_at = datetime.now(timezone.utc)
        snapshot = {
            "schema_version": 1,
            "canonical_version": DOCUMENTARY_CANONICAL_VERSION,
            "project_id": project_id,
            "org_id": org_id,
            # Issuer identity for the letterhead — rendered only on revisions
            # frozen after this field existed; older snapshots simply omit it.
            # The logo key is content-addressed, so the frozen sha pins the
            # exact bytes a re-rendered document may show.
            "organization": {
                "name": str(organization["name"]),
                "tax_id": str(organization["tax_id"]),
                "commercial_name": organization["commercial_name"],
                "giro": organization["giro"],
                "brand_address": organization["brand_address"],
                "brand_phone": organization["brand_phone"],
                "brand_email": organization["brand_email"],
                "brand_logo_key": organization["brand_logo_key"],
                "brand_logo_sha256": organization["brand_logo_sha256"],
                # P25: color de marca white-label y atribución DEKOPEN
                # opt-in — sellados con la revisión como el resto de la
                # identidad del emisor.
                "brand_color": organization["brand_color"],
                "doc_dekopen_credit": bool(organization["doc_dekopen_credit"]),
                # D06: sealed policy for how extras/services print —
                # DETAILED prints every sublínea, GROUPED folds them into
                # the position sum. Older snapshots omit it and render
                # detailed (the only behavior that ever existed).
                "extras_display": organization["extras_display"],
            },
            "revision": revision,
            "sealed_by": actor_id,
            "sealed_at": sealed_at,
            "project": {
                "code": str(project["code"]),
                "name": str(project["name"]),
                "client_name": str(project["client_name"]),
                "client_rut": project["client_rut"],
                "client_email": project["client_email"],
                "client_phone": project["client_phone"],
                "client_giro": project["client_giro"],
                "client_comuna": project["client_comuna"],
                "client_address": project["client_address"],
                "delivery_address": project["delivery_address"],
                "payment_terms": str(project_input["payment_terms"]),
                "quotation_valid_until": project_input["quotation_valid_until"],
                "notes_commercial": project["notes_commercial"],
                "currency": request.get("currency"),
                "total_price_net": D(str(project["total_price_net"])),
                "total_price_tax": D(str(project["total_price_tax"])),
                "total_price_gross": D(str(project["total_price_gross"])),
            },
            "positions": position_inputs,
            "bom": bom,
            "pricing": {
                "operation_id": operation["id"],
                "state": "APPLIED",
                "requested_by": operation["requested_by"],
                "approved_by": operation["approved_by"],
                "approved_at": operation["approved_at"],
                "request": request,
                "input_snapshot": pricing_snapshot,
                "result": pricing_result,
                "applied_total_cost_net": D(str(project["total_cost_net"])),
                "source_revision": operation["source_revision"],
            },
            "inspector": inspector_evidence,
            "manufacturing": manufacturing,
            "purchase_requirements": purchase.model_dump(mode="python") if purchase else None,
            "purchase_authorities": {
                "physical_stock_bindings": [
                    item.model_dump(mode="python")
                    for item in purchase_authorities.stock_bindings
                ],
                "glass": [item.model_dump(mode="python")
                          for item in purchase_authorities.glass_mappings],
                "hardware": [item.model_dump(mode="python")
                             for item in purchase_authorities.hardware_mappings],
                "panel": [item.model_dump(mode="python")
                          for item in purchase_authorities.panel_authorities],
            },
            "production_allowed": production_allowed,
            "documentary_complete": documentary_complete,
            "realized_waste": {"status": "NOT_RECORDED", "value": None},
            "bom_hash": bom_hash,
        }
        snapshot_sha256 = snapshot_sha256_v1(snapshot)
        version = one(
            "INSERT INTO public.project_versions("
            "project_id,org_id,revision_code,snapshot_json,pdf_storage_path,emitted_by,emitted_at,"
            "authority_version,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,"
            "production_allowed,documentary_complete) "
            "VALUES(%s,%s,%s,%s::jsonb,NULL,%s,%s,'SHOT10_V1',%s,%s,%s,%s,%s,%s) "
            "RETURNING id,revision_code,bom_hash,snapshot_sha256,production_allowed,"
            "documentary_complete,emitted_at",
            [project_id, org_id, revision,
             documentary_canonical_json_v1(snapshot).decode("utf-8"), actor_id, sealed_at,
             pricing_operation_id, DOCUMENTARY_CANONICAL_VERSION, bom_hash,
             snapshot_sha256, production_allowed, documentary_complete],
        )
        version_id = UUID(str(version["id"]))
        if purchase is not None:
            projection_snapshot = purchase.model_dump(mode="python")
            projection = one(
                "INSERT INTO public.purchase_projections("
                "project_id,project_version_id,org_id,bom_hash,snapshot_sha256,schema_version,"
                "projection_hash,snapshot_json,created_by,created_at) "
                "VALUES(%s,%s,%s,%s,%s,1,%s,%s::jsonb,%s,%s) RETURNING id",
                [project_id, version_id, org_id, bom_hash, snapshot_sha256,
                 purchase.projection_hash,
                 documentary_canonical_json_v1(projection_snapshot).decode("utf-8"),
                 actor_id, sealed_at],
            )
            projection_id = UUID(str(projection["id"]))
            for requirement in purchase.requirements:
                requirement_id = uuid5(
                    NAMESPACE_URL, f"https://dekopen.local/requirement/{version_id}/{requirement.requirement_key}"
                )
                common = {
                    "requirement_key", "order_type", "category", "authority_ids",
                    "technical_skus", "purchasing_sku", "physical_stock_identity",
                    "unit", "quantity", "source_trace",
                }
                payload = requirement.model_dump(mode="python")
                specification = {
                    key: value for key, value in payload.items()
                    if key not in common and value is not None
                }
                one(
                    "INSERT INTO public.purchase_requirement_lines("
                    "id,requirement_key,projection_id,project_id,project_version_id,org_id,"
                    "bom_hash,snapshot_sha256,order_type,category,technical_identity,purchasing_sku,"
                    "physical_stock_identity,unit,quantity,specification,source_trace) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s::jsonb) "
                    "RETURNING id",
                    [requirement_id, requirement.requirement_key, projection_id, project_id,
                     version_id, org_id, bom_hash, snapshot_sha256,
                     requirement.order_type.value, requirement.category,
                     json_text({"authority_ids": requirement.authority_ids,
                                "technical_skus": requirement.technical_skus}),
                     requirement.purchasing_sku, requirement.physical_stock_identity,
                     requirement.unit, requirement.quantity, json_text(specification),
                     json_text(requirement.source_trace)],
                )
        with commercial_backend():
            one(
                "UPDATE public.projects SET status='QUOTED',updated_at=clock_timestamp() "
                "WHERE id=%s AND org_id=%s AND status='DRAFT' AND current_revision=%s RETURNING id",
                [project_id, org_id, revision],
                "revision_state_transition_failed",
            )
        # §08 automations: a production-allowed freeze queues the material
        # forecast; a freeze that revealed missing catalog authority files a
        # catalog task per affected system instead. Emit inside this tx so the
        # job exists iff the version does.
        from automations.service import emit

        if production_allowed:
            emit(
                "automation.prep_forecast",
                org_id=org_id,
                actor_id=actor_id,
                idempotency_key=f"auto:prep:{version_id}",
                version_id=str(version_id),
            )
        else:
            for system_id in sorted(set(position_system_ids)):
                emit(
                    "automation.catalog_task",
                    org_id=org_id,
                    actor_id=actor_id,
                    idempotency_key=f"auto:catalog:{version_id}:{system_id}",
                    system_id=system_id,
                    version_id=str(version_id),
                )
        return {
            "id": str(version_id),
            "pricing_operation_id": str(pricing_operation_id),
            "created": True,
            "revision_code": revision,
            "bom_hash": bom_hash,
            "snapshot_sha256": snapshot_sha256,
            "production_allowed": production_allowed,
            "documentary_complete": documentary_complete,
            "emitted_at": sealed_at,
            "purchase_projection_hash": purchase.projection_hash if purchase else None,
        }


def prepare_documentary_inputs(
    *, org_id: UUID, project_id: UUID
) -> dict[str, object]:
    project = one(
        "SELECT id,status,current_revision FROM public.projects WHERE id=%s AND org_id=%s",
        [project_id, org_id],
        "project_not_found",
    )
    positions = rows(
        "SELECT position.id,position.system_id,position.location_tag,position.width_mm,"
        "position.height_mm,position.color_interior,position.color_exterior,"
        "position.parametric_tree,system.name AS system_name "
        "FROM public.project_positions position JOIN public.profile_systems system "
        "ON system.id=position.system_id WHERE position.project_id=%s AND position.org_id=%s "
        "ORDER BY position.position_index",
        [project_id, org_id],
    )
    project_inputs = rows(
        "SELECT payment_terms,quotation_valid_until FROM public.project_documentary_inputs "
        "WHERE project_id=%s AND org_id=%s",
        [project_id, org_id],
    )
    position_inputs = {
        str(item["position_id"]): item
        for item in rows(
            "SELECT position_id,manufacturing_placement_policy_id,handle_requirement_policy_id,"
            "reinforcement_cut_policy_id,workshop_annotations::text,structural_inputs::text,"
            "glass_polishing::text,handle_intents::text,accessory_schedule::text,"
            "legacy_handle_migration_confirmed,calculation_hash FROM public.position_documentary_inputs "
            "WHERE project_id=%s AND org_id=%s",
            [project_id, org_id],
        )
    }
    systems = {item["system_id"] for item in positions}

    def policy_options(table):
        if not systems:
            return {}
        placeholders = ",".join(["%s"] * len(systems))
        values = rows(
            f"SELECT id,system_id,version,authority->>'policy_id' AS label FROM public.{table} "
            f"WHERE system_id IN ({placeholders}) AND (org_id IS NULL OR org_id=%s) "
            "ORDER BY system_id,version DESC,id",
            [*systems, org_id],
        )
        grouped = {}
        for value in values:
            grouped.setdefault(str(value["system_id"]), []).append(
                {
                    "id": value["id"],
                    "label": value["label"] or f"Versión {value['version']}",
                    "version": value["version"],
                }
            )
        return grouped

    placement = policy_options("manufacturing_placement_policies")
    handles = policy_options("handle_requirement_policies")
    reinforcement = policy_options("reinforcement_cut_policies")
    handle_authorities: dict[str, HandleRequirementPolicyV1] = {}
    placement_authorities: dict[str, ManufacturingPlacementPolicyV1] = {}
    if systems:
        placeholders = ",".join(["%s"] * len(systems))
        for value in rows(
            "SELECT id,authority::text FROM public.handle_requirement_policies "
            f"WHERE system_id IN ({placeholders}) AND (org_id IS NULL OR org_id=%s)",
            [*systems, org_id],
        ):
            handle_authorities[str(value["id"])] = _handle_policy(value["authority"])
        for value in rows(
            "SELECT id,authority::text FROM public.manufacturing_placement_policies "
            f"WHERE system_id IN ({placeholders}) AND (org_id IS NULL OR org_id=%s)",
            [*systems, org_id],
        ):
            placement_authorities[str(value["id"])] = _placement_policy(
                value["authority"]
            )

    def selected(existing, key, options):
        if existing and existing[key] is not None:
            return existing[key]
        return options[0]["id"] if len(options) == 1 else None

    prepared = []
    # Full load (config + chamber clearance) is cached per system so the
    # readiness preview runs the same inspector the freeze will run.
    inspector_authorities: dict[str, InspectorAuthorities] = {}
    stock_repository = CuttingRepository()
    for position in positions:
        identity = str(position["id"])
        existing = position_inputs.get(identity)
        system_id = str(position["system_id"])
        system_id_uuid = UUID(system_id)
        placement_options = placement.get(system_id, [])
        handle_options = handles.get(system_id, [])
        reinforcement_options = reinforcement.get(system_id, [])

        tree = _json_object(position["parametric_tree"], "invalid_parametric_tree")
        color_interior = str(position["color_interior"])
        color_exterior = str(position["color_exterior"] or color_interior)
        params = SystemParamsRepository().load_visible(system_id_uuid, org_id)
        calculations, result = _position_calculations(
            tree=tree,
            width_mm=D(str(position["width_mm"])),
            height_mm=D(str(position["height_mm"])),
            color=color_interior,
            color_exterior=color_exterior,
            params=params,
            system_id=system_id_uuid,
            org_id=org_id,
        )
        calculation_request, legacy_request = _documentary_calculation_requests(
            system_id=system_id, tree=tree,
            width_mm=D(str(position["width_mm"])),
            height_mm=D(str(position["height_mm"])),
            color_interior=color_interior, color_exterior=color_exterior,
        )
        identity_hashes = _calculation_identity_hashes(
            calculation_request, result, legacy_request=legacy_request
        )
        identity_hash = identity_hashes[0]
        # A changed product no longer discards the estimator's work (review
        # WM3): saved values carry forward and the per-target filters below
        # drop only the entries whose bay/leaf/span disappeared — an
        # untouched leaf keeps its recorded measurements across re-prepare.
        valid_bays, valid_leaves, valid_spans, valid_glass = _valid_targets(calculations)

        trace_leaves: list[dict[str, object]] = []
        leaf_counts: dict[str | None, int] = {}
        for module_id, computation, _module_tree in calculations:
            trace = computation.manufacturing_trace
            if trace is None:
                continue
            for leaf in trace.leaves:
                leaf_counts[module_id] = leaf_counts.get(module_id, 0) + 1
                number = leaf_counts[module_id]
                trace_leaves.append(
                    {
                        "bay_id": (
                            f"{module_id}|{leaf.bay_id}"
                            if module_id
                            else leaf.bay_id
                        ),
                        "leaf_id": (
                            f"{module_id}|{leaf.leaf_id}"
                            if module_id and leaf.leaf_id is not None
                            else leaf.leaf_id
                        ),
                        "leaf_label": (
                            f"Unidad {module_id} · hoja {number}"
                            if module_id
                            else f"Hoja {number}"
                        ),
                        "leaf": leaf,
                        "nominal_height_mm": trace.nominal_height_mm,
                    }
                )

        existing_workshop = (
            decoded(existing["workshop_annotations"])
            if existing and existing["workshop_annotations"] is not None
            else []
        )
        existing_glass = (
            decoded(existing["glass_polishing"])
            if existing and existing["glass_polishing"] is not None
            else []
        )
        existing_structural = (
            decoded(existing["structural_inputs"])
            if existing and existing["structural_inputs"] is not None
            else []
        )
        existing_intents = (
            decoded(existing["handle_intents"])
            if existing and existing["handle_intents"] is not None
            else []
        )

        workshop = [
            item for item in (existing_workshop or [])
            if isinstance(item, dict)
            and item.get("bay_id") in valid_bays
            and (item.get("leaf_id") is None or (item.get("bay_id"), item.get("leaf_id")) in valid_leaves)
        ]
        glass = [
            item for item in (existing_glass or [])
            if isinstance(item, dict)
            and (item.get("bay_id"), item.get("leaf_id")) in valid_glass
        ]
        structural = [
            item for item in (existing_structural or [])
            if isinstance(item, dict)
            and item.get("target_id") in valid_spans
        ]
        intents = [
            item for item in (existing_intents or [])
            if isinstance(item, dict)
            and (item.get("bay_id"), item.get("leaf_id")) in valid_leaves
        ]

        inspector_authority = inspector_authorities.setdefault(
            system_id, InspectorRepository().load(system_id_uuid, org_id)
        )
        inspector_config = inspector_authority.config
        # Suggestions stay a separate channel: prepare returns what the
        # estimator actually stored, plus advisory defaults the emit form can
        # prefill. Absence is never synthesized into stored authority — what
        # the user sees and saves is what exists.
        workshop_suggestions = _seed_workshop_defaults(calculations, [], inspector_config)
        polishing_suggestions = _seed_polishing_defaults(valid_glass, [])

        # Readiness preview: the emit button must state what the revision
        # will allow BEFORE it runs — same inspector, same saved inputs the
        # freeze consumes, so "Sólo cotización" is never a surprise.
        preview_annotations = workshop_annotations(workshop)
        preview_structural = structural_inputs(structural)
        production_ready = True
        documentary_ready = True
        for module_id, computation, _module_tree in calculations:
            inertias: dict[str, Decimal | None] = {}
            for span in computation.spans:
                try:
                    _, inertia = stock_repository.reinforcement_stock(
                        system_id_uuid, org_id, span.parent_profile_sku
                    )
                except MissingStockAuthority:
                    inertia = None
                inertias[span.target_id] = inertia
            try:
                preview = inspect(
                    InspectorInput(
                        computation=computation,
                        chamber_clearance_mm=inspector_authority.chamber_clearance_mm,
                        annotations=_module_scoped(
                            preview_annotations, module_id, "bay_id", "leaf_id"
                        ),
                        structural_inputs=_module_scoped(
                            preview_structural, module_id, "target_id"
                        ),
                        reinforcement_ix_by_target=inertias,
                        mode=InspectionMode.DESIGN,
                        source_calculation_hash=str(identity_hash),
                    ),
                    inspector_config,
                )
            except ValueError:
                # A hard inspector failure is previewed as "not ready"; the
                # freeze surfaces the named rule if the estimator emits anyway.
                production_ready = False
                documentary_ready = False
                continue
            production_ready = production_ready and preview.production_allowed
            documentary_ready = documentary_ready and not any(
                evaluation.status is RuleEvaluationStatus.MISSING_INPUT
                for evaluation in preview.evaluations
            )

        prepared.append(
            {
                "position_id": position["id"],
                "calculation_hash": identity_hash,
                "location_tag": position["location_tag"] or "",
                "system_name": position["system_name"],
                "placement_options": placement_options,
                "handle_options": handle_options,
                "reinforcement_options": reinforcement_options,
                "manufacturing_placement_policy_id": selected(
                    existing, "manufacturing_placement_policy_id", placement_options
                ),
                "handle_requirement_policy_id": selected(
                    existing, "handle_requirement_policy_id", handle_options
                ),
                "reinforcement_cut_policy_id": selected(
                    existing, "reinforcement_cut_policy_id", reinforcement_options
                ),
                "workshop_annotations": workshop,
                "structural_inputs": structural,
                "glass_polishing": glass,
                "workshop_suggestions": workshop_suggestions,
                "polishing_suggestions": polishing_suggestions,
                "handle_intents": intents,
                "handle_requirements": [
                    {
                        "policy_id": option["id"],
                        "requirements": _handle_policy_requirements(
                            trace_leaves,
                            handle_authorities[str(option["id"])],
                            [
                                (str(placement["id"]), placement_authorities[str(placement["id"])])
                                for placement in placement_options
                                if str(placement["id"]) in placement_authorities
                            ],
                        ),
                    }
                    for option in handle_options
                    if str(option["id"]) in handle_authorities
                ],
                "workshop_targets": _workshop_targets(calculations, trace_leaves),
                "accessory_schedule": (
                    decoded(existing["accessory_schedule"])
                    if existing and existing["accessory_schedule"] is not None
                    else None
                ),
                "legacy_handle_migration_confirmed": bool(
                    existing and existing["legacy_handle_migration_confirmed"]
                ),
                "production_ready": production_ready,
                "documentary_ready": documentary_ready,
            }
        )
    values = project_inputs[0] if project_inputs else {}
    return {
        "project_id": project["id"],
        "revision_code": project["current_revision"],
        "payment_terms": values.get("payment_terms", ""),
        "quotation_valid_until": values.get("quotation_valid_until"),
        "positions": prepared,
    }


def save_documentary_inputs(
    *, org_id: UUID, actor_id: UUID, project_id: UUID, data: dict[str, object]
) -> dict[str, object]:
    supplied_values = data.get("positions")
    if not isinstance(supplied_values, list) or not all(
        isinstance(item, dict) for item in supplied_values
    ):
        raise DocumentaryError("invalid_documentary_inputs")
    with commercial_backend():
        project = one(
            "SELECT id,status FROM public.projects WHERE id=%s AND org_id=%s FOR UPDATE",
            [project_id, org_id],
            "project_not_found",
        )
        if project["status"] != "DRAFT":
            raise DocumentaryError("documentary_inputs_require_draft")
        positions = rows(
            "SELECT id,system_id,width_mm,height_mm,color_interior,color_exterior,parametric_tree "
            "FROM public.project_positions WHERE project_id=%s AND org_id=%s "
            "ORDER BY position_index FOR UPDATE",
            [project_id, org_id],
        )
        expected = {str(item["id"]) for item in positions}
        supplied = {str(item["position_id"]) for item in supplied_values}
        if supplied != expected or len(supplied_values) != len(supplied):
            raise DocumentaryError("documentary_position_coverage_required")
        positions_by_id = {str(item["id"]): item for item in positions}

    for item in supplied_values:
        pos = positions_by_id[str(item["position_id"])]
        system_id_uuid = UUID(str(pos["system_id"]))
        tree = _json_object(pos["parametric_tree"], "invalid_parametric_tree")
        color_interior = str(pos["color_interior"])
        color_exterior = str(pos["color_exterior"] or color_interior)
        params = SystemParamsRepository().load_visible(system_id_uuid, org_id)
        calculations, result = _position_calculations(
            tree=tree,
            width_mm=D(str(pos["width_mm"])),
            height_mm=D(str(pos["height_mm"])),
            color=color_interior,
            color_exterior=color_exterior,
            params=params,
            system_id=system_id_uuid,
            org_id=org_id,
        )
        calculation_request, legacy_request = _documentary_calculation_requests(
            system_id=system_id_uuid, tree=tree,
            width_mm=D(str(pos["width_mm"])),
            height_mm=D(str(pos["height_mm"])),
            color_interior=color_interior, color_exterior=color_exterior,
        )
        identity_hashes = _calculation_identity_hashes(
            calculation_request, result, legacy_request=legacy_request
        )
        valid_bays, valid_leaves, valid_spans, valid_glass = _valid_targets(calculations)
        item_workshop = item.get("workshop_annotations") or []
        for w in item_workshop:
            if not isinstance(w, dict) or w.get("bay_id") not in valid_bays or (
                w.get("leaf_id") is not None and (w.get("bay_id"), w.get("leaf_id")) not in valid_leaves
            ):
                raise DocumentaryError("workshop_annotation_target_invalid")
        item_structural = item.get("structural_inputs") or []
        for s in item_structural:
            if not isinstance(s, dict) or s.get("target_id") not in valid_spans:
                raise DocumentaryError("structural_input_target_invalid")
        item_glass = item.get("glass_polishing") or []
        for g in item_glass:
            if not isinstance(g, dict) or (g.get("bay_id"), g.get("leaf_id")) not in valid_glass:
                raise DocumentaryError("glass_polishing_target_invalid")
        for h in item.get("handle_intents") or []:
            if not isinstance(h, dict) or (h.get("bay_id"), h.get("leaf_id")) not in valid_leaves:
                raise DocumentaryError("handle_intent_target_invalid")
        if item.get("calculation_hash") not in identity_hashes:
            raise DocumentaryError("documentary_calculation_identity_stale")

    with documentary_backend():
        if rows(
            "SELECT version.id FROM public.project_versions version "
            "JOIN public.projects project ON project.id=version.project_id "
            "AND project.org_id=version.org_id "
            "WHERE version.project_id=%s AND version.org_id=%s "
            "AND version.revision_code=project.current_revision",
            [project_id, org_id],
        ):
            raise DocumentaryError("sealed_documentary_inputs_immutable")
        for item in supplied_values:
            one(
                "UPDATE public.project_positions SET location_tag=%s,updated_at=now() "
                "WHERE id=%s AND project_id=%s AND org_id=%s RETURNING id",
                [item["location_tag"], UUID(str(item["position_id"])), project_id, org_id],
            )
        one(
            "INSERT INTO public.project_documentary_inputs("
            "project_id,org_id,payment_terms,quotation_valid_until,created_by) "
            "VALUES(%s,%s,%s,%s,%s) "
            "ON CONFLICT(project_id,org_id) DO UPDATE SET "
            "payment_terms=EXCLUDED.payment_terms,"
            "quotation_valid_until=EXCLUDED.quotation_valid_until,updated_at=now() RETURNING id",
            [project_id, org_id, data["payment_terms"], data["quotation_valid_until"], actor_id],
        )
        for item in supplied_values:
            position_id = UUID(str(item["position_id"]))
            one(
                "INSERT INTO public.position_documentary_inputs("
                "position_id,project_id,org_id,manufacturing_placement_policy_id,"
                "handle_requirement_policy_id,reinforcement_cut_policy_id,workshop_annotations,"
                "structural_inputs,glass_polishing,handle_intents,accessory_schedule,"
                "legacy_handle_migration_confirmed,created_by,calculation_hash) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s) "
                "ON CONFLICT(position_id,org_id) DO UPDATE SET "
                "manufacturing_placement_policy_id=EXCLUDED.manufacturing_placement_policy_id,"
                "handle_requirement_policy_id=EXCLUDED.handle_requirement_policy_id,"
                "reinforcement_cut_policy_id=EXCLUDED.reinforcement_cut_policy_id,"
                "workshop_annotations=EXCLUDED.workshop_annotations,"
                "structural_inputs=EXCLUDED.structural_inputs,"
                "glass_polishing=EXCLUDED.glass_polishing,"
                "handle_intents=EXCLUDED.handle_intents,"
                "accessory_schedule=EXCLUDED.accessory_schedule,"
                "calculation_hash=EXCLUDED.calculation_hash,"
                "legacy_handle_migration_confirmed=EXCLUDED.legacy_handle_migration_confirmed,"
                "updated_at=now() RETURNING id",
                [position_id, project_id, org_id,
                 item["manufacturing_placement_policy_id"],
                 item["handle_requirement_policy_id"],
                 item["reinforcement_cut_policy_id"], json_text(item["workshop_annotations"]),
                 json_text(item["structural_inputs"]), json_text(item["glass_polishing"]),
                 json_text(item["handle_intents"]),
                 json_text(item["accessory_schedule"]) if item["accessory_schedule"] is not None else None,
                 item["legacy_handle_migration_confirmed"], actor_id, item["calculation_hash"]],
            )
    return {"project_id": str(project_id), "positions_saved": len(supplied_values)}


def revision_snapshot(version_id: UUID, org_id: UUID) -> tuple[dict[str, object], dict[str, object]]:
    with documentary_backend():
        version = one(
            "SELECT id,project_id,org_id,revision_code,authority_version,snapshot_json::text,"
            "bom_hash,snapshot_sha256,production_allowed,documentary_complete,"
            "emitted_by,emitted_at "
            "FROM public.project_versions WHERE id=%s AND org_id=%s",
            [version_id, org_id],
            "project_version_not_found",
        )
    if version["authority_version"] not in ("SHOT09_V1", "SHOT10_V1"):
        raise DocumentaryError("legacy_version_not_eligible")
    snapshot = _json_object(version["snapshot_json"], "invalid_frozen_revision_snapshot")
    if snapshot_sha256_v1(snapshot) != str(version["snapshot_sha256"]):
        raise DocumentaryError("frozen_revision_hash_mismatch")
    return version, snapshot


_COMPARE_FIELDS = (
    "position_index",
    "location_tag",
    "quantity",
    "typology",
    "system_id",
    "width_mm",
    "height_mm",
    "color_interior",
    "color_exterior",
    "price_net",
    "discount_pct",
    "measurement_state",
)


# Frozen-position fields that carry workshop/documentary authority beyond
# the engineering hash — annotations, intents, policies, structural inputs.
# A revision that only changed these must still report a change. D07: the
# vano record, the applied mounting rule and the fabrication pin live in
# the signature — a site rectification surfaces as a manufacturing change.
_DOCUMENTARY_SLICE = (
    "workshop_annotations",
    "structural_inputs",
    "glass_polishing",
    "handle_intents",
    "accessory_schedule",
    "manufacturing_policies",
    "legacy_handle_migration_confirmed",
    "process_facts",
    "rough_opening_input",
    "mounting_rule_id",
    "fabrication_lock",
    "measurement_state",
)


# Fields whose "changed" signal must be numeric, not lexical — "268000.00"
# vs "268000" is the same price, not a revision change.
_COMPARE_NUMERIC = {"quantity", "width_mm", "height_mm", "price_net", "discount_pct"}


def _compare_value(field: str, value: object) -> str:
    raw = str(value or "")
    if field in _COMPARE_NUMERIC:
        try:
            return format(D(raw).normalize(), "f")
        except (InvalidOperation, TypeError, ValueError):
            return raw
    return raw


def _compare_position(row: dict[str, object]) -> dict[str, object]:
    """The commercially legible slice of a frozen position — enough to render
    a thumbnail and read what changed, nothing the customer shouldn't see."""
    return {
        "id": str(row.get("id") or ""),
        "position_index": int(row["position_index"]),
        "location_tag": row.get("location_tag") or "",
        "typology": str(row.get("typology") or ""),
        "system_id": str(row.get("system_id") or ""),
        "quantity": int(row.get("quantity") or 0),
        "width_mm": str(row.get("width_mm") or ""),
        "height_mm": str(row.get("height_mm") or ""),
        "color_interior": str(row.get("color_interior") or ""),
        "color_exterior": str(row.get("color_exterior") or ""),
        "price_net": str(row.get("price_net") or ""),
        "discount_pct": str(row.get("discount_pct") or ""),
        "measurement_state": str(row.get("measurement_state") or ""),
        "rough_opening_input": row.get("rough_opening_input"),
        "mounting_rule_id": (
            None if row.get("mounting_rule_id") in (None, "")
            else str(row.get("mounting_rule_id"))
        ),
        "parametric_tree": row.get("parametric_tree"),
        "calculation_hash": str(row.get("calculation_hash") or ""),
        "documentary_signature": documentary_canonical_json_v1(
            {key: row.get(key) for key in _DOCUMENTARY_SLICE}
        ).decode("utf-8"),
    }


def _public_position(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        key: value
        for key, value in row.items()
        if key not in ("calculation_hash", "documentary_signature")
    }


def _compare_match_key(position: dict[str, object]) -> tuple[str, object]:
    """Persistent position id when the snapshot carries it; position_index
    only for snapshots frozen before ids existed. Index alone would merge a
    deleted position with a new one that reuses its number."""
    if position["id"]:
        return ("id", position["id"])
    return ("index", position["position_index"])


def compare_versions(
    *, org_id: UUID, project_id: UUID, base_code: str, head_code: str
) -> dict[str, object]:
    """Side-by-side diff of two frozen revisions of one project: positions
    keyed by position_index, commercial fields compared string-for-string.
    Snapshots that predate the hash columns are compared as stored; sealed
    integrity fields are still reported so the reader sees what is proven."""
    with documentary_backend():
        project = one(
            "SELECT id,code,name FROM public.projects WHERE id=%s AND org_id=%s",
            [str(project_id), str(org_id)],
            "project_not_found",
        )
        versions = {
            str(row["revision_code"]): row
            for row in rows(
                "SELECT id,revision_code,snapshot_json::text,snapshot_sha256,"
                "emitted_at FROM public.project_versions "
                "WHERE org_id=%s AND project_id=%s AND revision_code IN (%s,%s)",
                [str(org_id), str(project_id), base_code, head_code],
            )
        }
    if base_code not in versions or head_code not in versions:
        raise DocumentaryError("version_not_found")

    def snapshot_of(code: str) -> tuple[dict[str, object], str | None]:
        version = versions[code]
        snapshot = _json_object(
            version["snapshot_json"], "invalid_frozen_revision_snapshot"
        )
        integrity = None
        if version["snapshot_sha256"]:
            integrity = (
                "VERIFIED"
                if snapshot_sha256_v1(snapshot) == str(version["snapshot_sha256"])
                else "MISMATCH"
            )
        return snapshot, integrity

    base_snapshot, base_integrity = snapshot_of(base_code)
    head_snapshot, head_integrity = snapshot_of(head_code)
    base_positions = {
        _compare_match_key(row): row
        for row in (
            _compare_position(p)
            for p in base_snapshot.get("positions", [])
            if isinstance(p, dict) and p.get("position_index") is not None
        )
    }
    head_positions = {
        _compare_match_key(row): row
        for row in (
            _compare_position(p)
            for p in head_snapshot.get("positions", [])
            if isinstance(p, dict) and p.get("position_index") is not None
        )
    }
    entries: list[dict[str, object]] = []
    added = removed = changed = unchanged = 0
    keys = sorted(
        set(base_positions) | set(head_positions),
        key=lambda key: (
            (base_positions.get(key) or head_positions.get(key))["position_index"],
            key[0],
        ),
    )
    for key in keys:
        before = base_positions.get(key)
        after = head_positions.get(key)
        position_index = (
            after["position_index"] if after is not None else before["position_index"]
        )
        if before is None:
            added += 1
            entries.append(
                {
                    "position_index": position_index,
                    "change": "ADDED",
                    "location_tag": after["location_tag"],
                    "before": None,
                    "after": _public_position(after),
                    "changes": [],
                }
            )
            continue
        if after is None:
            removed += 1
            entries.append(
                {
                    "position_index": position_index,
                    "change": "REMOVED",
                    "location_tag": before["location_tag"],
                    "before": _public_position(before),
                    "after": None,
                    "changes": [],
                }
            )
            continue
        fields = [
            {"field": field, "before": str(before[field]), "after": str(after[field])}
            for field in _COMPARE_FIELDS
            if _compare_value(field, before[field]) != _compare_value(field, after[field])
        ]
        spec_drift = before["calculation_hash"] != after["calculation_hash"]
        if not (before["calculation_hash"] and after["calculation_hash"]):
            # Pre-hash snapshots cannot prove design equality by hash — fall
            # back to the canonical tree so a bay that changed FIXED→TURN_LEFT
            # still surfaces instead of reading as unchanged.
            spec_drift = documentary_canonical_json_v1(
                before.get("parametric_tree")
            ) != documentary_canonical_json_v1(after.get("parametric_tree"))
        if spec_drift:
            fields.append({"field": "spec", "before": "", "after": ""})
        if before["documentary_signature"] != after["documentary_signature"]:
            fields.append(
                {"field": "manufacturing", "before": "", "after": ""}
            )
        if fields:
            changed += 1
            entries.append(
                {
                    "position_index": position_index,
                    "change": "CHANGED",
                    "location_tag": after["location_tag"],
                    "before": _public_position(before),
                    "after": _public_position(after),
                    "changes": fields,
                }
            )
        else:
            unchanged += 1

    def totals(snapshot: dict[str, object]) -> dict[str, object]:
        project_data = snapshot.get("project", {})
        return {
            "currency": str(project_data.get("currency") or ""),
            "total_price_net": str(project_data.get("total_price_net") or ""),
            "total_price_tax": str(project_data.get("total_price_tax") or ""),
            "total_price_gross": str(project_data.get("total_price_gross") or ""),
        }

    base_totals = totals(base_snapshot)
    head_totals = totals(head_snapshot)
    # A monetary delta across currencies would be a conversion, not a
    # comparison — only same-currency totals produce one.
    price_delta = None
    if base_totals["currency"] and base_totals["currency"] == head_totals["currency"]:
        try:
            price_delta = str(
                D(str(head_totals["total_price_gross"]))
                - D(str(base_totals["total_price_gross"]))
            )
        except Exception:
            price_delta = None
    return {
        "project_id": str(project["id"]),
        "project_code": str(project["code"]),
        "base": {
            "revision_code": base_code,
            "emitted_at": versions[base_code]["emitted_at"].isoformat(),
            "integrity": base_integrity,
            **base_totals,
        },
        "head": {
            "revision_code": head_code,
            "emitted_at": versions[head_code]["emitted_at"].isoformat(),
            "integrity": head_integrity,
            **head_totals,
        },
        "summary": {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
            "price_gross_delta": price_delta,
        },
        "positions": entries,
    }
