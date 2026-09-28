from __future__ import annotations

from decimal import Decimal

import pytest

from dekopen_engine.contour import Contour
from dekopen_engine.models import (
    BayOpeningType,
    EffectiveProfileArticle,
    MaterialType,
    NodeType,
    ParametricNode,
    PlanPoint,
    ProfileRole,
    SlidingLayout,
    SlidingPanel,
    SlidingPanelKind,
    SystemParams,
)
from dekopen_engine.product import (
    ConnectionKind,
    CoupledAssembly,
    CouplingDef,
    EdgeSide,
    IssueCode,
    ProductModel,
    ProductModule,
    ProductStatus,
    Severity,
    coupling_ids,
    equalize_coupling_angles,
    equalize_module_widths,
    elevation_envelope,
    evaluate_product,
    make_bow_assembly,
    module_ids,
    nominal_height_mm,
    nominal_width_mm,
    set_coupler_sku,
    set_coupling_angle,
    set_module_count,
    set_module_opening,
    set_module_width,
)
from dekopen_engine.trig import cos_degrees, sin_degrees

GLASS_4_MM = Decimal("4.00")
GLASS_4_SPEC = "4"

COUPLER_ARTICLE = EffectiveProfileArticle(
    sku="ACOPLE-60",
    role=ProfileRole.COUPLER,
    material=MaterialType.PVC,
    face_width_mm=Decimal("40.00"),
    welding_loss_mm=Decimal("0.00"),
    reinforcement_gap_mm=Decimal("0.00"),
    weight_kg_m=Decimal("0.9000"),
    steel_weight_kg_m=None,
    reinforcement_sku="REF-ACOPLE",
)


def bow_3(module_count: int = 3) -> ProductModel:
    return make_bow_assembly(
        module_count=module_count,
        width_mm=Decimal("2100"),
        height_mm=Decimal("1400"),
        angle_deg=Decimal("15"),
        glass_thickness_mm=GLASS_4_MM,
        glass_spec=GLASS_4_SPEC,
    )


def with_couplers(
    product: ProductModel, sku: str | None = "ACOPLE-60"
) -> ProductModel:
    for coupling in product.assembly.couplings:
        product = set_coupler_sku(product, coupling.id, sku)
    return product


class TestTrig:
    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            ("0", "0"),
            ("30", "0.5"),
            ("45", "0.70710678118654752440"),
            ("60", "0.86602540378443864676"),
            ("90", "1"),
            ("180", "0"),
            ("270", "-1"),
            ("-30", "-0.5"),
            ("360", "0"),
            ("450", "1"),
        ],
    )
    def test_sin(self, degrees: str, expected: str) -> None:
        assert abs(sin_degrees(Decimal(degrees)) - Decimal(expected)) < Decimal(
            "1e-16"
        )

    @pytest.mark.parametrize(
        ("degrees", "expected"),
        [
            ("0", "1"),
            ("60", "0.5"),
            ("90", "0"),
            ("120", "-0.5"),
            ("180", "-1"),
            ("-90", "0"),
            ("360", "1"),
        ],
    )
    def test_cos(self, degrees: str, expected: str) -> None:
        assert abs(cos_degrees(Decimal(degrees)) - Decimal(expected)) < Decimal(
            "1e-16"
        )


class TestConstruction:
    def test_make_bow(self) -> None:
        product = bow_3()
        assert module_ids(product) == ["m1", "m2", "m3"]
        assert coupling_ids(product) == ["c1", "c2"]
        assert nominal_width_mm(product) == Decimal("2100")
        assert nominal_height_mm(product) == Decimal("1400")
        widths = [m.width_mm for m in product.assembly.modules]
        assert sum(widths) == Decimal("2100")

    def test_make_bow_requires_two_modules(self) -> None:
        with pytest.raises(ValueError):
            bow_3(module_count=1)


