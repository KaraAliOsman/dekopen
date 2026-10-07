"""Server-authoritative BOM costing, reproducible previews and approvals."""

from dataclasses import asdict
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from uuid import UUID

from django.db import connection, DatabaseError

from authentication.errors import contract_error
from authentication.rls import tx_aborted
from dekopen_engine.cascade import (
    CascadeComponent, CascadePosition, DeltaLine, DeltaStage,
    band_state, component_group, delta_contributions, price_cascade,
)
from dekopen_engine.commercial import (
    CommercialLine, PricingError, PricingMode, direct_cost, discount_state,
    finish_lines, target_project, unit_price, validate_segment,
)
from dekopen_engine.extras import evaluate_service_lines
from dekopen_engine.glass import exact_glass_area_m2
from dekopen_engine.glass_pricing import glass_price_lines
from dekopen_engine.models import (
    GlassSurchargeRate,
    PieceOrigin,
    ServiceArticle,
    ServiceKind,
    ServicePositionMeasure,
    ServiceQtyRule,
)
from engine_api.adapter import engine_result_from_api
from engine_api.cutting_repository import CuttingRepository
from engine_api.repository import SystemParamsRepository
from pricing.repository import PricingRepository, audit_reason, json_text, one, rows

D = Decimal

# Human es-CL detail per pricing failure code — the HTTP layer renders
# these so an estimator sees what to fix, never a raw engine code. Codes
# raised while iterating positions get prefixed with the position label
# ("Vano 3 · Dormitorio: …") so the blocker names where it lives.
PRICING_ERROR_DETAILS = {
    'ambiguous_authority': 'hay más de una autoridad de costos vigente para la fecha; revisa las listas de costos',
    'ambiguous_cost_list': 'hay más de una lista de costos vigente; revisa las vigencias en Configuración',
    'ambiguous_selected_glass': 'usa más de un vidrio distinto y el precio por m² exige un solo vidrio por vano',
    'audit_reason_required': 'indica el motivo del cambio para dejar trazabilidad',
    'authority_not_found': 'no se encontró la autoridad comercial requerida; revisa la configuración de precios',
    'commercial_revision_required': 'requiere una nueva revisión antes de cotizar; crea la revisión siguiente desde el proyecto',
    'cost_list_not_found': 'no existe la lista de costos indicada',
    'fx_snapshot_immutable': 'la cotización de moneda ya está cerrada',
    'glass_bay_not_found': 'no se encontró su paño de vidrio; revisa el diseño',
    'extra_price_missing': 'un accesorio seleccionado no declara precio en el catálogo; declara su precio o quita la selección',
    'hardware_option_price_missing': 'una selección de herraje vendible no declara precio en el catálogo; declara su delta o quita la selección',
    'incompatible_cost_unit': 'la unidad de costo de un material no es compatible con su uso; revisa la lista de costos',
    'invalid_admin_fields': 'revisa los campos de configuración',
    'invalid_column_mapping': 'revisa el mapeo de columnas del archivo',
    'invalid_xlsx_file': 'el archivo Excel no es válido o está dañado',
    'missing_fx_authority': 'falta la cotización de moneda para la fecha; regístrala antes de cotizar en otra moneda',
    'missing_glass_authority': 'no hay precio registrado para el vidrio seleccionado; agrégalo a la lista de costos o cambia el vidrio',
    'missing_selected_glass_sku': 'no declara el vidrio seleccionado; revisa el diseño',
    'negative_margin': 'la operación dejaría margen negativo; ajusta el precio o el costo',
    'operation_already_final': 'la operación de precios ya está cerrada',
    'operation_not_withdrawable': 'la operación ya no se puede anular',
    'owner_approval_required': 'el descuento requiere aprobación del dueño',
    'owner_confirmation_required': 'esta operación requiere la confirmación del dueño',
    'pricing_operation_not_found': 'no se encontró la operación comercial indicada; recarga el listado',
    'pricing_permission_denied': 'tu rol no permite esta operación comercial',
    'pricing_rules_not_found': 'no hay reglas de precio configuradas para tu taller; registra margen e impuesto en Ajustes → Costos y precios → Reglas comerciales antes de cotizar',
    'project_has_no_positions': 'el proyecto no tiene vanos para cotizar',
    'project_not_found': 'no se encontró el proyecto; recarga y vuelve a intentar',
    'service_price_missing': 'un servicio del proyecto no declara precio en el catálogo; declara su precio o quita el servicio',
    'stale_pricing_operation': 'los precios cambiaron desde que preparaste la operación; recarga y vuelve a aplicar',
    'target_margin_already_defines_final_price': 'el margen objetivo ya define el precio final y no admite descuento adicional',
    'unknown_pricing_resource': 'la configuración no está disponible',
    'xlsx_expanded_limit': 'el archivo supera el límite de filas permitido',
    'xlsx_header_missing_or_duplicate': 'el Excel no tiene los encabezados esperados o los repite',
    'xlsx_no_rows': 'el archivo no contiene filas de datos',
    'xlsx_sheet_limit': 'el archivo supera el tamaño permitido',
}


def _position_label(position):
    tag = (position.get('location_tag') or '').strip()
    return f"Vano {position['position_index']}" + (f" · {tag}" if tag else "")


def pricing_public_detail(code):
    """Failure code → standalone human sentence, for surfaces that show the
    detail without a position prefix (view mapping, batch item errors)."""
    detail = PRICING_ERROR_DETAILS.get(
        code,'la operación comercial requiere revisar sus permisos, datos o configuración')
    return detail[0].upper() + detail[1:] + '.'


def glass_sku(tree, bay_id):
    if tree.get('id') == bay_id:
        sku = tree.get('glass_article_sku')
        if not sku:
            raise PricingError('missing_selected_glass_sku')
        return sku
    for child in tree.get('children', []):
        try:
            return glass_sku(child,bay_id)
        except PricingError as error:
            if error.code != 'glass_bay_not_found':
                raise
    raise PricingError('glass_bay_not_found')


def design_glass_sku(tree, bay_id):
    # Assembly BOM items carry 'module_id|bay_id' — resolve inside the module tree.
    if isinstance(tree, dict) and tree.get('version') == 'product-v2':
        module_id, separator, inner_id = bay_id.partition('|')
        if not separator:
            raise PricingError('glass_bay_not_found')
        for module in tree.get('assembly', {}).get('modules', []):
            if module.get('id') == module_id:
                return glass_sku(module.get('tree', {}), inner_id)
        raise PricingError('glass_bay_not_found')
    return glass_sku(tree, bay_id)


def decoded(value):
    return json.loads(value, parse_float=Decimal) if isinstance(value,str) else value


def _composition_module(bay_id):
    """P06 — module attribution of a costed piece: assembly BOM ids are
    'module_id|inner_id'; a piece without that prefix (coupler cuts carry
    the coupling id, set-level surcharges carry none) stays unattributed —
    it prices into the set's shared bucket, never into a wrong module."""
    if isinstance(bay_id, str) and '|' in bay_id:
        return bay_id.partition('|')[0]
    return None


def source_revision(project, positions):
    # Full technical input plus stored commercial values detects edits and applies.
    return sha256(json_text({'project':project,'positions':positions}).encode()).hexdigest()


def linear_cost(repo, sku, length, stock_length):
    try:
        return repo.cost(sku,'BAR') * length / stock_length
    except PricingError as error:
        if error.code != 'incompatible_cost_unit':
            raise
        return repo.cost(sku,'M') * length / D('1000')


