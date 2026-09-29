-- SHOT-09/DOC-08: generic supplier order document for order types that have
-- no type-specific layout (SUPPLIER_HARDWARE_PO, SUPPLIER_PANEL_PO). DOC-02
-- stays bound to glass, DOC-04 to profiles — the generic document cannot
-- claim those pairings, and they cannot claim it.

ALTER TABLE public.document_artifacts
    DROP CONSTRAINT IF EXISTS document_artifacts_document_type_check;
ALTER TABLE public.document_artifacts
    ADD CONSTRAINT document_artifacts_document_type_check
    CHECK (document_type = ANY (ARRAY['DOC-01'::text, 'DOC-02'::text, 'DOC-03'::text,
        'DOC-04'::text, 'DOC-05'::text, 'DOC-06'::text, 'DOC-07'::text,
        'DOC-08'::text]));

ALTER TABLE public.document_artifacts
    DROP CONSTRAINT IF EXISTS document_artifacts_check1;
ALTER TABLE public.document_artifacts
    ADD CONSTRAINT document_artifacts_check1
    CHECK (
        artifact_scope = 'PROJECT_REVISION'::text
        AND artifact_scope_id = project_version_id
        AND order_id IS NULL AND order_type IS NULL
        AND (document_type = ANY (ARRAY['DOC-01'::text, 'DOC-03'::text,
            'DOC-05'::text, 'DOC-06'::text, 'DOC-07'::text]))
        OR artifact_scope = 'ORDER'::text
        AND artifact_scope_id = order_id AND order_id IS NOT NULL
        AND (
            document_type = 'DOC-02'::text
                AND order_type = 'SUPPLIER_GLASS_PO'::order_type
            OR document_type = 'DOC-04'::text
                AND order_type = 'SUPPLIER_PROFILE_PO'::order_type
            OR document_type = 'DOC-08'::text
                AND order_type = ANY (ARRAY[
                    'SUPPLIER_HARDWARE_PO'::order_type,
                    'SUPPLIER_PANEL_PO'::order_type])
        )
    );

ALTER TABLE public.document_artifacts
    DROP CONSTRAINT IF EXISTS document_artifacts_check2;
ALTER TABLE public.document_artifacts
    ADD CONSTRAINT document_artifacts_check2
    CHECK (
        (document_type = ANY (ARRAY['DOC-01'::text, 'DOC-03'::text,
            'DOC-05'::text, 'DOC-06'::text, 'DOC-07'::text]))
            AND format = 'PDF'::text
        OR document_type = 'DOC-02'::text AND format = 'XLSX'::text
        OR (document_type = ANY (ARRAY['DOC-04'::text, 'DOC-08'::text]))
            AND (format = ANY (ARRAY['PDF'::text, 'XLSX'::text]))
    );