class TestEvaluation:
    def test_bow_without_coupler_is_geometry_valid_manufacturing_incomplete(
        self, demo_60_params: SystemParams
    ) -> None:
        evaluation = evaluate_product(bow_3(), demo_60_params)
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE
        assert evaluation.plan is not None
        assert len(evaluation.plan.modules) == 3
        assert len(evaluation.plan.couplings) == 2
        missing = [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.COUPLER_PROFILE_MISSING.value
        ]
        assert len(missing) == 2
        # Module geometry still resolves into a BOM.
        assert evaluation.bom is not None
        assert any(
            cut.sku == "MARCO" for cut in evaluation.bom.profile_cuts
        )

    def test_bow_with_couplers_is_valid(self, demo_60_params: SystemParams) -> None:
        product = with_couplers(bow_3())
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.issues == []
        assert evaluation.bom is not None
        coupler_cuts = [
            cut
            for cut in evaluation.bom.profile_cuts
            if cut.role is ProfileRole.COUPLER
        ]
        assert len(coupler_cuts) == 2
        assert all(cut.sku == "ACOPLE-60" for cut in coupler_cuts)
        assert all(cut.length_mm == Decimal("1400") for cut in coupler_cuts)
        # Coupler cuts serialize at the canonical 1dp angle scale so stored,
        # priced and recomputed BOM payloads compare equal.
        assert all(str(cut.angle_left) == "90.0" for cut in coupler_cuts)
        assert all(str(cut.angle_right) == "90.0" for cut in coupler_cuts)
        reinf = [
            piece
            for piece in evaluation.bom.reinforcements
            if piece.role is ProfileRole.COUPLER
        ]
        assert [p.reinforcement_sku for p in reinf] == ["REF-ACOPLE"] * 2

    def test_unknown_coupler_sku_is_reported_never_faked(
        self, demo_60_params: SystemParams
    ) -> None:
        product = with_couplers(bow_3(), sku="DOES-NOT-EXIST")
        evaluation = evaluate_product(product, demo_60_params, coupler_articles={})
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE
        codes = {issue.code for issue in evaluation.issues}
        assert codes == {IssueCode.COUPLER_PROFILE_UNKNOWN.value}

    def test_height_mismatch_marks_coupling_incomplete(
        self, demo_60_params: SystemParams
    ) -> None:
        product = with_couplers(bow_3())
        m2 = product.assembly.modules[1].model_copy(
            update={"height_mm": Decimal("1200")}
        )
        product = product.model_copy(
            update={
                "assembly": product.assembly.model_copy(
                    update={
                        "modules": [
                            product.assembly.modules[0],
                            m2,
                            product.assembly.modules[2],
                        ]
                    }
                )
            }
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE
        mismatched = {
            issue.target
            for issue in evaluation.issues
            if issue.code == IssueCode.COUPLER_HEIGHT_MISMATCH.value
        }
        assert mismatched == {"coupling:c1", "coupling:c2"}

    def test_module_geometry_failure_is_a_warning(
        self, demo_60_params: SystemParams
    ) -> None:
        # DOOR_ENTRY requires a panel SKU the module does not declare.
        product = set_module_opening(bow_3(), "m2", BayOpeningType.DOOR_ENTRY)
        evaluation = evaluate_product(product, demo_60_params)
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE
        failed = [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.MODULE_GEOMETRY_FAILED.value
        ]
        assert len(failed) == 1
        assert failed[0].target == "module:m2"
        m2_eval = next(m for m in evaluation.modules if m.module_id == "m2")
        assert m2_eval.result is None

    def test_excessive_turn_is_invalid(self, demo_60_params: SystemParams) -> None:
        product = equalize_coupling_angles(bow_3(), Decimal("95"))
        evaluation = evaluate_product(product, demo_60_params)
        assert evaluation.status is ProductStatus.INVALID
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.ASSEMBLY_FOLDS_BACK.value in codes

    def test_coupler_reinforcement_uses_gap_adjusted_length(
        self, demo_60_params: SystemParams
    ) -> None:
        coupler = COUPLER_ARTICLE.model_copy(
            update={"reinforcement_gap_mm": Decimal("15.00")}
        )
        evaluation = evaluate_product(
            with_couplers(bow_3()),
            demo_60_params,
            coupler_articles={"ACOPLE-60": coupler},
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None
        steel = [
            piece
            for piece in evaluation.bom.reinforcements
            if piece.parent_profile_sku == "ACOPLE-60"
        ]
        assert len(steel) == 2
        # height 1400 - 2*15 gap; coupler posts are square-cut (no weld loss)
        assert {piece.length_mm for piece in steel} == {Decimal("1370.00")}

    def test_coupler_reinforcement_nonpositive_is_flagged(
        self, demo_60_params: SystemParams
    ) -> None:
        coupler = COUPLER_ARTICLE.model_copy(
            update={"reinforcement_gap_mm": Decimal("700.00")}
        )
        evaluation = evaluate_product(
            with_couplers(bow_3()),
            demo_60_params,
            coupler_articles={"ACOPLE-60": coupler},
        )
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE
        assert any(
            issue.code == IssueCode.COUPLER_REINFORCEMENT_NONPOSITIVE.value
            for issue in evaluation.issues
        )
        assert evaluation.bom is not None
        assert not any(
            piece.parent_profile_sku == "ACOPLE-60"
            for piece in evaluation.bom.reinforcements
        )

    def test_duplicate_coupling_ids_raise(
        self, demo_60_params: SystemParams
    ) -> None:
        product = bow_3()
        product = product.model_copy(
            update={
                "assembly": product.assembly.model_copy(
                    update={
                        "couplings": [
                            product.assembly.couplings[0],
                            product.assembly.couplings[0],
                        ]
                    }
                )
            }
        )
        with pytest.raises(ValueError, match="unique"):
            evaluate_product(product, demo_60_params)

    def test_couplings_count_mismatch_is_invalid(
        self, demo_60_params: SystemParams
    ) -> None:
        product = bow_3()
        product = product.model_copy(
            update={
                "assembly": product.assembly.model_copy(
                    update={"couplings": product.assembly.couplings[:1]}
                )
            }
        )
        evaluation = evaluate_product(product, demo_60_params)
        assert evaluation.status is ProductStatus.INVALID
        assert any(
            issue.code == IssueCode.COUPLINGS_COUNT_MISMATCH.value
            and issue.severity is Severity.ERROR
            for issue in evaluation.issues
        )

    def test_plan_depth_overlap_is_invalid(
        self, demo_60_params: SystemParams
    ) -> None:
        # Three 200 mm modules folding -85°/-85° on a deep (300 mm) system:
        # m3 swings back over m1 so their depth rectangles collide even
        # though no front-chain segments cross.
        deep = demo_60_params.model_copy(update={"depth_mm": Decimal("300.00")})
        product = make_bow_assembly(
            module_count=3,
            width_mm=Decimal("600"),
            height_mm=Decimal("1400"),
            angle_deg=Decimal("-85"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        evaluation = evaluate_product(product, deep)
        assert evaluation.status is ProductStatus.INVALID
        assert any(
            issue.code == IssueCode.PLAN_SELF_INTERSECTION.value
            and issue.severity is Severity.ERROR
            for issue in evaluation.issues
        )

    def test_plan_depth_no_false_positive_on_shallow_system(
        self, demo_60_params: SystemParams
    ) -> None:
        # Same fold magnitude in the positive direction on the real 60 mm
        # depth: the assembly fans outward so modules stay clear of each other.
        product = make_bow_assembly(
            module_count=3,
            width_mm=Decimal("600"),
            height_mm=Decimal("1400"),
            angle_deg=Decimal("85"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        evaluation = evaluate_product(product, demo_60_params)
        assert not any(
            issue.code == IssueCode.PLAN_SELF_INTERSECTION.value
            for issue in evaluation.issues
        )

    def test_plan_adjacent_negative_angle_is_invalid(
        self, demo_60_params: SystemParams
    ) -> None:
        # A negative deflection swings the next module's depth rectangle into
        # the previous one — a real collision at the joint even on the shallow
        # 60 mm system, with no front-chain crossing.
        product = make_bow_assembly(
            module_count=2,
            width_mm=Decimal("400"),
            height_mm=Decimal("1400"),
            angle_deg=Decimal("-20"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        evaluation = evaluate_product(product, demo_60_params)
        assert evaluation.status is ProductStatus.INVALID
        assert any(
            issue.code == IssueCode.PLAN_SELF_INTERSECTION.value
            and issue.severity is Severity.ERROR
            for issue in evaluation.issues
        )

    def test_plan_straight_and_positive_joints_stay_clean(
        self, demo_60_params: SystemParams
    ) -> None:
        # Adjacent rectangles share only their joint boundary at 0° and fan
        # apart at positive angles — neither is a collision.
        for angle in (Decimal("0"), Decimal("20")):
            product = make_bow_assembly(
                module_count=2,
                width_mm=Decimal("400"),
                height_mm=Decimal("1400"),
                angle_deg=angle,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            )
            evaluation = evaluate_product(product, demo_60_params)
            assert not any(
                issue.code == IssueCode.PLAN_SELF_INTERSECTION.value
                for issue in evaluation.issues
            ), f"angle {angle} must not collide"

    def test_plan_polygon_shape(self, demo_60_params: SystemParams) -> None:
        evaluation = evaluate_product(bow_3(), demo_60_params)
        plan = evaluation.plan
        assert plan is not None
        # 3 modules, 4 corners each; coupler wedges between them.
        for module in plan.modules:
            assert len(module.corners) == 4
        for coupling in plan.couplings:
            assert len(coupling.polygon) == 3
        # Bow with +15° joints curves upward: overall depth exceeds 60 mm.
        assert plan.height_mm > Decimal("60")
        # Front chain has 4 vertices: module 1 is the baseline (flat),
        # then the chain turns +15° at each coupling.
        assert len(plan.front_chain) == 4
        ys = [p.y_mm for p in plan.front_chain]
        assert ys[0] == ys[1] == Decimal("0.00")
        assert ys[2] > ys[1] and ys[3] > ys[2]

    def test_traceable_bay_ids_are_module_prefixed(
        self, demo_60_params: SystemParams
    ) -> None:
        evaluation = evaluate_product(
            with_couplers(bow_3()),
            demo_60_params,
            coupler_articles={"ACOPLE-60": COUPLER_ARTICLE},
        )
        assert evaluation.bom is not None
        bay_ids = {
            cut.bay_id for cut in evaluation.bom.profile_cuts if cut.bay_id
        }
        assert any(bay_id.startswith("m1|") for bay_id in bay_ids)
        assert {"c1", "c2"} <= bay_ids

    def test_bom_prefixes_panel_leaf_ids(
        self, demo_60_params: SystemParams
    ) -> None:
        product = make_bow_assembly(
            module_count=3,
            width_mm=Decimal("2100"),
            height_mm=Decimal("2000"),
            angle_deg=Decimal("15"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        product = set_module_opening(product, "m2", BayOpeningType.DOOR_ENTRY)
        product = set_module_width(product, "m2", Decimal("950"))
        modules = [
            module.model_copy(
                update={
                    "tree": module.tree.model_copy(
                        update={
                            "panel_article_sku": "PANEL-SANDWICH-DEMO-24",
                            "glass_thickness_mm": None,
                            "glass_spec": None,
                        }
                    )
                }
            )
            if module.id == "m2"
            else module
            for module in product.assembly.modules
        ]
        product = product.model_copy(
            update={
                "assembly": product.assembly.model_copy(
                    update={"modules": modules}
                )
            }
        )
        evaluation = evaluate_product(
            with_couplers(product),
            demo_60_params,
            coupler_articles={"ACOPLE-60": COUPLER_ARTICLE},
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None and evaluation.bom.panels
        assert all(
            panel.bay_id.startswith("m2|")
            and (panel.leaf_id is None or panel.leaf_id.startswith("m2|"))
            for panel in evaluation.bom.panels
        )


class TestCommands:
    def test_set_module_count_grows_and_shrinks(self) -> None:
        product = bow_3()
        grown = set_module_count(product, 5)
        assert len(grown.assembly.modules) == 5
        assert len(grown.assembly.couplings) == 4
        assert grown.assembly.couplings[-1].angle_deg == Decimal("15")
        shrunk = set_module_count(grown, 2)
        assert module_ids(shrunk) == ["m1", "m2"]
        assert coupling_ids(shrunk) == ["c1"]

    def test_equalize_widths_preserves_total(self) -> None:
        product = set_module_width(bow_3(), "m1", Decimal("900"))
        product = equalize_module_widths(product)
        widths = [m.width_mm for m in product.assembly.modules]
        assert sum(widths) == Decimal("2300")
        assert max(widths) - min(widths) <= Decimal("0.01")

    def test_commands_are_pure_and_return_new_models(self) -> None:
        product = bow_3()
        updated = set_coupling_angle(product, "c1", Decimal("20"))
        assert updated.assembly.couplings[0].angle_deg == Decimal("20")
        assert product.assembly.couplings[0].angle_deg == Decimal("15")

    def test_single_unit_is_a_degenerate_assembly(
        self, demo_60_params: SystemParams
    ) -> None:
        product = make_bow_assembly(
            module_count=2,
            width_mm=Decimal("1000"),
            height_mm=Decimal("1200"),
            angle_deg=Decimal("0"),
            glass_thickness_mm=GLASS_4_MM,
            glass_spec=GLASS_4_SPEC,
        )
        unit = set_module_count(product, 1)
        assert len(unit.assembly.couplings) == 0
        evaluation = evaluate_product(unit, demo_60_params)
        assert evaluation.status is ProductStatus.VALID


class TestConnections:
    """§6 general connection model: kinds, explicit endpoints, edge claims."""

    @staticmethod
    def _module(module_id: str, width: str, height: str) -> ProductModule:
        return ProductModule(
            id=module_id,
            width_mm=Decimal(width),
            height_mm=Decimal(height),
            tree=ParametricNode(
                id=module_id,
                type=NodeType.BAY,
                opening_type=BayOpeningType.FIXED,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
        )

    def _product(
        self, modules: list[ProductModule], couplings: list[CouplingDef]
    ) -> ProductModel:
        return ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(modules=modules, couplings=couplings),
        )

    def test_stacked_transom_projects_onto_its_column(
        self, demo_60_params: SystemParams
    ) -> None:
        # door 1000x2200 + transom 1000x400 stacked above: same plan footprint,
        # horizontal coupler cut spans the shared WIDTH (1000), not the height.
        product = self._product(
            [self._module("door", "1000", "2200"), self._module("tr", "1000", "400")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    modules=["door", "tr"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None and evaluation.plan is not None
        coupler = next(
            c for c in evaluation.bom.profile_cuts if c.role is ProfileRole.COUPLER
        )
        assert coupler.length_mm == Decimal("1000")
        # The anchored transom shares the door's plan slot — no second column.
        corners = {m.module_id: m.corners for m in evaluation.plan.modules}
        assert corners["tr"] == corners["door"]

    def test_storefront_door_transom_sidelight_validates(
        self, demo_60_params: SystemParams
    ) -> None:
        # The §36-E composition: door + transom over it + sidelight beside the
        # door + transom over the sidelight — two stacked columns beside.
        product = self._product(
            [
                self._module("door", "1000", "2200"),
                self._module("trL", "1000", "400"),
                self._module("sl", "600", "2200"),
                self._module("trR", "600", "400"),
            ],
            [
                CouplingDef(
                    id="s1", kind=ConnectionKind.STACKED, modules=["door", "trL"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM], coupler_profile_sku="ACOPLE-60",
                ),
                CouplingDef(
                    id="s2", kind=ConnectionKind.STACKED, modules=["sl", "trR"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM], coupler_profile_sku="ACOPLE-60",
                ),
                CouplingDef(
                    id="i1", kind=ConnectionKind.INLINE, modules=["door", "sl"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT], coupler_profile_sku="ACOPLE-60",
                ),
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None
        spans = sorted(
            c.length_mm for c in evaluation.bom.profile_cuts if c.role is ProfileRole.COUPLER
        )
        assert spans == [Decimal("600"), Decimal("1000"), Decimal("2200")]

    def test_tee_is_declared_but_honestly_unsupported(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "2000")],
            [
                CouplingDef(
                    id="t1", kind=ConnectionKind.TEE, modules=["a", "b"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                )
            ],
        )
        evaluation = evaluate_product(product, demo_60_params)
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.CONNECTION_TYPE_UNSUPPORTED.value in codes
        assert evaluation.bom is not None
        # No coupler cut was fabricated for the unsupported joint.
        assert not any(
            c.role is ProfileRole.COUPLER for c in evaluation.bom.profile_cuts
        )

    def test_stacked_width_mismatch_flags(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1200", "2000")],
            [
                CouplingDef(
                    id="s1", kind=ConnectionKind.STACKED, modules=["a", "b"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM], coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        mismatched = [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.COUPLER_WIDTH_MISMATCH.value
        ]
        assert len(mismatched) == 1
        assert mismatched[0].params["below_mm"] == "1000"

    def test_edge_claim_conflict_flags_second_coupling(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [
                self._module("a", "1000", "2000"),
                self._module("b", "1000", "400"),
                self._module("c", "1000", "400"),
            ],
            [
                CouplingDef(
                    id="s1", kind=ConnectionKind.STACKED, modules=["a", "b"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM], coupler_profile_sku="ACOPLE-60",
                ),
                CouplingDef(
                    id="s2", kind=ConnectionKind.STACKED, modules=["a", "c"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM], coupler_profile_sku="ACOPLE-60",
                ),
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        conflicts = [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.COUPLER_EDGE_CONFLICT.value
        ]
        assert len(conflicts) == 1 and conflicts[0].target == "coupling:s2"

    def test_unknown_module_endpoint_flags(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "2000")],
            [
                CouplingDef(
                    id="x1", kind=ConnectionKind.INLINE, modules=["a", "ghost"],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.COUPLER_MODULE_UNKNOWN.value in codes

    def test_positional_stacked_coupling_keeps_legacy_binding(
        self, demo_60_params: SystemParams
    ) -> None:
        # No explicit endpoints: a STACKED positional coupling binds modules
        # i.top to i+1.bottom — module i+1 becomes the upper member.
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "400")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None
        coupler = next(
            c for c in evaluation.bom.profile_cuts if c.role is ProfileRole.COUPLER
        )
        assert coupler.length_mm == Decimal("1000")

    def test_wrong_sides_for_kind_rejected(
        self, demo_60_params: SystemParams
    ) -> None:
        # An INLINE joint between top/bottom edges is not an inline coupling.
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "2000")],
            [
                CouplingDef(
                    id="x1", kind=ConnectionKind.INLINE, modules=["a", "b"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.COUPLER_EDGE_INVALID.value in codes

    def test_missing_couplings_disconnect_the_assembly(
        self, demo_60_params: SystemParams
    ) -> None:
        # Two modules, zero joints: two separate frames, never one product.
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "2000")],
            [],
        )
        evaluation = evaluate_product(product, demo_60_params)
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.ASSEMBLY_DISCONNECTED.value in codes
        assert evaluation.status is ProductStatus.INVALID

    def test_explicit_graph_must_reach_every_module(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [
                self._module("a", "1000", "2000"),
                self._module("b", "1000", "2000"),
                self._module("c", "1000", "2000"),
            ],
            [
                CouplingDef(
                    id="x1", kind=ConnectionKind.INLINE, modules=["a", "b"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        codes = {issue.code for issue in evaluation.issues}
        assert IssueCode.ASSEMBLY_DISCONNECTED.value in codes

    def test_stacked_layout_is_order_independent(
        self, demo_60_params: SystemParams
    ) -> None:
        # The transom declared BEFORE its column still projects onto the
        # door's footprint — declaration order cannot change the plan.
        couplings = [
            CouplingDef(
                id="s1",
                kind=ConnectionKind.STACKED,
                modules=["door", "tr"],
                edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                coupler_profile_sku="ACOPLE-60",
            )
        ]
        forward = self._product(
            [self._module("door", "1000", "2200"), self._module("tr", "1000", "400")],
            couplings,
        )
        reversed_order = self._product(
            [self._module("tr", "1000", "400"), self._module("door", "1000", "2200")],
            couplings,
        )
        first = evaluate_product(
            forward, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        second = evaluate_product(
            reversed_order,
            demo_60_params,
            coupler_articles={"ACOPLE-60": COUPLER_ARTICLE},
        )
        assert first.plan is not None and second.plan is not None
        corners = {
            module.module_id: module.corners for module in second.plan.modules
        }
        assert corners["tr"] == corners["door"]
        door_corners = next(
            module.corners
            for module in first.plan.modules
            if module.module_id == "door"
        )
        assert corners["door"] == door_corners

    def test_stacked_columns_derive_the_elevation_envelope(
        self, demo_60_params: SystemParams
    ) -> None:
        # A stacked member shares its column's width and adds its height —
        # the nominal envelope is door 1000x2200 + transom 400 → 1000x2600.
        product = self._product(
            [self._module("door", "1000", "2200"), self._module("tr", "1000", "400")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    modules=["door", "tr"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                )
            ],
        )
        assert elevation_envelope(product.assembly) == (
            Decimal("1000"),
            Decimal("2600"),
        )
        # Order-independent: the transom declared first resolves the same root.
        product = self._product(
            [self._module("tr", "1000", "400"), self._module("door", "1000", "2200")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    modules=["door", "tr"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                )
            ],
        )
        assert elevation_envelope(product.assembly) == (
            Decimal("1000"),
            Decimal("2600"),
        )

    def test_inline_angle_binds_the_joint_it_names(
        self, demo_60_params: SystemParams
    ) -> None:
        # Couplings declared out of chain order: {a,b} turns 5°, {c,d} turns
        # 10°, and the b→c joint stays straight. The angle must land on the
        # joint the coupling names — never on a declaration position.
        product = self._product(
            [
                self._module("a", "1000", "2200"),
                self._module("b", "1000", "2200"),
                self._module("c", "1000", "2200"),
                self._module("d", "1000", "2200"),
            ],
            [
                CouplingDef(
                    id="cd",
                    angle_deg=Decimal("10"),
                    modules=["c", "d"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                ),
                CouplingDef(
                    id="ab",
                    angle_deg=Decimal("5"),
                    modules=["a", "b"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                ),
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.plan is not None
        corners = {m.module_id: m.corners for m in evaluation.plan.modules}
        # b runs at 5° from the a→b joint; c inherits the same heading (the
        # b→c joint declares no coupling); d accumulates to 15°.
        single = Decimal("1000") * sin_degrees(Decimal("5"))
        assert corners["b"][1].y_mm == single.quantize(Decimal("0.01"))
        assert corners["c"][1].y_mm == (single * 2).quantize(Decimal("0.01"))
        expected_d = (single * 2 + Decimal("1000") * sin_degrees(Decimal("15"))).quantize(
            Decimal("0.01")
        )
        assert corners["d"][1].y_mm == expected_d

    def test_stacked_wider_member_widens_the_envelope(
        self, demo_60_params: SystemParams
    ) -> None:
        # A stacked member wider than its column centre-and-protrudes: the
        # nominal envelope spans the member extent, not the column band.
        product = self._product(
            [self._module("door", "900", "2100"), self._module("tr", "1200", "400")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    modules=["door", "tr"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                )
            ],
        )
        assert elevation_envelope(product.assembly) == (
            Decimal("1200"),
            Decimal("2500"),
        )

    def test_stacked_cycle_is_invalid(self, demo_60_params: SystemParams) -> None:
        # a hangs over b's top while b hangs over a's top — neither module has
        # a physical bottom. The union sees one connected assembly, so without
        # a dedicated error the impossible stack would evaluate VALID.
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "1000", "2000")],
            [
                CouplingDef(
                    id="s1",
                    kind=ConnectionKind.STACKED,
                    modules=["a", "b"],
                    edges=[EdgeSide.TOP, EdgeSide.BOTTOM],
                ),
                CouplingDef(
                    id="s2",
                    kind=ConnectionKind.STACKED,
                    modules=["a", "b"],
                    edges=[EdgeSide.BOTTOM, EdgeSide.TOP],
                ),
            ],
        )
        evaluation = evaluate_product(product, demo_60_params)
        assert evaluation.status is ProductStatus.INVALID
        assert IssueCode.STACKED_CYCLE.value in {issue.code for issue in evaluation.issues}

    def test_nonadjacent_inline_coupling_is_invalid(
        self, demo_60_params: SystemParams
    ) -> None:
        # a–c bridges over b: the front lays columns a,b,c so a–c has no
        # physical seam — connectivity alone would accept it and the BOM would
        # still cut a coupler for a joint that cannot exist.
        product = self._product(
            [
                self._module("a", "1000", "2000"),
                self._module("b", "800", "2000"),
                self._module("c", "1000", "2000"),
            ],
            [
                CouplingDef(
                    id="ac",
                    kind=ConnectionKind.INLINE,
                    modules=["a", "c"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                ),
                CouplingDef(
                    id="bc",
                    kind=ConnectionKind.INLINE,
                    modules=["b", "c"],
                    edges=[EdgeSide.LEFT, EdgeSide.RIGHT],
                    coupler_profile_sku="ACOPLE-60",
                ),
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.INVALID
        flagged = {
            issue.target
            for issue in evaluation.issues
            if issue.code == IssueCode.INLINE_NOT_ADJACENT.value
        }
        assert flagged == {"coupling:ac"}

    def test_adjacent_inline_couplings_still_validate(
        self, demo_60_params: SystemParams
    ) -> None:
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "800", "2000")],
            [
                CouplingDef(
                    id="ab",
                    kind=ConnectionKind.INLINE,
                    modules=["a", "b"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID

    def test_reversed_inline_edges_claim_outer_seam(
        self, demo_60_params: SystemParams
    ) -> None:
        # modules=[b,a] with edges=[right,left] names b's outer right and a's
        # outer left — no seam exists there; only the side-set check let it
        # through before.
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "800", "2000")],
            [
                CouplingDef(
                    id="ba",
                    kind=ConnectionKind.INLINE,
                    modules=["b", "a"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        flagged = {
            issue.target
            for issue in evaluation.issues
            if issue.code == IssueCode.COUPLER_EDGE_INVALID.value
        }
        assert flagged == {"coupling:ba"}
        assert evaluation.bom is not None
        assert not any(
            c.role is ProfileRole.COUPLER for c in evaluation.bom.profile_cuts
        )

    def test_reversed_module_order_inline_pair_still_cuts(
        self, demo_60_params: SystemParams
    ) -> None:
        # The same seam declared right-column first is valid — the edges just
        # have to mirror the column order (b.left meets a.right).
        product = self._product(
            [self._module("a", "1000", "2000"), self._module("b", "800", "2000")],
            [
                CouplingDef(
                    id="ba",
                    kind=ConnectionKind.INLINE,
                    modules=["b", "a"],
                    edges=[EdgeSide.LEFT, EdgeSide.RIGHT],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        assert evaluation.status is ProductStatus.VALID
        assert evaluation.bom is not None
        coupler = next(
            c for c in evaluation.bom.profile_cuts if c.role is ProfileRole.COUPLER
        )
        assert coupler.length_mm == Decimal("2000")

    def test_contour_module_refuses_couplings(
        self, demo_60_params: SystemParams
    ) -> None:
        # A contour edge is a shaped boundary: even a straight side edge is
        # shorter than the nominal box, so no straight coupler closes it.
        shaped = ProductModule(
            id="tr",
            width_mm=Decimal("1000"),
            height_mm=Decimal("2000"),
            contour=Contour(
                vertices=[
                    PlanPoint(x_mm=Decimal("0"), y_mm=Decimal("0")),
                    PlanPoint(x_mm=Decimal("1000"), y_mm=Decimal("0")),
                    PlanPoint(x_mm=Decimal("1000"), y_mm=Decimal("1800")),
                    PlanPoint(x_mm=Decimal("0"), y_mm=Decimal("2000")),
                ],
                bulges=[Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")],
            ),
            tree=ParametricNode(
                id="tr",
                type=NodeType.BAY,
                opening_type=BayOpeningType.FIXED,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
        )
        product = self._product(
            [self._module("a", "1000", "2000"), shaped],
            [
                CouplingDef(
                    id="ab",
                    kind=ConnectionKind.INLINE,
                    modules=["a", "tr"],
                    edges=[EdgeSide.RIGHT, EdgeSide.LEFT],
                    coupler_profile_sku="ACOPLE-60",
                )
            ],
        )
        evaluation = evaluate_product(
            product, demo_60_params, coupler_articles={"ACOPLE-60": COUPLER_ARTICLE}
        )
        flagged = {
            issue.target
            for issue in evaluation.issues
            if issue.code == IssueCode.CONTOUR_COUPLING_UNSUPPORTED.value
        }
        assert flagged == {"coupling:ab"}
        assert evaluation.bom is not None
        assert not any(
            c.role is ProfileRole.COUPLER for c in evaluation.bom.profile_cuts
        )


class TestSlidingTopologyEvaluation:
    def _sliding_module(self, layout: "SlidingLayout | None") -> ProductModule:
        return ProductModule(
            id="s",
            width_mm=Decimal("1800"),
            height_mm=Decimal("1500"),
            tree=ParametricNode(
                id="s",
                type=NodeType.BAY,
                opening_type=BayOpeningType.SLIDING,
                sliding_layout=layout,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
        )

    def test_sliding_facts_describe_the_resolved_topology(
        self, demo_60_params: SystemParams
    ) -> None:
        product = ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(
                modules=[
                    self._sliding_module(
                        SlidingLayout(
                            tracks=2,
                            panels=[
                                SlidingPanel(slot="fijo", kind=SlidingPanelKind.FIXED),
                                SlidingPanel(
                                    slot="corrediza",
                                    kind=SlidingPanelKind.MOVING,
                                    track=0,
                                ),
                                SlidingPanel(
                                    slot="corrediza2",
                                    kind=SlidingPanelKind.MOVING,
                                    track=1,
                                ),
                            ],
                        )
                    )
                ],
                couplings=[],
            ),
        )
        evaluation = evaluate_product(product, demo_60_params)
        module = evaluation.modules[0]
        assert module.sliding[0].bay_id == "s"
        assert module.sliding[0].tracks == 2
        assert [(p.slot, p.kind, p.track, p.leaf_id) for p in module.sliding[0].panels] == [
            ("fijo", SlidingPanelKind.FIXED, None, None),
            ("corrediza", SlidingPanelKind.MOVING, 0, "s:L2"),
            ("corrediza2", SlidingPanelKind.MOVING, 1, "s:L3"),
        ]
        leaf_ids = {
            cut.leaf_id for cut in (module.result.profile_cuts if module.result else [])
            if cut.leaf_id
        }
        assert leaf_ids == {"s:L2", "s:L3", "s:fijo"}

    def test_sliding_layout_errors_surface_as_issues(
        self, demo_60_params: SystemParams
    ) -> None:
        product = ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(
                modules=[self._sliding_module(None)], couplings=[]
            ),
        )
        evaluation = evaluate_product(product, demo_60_params)
        module = evaluation.modules[0]
        assert module.result is None
        assert [i.code for i in module.issues] == [
            IssueCode.SLIDING_LAYOUT_INVALID.value
        ]
        assert module.issues[0].severity is Severity.ERROR
        assert "sliding_layout" in module.issues[0].params["reason"]


class TestStockLength:
    """A member longer than the bar its article sells in cannot be produced —
    the catalog's commercial_length_mm is the authority, the issue is a
    warning (splice/order is a human call) not an invalidation."""

    @staticmethod
    def _module(module_id: str, width: str, height: str) -> ProductModule:
        return ProductModule(
            id=module_id,
            width_mm=Decimal(width),
            height_mm=Decimal(height),
            tree=ParametricNode(
                id=module_id,
                type=NodeType.BAY,
                opening_type=BayOpeningType.FIXED,
                glass_thickness_mm=GLASS_4_MM,
                glass_spec=GLASS_4_SPEC,
            ),
        )

    @staticmethod
    def _params_with_stock(
        params: SystemParams, stock: str | None
    ) -> SystemParams:
        articles = {
            role: article.model_copy(
                update={"commercial_length_mm": Decimal(stock) if stock else None}
            )
            for role, article in params.effective_profile_articles.items()
        }
        # Bead articles sit inside the rules — strip/set them too so the
        # helper means "stock length everywhere", not just profile roles.
        rules = {
            thickness: rule.model_copy(
                update={
                    "bead_article": rule.bead_article.model_copy(
                        update={
                            "commercial_length_mm": Decimal(stock)
                            if stock
                            else None
                        }
                    )
                }
            )
            for thickness, rule in params.glazing_bead_rules.items()
        }
        return params.model_copy(
            update={
                "effective_profile_articles": articles,
                "glazing_bead_rules": rules,
            }
        )

    def test_member_longer_than_stock_flags_warning(
        self, demo_60_params: SystemParams
    ) -> None:
        params = self._params_with_stock(demo_60_params, "6000")
        product = ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(
                modules=[self._module("wide", "7000", "1500")], couplings=[]
            ),
        )
        evaluation = evaluate_product(product, params)
        warnings = [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.MEMBER_EXCEEDS_STOCK.value
        ]
        assert warnings
        assert all(issue.severity is Severity.WARNING for issue in warnings)
        assert Decimal(warnings[0].params["stock_mm"]) == Decimal("6000")
        assert Decimal(warnings[0].params["length_mm"]) > Decimal("6000")
        assert evaluation.status is ProductStatus.MANUFACTURING_INCOMPLETE

    def test_undeclared_stock_does_not_flag(
        self, demo_60_params: SystemParams
    ) -> None:
        # No commercial_length_mm anywhere → UNKNOWN, not infinite bars: the
        # check stays silent instead of inventing a bound.
        params = self._params_with_stock(demo_60_params, None)
        product = ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(
                modules=[self._module("wide", "7000", "1500")], couplings=[]
            ),
        )
        evaluation = evaluate_product(product, params)
        assert not [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.MEMBER_EXCEEDS_STOCK.value
        ]

    def test_member_within_stock_passes_clean(
        self, demo_60_params: SystemParams
    ) -> None:
        params = self._params_with_stock(demo_60_params, "6000")
        product = ProductModel(
            version="product-v2",
            assembly=CoupledAssembly(
                modules=[self._module("normal", "2000", "1500")], couplings=[]
            ),
        )
        evaluation = evaluate_product(product, params)
        assert not [
            issue
            for issue in evaluation.issues
            if issue.code == IssueCode.MEMBER_EXCEEDS_STOCK.value
        ]