def position_cost(repo, position, rules):
    # Technical catalog has its existing authenticated policies; commercial raw
    # costs are read only after returning to the backend calculator role.
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL ROLE authenticated')
    try:
        params = SystemParamsRepository().load_visible(position['system_id'],repo.org_id)
        stock_repo = CuttingRepository()
        profile_stocks = {}
        steel_stocks = {}
        tree = decoded(position['parametric_tree'])
        color_interior = str(position['color_interior'])
        color_exterior = str(position['color_exterior'] or color_interior)
        result = engine_result_from_api(
            tree=tree, color=color_interior, color_exterior=color_exterior,
            params=params,
            nominal_width_mm=position['width_mm'],
            nominal_height_mm=position['height_mm'],
            coupler_articles=SystemParamsRepository().load_coupler_articles(
                position['system_id'], repo.org_id),
        )
        # D05: bars are priced under the position's resolved finish key
        # (plain code or "EXT/INT"); steel resolves color-free.
        stock_color = result.finish_key or (
            'WHITE' if color_interior=='WHITE' and color_exterior=='WHITE' else 'FOILED')
        for cut in result.profile_cuts:
            if cut.origin is PieceOrigin.EXTRA:
                # D06: a piece an extra mints is costed by the extra's own
                # declared unit_cost — the stock authority knows nothing of
                # finishing profiles and must never be asked.
                continue
            profile_stocks[cut.sku] = stock_repo.profile_stock(position['system_id'],repo.org_id,cut.sku,stock_color)
        for steel in result.reinforcements:
            steel_stocks[(steel.parent_profile_sku,steel.reinforcement_sku)] = stock_repo.reinforcement_stock(
                position['system_id'],repo.org_id,steel.parent_profile_sku,steel.reinforcement_sku)[0]
    except DatabaseError:
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE pricing_backend')
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE pricing_backend')
    tree = decoded(position['parametric_tree'])
    materials = []
    composition = []
    selection_delta = D('0')
    for cut in result.profile_cuts:
        if getattr(cut, 'origin', None) is PieceOrigin.EXTRA:
            continue
        stock = profile_stocks[cut.sku]
        cost = linear_cost(repo,stock.commercial_sku,cut.length_mm*cut.qty,stock.stock_length_mm)
        materials.append(cost)
        composition.append({'kind':'PROFILE','sku':stock.commercial_sku,
                            'module_id':_composition_module(cut.bay_id),
                            'quantity':str((cut.length_mm*cut.qty/D('1000')).quantize(D('0.001'))),
                            'unit':'M','cost':str(cost.quantize(D('0.0001')))})
    for steel in result.reinforcements:
        stock = steel_stocks[(steel.parent_profile_sku,steel.reinforcement_sku)]
        cost = linear_cost(repo,stock.commercial_sku,steel.length_mm*steel.qty,stock.stock_length_mm)
        materials.append(cost)
        composition.append({'kind':'REINFORCEMENT','sku':stock.commercial_sku,
                            'module_id':_composition_module(steel.bay_id),
                            'quantity':str((steel.length_mm*steel.qty/D('1000')).quantize(D('0.001'))),
                            'unit':'M','cost':str(cost.quantize(D('0.0001')))})
    for glass in result.glasses:
        # The selected commercial glass SKU is explicit in the persisted tree.
        sku = design_glass_sku(tree,glass.bay_id)
        # Rect panes keep exact w*h pricing; shaped pieces use the engine's
        # polygon area (bbox would overcharge a sloped or arched outline).
        glass_area = (
            glass.area_m2
            if getattr(glass, "shape", None)
            else exact_glass_area_m2(glass.width_mm, glass.height_mm)
        )
        # D02: a registered glass product bills its declared minimum cut area
        # and emits a line per applicable surcharge (tempering, polished
        # edges, drills, georgian-bar grids). Without a product row the
        # legacy flat-m² line stands — the cost list is the money authority
        # either way.
        product = (getattr(params, "glass_products", None) or {}).get(sku)
        if product is None:
            cost = repo.cost(sku,'M2') * glass_area
            materials.append(cost)
            composition.append({'kind':'GLASS','sku':sku,
                                'module_id':_composition_module(glass.bay_id),
                                'quantity':str(glass_area.quantize(D('0.0001'))),
                                'unit':'M2','cost':str(cost.quantize(D('0.0001')))})
        else:
            cost_per_m2 = repo.cost(sku,'M2')
            if product.surcharges:
                # Rate currency follows the org's declared currency — the
                # catalog row names it; never a silent CLP assumption.
                org_currency = one(
                    'SELECT currency FROM public.tenancy_organizations WHERE id=%s',
                    [repo.org_id],'organization_not_found')['currency']
            converted_rates = [
                GlassSurchargeRate(
                    kind=rate.kind, unit=rate.unit,
                    amount=repo.convert(
                        rate.amount, rate.currency or org_currency),
                    currency=None, label=rate.label)
                for rate in product.surcharges
            ]
            for line in glass_price_lines(
                sku=sku,
                cost_per_m2=cost_per_m2,
                exact_area_m2=glass_area,
                min_area_m2=product.min_area_m2,
                surcharges=converted_rates,
                selections=glass.surcharge_selections,
                composition=glass.composition,
                width_mm=glass.width_mm,
                height_mm=glass.height_mm,
                exposed_edges=glass.exposed_edges,
            ):
                materials.append(line.cost)
                composition.append({'kind':line.kind,'sku':line.sku,
                                    'module_id':_composition_module(glass.bay_id),
                                    'quantity':str(line.quantity.quantize(D('0.0001'))),
                                    'unit':line.unit,'cost':str(line.cost.quantize(D('0.0001'))),
                                    'label':line.label})
    for panel in result.panels:
        panel_area = exact_glass_area_m2(panel.width_mm,panel.height_mm)
        cost = repo.cost(panel.sku,'M2') * panel_area
        materials.append(cost)
        composition.append({'kind':'PANEL','sku':panel.sku,
                            'module_id':_composition_module(panel.bay_id),
                            'quantity':str(panel_area.quantize(D('0.0001'))),
                            'unit':'M2','cost':str(cost.quantize(D('0.0001')))})
    for kit in result.hardware_items:
        cost = repo.cost(kit.kit_sku,'KIT') * kit.qty
        materials.append(cost)
        composition.append({'kind':'HARDWARE','sku':kit.kit_sku,
                            'module_id':_composition_module(kit.bay_id),
                            'quantity':str(kit.qty),'unit':'KIT',
                            'cost':str(cost.quantize(D('0.0001')))})
        # D04 sell-side deltas: the catalog declares each selection's price
        # (handle model/colour, option) as a per-kit addend — it lands on the
        # unit price, never on materials cost. A selected source without a
        # declared delta refuses to quote rather than price at zero.
        for entry in kit.price_deltas:
            if entry.price_delta_clp is None:
                raise PricingError('hardware_option_price_missing')
            selection_delta += entry.price_delta_clp * kit.qty
    # Frameless supports/fittings are counted pieces: a declared SKU must
    # resolve a unit price or the quote fails — never silently priced at zero.
    for fitting in result.fittings:
        if getattr(fitting, 'origin', None) is PieceOrigin.EXTRA:
            continue
        cost = repo.cost(fitting.sku,'EA') * fitting.qty
        materials.append(cost)
        composition.append({'kind':'FITTING','sku':fitting.sku,
                            'module_id':_composition_module(getattr(fitting,'bay_id',None)),
                            'quantity':str(fitting.qty),'unit':'EA',
                            'cost':str(cost.quantize(D('0.0001')))})
    # D05: declared finish surcharges — the engine resolved each basis;
    # the pricing boundary converts the declared rate and adds the amount
    # to the unit sell price (never into materials cost).
    color_delta = D('0')
    if result.color_surcharges:
        org_currency = one(
            'SELECT currency FROM public.tenancy_organizations WHERE id=%s',
            [repo.org_id],'organization_not_found')['currency']
        for application in result.color_surcharges:
            rate = repo.convert(application.rate, application.currency or org_currency)
            if application.kind == 'PCT_OF_MATERIALS':
                amount = rate * sum(materials, D('0'))
            elif application.kind == 'FIXED_PER_POSITION':
                amount = rate
            else:
                amount = rate * (application.basis or D('0'))
            color_delta += amount
            composition.append({
                'kind':'COLOR_SURCHARGE',
                'sku':application.option_code,
                'quantity':str((application.basis or D('1')).quantize(D('0.0001'))),
                'unit':application.basis_unit,
                'cost':str(amount.quantize(D('0.0001'))),
                'label':application.label or application.option_name})
    # D06: each selected extra is its own sublínea — cantidad × precio
    # unitario = total at the article's declared price, added to the unit
    # sell like the D04 hardware deltas. Its material cost is the article's
    # declared unit_cost; a missing price refuses to quote rather than
    # silently charge zero.
    extra_sell = D('0')
    for line in getattr(result, 'extra_lines', None) or []:
        if line.total_price is None:
            raise PricingError('extra_price_missing')
        extra_sell += line.total_price
        materials.append(line.total_cost or D('0'))
        composition.append({'kind':'EXTRA','sku':line.sku,
                            'quantity':str(line.quantity),'unit':line.unit.value,
                            'cost':str((line.total_cost or D('0')).quantize(D('0.0001'))),
                            'label':line.name})
    area = exact_glass_area_m2(position['width_mm'],position['height_mm'])
    total = direct_cost(materials,area,rules['waste_factor_pct'],rules['labor_rate_per_m2'],
                        rules['installation_rate_per_m2'])
    formation = {'composition':composition,
                 'materials_cost':str(sum(materials,D('0')).quantize(D('0.0001'))),
                 'hardware_option_delta':str(selection_delta.quantize(D('0.0001'))),
                 'color_surcharge_delta':str(color_delta.quantize(D('0.0001'))),
                 'extra_sell_delta':str(extra_sell.quantize(D('0.0001'))),
                 'extra_lines':[line.model_dump(mode='json')
                                for line in (getattr(result, 'extra_lines', None) or [])],
                 'waste_pct':str(rules['waste_factor_pct']),
                 'labor_rate_per_m2':str(rules['labor_rate_per_m2']),
                 'installation_rate_per_m2':str(rules['installation_rate_per_m2']),
                 'area_m2':str(area.quantize(D('0.0001')))}
    return total, area, result, formation


