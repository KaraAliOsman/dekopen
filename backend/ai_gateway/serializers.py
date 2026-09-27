import json

from rest_framework import serializers

MAX_INPUT_BYTES = 65_536


class AiInvokeRequestSerializer(serializers.Serializer):
    capability = serializers.CharField(min_length=2, max_length=100)
    tool_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    operation_key = serializers.CharField(min_length=8, max_length=120)
    input_payload = serializers.DictField()

    def validate_input_payload(self, value):
        # Measure the real UTF-8 wire size — ensure_ascii would count the
        # \uXXXX escapes and reject unicode-heavy payloads far below 64 KB.
        encoded = json.dumps(value, default=str, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_INPUT_BYTES:
            raise serializers.ValidationError(
                "input_payload excede el límite de 64 KB."
            )
        return value


class AiInvokeResponseSerializer(serializers.Serializer):
    audit_id = serializers.CharField()
    capability = serializers.CharField()
    model = serializers.CharField()
    output = serializers.CharField()
    tokens_prompt = serializers.IntegerField()
    tokens_completion = serializers.IntegerField()
    latency_ms = serializers.IntegerField()
    credits_debited = serializers.IntegerField()


class AiAskRequestSerializer(serializers.Serializer):
    surface = serializers.CharField(min_length=2, max_length=40)
    refs = serializers.DictField(required=False)
    question = serializers.CharField(min_length=1, max_length=2000)
    operation_key = serializers.CharField(min_length=8, max_length=120)

    def validate_refs(self, value):
        # Refs are identifiers only — the server resolves them into the typed
        # context itself. Anything else (a nested blob, a payload-shaped
        # object) is not an identity and is refused.
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, (str, int)) or isinstance(item, bool):
                raise serializers.ValidationError(
                    "Las referencias de contexto deben ser identificadores simples."
                )
        return value


class AiAskActionSerializer(serializers.Serializer):
    kind = serializers.CharField()
    path = serializers.CharField()
    label = serializers.CharField()


class AiAskResponseSerializer(serializers.Serializer):
    audit_id = serializers.CharField()
    model = serializers.CharField()
    credits_debited = serializers.IntegerField()
    answer = serializers.CharField()
    actions = AiAskActionSerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())


class AiAskTurnSerializer(serializers.Serializer):
    """One durable ask turn — the dock replays these to rebuild the
    conversation for the current context after navigation or reload."""

    question = serializers.CharField()
    answer = AiAskResponseSerializer()
    created_at = serializers.CharField(allow_null=True)


class _RefsDictField(serializers.DictField):
    """Identity refs are name → identifier only — anything payload-shaped is
    not an identity and is refused, mirroring the ask contract."""

    def run_validation(self, data=serializers.empty):
        value = super().run_validation(data)
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, (str, int)) or isinstance(item, bool):
                raise serializers.ValidationError(
                    "Las referencias de contexto deben ser identificadores simples."
                )
        return value


class AiAgentHistorySerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "agent"])
    content = serializers.CharField(min_length=1, max_length=2000)


# The live product payload is a design tree — generous but bounded so a
# bloated document can't push the request body into arbitrary sizes.
MAX_PRODUCT_BYTES = 262144


