-- P16 — La procedencia del catálogo no se autocertifica y la importación deja
-- auditoría inmutable.
--
-- P16-01  Elevating the provenance triple to "VERIFICADO" (setting
--         technical_reviewed_at / technical_reviewed_by or clearing
--         review_pending) was enforced only in the Python edge: any member
--         reaching the catalog_backend write path could stamp a review. A
--         BEFORE trigger now requires the technical-reviewer role
--         (private.can_review_catalog = WORKSHOP_MANAGER, or OWNER at aal2)
--         inside the same organization, resolved from request.jwt.claims —
--         the same predicate the API's WRITE_ROLES grants, now the last line
--         of defense at the storage layer. privileged fixture/seed paths
--         (postgres/service_role) keep their authority.
-- P16-02  catalog_imports gained no durable review audit: who confirmed,
--         when, and what the extraction produced lived only in mutable
--         result/status columns. catalog_import_events is an append-only
--         ledger (UPLOADED → EXTRACTED → CONFIRMED) that members can read
--         for their own org and no role can rewrite.
-- P16-03  catalog_imports.reviewed_by/reviewed_at: the reviewer's identity
--         and timestamp at confirm time — separate from created_by (who
--         uploaded). The API stamps them; members can't write the columns.

BEGIN;

-- ─── P16-01: technical-reviewer authority + certification trigger ──────────
CREATE FUNCTION private.can_review_catalog(target_org UUID)
RETURNS BOOLEAN
LANGUAGE SQL STABLE SECURITY DEFINER
SET search_path = ''
AS $$
    -- The reviewer predicate mirrors can_manage_catalog: the workshop's
    -- technical authority (WORKSHOP_MANAGER at any assurance level, OWNER
    -- only after a second-factor login). It is a separate function so the
    -- reviewer role can diverge from general catalog management later.
    SELECT EXISTS (
        SELECT 1
        FROM public.tenancy_memberships AS membership
        WHERE membership.org_id = target_org
          AND membership.user_id = auth.uid()
          AND membership.is_active
          AND (
              membership.role = 'WORKSHOP_MANAGER'
              OR (
                  membership.role = 'OWNER'
                  AND auth.jwt() ->> 'aal' = 'aal2'
              )
          )
    );
$$;