def _project_service_lines(project_id, org_id, positions):
    """D06 project services — the selections the project declared resolve
    against the catalog and the engine measures quantities off the
    positions' real geometry. Read under the authenticated role so the
    org-scope RLS policies evaluate on the caller's memberships."""
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL ROLE authenticated')
    try:
        selected = rows(
            'SELECT a.code, a.name, a.kind::text, a.qty_rule::text,'
            ' a.unit_price, a.unit_price_currency, a.unit_cost, a.unit_cost_currency'
            ' FROM public.project_service_selections sel'
            ' JOIN public.service_articles a ON a.id = sel.service_article_id'
            ' WHERE sel.project_id=%s AND sel.org_id=%s ORDER BY a.code',
            [project_id, org_id])
    except DatabaseError:
        raise
    except BaseException:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE pricing_backend')
        raise
    else:
        if not tx_aborted():
            with connection.cursor() as cursor:
                cursor.execute('SET LOCAL ROLE pricing_backend')
    if not selected:
        return []
    articles = [
        ServiceArticle(
            code=str(item['code']),
            name=str(item['name']),
            kind=ServiceKind(str(item['kind'])),
            qty_rule=ServiceQtyRule(str(item['qty_rule'])),
            unit_price=(
                None if item['unit_price'] is None else D(str(item['unit_price']))
            ),
            unit_price_currency=(
                None
                if item['unit_price_currency'] is None
                else str(item['unit_price_currency'])
            ),
            unit_cost=(
                None if item['unit_cost'] is None else D(str(item['unit_cost']))
            ),
            unit_cost_currency=(
                None
                if item['unit_cost_currency'] is None
                else str(item['unit_cost_currency'])
            ),
        )
        for item in selected
    ]
    measures = [
        ServicePositionMeasure(
            width_mm=D(str(position['width_mm'])),
            height_mm=D(str(position['height_mm'])),
            quantity=int(position['quantity']),
        )
        for position in positions
    ]
    lines = evaluate_service_lines(articles, measures)
    for line in lines:
        if line.total_price is None:
            raise PricingError('service_price_missing')
    return lines


