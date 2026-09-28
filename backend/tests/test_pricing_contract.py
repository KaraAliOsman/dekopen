"""SHOT-08 import precision and transport boundaries, without production stubs."""

from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from openpyxl import Workbook
import pytest

from dekopen_engine.commercial import PricingError
from pricing.serializers import CostItemSerializer, FxSerializer, PriceRequestSerializer
from pricing.views import DecimalJSONParser, price_response
from pricing.xlsx_import import parse_xlsx

MAPPING = {'sku':'SKU','description':'Description','unit':'Unit','unit_cost':'Cost'}


def workbook_bytes(rows):
    book = Workbook()
    sheet = book.active
    sheet.append(['SKU','Description','Unit','Cost'])
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def test_xlsx_mapping_preserves_four_decimals_description_and_locale():
    output = parse_xlsx(workbook_bytes([['A','Profile','BAR','1,2345']]),MAPPING,',')
    assert output == [{'sku':'A','description':'Profile','unit':'BAR','unit_cost':Decimal('1.2345')}]


@pytest.mark.parametrize('price', ['1,234.50','1 234,50','NaN','Infinity','-1','0,00001'])
def test_xlsx_rejects_ambiguous_or_invalid_prices(price):
    with pytest.raises(PricingError):
        parse_xlsx(workbook_bytes([['A','Profile','BAR',price]]),MAPPING,',')


@pytest.mark.parametrize('rows', [
    [['A','Profile','BAR','=1+1']], [['A','Profile','BAR','1'],['A','Other','BAR','2']],
    [['A','Profile','UNKNOWN','1']], [['','Profile','M','1']],
])
def test_xlsx_rejects_formulas_duplicates_and_invalid_units(rows):
    with pytest.raises(PricingError):
        parse_xlsx(workbook_bytes(rows),MAPPING,'.')


def test_numeric_xml_lexeme_is_not_rounded_through_binary_number():
    content = workbook_bytes([['A','Numeric authority','M',1]])
    target = BytesIO()
    with ZipFile(BytesIO(content)) as original, ZipFile(target,'w') as changed:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = data.replace(b'<v>1</v>',b'<v>1.000000000000000001</v>')
            changed.writestr(item,data)
    with pytest.raises(PricingError,match='xlsx_invalid_price_row_2'):
        parse_xlsx(target.getvalue(),MAPPING,'.')


def test_decimal_json_parser_preserves_lexeme_and_rejects_nonfinite():
    assert DecimalJSONParser().parse(BytesIO(b'{"value":1.2345}'))['value'] == Decimal('1.2345')
    with pytest.raises(Exception,match='Revisa'):
        DecimalJSONParser().parse(BytesIO(b'{"value":NaN}'))


def test_admin_cost_precision_and_unknown_fields_are_rejected():
    data = {'cost_list_id':'11111111-1111-4111-8111-111111111111','sku':'A',
            'unit':'M','item_type':'PROFILE','unit_cost':'1.00001'}
    assert not CostItemSerializer(data=data).is_valid()
    data['unit_cost']='1.2345'
    assert CostItemSerializer(data=data).is_valid()
    data['org_id']='22222222-2222-4222-8222-222222222222'
    assert not CostItemSerializer(data=data).is_valid()


def test_fx_requires_positive_rate_and_explicit_source():
    data = {'base_currency':'USD','quote_currency':'CLP','observed_rate':'0',
            'observed_date':'2026-09-10','effective_date':'2026-09-10','source':'Owner observation'}
    assert not FxSerializer(data=data).is_valid()
    data['observed_rate']='900.12345678'
    assert FxSerializer(data=data).is_valid()


def test_pricing_request_cannot_supply_cost_or_actor():
    data = {'project_id':'11111111-1111-4111-8111-111111111111','pricing_mode':'COST_PLUS_MARGIN',
            'currency':'CLP','effective_date':'2026-09-10','reason':'Review','cost':'0'}
    assert not PriceRequestSerializer(data=data).is_valid()


