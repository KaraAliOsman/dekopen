-- P24 — Analítica que sirve para decidir: conversión, margen real vs.
-- cotizado, merma y tiempos. Las métricas viven como funciones
-- ``private.analytics_*`` SECURITY DEFINER: son la única vía de lectura
-- agregada (PostgREST no expone ``private``) y cada una exige membresía
-- activa + rol lector dentro de la org objetivo — nunca agregan entre
-- organizaciones. Definiciones: docs/analytics/metricas.md.

-- ---------------------------------------------------------------------------
-- Ajustes de analítica: quién ve montos/márgenes (dinero) y la tarifa horaria
-- que convierte horas de estación en costo real de mano de obra.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS analytics_financial_roles TEXT[] NOT NULL DEFAULT '{OWNER}'
        CONSTRAINT tenancy_organizations_analytics_financial_roles_check
        CHECK (
            analytics_financial_roles <> '{}'::text[]
            AND analytics_financial_roles <@ ARRAY[
                'OWNER','ESTIMATOR','WORKSHOP_MANAGER','INSTALLER','OPERATOR']::text[]
        );

ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS analytics_hourly_rate_clp NUMERIC(14, 2)
        CONSTRAINT tenancy_organizations_analytics_hourly_rate_check
        CHECK (analytics_hourly_rate_clp IS NULL OR analytics_hourly_rate_clp >= 0);

GRANT UPDATE (analytics_financial_roles, analytics_hourly_rate_clp)
    ON public.tenancy_organizations TO documentary_backend;