def preview(org_id, actor, request):
    project = one('SELECT * FROM public.projects WHERE id=%s AND org_id=%s FOR UPDATE',
                  [request['project_id'],org_id],'project_not_found')
    if project['status'] != 'DRAFT':
        raise PricingError('commercial_revision_required')
    if rows(
        "SELECT operation.id FROM public.pricing_operations operation "
        "JOIN public.projects project ON project.id=operation.project_id AND project.org_id=operation.org_id "
        "WHERE operation.org_id=%s AND operation.project_id=%s AND operation.state='APPLIED' "
        "AND COALESCE(operation.revision_code,'REV-A')=project.current_revision "
        "AND (project.pricing_reset_at IS NULL OR operation.approved_at>project.pricing_reset_at) LIMIT 1",
        [org_id, project['id']],
    ):
        raise PricingError('commercial_revision_required')
    positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s AND org_id=%s '
                     'ORDER BY position_index FOR UPDATE',[project['id'],org_id])
    if not positions:
        raise PricingError('project_has_no_positions')
    rules = one('SELECT * FROM public.pricing_rules WHERE org_id=%s',[org_id],'pricing_rules_not_found')
    repo = PricingRepository(org_id,request['effective_date'],request['currency'],request.get('fx_snapshot_id'))
    mode = PricingMode(request['pricing_mode'])
    if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT and actor.active_organization.role != 'OWNER':
        raise PricingError('pricing_permission_denied')
    organization = one('SELECT currency FROM public.tenancy_organizations WHERE id=%s',[org_id])
    repo.authorities.append({'organization_currency':organization['currency']})
    calculation_rules = {**rules,
        'labor_rate_per_m2':repo.convert(rules['labor_rate_per_m2'],organization['currency']),
        'installation_rate_per_m2':repo.convert(rules['installation_rate_per_m2'],organization['currency'])}
    discount = request['discount_pct']
    # El margen de la cotización: la regla del taller es el defecto y el
    # estimador puede moverlo — un cambio de margen se audita como request.
    margin = request.get('margin_pct')
    if margin is None:
        margin = rules['default_margin_pct']
    state = discount_state(actor.active_organization.role,discount,request['confirmed'],
                           D(str(rules.get('discount_approval_threshold_pct') or '0.10')))
    if mode == PricingMode.COMMERCIAL_LIST_WITH_DISCOUNTS:
        # Segment bands only bound the list-with-discounts catalogue: RETAIL
        # requires 0% and ARCHITECT 8–12%, so applying them to the manual
        # discount decision would make the estimator approval path
        # unreachable for any negotiated discount.
        validate_segment(request['segment'],discount,sum(p['quantity'] for p in positions))
    if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT and discount:
        raise PricingError('target_margin_already_defines_final_price')
    cost_lines, priced_lines, technical = [], [], []
    # P10 — una alternativa (`is_option`) se precifica por línea pero queda
    # fuera del total del trato: "no incluida en el precio". Su neto existe
    # en `lines` para que el aplicador selle su precio, pero el neto/IVA/
    # bruto del proyecto solo cuentan las posiciones incluidas.
    option_indexes = {
        int(p['position_index']) for p in positions if p.get('is_option')
    }
    unit_costs: dict[int, Decimal] = {}
    selection_extra = D('0')
    with localcontext() as context:
        context.prec = 80
        for position in positions:
            try:
                cost, area, result, formation = position_cost(repo,position,calculation_rules)
                index = position['position_index']
                unit_costs[index] = cost
                cost_lines.append((index,cost*position['quantity']))
                # D04 deltas are sell additions; under a project target margin
                # they ride as undiscounted additions like project extras.
                selection_extra += (D(formation['hardware_option_delta'])
                                    + D(formation['color_surcharge_delta'])
                                    + D(formation['extra_sell_delta'])) * position['quantity']
                technical.append({'position_id':position['id'],
                                  'position_index':index,
                                  'is_option':index in option_indexes,
                                  'unit_cost':str(cost.quantize(D('0.0001'))),
                                  'quantity':int(position['quantity']),
                                  'width_mm':str(position['width_mm']),
                                  'height_mm':str(position['height_mm']),
                                  'typology':position.get('typology'),
                                  'location_tag':position.get('location_tag'),
                                  'bom':result.model_dump(mode='json'),**formation})
                if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT:
                    continue
                extra = {}
                if mode != PricingMode.COST_PLUS_MARGIN:
                    config = repo.configuration(mode.value,request['context_code'],position['typology'])
                    if mode == PricingMode.PRICE_PER_M2_BY_TYPOLOGY:
                        if not config['base_glass_sku'] or not result.glasses:
                            raise PricingError('missing_glass_authority')
                        selected = {design_glass_sku(decoded(position['parametric_tree']),glass.bay_id)
                                    for glass in result.glasses}
                        if len(selected) != 1:
                            raise PricingError('ambiguous_selected_glass')
                        extra = {'rate':repo.convert(config['rate_per_m2'],config['currency']),
                                 'selected_glass':repo.cost(next(iter(selected)),'M2'),
                                 'base_glass':repo.cost(config['base_glass_sku'],'M2')}
                    elif mode == PricingMode.FIXED_PRICE_MATRIX_DIMENSIONAL:
                        extra = {'cells':repo.matrix(config)}
                    else:
                        extra = {'catalog_price':repo.convert(config['catalog_price'],config['currency'])}
                exact_price = unit_price(mode,cost=cost,margin=margin,area=area,
                                         width=position['width_mm'],height=position['height_mm'],
                                         foil=position['color_interior']!='WHITE' or position['color_exterior']!='WHITE',**extra)
                # D04 + D05 + D06: declared selections, finish surcharges
                # and extras sublines add to the unit price as sell deltas —
                # discounted with the line like any other sell.
                exact_price += (D(formation['hardware_option_delta'])
                                + D(formation['color_surcharge_delta'])
                                + D(formation['extra_sell_delta']))
                priced_lines.append(CommercialLine(index,position['quantity'],cost,exact_price,discount))
            except PricingError as error:
                # The estimator fixing this has to know WHICH vano fails —
                # name the position, then the human reason for the code.
                detail = PRICING_ERROR_DETAILS.get(
                    error.code,'la operación comercial requiere revisar sus permisos, datos o configuración')
                raise contract_error(422,error.code,f'{_position_label(position)}: {detail}.') from error
        service_lines = _project_service_lines(project['id'], org_id, positions)
        extra_amounts = [D(str(item['amount'])) for item in request.get('extras') or []]
        # Catalogued services ride the same undiscounted, taxed additions
        # channel as a manual project charge — their totals are engine-
        # measured, never free text.
        extra_amounts.extend(
            line.total_price for line in service_lines if line.total_price is not None
        )
        if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT and selection_extra:
            # Other modes already carry the delta inside each unit price.
            extra_amounts.append(selection_extra)
        # El trato se cierra solo sobre las posiciones incluidas; si toda la
        # cotización son alternativas no hay trato que totalizar.
        included_priced = [
            line for line in priced_lines if line.position_index not in option_indexes
        ]
        included_costs = [
            pair for pair in cost_lines if pair[0] not in option_indexes
        ]
        if not included_costs or (
            mode != PricingMode.TARGET_GROSS_MARGIN_PROJECT and not included_priced
        ):
            raise contract_error(
                422,
                'options_need_base_position',
                'La cotización necesita al menos una posición incluida en el total — '
                'las alternativas no suman al precio.')
        if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT:
            output = target_project(included_costs,request['target_margin'],request['currency'],rules['tax_rate_pct'],extra_amounts)
            # En objetivo, la alternativa se ofrece al mismo margen del
            # trato — su precio es convención declarada, no reasignación.
            option_lines_built = [
                CommercialLine(
                    index,
                    int(next(p['quantity'] for p in positions if p['position_index'] == index)),
                    unit_costs[index],
                    unit_price(
                        PricingMode.COST_PLUS_MARGIN,
                        cost=unit_costs[index],
                        margin=D(str(request['target_margin']))),
                    discount)
                for index in sorted(option_indexes)
            ]
        else:
            output = finish_lines(included_priced,request['currency'],rules['tax_rate_pct'],extra_amounts)
            option_lines_built = [
                line for line in priced_lines if line.position_index in option_indexes
            ]
        option_output = (
            finish_lines(option_lines_built,request['currency'],rules['tax_rate_pct'],[])
            if option_lines_built else None)
        merged_lines = tuple(sorted(
            tuple(output.lines) + (tuple(option_output.lines) if option_output else ()))
        )
        deal_cost = sum((D(str(cost)) for _, cost in included_costs), D('0'))
        option_net = (
            sum((D(str(net)) for _, net in option_output.lines), D('0'))
            if option_output else None)
    # P07 — la banda de margen es puerta de decisión: el estimador que
    # cotiza fuera de banda pide aprobación; el dueño confirma explícito.
    # El margen realizado es (neto−costo)/neto — sobre la venta, jamás markup.
    # El margen del trato se mide sobre el trato: costo y neto de las
    # posiciones incluidas — una alternativa ni lo engorda ni lo diluye.
    project_cost = deal_cost
    margin_realized = (
        (output.project_net - project_cost) / output.project_net
        if output.project_net > 0 else None)
    band = {
        'min': str(rules['margin_min_pct']),
        'objective': str(request['target_margin']
                         if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT
                         else margin),
        'max': str(rules['margin_max_pct']),
        'state': band_state(
            margin_realized, rules['margin_min_pct'], rules['margin_max_pct']),
    }
    # Fuera de banda: la vista previa del estimador nace directamente como
    # solicitud (PENDING). El dueño siempre ve PREVIEW — su confirmación se
    # exige al aplicar, en apply_operation (owner_confirmation_required);
    # bloquearle la vista le impediría siquiera mirar la banda.
    if band['state'] != 'IN_BAND' and actor.active_organization.role != 'OWNER':
        state = 'PENDING'
    # Per-line selling detail so the decision screen can show unit price,
    # quantity and discount next to the line total — a line net is a per-
    # position TOTAL (unit × qty × (1−discount)), never a unit price. The
    # authority stays in the engine: exact_unit_price is the pre-discount
    # computed unit; the target-margin mode has no per-line discount, so
    # its unit readout is the allocated line net over quantity.
    quantities = {position['position_index']: int(position['quantity']) for position in positions}
    # `result_view` es el resultado que se guarda: las líneas cubren todas
    # las posiciones (incluidas + alternativas, para que apply selle cada
    # price_net) y los totales solo el trato incluido.
    result_view = {**asdict(output),
                   'lines': merged_lines,
                   'option_indexes': sorted(option_indexes),
                   'deal_cost_net': str(deal_cost),
                   'option_net': str(option_net) if option_net is not None else None}
    if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT:
        line_detail = [
            {'position_index': index, 'quantity': quantities[index],
             'unit_price': str((D(str(net)) / quantities[index]).quantize(D('0.0001'))),
             'discount_pct': '0'}
            for index, net in merged_lines]
    else:
        line_detail = [
            {'position_index': line.position_index, 'quantity': quantities[line.position_index],
             'unit_price': str(line.exact_unit_price.quantize(D('0.0001'))),
             'discount_pct': str(line.discount)}
            for line in priced_lines]
    audit_reason(request['reason'])
    record = one(
        'INSERT INTO public.pricing_operations(org_id,project_id,requested_by,requested_by_email,'
        'request,input_snapshot,result,source_revision,revision_code,state,reason) '
        'VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s) RETURNING id,created_at',
        [org_id,project['id'],request['_actor_id'],request.get('_actor_email'),
         json_text({key:value for key,value in request.items() if not key.startswith('_')}),
         json_text({'rules':rules,'authorities':repo.authorities,'positions':technical,'cost_lines':cost_lines}),
         json_text({**result_view,'line_detail':line_detail,
                    'margin_realized':str(margin_realized) if margin_realized is not None else None,
                    'band':band,
                    'service_lines':[line.model_dump(mode='json')
                                     for line in service_lines]}),
         source_revision(project,positions),project['current_revision'],
         'PENDING' if state=='PENDING' else 'PREVIEW',request['reason']])
    costs = [(index, D(str(cost))) for index, cost in cost_lines]
    breakdown = [{
        'position_id':str(p['position_id']),
        'position_index':p.get('position_index'),
        'unit_cost':str(p.get('unit_cost') or ''),
        'area_m2':str(p.get('area_m2') or ''),
        'materials_cost':str(p.get('materials_cost') or ''),
        'waste_pct':str(p.get('waste_pct') or ''),
        'labor_rate_per_m2':str(p.get('labor_rate_per_m2') or ''),
        'installation_rate_per_m2':str(p.get('installation_rate_per_m2') or ''),
        'hardware_option_delta':str(p.get('hardware_option_delta') or '0'),
        'color_surcharge_delta':str(p.get('color_surcharge_delta') or '0'),
        'extra_sell_delta':str(p.get('extra_sell_delta') or '0'),
        'quantity':p.get('quantity'),
        'width_mm':str(p.get('width_mm') or ''),
        'height_mm':str(p.get('height_mm') or ''),
        'typology':p.get('typology'),
        'location_tag':p.get('location_tag'),
        'composition':p.get('composition') or [],
    } for p in technical]
    stored = {'request':{key:value for key,value in request.items() if not key.startswith('_')},
              'input_snapshot':{'rules':rules,'authorities':repo.authorities,'positions':technical,'cost_lines':cost_lines},
              'result':{**result_view,'line_detail':line_detail,
                        'margin_realized':str(margin_realized) if margin_realized is not None else None,
                        'band':band,
                        'service_lines':[line.model_dump(mode='json') for line in service_lines]}}
    return {'id':str(record['id']),'state':'PENDING' if state=='PENDING' else 'PREVIEW',
            'project_id':str(project['id']),
            'project_code':project.get('code') or '',
            'project_name':project.get('name') or '',
            'client_name':project.get('client_name') or '',
            'revision_code':project['current_revision'],
            'discount_pct':str(discount),
            'pricing_mode':request.get('pricing_mode') or '',
            'segment':request.get('segment') or '',
            'currency':request['currency'],**result_view,
            'line_detail':line_detail,
            'margin_realized':str(margin_realized) if margin_realized is not None else None,
            'band':band,
            'cascade':_cascade_payload(stored['input_snapshot'],stored['result'],stored['request']),
            'delta':_delta_payload(org_id,project['id'],None,stored['input_snapshot'],
                                   stored['result'],stored['request']),
            'extras':[{'label':item['label'],'kind':item['kind'],
                       'amount':str(item['amount'])}
                      for item in request.get('extras') or []],
            'service_lines':[line.model_dump(mode='json') for line in service_lines],
            'cost_lines':[{'position_index':index,'line_cost':str(cost)} for index,cost in costs],
            'total_cost':str(deal_cost),
            'positions_breakdown':breakdown,
            'authorities':repo.authorities,
            'rules':{key:str(rules[key]) for key in
                     ('default_margin_pct','tax_rate_pct','waste_factor_pct','labor_rate_per_m2',
                      'installation_rate_per_m2') if key in rules},
            'reason':request['reason'],'requested_by':str(request['_actor_id']),
            'requested_by_email':request.get('_actor_email'),
            'approved_by':None,'approved_at':None,
            'created_at':record['created_at'].isoformat()}


