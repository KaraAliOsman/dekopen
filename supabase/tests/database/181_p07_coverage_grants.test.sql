BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(14);

-- P07 — cobertura de SKU: pricing_backend lee las identidades de compra.
-- Los 4 mapeos nuevos llevan GRANT explícito; las 7 tablas llevan una
-- política de lectura propia para el rol (una política TO authenticated no
-- lo cubre y devolvería filas vacías sin error).

SELECT ok(
    has_table_privilege('pricing_backend', 'public.glass_purchase_mappings', 'SELECT'),
    'pricing_backend puede leer glass_purchase_mappings'
);
SELECT ok(
    has_table_privilege('pricing_backend', 'public.panel_purchase_authorities', 'SELECT'),
    'pricing_backend puede leer panel_purchase_authorities'
);
SELECT ok(
    has_table_privilege('pricing_backend', 'public.hardware_purchase_mappings', 'SELECT'),
    'pricing_backend puede leer hardware_purchase_mappings'
);
SELECT ok(
    has_table_privilege('pricing_backend', 'public.fitting_purchase_mappings', 'SELECT'),
    'pricing_backend puede leer fitting_purchase_mappings'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'profile_purchase_mappings'
           AND policyname = 'profile_purchase_mappings_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'profile_purchase_mappings expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'reinforcement_articles'
           AND policyname = 'reinforcement_articles_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'reinforcement_articles expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'infill_articles'
           AND policyname = 'infill_articles_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'infill_articles expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'glass_purchase_mappings'
           AND policyname = 'glass_purchase_mappings_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'glass_purchase_mappings expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'panel_purchase_authorities'
           AND policyname = 'panel_purchase_authorities_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'panel_purchase_authorities expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'hardware_purchase_mappings'
           AND policyname = 'hardware_purchase_mappings_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'hardware_purchase_mappings expone lectura a pricing_backend'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public' AND tablename = 'fitting_purchase_mappings'
           AND policyname = 'fitting_purchase_mappings_pricing_read'
           AND 'pricing_backend' = ANY (roles)
    ),
    'fitting_purchase_mappings expone lectura a pricing_backend'
);

-- El aviso por correo resuelve emails vía funciones SECURITY DEFINER:
-- los roles backend no pueden leer el schema auth directamente (el rol de
-- migraciones no puede otorgarlo — migración 20261212), la membresía del
-- tenant queda dentro de la función.
SELECT ok(
    has_function_privilege(
        'documentary_backend',
        'private.org_member_emails(uuid, text[])',
        'EXECUTE'
    ),
    'documentary_backend ejecuta private.org_member_emails'
);
SELECT ok(
    has_function_privilege(
        'documentary_backend',
        'private.user_email(uuid)',
        'EXECUTE'
    ),
    'documentary_backend ejecuta private.user_email'
);
SELECT ok(
    NOT has_function_privilege(
        'authenticated',
        'private.org_member_emails(uuid, text[])',
        'EXECUTE'
    ),
    'authenticated no ejecuta private.org_member_emails'
);

SELECT * FROM finish();
ROLLBACK;
