-- Work-order release is the action that moves a project into production:
-- `release_production` writes status='IN_PRODUCTION' on QUOTED/APPROVED
-- projects under documentary_backend. Until now the role held UPDATE(status)
-- solely so SELECT … FOR UPDATE could admit the row lock
-- (20261222000000_project_lock_update_grant.sql); the release statement also
-- stamps updated_at, which was never granted, and neither
-- guard_commercial_write nor guard_project_revision_state had an allowance
-- for the lifecycle transition — the write died at the grant check on any
-- real database.
--
-- This migration makes the transition a sanctioned write, bounded on all
-- three axes:
--   * grant    — status + updated_at only (never commercials);
--   * policy   — project_documentary_backend_lock already gates UPDATE rows
--                to OWNER/ESTIMATOR/WORKSHOP_MANAGER memberships;
--   * triggers — both guards admit only the exact transition
--                QUOTED|APPROVED → IN_PRODUCTION with no other column moved.

GRANT UPDATE (status, updated_at) ON public.projects TO documentary_backend;

CREATE OR REPLACE FUNCTION private.guard_commercial_write() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    project_is_priced BOOLEAN;
BEGIN
    IF current_setting('role') = 'pricing_backend' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        RETURN NEW;
    END IF;
    IF current_setting('role') = 'documentary_backend'
       AND TG_TABLE_NAME = 'project_positions' THEN
        IF TG_OP = 'UPDATE'
           AND (to_jsonb(NEW) - ARRAY['location_tag', 'updated_at'])
               = (to_jsonb(OLD) - ARRAY['location_tag', 'updated_at'])
           AND NOT EXISTS (
               SELECT 1
               FROM public.projects project
               JOIN public.project_versions version
                 ON version.project_id = project.id
                AND version.revision_code = project.current_revision
               WHERE project.id = OLD.project_id
           ) THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'documentary_position_update_forbidden' USING ERRCODE = '42501';
    END IF;
    IF current_setting('role') = 'documentary_backend'
       AND TG_TABLE_NAME = 'projects' THEN
        -- Production release: the only project write the documentary role may
        -- perform — status QUOTED|APPROVED → IN_PRODUCTION, no other column.
        IF TG_OP = 'UPDATE'
           AND (to_jsonb(NEW) - ARRAY['status', 'updated_at'])
               = (to_jsonb(OLD) - ARRAY['status', 'updated_at'])
           AND OLD.status IN ('QUOTED', 'APPROVED')
           AND NEW.status = 'IN_PRODUCTION' THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'documentary_project_update_forbidden' USING ERRCODE = '42501';
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF (session_user IN ('postgres', 'supabase_admin') OR
            (session_user = 'authenticator' AND current_setting('role') = 'service_role'))
           AND auth.uid() IS NULL AND pg_trigger_depth() > 1
           AND NOT EXISTS (
               SELECT 1 FROM public.tenancy_organizations WHERE id = OLD.org_id
           ) THEN
            RETURN OLD;
        END IF;
    END IF;
    IF TG_TABLE_NAME = 'project_positions' THEN
        IF TG_OP = 'INSERT' THEN
            project_is_priced := private.project_has_applied_commercial_state(NEW.project_id);
            IF NEW.cost_net <> 0 OR NEW.price_net <> 0 OR NEW.discount_pct <> 0
               OR project_is_priced THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
        ELSIF TG_OP = 'UPDATE' THEN
            project_is_priced := private.project_has_applied_commercial_state(OLD.project_id)
                OR (NEW.project_id IS DISTINCT FROM OLD.project_id
                    AND private.project_has_applied_commercial_state(NEW.project_id));
            IF (NEW.cost_net, NEW.price_net, NEW.discount_pct)
                 IS DISTINCT FROM (OLD.cost_net, OLD.price_net, OLD.discount_pct)
               OR project_is_priced THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
        ELSE
            project_is_priced := private.project_has_applied_commercial_state(OLD.project_id);
            IF OLD.cost_net <> 0 OR OLD.price_net <> 0 OR OLD.discount_pct <> 0
               OR project_is_priced THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
            RETURN OLD;
        END IF;
    ELSE
        IF TG_OP = 'INSERT' THEN
            IF NEW.total_cost_net <> 0 OR NEW.total_price_net <> 0
               OR NEW.total_price_tax <> 0 OR NEW.total_price_gross <> 0 THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
        ELSIF TG_OP = 'UPDATE' THEN
            project_is_priced := private.project_has_applied_commercial_state(OLD.id);
            IF (NEW.total_cost_net, NEW.total_price_net,
                NEW.total_price_tax, NEW.total_price_gross)
                 IS DISTINCT FROM (OLD.total_cost_net, OLD.total_price_net,
                                   OLD.total_price_tax, OLD.total_price_gross)
               OR project_is_priced THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
        ELSE
            project_is_priced := private.project_has_applied_commercial_state(OLD.id);
            IF project_is_priced THEN
                RAISE EXCEPTION 'pricing_service_required' USING ERRCODE = '42501';
            END IF;
            RETURN OLD;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.guard_commercial_write() FROM PUBLIC;

-- guard_project_revision_state confines (status, current_revision) writes to
-- pricing_backend. The release transition is the one sanctioned exception
-- for documentary_backend: status only, QUOTED|APPROVED → IN_PRODUCTION.
CREATE OR REPLACE FUNCTION private.guard_project_revision_state()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF (NEW.status, NEW.current_revision) IS DISTINCT FROM (OLD.status, OLD.current_revision) THEN
        IF current_setting('role') = 'pricing_backend' THEN
            RETURN NEW;
        END IF;
        IF current_setting('role') = 'documentary_backend'
           AND TG_OP = 'UPDATE'
           AND NEW.current_revision = OLD.current_revision
           AND OLD.status IN ('QUOTED', 'APPROVED')
           AND NEW.status = 'IN_PRODUCTION' THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'project_revision_service_required' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.guard_project_revision_state() FROM PUBLIC;