def _module_net_split(unit_net, formation, design):
    """P06 — precio por módulo: reparte el neto unitario del conjunto en
    proporción al costo de material que el motor atribuyó a cada módulo
    (composition lines carry module_id). El total cuadra al peso — el
    último módulo cierra la diferencia de redondeo — y las líneas sin dueño
    (acopladores, recargos del conjunto) se reparten en la misma
    proporción: nunca desaparecen del precio ni caen en un módulo ajeno.
    Devuelve None cuando el diseño no es un conjunto product-v2 o el modo
    de precio no puede declarar neto honesto."""
    if unit_net is None or not formation:
        return None
    modules = (
        (design.get('parametric_tree') or {}).get('assembly', {}).get('modules', [])
        if isinstance(design.get('parametric_tree'), dict) else []
    )
    order = [m.get('id') for m in modules if isinstance(m, dict) and m.get('id')]
    if not order:
        return None
    shares = {mid: D('0') for mid in order}
    for line in formation.get('composition', []):
        mid = line.get('module_id')
        if mid in shares:
            shares[mid] += D(line['cost'])
    total = sum(shares.values())
    if total <= 0:
        return None
    net = D(str(unit_net))
    split = []
    running = D('0')
    for index, mid in enumerate(order):
        part = (
            (net * shares[mid] / total).quantize(D('0.0001'))
            if index < len(order) - 1
            else net - running
        )
        running += part
        split.append({'module_id': mid, 'unit_net': str(part)})
    return split


def _design_net_price(cost, area, formation, rules, *, width, height, foil):
    """Net unit sell price for a priced design: the declared margin applied to
    engine cost plus the declared sell deltas (hardware selections, finish
    surcharges, extras) — the same composition `preview` applies per line.
    Only COST_PLUS_MARGIN can be computed honestly for a single design: the
    catalogue modes (m²-by-typology, dimensional matrix, price list) need
    project context and authorities this preview does not have — for those
    the net fields stay None and the UI shows an honest dash."""
    if rules.get('pricing_mode') != PricingMode.COST_PLUS_MARGIN.value:
        return None
    if formation is None:
        return None
    price = unit_price(PricingMode.COST_PLUS_MARGIN,cost=cost,
        margin=rules['default_margin_pct'],area=area,width=width,height=height,foil=foil)
    return (price + (D(formation['hardware_option_delta'])
                     + D(formation['color_surcharge_delta'])
                     + D(formation['extra_sell_delta']))).quantize(D('0.0001'))


def _notify_pricing_decision(org_id, actor_id, operation, outcome):
    """P07 — aviso durable al solicitante cuando su operación se decide.

    Emitir desde la transacción que sella el estado: el job handler re-lee
    la operación comprometida y materializa mail_messages (proveedor
    sandbox por defecto — ver docs/ACTIVACION.md)."""
    from automations.service import emit

    emit(
        'mail.pricing_decision',
        org_id=org_id,
        actor_id=actor_id,
        idempotency_key=f'mail:pricing-decision:{operation["id"]}:{outcome}',
        operation_id=str(operation['id']),
        outcome=outcome,
    )


def _operation_econ(snapshot, result, request):
    """Per-position economics from a stored operation shape.

    Returns {match_key: {index, qty, uc, exact, d, sell, groups, dims}} or
    None when the snapshot predates the fields the decomposition needs —
    honesty over a guessed split. Everything read is the stored authority;
    nothing is recomputed from the catalog."""
    detail = {entry['position_index']: entry for entry in result.get('line_detail') or []}
    try:
        lines = {int(index): D(str(net)) for index, net in result['lines']}
        costs = {int(index): D(str(cost)) for index, cost in snapshot.get('cost_lines') or []}
        discount = D(str(request.get('discount_pct') or '0'))
    except (KeyError, TypeError, ArithmeticError):
        return None
    # P10 — las alternativas no participan del trato: quedan fuera de la
    # cascada y del delta (sus líneas sí viajan en result['lines']).
    options = {int(index) for index in result.get('option_indexes') or []}
    econ = {}
    for entry in snapshot.get('positions') or []:
        index = int(entry['position_index'])
        if index in options:
            continue
        if index not in lines or 'unit_cost' not in entry:
            continue
        unit_cost = D(str(entry['unit_cost']))
        quantity = (detail.get(index) or {}).get('quantity') or entry.get('quantity')
        if quantity is None:
            if unit_cost == 0 or index not in costs:
                return None
            ratio = costs[index] / unit_cost
            if ratio != ratio.to_integral_value() or ratio < 1:
                return None
            quantity = int(ratio)
        quantity = int(quantity)
        applied_discount = D(str((detail.get(index) or {}).get('discount_pct') or discount))
        exact = (detail.get(index) or {}).get('unit_price')
        if exact is None:
            factor = (D('1') - applied_discount) * quantity
            if factor <= 0:
                return None
            exact = lines[index] / factor
        sell = (
            D(str(entry.get('hardware_option_delta') or '0'))
            + D(str(entry.get('color_surcharge_delta') or '0'))
            + D(str(entry.get('extra_sell_delta') or '0'))
        )
        groups: dict[str, Decimal] = {}
        for component in entry.get('composition') or []:
            group = component_group(str(component.get('kind') or ''))
            if group is not None:
                groups[group] = groups.get(group, D('0')) + D(str(component['cost']))
        dims = None
        if entry.get('width_mm') is not None and entry.get('height_mm') is not None:
            dims = (str(entry['width_mm']), str(entry['height_mm']))
        econ[str(entry.get('position_id') or index)] = {
            'index': index,
            'qty': quantity,
            'uc': unit_cost,
            'exact': D(str(exact)),
            'd': applied_discount,
            'sell': sell,
            'groups': groups,
            'dims': dims,
        }
    return econ


