-- §12-7 security: the *_backend import/provenance policies were USING(true)
-- WITH CHECK(true) — Python's org filter was the ONLY tenant wall, so a
-- single missed org_id= in new code would silently leak across tenants.
-- Backend roles evaluate request.jwt.claims identically to authenticated
-- (request scope and the jobs worker both set it), so they can carry the
-- same org predicate.

DROP POLICY document_imports_backend ON public.document_imports;
CREATE POLICY document_imports_backend ON public.document_imports
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

DROP POLICY catalog_imports_backend ON public.catalog_imports;
CREATE POLICY catalog_imports_backend ON public.catalog_imports
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

DROP POLICY ai_audit_provenance_backend ON public.ai_audit_provenance;
-- provenance has no org_id column by design — scope it through the parent
-- audit log's org so a cross-org audit row can never be written or read.
CREATE POLICY ai_audit_provenance_backend ON public.ai_audit_provenance
    FOR ALL TO billing_backend
    USING (
        audit_id IN (
            SELECT id FROM public.ai_audit_logs
            WHERE org_id IN (SELECT private.current_user_org_ids())
        )
    )
    WITH CHECK (
        audit_id IN (
            SELECT id FROM public.ai_audit_logs
            WHERE org_id IN (SELECT private.current_user_org_ids())
        )
    );
