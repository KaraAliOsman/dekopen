"""Resolved commercial authorities inside verified, transaction-local RLS."""

from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json
from uuid import UUID

from django.db import connection, DatabaseError

from authentication.rls import tx_aborted
from psycopg import sql

from dekopen_engine.commercial import PricingError, convert_cost


def encode(value):
    if isinstance(value, (Decimal, UUID, date)):
        return str(value)
    raise TypeError(f'Unsupported persisted type: {type(value).__name__}')


def json_text(value):
    return json.dumps(value, default=encode, sort_keys=True, separators=(',', ':'), allow_nan=False)


def rows(query, parameters=()):
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def write(query, parameters=()):
    """Statement without a row result — returns rowcount.
    `rows()` is SELECT-only: `cursor.description` is None on writes."""
    with connection.cursor() as cursor:
        cursor.execute(query, parameters)
        return cursor.rowcount


def one(query, parameters=(), code='authority_not_found'):
    result = rows(query, parameters)
    if len(result) != 1:
        raise PricingError('ambiguous_authority' if result else code)
    return result[0]


def audit_reason(reason: str):
    if not reason.strip():
        raise PricingError('audit_reason_required')
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.pricing_reason',%s,true)", [reason])


@contextmanager
def commercial_backend():
    # Session user is trusted; clients never receive membership in this role.
    # Its own tenant RLS policies remain active and JWT claims remain unchanged.
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL ROLE pricing_backend')
    try:
        yield
    except DatabaseError:
        # A PostgreSQL statement error aborts the transaction even when Django
        # has not marked needs_rollback yet. Do not mask it with SET ROLE.
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE authenticated')
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE authenticated')


class PricingRepository:
    def __init__(self, org_id, effective_date: date, currency: str, fx_id=None):
        self.org_id = org_id
        self.effective_date = effective_date
        self.currency = currency
        self.fx_id = fx_id
        self.authorities = []

    def convert(self, value, currency):
        snapshot = None
        if currency != self.currency:
            if self.fx_id is None:
                raise PricingError('missing_fx_authority')
            snapshot = one(
                'SELECT * FROM public.pricing_fx_snapshots WHERE id=%s AND org_id=%s '
                'AND effective_date=%s AND base_currency=%s AND quote_currency=%s',
                [self.fx_id,self.org_id,self.effective_date,currency,self.currency],
                'missing_fx_authority')
            self.authorities.append({'fx': snapshot})
        return convert_cost(value,currency,self.currency,
                            None if snapshot is None else snapshot['observed_rate'])

    def cost(self, sku: str, required_unit: str):
        candidates = rows(
            'SELECT i.id,i.sku,i.unit,i.unit_cost,l.id AS cost_list_id,l.currency,l.valid_from,l.valid_to '
            'FROM public.cost_list_items i JOIN public.cost_lists l '
            'ON l.id=i.cost_list_id AND l.org_id=i.org_id '
            'WHERE i.org_id=%s AND i.sku=%s AND l.is_active AND l.valid_from<=%s '
            'AND (l.valid_to IS NULL OR l.valid_to>=%s) ORDER BY l.valid_from DESC',
            [self.org_id,sku,self.effective_date,self.effective_date])
        if not candidates:
            raise PricingError('cost_list_not_found')
        latest = [item for item in candidates if item['valid_from'] == candidates[0]['valid_from']]
        if len(latest) != 1:
            raise PricingError('ambiguous_cost_list')
        value = latest[0]
        if value['unit'].upper() != required_unit.upper():
            raise PricingError('incompatible_cost_unit')
        self.authorities.append({'cost': value})
        return self.convert(value['unit_cost'],value['currency'])

    def configuration(self, mode, context, typology):
        config = one(
            'SELECT * FROM public.pricing_configurations WHERE org_id=%s AND pricing_mode=%s '
            'AND context_code=%s AND typology=%s AND is_active',
            [self.org_id,mode,context,typology], 'pricing_configuration_not_found')
        self.authorities.append({'configuration': config})
        return config

    def matrix(self, configuration):
        cells = rows('SELECT width_mm,height_mm,price FROM public.pricing_matrix_cells '
                     'WHERE org_id=%s AND configuration_id=%s',
                     [self.org_id,configuration['id']])
        self.authorities.append({'cells': cells})
        return {(cell['width_mm'],cell['height_mm']): self.convert(cell['price'],configuration['currency'])
                for cell in cells}


ADMIN_TABLES = {
    'cost-lists': ('cost_lists', ('supplier_name','description','currency','valid_from','valid_to','is_active')),
    'cost-items': ('cost_list_items', ('cost_list_id','sku','description','item_type','unit','unit_cost')),
    'rules': ('pricing_rules', ('pricing_mode','default_margin_pct','tax_rate_pct','waste_factor_pct',
                              'labor_rate_per_m2','installation_rate_per_m2',
                              'margin_min_pct','margin_max_pct',
                              'discount_approval_threshold_pct')),
    'configurations': ('pricing_configurations', ('context_code','typology','pricing_mode','currency',
                                                'rate_per_m2','base_glass_sku','catalog_price','is_active')),
    'matrix-cells': ('pricing_matrix_cells', ('configuration_id','width_mm','height_mm','price')),
    'fx': ('pricing_fx_snapshots', ('base_currency','quote_currency','observed_rate',
                                 'observed_date','effective_date','source')),
}