def _cascade_payload(snapshot, result, request):
    """The stored operation → waterfall rows, per project and per position.

    Returns None when the operation predates the fields the cascade needs —
    the UI says 'sin cascada' instead of drawing an approximate one."""
    econ = _operation_econ(snapshot, result, request or {})
    if econ is None:
        return None
    positions = []
    by_index = {entry['index']: entry for entry in econ.values()}
    position_index_of = {
        int(entry['position_index']): entry for entry in snapshot.get('positions') or []
    }
    target_mode = str((request or {}).get('pricing_mode') or '') == 'TARGET_GROSS_MARGIN_PROJECT'
    for index, entry in by_index.items():
        raw = position_index_of.get(index) or {}
        sell = entry['sell']
        # En TARGET el delta de venta viaja como cargo de proyecto: la
        # posición no lo lleva en su precio unitario.
        if target_mode:
            sell = D('0')
        try:
            positions.append(
                CascadePosition(
                    position_index=index,
                    quantity=entry['qty'],
                    unit_cost=entry['uc'],
                    materials_cost=D(str(raw.get('materials_cost') or '0')),
                    waste_pct=D(str(raw.get('waste_pct') or '0')),
                    labour_per_m2=(
                        D(str(raw.get('labor_rate_per_m2') or '0'))
                        + D(str(raw.get('installation_rate_per_m2') or '0'))
                    ),
                    area_m2=D(str(raw.get('area_m2') or '0')),
                    components=tuple(
                        CascadeComponent(
                            kind=str(component.get('kind') or ''),
                            cost=D(str(component['cost'])),
                        )
                        for component in raw.get('composition') or []
                    ),
                    sell_delta=sell,
                    exact_unit_price=entry['exact'],
                    discount=entry['d'],
                    line_net=D(str(dict(result['lines'])[index])),
                )
            )
        except (KeyError, TypeError, ArithmeticError):
            return None
    # La cascada cuadra con las líneas del trato — las alternativas quedan
    # fuera de posiciones y de líneas comparadas.
    options = {int(index) for index in result.get('option_indexes') or []}
    deal_lines = [
        pair for pair in (result.get('lines') or [])
        if int(pair[0]) not in options]
    if len(positions) != len(deal_lines):
        # A position without economics would silently drop a waterfall row.
        return None
    try:
        cascade = price_cascade(
            positions,
            extras_net=D(str(result.get('extras_net') or '0')),
            project_net=D(str(result['project_net'])),
            project_tax=D(str(result['project_tax'])),
            project_gross=D(str(result['project_gross'])),
            total_cost=D(str(result.get('deal_cost_net')
                             or sum((D(str(c)) for _, c in snapshot.get('cost_lines') or []), D('0')))),
        )
    except (PricingError, KeyError, TypeError, ArithmeticError):
        return None
    return {
        'rows': [{'key': row.key, 'amount': str(row.amount), 'kind': row.kind}
                 for row in cascade.rows],
        'positions': [
            {
                'position_index': item['position_index'],
                'groups': {key: str(value) for key, value in item['groups'].items()},
                'materials': str(item['materials']),
                'waste': str(item['waste']),
                'labour': str(item['labour']),
                'rounding': str(item['rounding']),
                'cost': str(item['cost']),
                'margin': str(item['margin']),
                'sell': str(item['sell']),
                'list_price': str(item['list_price']),
                'discount': str(item['discount']),
                'net': str(item['net']),
            }
            for item in cascade.positions
        ],
        'margin_realized': (
            str(cascade.margin_realized) if cascade.margin_realized is not None else None
        ),
    }


def _delta_stages(econ_a, econ_b, request_a, request_b, rules_b, extras_a, extras_b):
    """Canonical scenarios baseline→proposed, one per driver.

    Attribution rules (documented, fixed by golden tests):
    - 'quantity' takes position set changes and quantity edits; a position
      that appears carries its full proposed economics.
    - 'dimensions' absorbs the whole residual of a vano whose measures
      changed — its composition deltas are indistinguishable from geometry.
    - glass/hardware/cost_list take the composition-bucket cost delta; in
      COST_PLUS_MARGIN its price effect scales by 1/(1−margen), in catalog
      modes the list price does not move with cost.
    - 'fx' takes the entire residual when currency or FX snapshot changed.
    - 'selections' takes the declared sell deltas (herraje, color, extras);
      'commercial' takes the residual unit-price delta (margen, modo,
      segmento); 'discount' and 'services' close the chain.
    """
    mode_b = str(request_b.get('pricing_mode') or '')
    margin_b = request_b.get('margin_pct') or (rules_b or {}).get('default_margin_pct')
    price_factor = (
        D('1') / (D('1') - D(str(margin_b)))
        if mode_b == 'COST_PLUS_MARGIN' and margin_b is not None
        else D('0')
    )
    common = [key for key in econ_a if key in econ_b]
    removed = [key for key in econ_a if key not in econ_b]
    added = [key for key in econ_b if key not in econ_a]
    states = {key: dict(econ_a[key]) for key in econ_a}

    def snapshot_lines():
        return tuple(
            DeltaLine(
                position_index=state['index'],
                quantity=state['qty'],
                unit_cost=state['uc'],
                exact_unit_price=state['exact'],
                discount=state['d'],
            )
            for _, state in sorted(states.items(), key=lambda item: item[1]['index'])
        )

    def dims_changed(key):
        before, after = econ_a[key]['dims'], econ_b[key]['dims']
        return bool(before and after and before != after)

    stages = [DeltaStage('baseline', snapshot_lines(), extras=extras_a)]
    for key in removed:
        states.pop(key)
    for key in added:
        states[key] = dict(econ_b[key])
    for key in common:
        states[key]['qty'] = econ_b[key]['qty']
    stages.append(DeltaStage('quantity', snapshot_lines(), extras=extras_a))
    for key in common:
        if dims_changed(key):
            states[key]['uc'] = econ_b[key]['uc']
            states[key]['exact'] = econ_b[key]['exact']
    stages.append(DeltaStage('dimensions', snapshot_lines(), extras=extras_a))
    for driver, buckets in (
        ('glass', ('glass', 'glass_surcharges')),
        ('hardware', ('hardware', 'fittings')),
        ('cost_list', ('profiles', 'reinforcement', 'panels', 'extras_material')),
    ):
        for key in common:
            if dims_changed(key):
                continue
            delta_cost = sum(
                (econ_b[key]['groups'].get(group, D('0'))
                 - econ_a[key]['groups'].get(group, D('0'))
                 for group in buckets),
                D('0'),
            )
            if delta_cost:
                states[key]['uc'] += delta_cost
                states[key]['exact'] += delta_cost * price_factor
        stages.append(DeltaStage(driver, snapshot_lines(), extras=extras_a))
    fx_changed = str(request_a.get('fx_snapshot_id') or '') != str(
        request_b.get('fx_snapshot_id') or '')
    if fx_changed:
        for key in states:
            states[key]['exact'] = econ_b[key]['exact']
    stages.append(DeltaStage('fx', snapshot_lines(), extras=extras_a))
    if not fx_changed:
        for key in common:
            states[key]['exact'] += econ_b[key]['sell'] - econ_a[key]['sell']
    stages.append(DeltaStage('selections', snapshot_lines(), extras=extras_a))
    if not fx_changed:
        for key in common:
            states[key]['exact'] = econ_b[key]['exact']
    stages.append(DeltaStage('commercial', snapshot_lines(), extras=extras_a))
    for key in states:
        states[key]['d'] = econ_b[key]['d']
    stages.append(DeltaStage('discount', snapshot_lines(), extras=extras_a))
    stages.append(DeltaStage('services', snapshot_lines(), extras=extras_b))
    return stages


def _delta_payload(org_id, project_id, operation, snapshot, result, request):
    """'¿Por qué cambió?' — decomposition of the net Δ against the last
    APPLIED operation of the project (the price the client last saw).

    None when there is no baseline (first quote of the project), when the
    currencies differ (nets are not comparable), or when the baseline
    predates the snapshot fields the attribution needs."""
    condition = ' AND operation.created_at<%s' if operation is not None else ''
    parameters = [org_id, project_id] + ([operation['created_at']] if operation is not None else [])
    baseline_row = rows(
        'SELECT * FROM public.pricing_operations operation '
        "WHERE operation.org_id=%s AND operation.project_id=%s AND operation.state='APPLIED'"
        + condition + ' ORDER BY operation.created_at DESC,operation.id LIMIT 1',
        parameters)
    if not baseline_row:
        return None
    baseline = baseline_row[0]
    baseline_request = decoded(baseline['request'])
    if str(baseline_request.get('currency')) != str(request.get('currency')):
        return None
    # Tipos persistentes: el request vivo trae UUID/fechas; lo almacenado,
    # strings. Normaliza ambos antes de comparar impulsores.
    request = {
        key: (str(value) if isinstance(value, (UUID,)) else value)
        for key, value in request.items()
    }
    econ_a = _operation_econ(decoded(baseline['input_snapshot']), decoded(baseline['result']), baseline_request)
    econ_b = _operation_econ(snapshot, result, request)
    if econ_a is None or econ_b is None:
        return None
    baseline_snapshot = decoded(baseline['input_snapshot'])
    baseline_result = decoded(baseline['result'])
    rules_b = (snapshot.get('rules') or {})
    extras_a = (D(str(baseline_result.get('extras_net') or '0')),)
    extras_b = (D(str(result.get('extras_net') or '0')),)
    stages = _delta_stages(
        econ_a, econ_b, baseline_request, request, rules_b, extras_a, extras_b)
    tax_rate = D(str((baseline_snapshot.get('rules') or {}).get('tax_rate_pct') or '0'))
    contributions = delta_contributions(stages, str(request['currency']), tax_rate)
    # Zero-mover drivers carry no row — the chain still telescopes.
    return {
        'baseline_operation_id': str(baseline['id']),
        'baseline_revision': baseline.get('revision_code') or 'REV-A',
        'baseline_net': str(baseline_result['project_net']),
        'proposed_net': str(result['project_net']),
        'net_delta': str(D(str(result['project_net'])) - D(str(baseline_result['project_net']))),
        'drivers': [
            {
                'driver': item.driver,
                'net_delta': str(item.net_delta),
                'cost_delta': str(item.cost_delta),
                'net_after': str(item.net_after),
            }
            for item in contributions
            if item.net_delta != 0 or item.cost_delta != 0
        ],
    }


