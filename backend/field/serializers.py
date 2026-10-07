"""OpenAPI-visible contracts for the field/site API (P23)."""

from __future__ import annotations

from rest_framework import serializers


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("Unknown input fields")
        return super().to_internal_value(data)


class FieldPhotoSerializer(serializers.Serializer):
    key = serializers.CharField()
    sha256 = serializers.CharField(allow_null=True, required=False)
    label = serializers.CharField(allow_null=True, required=False)


class FieldCrewSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    kind = serializers.ChoiceField(choices=("VEHICLE", "TEAM"))
    plate = serializers.CharField(allow_null=True)
    active = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class FieldCrewListSerializer(serializers.Serializer):
    crews = FieldCrewSerializer(many=True)


class FieldCrewRequestSerializer(StrictSerializer):
    name = serializers.CharField(max_length=120)
    kind = serializers.ChoiceField(choices=("VEHICLE", "TEAM"))
    plate = serializers.CharField(required=False, allow_blank=True, max_length=20)
    active = serializers.BooleanField(required=False)


class DispatchStopSerializer(serializers.Serializer):
    delivery_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    address = serializers.CharField()
    time_window = serializers.CharField()
    status = serializers.CharField()
    route_order = serializers.IntegerField(allow_null=True)
    installer_name = serializers.CharField(allow_null=True)
    installer_user_id = serializers.UUIDField(allow_null=True)
    units = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    manifest_total = serializers.IntegerField()
    crew_id = serializers.UUIDField(allow_null=True)
    load_checked = serializers.BooleanField()
    note_issued = serializers.BooleanField()


class DispatchCrewSlotSerializer(serializers.Serializer):
    crew_id = serializers.UUIDField(allow_null=True)
    stops = DispatchStopSerializer(many=True)


class DispatchDaySerializer(serializers.Serializer):
    date = serializers.CharField()
    weekday = serializers.CharField()
    today = serializers.BooleanField()
    crews = DispatchCrewSlotSerializer(many=True)


class DispatchReadyOrderSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    project_code = serializers.CharField()
    client_name = serializers.CharField()
    delivery_address = serializers.CharField(allow_null=True)
    units = serializers.IntegerField()


class DispatchPlanSerializer(serializers.Serializer):
    days = DispatchDaySerializer(many=True)
    crews = FieldCrewSerializer(many=True)
    ready = DispatchReadyOrderSerializer(many=True)


class DispatchScheduleSerializer(StrictSerializer):
    order_id = serializers.UUIDField()
    scheduled_date = serializers.CharField(max_length=10)
    time_window = serializers.ChoiceField(
        choices=("AM", "PM", "JORNADA"), required=False, default="AM"
    )
    address = serializers.CharField(max_length=300)
    contact_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=50)
    installer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    installer_user_id = serializers.UUIDField(required=False, allow_null=True)
    crew_id = serializers.UUIDField(required=False, allow_null=True)
    route_order = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    unit_indexes = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_null=True,
    )


class AgendaDeliverySerializer(serializers.Serializer):
    delivery_id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    status = serializers.CharField()
    time_window = serializers.CharField()
    address = serializers.CharField()
    contact_name = serializers.CharField(allow_null=True)
    contact_phone = serializers.CharField(allow_null=True)
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    client_name = serializers.CharField()
    position_id = serializers.UUIDField(allow_null=True)
    location_tag = serializers.CharField(allow_null=True)
    units = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    manifest_total = serializers.IntegerField()
    notes = serializers.CharField(allow_null=True)
    crew_id = serializers.UUIDField(allow_null=True)
    route_order = serializers.IntegerField(allow_null=True)
    checklists_done = serializers.IntegerField()
    checks_total = serializers.IntegerField()
    measurement_state = serializers.CharField(allow_null=True)
    open_incidents = serializers.IntegerField()
    confirmed = serializers.BooleanField()


class AgendaServiceVisitSerializer(serializers.Serializer):
    ticket_id = serializers.UUIDField()
    code = serializers.CharField()
    scheduled_visit_at = serializers.DateTimeField()
    project_code = serializers.CharField()
    client_name = serializers.CharField(allow_null=True)
    address = serializers.CharField(allow_null=True)
    crew_name = serializers.CharField(allow_null=True)


class FieldAgendaSerializer(serializers.Serializer):
    date = serializers.CharField()
    mine_only = serializers.BooleanField()
    items = AgendaDeliverySerializer(many=True)
    service_visits = AgendaServiceVisitSerializer(many=True)


