BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(4);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'workshop_label_format'
    ),
    'tenancy_organizations carries workshop_label_format'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.tenancy_organizations'::regclass
          AND conname = 'workshop_label_format_values'
    ),
    'workshop_label_format is constrained to GRID | THERMAL_100X50'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.column_privileges
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'workshop_label_format'
          AND grantee = 'documentary_backend' AND privilege_type = 'UPDATE'
    ),
    'documentary_backend can write workshop_label_format'
);

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('00000000-0000-0000-0000-00000000d013', 'Label Org', '76.000.013-0');

PREPARE set_bad_format AS
    UPDATE public.tenancy_organizations
    SET workshop_label_format = 'ROLL_58MM'
    WHERE id = '00000000-0000-0000-0000-00000000d013';
SELECT throws_ok(
    'set_bad_format',
    '23514',
    NULL,
    'workshop_label_format rejects an unlisted format'
);

SELECT * FROM finish();
ROLLBACK;