-- ---------------------------------------------------------------------------
-- Guardia compartida: la org pedida debe ser una del llamante y su rol debe
-- poder leer analítica (OWNER / WORKSHOP_MANAGER). Devuelve si el rol puede
-- además ver dinero según ``analytics_financial_roles`` de la org.
CREATE OR REPLACE FUNCTION private.analytics_access(target_org UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
BEGIN
    IF target_org IS NULL
       OR NOT (target_org IN (SELECT private.current_user_org_ids()))
       OR NOT private.documentary_role(
                  target_org, ARRAY['OWNER', 'WORKSHOP_MANAGER']) THEN
        RAISE EXCEPTION 'analytics_forbidden' USING ERRCODE = '42501';
    END IF;
    RETURN EXISTS (
        SELECT 1
          FROM public.tenancy_memberships m
          JOIN public.tenancy_organizations t ON t.id = m.org_id
         WHERE m.org_id = target_org
           AND m.user_id = auth.uid()
           AND m.is_active
           AND m.role::text = ANY(t.analytics_financial_roles)
    );
END;
$fn$;

-- Tarifa horaria configurada (NULL = «Sin dato»: la mano de obra real queda
-- sin valorizar y cada métrica que la necesita declara la causa).
CREATE OR REPLACE FUNCTION private.analytics_hourly_rate(target_org UUID)
RETURNS NUMERIC
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
    SELECT analytics_hourly_rate_clp
      FROM public.tenancy_organizations
     WHERE id = target_org
$fn$;

-- Precio real por SKU de compra: último precio sellado en una línea de OC no
-- anulada; respaldo la lista de costos vigente (la misma autoridad con que se
-- cotizó). source = 'OC' | 'LISTA'.
CREATE OR REPLACE FUNCTION private.analytics_sku_prices(target_org UUID)
RETURNS TABLE (sku TEXT, unit_price NUMERIC, price_source TEXT)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
    WITH po AS (
        SELECT DISTINCT ON (line.line_snapshot ->> 'purchasing_sku')
               line.line_snapshot ->> 'purchasing_sku' AS sku,
               (line.line_snapshot ->> 'unit_price')::numeric AS unit_price
          FROM public.order_requirement_lines line
          JOIN public.orders o
            ON o.id = line.order_id AND o.org_id = line.org_id
         WHERE line.org_id = target_org
           AND o.status::text <> 'CANCELLED'
           AND line.line_snapshot ->> 'unit_price' IS NOT NULL
           AND (line.line_snapshot ->> 'unit_price')::numeric >= 0
         ORDER BY line.line_snapshot ->> 'purchasing_sku',
                  o.created_at DESC
    ),
    lista AS (
        SELECT DISTINCT ON (cli.sku)
               cli.sku, cli.unit_cost AS unit_price
          FROM public.cost_list_items cli
          JOIN public.cost_lists cl ON cl.id = cli.cost_list_id
         WHERE cli.org_id = target_org
           AND cl.is_active
           AND cl.valid_from <= CURRENT_DATE
           AND (cl.valid_to IS NULL OR cl.valid_to >= CURRENT_DATE)
         ORDER BY cli.sku, cl.valid_from DESC
    )
    SELECT po.sku, po.unit_price, 'OC'::text AS price_source FROM po
    UNION ALL
    SELECT lista.sku, lista.unit_price, 'LISTA'::text AS price_source
     FROM lista
     WHERE lista.sku NOT IN (SELECT sku FROM po)
$fn$;

-- Precio por unidad física del retazo: CLP/mm para barras (precio de la barra
-- madre ÷ su largo comercial), CLP/mm² para placas (precio de la placa ÷ su
-- área declarada en el ítem de stock). NULL = sin cadena de precio → la
-- métrica lo reporta como material sin precio, jamás como 0.
CREATE OR REPLACE FUNCTION private.analytics_remnant_unit_price(target_org UUID, remnant UUID)
RETURNS NUMERIC
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    r RECORD;
    price NUMERIC;
BEGIN
    SELECT kind, stock_authority_id, sheet_workshop_sku
      INTO r
      FROM public.inventory_remnants
     WHERE org_id = target_org AND id = remnant;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    IF r.kind = 'BAR' THEN
        SELECT sp.unit_price / NULLIF(pa.commercial_length_mm, 0)
          INTO price
          FROM public.profile_purchase_mappings ppm
          JOIN public.profile_articles pa ON pa.id = ppm.profile_article_id
          JOIN private.analytics_sku_prices(target_org) sp
            ON sp.sku = ppm.commercial_sku
         WHERE ppm.id = r.stock_authority_id
         LIMIT 1;
        IF price IS NULL THEN
            SELECT sp.unit_price / NULLIF(ra.stock_length_mm, 0)
              INTO price
              FROM public.reinforcement_articles ra
              JOIN private.analytics_sku_prices(target_org) sp
                ON sp.sku = ra.commercial_sku
             WHERE ra.id = r.stock_authority_id
             LIMIT 1;
        END IF;
        RETURN price;
    END IF;
    SELECT sp.unit_price
         / NULLIF((i.attributes ->> 'sheet_width_mm')::numeric
                  * (i.attributes ->> 'sheet_height_mm')::numeric, 0)
      INTO price
      FROM public.inventory_items i
      JOIN private.analytics_sku_prices(target_org) sp
        ON sp.sku = COALESCE(i.attributes ->> 'purchasing_sku', i.sku)
     WHERE i.org_id = target_org
       AND i.sku = r.sheet_workshop_sku
       AND i.attributes ? 'sheet_width_mm'
       AND i.attributes ? 'sheet_height_mm'
     LIMIT 1;
    RETURN price;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- VENTAS — cohorte: revisiones emitidas dentro del período.
CREATE OR REPLACE FUNCTION private.analytics_sales(target_org UUID, desde DATE, hasta DATE)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    fin BOOLEAN := private.analytics_access(target_org);
BEGIN
    RETURN (
    WITH cohort AS (
        SELECT v.id AS version_id, v.project_id, v.revision_code,
               v.emitted_at, v.emitted_by,
               NULLIF(v.snapshot_json -> 'pricing' -> 'result' ->> 'project_net', '')::numeric
                   AS net,
               NULLIF(v.snapshot_json -> 'project' ->> 'total_price_net', '')::numeric
                   AS net_doc,
               p.code, p.name AS project_name, p.client_name
          FROM public.project_versions v
          JOIN public.projects p
            ON p.id = v.project_id AND p.org_id = v.org_id
         WHERE v.org_id = target_org
           AND v.emitted_at IS NOT NULL
           AND (v.emitted_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    decision AS (
        SELECT DISTINCT ON (a.project_version_id)
               a.project_version_id, a.status, a.decided_at, a.expires_at
          FROM public.customer_approvals a
          JOIN cohort c ON c.version_id = a.project_version_id
         WHERE a.org_id = target_org
         ORDER BY a.project_version_id,
                  a.decided_at DESC NULLS LAST, a.created_at DESC
    ),
    joined AS (
        SELECT c.*, d.status AS decision_status, d.decided_at, d.expires_at
          FROM cohort c
          LEFT JOIN decision d ON d.project_version_id = c.version_id
    ),
    typ AS (
        SELECT DISTINCT ON (c.project_id)
               c.project_id, pp.typology
          FROM cohort c
          JOIN public.project_positions pp
            ON pp.project_id = c.project_id AND pp.org_id = target_org
         ORDER BY c.project_id, pp.price_net DESC NULLS LAST,
                  pp.position_index ASC
    ),
    counts AS (
        SELECT
            COUNT(*)::int AS emitted,
            COUNT(*) FILTER (WHERE decision_status = 'APPROVED')::int AS approved,
            COUNT(*) FILTER (WHERE decision_status = 'DECLINED')::int AS declined,
            COUNT(*) FILTER (WHERE decision_status = 'CHANGES_REQUESTED')::int AS changes,
            COUNT(*) FILTER (WHERE decision_status IS NULL
                             OR decision_status = 'PENDING')::int AS pending,
            COUNT(*) FILTER (WHERE decision_status = 'REVOKED')::int AS revoked,
            COUNT(*) FILTER (WHERE decision_status IN ('APPROVED','DECLINED'))::int AS decided,
            ROUND(AVG(EXTRACT(EPOCH FROM (decided_at - emitted_at)) / 86400.0)
                  FILTER (WHERE decision_status IN ('APPROVED','DECLINED')), 1)
                AS avg_decision_days
          FROM joined
    ),
    pipeline AS (
        SELECT CASE
                   WHEN decision_status = 'CHANGES_REQUESTED' THEN 'EN_CAMBIOS'
                   WHEN expires_at IS NOT NULL AND expires_at < now() THEN 'VENCIDA'
                   ELSE 'PENDIENTE'
               END AS phase,
               COUNT(*)::int AS n,
               SUM(COALESCE(net, net_doc)) AS net
          FROM joined
         WHERE decision_status IS NULL
            OR decision_status IN ('PENDING', 'CHANGES_REQUESTED')
         GROUP BY 1
    ),
    per_estimator AS (
        SELECT private.user_email(j.emitted_by) AS estimator,
               COUNT(*)::int AS emitted,
               COUNT(*) FILTER (WHERE j.decision_status IN ('APPROVED','DECLINED'))::int AS decided,
               COUNT(*) FILTER (WHERE j.decision_status = 'APPROVED')::int AS approved,
               ROUND(100.0 * COUNT(*) FILTER (WHERE j.decision_status = 'APPROVED')
                     / NULLIF(COUNT(*) FILTER (WHERE j.decision_status IN ('APPROVED','DECLINED')), 0), 1)
                   AS conversion_pct
          FROM joined j
         GROUP BY 1
    ),
    per_typology AS (
        SELECT COALESCE(typ.typology, '') AS typology,
               COUNT(*)::int AS emitted,
               COUNT(*) FILTER (WHERE j.decision_status IN ('APPROVED','DECLINED'))::int AS decided,
               COUNT(*) FILTER (WHERE j.decision_status = 'APPROVED')::int AS approved,
               ROUND(100.0 * COUNT(*) FILTER (WHERE j.decision_status = 'APPROVED')
                     / NULLIF(COUNT(*) FILTER (WHERE j.decision_status IN ('APPROVED','DECLINED')), 0), 1)
                   AS conversion_pct,
               SUM(COALESCE(j.net, j.net_doc)) AS net
          FROM joined j
          LEFT JOIN typ ON typ.project_id = j.project_id
         GROUP BY 1
    ),
    reasons AS (
        SELECT e.decision,
               COALESCE(NULLIF(btrim(e.decided_note), ''), '«sin motivo escrito»') AS note,
               COUNT(*)::int AS n
          FROM public.customer_approval_events e
          JOIN public.customer_approvals a ON a.id = e.approval_id
          JOIN cohort c ON c.version_id = a.project_version_id
         WHERE e.org_id = target_org
           AND e.decision IN ('DECLINED', 'CHANGES_REQUESTED')
         GROUP BY 1, 2
         ORDER BY n DESC, note
         LIMIT 8
    ),
    detail AS (
        SELECT j.version_id, j.project_id, j.code, j.project_name, j.client_name,
               j.revision_code, j.emitted_at,
               private.user_email(j.emitted_by) AS emitted_by,
               j.decision_status, j.decided_at,
               ROUND(EXTRACT(EPOCH FROM (j.decided_at - j.emitted_at)) / 86400.0, 1)
                   AS decision_days,
               COALESCE(j.net, j.net_doc) AS net
          FROM joined j
         ORDER BY j.emitted_at DESC
    )
    SELECT jsonb_build_object(
        'period', jsonb_build_object('desde', desde, 'hasta', hasta),
        'financial', fin,
        'metrics', jsonb_build_object(
            'emitted', counts.emitted,
            'approved', counts.approved,
            'declined', counts.declined,
            'changes_requested', counts.changes,
            'pending', counts.pending,
            'revoked', counts.revoked,
            'decided', counts.decided,
            'conversion_pct', jsonb_build_object(
                'value', ROUND(100.0 * counts.approved / NULLIF(counts.decided, 0), 1),
                'n', counts.decided,
                'cause', CASE WHEN counts.decided = 0
                         THEN 'ninguna cotización emitida en el período tiene decisión del cliente'
                         END),
            'avg_decision_days', jsonb_build_object(
                'value', counts.avg_decision_days,
                'n', counts.decided,
                'cause', CASE WHEN counts.decided = 0
                         THEN 'ninguna cotización emitida en el período fue decidida aún'
                         END),
            'pipeline_net', jsonb_build_object(
                'value', CASE WHEN fin THEN (
                    SELECT COALESCE(SUM(net), 0) FROM pipeline) END,
                'n', COALESCE((SELECT SUM(n)::int FROM pipeline), 0),
                'cause', CASE WHEN NOT fin THEN 'restricted' END)
        ),
        'pipeline_by_phase', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'phase', phase, 'count', n,
                       'net', CASE WHEN fin THEN net END)
                   ORDER BY phase)
            FROM pipeline), '[]'::jsonb),
        'by_estimator', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'estimator', estimator, 'emitted', emitted,
                       'decided', decided, 'approved', approved,
                       'conversion_pct', conversion_pct))
            FROM per_estimator), '[]'::jsonb),
        'by_typology', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'typology', NULLIF(typology, ''),
                       'emitted', emitted, 'decided', decided,
                       'approved', approved,
                       'conversion_pct', conversion_pct,
                       'net', CASE WHEN fin THEN net END))
            FROM per_typology), '[]'::jsonb),
        'rejection_reasons', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'decision', decision, 'note', note, 'count', n))
            FROM reasons), '[]'::jsonb),
        'rows', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'version_id', version_id, 'project_id', project_id,
                       'code', code, 'project_name', project_name,
                       'client_name', client_name,
                       'revision_code', revision_code, 'emitted_at', emitted_at,
                       'emitted_by', emitted_by,
                       'decision_status', decision_status,
                       'decided_at', decided_at, 'decision_days', decision_days,
                       'net', CASE WHEN fin THEN net END))
            FROM detail), '[]'::jsonb)
    )
    FROM counts);
END;
$fn$;

-- ---------------------------------------------------------------------------
-- MARGEN — obras aprobadas en el período: cotizado sellado vs. costo real
-- medido (consumos valorizados + horas de estación × tarifa + remakes).
CREATE OR REPLACE FUNCTION private.analytics_margins(target_org UUID, desde DATE, hasta DATE)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    fin BOOLEAN := private.analytics_access(target_org);
    hourly NUMERIC := private.analytics_hourly_rate(target_org);