def design_batch_preview(org_id, _actor, request):
    """§08-WC — honest money diff for a proposed batch design edit. Each
    item's proposed design passes the same engine gate a save would
    (calculate_design), then position_cost prices the stored position and
    the proposed product under the same rules — the count + Δ the human
    confirms is the real unit cost, never a model estimate. A null
    `position_id` prices the proposed design after-only — the position
    editor's live-price chip rides this path for an unsaved draft."""
    from authentication.errors import ContractAPIException
    from projects.service import calculate_design

    project = one('SELECT * FROM public.projects WHERE id=%s AND org_id=%s',
                  [request['project_id'],org_id],'project_not_found')
    if project['status'] != 'DRAFT':
        raise PricingError('commercial_revision_required')
    # Mirror editable(): a version row on the current revision means it is
    # sealed — positions can no longer change, so a batch preview is moot.
    # project_versions is role-denied to `authenticated` (rbac_repair), so the
    # check must run as documentary_backend like every other reader does.
    from documents.repository import documentary_backend

    with documentary_backend():
        sealed = rows(
            "SELECT id FROM public.project_versions WHERE org_id=%s AND project_id=%s "
            "AND revision_code=%s LIMIT 1",
            [org_id, project['id'], project['current_revision']],
        )
    if sealed:
        raise PricingError('commercial_revision_required')
    rules = one('SELECT * FROM public.pricing_rules WHERE org_id=%s',[org_id],'pricing_rules_not_found')
    organization = one('SELECT currency FROM public.tenancy_organizations WHERE id=%s',[org_id])
    repo = PricingRepository(org_id,request['effective_date'],organization['currency'],None)
    repo.authorities.append({'organization_currency':organization['currency']})
    calculation_rules = {**rules,
        'labor_rate_per_m2':repo.convert(rules['labor_rate_per_m2'],organization['currency']),
        'installation_rate_per_m2':repo.convert(rules['installation_rate_per_m2'],organization['currency'])}
    items = []
    with localcontext() as context:
        context.prec = 80
        for entry in request['items']:
            position_id = entry.get('position_id')
            design = entry['design']
            position = None
            if position_id is not None:
                found = rows(
                    'SELECT * FROM public.project_positions WHERE id=%s AND org_id=%s AND project_id=%s',
                    [position_id,org_id,project['id']],
                )
                if not found:
                    items.append({'position_id':position_id,'ok':False,
                                  'error_code':'position_not_found','error':'La posición no existe en este proyecto.'})
                    continue
                position = found[0]
            try:
                # Engine validity under the member-facing role, exactly like
                # a save; cost reads swap roles internally as position_cost
                # already does.
                with connection.cursor() as cursor:
                    cursor.execute('SET LOCAL ROLE authenticated')
                try:
                    calculate_design(org_id,{**design,'system_id':str(design['system_id'])})
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute('SET LOCAL ROLE pricing_backend')
                before = before_net = None
                if position is not None:
                    before, before_area, _, before_formation = position_cost(
                        repo,position,calculation_rules)
                    before_net = _design_net_price(
                        before,before_area,before_formation,rules,
                        width=position['width_mm'],height=position['height_mm'],
                        foil=position['color_interior']!='WHITE'
                             or position['color_exterior']!='WHITE')
                pseudo = {
                    'system_id':design['system_id'],
                    'parametric_tree':design['parametric_tree'],
                    'width_mm':D(str(design['nominal_width_mm'])),
                    'height_mm':D(str(design['nominal_height_mm'])),
                    'color_interior':design['color'],
                    'color_exterior':design.get('color_exterior') or design['color'],
                }
                after, after_area, _, after_formation = position_cost(repo,pseudo,calculation_rules)
                after_net = _design_net_price(
                    after,after_area,after_formation,rules,
                    width=pseudo['width_mm'],height=pseudo['height_mm'],
                    foil=design['color']!='WHITE'
                         or pseudo['color_exterior']!='WHITE')
            except ContractAPIException as error:
                items.append({'position_id':position_id,'ok':False,
                              'error_code':error.contract_code,'error':error.public_detail})
                continue
            except PricingError as error:
                items.append({'position_id':position_id,'ok':False,
                              'error_code':error.code,
                              'error':pricing_public_detail(error.code)})
                continue
            # IA2 — a proposed quantity change is part of the design the
            # client prices (batch ops may carry set_quantity); the stored
            # quantity stays the fallback. An unsaved design has no stored
            # position either, so quantity defaults to 1.
            quantity = (entry.get('quantity') or design.get('quantity')
                        or (position['quantity'] if position else 1))
            items.append({
                'position_id':position_id,
                'index':position['position_index'] if position is not None else None,
                'ok':True,
                'quantity':quantity,
                'unit_cost_before':str(before) if before is not None else None,
                'unit_cost_after':str(after),
                'line_cost_before':str(before*quantity) if before is not None else None,
                'line_cost_after':str(after*quantity),
                'unit_net_before':str(before_net) if before_net is not None else None,
                'unit_net_after':str(after_net) if after_net is not None else None,
                'line_net_before':str(before_net*quantity) if before_net is not None else None,
                'line_net_after':str(after_net*quantity) if after_net is not None else None,
                'module_net_after':_module_net_split(after_net, after_formation, design),
            })
    return {'currency':organization['currency'],'items':items}


def operation_public(operation):
    # The decision surface reads cost next to price: both were stored at
    # preview time from the same authority, so the margin the estimator sees
    # is the margin the approver audited.
    snapshot = decoded(operation['input_snapshot'])
    costs = snapshot.get('cost_lines') or []
    snapshot_rules = snapshot.get('rules') or {}
    breakdown = [{
        'position_id':str(p['position_id']),
        'position_index':p.get('position_index'),
        'unit_cost':str(p.get('unit_cost') or ''),
        'area_m2':str(p.get('area_m2') or ''),
        'materials_cost':str(p.get('materials_cost') or ''),
        'waste_pct':str(p.get('waste_pct') or ''),
        'labor_rate_per_m2':str(p.get('labor_rate_per_m2') or ''),
        'installation_rate_per_m2':str(p.get('installation_rate_per_m2') or ''),
        'hardware_option_delta':str(p.get('hardware_option_delta') or '0'),
        'color_surcharge_delta':str(p.get('color_surcharge_delta') or '0'),
        'extra_sell_delta':str(p.get('extra_sell_delta') or '0'),
        'quantity':p.get('quantity'),
        'width_mm':str(p.get('width_mm') or ''),
        'height_mm':str(p.get('height_mm') or ''),
        'typology':p.get('typology'),
        'location_tag':p.get('location_tag'),
        'composition':p.get('composition') or [],
    } for p in snapshot.get('positions') or []]
    result_dto = {'total_cost':str(sum((D(str(cost)) for _, cost in costs), D('0')))}
    enrichment = _operation_enrichment(str(operation['org_id']), operation, result_dto)
    return {'id':str(operation['id']),'state':operation['state'],
            'project_id':str(operation['project_id']),
            'project_code':operation.get('project_code') or '',
            'project_name':operation.get('project_name') or '',
            'client_name':operation.get('client_name') or '',
            'revision_code':operation.get('revision_code') or 'REV-A',
            'discount_pct':str(decoded(operation['request'])['discount_pct']),
            'pricing_mode':decoded(operation['request']).get('pricing_mode') or '',
            'segment':decoded(operation['request']).get('segment') or '',
            'currency':decoded(operation['request'])['currency'],**decoded(operation['result']),
            'extras':[{'label':item['label'],'kind':item.get('kind') or 'OTHER',
                       'amount':str(item['amount'])}
                      for item in decoded(operation['request']).get('extras') or []],
            'cost_lines':[{'position_index':index,'line_cost':str(cost)} for index,cost in costs],
            'total_cost':str(sum((D(str(cost)) for _, cost in costs), D('0'))),
            'positions_breakdown':breakdown,
            'authorities':snapshot.get('authorities') or [],
            'rules':{key:str(snapshot_rules[key]) for key in
                     ('default_margin_pct','tax_rate_pct','waste_factor_pct','labor_rate_per_m2',
                      'installation_rate_per_m2') if key in snapshot_rules},
            'reason':str(operation['reason']),
            'requested_by':str(operation['requested_by']),
            'requested_by_email':operation.get('requested_by_email'),
            'approved_by':str(operation['approved_by']) if operation['approved_by'] else None,
            'approved_at':operation['approved_at'].isoformat() if operation['approved_at'] else None,
            'created_at':operation['created_at'].isoformat(),
            **enrichment}


