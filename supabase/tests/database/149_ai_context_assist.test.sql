BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(4);

SELECT ok(
    EXISTS (
        SELECT 1 FROM public.ai_routes
        WHERE capability = 'context_assist' AND enabled
    ),
    'context_assist route exists and is enabled'
);
SELECT is(
    (SELECT provider || '|' || provider_model FROM public.ai_routes
     WHERE capability = 'context_assist'),
    'MIMO|mimo-v2.6-pro',
    'context_assist is pinned to the sole MiMo model'
);
SELECT ok(
    (SELECT credits_cost > 0 FROM public.ai_routes WHERE capability = 'context_assist'),
    'context_assist carries a positive per-invocation price'
);
SELECT isnt_empty(
    'SELECT public_name FROM public.ai_routes WHERE capability = ''context_assist''',
    'context_assist carries a white-label public name'
);

SELECT * FROM finish();
ROLLBACK;