BEGIN
    RETURN (
    WITH obras AS (
        SELECT DISTINCT ON (a.project_id)
               a.project_id, a.project_version_id, a.decided_at AS approved_at,
               v.snapshot_json, v.revision_code,
               p.code, p.name AS project_name, p.client_name
          FROM public.customer_approvals a
          JOIN public.project_versions v
            ON v.id = a.project_version_id AND v.org_id = a.org_id
          JOIN public.projects p
            ON p.id = a.project_id AND p.org_id = a.org_id
         WHERE a.org_id = target_org
           AND a.status = 'APPROVED'
           AND a.decided_at IS NOT NULL
           AND (a.decided_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
         ORDER BY a.project_id, a.decided_at DESC
    ),
    ots AS (
        SELECT o.id, o.project_id, o.order_code, o.status::text AS status,
               (o.payload_json ? 'remake_of') AS is_remake
          FROM public.orders o
          JOIN obras b ON b.project_id = o.project_id
         WHERE o.org_id = target_org AND o.order_type = 'WORKSHOP_OT'
    ),
    move_items AS (
        SELECT m.order_id, m.movement_type, m.quantity, ots.project_id,
               ots.is_remake, i.sku, i.unit,
               sp.unit_price,
               CASE WHEN sp.unit_price IS NOT NULL
                    THEN m.quantity * sp.unit_price END AS amount
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
          JOIN public.inventory_items i ON i.id = m.item_id
          LEFT JOIN private.analytics_sku_prices(target_org) sp
            ON sp.sku = i.sku
         WHERE m.org_id = target_org
           AND m.movement_type IN ('CONSUMPTION', 'SCRAP')
           AND m.item_id IS NOT NULL
    ),
    move_remnants AS (
        SELECT m.order_id, m.movement_type, NULL::numeric AS quantity,
               ots.project_id, ots.is_remake, r.remnant_code AS sku,
               r.kind AS unit,
               private.analytics_remnant_unit_price(target_org, m.remnant_id)
                   AS unit_price,
               CASE WHEN private.analytics_remnant_unit_price(target_org, m.remnant_id) IS NOT NULL
                    THEN private.analytics_remnant_unit_price(target_org, m.remnant_id)
                         * CASE WHEN r.kind = 'BAR' THEN r.length_mm
                                ELSE r.width_mm * r.height_mm END
               END AS amount
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
          JOIN public.inventory_remnants r ON r.id = m.remnant_id
         WHERE m.org_id = target_org
           AND m.movement_type IN ('CONSUMPTION', 'SCRAP')
           AND m.remnant_id IS NOT NULL
    ),
    costs AS (
        SELECT project_id,
               SUM(amount) FILTER (WHERE NOT is_remake
                                   AND movement_type <> 'SCRAP') AS material_normal,
               SUM(amount) FILTER (WHERE movement_type = 'SCRAP') AS scrap,
               SUM(amount) FILTER (WHERE is_remake
                                   AND movement_type <> 'SCRAP') AS remake_material,
               COUNT(*) FILTER (WHERE unit_price IS NULL)::int AS unpriced_count
          FROM (
              SELECT order_id, movement_type, quantity, project_id, is_remake,
                     sku, unit, unit_price, amount
                FROM move_items
              UNION ALL
              SELECT order_id, movement_type, quantity, project_id, is_remake,
                     sku, unit, unit_price, amount
                FROM move_remnants
          ) all_moves
         GROUP BY project_id
    ),
    labor AS (
        SELECT ots.project_id,
               SUM(EXTRACT(EPOCH FROM (s.finished_at - s.started_at)) / 3600.0)
                   FILTER (WHERE NOT ots.is_remake) AS hours_normal,
               SUM(EXTRACT(EPOCH FROM (s.finished_at - s.started_at)) / 3600.0)
                   FILTER (WHERE ots.is_remake) AS hours_remake
          FROM public.production_steps s
          JOIN ots ON ots.id = s.order_id
         WHERE s.org_id = target_org AND s.status = 'DONE'
           AND s.started_at IS NOT NULL AND s.finished_at IS NOT NULL
         GROUP BY ots.project_id
    ),
    ot_state AS (
        SELECT project_id, COUNT(*)::int AS ots_total,
               COUNT(*) FILTER (WHERE status IN ('COMPLETED','DISPATCHED','INSTALLED'))::int
                   AS ots_done
          FROM ots
         GROUP BY project_id
    ),
    typ AS (
        SELECT DISTINCT ON (b.project_id)
               b.project_id, pp.typology
          FROM obras b
          JOIN public.project_positions pp
            ON pp.project_id = b.project_id AND pp.org_id = target_org
         ORDER BY b.project_id, pp.price_net DESC NULLS LAST,
                  pp.position_index ASC
    ),
    computed AS (
        SELECT b.project_id, b.code, b.project_name, b.client_name,
               b.revision_code, b.approved_at, typ.typology,
               NULLIF(b.snapshot_json -> 'pricing' -> 'result' ->> 'project_net', '')::numeric
                   AS quoted_net,
               NULLIF(b.snapshot_json -> 'pricing' -> 'result' ->> 'deal_cost_net', '')::numeric
                   AS quoted_cost,
               COALESCE(c.material_normal, 0) AS real_material,
               COALESCE(c.scrap, 0) AS real_scrap,
               COALESCE(c.remake_material, 0)
                   + COALESCE(l.hours_remake, 0) * COALESCE(hourly, 0) AS real_remake,
               COALESCE(l.hours_normal, 0) * hourly AS real_labor,
               COALESCE(l.hours_normal, 0) + COALESCE(l.hours_remake, 0) AS hours,
               COALESCE(c.unpriced_count, 0) AS unpriced_count,
               COALESCE(os.ots_total, 0) AS ots_total,
               COALESCE(os.ots_done, 0) AS ots_done,
               CASE
                   WHEN COALESCE(os.ots_total, 0) = 0 THEN 'SIN_PRODUCCION'
                   WHEN os.ots_total = os.ots_done THEN 'TERMINADA'
                   ELSE 'EN_PRODUCCION'
               END AS obra_state,
               -- Costo real medido: sin tarifa las horas no valorizan y la
               -- cifra se declara parcial (la causa va en ``missing``).
               (COALESCE(c.material_normal, 0) + COALESCE(c.scrap, 0)
                + COALESCE(c.remake_material, 0)
                + COALESCE(l.hours_remake, 0) * COALESCE(hourly, 0)
                + COALESCE(l.hours_normal, 0) * COALESCE(hourly, 0)) AS real_cost,
               (CASE WHEN hourly IS NULL
                          AND COALESCE(l.hours_normal, 0)
                              + COALESCE(l.hours_remake, 0) > 0
                     THEN ARRAY['tarifa horaria no configurada'] ELSE '{}'::text[] END
                || CASE WHEN COALESCE(c.unpriced_count, 0) > 0
                     THEN ARRAY['material sin precio registrado'] ELSE '{}'::text[] END
               ) AS missing
          FROM obras b
          LEFT JOIN typ ON typ.project_id = b.project_id
          LEFT JOIN costs c ON c.project_id = b.project_id
          LEFT JOIN labor l ON l.project_id = b.project_id
          LEFT JOIN ot_state os ON os.project_id = b.project_id
    ),
    final AS (
        SELECT computed.*,
               CASE WHEN quoted_net > 0 THEN
                   ROUND(100.0 * (quoted_net - quoted_cost) / quoted_net, 1)
               END AS quoted_margin_pct,
               CASE WHEN quoted_net > 0 THEN
                   ROUND(100.0 * (quoted_net - real_cost) / quoted_net, 1)
               END AS real_margin_pct
          FROM computed
    )
    SELECT jsonb_build_object(
        'period', jsonb_build_object('desde', desde, 'hasta', hasta),
        'financial', fin,
        'hourly_rate_configured', hourly IS NOT NULL,
        'metrics', jsonb_build_object(
            'obras', COUNT(*)::int,
            'obras_terminadas', COUNT(*) FILTER (WHERE obra_state = 'TERMINADA')::int,
            'quoted_avg_margin_pct', jsonb_build_object(
                'value', CASE WHEN fin THEN ROUND(AVG(quoted_margin_pct), 1) END,
                'n', COUNT(*) FILTER (WHERE quoted_margin_pct IS NOT NULL)::int,
                'cause', CASE WHEN COUNT(*) FILTER (WHERE quoted_margin_pct IS NOT NULL) = 0
                         THEN 'ninguna obra aprobada en el período tiene margen cotizado sellado'
                         END),
            'real_avg_margin_pct', jsonb_build_object(
                'value', CASE WHEN fin THEN
                    ROUND(AVG(real_margin_pct)
                          FILTER (WHERE obra_state = 'TERMINADA'), 1) END,
                'n', COUNT(*) FILTER (WHERE obra_state = 'TERMINADA'
                                      AND real_margin_pct IS NOT NULL)::int,
                'cause', CASE WHEN COUNT(*) FILTER (WHERE obra_state = 'TERMINADA') = 0
                         THEN 'ninguna obra del período tiene toda su producción terminada'
                         END),
            'deviation_pp', jsonb_build_object(
                'value', CASE WHEN fin THEN ROUND(
                    AVG(real_margin_pct - quoted_margin_pct)
                    FILTER (WHERE obra_state = 'TERMINADA'
                            AND real_margin_pct IS NOT NULL
                            AND quoted_margin_pct IS NOT NULL), 1) END,
                'n', COUNT(*) FILTER (WHERE obra_state = 'TERMINADA'
                                      AND real_margin_pct IS NOT NULL
                                      AND quoted_margin_pct IS NOT NULL)::int,
                'cause', CASE WHEN COUNT(*) FILTER (WHERE obra_state = 'TERMINADA') = 0
                         THEN 'sin obras terminadas no hay margen real comparable'
                         END)
        ),
        'obras', COALESCE(jsonb_agg(jsonb_build_object(
            'project_id', project_id, 'code', code,
            'project_name', project_name, 'client_name', client_name,
            'typology', typology, 'revision_code', revision_code,
            'approved_at', approved_at, 'state', obra_state,
            'ots_total', ots_total, 'ots_done', ots_done,
            'quoted_net', CASE WHEN fin THEN quoted_net END,
            'quoted_cost', CASE WHEN fin THEN quoted_cost END,
            'quoted_margin_pct', CASE WHEN fin THEN quoted_margin_pct END,
            'real_cost', CASE WHEN fin THEN real_cost END,
            'real_margin_pct', CASE WHEN fin THEN real_margin_pct END,
            'deviation_pp', CASE WHEN fin
                                 AND real_margin_pct IS NOT NULL
                                 AND quoted_margin_pct IS NOT NULL
                            THEN ROUND(real_margin_pct - quoted_margin_pct, 1) END,
            'partial', (cardinality(missing) > 0),
            'missing', to_jsonb(missing),
            'unpriced_count', unpriced_count
        ) ORDER BY code), '[]'::jsonb),
        'by_typology', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'typology', typology, 'obras', obras,
                       'avg_deviation_pp', CASE WHEN fin THEN avg_dev END)
                   ORDER BY obras DESC, typology)
              FROM (SELECT typology, COUNT(*)::int AS obras,
                           ROUND(AVG(real_margin_pct - quoted_margin_pct)
                                 FILTER (WHERE obra_state = 'TERMINADA'
                                         AND real_margin_pct IS NOT NULL
                                         AND quoted_margin_pct IS NOT NULL), 1)
                               AS avg_dev
                      FROM final GROUP BY typology) t), '[]'::jsonb)
    )
    FROM final);
