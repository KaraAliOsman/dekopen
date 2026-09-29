"""Populated pre-pricing schema upgrade and transactional rejection on PostgreSQL 16.

Builds the schema through the pre-pricing migrations on populated cost-list
data, applies the pricing migration, and proves historical rows survive while
a deliberately invalid populated database is rejected atomically.
"""

from pathlib import Path
import subprocess

import local_gates

ROOT = Path(__file__).resolve().parents[1]


def verify(container: str) -> None:
    docker = local_gates.executable("docker")

    def sql(database: str, source: str, expected_error: str | None = None) -> None:
        command = [docker, "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1",
                   "-U", "postgres", "-d", database]
        if expected_error is None:
            local_gates.run(command, input_text=source)
        else:
            result = subprocess.run(command, input=source, capture_output=True,
                                    text=True, encoding="utf-8", check=False)
            if result.returncode != 3 or expected_error not in result.stderr:
                raise RuntimeError("SHOT-08 invalid upgrade was not rejected atomically: "
                                   + local_gates.redact(result.stderr))

    bootstrap = (ROOT / "supabase/compat/postgres16_bootstrap.sql").read_text(encoding="utf-8")
    bootstrap = bootstrap[bootstrap.index("CREATE SCHEMA auth;"):]
    migration_path = ROOT / "supabase/migrations/20260910000000_shot_08_pricing.sql"
    migration = migration_path.read_text(encoding="utf-8")
    for database, invalid in (("shot08_upgrade", False), ("shot08_rejected", True)):
        sql("postgres", f"CREATE DATABASE {database};")
        sql(database, bootstrap)
        for path in sorted(migration_path.parent.glob("*.sql")):
            if path.name >= migration_path.name:
                break
            sql(database, path.read_text(encoding="utf-8"))
        # No seed.sql replay: the demo catalog already arrives via its own
        # migrations above, and seed.sql tracks the current schema — piping it
        # onto this historical schema breaks whenever the seed gains a newer
        # column (exactly the drift this drill exists to catch).
        sql(database, """
          INSERT INTO public.tenancy_organizations(id,name,tax_id)
            VALUES('88880000-0000-4000-8000-000000000001','Populated upgrade','SHOT08-UPGRADE');
          INSERT INTO public.cost_lists(id,org_id,supplier_name,valid_from)
            VALUES('88880000-0000-4000-8000-000000000002','88880000-0000-4000-8000-000000000001','Existing','2026-09-01');
          INSERT INTO public.cost_list_items(org_id,cost_list_id,sku,item_type,unit,unit_cost)
            VALUES('88880000-0000-4000-8000-000000000001','88880000-0000-4000-8000-000000000002','Existing','PROFILE','M',1.2345);
        """)
        if invalid:
            sql(database, "UPDATE public.cost_lists SET valid_to=DATE '2026-08-01';")
            sql(database, migration, "cost_list_dates")
            sql(database, """DO $$ BEGIN
              IF to_regclass('public.pricing_operations') IS NOT NULL OR EXISTS(
                SELECT 1 FROM information_schema.columns WHERE table_schema='public'
                  AND table_name='price_audit_logs' AND column_name='new_record') THEN
                RAISE EXCEPTION 'SHOT08 partial upgrade survived rollback'; END IF;
              IF (SELECT count(*) FROM public.cost_list_items WHERE sku='Existing' AND unit_cost=1.2345)<>1 THEN
                RAISE EXCEPTION 'SHOT08 rollback changed historical cost'; END IF;
            END $$;""")
        else:
            sql(database, migration)
            sql(database, """DO $$ BEGIN
              IF (SELECT count(*) FROM public.cost_list_items WHERE sku='Existing' AND unit_cost=1.2345)<>1 THEN
                RAISE EXCEPTION 'SHOT08 upgrade changed historical cost'; END IF;
              IF (SELECT count(*) FROM pg_class WHERE relname IN ('pricing_configurations','pricing_matrix_cells',
                  'pricing_fx_snapshots','pricing_operations') AND relrowsecurity)<>4 THEN
                RAISE EXCEPTION 'SHOT08 upgrade omitted RLS'; END IF;
            END $$;""")
    print("  SHOT-08 populated upgrade and failure rollback: PASS", flush=True)