def test_position_cost_uses_engine_area_for_shaped_glass(monkeypatch):
    """A contoured glass piece prices by polygon area, never by bounding box."""
    from types import SimpleNamespace

    from dekopen_engine.models import GlassPiece, PlanPoint
    import pricing.service as service

    shape = [
        PlanPoint(x_mm=Decimal("0.00"), y_mm=Decimal("0.00")),
        PlanPoint(x_mm=Decimal("2000.00"), y_mm=Decimal("0.00")),
        PlanPoint(x_mm=Decimal("1800.00"), y_mm=Decimal("1000.00")),
        PlanPoint(x_mm=Decimal("200.00"), y_mm=Decimal("1000.00")),
    ]
    # bbox is 2.000000 m2; the engine polygon area is 1.800000 m2.
    glass = GlassPiece(
        bay_id="B1", width_mm=Decimal("2000.00"), height_mm=Decimal("1000.00"),
        shape=shape, area_m2=Decimal("1.80"), weight_kg=Decimal("9.00"),
        thickness_net_mm=Decimal("4.00"),
    )
    result = SimpleNamespace(
        profile_cuts=[], reinforcements=[], glasses=[glass],
        panels=[], hardware_items=[], fittings=[], leaf_weights=[],
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql):
            return None

    class Conn:
        needs_rollback = False

        def cursor(self):
            return Cursor()

    class Repo:
        org_id = "org"

        def cost(self, sku, unit):
            assert (sku, unit) == ("V4", "M2")
            return Decimal("100")

    position = {
        "system_id": "sys", "width_mm": Decimal("2000"),
        "height_mm": Decimal("1000"),
        "parametric_tree": {"id": "B1", "glass_article_sku": "V4"},
        "color_interior": "WHITE", "color_exterior": "WHITE",
    }
    params_repo = SimpleNamespace(
        load_visible=lambda *a, **k: None,
        load_coupler_articles=lambda *a, **k: {},
    )
    monkeypatch.setattr(service, "connection", Conn())
    monkeypatch.setattr(service, "SystemParamsRepository", lambda: params_repo)
    monkeypatch.setattr(service, "CuttingRepository", lambda: SimpleNamespace())
    monkeypatch.setattr(
        service, "engine_result_from_api", lambda **kwargs: result
    )
    total, _area, _result, _formation = service.position_cost(
        Repo(), position,
        {"waste_factor_pct": Decimal("0"),
         "labor_rate_per_m2": Decimal("0"),
         "installation_rate_per_m2": Decimal("0")},
    )
    assert total == Decimal("180")


def test_position_cost_prices_fittings_as_unit_pieces(monkeypatch):
    """Frameless fittings are real material: each declared SKU must resolve an
    'EA' cost-list entry or the quote fails — never silently priced at zero."""
    from types import SimpleNamespace

    from dekopen_engine.models import GlassPiece
    import pricing.service as service

    glass = GlassPiece(
        bay_id="B1", width_mm=Decimal("1000.00"), height_mm=Decimal("1000.00"),
        area_m2=Decimal("1.00"), weight_kg=Decimal("2.50"),
        thickness_net_mm=Decimal("4.00"),
    )
    fitting = SimpleNamespace(sku="CLAMP-SQ", qty=4)
    result = SimpleNamespace(
        profile_cuts=[], reinforcements=[], glasses=[glass],
        panels=[], hardware_items=[], fittings=[fitting], leaf_weights=[],
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql):
            return None

    class Conn:
        needs_rollback = False

        def cursor(self):
            return Cursor()

    calls = []

    class Repo:
        org_id = "org"

        def cost(self, sku, unit):
            calls.append((sku, unit))
            return Decimal("100") if unit == "M2" else Decimal("25")

    position = {
        "system_id": "sys", "width_mm": Decimal("1000"),
        "height_mm": Decimal("1000"),
        "parametric_tree": {"id": "B1", "type": "BAY",
                            "glass_article_sku": "V4"},
        "color_interior": "WHITE", "color_exterior": "WHITE",
    }
    params_repo = SimpleNamespace(
        load_visible=lambda *a, **k: None,
        load_coupler_articles=lambda *a, **k: {},
    )
    monkeypatch.setattr(service, "connection", Conn())
    monkeypatch.setattr(service, "SystemParamsRepository", lambda: params_repo)
    monkeypatch.setattr(service, "CuttingRepository", lambda: SimpleNamespace())
    monkeypatch.setattr(
        service, "engine_result_from_api", lambda **kwargs: result
    )
    total, _area, _result, _formation = service.position_cost(
        Repo(), position,
        {"waste_factor_pct": Decimal("0"),
         "labor_rate_per_m2": Decimal("0"),
         "installation_rate_per_m2": Decimal("0")},
    )
    assert ("CLAMP-SQ", "EA") in calls
    assert total == Decimal("200")  # 1 m² glass + 4 clamps