class VanoMeasurementSerializer(StrictSerializer):
    width_points_mm = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=3
    )
    height_points_mm = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=3
    )
    wall_type = serializers.ChoiceField(
        choices=("MASONRY", "CONCRETE", "PARTITION", "WOOD"),
        required=False, allow_null=True,
    )
    square_mm = serializers.CharField(required=False, allow_null=True)
    plumb_mm = serializers.CharField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)


class SiteMeasurementRequestSerializer(StrictSerializer):
    position_id = serializers.UUIDField()
    operation_key = serializers.CharField(max_length=80)
    vano = VanoMeasurementSerializer(required=False, allow_null=True)
    mounting_rule_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    photos = serializers.ListField(child=serializers.DictField(), required=False)


class SiteMeasurementSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    position_id = serializers.UUIDField()
    operation_key = serializers.CharField()
    rough_opening_input = serializers.DictField()
    mounting_rule_id = serializers.UUIDField(allow_null=True)
    notes = serializers.CharField(allow_null=True)
    photos = serializers.ListField()
    previous_input = serializers.DictField(allow_null=True)
    resolution = serializers.DictField(allow_null=True)
    applied_state = serializers.CharField()
    applied_revision_code = serializers.CharField(allow_null=True)
    measured_by = serializers.UUIDField(allow_null=True)
    taken_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class SiteMeasurementResponseSerializer(serializers.Serializer):
    measurement = SiteMeasurementSerializer()
    replayed = serializers.BooleanField(required=False)


class InstallationCheckRequestSerializer(StrictSerializer):
    unit_index = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    items = serializers.DictField(child=serializers.BooleanField())
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    photos = serializers.ListField(child=serializers.DictField(), required=False)
    operation_key = serializers.CharField(max_length=80)


class InstallationCheckSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_id = serializers.UUIDField()
    unit_index = serializers.IntegerField(allow_null=True)
    items = serializers.DictField()
    notes = serializers.CharField(allow_null=True)
    photos = serializers.ListField()
    checked_by = serializers.UUIDField(allow_null=True)
    checked_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class InstallationCheckResponseSerializer(serializers.Serializer):
    check = InstallationCheckSerializer()
    replayed = serializers.BooleanField(required=False)


class LoadCheckRequestSerializer(StrictSerializer):
    scanned_codes = serializers.ListField(
        child=serializers.CharField(max_length=200), allow_empty=False
    )


class LoadCheckResponseSerializer(serializers.Serializer):
    delivery_id = serializers.UUIDField()
    load_checked = serializers.BooleanField()
    missing = serializers.ListField(child=serializers.IntegerField())
    unexpected = serializers.ListField(child=serializers.CharField())


class IncidentRequestSerializer(StrictSerializer):
    kind = serializers.ChoiceField(
        choices=("DAMAGE", "WRONG_MEASURE", "MISSING", "ADJUSTMENT")
    )
    operation_key = serializers.CharField(max_length=80)
    delivery_id = serializers.UUIDField(required=False, allow_null=True)
    unit_index = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    piece_code = serializers.CharField(required=False, allow_blank=True, max_length=80)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    photos = serializers.ListField(child=serializers.DictField(), required=False)


class IncidentResolveRequestSerializer(StrictSerializer):
    resolution_kind = serializers.ChoiceField(
        choices=("REMAKE", "PURCHASE", "SERVICE", "NONE")
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    # PURCHASE
    purchase_item = serializers.CharField(
        required=False, allow_blank=True, max_length=300
    )
    purchase_quantity = serializers.CharField(required=False, allow_null=True)
    purchase_unit = serializers.CharField(required=False, allow_blank=True, max_length=20)
    purchase_supplier_hint = serializers.CharField(
        required=False, allow_blank=True, max_length=200
    )
    purchase_needed_at = serializers.DateField(required=False, allow_null=True)


class IncidentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    order_id = serializers.UUIDField()
    order_code = serializers.CharField()
    project_code = serializers.CharField(allow_null=True)
    delivery_id = serializers.UUIDField(allow_null=True)
    unit_index = serializers.IntegerField(allow_null=True)
    piece_code = serializers.CharField(allow_null=True)
    kind = serializers.CharField()
    note = serializers.CharField(allow_null=True)
    photos = serializers.ListField()
    status = serializers.CharField()
    resolution_kind = serializers.CharField(allow_null=True)
    resolution_note = serializers.CharField(allow_null=True)
    resolution_ref_id = serializers.UUIDField(allow_null=True)
    resolution_ref_code = serializers.CharField(allow_null=True)
    reported_by = serializers.UUIDField(allow_null=True)
    reported_at = serializers.DateTimeField()
    resolved_by = serializers.UUIDField(allow_null=True)
    resolved_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class IncidentListSerializer(serializers.Serializer):
    incidents = IncidentSerializer(many=True)


class IncidentReportResponseSerializer(serializers.Serializer):
    incident = IncidentSerializer()
    replayed = serializers.BooleanField(required=False)


class IncidentResolveResponseSerializer(serializers.Serializer):
    incident = IncidentSerializer()
    remake_order_id = serializers.UUIDField(allow_null=True)
    remake_order_code = serializers.CharField(allow_null=True)
    purchase_request_code = serializers.CharField(allow_null=True)
    ticket_code = serializers.CharField(allow_null=True)
    replayed = serializers.BooleanField(required=False)


class PurchaseRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    incident_id = serializers.UUIDField()
    incident_code = serializers.CharField()
    item = serializers.CharField()
    quantity = serializers.CharField(allow_null=True)
    unit = serializers.CharField(allow_null=True)
    supplier_hint = serializers.CharField(allow_null=True)
    needed_at = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class PurchaseRequestListSerializer(serializers.Serializer):
    items = PurchaseRequestSerializer(many=True)


class PurchaseRequestMarkSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=("ORDERED", "RECEIVED", "CANCELLED"))


