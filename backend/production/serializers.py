"""OpenAPI-visible contracts for the production API."""

from __future__ import annotations

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown input fields")
        return super().to_internal_value(data)


class ProductionStepSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    sequence = serializers.IntegerField()
    code = serializers.CharField()
    label = serializers.CharField()
    status = serializers.ChoiceField(
        choices=("PENDING", "READY", "IN_PROGRESS", "DONE", "BLOCKED")
    )
    work_center_id = serializers.UUIDField(allow_null=True)
    work_center_code = serializers.CharField(allow_null=True)
    work_center_name = serializers.CharField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    actor_id = serializers.UUIDField(allow_null=True)
    note = serializers.CharField(allow_null=True)


class ProductionNextStepSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class ProductionOrderSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_code = serializers.CharField()
    order_type = serializers.CharField()
    status = serializers.CharField()
    position_id = serializers.CharField(allow_null=True)
    quantity = serializers.IntegerField(allow_null=True)
    steps_done = serializers.IntegerField()
    steps_total = serializers.IntegerField()
    next_step = ProductionNextStepSerializer(allow_null=True)
    dispatch_ready = serializers.BooleanField()
    shortage = serializers.IntegerField()
    version_shortage = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    project_version_id = serializers.UUIDField(allow_null=True, required=False)
    payload = serializers.DictField(required=False)


class ProductionPrepItemSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    project_id = serializers.UUIDField()
    project_code = serializers.CharField()
    revision_code = serializers.CharField()
    positions = serializers.IntegerField()


class ProductionPrepSerializer(serializers.Serializer):
    versions = ProductionPrepItemSerializer(many=True)


class ProductionReleaseSerializer(serializers.Serializer):
    version_id = serializers.UUIDField()
    released = serializers.IntegerField()
    created = serializers.IntegerField()
    orders = ProductionOrderSerializer(many=True)


class ProductionOrderListSerializer(serializers.Serializer):
    orders = ProductionOrderSerializer(many=True)


class ProductionStepEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    step_id = serializers.UUIDField(allow_null=True)
    step_code = serializers.CharField(allow_null=True, required=False)
    event = serializers.CharField()
    actor_id = serializers.UUIDField(allow_null=True)
    actor_label = serializers.CharField(allow_null=True, required=False)
    payload = serializers.DictField()
    created_at = serializers.DateTimeField()


class ProductionOrderMakingSerializer(serializers.Serializer):
    position_index = serializers.IntegerField(required=False, allow_null=True)
    code = serializers.CharField(required=False, allow_null=True)
    typology = serializers.CharField(required=False, allow_null=True)
    quantity = serializers.IntegerField(required=False, allow_null=True)
    width_mm = serializers.CharField(required=False, allow_null=True)
    height_mm = serializers.CharField(required=False, allow_null=True)
    color_interior = serializers.CharField(required=False, allow_null=True)
    color_exterior = serializers.CharField(required=False, allow_null=True)
    location_tag = serializers.CharField(required=False, allow_null=True)


class ProductionOrderDetailSerializer(ProductionOrderSerializer):
    steps = ProductionStepSerializer(many=True)
    events = ProductionStepEventSerializer(many=True)
    making = ProductionOrderMakingSerializer(allow_null=True, required=False)
    delivery_address = serializers.CharField(allow_null=True, required=False)
    dispatch_note_code = serializers.CharField(allow_null=True, required=False)
    dispatch_note_voided = serializers.BooleanField()
    dispatch_note_dte = serializers.DictField(allow_null=True, required=False)


class QcCheckSerializer(StrictSerializer):
    check = serializers.CharField(max_length=200)
    expected = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    actual = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    item_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    result = serializers.ChoiceField(choices=("PASS", "FAIL"))


class StepTransitionRequestSerializer(StrictSerializer):
    action = serializers.ChoiceField(
        choices=("START", "COMPLETE", "BLOCK", "UNBLOCK", "NOTE", "QC_CHECK")
    )
    note = serializers.CharField(required=False, allow_null=True, max_length=500)
    qc_result = serializers.ChoiceField(choices=("PASS", "FAIL"), required=False, allow_null=True)
    qc_check = QcCheckSerializer(required=False, allow_null=True)
    qc_item = serializers.CharField(max_length=50, required=False, allow_blank=True, allow_null=True)
    ops_done = serializers.ListField(
        child=serializers.CharField(max_length=80),
        required=False,
        allow_null=True,
    )

    def validate(self, data):
        data = super().validate(data)
        if data["action"] == "NOTE" and not (data.get("note") or "").strip():
            raise serializers.ValidationError({"note": "Note text is required for NOTE"})
        if data.get("qc_result") and data["action"] != "COMPLETE":
            raise serializers.ValidationError(
                {"qc_result": "QC outcome only applies to COMPLETE"}
            )
        if data["action"] == "QC_CHECK" and not data.get("qc_check"):
            raise serializers.ValidationError({"qc_check": "QC check payload is required"})
        if data.get("qc_check") and data["action"] != "QC_CHECK":
            raise serializers.ValidationError(
                {"qc_check": "QC check payload only applies to QC_CHECK"}
            )
        if data.get("qc_item") and data.get("qc_result") != "FAIL":
            raise serializers.ValidationError(
                {"qc_item": "A failing item only applies to a QC rejection"}
            )
        if data.get("ops_done") and data["action"] != "COMPLETE":
            raise serializers.ValidationError(
                {"ops_done": "Operation evidence only applies to COMPLETE"}
            )
        return data


class CncExportSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    exported_at = serializers.CharField()
    files = serializers.DictField(child=serializers.CharField())


class DxfExportSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    exported_at = serializers.CharField()
    files = serializers.DictField(child=serializers.CharField())


class OpsExportSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    exported_at = serializers.CharField()
    operation_count = serializers.IntegerField()
    counts_by_kind = serializers.DictField()
    files = serializers.DictField(child=serializers.CharField())


class PackingManifestSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    packing = serializers.DictField()


class DispatchRequestSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InstallationRequestSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DispatchNoteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    note_code = serializers.CharField()
    work_order_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    voided_at = serializers.DateTimeField(allow_null=True)
    voided_reason = serializers.CharField(allow_null=True)


class DispatchNoteAccessSerializer(DispatchNoteSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class DispatchNoteDteEmitSerializer(StrictSerializer):
    # 1 = venta (goods delivered under a sale); 5 = traslado interno.
    ind_traslado = serializers.ChoiceField(choices=(1, 5), default=1)


class DispatchNoteDteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    dispatch_note_id = serializers.UUIDField()
    dte_type = serializers.IntegerField()
    folio = serializers.IntegerField()
    issued_at = serializers.CharField()


class DispatchNoteDteAccessSerializer(DispatchNoteDteSerializer):
    signed_url = serializers.CharField()
    tributario_signed_url = serializers.CharField(allow_null=True)
    expires_in = serializers.IntegerField()


class DispatchNoteVoidSerializer(StrictSerializer):
    reason = serializers.CharField(required=True, allow_blank=False, max_length=500)


class RemakeRequestSerializer(StrictSerializer):
    note = serializers.CharField(required=False, allow_null=True, max_length=500)


class StepTransitionSerializer(serializers.Serializer):
    step = ProductionStepSerializer()
    order_status = serializers.CharField()


class PackingLabelSerializer(serializers.Serializer):
    unit_index = serializers.IntegerField()
    label_code = serializers.CharField()
    pieces = serializers.IntegerField()
    profiles = serializers.IntegerField()
    reinforcements = serializers.IntegerField()
    glasses = serializers.IntegerField()
    panels = serializers.IntegerField()
    hardware = serializers.IntegerField()
    qr_payload = serializers.CharField()
    qr_svg = serializers.CharField()


class PackingLabelsSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    status = serializers.CharField()
    labels = PackingLabelSerializer(many=True)


class WorkCenterSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    display_order = serializers.IntegerField()
    active = serializers.BooleanField()


class WorkCenterListSerializer(serializers.Serializer):
    centers = WorkCenterSerializer(many=True)


class WorkCenterRequestSerializer(StrictSerializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(
        choices=(
            "CUT", "PROFILE_CUT", "REINFORCEMENT_CUT", "MACHINING",
            "WELDING", "CLEANING", "CRIMPING", "SASH_ASSEMBLY", "ASSEMBLY",
            "HARDWARE", "GLAZING", "QC", "PACK",
        )
    )
    display_order = serializers.IntegerField(required=False, default=0)


class WorkOrderOptimizeRequestSerializer(StrictSerializer):
    # Optional: the sealed payload color is authoritative — a contradicting
    # request color is refused, an omitted one inherits the sealed value.
    # Only legacy orders without a sealed color still require it (service 422).
    color = serializers.CharField(required=False, allow_blank=True, max_length=50)
    cutting_profile_code = serializers.CharField(required=False, allow_null=True, max_length=50)
    strategy = serializers.ChoiceField(
        choices=["fast", "deep", "auto"], required=False, default="auto"
    )


class WorkOrderOptimizeSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    optimization = serializers.DictField()


class WorkOrderOptimizeCompareRequestSerializer(StrictSerializer):
    color = serializers.CharField(required=False, allow_blank=True, max_length=50)


class OptimizeStrategyStatsSerializer(serializers.Serializer):
    strategy = serializers.CharField()
    bars_total = serializers.IntegerField()
    bars_new = serializers.IntegerField()
    bars_remnant = serializers.IntegerField()
    cuts_total = serializers.IntegerField()
    waste_mm = serializers.CharField()
    process_waste_mm = serializers.CharField()
    reusable_remnant_mm = serializers.CharField()
    sheets_total = serializers.IntegerField()
    pieces_sheets = serializers.IntegerField()
    unnested_count = serializers.IntegerField()
    purchase_bars = serializers.IntegerField()
    purchase_sheets = serializers.IntegerField()
    remnants_consumed = serializers.IntegerField()
    remnants_produced = serializers.IntegerField()
    runtime_ms = serializers.IntegerField()


class WorkOrderOptimizeCompareSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    color = serializers.CharField()
    strategies = OptimizeStrategyStatsSerializer(many=True)


class DeliveryConfirmationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    confirmation_code = serializers.CharField()
    order_id = serializers.UUIDField()
    delivery_id = serializers.UUIDField()
    payment_id = serializers.UUIDField(allow_null=True)
    issued_at = serializers.DateTimeField()


class DeliveryConfirmationAccessSerializer(DeliveryConfirmationSerializer):
    signed_url = serializers.CharField()
    expires_in = serializers.IntegerField()


class DeliverySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    scheduled_date = serializers.CharField()
    time_window = serializers.CharField()
    address = serializers.CharField()
    contact_name = serializers.CharField(allow_null=True)
    contact_phone = serializers.CharField(allow_null=True)
    installer_name = serializers.CharField(allow_null=True)
    notes = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(
        choices=("SCHEDULED", "ON_ROUTE", "DELIVERED", "FAILED")
    )
    confirmation = DeliveryConfirmationSerializer(allow_null=True)
    scheduled_by = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class DeliveryResponseSerializer(serializers.Serializer):
    delivery = DeliverySerializer(allow_null=True)


class DeliveryScheduleRequestSerializer(StrictSerializer):
    scheduled_date = serializers.CharField(max_length=10)
    time_window = serializers.ChoiceField(
        choices=("AM", "PM", "JORNADA"), required=False, default="AM"
    )
    address = serializers.CharField(max_length=300)
    contact_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    installer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DeliveryTransitionRequestSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("ON_ROUTE", "DELIVERED", "FAILED"))


class DeliveryPaymentRequestSerializer(StrictSerializer):
    amount = serializers.CharField()
    method = serializers.ChoiceField(
        choices=("TRANSFER", "CASH", "CARD", "CHECK", "OTHER")
    )
    kind = serializers.ChoiceField(
        choices=("ANTICIPO", "PARCIAL", "SALDO"), required=False, default="SALDO"
    )
    reference = serializers.CharField(required=False, allow_blank=True, max_length=120)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class DeliveryConfirmRequestSerializer(StrictSerializer):
    receiver_name = serializers.CharField(max_length=200)
    receiver_rut = serializers.CharField(required=False, allow_blank=True, max_length=30)
    signature_png = serializers.CharField()
    payment = DeliveryPaymentRequestSerializer(required=False, allow_null=True)


class DeliveryConfirmResponseSerializer(serializers.Serializer):
    confirmation = DeliveryConfirmationSerializer()
    delivery = DeliverySerializer()


class ProductionOrderTraceSerializer(serializers.Serializer):
    work_order = serializers.DictField()
    project = serializers.DictField(allow_null=True)
    version = serializers.DictField(allow_null=True)
    position_id = serializers.CharField(allow_null=True, required=False)
    labels = serializers.DictField(required=False)
    plan = serializers.DictField()
    stock = serializers.DictField()
    steps = serializers.ListField()
    events = serializers.ListField()
    operations = serializers.DictField()


class ProductionPieceTraceSerializer(serializers.Serializer):
    piece_id = serializers.CharField()
    matches = serializers.ListField()


class ProductionVersionTraceSerializer(serializers.Serializer):
    version = serializers.DictField()
    project = serializers.DictField(allow_null=True)
    work_orders = serializers.ListField()


class ProductionStationQueueSerializer(serializers.Serializer):
    stations = serializers.ListField()


class CncToolRequestSerializer(StrictSerializer):
    code = serializers.CharField(max_length=40)
    name = serializers.CharField(max_length=120)
    kind = serializers.CharField(max_length=30)
    diameter_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    working_length_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    max_depth_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    compatible_kinds = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )
    active = serializers.BooleanField(required=False)


class CncToolSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    diameter_mm = serializers.CharField(allow_null=True)
    working_length_mm = serializers.CharField(allow_null=True)
    max_depth_mm = serializers.CharField(allow_null=True)
    compatible_kinds = serializers.ListField(required=False, allow_null=True)
    active = serializers.BooleanField()


class CncMachineRequestSerializer(StrictSerializer):
    code = serializers.CharField(max_length=40)
    name = serializers.CharField(max_length=120)
    manufacturer = serializers.CharField(required=False, allow_blank=True, max_length=120)
    model = serializers.CharField(required=False, allow_blank=True, max_length=120)
    controller_family = serializers.CharField(required=False, max_length=80)
    coordinate_systems = serializers.ListField(child=serializers.CharField(), required=False)
    supported_kinds = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    supported_faces = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    max_member_length_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    safe_margin_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    clamp_zones = serializers.ListField(child=serializers.DictField(), required=False)
    tool_ids = serializers.ListField(child=serializers.CharField(), required=False)
    postprocessor_id = serializers.CharField(required=False, max_length=80)
    postprocessor_version = serializers.CharField(required=False, max_length=40)
    units = serializers.CharField(required=False, max_length=20)
    encoding = serializers.CharField(required=False, max_length=40)
    active = serializers.BooleanField(required=False)


class CncMachineSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    manufacturer = serializers.CharField()
    model = serializers.CharField()
    controller_family = serializers.CharField()
    coordinate_systems = serializers.ListField()
    supported_kinds = serializers.ListField(allow_null=True)
    supported_faces = serializers.ListField(allow_null=True)
    max_member_length_mm = serializers.CharField(allow_null=True)
    safe_margin_mm = serializers.CharField(allow_null=True)
    clamp_zones = serializers.ListField()
    tool_ids = serializers.ListField()
    postprocessor_id = serializers.CharField()
    postprocessor_version = serializers.CharField()
    units = serializers.CharField()
    encoding = serializers.CharField()
    active = serializers.BooleanField()


class CncMachineListSerializer(serializers.Serializer):
    machines = CncMachineSerializer(many=True)


class CncToolListSerializer(serializers.Serializer):
    tools = CncToolSerializer(many=True)


class CncWorkspaceSerializer(serializers.Serializer):
    machines = CncMachineSerializer(many=True)
    tools = CncToolSerializer(many=True)
    orders = serializers.ListField()


class CncGenerateRequestSerializer(StrictSerializer):
    machine_id = serializers.CharField()
    member_id = serializers.CharField(max_length=200)


class CncReadinessSerializer(serializers.Serializer):
    order_id = serializers.CharField()
    order_code = serializers.CharField()
    members = serializers.ListField()
    issues = serializers.ListField(required=False)
    machines = CncMachineSerializer(many=True)
    programs = serializers.ListField()


class CncProgramSerializer(serializers.Serializer):
    id = serializers.CharField()
    program_no = serializers.CharField()
    verdict = serializers.CharField()
    fingerprint = serializers.CharField()
    operation_count = serializers.IntegerField()
    member_label = serializers.CharField()
    machine_code = serializers.CharField()
    files = serializers.DictField(required=False)
    created_at = serializers.CharField()


class CncProgramListSerializer(serializers.Serializer):
    programs = serializers.ListField()


class CncToolPatchSerializer(StrictSerializer):
    code = serializers.CharField(max_length=40, required=False)
    name = serializers.CharField(max_length=120, required=False)
    kind = serializers.CharField(max_length=30, required=False)
    diameter_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    working_length_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    max_depth_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    compatible_kinds = serializers.ListField(
        child=serializers.CharField(), required=False, allow_null=True
    )
    active = serializers.BooleanField(required=False)


class CncMachinePatchSerializer(StrictSerializer):
    code = serializers.CharField(max_length=40, required=False)
    name = serializers.CharField(max_length=120, required=False)
    manufacturer = serializers.CharField(required=False, allow_blank=True, max_length=120)
    model = serializers.CharField(required=False, allow_blank=True, max_length=120)
    controller_family = serializers.CharField(required=False, max_length=80)
    coordinate_systems = serializers.ListField(child=serializers.CharField(), required=False)
    supported_kinds = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    supported_faces = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    max_member_length_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    safe_margin_mm = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    clamp_zones = serializers.ListField(child=serializers.DictField(), required=False)
    tool_ids = serializers.ListField(child=serializers.CharField(), required=False)
    postprocessor_id = serializers.CharField(required=False, max_length=80)
    postprocessor_version = serializers.CharField(required=False, max_length=40)
    units = serializers.CharField(required=False, max_length=20)
    encoding = serializers.CharField(required=False, max_length=40)
    active = serializers.BooleanField(required=False)