def test_public_response_uses_line_total_strings():
    result = price_response({'lines':((1,Decimal('2')),),'project_net':Decimal('2'),
                             'project_tax':Decimal('0'),'project_gross':Decimal('2')})
    assert result['lines']==[{'position_index':1,'line_net':'2'}]
    assert result['project_net']=='2'
    assert 'line_detail' not in result


def test_public_response_merges_line_selling_detail():
    """line_net is a position TOTAL (unit × qty × (1−discount)) — the
    decision surface must also see the unit price authority, the quantity
    and the applied discount, or it would divide the total back itself."""
    result = price_response({
        'lines': ((1, Decimal('90000')), (2, Decimal('76500'))),
        'line_detail': [
            {'position_index': 1, 'quantity': 3, 'unit_price': '31578.9474',
             'discount_pct': '0.05'},
            {'position_index': 2, 'quantity': 1, 'unit_price': '76500',
             'discount_pct': '0'},
        ],
        'project_net': Decimal('166500'), 'project_tax': Decimal('0'),
        'project_gross': Decimal('166500')})
    assert result['lines'] == [
        {'position_index': 1, 'line_net': '90000', 'quantity': 3,
         'unit_price': '31578.9474', 'discount_pct': '0.05'},
        {'position_index': 2, 'line_net': '76500', 'quantity': 1,
         'unit_price': '76500', 'discount_pct': '0'},
    ]
    assert 'line_detail' not in result
    # unit × qty × (1−discount) must reconstruct the line total.
    assert (Decimal('31578.9474') * 3 * (Decimal('1') - Decimal('0.05'))
            ).quantize(Decimal('1')) == Decimal('90000')


def test_design_batch_preview_prices_before_and_after(monkeypatch):
    """§08-WC — the batch diff is the engine-checked proposed design priced
    under the same rules; cost strings keep Decimal precision."""
    from types import SimpleNamespace
    from uuid import uuid4

    import pricing.service as service
    import projects.service as projects_service

    org_id, project_id, position_id, system_id = uuid4(), uuid4(), uuid4(), uuid4()
    tables = {
        'projects': [{
            'id': project_id, 'status': 'DRAFT', 'current_revision': 1,
        }],
        'project_versions': [],
        'pricing_rules': [{
            'waste_factor_pct': Decimal('0'),
            'labor_rate_per_m2': Decimal('0'),
            'installation_rate_per_m2': Decimal('0'),
        }],
        'tenancy_organizations': [{'currency': 'CLP'}],
        'project_positions': [{
            'id': position_id, 'position_index': 1, 'quantity': Decimal('2'),
            'system_id': system_id, 'width_mm': Decimal('1000'),
            'height_mm': Decimal('1000'), 'parametric_tree': {},
            'color_interior': 'WHITE', 'color_exterior': 'WHITE',
        }],
    }

    def _table(query):
        return next(key for key in tables if f'public.{key}' in query)

    monkeypatch.setattr(
        service, 'one',
        lambda query, params=(), code='missing': tables[_table(query)][0],
    )
    monkeypatch.setattr(
        service, 'rows',
        lambda query, params=(): tables[_table(query)],
    )

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql):
            return None

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(service, 'connection', Conn())
    # design_batch_preview opens documents.repository.documentary_backend for
    # the sealed-revision check — stub it (the rows() it guards are mocked).
    from contextlib import nullcontext

    import documents.repository as documents_repository
    monkeypatch.setattr(documents_repository, 'documentary_backend', nullcontext)
    monkeypatch.setattr(
        service, 'PricingRepository',
        lambda *a: SimpleNamespace(authorities=[], convert=lambda value, c: value),
    )
    checked = []
    monkeypatch.setattr(
        projects_service, 'calculate_design',
        lambda oid, design: checked.append(design),
    )
    priced = []

    def fake_cost(repo, position, rules):
        priced.append(position)
        return (Decimal('100') if len(priced) == 1 else Decimal('120'), None, None)

    monkeypatch.setattr(service, 'position_cost', fake_cost)

    result = service.design_batch_preview(org_id, None, {
        'project_id': str(project_id),
        'effective_date': '2026-01-01',
        'items': [{
            'position_id': str(position_id),
            'design': {
                'system_id': str(system_id),
                'nominal_width_mm': '1000',
                'nominal_height_mm': '1000',
                'color': 'WHITE',
                'parametric_tree': {'version': 'product-v2'},
            },
        }],
    })

    assert len(checked) == 1  # engine gate ran per item, like a save
    assert len(priced) == 2  # stored position + proposed pseudo-design
    item = result['items'][0]
    assert item['ok'] is True
    assert item['unit_cost_before'] == '100'
    assert item['unit_cost_after'] == '120'
    assert item['line_cost_after'] == '240'
    assert result['currency'] == 'CLP'