END;
$fn$;

-- ---------------------------------------------------------------------------
-- MARGEN — descomposición por obra (roof-raiser §8): cada causa de la
-- diferencia con su monto y el enlace al origen (OTs, movimientos, horas).
CREATE OR REPLACE FUNCTION private.analytics_margin_breakdown(target_org UUID, project UUID)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    fin BOOLEAN := private.analytics_access(target_org);
    hourly NUMERIC := private.analytics_hourly_rate(target_org);
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.projects
         WHERE id = project AND org_id = target_org
    ) THEN
        RAISE EXCEPTION 'analytics_project_not_found' USING ERRCODE = 'P0002';
    END IF;

    RETURN (
    WITH appr AS (
        SELECT DISTINCT ON (a.project_id)
               a.project_id, a.project_version_id, a.decided_at AS approved_at,
               v.snapshot_json, v.revision_code
          FROM public.customer_approvals a
          JOIN public.project_versions v
            ON v.id = a.project_version_id AND v.org_id = a.org_id
         WHERE a.org_id = target_org AND a.project_id = project
           AND a.status = 'APPROVED'
         ORDER BY a.project_id, a.decided_at DESC
    ),
    snap AS (
        SELECT appr.*, p.code, p.name AS project_name, p.client_name
          FROM appr JOIN public.projects p ON p.id = appr.project_id
    ),
    opt_idx AS (
        SELECT o.value AS idx
          FROM snap s,
               LATERAL jsonb_array_elements_text(
                   COALESCE(s.snapshot_json -> 'pricing' -> 'result' -> 'option_indexes',
                            '[]'::jsonb)) AS o(value)
    ),
    positions AS (
        SELECT pos.value ->> 'position_index' AS position_index,
               NULLIF(pos.value ->> 'materials_cost', '')::numeric AS materials_cost,
               NULLIF(pos.value ->> 'area_m2', '')::numeric AS area_m2,
               NULLIF(pos.value ->> 'labor_rate_per_m2', '')::numeric AS labor_rate,
               NULLIF(pos.value ->> 'installation_rate_per_m2', '')::numeric AS install_rate
          FROM snap s,
               LATERAL jsonb_array_elements(
                   COALESCE(s.snapshot_json -> 'pricing' -> 'input_snapshot' -> 'positions',
                            '[]'::jsonb)) pos
         WHERE pos.value ->> 'position_index' IS NULL
            OR pos.value ->> 'position_index' NOT IN (SELECT idx FROM opt_idx)
    ),
    quoted AS (
        SELECT NULLIF(s.snapshot_json -> 'pricing' -> 'result' ->> 'project_net', '')::numeric
                   AS net,
               NULLIF(s.snapshot_json -> 'pricing' -> 'result' ->> 'deal_cost_net', '')::numeric
                   AS cost,
               (SELECT SUM(p.materials_cost) FROM positions p) AS materials_cost,
               (SELECT SUM(p.area_m2 * p.labor_rate) FROM positions p) AS labor_cost,
               (SELECT SUM(p.area_m2 * p.install_rate) FROM positions p) AS install_cost
          FROM snap s
    ),
    lines AS (
        SELECT ld.value ->> 'position_index' AS position_index,
               NULLIF(ld.value ->> 'unit_price', '')::numeric AS unit_price,
               NULLIF(ld.value ->> 'quantity', '')::numeric AS qty,
               NULLIF(ld.value ->> 'discount_pct', '')::numeric AS discount
          FROM snap s,
               LATERAL jsonb_array_elements(
                   COALESCE(s.snapshot_json -> 'pricing' -> 'result' -> 'line_detail',
                            '[]'::jsonb)) ld
    ),
    discount AS (
        SELECT SUM(l.unit_price * l.qty * l.discount) AS discount_net
          FROM lines l
         WHERE l.position_index NOT IN (SELECT idx FROM opt_idx)
            OR NOT EXISTS (SELECT 1 FROM opt_idx)
    ),
    ots AS (
        SELECT o.id, o.order_code, o.status::text AS status,
               (o.payload_json ? 'remake_of') AS is_remake,
               o.created_at,
               (SELECT MIN(e.created_at) FROM public.production_step_events e
                 WHERE e.org_id = o.org_id AND e.order_id = o.id
                   AND e.event = 'WO_COMPLETED') AS completed_at
          FROM public.orders o
         WHERE o.org_id = target_org AND o.project_id = project
           AND o.order_type = 'WORKSHOP_OT'
    ),
    move_items AS (
        SELECT m.id AS movement_id, m.order_id, m.movement_type,
               m.quantity, m.created_at, ots.order_code, ots.is_remake,
               i.sku, i.name AS item_name, i.unit,
               sp.unit_price, sp.price_source,
               CASE WHEN sp.unit_price IS NOT NULL
                    THEN m.quantity * sp.unit_price END AS amount,
               NULL::text AS remnant_code, NULL::numeric AS mm_amount
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
          JOIN public.inventory_items i ON i.id = m.item_id
          LEFT JOIN private.analytics_sku_prices(target_org) sp
            ON sp.sku = i.sku
         WHERE m.org_id = target_org
           AND m.movement_type IN ('CONSUMPTION', 'SCRAP')
           AND m.item_id IS NOT NULL
    ),
    move_remnants AS (
        SELECT m.id AS movement_id, m.order_id, m.movement_type,
               NULL::numeric AS quantity, m.created_at, ots.order_code, ots.is_remake,
               r.remnant_code AS sku, r.remnant_code AS item_name, r.kind AS unit,
               private.analytics_remnant_unit_price(target_org, m.remnant_id) AS unit_price,
               NULL::text AS price_source,
               CASE WHEN private.analytics_remnant_unit_price(target_org, m.remnant_id) IS NOT NULL
                    THEN private.analytics_remnant_unit_price(target_org, m.remnant_id)
                         * CASE WHEN r.kind = 'BAR' THEN r.length_mm
                                ELSE r.width_mm * r.height_mm END
               END AS amount,
               r.remnant_code,
               CASE WHEN r.kind = 'BAR' THEN r.length_mm
                    ELSE r.width_mm * r.height_mm / 1000000.0 END AS mm_amount
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
          JOIN public.inventory_remnants r ON r.id = m.remnant_id
         WHERE m.org_id = target_org
           AND m.movement_type IN ('CONSUMPTION', 'SCRAP')
           AND m.remnant_id IS NOT NULL
    ),
    moves AS (
        SELECT * FROM move_items
        UNION ALL
        SELECT * FROM move_remnants
    ),
    totals AS (
        SELECT
            SUM(amount) FILTER (WHERE NOT is_remake AND movement_type <> 'SCRAP') AS material_normal,
            SUM(amount) FILTER (WHERE movement_type = 'SCRAP') AS scrap,
            SUM(amount) FILTER (WHERE is_remake AND movement_type <> 'SCRAP') AS remake_material,
            COUNT(*) FILTER (WHERE unit_price IS NULL)::int AS unpriced_count
          FROM moves
    ),
    hours AS (
        SELECT s.code AS step_code, s.label, ots.is_remake,
               SUM(EXTRACT(EPOCH FROM (s.finished_at - s.started_at)) / 3600.0) AS hours
          FROM public.production_steps s
          JOIN ots ON ots.id = s.order_id
         WHERE s.org_id = target_org AND s.status = 'DONE'
           AND s.started_at IS NOT NULL AND s.finished_at IS NOT NULL
         GROUP BY s.code, s.label, ots.is_remake
    ),
    labor AS (
        SELECT SUM(hours) FILTER (WHERE NOT is_remake) AS hours_normal,
               SUM(hours) FILTER (WHERE is_remake) AS hours_remake
          FROM hours
    ),
    causes AS (
        SELECT * FROM (VALUES
            ('material',
             COALESCE((SELECT material_normal FROM totals), 0)
               - COALESCE((SELECT materials_cost FROM quoted), 0)),
            ('remake',
             COALESCE((SELECT remake_material FROM totals), 0)
               + COALESCE((SELECT hours_remake FROM labor), 0) * COALESCE(hourly, 0)),
            ('horas',
             COALESCE((SELECT hours_normal FROM labor), 0) * COALESCE(hourly, 0)
               - COALESCE((SELECT labor_cost FROM quoted), 0)),
            ('descarte',
             COALESCE((SELECT scrap FROM totals), 0)),
            ('descuento',
             COALESCE((SELECT discount_net FROM discount), 0))
        ) AS c(key, amount)
    )
    SELECT jsonb_build_object(
        'financial', fin,
        'hourly_rate_configured', hourly IS NOT NULL,
        'project', (SELECT jsonb_build_object(
            'id', s.project_id, 'code', s.code, 'name', s.project_name,
            'client_name', s.client_name, 'revision_code', s.revision_code,
            'approved_at', s.approved_at) FROM snap s),
        'has_snapshot', EXISTS (SELECT 1 FROM snap),
        'quoted', (SELECT jsonb_build_object(
            'net', CASE WHEN fin THEN net END,
            'cost', CASE WHEN fin THEN cost END,
            'margin_pct', CASE WHEN fin AND net > 0
                THEN ROUND(100.0 * (net - cost) / net, 1) END,
            'materials_cost', CASE WHEN fin THEN materials_cost END,
            'labor_cost', CASE WHEN fin THEN labor_cost END,
            'install_cost', CASE WHEN fin THEN install_cost END,
            'discount_net', CASE WHEN fin THEN (SELECT discount_net FROM discount) END
        ) FROM quoted),
        'real', (SELECT jsonb_build_object(
            'material', CASE WHEN fin THEN COALESCE(t.material_normal, 0) END,
            'scrap', CASE WHEN fin THEN COALESCE(t.scrap, 0) END,
            'remake', CASE WHEN fin THEN COALESCE(t.remake_material, 0)
                        + COALESCE((SELECT hours_remake FROM labor), 0)
                            * COALESCE(hourly, 0) END,
            'labor', CASE WHEN fin THEN COALESCE((SELECT hours_normal FROM labor), 0)
                        * hourly END,
            'total', CASE WHEN fin THEN COALESCE(t.material_normal, 0)
                        + COALESCE(t.scrap, 0) + COALESCE(t.remake_material, 0)
                        + COALESCE((SELECT hours_remake FROM labor), 0) * COALESCE(hourly, 0)
                        + COALESCE((SELECT hours_normal FROM labor), 0) * COALESCE(hourly, 0) END,
            'hours', (SELECT ROUND(COALESCE(hours_normal + hours_remake, 0), 2) FROM labor),
            'unpriced_count', COALESCE(t.unpriced_count, 0),
            'missing', to_jsonb(
                CASE WHEN hourly IS NULL
                          AND COALESCE((SELECT hours_normal FROM labor), 0)
                              + COALESCE((SELECT hours_remake FROM labor), 0) > 0
                     THEN ARRAY['tarifa horaria no configurada'] ELSE '{}'::text[] END
                || CASE WHEN COALESCE(t.unpriced_count, 0) > 0
                     THEN ARRAY['material sin precio registrado'] ELSE '{}'::text[] END
                || ARRAY['costo de instalación no medido'])
        ) FROM totals t),
        'causes', COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'key', c.key,
            'amount', CASE WHEN fin THEN ROUND(c.amount, 0) END)
            ORDER BY c.key) FROM causes c), '[]'::jsonb),
        'ots', COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'id', id, 'code', order_code, 'status', status,
            'is_remake', is_remake, 'created_at', created_at,
            'completed_at', completed_at) ORDER BY created_at)
            FROM ots), '[]'::jsonb),
        'movements', COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'id', movement_id, 'order_code', order_code,
            'type', movement_type, 'sku', sku, 'item_name', item_name,
            'quantity', quantity, 'unit', unit,
            'unit_price', CASE WHEN fin THEN unit_price END,
            'price_source', price_source,
            'amount', CASE WHEN fin THEN amount END,
            'remnant_code', remnant_code, 'mm_amount', mm_amount,
            'is_remake', is_remake,
            'created_at', created_at) ORDER BY created_at)
            FROM moves), '[]'::jsonb),
        'hours_by_station', COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'code', step_code, 'label', label, 'hours', ROUND(hours, 2),
            'cost', CASE WHEN fin THEN ROUND(hours * COALESCE(hourly, 0), 0) END,
            'is_remake', is_remake) ORDER BY hours DESC)
            FROM hours), '[]'::jsonb),
        'unpriced', COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'sku', sku, 'quantity', quantity, 'unit', unit))
            FROM (SELECT sku, SUM(quantity) AS quantity, unit FROM move_items
                   WHERE unit_price IS NULL GROUP BY sku, unit) u), '[]'::jsonb)
    ));