REVOKE ALL ON FUNCTION private.can_review_catalog(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.can_review_catalog(UUID)
    TO authenticated, catalog_backend;

-- catalog_backend only ever had USAGE on public (20261205000000); calling
-- private.* helpers — can_review_catalog from the trigger, user_email from
-- the API — needs the schema privilege first.
GRANT USAGE ON SCHEMA private TO catalog_backend;

-- The API resolves reviewer/actor UUIDs to an email label inside org-scoped
-- payloads (ficha provenance, import audit); members never call it directly.
GRANT EXECUTE ON FUNCTION private.user_email(UUID) TO catalog_backend;

CREATE FUNCTION private.guard_catalog_certification() RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    -- Seed/migration/maintenance paths keep their existing authority; every
    -- member-API write (authenticated PostgREST or the API's catalog_backend
    -- switch) passes here with request.jwt.claims intact.
    IF current_user NOT IN ('authenticated', 'catalog_backend') THEN
        RETURN NEW;
    END IF;

    -- Elevation = a review stamp appearing where there was none (or being
    -- replaced), or a pending review being closed. Demotions (clearing the
    -- stamp, flagging review_pending) and ordinary technical writes are not
    -- gated here.
    DECLARE
        elevation BOOLEAN;
    BEGIN
        IF TG_TABLE_NAME = 'catalog_parameter_evidence' THEN
            IF TG_OP = 'INSERT' THEN
                elevation := NEW.review_state = 'REVIEWED'
                    OR NEW.reviewed_at IS NOT NULL
                    OR NEW.reviewed_by IS NOT NULL;
            ELSE
                elevation :=
                    (NEW.review_state = 'REVIEWED'
                     AND OLD.review_state IS DISTINCT FROM 'REVIEWED')
                    OR (NEW.reviewed_at IS NOT NULL
                        AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at)
                    OR (NEW.reviewed_by IS NOT NULL
                        AND NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by);
            END IF;
        ELSIF TG_OP = 'INSERT' THEN
            elevation := NEW.technical_reviewed_at IS NOT NULL
                OR NEW.technical_reviewed_by IS NOT NULL;
        ELSE
            elevation :=
                (NEW.technical_reviewed_at IS NOT NULL
                 AND NEW.technical_reviewed_at IS DISTINCT FROM OLD.technical_reviewed_at)
                OR (NEW.technical_reviewed_by IS NOT NULL
                    AND NEW.technical_reviewed_by IS DISTINCT FROM OLD.technical_reviewed_by)
                OR (OLD.review_pending = TRUE AND NEW.review_pending = FALSE);
        END IF;
        IF NOT elevation THEN
            RETURN NEW;
        END IF;
    END;

    -- Global catalog rows (org_id NULL) are platform-managed: no member
    -- claim may certify them. For org rows the claim must carry the
    -- technical-reviewer role inside THAT organization — this is the
    -- organization-scoped gate, not a global flag (PR #107 regression class).
    -- The stamp value itself (which reviewer id) is stamped honestly by the
    -- API and may legitimately be preserved verbatim when a catalog is
    -- cloned — the role is what cannot be self-conferred.
    IF NEW.org_id IS NULL
       OR NOT private.can_review_catalog(NEW.org_id) THEN
        RAISE EXCEPTION 'catalog_review_requires_reviewer'
            USING ERRCODE = '42501',
                  HINT = 'Solo un revisor técnico de la organización puede certificar un dato del catálogo.';
    END IF;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.guard_catalog_certification() FROM PUBLIC;

-- Every public table carrying the provenance triple gets the guard —
-- discovered from the schema itself so the list can never drift from the
-- columns it protects (profiles, glass, hardware, rules, extras, colors…).
-- catalog_parameter_evidence has its own review triple (review_state /
-- reviewed_by / reviewed_at) and the trigger reads it by TG_TABLE_NAME.
DO $$
DECLARE target_table TEXT;
BEGIN
    FOR target_table IN
        SELECT columns.table_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_name = 'technical_reviewed_at'
          AND columns.table_name <> 'catalog_parameter_evidence'
          AND EXISTS (
              SELECT 1 FROM information_schema.columns AS pending
              WHERE pending.table_schema = 'public'
                AND pending.table_name = columns.table_name
                AND pending.column_name = 'review_pending')
          AND EXISTS (
              SELECT 1 FROM information_schema.columns AS org
              WHERE org.table_schema = 'public'
                AND org.table_name = columns.table_name
                AND org.column_name = 'org_id')
    LOOP
        EXECUTE format(
            'CREATE TRIGGER catalog_certification_guard
             BEFORE INSERT OR UPDATE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION private.guard_catalog_certification()',
            target_table
        );
    END LOOP;
END $$;

CREATE TRIGGER catalog_certification_guard
    BEFORE INSERT OR UPDATE ON public.catalog_parameter_evidence
    FOR EACH ROW EXECUTE FUNCTION private.guard_catalog_certification();

-- ─── P16-02: append-only import audit ──────────────────────────────────────
CREATE TABLE public.catalog_import_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    import_id UUID NOT NULL
        REFERENCES public.catalog_imports(id) ON DELETE CASCADE,
    event TEXT NOT NULL CHECK (event IN ('UPLOADED', 'EXTRACTED', 'CONFIRMED')),
    actor_id UUID,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX catalog_import_events_import
    ON public.catalog_import_events (import_id, created_at, id);

ALTER TABLE public.catalog_import_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY catalog_import_events_read
ON public.catalog_import_events FOR SELECT TO authenticated
USING (org_id IN (SELECT private.current_user_org_ids()));

CREATE POLICY catalog_import_events_backend
ON public.catalog_import_events FOR ALL TO documentary_backend, catalog_backend
USING (org_id IN (SELECT private.current_user_org_ids()))
WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

GRANT SELECT ON public.catalog_import_events TO authenticated;
GRANT SELECT, INSERT ON public.catalog_import_events
    TO documentary_backend, catalog_backend;

-- Inherited default privileges (postgres grants arwdDxtm to anon/authenticated
-- on every new table) would let a member forge or rewrite the ledger; the
-- SELECT grant above is the only member surface. Backend INSERT stays.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE
    ON public.catalog_import_events FROM authenticated, anon;
-- No UPDATE/DELETE grants anywhere: the ledger is append-only.

-- ─── P16-03: reviewer identity on the import ───────────────────────────────
ALTER TABLE public.catalog_imports
    ADD COLUMN reviewed_by UUID,
    ADD COLUMN reviewed_at TIMESTAMPTZ;

COMMIT;