class _BoundedDictField(serializers.DictField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if len(json.dumps(value, default=str)) > MAX_PRODUCT_BYTES:
            raise serializers.ValidationError("too_large")
        return value


class AiAgentRequestSerializer(serializers.Serializer):
    surface = serializers.CharField(min_length=2, max_length=40)
    refs = _RefsDictField(required=False)
    goal = serializers.CharField(min_length=1, max_length=2000)
    product = _BoundedDictField(required=False)
    # The client's fingerprint of the product payload — persisted on the
    # turn so a restored ops step can refuse to apply onto a changed design.
    product_sig = serializers.CharField(required=False, max_length=64, allow_blank=True)
    history = AiAgentHistorySerializer(many=True, required=False, max_length=6)
    operation_key = serializers.CharField(min_length=8, max_length=120)


class AiAgentStepSerializer(serializers.Serializer):
    kind = serializers.CharField()
    tool = serializers.CharField(required=False)
    label = serializers.CharField()
    path = serializers.CharField(required=False)
    action = serializers.CharField(required=False)
    ops = serializers.ListField(child=serializers.DictField(), required=False)
    # §08-WC batch edits: validated ops grouped per position.
    items = serializers.ListField(child=serializers.DictField(), required=False)


class AiAgentQuerySerializer(serializers.Serializer):
    surface = serializers.CharField()
    tool = serializers.CharField(required=False)
    status = serializers.CharField()


class AiAgentRejectedSerializer(serializers.Serializer):
    op = serializers.CharField(allow_null=True)
    reason = serializers.CharField()


class AiAgentAcceptedSerializer(serializers.Serializer):
    """202 — the run is queued on the durable worker; the client polls the
    job detail for the live transcript and the terminal result."""

    job_id = serializers.UUIDField()
    state = serializers.CharField()


class AiAgentRunSerializer(serializers.Serializer):
    """Durable-job payload for one agent round (first submit or follow-up)."""

    ai_job_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["new", "resume"])
    surface = serializers.CharField(min_length=2, max_length=40)
    refs = serializers.DictField(required=False)
    goal = serializers.CharField(min_length=1, max_length=2000)
    product = serializers.DictField(required=False, allow_null=True)
    history = AiAgentHistorySerializer(many=True, required=False, max_length=24)
    operation_key = serializers.CharField(min_length=8, max_length=200)
    # Retry replays the job's original goal — the marker travels so the
    # transcript turn reads "this was a re-run", not a retyped message.
    replay = serializers.BooleanField(required=False, default=False)
    product_sig = serializers.CharField(required=False, max_length=64, allow_blank=True)
    # Set by the resume path only: its history was rebuilt server-side from
    # the stored transcript, so its numbers may ground a follow-up. A
    # first-run payload's history is client-supplied and never trusted.
    history_trusted = serializers.BooleanField(required=False, default=False)


class AiAgentResultSerializer(serializers.Serializer):
    """The payload act() stores on the job's `result` column — the envelope
    fields (audit/job ids, state, transcript) live on the job row itself."""

    model = serializers.CharField()
    credits_debited = serializers.IntegerField()
    reply = serializers.CharField()
    plan = serializers.ListField(child=serializers.DictField())
    claims = serializers.ListField(child=serializers.DictField())
    references = serializers.ListField(child=serializers.CharField())
    questions = serializers.ListField(child=serializers.CharField())
    artifacts = serializers.ListField(child=serializers.DictField())
    steps = AiAgentStepSerializer(many=True)
    queries = AiAgentQuerySerializer(many=True)
    warnings = serializers.ListField(child=serializers.CharField())
    rejected = AiAgentRejectedSerializer(many=True)


class AiJobMessageSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1, max_length=2000)
    # Follow-ups carry the position's live product so design ops evaluate
    # the current design — a stored snapshot would go stale between turns.
    product = _BoundedDictField(required=False)
    # And the caller's live context refs — a volatile pointer (e.g. the
    # canvas selection) refreshes what "this" means without re-keying the
    # job, whose stored refs stay stable.
    refs = _RefsDictField(required=False)
    # The client's fingerprint of the product payload — persisted on the
    # turn so a restored ops step can refuse to apply onto a changed design.
    product_sig = serializers.CharField(required=False, max_length=64, allow_blank=True)


class AiJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    surface = serializers.CharField()
    refs = serializers.DictField()
    goal = serializers.CharField()
    state = serializers.CharField()
    cancel_signaled = serializers.BooleanField(required=False)
    plan = serializers.ListField()
    artifacts = serializers.ListField()
    warnings = serializers.ListField()
    result = AiAgentResultSerializer(required=False, allow_null=True)
    error_code = serializers.CharField(required=False, allow_null=True)
    outcomes = serializers.ListField(required=False)
    # Mid-run signal from the worker's job_runs row — the ai_jobs writes
    # commit only when the run finishes, so live progress rides this.
    live = serializers.DictField(required=False, allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(required=False, allow_null=True)


class AiJobOutcomeSerializer(serializers.Serializer):
    """Client report: what the human did with one proposed step."""

    turn_index = serializers.IntegerField(min_value=0, max_value=1000)
    step_index = serializers.IntegerField(min_value=0, max_value=1000)
    action = serializers.ChoiceField(
        choices=["applied", "declined", "apply_failed"]
    )
    ops = serializers.ListField(
        child=serializers.CharField(max_length=80),
        required=False,
        max_length=200,
    )


class AiJobOutcomeResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    recorded = serializers.BooleanField()


class AiMetricsSerializer(serializers.Serializer):
    window_days = serializers.IntegerField()
    jobs = serializers.DictField()
    commands = serializers.DictField()
    approvals = serializers.DictField()
    artifacts_produced = serializers.IntegerField()
    cost = serializers.DictField()
    time_saved = serializers.DictField()


class AiJobDetailSerializer(AiJobSerializer):
    transcript = serializers.ListField()


class AiAgentResumeRequestSerializer(serializers.Serializer):
    pass