END;
$fn$;

-- ---------------------------------------------------------------------------
-- PRODUCCIÓN — merma real vs. plan, aprovechamiento, retazos, tiempos por
-- estación, OTs a tiempo y remakes. Cohorte de merma: OTs que consumieron
-- material en el período o cuyo plan quedó registrado en el período.
CREATE OR REPLACE FUNCTION private.analytics_production(target_org UUID, desde DATE, hasta DATE)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    fin BOOLEAN := private.analytics_access(target_org);
BEGIN
    RETURN (
    WITH ots AS (
        SELECT o.id, o.project_id, o.order_code, o.status::text AS status,
               o.payload_json, o.created_at,
               (o.payload_json ? 'remake_of') AS is_remake
          FROM public.orders o
         WHERE o.org_id = target_org AND o.order_type = 'WORKSHOP_OT'
    ),
    -- La merma de una OT se mide con TODO su libro de consumos (una OT se
    -- consume una sola vez); el período solo elige qué OTs reportan ahora —
    -- las que consumieron o terminaron dentro de la ventana.
    consume AS (
        SELECT m.order_id, m.item_id, m.remnant_id, m.movement_type,
               m.quantity, i.sku, i.unit, m.created_at
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
          LEFT JOIN public.inventory_items i ON i.id = m.item_id
         WHERE m.org_id = target_org
           AND m.movement_type IN ('CONSUMPTION', 'SCRAP')
    ),
    in_period AS (
        SELECT DISTINCT order_id FROM consume
         WHERE (created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
        UNION
        SELECT e.order_id FROM public.production_step_events e
          JOIN ots ON ots.id = e.order_id
         WHERE e.org_id = target_org AND e.event = 'WO_COMPLETED'
           AND (e.created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    -- mm por barra: el plan declara stock_length_mm por sku.
    plan_bar_len AS (
        SELECT ots.id AS order_id,
               bar.value ->> 'stock_sku' AS sku,
               MAX(NULLIF(bar.value ->> 'stock_length_mm', '')::numeric) AS bar_mm
          FROM ots,
               LATERAL jsonb_array_elements(
                   COALESCE(ots.payload_json -> 'optimization' -> 'bars'
                            -> 'workshop_cut_plan', '[]'::jsonb)) bar
         WHERE bar.value ? 'stock_length_mm'
         GROUP BY ots.id, bar.value ->> 'stock_sku'
    ),
    consumed AS (
        SELECT c.order_id,
               SUM(CASE WHEN c.item_id IS NOT NULL AND c.unit = 'BAR'
                        THEN c.quantity * pb.bar_mm END) AS bars_mm,
               SUM(CASE WHEN c.remnant_id IS NOT NULL AND r.kind = 'BAR'
                        THEN r.length_mm END) AS remnant_mm,
               COUNT(*) FILTER (WHERE c.item_id IS NOT NULL AND c.unit = 'BAR'
                                AND pb.bar_mm IS NULL)::int AS bar_unmeasured,
               SUM(CASE WHEN c.item_id IS NOT NULL AND c.unit <> 'BAR'
                        THEN c.quantity
                            * NULLIF(i2.attributes ->> 'sheet_width_mm', '')::numeric
                            * NULLIF(i2.attributes ->> 'sheet_height_mm', '')::numeric
                        WHEN c.remnant_id IS NOT NULL AND r.kind = 'SHEET'
                        THEN r.width_mm * r.height_mm END) AS sheets_mm2
          FROM consume c
          LEFT JOIN plan_bar_len pb
            ON pb.order_id = c.order_id AND pb.sku = c.sku
          LEFT JOIN public.inventory_remnants r ON r.id = c.remnant_id
          LEFT JOIN public.inventory_items i2 ON i2.id = c.item_id
         WHERE c.movement_type = 'CONSUMPTION'
         GROUP BY c.order_id
    ),
    scrapped AS (
        SELECT c.order_id,
               SUM(CASE WHEN c.item_id IS NOT NULL AND c.unit = 'BAR'
                        THEN c.quantity * pb.bar_mm
                        WHEN c.remnant_id IS NOT NULL AND r.kind = 'BAR'
                        THEN r.length_mm END) AS scrap_mm,
               SUM(CASE WHEN c.item_id IS NOT NULL AND c.unit <> 'BAR'
                        THEN c.quantity
                            * NULLIF(i2.attributes ->> 'sheet_width_mm', '')::numeric
                            * NULLIF(i2.attributes ->> 'sheet_height_mm', '')::numeric
                        WHEN c.remnant_id IS NOT NULL AND r.kind = 'SHEET'
                        THEN r.width_mm * r.height_mm END) AS scrap_mm2
          FROM consume c
          LEFT JOIN plan_bar_len pb
            ON pb.order_id = c.order_id AND pb.sku = c.sku
          LEFT JOIN public.inventory_remnants r ON r.id = c.remnant_id
          LEFT JOIN public.inventory_items i2 ON i2.id = c.item_id
         WHERE c.movement_type = 'SCRAP'
         GROUP BY c.order_id
    ),
    plans AS (
        SELECT ots.id AS order_id,
               NULLIF(ots.payload_json -> 'optimization' -> 'bars'
                      -> 'metrics' ->> 'process_waste_mm', '')::numeric AS plan_waste_mm,
               NULLIF(ots.payload_json -> 'optimization' -> 'bars'
                      -> 'metrics' ->> 'productive_length_mm', '')::numeric AS productive_mm,
               (SELECT COALESCE(SUM(NULLIF(b.value ->> 'remainder_mm', '')::numeric), 0)
                  FROM jsonb_array_elements(
                      COALESCE(ots.payload_json -> 'optimization' -> 'produced_bars',
                               '[]'::jsonb)) b) AS returned_mm,
               (SELECT COALESCE(SUM(NULLIF(p2.value ->> 'width_mm', '')::numeric
                                    * NULLIF(p2.value ->> 'height_mm', '')::numeric), 0)
                  FROM jsonb_array_elements(
                      COALESCE(ots.payload_json -> 'optimization' -> 'sheets',
                               '[]'::jsonb)) sh,
                       LATERAL jsonb_array_elements(
                           COALESCE(sh.value -> 'placements', '[]'::jsonb)) p2) AS placed_mm2,
               (SELECT COALESCE(SUM(NULLIF(rm.value ->> 'width_mm', '')::numeric
                                    * NULLIF(rm.value ->> 'height_mm', '')::numeric), 0)
                  FROM jsonb_array_elements(
                      COALESCE(ots.payload_json -> 'optimization' -> 'sheets',
                               '[]'::jsonb)) sh2,
                       LATERAL jsonb_array_elements(
                           COALESCE(sh2.value -> 'produced_remnants', '[]'::jsonb)) rm) AS produced_mm2,
               COALESCE(jsonb_array_length(
                   ots.payload_json -> 'optimization' -> 'produced_bars'), 0)
                   + COALESCE(jsonb_array_length(
                      ots.payload_json -> 'optimization' -> 'produced_sheets'), 0)
                   AS remnants_produced
          FROM ots
    ),
    ot_waste AS (
        SELECT ots.id, ots.order_code, ots.project_id, ots.status,
               p.code AS project_code, plans.plan_waste_mm, plans.productive_mm,
               plans.returned_mm, plans.remnants_produced,
               plans.placed_mm2, plans.produced_mm2,
               COALESCE(con.bars_mm, 0) + COALESCE(con.remnant_mm, 0) AS consumed_mm,
               COALESCE(con.sheets_mm2, 0) AS consumed_mm2,
               COALESCE(sc.scrap_mm, 0) AS scrapped_mm,
               COALESCE(sc.scrap_mm2, 0) AS scrapped_mm2,
               COALESCE(con.bar_unmeasured, 0)::int AS bar_unmeasured,
               -- Barras consumidas cuyo largo no está en el plan: la OT queda
               -- «sin medir» antes que mostrar una merma inventada.
               CASE WHEN COALESCE(con.bar_unmeasured, 0) = 0
                    THEN COALESCE(con.bars_mm, 0) + COALESCE(con.remnant_mm, 0)
                         - COALESCE(plans.productive_mm, 0)
                         - COALESCE(plans.returned_mm, 0)
                         + COALESCE(sc.scrap_mm, 0)
               END AS real_waste_mm,
               -- Placas: sólo hay merma medible si la OT movió placas;
               -- en un plan de barras queda «Sin dato», no 0.
               CASE WHEN COALESCE(con.sheets_mm2, 0) > 0
                      OR COALESCE(sc.scrap_mm2, 0) > 0
                      OR COALESCE(plans.placed_mm2, 0) > 0
                      OR COALESCE(plans.produced_mm2, 0) > 0
                    THEN COALESCE(con.sheets_mm2, 0)
                         - COALESCE(plans.placed_mm2, 0)
                         - COALESCE(plans.produced_mm2, 0)
                         + COALESCE(sc.scrap_mm2, 0)
               END AS real_waste_mm2
          FROM ots
          JOIN in_period ON in_period.order_id = ots.id
          LEFT JOIN plans ON plans.order_id = ots.id
          LEFT JOIN consumed con ON con.order_id = ots.id
          LEFT JOIN scrapped sc ON sc.order_id = ots.id
          LEFT JOIN public.projects p ON p.id = ots.project_id
    ),
    stations AS (
        SELECT s.code, s.label,
               COUNT(*)::int AS n,
               ROUND(AVG(EXTRACT(EPOCH FROM (s.finished_at - s.started_at)) / 3600.0)::numeric, 2)
                   AS avg_hours,
               ROUND(percentile_cont(0.5) WITHIN GROUP
                     (ORDER BY EXTRACT(EPOCH FROM (s.finished_at - s.started_at))
                              / 3600.0)::numeric, 2) AS median_hours
          FROM public.production_steps s
          JOIN ots ON ots.id = s.order_id
         WHERE s.org_id = target_org AND s.status = 'DONE'
           AND s.started_at IS NOT NULL AND s.finished_at IS NOT NULL
           AND (s.finished_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
         GROUP BY s.code, s.label
    ),
    punct AS (
        SELECT ots.id, ots.order_code, p.code AS project_code,
               comp.completed_at, d.committed_date,
               CASE
                   WHEN d.committed_date IS NULL THEN 'SIN_PLAZO'
                   WHEN (comp.completed_at AT TIME ZONE 'America/Santiago')::date
                        <= d.committed_date THEN 'A_TIEMPO'
                   ELSE 'ATRASADA'
               END AS verdict
          FROM ots
          JOIN public.projects p ON p.id = ots.project_id
          JOIN (
              SELECT order_id, MIN(created_at) AS completed_at
                FROM public.production_step_events
               WHERE org_id = target_org AND event = 'WO_COMPLETED'
               GROUP BY order_id
          ) comp ON comp.order_id = ots.id
          LEFT JOIN (
              SELECT order_id, MIN(scheduled_date) AS committed_date
                FROM public.deliveries
               WHERE org_id = target_org
               GROUP BY order_id
          ) d ON d.order_id = ots.id
         WHERE (comp.completed_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    remakes AS (
        SELECT o.id, o.order_code, o.created_at,
               src.order_code AS source_code,
               o.payload_json -> 'remake_reason' AS reason
          FROM public.orders o
          LEFT JOIN public.orders src
            ON src.id::text = o.payload_json ->> 'remake_of'
           AND src.org_id = o.org_id
         WHERE o.org_id = target_org
           AND o.order_type = 'WORKSHOP_OT'
           AND o.payload_json ? 'remake_of'
           AND (o.created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    remnant_stats AS (
        SELECT
            COUNT(*) FILTER (WHERE m.movement_type = 'CONSUMPTION'
                             AND m.remnant_id IS NOT NULL)::int AS consumed,
            COUNT(*) FILTER (WHERE m.movement_type = 'SCRAP'
                             AND m.remnant_id IS NOT NULL)::int AS scrapped
          FROM public.inventory_movements m
          JOIN ots ON ots.id = m.order_id
         WHERE m.org_id = target_org
           AND (m.created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    remnant_produced AS (
        SELECT COUNT(*)::int AS produced
          FROM public.inventory_remnants r
          JOIN ots ON ots.id = r.origin_order_id
         WHERE r.org_id = target_org AND r.origin = 'PRODUCTION'
           AND (r.created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    steps_done AS (
        SELECT COUNT(*)::int AS n
          FROM public.production_steps s
          JOIN ots ON ots.id = s.order_id
         WHERE s.org_id = target_org AND s.status = 'DONE'
           AND (s.finished_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    )
    SELECT jsonb_build_object(
        'period', jsonb_build_object('desde', desde, 'hasta', hasta),
        'financial', fin,
        'metrics', jsonb_build_object(
            'ots_total', (SELECT COUNT(*)::int FROM ots),
            'ots_remakes', (SELECT COUNT(*)::int FROM remakes),
            'merma_plan_mm', jsonb_build_object(
                'value', (SELECT SUM(plan_waste_mm) FROM ot_waste),
                'n', (SELECT COUNT(*)::int FROM ot_waste),
                'cause', CASE WHEN (SELECT COUNT(*) FROM ot_waste) = 0
                         THEN 'no hay órdenes de taller con plan o consumo en el período'
                         END),
            'merma_real_mm', jsonb_build_object(
                'value', (SELECT SUM(real_waste_mm) FROM ot_waste),
                'n', (SELECT COUNT(*)::int FROM ot_waste
                      WHERE real_waste_mm IS NOT NULL),
                'cause', CASE WHEN (SELECT COUNT(*) FROM ot_waste
                                    WHERE real_waste_mm IS NOT NULL) = 0
                         THEN 'no hay consumo de material medible registrado en el período'
                         END),
            'merma_placas_mm2', jsonb_build_object(
                'value', (SELECT SUM(real_waste_mm2) FROM ot_waste),
                'n', (SELECT COUNT(*)::int FROM ot_waste
                      WHERE consumed_mm2 > 0 OR placed_mm2 > 0),
                'cause', CASE WHEN (SELECT COUNT(*) FROM ot_waste
                                    WHERE consumed_mm2 > 0 OR placed_mm2 > 0) = 0
                         THEN 'no hay consumo de placas registrado en el período'
                         END),
            'aprovechamiento_pct', jsonb_build_object(
                'value', (SELECT ROUND(100.0 * SUM(productive_mm)
                            / NULLIF(SUM(consumed_mm), 0), 1)
                            FROM ot_waste WHERE consumed_mm > 0),
                'n', (SELECT COUNT(*)::int FROM ot_waste WHERE consumed_mm > 0),
                'cause', CASE WHEN (SELECT COUNT(*) FROM ot_waste
                                    WHERE consumed_mm > 0) = 0
                         THEN 'sin mm consumidos no hay aprovechamiento que medir'
                         END),
            'ot_punctuality', jsonb_build_object(
                'a_tiempo', (SELECT COUNT(*)::int FROM punct WHERE verdict = 'A_TIEMPO'),
                'atrasadas', (SELECT COUNT(*)::int FROM punct WHERE verdict = 'ATRASADA'),
                'sin_plazo', (SELECT COUNT(*)::int FROM punct WHERE verdict = 'SIN_PLAZO'),
                'on_time_pct', jsonb_build_object(
                    'value', (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE verdict = 'A_TIEMPO')
                               / NULLIF(COUNT(*) FILTER (WHERE verdict IN ('A_TIEMPO','ATRASADA')), 0), 1)
                              FROM punct),
                    'n', (SELECT COUNT(*)::int FROM punct
                          WHERE verdict IN ('A_TIEMPO','ATRASADA')),
                    'cause', CASE WHEN (SELECT COUNT(*) FROM punct
                                        WHERE verdict IN ('A_TIEMPO','ATRASADA')) = 0
                             THEN 'ninguna OT completada en el período tenía fecha comprometida'
                             END)),
            'steps_done', (SELECT n FROM steps_done)
        ),
        'ot_waste', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'order_id', id, 'order_code', order_code,
                       'project_code', project_code, 'status', status,
                       'plan_waste_mm', plan_waste_mm,
                       'productive_mm', productive_mm,
                       'consumed_mm', consumed_mm,
                       'scrapped_mm', scrapped_mm,
                       'real_waste_mm', real_waste_mm,
                       'real_waste_mm2', real_waste_mm2,
                       'unmeasured', (bar_unmeasured > 0),
                       'delta_mm', real_waste_mm - COALESCE(plan_waste_mm, 0),
                       'utilization_pct', ROUND(100.0 * productive_mm
                           / NULLIF(consumed_mm, 0), 1),
                       'remnants_produced', remnants_produced)
                   ORDER BY real_waste_mm DESC NULLS LAST)
            FROM ot_waste), '[]'::jsonb),
        'station_times', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'code', code, 'label', label, 'n', n,
                       'avg_hours', avg_hours, 'median_hours', median_hours)
                   ORDER BY avg_hours DESC NULLS LAST)
            FROM stations), '[]'::jsonb),
        'retazos', jsonb_build_object(
            'consumed', COALESCE((SELECT consumed FROM remnant_stats), 0),
            'produced', COALESCE((SELECT produced FROM remnant_produced), 0),
            'scrapped', COALESCE((SELECT scrapped FROM remnant_stats), 0)),
        'remakes', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'order_id', id, 'order_code', order_code,
                       'source_code', source_code, 'reason', reason,
                       'created_at', created_at) ORDER BY created_at DESC)
            FROM remakes), '[]'::jsonb),
        'ot_rows', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'order_id', id, 'order_code', order_code,
                       'project_code', project_code,
                       'completed_at', completed_at,
                       'committed_date', committed_date,
                       'verdict', verdict) ORDER BY completed_at DESC)
            FROM punct), '[]'::jsonb)
    ));