def admin_list(resource, org_id):
    if resource == 'audits':
        return rows('SELECT l.*, p.code AS project_code, p.name AS project_name '
                    'FROM public.price_audit_logs l '
                    'LEFT JOIN public.projects p ON p.id=l.project_id AND p.org_id=l.org_id '
                    'WHERE l.org_id=%s ORDER BY l.created_at DESC,l.id LIMIT 200', [org_id])
    if resource == 'coverage':
        # P07 — los SKU que el motor efectivamente pide a la lista de costos:
        # las identidades de compra declaradas por el catálogo (no la
        # clase técnica). org_id NULL = catálogo global compartido.
        return rows("""WITH catalog AS (
            SELECT m.commercial_sku::text AS sku, a.name::text AS name,
                   'PROFILE'::text AS kind, 'M'::text AS required_unit
              FROM public.profile_purchase_mappings m
              JOIN public.profile_articles a ON a.id=m.profile_article_id
             WHERE m.org_id=%s OR m.org_id IS NULL
            UNION ALL
            SELECT r.commercial_sku::text, r.name::text, 'REINFORCEMENT', 'M'
              FROM public.reinforcement_articles r
             WHERE r.org_id=%s OR r.org_id IS NULL
            UNION ALL
            SELECT g.technical_sku::text, g.manufacturer_name::text, 'GLASS', 'M2'
              FROM public.glass_purchase_mappings g
             WHERE g.org_id=%s OR g.org_id IS NULL
            UNION ALL
            SELECT g.purchasing_sku::text, g.manufacturer_name::text, 'GLASS', 'EA'
              FROM public.glass_purchase_mappings g
             WHERE g.org_id=%s OR g.org_id IS NULL
            UNION ALL
            SELECT p.sku::text, p.name::text, 'PANEL', 'M2'
              FROM public.infill_articles p
             WHERE p.org_id=%s OR p.org_id IS NULL
            UNION ALL
            SELECT p.purchasing_sku::text, p.manufacturer_name::text, 'PANEL', 'EA'
              FROM public.panel_purchase_authorities p
             WHERE p.org_id=%s OR p.org_id IS NULL
            UNION ALL
            SELECT k.sku::text, k.name::text, 'HARDWARE', 'KIT'
              FROM public.hardware_kits k
             WHERE k.org_id=%s OR k.org_id IS NULL
            UNION ALL
            SELECT h.purchasing_sku::text, h.manufacturer_name::text, 'HARDWARE', 'KIT'
              FROM public.hardware_purchase_mappings h
             WHERE h.org_id=%s OR h.org_id IS NULL
            UNION ALL
            SELECT f.technical_sku::text, f.manufacturer_name::text, 'FITTING', 'EA'
              FROM public.fitting_purchase_mappings f
             WHERE f.org_id=%s OR f.org_id IS NULL
            UNION ALL
            SELECT f.purchasing_sku::text, f.manufacturer_name::text, 'FITTING', 'EA'
              FROM public.fitting_purchase_mappings f
             WHERE f.org_id=%s OR f.org_id IS NULL
        )
        SELECT c.sku, c.name, c.kind, c.required_unit, COUNT(i.id) AS active_cost_items
        FROM catalog c
        LEFT JOIN public.cost_list_items i
          ON i.org_id=%s AND i.sku=c.sku
         AND EXISTS (SELECT 1 FROM public.cost_lists l
                     WHERE l.id=i.cost_list_id AND l.org_id=%s AND l.is_active
                       AND (l.valid_to IS NULL OR l.valid_to>=current_date))
        GROUP BY c.sku, c.name, c.kind, c.required_unit
        ORDER BY COUNT(i.id), c.kind, c.sku""", [org_id]*11)
    if resource not in ADMIN_TABLES:
        raise PricingError('unknown_pricing_resource')
    table, _ = ADMIN_TABLES[resource]
    return rows(sql.SQL('SELECT * FROM public.{} WHERE org_id=%s ORDER BY id').format(sql.Identifier(table)), [org_id])


def admin_write(resource, org_id, values, reason, row_id=None):
    if resource not in ADMIN_TABLES:
        raise PricingError('unknown_pricing_resource')
    if resource == 'fx' and row_id is not None:
        raise PricingError('fx_snapshot_immutable')
    table, fields = ADMIN_TABLES[resource]
    data = {key: value for key,value in values.items() if key in fields}
    if not data or set(values)-set(fields):
        raise PricingError('invalid_admin_fields')
    audit_reason(reason)
    if row_id is None:
        data['org_id'] = org_id
        statement = sql.SQL('INSERT INTO public.{} ({}) VALUES ({}) RETURNING *').format(
            sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,data)),
            sql.SQL(',').join(sql.Placeholder() for _ in data))
        return one(statement,list(data.values()))
    statement = sql.SQL('UPDATE public.{} SET {} WHERE id=%s AND org_id=%s RETURNING *').format(
        sql.Identifier(table),sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(key)) for key in data))
    return one(statement,[*data.values(),row_id,org_id])