class PurchaseTransitionResponseSerializer(serializers.Serializer):
    item = PurchaseRequestSerializer()


class ServiceTicketRequestSerializer(StrictSerializer):
    kind = serializers.ChoiceField(choices=("WARRANTY", "SERVICE"))
    description = serializers.CharField(max_length=1000)
    operation_key = serializers.CharField(max_length=80)
    order_id = serializers.UUIDField(required=False, allow_null=True)
    unit_index = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    piece_code = serializers.CharField(required=False, allow_blank=True, max_length=80)
    diagnosis = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    photos = serializers.ListField(child=serializers.DictField(), required=False)
    scheduled_visit_at = serializers.DateTimeField(required=False, allow_null=True)
    scheduled_crew_id = serializers.UUIDField(required=False, allow_null=True)


class ServiceTicketTransitionSerializer(StrictSerializer):
    status = serializers.ChoiceField(
        choices=("SCHEDULED", "IN_PROGRESS", "CLOSED", "CANCELLED")
    )
    scheduled_visit_at = serializers.DateTimeField(required=False, allow_null=True)
    scheduled_crew_id = serializers.UUIDField(required=False, allow_null=True)
    visit_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    diagnosis = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    close_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ServiceTicketSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    project_id = serializers.UUIDField()
    project_code = serializers.CharField(allow_null=True)
    project_name = serializers.CharField(allow_null=True)
    client_name = serializers.CharField(allow_null=True)
    site_address = serializers.CharField(allow_null=True)
    order_id = serializers.UUIDField(allow_null=True)
    order_code = serializers.CharField(allow_null=True)
    unit_index = serializers.IntegerField(allow_null=True)
    piece_code = serializers.CharField(allow_null=True)
    incident_id = serializers.UUIDField(allow_null=True)
    kind = serializers.CharField()
    description = serializers.CharField()
    diagnosis = serializers.CharField(allow_null=True)
    photos = serializers.ListField()
    warranty_until = serializers.CharField(allow_null=True)
    warranty_months = serializers.IntegerField(allow_null=True)
    in_warranty = serializers.BooleanField()
    status = serializers.CharField()
    scheduled_visit_at = serializers.DateTimeField(allow_null=True)
    scheduled_crew_id = serializers.UUIDField(allow_null=True)
    crew_name = serializers.CharField(allow_null=True)
    visit_note = serializers.CharField(allow_null=True)
    close_note = serializers.CharField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    created_by = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class ServiceTicketListSerializer(serializers.Serializer):
    tickets = ServiceTicketSerializer(many=True)


class ServiceTicketResponseSerializer(serializers.Serializer):
    ticket = ServiceTicketSerializer()
    replayed = serializers.BooleanField(required=False)


class PhotoUploadRequestSerializer(StrictSerializer):
    content_b64 = serializers.CharField()
    label = serializers.CharField(required=False, allow_blank=True, max_length=120)


class PhotoUploadResponseSerializer(serializers.Serializer):
    key = serializers.CharField()
    sha256 = serializers.CharField()


class PhotoAccessSerializer(serializers.Serializer):
    url = serializers.CharField()
    expires_in = serializers.IntegerField()


class FieldOrderCardSerializer(serializers.Serializer):
    order = serializers.DictField()
    project = serializers.DictField()
    position = serializers.DictField(allow_null=True)
    delivery = serializers.DictField(allow_null=True)
    confirmation = serializers.DictField(allow_null=True, required=False)
    measurement = serializers.DictField(allow_null=True)
    checklists = InstallationCheckSerializer(many=True)
    incidents = IncidentSerializer(many=True)
    warranty = serializers.DictField(allow_null=True)