def test_design_batch_preview_refuses_sealed_revision(monkeypatch):
    """A sealed version at the current revision makes the preview moot —
    positions can't change, so there is nothing to diff."""
    from uuid import uuid4

    import pricing.service as service

    org_id, project_id = uuid4(), uuid4()
    tables = {
        'projects': [{'id': project_id, 'status': 'DRAFT', 'current_revision': 2}],
        'project_versions': [{'id': uuid4()}],
    }

    monkeypatch.setattr(
        service, 'one',
        lambda query, params=(), code='missing': tables['projects'][0],
    )
    monkeypatch.setattr(
        service, 'rows',
        lambda query, params=(): tables['project_versions'],
    )
    # The sealed-version check runs under documents.repository.documentary_backend;
    # stub it — the rows() it guards are mocked.
    from contextlib import nullcontext

    import documents.repository as documents_repository
    monkeypatch.setattr(documents_repository, 'documentary_backend', nullcontext)

    try:
        service.design_batch_preview(org_id, None, {
            'project_id': str(project_id),
            'effective_date': '2026-01-01',
            'items': [],
        })
        raise AssertionError('expected PricingError')
    except PricingError as error:
        assert error.code == 'commercial_revision_required'


def test_withdraw_retracts_only_own_pending(monkeypatch):
    """A pending approval is only retractable by its requester (or an OWNER
    clearing the queue); decided operations stay immutable."""
    from uuid import uuid4

    import pricing.service as service

    org_id, operation_id, requester = uuid4(), uuid4(), uuid4()
    operation = {
        'id': operation_id, 'org_id': org_id, 'state': 'PENDING',
        'requested_by': requester, 'requested_by_email': 'e@x.cl',
        'project_id': uuid4(), 'revision_code': 'REV-A', 'reason': 'Cotización',
        'input_snapshot': '{}', 'request': '{}', 'result': '{}',
        'approved_by': None, 'approved_at': None,
        'created_at': '2026-09-25T00:00:00Z',
    }
    queries = []
    monkeypatch.setattr(service, 'one',
                        lambda query, params=(), code='missing': (queries.append(query), operation)[1])
    monkeypatch.setattr(service, 'audit_reason', lambda reason: None)
    monkeypatch.setattr(service, 'operation_public', lambda row: row)

    output = service.withdraw_operation(org_id, requester, 'ESTIMATOR', operation_id, 'mistake')
    assert output is operation
    assert any(query.startswith('UPDATE public.pricing_operations') for query in queries)

    # A different estimator cannot retract someone else's request.
    queries.clear()
    with pytest.raises(PricingError):
        service.withdraw_operation(org_id, uuid4(), 'ESTIMATOR', operation_id, 'mistake')

    # An owner can clear the pending queue for review hygiene.
    service.withdraw_operation(org_id, uuid4(), 'OWNER', operation_id, 'cleanup')

    # A decided operation is immutable — history keeps its verdict.
    operation['state'] = 'APPLIED'
    with pytest.raises(PricingError):
        service.withdraw_operation(org_id, requester, 'ESTIMATOR', operation_id, 'mistake')


def test_extras_serializer_contract():
    base = {'project_id':'11111111-1111-4111-8111-111111111111','pricing_mode':'COST_PLUS_MARGIN',
            'currency':'CLP','effective_date':'2026-09-10','reason':'Review'}
    ok = {**base,'extras':[{'label':'Instalación','kind':'INSTALLATION','amount':'150000'},
                           {'label':'Traslado','kind':'FREIGHT','amount':'0'}]}
    assert PriceRequestSerializer(data=ok).is_valid()
    negative = {**base,'extras':[{'label':'X','kind':'OTHER','amount':'-1'}]}
    assert not PriceRequestSerializer(data=negative).is_valid()
    unknown_kind = {**base,'extras':[{'label':'X','kind':'MYSTERY','amount':'1'}]}
    assert not PriceRequestSerializer(data=unknown_kind).is_valid()
    blank_label = {**base,'extras':[{'label':'  ','kind':'OTHER','amount':'1'}]}
    assert not PriceRequestSerializer(data=blank_label).is_valid()
    overflow = {**base,'extras':[{'label':str(i),'kind':'OTHER','amount':'1'} for i in range(11)]}
    assert not PriceRequestSerializer(data=overflow).is_valid()