def _operation_enrichment(org_id, operation, result):
    """P07 read-model: margin band, cascade and delta for a stored operation.

    Ops priced after P07 carry margin_realized/band/cascade/delta inside
    their stored result; older rows get them computed on read — the math is
    deterministic over the same snapshot, so history never diverges."""
    stored = decoded(operation['result'])
    enrichment = {}
    margin_realized = stored.get('margin_realized')
    if margin_realized is None:
        try:
            net, cost = D(str(stored['project_net'])), D(str(result.get('total_cost') or '0'))
            margin_realized = (
                str((net - cost) / net) if net > 0 else None)
        except (KeyError, ArithmeticError):
            margin_realized = None
    enrichment['margin_realized'] = margin_realized
    enrichment['band'] = stored.get('band')
    if enrichment['band'] is None:
        rules_row = rows('SELECT margin_min_pct,default_margin_pct,margin_max_pct '
                         'FROM public.pricing_rules WHERE org_id=%s', [org_id])
        if rules_row:
            rules_row = rules_row[0]
            enrichment['band'] = {
                'min': str(rules_row['margin_min_pct']),
                'objective': str(rules_row['default_margin_pct']),
                'max': str(rules_row['margin_max_pct']),
                'state': band_state(
                    None if margin_realized is None else D(str(margin_realized)),
                    D(str(rules_row['margin_min_pct'])),
                    D(str(rules_row['margin_max_pct']))),
            }
    enrichment['cascade'] = stored.get('cascade') or _cascade_payload(
        decoded(operation['input_snapshot']), stored, decoded(operation['request']))
    enrichment['delta'] = stored.get('delta') or _delta_payload(
        org_id, operation['project_id'], operation,
        decoded(operation['input_snapshot']), stored, decoded(operation['request']))
    return enrichment


def apply_operation(org_id, actor_id, role, operation_id, reason, confirmed, reject=False):
    operation = one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s FOR UPDATE',
                    [operation_id,org_id],'pricing_operation_not_found')
    if role not in ('OWNER','ESTIMATOR') or (role != 'OWNER' and operation['requested_by'] != actor_id):
        raise PricingError('pricing_permission_denied')
    if operation['state'] not in ('PREVIEW','PENDING'):
        raise PricingError('operation_already_final')
    request = decoded(operation['request'])
    rules_row = one('SELECT discount_approval_threshold_pct FROM public.pricing_rules '
                    'WHERE org_id=%s',[org_id],'pricing_rules_not_found')
    state = discount_state(role,D(str(request['discount_pct'])),confirmed,
                           D(str(rules_row['discount_approval_threshold_pct'])))
    if state == 'PENDING' or (reject and role != 'OWNER'):
        raise PricingError('owner_approval_required')
    # P07 — la banda también gobierna la aplicación: un PREVIEW fuera de
    # banda no se cuela por el camino directo.
    band = (decoded(operation['result']).get('band') or {})
    if band.get('state') and band['state'] != 'IN_BAND' and not reject:
        if role != 'OWNER':
            raise PricingError('owner_approval_required')
        if not confirmed:
            raise PricingError('owner_confirmation_required')
    audit_reason(reason)
    if reject:
        one("UPDATE public.pricing_operations SET state='REJECTED',approved_by=%s,approved_at=now(),reason=%s "
            'WHERE id=%s AND org_id=%s RETURNING id',[actor_id,reason,operation_id,org_id])
        _notify_pricing_decision(org_id, actor_id, operation, 'REJECTED')
        return operation_public(one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s',
                                    [operation_id,org_id]))
    project = one('SELECT * FROM public.projects WHERE id=%s AND org_id=%s FOR UPDATE',
                  [operation['project_id'],org_id])
    positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s AND org_id=%s '
                     'ORDER BY position_index FOR UPDATE',[project['id'],org_id])
    if (project['status'] != 'DRAFT'
            or (operation.get('revision_code') or 'REV-A') != project['current_revision']
            or source_revision(project,positions) != operation['source_revision']):
        raise PricingError('stale_pricing_operation')
    output = decoded(operation['result'])
    snapshot = decoded(operation['input_snapshot'])
    costs = {int(index):D(str(cost)) for index,cost in snapshot['cost_lines']}
    prices = {int(index):D(str(price)) for index,price in output['lines']}
    with connection.cursor() as cursor:
        for position in positions:
            index = position['position_index']
            if prices[index] < costs[index]:
                raise PricingError('negative_margin')
            cursor.execute('UPDATE public.project_positions SET cost_net=%s,price_net=%s,discount_pct=%s,'
                           'updated_at=now() WHERE id=%s AND org_id=%s',
                           [costs[index],prices[index],request['discount_pct'],position['id'],org_id])
        # El costo del proyecto es el costo del trato: las alternativas
        # quedan fuera (su price_net/cost_net propios sí se sellaron arriba).
        deal_cost = (D(str(output['deal_cost_net']))
                     if output.get('deal_cost_net') is not None
                     else sum(costs.values(),D('0')))
        cursor.execute('UPDATE public.projects SET total_cost_net=%s,total_price_net=%s,total_price_tax=%s,'
                       'total_price_gross=%s,updated_at=now() WHERE id=%s AND org_id=%s',
                       [deal_cost,output['project_net'],output['project_tax'],
                        output['project_gross'],project['id'],org_id])
        cursor.execute("UPDATE public.pricing_operations SET state='APPLIED',approved_by=%s,approved_at=clock_timestamp(),reason=%s "
                       'WHERE id=%s AND org_id=%s',[actor_id,reason,operation_id,org_id])
    _notify_pricing_decision(org_id, actor_id, operation, 'APPLIED')
    return operation_public(one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s',
                                [operation_id,org_id]))


def withdraw_operation(org_id, actor_id, role, operation_id, reason):
    """A PENDING request the requester no longer wants reviewed — or the owner
    clearing the queue — must not stay actionable forever."""
    operation = one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s FOR UPDATE',
                    [operation_id,org_id],'pricing_operation_not_found')
    if role not in ('OWNER','ESTIMATOR') or (role != 'OWNER' and operation['requested_by'] != actor_id):
        raise PricingError('pricing_permission_denied')
    if operation['state'] != 'PENDING':
        raise PricingError('operation_not_withdrawable')
    audit_reason(reason)
    one("UPDATE public.pricing_operations SET state='WITHDRAWN',approved_by=%s,approved_at=clock_timestamp(),"
        'reason=%s WHERE id=%s AND org_id=%s RETURNING id',
        [actor_id,reason,operation_id,org_id])
    if role == 'OWNER' and str(operation['requested_by']) != str(actor_id):
        # Retiro por el dueño también le avisa al solicitante.
        _notify_pricing_decision(org_id, actor_id, operation, 'WITHDRAWN')
    return operation_public(one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s',
                                [operation_id,org_id]))
