"""Server-authoritative BOM costing, reproducible previews and approvals."""

from dataclasses import asdict
from decimal import Decimal, localcontext
from hashlib import sha256
import json

from django.db import connection, DatabaseError

from authentication.errors import contract_error
from authentication.rls import tx_aborted
from dekopen_engine.commercial import (
    CommercialLine, PricingError, PricingMode, direct_cost, discount_state,
    finish_lines, target_project, unit_price, validate_segment,
)
from dekopen_engine.glass import exact_glass_area_m2
from dekopen_engine.glass_pricing import glass_price_lines
from dekopen_engine.models import GlassSurchargeRate
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
        stock = profile_stocks[cut.sku]
        cost = linear_cost(repo,stock.commercial_sku,cut.length_mm*cut.qty,stock.stock_length_mm)
        materials.append(cost)
        composition.append({'kind':'PROFILE','sku':stock.commercial_sku,
                            'quantity':str((cut.length_mm*cut.qty/D('1000')).quantize(D('0.001'))),
                            'unit':'M','cost':str(cost.quantize(D('0.0001')))})
    for steel in result.reinforcements:
        stock = steel_stocks[(steel.parent_profile_sku,steel.reinforcement_sku)]
        cost = linear_cost(repo,stock.commercial_sku,steel.length_mm*steel.qty,stock.stock_length_mm)
        materials.append(cost)
        composition.append({'kind':'REINFORCEMENT','sku':stock.commercial_sku,
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
                                    'quantity':str(line.quantity.quantize(D('0.0001'))),
                                    'unit':line.unit,'cost':str(line.cost.quantize(D('0.0001'))),
                                    'label':line.label})
    for panel in result.panels:
        panel_area = exact_glass_area_m2(panel.width_mm,panel.height_mm)
        cost = repo.cost(panel.sku,'M2') * panel_area
        materials.append(cost)
        composition.append({'kind':'PANEL','sku':panel.sku,
                            'quantity':str(panel_area.quantize(D('0.0001'))),
                            'unit':'M2','cost':str(cost.quantize(D('0.0001')))})
    for kit in result.hardware_items:
        cost = repo.cost(kit.kit_sku,'KIT') * kit.qty
        materials.append(cost)
        composition.append({'kind':'HARDWARE','sku':kit.kit_sku,
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
        cost = repo.cost(fitting.sku,'EA') * fitting.qty
        materials.append(cost)
        composition.append({'kind':'FITTING','sku':fitting.sku,
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
    area = exact_glass_area_m2(position['width_mm'],position['height_mm'])
    total = direct_cost(materials,area,rules['waste_factor_pct'],rules['labor_rate_per_m2'],
                        rules['installation_rate_per_m2'])
    formation = {'composition':composition,
                 'materials_cost':str(sum(materials,D('0')).quantize(D('0.0001'))),
                 'hardware_option_delta':str(selection_delta.quantize(D('0.0001'))),
                 'color_surcharge_delta':str(color_delta.quantize(D('0.0001'))),
                 'waste_pct':str(rules['waste_factor_pct']),
                 'labor_rate_per_m2':str(rules['labor_rate_per_m2']),
                 'installation_rate_per_m2':str(rules['installation_rate_per_m2']),
                 'area_m2':str(area.quantize(D('0.0001')))}
    return total, area, result, formation


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
    state = discount_state(actor.active_organization.role,discount,request['confirmed'])
    if mode == PricingMode.COMMERCIAL_LIST_WITH_DISCOUNTS:
        # Segment bands only bound the list-with-discounts catalogue: RETAIL
        # requires 0% and ARCHITECT 8–12%, so applying them to the manual
        # discount decision would make the estimator approval path
        # unreachable for any negotiated discount.
        validate_segment(request['segment'],discount,sum(p['quantity'] for p in positions))
    if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT and discount:
        raise PricingError('target_margin_already_defines_final_price')
    cost_lines, priced_lines, technical = [], [], []
    selection_extra = D('0')
    with localcontext() as context:
        context.prec = 80
        for position in positions:
            try:
                cost, area, result, formation = position_cost(repo,position,calculation_rules)
                index = position['position_index']
                cost_lines.append((index,cost*position['quantity']))
                # D04 deltas are sell additions; under a project target margin
                # they ride as undiscounted additions like project extras.
                selection_extra += (D(formation['hardware_option_delta'])
                                    + D(formation['color_surcharge_delta'])) * position['quantity']
                technical.append({'position_id':position['id'],
                                  'position_index':index,
                                  'unit_cost':str(cost.quantize(D('0.0001'))),
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
                exact_price = unit_price(mode,cost=cost,margin=rules['default_margin_pct'],area=area,
                                         width=position['width_mm'],height=position['height_mm'],
                                         foil=position['color_interior']!='WHITE' or position['color_exterior']!='WHITE',**extra)
                # D04 + D05: declared hardware selections and finish
                # surcharges add to the unit price as sell deltas —
                # discounted with the line like any other sell.
                exact_price += D(formation['hardware_option_delta']) + D(
                    formation['color_surcharge_delta'])
                priced_lines.append(CommercialLine(index,position['quantity'],cost,exact_price,discount))
            except PricingError as error:
                # The estimator fixing this has to know WHICH vano fails —
                # name the position, then the human reason for the code.
                detail = PRICING_ERROR_DETAILS.get(
                    error.code,'la operación comercial requiere revisar sus permisos, datos o configuración')
                raise contract_error(422,error.code,f'{_position_label(position)}: {detail}.') from error
        extra_amounts = [D(str(item['amount'])) for item in request.get('extras') or []]
        if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT and selection_extra:
            # Other modes already carry the delta inside each unit price.
            extra_amounts.append(selection_extra)
        output = (target_project(cost_lines,request['target_margin'],request['currency'],rules['tax_rate_pct'],extra_amounts)
                  if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT
                  else finish_lines(priced_lines,request['currency'],rules['tax_rate_pct'],extra_amounts))
    # Per-line selling detail so the decision screen can show unit price,
    # quantity and discount next to the line total — a line net is a per-
    # position TOTAL (unit × qty × (1−discount)), never a unit price. The
    # authority stays in the engine: exact_unit_price is the pre-discount
    # computed unit; the target-margin mode has no per-line discount, so
    # its unit readout is the allocated line net over quantity.
    quantities = {position['position_index']: int(position['quantity']) for position in positions}
    if mode == PricingMode.TARGET_GROSS_MARGIN_PROJECT:
        line_detail = [
            {'position_index': index, 'quantity': quantities[index],
             'unit_price': str((D(str(net)) / quantities[index]).quantize(D('0.0001'))),
             'discount_pct': '0'}
            for index, net in output.lines]
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
         json_text({**asdict(output),'line_detail':line_detail}),source_revision(project,positions),project['current_revision'],
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
        'composition':p.get('composition') or [],
    } for p in technical]
    return {'id':str(record['id']),'state':'PENDING' if state=='PENDING' else 'PREVIEW',
            'project_id':str(project['id']),
            'project_code':project.get('code') or '',
            'project_name':project.get('name') or '',
            'client_name':project.get('client_name') or '',
            'revision_code':project['current_revision'],
            'discount_pct':str(discount),
            'pricing_mode':request.get('pricing_mode') or '',
            'segment':request.get('segment') or '',
            'currency':request['currency'],**asdict(output),
            'line_detail':line_detail,
            'extras':[{'label':item['label'],'kind':item['kind'],
                       'amount':str(item['amount'])}
                      for item in request.get('extras') or []],
            'cost_lines':[{'position_index':index,'line_cost':str(cost)} for index,cost in costs],
            'total_cost':str(sum((cost for _, cost in costs), D('0'))),
            'positions_breakdown':breakdown,
            'authorities':repo.authorities,
            'rules':{key:str(rules[key]) for key in
                     ('default_margin_pct','tax_rate_pct','waste_factor_pct','labor_rate_per_m2',
                      'installation_rate_per_m2') if key in rules},
            'reason':request['reason'],'requested_by':str(request['_actor_id']),
            'requested_by_email':request.get('_actor_email'),
            'approved_by':None,'approved_at':None,
            'created_at':record['created_at'].isoformat()}


def design_batch_preview(org_id, _actor, request):
    """§08-WC — honest money diff for a proposed batch design edit. Each
    item's proposed design passes the same engine gate a save would
    (calculate_design), then position_cost prices the stored position and
    the proposed product under the same rules — the count + Δ the human
    confirms is the real unit cost, never a model estimate."""
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
            position_id = entry['position_id']
            design = entry['design']
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
                before, *_ = position_cost(repo,position,calculation_rules)
                pseudo = {
                    'system_id':design['system_id'],
                    'parametric_tree':design['parametric_tree'],
                    'width_mm':D(str(design['nominal_width_mm'])),
                    'height_mm':D(str(design['nominal_height_mm'])),
                    'color_interior':design['color'],
                    'color_exterior':design['color'],
                }
                after, *_ = position_cost(repo,pseudo,calculation_rules)
            except ContractAPIException as error:
                items.append({'position_id':position_id,'ok':False,
                              'error_code':error.contract_code,'error':error.public_detail})
                continue
            except PricingError as error:
                items.append({'position_id':position_id,'ok':False,
                              'error_code':error.code,
                              'error':pricing_public_detail(error.code)})
                continue
            quantity = position['quantity']
            items.append({
                'position_id':position_id,
                'index':position['position_index'],
                'ok':True,
                'quantity':quantity,
                'unit_cost_before':str(before),
                'unit_cost_after':str(after),
                'line_cost_before':str(before*quantity),
                'line_cost_after':str(after*quantity),
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
        'composition':p.get('composition') or [],
    } for p in snapshot.get('positions') or []]
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
            'created_at':operation['created_at'].isoformat()}


def apply_operation(org_id, actor_id, role, operation_id, reason, confirmed, reject=False):
    operation = one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s FOR UPDATE',
                    [operation_id,org_id],'pricing_operation_not_found')
    if role not in ('OWNER','ESTIMATOR') or (role != 'OWNER' and operation['requested_by'] != actor_id):
        raise PricingError('pricing_permission_denied')
    if operation['state'] not in ('PREVIEW','PENDING'):
        raise PricingError('operation_already_final')
    request = decoded(operation['request'])
    state = discount_state(role,D(str(request['discount_pct'])),confirmed)
    if state == 'PENDING' or (reject and role != 'OWNER'):
        raise PricingError('owner_approval_required')
    audit_reason(reason)
    if reject:
        one("UPDATE public.pricing_operations SET state='REJECTED',approved_by=%s,approved_at=now(),reason=%s "
            'WHERE id=%s AND org_id=%s RETURNING id',[actor_id,reason,operation_id,org_id])
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
        cursor.execute('UPDATE public.projects SET total_cost_net=%s,total_price_net=%s,total_price_tax=%s,'
                       'total_price_gross=%s,updated_at=now() WHERE id=%s AND org_id=%s',
                       [sum(costs.values(),D('0')),output['project_net'],output['project_tax'],
                        output['project_gross'],project['id'],org_id])
        cursor.execute("UPDATE public.pricing_operations SET state='APPLIED',approved_by=%s,approved_at=clock_timestamp(),reason=%s "
                       'WHERE id=%s AND org_id=%s',[actor_id,reason,operation_id,org_id])
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
    return operation_public(one('SELECT * FROM public.pricing_operations WHERE id=%s AND org_id=%s',
                                [operation_id,org_id]))
