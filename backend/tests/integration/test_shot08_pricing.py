"""Real PostgreSQL commercial authorities and atomic audit invariants."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from threading import Event, get_ident
from uuid import UUID, uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, transaction, DatabaseError, IntegrityError, ProgrammingError
from django.db.backends.utils import CursorWrapper
import pytest
from rest_framework.test import APIClient

from authentication.errors import ContractAPIException
from authentication.rls import authenticated_rls_context
from authentication.tenancy import MembershipRepository
from authentication.types import Membership, SupabaseUser, TenantContext, VerifiedSupabaseToken
from pricing.repository import PricingRepository, admin_write, audit_reason, commercial_backend, rows
from dekopen_engine.commercial import PricingError
import pricing.service as pricing_service
import pricing.views as pricing_views
from pricing.service import preview, apply_operation
from pricing.repository import json_text, one
from pricing.xlsx_import import import_rows, parse_xlsx
from projects import service as project_service
from projects.serializers import PositionWriteSerializer
from backend.tests.test_pricing_contract import MAPPING, workbook_bytes

pytestmark = pytest.mark.rls_integration


@pytest.fixture
def commercial_rows(django_db_blocker):
    with django_db_blocker.unblock():
        if connection.vendor != 'postgresql':
            pytest.fail('SHOT-08 requires real PostgreSQL; never skipped')
        with transaction.atomic():
            org, other = uuid4(),uuid4()
            users = {role:uuid4() for role in ('OWNER','ESTIMATOR','WORKSHOP_MANAGER','INSTALLER')}
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO public.tenancy_organizations(id,name,tax_id) VALUES(%s,%s,%s),(%s,%s,%s)',
                               [org,'Pricing fixture A',str(org),other,'Pricing fixture B',str(other)])
                for role,user in users.items():
                    cursor.execute('INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,%s)',
                                   [org,user,role])
            yield org,other,users
            transaction.set_rollback(True)


@pytest.fixture
def committed_commercial_rows(django_db_blocker):
    with django_db_blocker.unblock():
        if connection.vendor != 'postgresql':
            pytest.fail('SHOT-08 requires real PostgreSQL; never skipped')
        org, other = uuid4(), uuid4()
        users = {role:uuid4() for role in ('OWNER','ESTIMATOR','WORKSHOP_MANAGER','INSTALLER')}
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO public.tenancy_organizations(id,name,tax_id) VALUES(%s,%s,%s),(%s,%s,%s)',
                           [org,'Committed pricing A',str(org),other,'Committed pricing B',str(other)])
            for role,user in users.items():
                cursor.execute('INSERT INTO public.tenancy_memberships(org_id,user_id,role) VALUES(%s,%s,%s)',
                               [org,user,role])
        try:
            yield org,other,users
        finally:
            connection.close()
            with connection.cursor() as cursor:
                # Immutable evidence (ai_audit_logs, sealed ledger) deliberately
                # refuses org teardown — committed residue is harmless because
                # every fixture identifier is uuid-random per run.
                try:
                    cursor.execute('DELETE FROM public.tenancy_organizations WHERE id IN (%s,%s)',[org,other])
                except (IntegrityError, ProgrammingError):
                    pass


@contextmanager
def as_user(user):
    with authenticated_rls_context({'sub':str(user),'role':'authenticated','aal':'aal2'}):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",[str(user)])
        audit_reason('Independent SHOT-08 integration test')
        yield


def make_list(org, valid_from, price, currency='CLP', valid_to=None, active=True):
    parent = admin_write('cost-lists',org,{'supplier_name':'Fixture supplier','currency':currency,
                        'valid_from':valid_from,'valid_to':valid_to,'is_active':active},'Create fixture list')
    admin_write('cost-items',org,{'cost_list_id':parent['id'],'sku':'SKU-A','item_type':'PROFILE',
                'unit':'M','unit_cost':Decimal(price)},'Create fixture price')
    return parent['id']


def test_temporal_latest_ties_missing_and_no_silent_zero(commercial_rows):
    org,_,users = commercial_rows
    with as_user(users['OWNER']):
        make_list(org,date(2026,9,1),'10')
        make_list(org,date(2026,9,5),'12',valid_to=date(2026,9,10))
        make_list(org,date(2026,9,9),'99',active=False)
        repo = PricingRepository(org,date(2026,9,10),'CLP')
        assert repo.cost('SKU-A','M') == Decimal('12')
        assert PricingRepository(org,date(2026,9,11),'CLP').cost('SKU-A','M') == Decimal('10')
        make_list(org,date(2026,9,5),'13')
        with pytest.raises(PricingError,match='ambiguous_cost_list'):
            repo.cost('SKU-A','M')
        with pytest.raises(PricingError,match='cost_list_not_found'):
            repo.cost('MISSING','M')


def test_fx_snapshot_and_four_decimal_cost(commercial_rows):
    org,_,users = commercial_rows
    with as_user(users['OWNER']):
        make_list(org,date(2026,9,1),'0.1234','USD')
        fx = admin_write('fx',org,{'base_currency':'USD','quote_currency':'CLP',
                         'observed_rate':Decimal('900'),'observed_date':date(2026,9,10),
                         'effective_date':date(2026,9,10),'source':'Synthetic FX fixture'},'Record FX')
        repo = PricingRepository(org,date(2026,9,10),'CLP',fx['id'])
        assert repo.cost('SKU-A','M') == Decimal('116.613')
        with pytest.raises(PricingError,match='missing_fx_authority'):
            PricingRepository(org,date(2026,9,11),'CLP',fx['id']).cost('SKU-A','M')
        with pytest.raises(PricingError,match='fx_snapshot_immutable'):
            admin_write('fx',org,{'observed_rate':Decimal('901')},'Attempt change',fx['id'])


def test_role_and_cross_tenant_cost_confidentiality(commercial_rows):
    org,other,users = commercial_rows
    with as_user(users['OWNER']):
        make_list(org,date(2026,9,1),'7')
        with pytest.raises(DatabaseError), transaction.atomic():
            make_list(other,date(2026,9,1),'8')
    for role in ('ESTIMATOR','INSTALLER'):
        with as_user(users[role]):
            assert rows('SELECT * FROM public.cost_list_items') == []
            assert rows('SELECT * FROM public.price_audit_logs') == []
            assert rows('SELECT * FROM public.pricing_operations') == []
            with pytest.raises(DatabaseError), transaction.atomic():
                rows('SELECT total_cost_net FROM public.projects')
            with pytest.raises(DatabaseError), transaction.atomic():
                rows('SELECT cost_net FROM public.project_positions')
    with as_user(users['WORKSHOP_MANAGER']):
        assert len(rows('SELECT * FROM public.cost_list_items')) == 1
        assert rows("UPDATE public.cost_list_items SET unit_cost=99 RETURNING id") == []
    with as_user(users['ESTIMATOR']), commercial_backend():
        assert PricingRepository(org,date(2026,9,10),'CLP').cost('SKU-A','M') == Decimal('7')
        with pytest.raises(PricingError,match='cost_list_not_found'):
            PricingRepository(other,date(2026,9,10),'CLP').cost('SKU-A','M')


def test_audit_precedes_mutation_and_failure_rolls_back(commercial_rows):
    org,_,users = commercial_rows
    # An AFTER-row assertion checks evidence already exists when the row becomes visible.
    with connection.cursor() as cursor:
        cursor.execute("""CREATE FUNCTION pg_temp.assert_price_audit() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN IF NOT EXISTS(SELECT 1 FROM public.price_audit_logs WHERE entity_id=NEW.id
            AND new_record->>'unit_cost'=to_jsonb(NEW)->>'unit_cost') THEN
            RAISE EXCEPTION 'audit_was_not_first'; END IF; RETURN NEW; END $$;
          CREATE TRIGGER zz_assert_audit AFTER INSERT OR UPDATE ON public.cost_list_items
          FOR EACH ROW EXECUTE FUNCTION pg_temp.assert_price_audit();""")
    with as_user(users['OWNER']):
        list_id = make_list(org,date(2026,9,1),'1.2345')
        item = rows('SELECT id FROM public.cost_list_items WHERE cost_list_id=%s',[list_id])[0]
        admin_write('cost-items',org,{'unit_cost':Decimal('1.2346')},'Fourth digit',item['id'])
        audit = rows("SELECT old_value,new_value,actor_user_id FROM public.price_audit_logs "
                     "WHERE entity_id=%s AND field='UPDATE'",[item['id']])[0]
        assert (audit['old_value'],audit['new_value']) == (Decimal('1.2345'),Decimal('1.2346'))
        assert audit['actor_user_id']==users['OWNER']
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.pricing_reason','',true)")
            cursor.execute('UPDATE public.cost_list_items SET unit_cost=9 WHERE id=%s',[item['id']])
        assert rows('SELECT unit_cost FROM public.cost_list_items WHERE id=%s',[item['id']])[0]['unit_cost']==Decimal('1.2346')
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('DELETE FROM public.price_audit_logs WHERE entity_id=%s',[item['id']])


def test_xlsx_preview_apply_and_partial_failure_rollback(commercial_rows):
    org,other,users = commercial_rows
    workbook = workbook_bytes([['EXCEL-1','Exact description','M','1.2345']])
    parsed = parse_xlsx(workbook,MAPPING,'.')
    with as_user(users['OWNER']):
        list_id = make_list(org,date(2026,9,1),'1')
        count = one('SELECT count(*) AS n FROM public.price_audit_logs')['n']
        assert import_rows(org,list_id,parsed,'Preview import',False)==parsed
        assert one('SELECT count(*) AS n FROM public.price_audit_logs')['n']==count
        assert rows("SELECT id FROM public.cost_list_items WHERE sku='EXCEL-1'")==[]
        import_rows(org,list_id,parsed,'Apply exact workbook',True)
        item = one("SELECT * FROM public.cost_list_items WHERE sku='EXCEL-1'")
        assert item['unit_cost']==Decimal('1.2345')
        assert item['description']=='Exact description'
        assert one('SELECT reason FROM public.price_audit_logs WHERE entity_id=%s',[item['id']])['reason']=='Apply exact workbook'
        with pytest.raises(PricingError,match='cost_list_not_found'):
            import_rows(other,list_id,parsed,'Wrong tenant',True)
        failing = [{**parsed[0],'sku':'MUST-ROLLBACK'},parsed[0]]
        count = one('SELECT count(*) AS n FROM public.price_audit_logs')['n']
        with pytest.raises(DatabaseError), transaction.atomic():
            import_rows(org,list_id,failing,'Conflicting import',True)
        assert rows("SELECT id FROM public.cost_list_items WHERE sku='MUST-ROLLBACK'")==[]
        assert one('SELECT count(*) AS n FROM public.price_audit_logs')['n']==count


def test_configuration_requires_base_glass_and_finite_authorities(commercial_rows):
    org,_,users = commercial_rows
    with as_user(users['OWNER']):
        with pytest.raises(DatabaseError), transaction.atomic():
            admin_write('configurations',org,{'context_code':'NO-BASE','typology':'FIXED',
                'pricing_mode':'PRICE_PER_M2_BY_TYPOLOGY','currency':'CLP','rate_per_m2':Decimal('1')},'Invalid base')
        with pytest.raises(DatabaseError), transaction.atomic():
            admin_write('fx',org,{'base_currency':'USD','quote_currency':'CLP',
                'observed_rate':Decimal('NaN'),'observed_date':date(2026,9,10),
                'effective_date':date(2026,9,10),'source':'Invalid fixture'},'Reject nonfinite')


def seed_unpriced_project(org, owner, system=None):
    system = system or one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")['id']
    project = one('INSERT INTO public.projects(org_id,code,name,client_name,created_by) '
                  'VALUES(%s,%s,%s,%s,%s) RETURNING id',[org,str(uuid4()),'Commercial gate','Fixture',owner])['id']
    tree = {'id':'root','type':'BAY','opening_type':'FIXED','glass_spec':'4-12-4 Float Incoloro',
            'glass_thickness_mm':'24.00','glass_article_sku':'GLASS-BASE'}
    one('INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,typology,system_id,'
        'width_mm,height_mm,parametric_tree,bom_snapshot) VALUES(%s,%s,1,1,%s,%s,1000,1000,%s::jsonb,%s::jsonb) RETURNING id',
        [org,project,'FIXED',system,json_text(tree),'{}'])
    return project


def seed_commercial_project(org, owner, system=None):
    project = seed_unpriced_project(org, owner, system)
    with as_user(owner):
        parent = admin_write('cost-lists',org,{'supplier_name':'Gate','currency':'CLP','valid_from':date(2026,9,1)},'Gate setup')
        for sku,unit,cost in [('DEMO-BAR-MARCO','BAR','100'),('DEMO-BAR-JQ-10','BAR','100'),
                              ('DEMO-STEEL-BAR-MARCO','BAR','100'),('GLASS-BASE','M2','100')]:
            admin_write('cost-items',org,{'cost_list_id':parent['id'],'sku':sku,'item_type':'FIXTURE',
                        'unit':unit,'unit_cost':Decimal(cost)},'Gate input')
        admin_write('rules',org,{'pricing_mode':'COST_PLUS_MARGIN','default_margin_pct':Decimal('0.35'),
                    'tax_rate_pct':Decimal('0.19'),'waste_factor_pct':Decimal('0.08'),
                    'labor_rate_per_m2':Decimal('15'),'installation_rate_per_m2':Decimal('12')},'Gate rules')
        for mode in ('PRICE_PER_M2_BY_TYPOLOGY','FIXED_PRICE_MATRIX_DIMENSIONAL','COMMERCIAL_LIST_WITH_DISCOUNTS'):
            values = {'context_code':'DEFAULT','typology':'FIXED','pricing_mode':mode,'currency':'CLP'}
            if mode=='PRICE_PER_M2_BY_TYPOLOGY':
                values.update(rate_per_m2=Decimal('2000'),base_glass_sku='GLASS-BASE')
            if mode=='COMMERCIAL_LIST_WITH_DISCOUNTS':
                values['catalog_price']=Decimal('2000')
            config=admin_write('configurations',org,values,'Gate config')
            if mode=='FIXED_PRICE_MATRIX_DIMENSIONAL':
                admin_write('matrix-cells',org,{'configuration_id':config['id'],'width_mm':1000,
                            'height_mm':1000,'price':Decimal('2000')},'Gate matrix')
    return project


def price_request(project, user, mode='COST_PLUS_MARGIN', discount='0'):
    return {'project_id':project,'pricing_mode':mode,'currency':'CLP','effective_date':date(2026,9,10),
            'context_code':'DEFAULT','discount_pct':Decimal(discount),'target_margin':Decimal('0.35'),
            'segment':'RETAIL','confirmed':False,'reason':'Independent gate preview','_actor_id':user}


def tenant(org,role):
    membership=Membership(organization_id=org,organization_name='Fixture',role=role)
    return TenantContext(active_organization=membership,memberships=(membership,))


@pytest.mark.parametrize('mode',['COST_PLUS_MARGIN','PRICE_PER_M2_BY_TYPOLOGY',
    'FIXED_PRICE_MATRIX_DIMENSIONAL','TARGET_GROSS_MARGIN_PROJECT','COMMERCIAL_LIST_WITH_DISCOUNTS'])
def test_five_modes_resolve_real_bom_and_apply_atomically(commercial_rows,mode):
    org,_,users=commercial_rows
    project=seed_commercial_project(org,users['OWNER'])
    with as_user(users['OWNER']),commercial_backend():
        output=preview(org,tenant(org,'OWNER'),price_request(project,users['OWNER'],mode))
        assert output['state']=='PREVIEW'
        assert output['revision_code']=='REV-A'
        if mode in ('PRICE_PER_M2_BY_TYPOLOGY','FIXED_PRICE_MATRIX_DIMENSIONAL','COMMERCIAL_LIST_WITH_DISCOUNTS'):
            assert output['project_net']==Decimal('2000')
            assert output['project_tax']==Decimal('380')
        else:
            # Independent G1 oracle: (4024+3676+3880)/6000*100 + .8281*100
            # = 275.81 materials; *1.08 + 15+12 = 324.8748; /.65 -> CLP500.
            assert output['project_net']==Decimal('500')
            assert output['project_tax']==Decimal('95')
        applied=apply_operation(org,users['OWNER'],'OWNER',output['id'],'Apply approved gate',False)
        assert applied['state']=='APPLIED'
        persisted=one('SELECT total_price_net FROM public.projects WHERE id=%s',[project])
        assert persisted['total_price_net']==Decimal(str(output['project_net']))
        with pytest.raises(PricingError,match='operation_already_final'):
            apply_operation(org,users['OWNER'],'OWNER',output['id'],'Retry',False)


def test_composite_pricing_requires_exact_typology_configuration(commercial_rows):
    org,_,users=commercial_rows
    project=seed_commercial_project(org,users['OWNER'])
    position=one('SELECT id,system_id,updated_at FROM public.project_positions WHERE project_id=%s',[project])
    tree={
        'id':'S1','type':'SPLIT_V','split_offset_mm':'500.00','mullion_profile_sku':'POSTE-V',
        'children':[
            {'id':'B1','type':'BAY','opening_type':'FIXED','glass_spec':'4-12-4 Float Incoloro',
             'glass_thickness_mm':'24.00','glass_article_sku':'GLASS-BASE'},
            {'id':'B2','type':'BAY','opening_type':'FIXED','glass_spec':'4-12-4 Float Incoloro',
             'glass_thickness_mm':'24.00','glass_article_sku':'GLASS-BASE'},
        ],
    }
    serializer=PositionWriteSerializer(data={'location_tag':'Fachada','quantity':1,'design':{
        'system_id':position['system_id'],'nominal_width_mm':'1000.00','nominal_height_mm':'1000.00',
        'color':'WHITE','parametric_tree':tree}})
    assert serializer.is_valid(),serializer.errors
    values=serializer.validated_data
    values['expected_updated_at']=position['updated_at']
    with as_user(users['OWNER']):
        saved=project_service.save_position(org,project,values,position_id=position['id'])
        assert saved['typology']=='COMPOSITE'
        cost_list=one('SELECT id FROM public.cost_lists WHERE org_id=%s',[org])
        for sku in ('DEMO-BAR-POSTE-V','DEMO-STEEL-BAR-POSTE-V'):
            admin_write('cost-items',org,{'cost_list_id':cost_list['id'],'sku':sku,
                'item_type':'FIXTURE','unit':'BAR','unit_cost':Decimal('100')},'Composite input')
        with commercial_backend():
            assert preview(org,tenant(org,'OWNER'),price_request(
                project,users['OWNER'],'COST_PLUS_MARGIN'))['state']=='PREVIEW'
            assert preview(org,tenant(org,'OWNER'),price_request(
                project,users['OWNER'],'TARGET_GROSS_MARGIN_PROJECT'))['state']=='PREVIEW'
            for mode in ('PRICE_PER_M2_BY_TYPOLOGY','FIXED_PRICE_MATRIX_DIMENSIONAL',
                         'COMMERCIAL_LIST_WITH_DISCOUNTS'):
                with pytest.raises(ContractAPIException) as caught:
                    preview(org,tenant(org,'OWNER'),price_request(project,users['OWNER'],mode))
                assert caught.value.contract_code=='pricing_configuration_not_found'
                assert 'Fachada' in caught.value.public_detail
        for mode in ('PRICE_PER_M2_BY_TYPOLOGY','FIXED_PRICE_MATRIX_DIMENSIONAL',
                     'COMMERCIAL_LIST_WITH_DISCOUNTS'):
            config_values={'context_code':'DEFAULT','typology':'COMPOSITE','pricing_mode':mode,
                           'currency':'CLP'}
            if mode=='PRICE_PER_M2_BY_TYPOLOGY':
                config_values.update(rate_per_m2=Decimal('3000'),base_glass_sku='GLASS-BASE')
            if mode=='COMMERCIAL_LIST_WITH_DISCOUNTS':
                config_values['catalog_price']=Decimal('3000')
            config=admin_write('configurations',org,config_values,'Composite authority')
            if mode=='FIXED_PRICE_MATRIX_DIMENSIONAL':
                admin_write('matrix-cells',org,{'configuration_id':config['id'],'width_mm':1000,
                            'height_mm':1000,'price':Decimal('3000')},'Composite matrix')
            with commercial_backend():
                assert preview(org,tenant(org,'OWNER'),price_request(
                    project,users['OWNER'],mode))['project_net']==Decimal('3000')


def test_legacy_draft_rejects_submitted_typology_mismatch(commercial_rows):
    org,_,users=commercial_rows
    system=one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")['id']
    code=f"MISMATCH-{uuid4()}"
    response=owner_client(users['OWNER']).post('/api/v1/pricing/drafts/',{
        'code':code,'name':'Legacy mismatch','client_name':'Fixture','reason':'Legacy proof',
        'positions':[{'position_index':1,'quantity':1,'typology':'TURN','system_id':str(system),
            'nominal_width_mm':'1000.00','nominal_height_mm':'1000.00','color':'WHITE',
            'parametric_tree':{'id':'B1','type':'BAY','opening_type':'FIXED',
                'glass_spec':'4-12-4 Float Incoloro','glass_thickness_mm':'24.00',
                'glass_article_sku':'GLASS-BASE'}}]},format='json')
    assert response.status_code==400
    assert response.json()['error']['code']=='typology_mismatch'
    with as_user(users['OWNER']):
        assert rows('SELECT id FROM public.projects WHERE org_id=%s AND code=%s',[org,code])==[]


def test_estimator_pending_owner_approval_and_stale_input(commercial_rows):
    org,_,users=commercial_rows
    project=seed_commercial_project(org,users['OWNER'])
    draft=seed_unpriced_project(org,users['OWNER'])
    with as_user(users['ESTIMATOR']),commercial_backend():
        with pytest.raises(PricingError,match='pricing_permission_denied'):
            preview(org,tenant(org,'ESTIMATOR'),price_request(project,users['ESTIMATOR'],'TARGET_GROSS_MARGIN_PROJECT'))
        output=preview(org,tenant(org,'ESTIMATOR'),price_request(project,users['ESTIMATOR'],discount='0.15'))
        assert output['state']=='PENDING'
        with pytest.raises(PricingError,match='owner_approval_required'):
            apply_operation(org,users['ESTIMATOR'],'ESTIMATOR',output['id'],'Try unauthorized',False)
    with as_user(users['OWNER']),commercial_backend():
        assert apply_operation(org,users['OWNER'],'OWNER',output['id'],'Approve exact request',False)['state']=='APPLIED'
        next_output=preview(org,tenant(org,'OWNER'),price_request(draft,users['OWNER']))
    with as_user(users['OWNER']):
        assert len(rows('UPDATE public.project_positions SET quantity=2 WHERE project_id=%s RETURNING id',
                        [draft]))==1
    with as_user(users['OWNER']),commercial_backend():
        with pytest.raises(PricingError,match='stale_pricing_operation'):
            apply_operation(org,users['OWNER'],'OWNER',next_output['id'],'Stale',False)


@pytest.mark.parametrize('session_role', ['postgres', 'service_role', 'OWNER', 'ESTIMATOR'])
def test_direct_commercial_insert_guard_all_fields(commercial_rows, session_role):
    """Real roles: zero drafts remain valid; every nonzero commercial field fails."""
    from contextlib import nullcontext
    from psycopg import sql

    org, _, users = commercial_rows
    system = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")['id']
    creator = users.get(session_role, users['OWNER'])
    identity = as_user(users[session_role]) if session_role in users else nullcontext()
    with transaction.atomic(), identity:
        with connection.cursor() as cursor:
            if session_role not in users:
                cursor.execute("SELECT set_config('request.jwt.claims','{}',true)")
                cursor.execute("SELECT set_config('request.jwt.claim.sub','',true)")
                cursor.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(session_role)))
                cursor.execute('SELECT auth.uid()')
                assert cursor.fetchone()[0] is None
            project = uuid4()
            cursor.execute('INSERT INTO public.projects(id,org_id,code,name,client_name,created_by) '
                           'VALUES(%s,%s,%s,%s,%s,%s)',
                           [project,org,str(project),'Zero draft','Fixture',creator])
            position = uuid4()
            position_values = [position,org,project,1,'FIXED',system,'{}','{}']
            position_insert = ('INSERT INTO public.project_positions(id,org_id,project_id,position_index,'
                               'typology,system_id,parametric_tree,bom_snapshot{extra}) '
                               'VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb{value})')
            # Dimensions are mandatory but their schema defaults are not assumed.
            position_insert = position_insert.replace('bom_snapshot{extra}',
                'bom_snapshot,width_mm,height_mm{extra}').replace('%s::jsonb{value}',
                '%s::jsonb,1000,1000{value}')
            cursor.execute(position_insert.format(extra='',value=''),position_values)
            for field in ('total_cost_net','total_price_net','total_price_tax','total_price_gross'):
                attempted = uuid4()
                with pytest.raises(DatabaseError,match='pricing_service_required') as rejected, transaction.atomic():
                    cursor.execute(sql.SQL('INSERT INTO public.projects(id,org_id,code,name,client_name,created_by,{}) '
                        'VALUES(%s,%s,%s,%s,%s,%s,1)').format(sql.Identifier(field)),
                        [attempted,org,str(attempted),'Forbidden','Fixture',creator])
                assert rejected.value.__cause__.sqlstate == '42501'
                cursor.execute('SELECT count(*) FROM public.projects WHERE id=%s',[attempted])
                assert cursor.fetchone()[0] == 0
            for field in ('cost_net','price_net','discount_pct'):
                attempted = uuid4()
                with pytest.raises(DatabaseError,match='pricing_service_required') as rejected, transaction.atomic():
                    cursor.execute(position_insert.format(extra=','+field,value=',0.01'),
                                   [attempted,org,project,2,'FIXED',system,'{}','{}'])
                assert rejected.value.__cause__.sqlstate == '42501'
                cursor.execute('SELECT count(*) FROM public.project_positions WHERE id=%s',[attempted])
                assert cursor.fetchone()[0] == 0
            cursor.execute('SELECT count(*) FROM public.projects WHERE id=%s',[project])
            assert cursor.fetchone()[0] == 1
            cursor.execute('SELECT count(*) FROM public.project_positions WHERE id=%s',[position])
            assert cursor.fetchone()[0] == 1


def test_authorized_apply_audit_before_and_full_rollback(commercial_rows):
    """A second BEFORE trigger witnesses prior evidence; a late failure rolls all back."""
    org, _, users = commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
        cursor.execute("""CREATE FUNCTION pg_temp.assert_commercial_before() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
          IF NOT EXISTS(SELECT 1 FROM public.price_audit_logs WHERE entity_id=NEW.id
            AND old_record=to_jsonb(OLD) AND new_record=to_jsonb(NEW)
            AND actor_user_id=auth.uid() AND reason='Apply owner fix gate') THEN
            RAISE EXCEPTION 'commercial_audit_not_before'; END IF;
          RETURN NEW; END $$;
          CREATE TRIGGER zz_assert_commercial_before BEFORE UPDATE ON public.project_positions
            FOR EACH ROW EXECUTE FUNCTION pg_temp.assert_commercial_before();
          CREATE TRIGGER zz_assert_commercial_before BEFORE UPDATE ON public.projects
            FOR EACH ROW EXECUTE FUNCTION pg_temp.assert_commercial_before();
          CREATE FUNCTION pg_temp.reject_commercial_apply() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.state='APPLIED' THEN RAISE EXCEPTION 'forced_apply_rollback'; END IF;
            RETURN NEW; END $$;
          CREATE TRIGGER zz_reject_apply BEFORE UPDATE ON public.pricing_operations
            FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_commercial_apply();""")
    with as_user(users['OWNER']), commercial_backend():
        operation = preview(org,tenant(org,'OWNER'),price_request(project,users['OWNER']))
    with connection.cursor() as cursor:
        cursor.execute('RESET ROLE')
    before_project = one('SELECT * FROM public.projects WHERE id=%s',[project])
    before_positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s',[project])
    count = one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',[org])['n']
    with pytest.raises(DatabaseError,match='forced_apply_rollback'), transaction.atomic():
        with as_user(users['OWNER']), commercial_backend():
            apply_operation(org,users['OWNER'],'OWNER',operation['id'],'Apply owner fix gate',False)
    assert one('SELECT * FROM public.projects WHERE id=%s',[project]) == before_project
    assert rows('SELECT * FROM public.project_positions WHERE project_id=%s',[project]) == before_positions
    assert one('SELECT state FROM public.pricing_operations WHERE id=%s',[operation['id']])['state']=='PREVIEW'
    assert one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',[org])['n']==count
    with connection.cursor() as cursor:
        cursor.execute('DROP TRIGGER zz_reject_apply ON public.pricing_operations')
    with as_user(users['OWNER']), commercial_backend():
        assert apply_operation(org,users['OWNER'],'OWNER',operation['id'],
                               'Apply owner fix gate',False)['state']=='APPLIED'
    with connection.cursor() as cursor:
        cursor.execute('RESET ROLE')
    assert one('SELECT total_price_net FROM public.projects WHERE id=%s',[project])['total_price_net']==Decimal('500')
    assert one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',[org])['n']==count+3


def price_payload(project, mode='COST_PLUS_MARGIN', discount='0'):
    request = price_request(project,None,mode,discount)
    request.pop('_actor_id')
    return {key:str(value) if isinstance(value,(UUID,date,Decimal)) else value
            for key,value in request.items()}


def owner_client(user):
    client = APIClient()
    client.force_authenticate(
        user=SupabaseUser(id=user,email='owner@fixture.local'),
        token=VerifiedSupabaseToken(access_token='verified-token',user_id=user,
            email='owner@fixture.local',aal='aal2',
            claims={'sub':str(user),'role':'authenticated','aal':'aal2'}))
    return client


def assert_public_error(response, status_code, code, detail):
    assert response.status_code==status_code
    assert response.json()=={'error':{'code':code,'detail':detail}}
    body = response.content.decode()
    for marker in ('Traceback','InvalidEngineRequest','InvalidCutContract','MissingStockAuthority',
                   'AmbiguousStockAuthority','UnsupportedEngineContract','UnsupportedCatalogContract',
                   'SystemNotFound','PricingError','ValueError','SELECT','INSERT','UPDATE','DELETE',
                   'backend/','backend\\','C:\\','C:/'):
        assert marker not in body


def threaded_preview(user, project, before=None):
    close_old_connections()
    try:
        if before is not None:
            before()
        return owner_client(user).post('/api/v1/pricing/preview/',price_payload(project),format='json')
    finally:
        close_old_connections()


def pricing_operation_evidence(org, project):
    operations = rows('SELECT id,input_snapshot,result,source_revision FROM public.pricing_operations '
                      'WHERE org_id=%s AND project_id=%s ORDER BY created_at,id',[org,project])
    audits = rows("SELECT entity_id FROM public.price_audit_logs WHERE org_id=%s "
                  "AND entity='pricing_operations' ORDER BY created_at,id",[org])
    return operations, audits


def required_cost_list(org, valid_from, cost):
    parent = admin_write('cost-lists',org,{'supplier_name':'Snapshot fixture','currency':'CLP',
                         'valid_from':valid_from},'Snapshot list')
    for sku,unit in [('DEMO-BAR-MARCO','BAR'),('DEMO-BAR-JQ-10','BAR'),
                     ('DEMO-STEEL-BAR-MARCO','BAR'),('GLASS-BASE','M2')]:
        admin_write('cost-items',org,{'cost_list_id':parent['id'],'sku':sku,
                    'item_type':'FIXTURE','unit':unit,'unit_cost':Decimal(cost)},'Snapshot cost')
    return parent['id']


@contextmanager
def deferred_preview_failure(sqlstate, once):
    if sqlstate not in {'40001','40P01','23505','23514','42501','55P03','57014','25P02'}:
        raise ValueError('unsupported test SQLSTATE')
    suffix = uuid4().hex
    sequence = f'test_preview_attempt_{suffix}'
    function = f'test_preview_failure_{suffix}'
    trigger = f'test_preview_commit_{suffix}'
    condition = 'attempt_no = 1' if once else 'TRUE'
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SEQUENCE public.{sequence}')
        cursor.execute(f"""CREATE FUNCTION public.{function}() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
          DECLARE attempt_no BIGINT;
          BEGIN
            attempt_no := nextval('public.{sequence}'::regclass);
            IF {condition} THEN
              RAISE EXCEPTION 'forced_preview_commit_failure' USING ERRCODE='{sqlstate}';
            END IF;
            RETURN NEW;
          END $$""")
        cursor.execute(f"""CREATE CONSTRAINT TRIGGER {trigger}
          AFTER INSERT ON public.pricing_operations DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION public.{function}()""")
    try:
        yield sequence
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TRIGGER {trigger} ON public.pricing_operations')
            cursor.execute(f'DROP FUNCTION public.{function}()')
            cursor.execute(f'DROP SEQUENCE public.{sequence}')


def test_pricing_http_invalid_design_returns_public_400(committed_commercial_rows):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    with as_user(users['OWNER']):
        assert len(rows("UPDATE public.project_positions SET parametric_tree="
                        "jsonb_set(parametric_tree,'{width_mm}','\"999.00\"'::jsonb) "
                        "WHERE project_id=%s RETURNING id",[project]))==1
    response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',price_payload(project),
                                                 format='json')
    assert_public_error(response,400,'validation_error','Revisa los campos y los valores ingresados.')


@pytest.mark.parametrize("defect", ["missing", "ambiguous", "zero", "negative"])
def test_pricing_http_invalid_stock_returns_public_422(committed_commercial_rows, defect):
    from backend.tests.integration.catalog_fixture import copy_fixed_catalog
    org, _, users = committed_commercial_rows
    system = copy_fixed_catalog(org)
    article = one("SELECT id FROM public.profile_articles WHERE system_id=%s AND sku='MARCO'", [system])
    if defect == "missing":
        one("UPDATE public.profile_purchase_mappings SET is_active=FALSE WHERE profile_article_id=%s RETURNING id", [article["id"]])
    elif defect == "ambiguous":
        one("INSERT INTO public.profile_purchase_mappings(profile_article_id,org_id,commercial_sku,manufacturer_name,purchase_unit) "
            "VALUES(%s,%s,'ALTERNATIVE','Fixture','BAR') RETURNING id", [article["id"],org])
    else:
        one("UPDATE public.profile_articles SET commercial_length_mm=%s WHERE id=%s RETURNING id",
            [0 if defect == "zero" else -1, article["id"]])
    project = seed_commercial_project(org,users["OWNER"],system)
    response = owner_client(users["OWNER"]).post("/api/v1/pricing/preview/",price_payload(project),format="json")
    assert_public_error(response,422,"technical_authority_required",
                        "Revisa el dise\u00f1o y su cat\u00e1logo t\u00e9cnico antes de cotizar.")


def test_pricing_http_valid_preview_remains_successful(committed_commercial_rows):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',price_payload(project),
                                                 format='json')
    assert response.status_code==200
    body = response.json()
    assert set(body)=={'id','project_id','revision_code','discount_pct','state','currency','lines',
                      'project_net','project_tax','project_gross','cost_lines','total_cost',
                      'project_code','project_name','client_name','pricing_mode','segment',
                      'positions_breakdown','authorities','rules','requested_by_email',
                      'reason','requested_by','approved_by','approved_at','created_at',
                      'extras','extras_net'}
    assert body['approved_by'] is None and body['approved_at'] is None
    assert body['state']=='PREVIEW'
    assert body['project_id']==str(project)
    assert body['revision_code']=='REV-A'
    assert body['discount_pct']=='0.0000'
    assert body['currency']=='CLP'
    assert body['project_net']=='500'
    assert body['project_tax']=='95'
    assert body['project_gross']=='595'
    assert body['lines']==[{'position_index':1,'line_net':'500'}]


def privileged_role():
    with connection.cursor() as cursor:
        cursor.execute('RESET ROLE')


def applied_commercial_project(org, owner):
    project = seed_commercial_project(org,owner)
    with as_user(owner), commercial_backend():
        output = preview(org,tenant(org,'OWNER'),price_request(project,owner))
        assert apply_operation(org,owner,'OWNER',output['id'],
                               'Apply fixture gate',False)['state']=='APPLIED'
    privileged_role()
    return project


def assert_commercial_state(project, before_project, before_positions, org, before_audit):
    assert one('SELECT * FROM public.projects WHERE id=%s',[project])==before_project
    assert rows('SELECT * FROM public.project_positions WHERE project_id=%s ORDER BY id',
                [project])==before_positions
    assert one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',
               [org])['n']==before_audit


def test_applied_commercial_state_rejects_direct_writes(commercial_rows):
    org,_,users = commercial_rows
    project = applied_commercial_project(org,users['OWNER'])
    draft = seed_unpriced_project(org,users['OWNER'])
    system = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")['id']
    position = one('SELECT id FROM public.project_positions WHERE project_id=%s',[project])['id']
    draft_position = one('SELECT id FROM public.project_positions WHERE project_id=%s',[draft])['id']
    before_project = one('SELECT * FROM public.projects WHERE id=%s',[project])
    before_positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s ORDER BY id',
                            [project])
    before_draft = one('SELECT * FROM public.projects WHERE id=%s',[draft])
    before_draft_positions = rows(
        'SELECT * FROM public.project_positions WHERE project_id=%s ORDER BY id',[draft])
    before_audit = one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',[org])['n']
    forbidden = [
        ('DELETE FROM public.project_positions WHERE id=%s RETURNING id',[position]),
        ('DELETE FROM public.projects WHERE id=%s RETURNING id',[project]),
        ('UPDATE public.project_positions SET quantity=2 WHERE id=%s RETURNING id',[position]),
        ('UPDATE public.project_positions SET width_mm=1100 WHERE id=%s RETURNING id',[position]),
        ("UPDATE public.project_positions SET parametric_tree='{}'::jsonb WHERE id=%s RETURNING id",
         [position]),
        ("UPDATE public.project_positions SET color_exterior='FOILED' WHERE id=%s RETURNING id",
         [position]),
        ("UPDATE public.projects SET name='Direct rename' WHERE id=%s RETURNING id",[project]),
        ('INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,typology,'
         'system_id,width_mm,height_mm,parametric_tree,bom_snapshot) '
         'VALUES(%s,%s,9,1,%s,%s,1000,1000,%s::jsonb,%s::jsonb) RETURNING id',
         [org,project,'FIXED',system,'{}','{}']),
        ('UPDATE public.project_positions SET project_id=%s WHERE id=%s RETURNING id',
         [project,draft_position]),
        ('UPDATE public.project_positions SET project_id=%s WHERE id=%s RETURNING id',
         [draft,position]),
    ]
    with as_user(users['OWNER']):
        for statement,parameters in forbidden:
            with pytest.raises(DatabaseError,match='pricing_service_required') as rejected, \
                    transaction.atomic():
                rows(statement,parameters)
            assert rejected.value.__cause__.sqlstate=='42501'
    privileged_role()
    assert_commercial_state(project,before_project,before_positions,org,before_audit)
    assert one('SELECT * FROM public.projects WHERE id=%s',[draft])==before_draft
    assert rows('SELECT * FROM public.project_positions WHERE project_id=%s ORDER BY id',
                [draft])==before_draft_positions


def test_other_tenant_direct_writes_touch_zero_rows(commercial_rows):
    org,other,users = commercial_rows
    project = applied_commercial_project(org,users['OWNER'])
    position = one('SELECT id FROM public.project_positions WHERE project_id=%s',[project])['id']
    outsider = uuid4()
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO public.tenancy_memberships(org_id,user_id,role) '
                       'VALUES(%s,%s,%s)',[other,outsider,'OWNER'])
    before_project = one('SELECT * FROM public.projects WHERE id=%s',[project])
    before_positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s ORDER BY id',
                            [project])
    before_audit = one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',[org])['n']
    with as_user(outsider):
        assert rows("UPDATE public.projects SET name='Hidden' WHERE id=%s RETURNING id",
                    [project])==[]
        assert rows('DELETE FROM public.projects WHERE id=%s RETURNING id',[project])==[]
        assert rows('UPDATE public.project_positions SET quantity=9 WHERE id=%s RETURNING id',
                    [position])==[]
        assert rows('DELETE FROM public.project_positions WHERE id=%s RETURNING id',[position])==[]
    privileged_role()
    assert_commercial_state(project,before_project,before_positions,org,before_audit)


def test_zero_unapplied_draft_remains_directly_mutable(commercial_rows):
    org,_,users = commercial_rows
    system = one("SELECT id FROM public.profile_systems WHERE code='DEMO_60'")['id']
    before_audit = one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',
                       [org])['n']
    with as_user(users['OWNER']):
        project = one('INSERT INTO public.projects(org_id,code,name,client_name,created_by) '
                      'VALUES(%s,%s,%s,%s,%s) RETURNING id',
                      [org,str(uuid4()),'Direct draft','Fixture',users['OWNER']])['id']
        first = one('INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,'
                    'typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot) '
                    'VALUES(%s,%s,1,1,%s,%s,1000,1000,%s::jsonb,%s::jsonb) RETURNING id',
                    [org,project,'FIXED',system,'{}','{}'])['id']
        second = one('INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,'
                     'typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot) '
                     'VALUES(%s,%s,2,1,%s,%s,1000,1000,%s::jsonb,%s::jsonb) RETURNING id',
                     [org,project,'FIXED',system,'{}','{}'])['id']
        assert len(rows("UPDATE public.project_positions SET quantity=2,width_mm=1100,"
                        "color_exterior='FOILED' WHERE id=%s RETURNING id",[first]))==1
        assert len(rows("UPDATE public.projects SET name='Renamed draft' WHERE id=%s RETURNING id",
                        [project]))==1
        assert len(rows('DELETE FROM public.project_positions WHERE id=%s RETURNING id',
                        [first]))==1
        assert len(rows('DELETE FROM public.projects WHERE id=%s RETURNING id',[project]))==1
        assert rows('SELECT id FROM public.project_positions WHERE id=%s',[second])==[]
        assert rows('SELECT id FROM public.projects WHERE id=%s',[project])==[]
    privileged_role()
    assert one('SELECT count(*) AS n FROM public.price_audit_logs WHERE org_id=%s',
               [org])['n']==before_audit


def import_file():
    return SimpleUploadedFile('prices.xlsx',workbook_bytes([['IMP-1','Importable','M','1.5']]),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def import_payload(list_id,**overrides):
    data = {'file':import_file(),'mapping':json_text(MAPPING),'decimal_separator':'.',
            'cost_list_id':str(list_id),'reason':'Audited import','apply':'false'}
    for key,value in overrides.items():
        if value is None:
            data.pop(key)
        else:
            data[key] = value
    return data


@pytest.mark.parametrize('override',[
    {'cost_list_id':'not-a-uuid'},
    {'apply':'not-boolean'},
    {'decimal_separator':';'},
    {'reason':None},
    {'file':None},
    {'mapping':'{'},
    {'org_id':str(uuid4())},
],ids=['malformed-uuid','invalid-boolean','invalid-separator','missing-reason',
       'missing-file','malformed-mapping','unknown-org-id'])
def test_pricing_import_http_contract_failures_are_canonical_400(commercial_rows,override):
    org,_,users = commercial_rows
    with as_user(users['OWNER']):
        list_id = make_list(org,date(2026,9,1),'1')
    response = owner_client(users['OWNER']).post('/api/v1/pricing/import/',
        import_payload(list_id,**override),format='multipart')
    assert_public_error(response,400,'validation_error','Revisa los campos y los valores ingresados.')


def test_pricing_import_http_valid_preview_persists_nothing(commercial_rows):
    org,_,users = commercial_rows
    with as_user(users['OWNER']):
        list_id = make_list(org,date(2026,9,1),'1')
    response = owner_client(users['OWNER']).post('/api/v1/pricing/import/',
        import_payload(list_id),format='multipart')
    assert response.status_code==200
    assert response.json()['items']==[{'sku':'IMP-1','description':'Importable','unit':'M',
                                       'unit_cost':'1.5'}]
    assert rows("SELECT id FROM public.cost_list_items WHERE sku='IMP-1'")==[]


def test_preview_uses_one_snapshot_for_rules_costs_and_repeated_skus(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    one('INSERT INTO public.project_positions(org_id,project_id,position_index,quantity,typology,'
        'system_id,width_mm,height_mm,parametric_tree,bom_snapshot,color_interior,color_exterior) '
        'SELECT org_id,project_id,2,quantity,typology,system_id,width_mm,height_mm,parametric_tree,'
        'bom_snapshot,color_interior,color_exterior FROM public.project_positions '
        'WHERE project_id=%s AND position_index=1 RETURNING id',[project])
    early_read, resume = Event(), Event()
    original_cost = PricingRepository.cost

    def paused_cost(repo, sku, required_unit):
        value = original_cost(repo,sku,required_unit)
        if not early_read.is_set():
            early_read.set()
            assert resume.wait(10)
        return value

    monkeypatch.setattr(PricingRepository,'cost',paused_cost)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(threaded_preview,users['OWNER'],project)
        assert early_read.wait(10)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE public.cost_list_items SET unit_cost=200 WHERE org_id=%s',[org])
            cursor.execute('UPDATE public.pricing_rules SET labor_rate_per_m2=30 WHERE org_id=%s',[org])
        resume.set()
        response = request.result(timeout=15)
    assert response.status_code==200
    first = one('SELECT input_snapshot FROM public.pricing_operations WHERE id=%s',[response.json()['id']])
    snapshot = pricing_service.decoded(first['input_snapshot'])
    first_costs = [item['cost'] for item in snapshot['authorities'] if 'cost' in item]
    assert len(first_costs)>4
    assert {Decimal(str(item['unit_cost'])) for item in first_costs}=={Decimal('100')}
    assert Decimal(str(snapshot['rules']['labor_rate_per_m2']))==Decimal('15')
    second = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',price_payload(project),format='json')
    assert second.status_code==200
    current = pricing_service.decoded(one('SELECT input_snapshot FROM public.pricing_operations '
        'WHERE id=%s',[second.json()['id']])['input_snapshot'])
    second_costs = [item['cost'] for item in current['authorities'] if 'cost' in item]
    assert {Decimal(str(item['unit_cost'])) for item in second_costs}=={Decimal('200')}
    assert Decimal(str(current['rules']['labor_rate_per_m2']))==Decimal('30')


def test_preview_snapshot_excludes_newly_applicable_cost_authority(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    old_list = one('SELECT id FROM public.cost_lists WHERE org_id=%s',[org])['id']
    snapshot_ready, resume = Event(), Event()
    original_one = pricing_service.one

    def pause_after_rules(query, parameters=(), code='authority_not_found'):
        value = original_one(query,parameters,code)
        if 'FROM public.pricing_rules' in str(query) and not snapshot_ready.is_set():
            snapshot_ready.set()
            assert resume.wait(10)
        return value

    monkeypatch.setattr(pricing_service,'one',pause_after_rules)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(threaded_preview,users['OWNER'],project)
        assert snapshot_ready.wait(10)
        with transaction.atomic(), as_user(users['OWNER']):
            new_list = required_cost_list(org,date(2026,9,10),'300')
        resume.set()
        response = request.result(timeout=15)
    assert response.status_code==200
    first = pricing_service.decoded(one('SELECT input_snapshot FROM public.pricing_operations '
        'WHERE id=%s',[response.json()['id']])['input_snapshot'])
    assert {item['cost']['cost_list_id'] for item in first['authorities'] if 'cost' in item}=={str(old_list)}
    second = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',price_payload(project),format='json')
    assert second.status_code==200
    current = pricing_service.decoded(one('SELECT input_snapshot FROM public.pricing_operations '
        'WHERE id=%s',[second.json()['id']])['input_snapshot'])
    assert {item['cost']['cost_list_id'] for item in current['authorities'] if 'cost' in item}=={str(new_list)}


def test_preview_project_conflict_retries_complete_attempt_and_commits_once(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    snapshot_ready, resume = Event(), Event()
    membership_calls = []
    original_memberships = MembershipRepository.list_active_for_user

    def paused_memberships(repo, user_id):
        memberships = original_memberships(repo,user_id)
        membership_calls.append(tuple(memberships))
        if len(membership_calls)==1:
            snapshot_ready.set()
            assert resume.wait(10)
        return memberships

    monkeypatch.setattr(MembershipRepository,'list_active_for_user',paused_memberships)
    attempts = []
    original_attempt = pricing_views._preview_attempt

    def counted_attempt(*args,**kwargs):
        attempts.append(1)
        return original_attempt(*args,**kwargs)

    monkeypatch.setattr(pricing_views,'_preview_attempt',counted_attempt)
    sqlstates = []
    original_sqlstate = pricing_views._database_sqlstate

    def observed_sqlstate(error):
        state = original_sqlstate(error)
        sqlstates.append(state)
        return state

    monkeypatch.setattr(pricing_views,'_database_sqlstate',observed_sqlstate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(threaded_preview,users['OWNER'],project)
        assert snapshot_ready.wait(10)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE public.projects SET name='Concurrent revision' WHERE id=%s",[project])
        resume.set()
        response = request.result(timeout=15)
    assert response.status_code==200
    assert sqlstates==['40001']
    assert len(attempts)==2
    assert len(membership_calls)==2
    operations,audits = pricing_operation_evidence(org,project)
    assert len(operations)==1
    assert [item['entity_id'] for item in audits]==[operations[0]['id']]
    current_project = one('SELECT * FROM public.projects WHERE id=%s',[project])
    positions = rows('SELECT * FROM public.project_positions WHERE project_id=%s '
                     'ORDER BY position_index FOR UPDATE',[project])
    assert operations[0]['source_revision']==pricing_service.source_revision(current_project,positions)


def test_preview_retry_refreshes_membership_authorization(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    snapshot_ready, resume = Event(), Event()
    calls = []
    original_memberships = MembershipRepository.list_active_for_user

    def paused_memberships(repo, user_id):
        memberships = original_memberships(repo,user_id)
        calls.append(memberships[0].role)
        if len(calls)==1:
            snapshot_ready.set()
            assert resume.wait(10)
        return memberships

    monkeypatch.setattr(MembershipRepository,'list_active_for_user',paused_memberships)
    sqlstates = []
    original_sqlstate = pricing_views._database_sqlstate

    def observed_sqlstate(error):
        state = original_sqlstate(error)
        sqlstates.append(state)
        return state

    monkeypatch.setattr(pricing_views,'_database_sqlstate',observed_sqlstate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(threaded_preview,users['OWNER'],project)
        assert snapshot_ready.wait(10)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE public.projects SET name='Authorization revision' WHERE id=%s",[project])
            cursor.execute("UPDATE public.tenancy_memberships SET role='INSTALLER' "
                           'WHERE org_id=%s AND user_id=%s',[org,users['OWNER']])
        resume.set()
        response = request.result(timeout=15)
    assert_public_error(response,403,'pricing_permission_denied',
                        'Tu rol no permite esta operación comercial.')
    assert sqlstates==['40001']
    assert calls==['OWNER','INSTALLER']
    assert pricing_operation_evidence(org,project)==([],[])


def test_preview_deadlock_retries_complete_attempt_and_commits_once(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    position = one('SELECT id FROM public.project_positions WHERE project_id=%s',[project])['id']
    child_locked, parent_locked, writer_done = Event(), Event(), Event()

    def writer_cycle():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET deadlock_timeout='5s'")
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute('SELECT id FROM public.project_positions WHERE id=%s FOR UPDATE',[position])
                child_locked.set()
                assert parent_locked.wait(10)
                cursor.execute('SELECT id FROM public.projects WHERE id=%s FOR UPDATE',[project])
        finally:
            writer_done.set()
            close_old_connections()

    original_rows = pricing_service.rows
    lock_attempts = []

    def observed_position_lock(query, parameters=()):
        if 'FROM public.project_positions' in str(query) and 'FOR UPDATE' in str(query):
            lock_attempts.append(1)
            if len(lock_attempts)==1:
                parent_locked.set()
        return original_rows(query,parameters)

    monkeypatch.setattr(pricing_service,'rows',observed_position_lock)
    attempts = []
    original_attempt = pricing_views._preview_attempt

    def counted_attempt(*args,**kwargs):
        attempts.append(1)
        if len(attempts)==2:
            assert writer_done.wait(10)
        return original_attempt(*args,**kwargs)

    monkeypatch.setattr(pricing_views,'_preview_attempt',counted_attempt)
    sqlstates = []
    original_sqlstate = pricing_views._database_sqlstate

    def observed_sqlstate(error):
        state = original_sqlstate(error)
        sqlstates.append(state)
        return state

    monkeypatch.setattr(pricing_views,'_database_sqlstate',observed_sqlstate)

    def preview_timeout():
        with connection.cursor() as cursor:
            cursor.execute("SET deadlock_timeout='100ms'")

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(writer_cycle)
        assert child_locked.wait(10)
        request = pool.submit(threaded_preview,users['OWNER'],project,preview_timeout)
        response = request.result(timeout=20)
        writer.result(timeout=20)
    assert response.status_code==200
    assert sqlstates==['40P01']
    assert len(attempts)==2
    operations,audits = pricing_operation_evidence(org,project)
    assert len(operations)==1
    assert [item['entity_id'] for item in audits]==[operations[0]['id']]


def test_preview_commit_failure_retries_after_full_rollback(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    attempts = []
    original_attempt = pricing_views._preview_attempt

    def counted_attempt(*args,**kwargs):
        attempts.append(1)
        return original_attempt(*args,**kwargs)

    monkeypatch.setattr(pricing_views,'_preview_attempt',counted_attempt)
    with deferred_preview_failure('40001',True) as sequence:
        response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',
                                                     price_payload(project),format='json')
        assert one(f'SELECT last_value FROM public.{sequence}')['last_value']==2
    assert response.status_code==200
    assert len(attempts)==2
    operations,audits = pricing_operation_evidence(org,project)
    assert len(operations)==1
    assert [item['entity_id'] for item in audits]==[operations[0]['id']]


@pytest.mark.parametrize('sqlstate',['40001','40P01'])
def test_preview_retry_exhaustion_is_three_attempts_and_zero_state(
    committed_commercial_rows, sqlstate
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    with deferred_preview_failure(sqlstate,False) as sequence:
        response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',
                                                     price_payload(project),format='json')
        assert one(f'SELECT last_value FROM public.{sequence}')['last_value']==3
    assert_public_error(response,409,'pricing_transaction_rejected',
                        'No se guardó el cambio. Revisa duplicados, vigencia y permisos; vuelve a cargar los datos.')
    assert pricing_operation_evidence(org,project)==([],[])


@pytest.mark.parametrize('sqlstate',['23505','23514','42501','55P03','57014','25P02'])
def test_preview_does_not_retry_nonretryable_commit_failures(committed_commercial_rows,sqlstate):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    with deferred_preview_failure(sqlstate,False) as sequence:
        response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',
                                                     price_payload(project),format='json')
        assert one(f'SELECT last_value FROM public.{sequence}')['last_value']==1
    assert_public_error(response,409,'pricing_transaction_rejected',
                        'No se guardó el cambio. Revisa duplicados, vigencia y permisos; vuelve a cargar los datos.')
    assert pricing_operation_evidence(org,project)==([],[])


def test_preview_isolation_first_sql_and_normal_endpoint_is_read_committed(
    committed_commercial_rows, monkeypatch
):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    statements = []
    request_thread = get_ident()
    original_execute = CursorWrapper.execute

    preview_isolation = []

    def traced_execute(cursor, sql, params=None):
        if get_ident()==request_thread:
            statement=str(sql).strip()
            statements.append(statement)
            # Sample the connection's isolation level once the request's
            # transaction is live — the first real statement after the SET.
            if not preview_isolation and not statement.upper().startswith('SET '):
                with connection.cursor() as probe:
                    original_execute(probe,'SHOW transaction_isolation')
                    preview_isolation.append(probe.fetchone()[0])
        return original_execute(cursor,sql,params)

    monkeypatch.setattr(CursorWrapper,'execute',traced_execute)
    response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',
                                                 price_payload(project),format='json')
    assert response.status_code==200
    assert statements[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'
    assert preview_isolation==['repeatable read']
    normal_isolation = []
    original_admin_list = pricing_views.admin_list

    def checked_admin_list(*args,**kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SHOW transaction_isolation')
            normal_isolation.append(cursor.fetchone()[0])
        return original_admin_list(*args,**kwargs)

    monkeypatch.setattr(pricing_views,'admin_list',checked_admin_list)
    response = owner_client(users['OWNER']).get('/api/v1/pricing/admin/cost-lists/')
    assert response.status_code==200
    assert normal_isolation==['read committed']


def test_preview_refuses_an_enclosing_transaction(committed_commercial_rows):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    with transaction.atomic():
        response = owner_client(users['OWNER']).post('/api/v1/pricing/preview/',
                                                     price_payload(project),format='json')
    assert_public_error(response,409,'pricing_transaction_rejected',
                        'No se guardó el cambio. Revisa duplicados, vigencia y permisos; vuelve a cargar los datos.')
    assert pricing_operation_evidence(org,project)==([],[])


def test_apply_uses_frozen_preview_after_authority_change(committed_commercial_rows):
    org,_,users = committed_commercial_rows
    project = seed_commercial_project(org,users['OWNER'])
    client = owner_client(users['OWNER'])
    preview_response = client.post('/api/v1/pricing/preview/',price_payload(project),format='json')
    assert preview_response.status_code==200
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('UPDATE public.cost_list_items SET unit_cost=400 WHERE org_id=%s',[org])
    applied = client.post(f"/api/v1/pricing/operations/{preview_response.json()['id']}/apply/",
                          {'reason':'Apply frozen authority','confirmed':False,'reject':False},format='json')
    assert applied.status_code==200
    assert applied.json()['project_net']==preview_response.json()['project_net']
    assert one('SELECT total_price_net FROM public.projects WHERE id=%s',[project])['total_price_net']==Decimal(
        preview_response.json()['project_net'])


def test_position_cost_preserves_original_database_sqlstate(commercial_rows,monkeypatch):
    org,_,users = commercial_rows
    project = seed_commercial_project(org,users['OWNER'])

    def failed_technical_read(*args,**kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM public.missing_shot08_technical_authority')

    monkeypatch.setattr(pricing_service.SystemParamsRepository,'load_visible',failed_technical_read)
    with pytest.raises(DatabaseError) as rejected:
        with as_user(users['OWNER']), commercial_backend():
            repo = PricingRepository(org,date(2026,9,10),'CLP')
            position = one('SELECT * FROM public.project_positions WHERE project_id=%s',[project])
            rules = one('SELECT * FROM public.pricing_rules WHERE org_id=%s',[org])
            pricing_service.position_cost(repo,position,rules)
    assert rejected.value.__cause__.sqlstate=='42P01'
    assert one('SELECT 1 AS value')['value']==1
