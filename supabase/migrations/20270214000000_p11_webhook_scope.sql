-- P11 follow-up: the public Flow webhook (and the simulated checkout's
-- settle, which walks the same path) carries no JWT, so the org-scoped
-- isolation policy hid the very link row the callback proves itself with —
-- confirm_link/confirm_simulated returned payment_link_not_found for every
-- unauthenticated settle. Scope resolution is therefore a SECURITY DEFINER
-- lookup keyed by the opaque identifiers the caller already knows (link id
-- or provider token): it discloses nothing the bearer does not already hold.
-- After resolving, the caller asserts request.jwt.claims = created_by — the
-- same delegation pattern the portal approval transition uses — so the rest
-- of the settle runs under real RLS with the link creator's membership.

CREATE FUNCTION private.payment_link_public_scope(
    p_link_id UUID,
    p_flow_token TEXT
)
RETURNS TABLE(id UUID, org_id UUID, project_id UUID, created_by UUID)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT l.id, l.org_id, l.project_id, l.created_by
    FROM public.project_payment_links l
    WHERE (p_link_id IS NOT NULL AND l.id = p_link_id)
       OR (p_flow_token IS NOT NULL AND l.flow_token = p_flow_token)
    LIMIT 1;
$$;

REVOKE ALL ON FUNCTION private.payment_link_public_scope(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.payment_link_public_scope(UUID, TEXT)
    TO documentary_backend;