END;
$fn$;

-- ---------------------------------------------------------------------------
-- INSTALACIÓN Y POSTVENTA — entregas a tiempo, incidencias y garantías.
CREATE OR REPLACE FUNCTION private.analytics_field(target_org UUID, desde DATE, hasta DATE)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
DECLARE
    fin BOOLEAN := private.analytics_access(target_org);
BEGIN
    RETURN (
    WITH dels AS (
        SELECT d.id, d.order_id, d.scheduled_date, d.status, d.updated_at,
               o.order_code, o.project_id, p.code AS project_code
          FROM public.deliveries d
          JOIN public.orders o ON o.id = d.order_id AND o.org_id = d.org_id
          JOIN public.projects p ON p.id = o.project_id
         WHERE d.org_id = target_org
           AND d.scheduled_date BETWEEN desde AND hasta
    ),
    delivered_ts AS (
        SELECT order_id, MIN(created_at) AS delivered_at
          FROM public.production_step_events
         WHERE org_id = target_org AND event = 'WO_DELIVERY_DELIVERED'
         GROUP BY order_id
    ),
    del_verdict AS (
        SELECT dels.*,
               COALESCE(dt.delivered_at,
                        CASE WHEN dels.status = 'DELIVERED' THEN dels.updated_at END)
                   AS delivered_at,
               CASE
                   WHEN dels.status = 'FAILED' THEN 'FALLIDA'
                   WHEN dels.status IN ('SCHEDULED','ON_ROUTE')
                        AND dels.scheduled_date < CURRENT_DATE THEN 'VENCIDA'
                   WHEN dels.status IN ('SCHEDULED','ON_ROUTE') THEN 'PENDIENTE'
                   WHEN (COALESCE(dt.delivered_at, dels.updated_at)
                         AT TIME ZONE 'America/Santiago')::date
                        <= dels.scheduled_date THEN 'A_TIEMPO'
                   ELSE 'ATRASADA'
               END AS verdict
          FROM dels
          LEFT JOIN delivered_ts dt ON dt.order_id = dels.order_id
    ),
    installed AS (
        SELECT COUNT(*)::int AS n
          FROM public.production_step_events e
         WHERE e.org_id = target_org AND e.event = 'WO_INSTALLED'
           AND (e.created_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    checks AS (
        SELECT COUNT(*)::int AS n
          FROM public.installation_checks c
         WHERE c.org_id = target_org
           AND (c.checked_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    incidents AS (
        SELECT i.id, i.code, i.kind, i.status, i.reported_at, i.order_id,
               o.order_code, o.project_id, p.code AS project_code,
               pp.typology
          FROM public.site_incidents i
          JOIN public.orders o ON o.id = i.order_id AND o.org_id = i.org_id
          JOIN public.projects p ON p.id = o.project_id
          LEFT JOIN public.project_positions pp
            ON pp.id::text = o.payload_json ->> 'position_id'
           AND pp.org_id = i.org_id
         WHERE i.org_id = target_org
           AND (i.reported_at AT TIME ZONE 'America/Santiago')::date
               BETWEEN desde AND hasta
    ),
    incidents_open AS (
        SELECT COUNT(*)::int AS n
          FROM public.site_incidents
         WHERE org_id = target_org AND status IN ('OPEN','IN_PROGRESS')
    ),
    tickets AS (
        SELECT t.id, t.code, t.kind, t.status, t.warranty_until, t.created_at,
               p.code AS project_code, o.order_code
          FROM public.service_tickets t
          JOIN public.projects p ON p.id = t.project_id
          LEFT JOIN public.orders o ON o.id = t.order_id AND o.org_id = t.org_id
         WHERE t.org_id = target_org
    ),
    warranty AS (
        SELECT
            COUNT(*) FILTER (WHERE kind = 'WARRANTY'
                AND status IN ('OPEN','SCHEDULED','IN_PROGRESS'))::int AS open_now,
            COUNT(*) FILTER (WHERE kind = 'WARRANTY'
                AND status IN ('OPEN','SCHEDULED','IN_PROGRESS')
                AND warranty_until IS NOT NULL
                AND warranty_until <= CURRENT_DATE + 60)::int AS expiring_60d,
            COUNT(*) FILTER (WHERE (created_at AT TIME ZONE 'America/Santiago')::date
                    BETWEEN desde AND hasta)::int AS created_in_period
          FROM tickets
    )
    SELECT jsonb_build_object(
        'period', jsonb_build_object('desde', desde, 'hasta', hasta),
        'financial', fin,
        'metrics', jsonb_build_object(
            'deliveries', (SELECT COUNT(*)::int FROM del_verdict),
            'deliveries_on_time_pct', jsonb_build_object(
                'value', (SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE verdict = 'A_TIEMPO')
                          / NULLIF(COUNT(*) FILTER (WHERE verdict IN ('A_TIEMPO','ATRASADA')), 0), 1)
                          FROM del_verdict),
                'n', (SELECT COUNT(*)::int FROM del_verdict
                      WHERE verdict IN ('A_TIEMPO','ATRASADA')),
                'cause', CASE WHEN (SELECT COUNT(*) FROM del_verdict
                                    WHERE verdict IN ('A_TIEMPO','ATRASADA')) = 0
                         THEN 'ninguna entrega del período llegó aún a destino'
                         END),
            'deliveries_failed', (SELECT COUNT(*)::int FROM del_verdict WHERE verdict = 'FALLIDA'),
            'deliveries_pending', (SELECT COUNT(*)::int FROM del_verdict
                                   WHERE verdict IN ('PENDIENTE','VENCIDA')),
            'installations', (SELECT n FROM installed),
            'installation_checks', (SELECT n FROM checks),
            'incidents', (SELECT COUNT(*)::int FROM incidents),
            'incidents_open', (SELECT n FROM incidents_open),
            'warranties_open', (SELECT open_now FROM warranty),
            'warranties_expiring', (SELECT expiring_60d FROM warranty),
            'tickets_created', (SELECT created_in_period FROM warranty)
        ),
        'deliveries', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'id', id, 'order_code', order_code,
                       'project_code', project_code,
                       'scheduled_date', scheduled_date,
                       'delivered_at', delivered_at,
                       'status', status, 'verdict', verdict)
                   ORDER BY scheduled_date DESC)
            FROM del_verdict), '[]'::jsonb),
        'incidents_by_kind', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('kind', kind, 'count', n)
                   ORDER BY n DESC)
            FROM (SELECT kind, COUNT(*)::int AS n FROM incidents GROUP BY kind) k), '[]'::jsonb),
        'incidents_by_typology', COALESCE((
            SELECT jsonb_agg(jsonb_build_object('typology', typology, 'count', n)
                   ORDER BY n DESC)
            FROM (SELECT typology, COUNT(*)::int AS n
                    FROM incidents GROUP BY typology) t2), '[]'::jsonb),
        'incidents', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'id', id, 'code', code, 'kind', kind, 'status', status,
                       'order_code', order_code, 'project_code', project_code,
                       'typology', typology, 'reported_at', reported_at)
                   ORDER BY reported_at DESC)
            FROM incidents), '[]'::jsonb),
        'warranties', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'id', id, 'code', code, 'status', status,
                       'project_code', project_code, 'order_code', order_code,
                       'warranty_until', warranty_until, 'created_at', created_at)
                   ORDER BY warranty_until ASC NULLS LAST)
            FROM (SELECT * FROM tickets WHERE kind = 'WARRANTY'
                  AND status IN ('OPEN','SCHEDULED','IN_PROGRESS')) w), '[]'::jsonb)
    ));
