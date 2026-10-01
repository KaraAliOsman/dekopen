-- §06 system identity: manufacturer, family and declared applications.
-- Declarative metadata only — NULL stays unknown and is never inferred;
-- readiness and engine math read nothing from these columns.

BEGIN;

ALTER TABLE public.profile_systems
    ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(255),
    ADD COLUMN IF NOT EXISTS family VARCHAR(150),
    ADD COLUMN IF NOT EXISTS applications TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN public.profile_systems.manufacturer IS
    'Declared manufacturer name (e.g. VEKA, Aluminco). NULL = unknown.';
COMMENT ON COLUMN public.profile_systems.family IS
    'Declared product family inside the manufacturer line (e.g. Softline 82).';
COMMENT ON COLUMN public.profile_systems.applications IS
    'Declared applications (WINDOW, DOOR, SLIDING, FACADE, ...). Empty = undeclared.';

COMMIT;
