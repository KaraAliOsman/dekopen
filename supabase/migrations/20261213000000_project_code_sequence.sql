-- Human project codes: P-000123 instead of P-98DEDD1E2C42.
-- A single org-spanning sequence keeps codes opaque (no row-count leak),
-- monotonic, and race-free under (org_id, code) uniqueness.
CREATE SEQUENCE IF NOT EXISTS public.project_code_seq START 1;

-- The same roles that may INSERT INTO public.projects.
GRANT USAGE, SELECT ON SEQUENCE public.project_code_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.project_code_seq TO documentary_backend;
GRANT USAGE, SELECT ON SEQUENCE public.project_code_seq TO pricing_backend;