END;
$fn$;

-- ---------------------------------------------------------------------------
-- Detalle/exportación F6: las filas detrás de una métrica — la misma forma
-- que alimenta la tabla de detalle y el CSV (decimales canónicos).
CREATE OR REPLACE FUNCTION private.analytics_export_rows(target_org UUID, metric TEXT,
                                              desde DATE, hasta DATE)
RETURNS JSONB
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
BEGIN
    -- Sello de acceso; el recorte financiero lo aplica cada función de sección.
    PERFORM private.analytics_access(target_org);
    CASE metric
        WHEN 'quotes' THEN
            RETURN private.analytics_sales(target_org, desde, hasta) -> 'rows';
        WHEN 'obras' THEN
            RETURN private.analytics_margins(target_org, desde, hasta) -> 'obras';
        WHEN 'ots' THEN
            RETURN private.analytics_production(target_org, desde, hasta) -> 'ot_waste';
        WHEN 'steps' THEN
            RETURN private.analytics_production(target_org, desde, hasta) -> 'station_times';
        WHEN 'remakes' THEN
            RETURN private.analytics_production(target_org, desde, hasta) -> 'remakes';
        WHEN 'deliveries' THEN
            RETURN private.analytics_field(target_org, desde, hasta) -> 'deliveries';
        WHEN 'incidents' THEN
            RETURN private.analytics_field(target_org, desde, hasta) -> 'incidents';
        WHEN 'warranties' THEN
            RETURN private.analytics_field(target_org, desde, hasta) -> 'warranties';
        ELSE
            RAISE EXCEPTION 'analytics_metric_unknown' USING ERRCODE = '22023';
    END CASE;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- Grants: funciones de lectura para backend + authenticated (pgTAP ejerce el
-- aislamiento bajo el rol real). Los helpers internos quedan cerrados.
REVOKE ALL ON FUNCTION private.analytics_access(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_hourly_rate(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_sku_prices(UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_remnant_unit_price(UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_sales(UUID, DATE, DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_margins(UUID, DATE, DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_margin_breakdown(UUID, UUID) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_production(UUID, DATE, DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_field(UUID, DATE, DATE) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.analytics_export_rows(UUID, TEXT, DATE, DATE) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION private.analytics_access(UUID)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_hourly_rate(UUID)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_sku_prices(UUID)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_remnant_unit_price(UUID, UUID)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_sales(UUID, DATE, DATE)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_margins(UUID, DATE, DATE)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_margin_breakdown(UUID, UUID)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_production(UUID, DATE, DATE)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_field(UUID, DATE, DATE)
    TO documentary_backend, authenticated;
GRANT EXECUTE ON FUNCTION private.analytics_export_rows(UUID, TEXT, DATE, DATE)
    TO documentary_backend, authenticated;
