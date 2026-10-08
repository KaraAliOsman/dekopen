DO $$
DECLARE
    business_table_count INT;
    rls_table_count INT;
    demo_system_count INT;
    demo_profile_authority_count INT;
    demo_glazing_rule_count INT;
BEGIN
    IF current_setting('server_version_num')::INT < 160000
        OR current_setting('server_version_num')::INT >= 170000 THEN
        RAISE EXCEPTION 'Expected PostgreSQL 16, got %', current_setting('server_version');
    END IF;

    SELECT count(*)
    INTO business_table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = ANY (ARRAY[
          'tenancy_organizations',
          'tenancy_memberships',
          'profile_systems',
          'profile_articles',
          'glazing_bead_matrix',
          'hardware_kits',
          'infill_articles',
          'cost_lists',
          'cost_list_items',
          'pricing_rules',
          'price_audit_logs',
          'projects',
          'project_positions',
          'project_versions',
          'orders',
          'offcut_inventory',
          'ai_audit_logs',
          'payment_customers',
          'subscriptions',
          'payments',
          'payment_events',
          'credit_ledger',
          'glass_products',
          'glass_product_surcharges',
          'glass_safety_rules',
          'glass_type_limits'
      ]);

    IF business_table_count <> 26 THEN
        RAISE EXCEPTION 'Expected 26 business tables, got %', business_table_count;
    END IF;

    SELECT count(*)
    INTO rls_table_count
    FROM pg_class AS catalog
    JOIN pg_namespace AS namespace ON namespace.oid = catalog.relnamespace
    WHERE namespace.nspname = 'public'
      AND catalog.relname = ANY (ARRAY[
          'tenancy_organizations',
          'tenancy_memberships',
          'profile_systems',
          'profile_articles',
          'glazing_bead_matrix',
          'hardware_kits',
          'infill_articles',
          'cost_lists',
          'cost_list_items',
          'pricing_rules',
          'price_audit_logs',
          'projects',
          'project_positions',
          'project_versions',
          'orders',
          'offcut_inventory',
          'ai_audit_logs',
          'payment_customers',
          'subscriptions',
          'payments',
          'payment_events',
          'credit_ledger',
          'glass_products',
          'glass_product_surcharges',
          'glass_safety_rules',
          'glass_type_limits'
      ])
      AND catalog.relrowsecurity = TRUE;

    IF rls_table_count <> 26 THEN
        RAISE EXCEPTION 'Expected RLS on 26 business tables, got %', rls_table_count;
    END IF;

    SELECT count(*)
    INTO demo_system_count
    FROM public.profile_systems
    WHERE code = 'DEMO_60'
      AND org_id IS NULL
      AND is_global = TRUE
      AND is_demo = TRUE
      AND central_overlap_mm = 40.00;

    IF demo_system_count <> 1 THEN
        RAISE EXCEPTION 'Expected one canonical global DEMO_60 system, got %', demo_system_count;
    END IF;

    SELECT count(*)
    INTO demo_profile_authority_count
    FROM public.profile_articles AS article
    JOIN public.profile_systems AS profile_system
      ON profile_system.id = article.system_id
    WHERE profile_system.code = 'DEMO_60'
      AND (
          (article.role = 'FRAME' AND article.face_width_mm = 60.00 AND article.reinforcement_gap_mm = 15.00)
          OR (article.role = 'SASH' AND article.face_width_mm = 75.00 AND article.reinforcement_gap_mm = 15.00)
          OR (article.role = 'MULLION_V' AND article.face_width_mm = 80.00 AND article.reinforcement_gap_mm = 5.00)
          OR (article.role = 'MULLION_H' AND article.face_width_mm = 80.00 AND article.reinforcement_gap_mm = 5.00)
      );

    IF demo_profile_authority_count <> 4 THEN
        RAISE EXCEPTION
            'Expected four canonical DEMO_60 profile authorities, got %',
            demo_profile_authority_count;
    END IF;

    SELECT count(*)
    INTO demo_glazing_rule_count
    FROM public.glazing_bead_matrix AS bead_rule
    JOIN public.profile_systems AS profile_system
      ON profile_system.id = bead_rule.system_id
    WHERE profile_system.code = 'DEMO_60'
      AND bead_rule.cut_add_mm = 9.00;

    IF demo_glazing_rule_count <> 6 THEN
        RAISE EXCEPTION
            'Expected six DEMO_60 glazing rules with cut_add_mm 9.00, got %',
            demo_glazing_rule_count;
    END IF;
END;
$$;
