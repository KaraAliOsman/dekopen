-- The guía de despacho seals the client RUT/address fallback while running
-- under documentary_backend — a role with no SELECT on public.clients, so
-- every dispatch on a project whose row lacked those fields died on
-- permission denied (phase-10 defect). clients_member_read (public,
-- org-scoped) still applies: the grant never widens scope, it restores it.
GRANT SELECT ON public.clients TO documentary_backend;
