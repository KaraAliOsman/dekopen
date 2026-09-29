"""Authenticated pricing endpoints with separate public and confidential data."""

from contextlib import contextmanager
from decimal import Decimal
import json
import logging

from django.db import connection, DatabaseError, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from psycopg.pq import TransactionStatus
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.errors import contract_error
from authentication.rls import authenticated_rls_context
from authentication.serializers import ACTIVE_ORGANIZATION_HEADER, ErrorResponseSerializer
from authentication.tenancy import MembershipRepository, enforce_owner_mfa, resolve_tenant_context
from authentication.views import verified_request_token
from dekopen_engine.commercial import PricingError
from dekopen_engine.cutting import InvalidCutContract
from engine_api.adapter import calculate_from_api, InvalidEngineRequest, UnsupportedEngineContract
from engine_api.repository import SystemParamsRepository, UnsupportedCatalogContract, SystemNotFound
from pricing.repository import (admin_list, admin_write, audit_reason, commercial_backend,
                                json_text, one, rows)
from pricing.serializers import (
    AdminResponseSerializer, AdminWriteSerializer, ApplySerializer, DraftProjectSerializer,
    DraftResponseSerializer, PriceRequestSerializer, PriceResponseSerializer, RESOURCE_SERIALIZERS,
    ImportRequestSerializer, DesignBatchPreviewRequestSerializer,
    DesignBatchPreviewResponseSerializer, WithdrawSerializer,
)
from pricing.service import (apply_operation, design_batch_preview, operation_public,
                             preview, withdraw_operation, pricing_public_detail)
from pricing.xlsx_import import import_rows, parse_xlsx
from projects.typology import derive_typology

logger = logging.getLogger(__name__)
ERRORS = {code:OpenApiResponse(ErrorResponseSerializer) for code in (400,401,403,404,409,422,503)}


class DecimalJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return json.load(stream,parse_float=Decimal,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        except (ValueError,UnicodeDecodeError) as error:
            raise contract_error(400,'invalid_json','Revisa el formato de los datos.') from error


def validate(serializer_type, data, *, partial=False):
    serializer = serializer_type(data=data, partial=partial)
    if not serializer.is_valid():
        raise contract_error(400,'validation_error','Revisa los campos y los valores ingresados.')
    return serializer.validated_data


@contextmanager
def public_pricing_errors():
    try:
        yield
    except PricingError as error:
        forbidden = error.code in ('pricing_permission_denied','owner_confirmation_required','owner_approval_required')
        raise contract_error(403 if forbidden else 422,error.code,
                             pricing_public_detail(error.code)) from error
    except InvalidEngineRequest as error:
        raise contract_error(400,'validation_error',
                             'Revisa los campos y los valores ingresados.') from error
    except (InvalidCutContract,UnsupportedEngineContract,UnsupportedCatalogContract,SystemNotFound) as error:
        raise contract_error(422,'technical_authority_required','Revisa el diseño y su catálogo técnico antes de cotizar.') from error
    except DatabaseError as error:
        cause = error.__cause__
        logger.warning('Pricing transaction rejected (%s, SQLSTATE=%s, constraint=%s)',
            type(error).__name__,getattr(cause,'sqlstate',None),
            getattr(getattr(cause,'diag',None),'constraint_name',None))
        raise contract_error(409,'pricing_transaction_rejected',
                             'No se guardó el cambio. Revisa duplicados, vigencia y permisos; vuelve a cargar los datos.') from error


@contextmanager
def scope(request, allowed=('OWNER',)):
    token = verified_request_token(request)
    with public_pricing_errors():
        with authenticated_rls_context(token.claims):
            tenant = resolve_tenant_context(MembershipRepository().list_active_for_user(token.user_id),
                                            request.headers.get('X-Organization-ID'))
            enforce_owner_mfa(tenant,token.aal)
            request._request.verified_org_id = str(tenant.active_organization.organization_id)
            if tenant.active_organization.role not in allowed:
                raise PricingError('pricing_permission_denied')
            yield token,tenant,tenant.active_organization.organization_id


def _preview_connection_ready():
    if connection.vendor != 'postgresql':
        raise DatabaseError('Pricing preview requires PostgreSQL')
    connection.ensure_connection()
    raw_connection = connection.connection
    if (raw_connection is None or raw_connection.closed or connection.in_atomic_block
            or not connection.get_autocommit()
            or raw_connection.info.transaction_status != TransactionStatus.IDLE):
        raise DatabaseError('Pricing preview requires an idle outermost connection')


def _preview_attempt(token, claims, organization_header, data, service=preview):
    _preview_connection_ready()
    with transaction.atomic(durable=True):
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            cursor.execute("SELECT set_config('request.jwt.claims',%s,true)",
                           [json.dumps(claims,separators=(',',':'),sort_keys=True)])
            cursor.execute('SET LOCAL ROLE authenticated')
        tenant = resolve_tenant_context(MembershipRepository().list_active_for_user(token.user_id),
                                        organization_header)
        enforce_owner_mfa(tenant,token.aal)
        if tenant.active_organization.role not in ('OWNER','ESTIMATOR'):
            raise PricingError('pricing_permission_denied')
        attempt_data = {**data,'_actor_id':token.user_id,'_actor_email':token.email}
        with commercial_backend():
            output = service(tenant.active_organization.organization_id,tenant,attempt_data)
    return output


def _database_sqlstate(error):
    return getattr(error.__cause__,'sqlstate',None)


def _preview_with_retry(token, claims, organization_header, data, service=preview):
    for attempt in range(3):
        try:
            return _preview_attempt(token,claims,organization_header,data,service)
        except DatabaseError as error:
            if _database_sqlstate(error) not in ('40001','40P01') or attempt==2:
                raise
    raise AssertionError('unreachable preview retry state')


def price_response(value):
    # Each line carries its selling detail (unit price authority, quantity,
    # applied discount) so the decision surface never divides a line total
    # back into a unit price itself. Operations stored before the detail
    # existed simply omit it.
    detail = {entry['position_index']:entry for entry in value.get('line_detail') or []}
    return {**{key:item for key,item in value.items() if key != 'line_detail'},
            'lines':[{**detail.get(index,{}),'position_index':index,'line_net':str(amount)}
                             for index,amount in value['lines']],
            'extras':value.get('extras') or [],'extras_net':str(value.get('extras_net') or '0'),
            'project_net':str(value['project_net']),'project_tax':str(value['project_tax']),
            'project_gross':str(value['project_gross'])}


class AdminView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_admin_list',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   responses={200:AdminResponseSerializer,**ERRORS},tags=['pricing'])
    def get(self,request,resource):
        allowed = ('OWNER','WORKSHOP_MANAGER') if resource in ('cost-lists','cost-items') else ('OWNER',)
        with scope(request,allowed) as (_,_,org):
            output = admin_list(resource,org)
        return Response(json.loads(json_text({'items':output})))

    @extend_schema(operation_id='pricing_admin_write',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=AdminWriteSerializer,responses={200:AdminResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request,resource):
        data = validate(AdminWriteSerializer,request.data)
        if resource not in RESOURCE_SERIALIZERS:
            raise contract_error(404,'unknown_resource','Configuración no disponible.')
        values = validate(RESOURCE_SERIALIZERS[resource],data['values'])
        with scope(request) as (_,_,org):
            output = admin_write(resource,org,values,data['reason'],data.get('id'))
        return Response(json.loads(json_text({'items':[output]})))


class PreviewView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_preview',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=PriceRequestSerializer,responses={200:PriceResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request):
        data = validate(PriceRequestSerializer,request.data)
        token = verified_request_token(request)
        claims = dict(token.claims)
        organization_header = request.headers.get('X-Organization-ID')
        with public_pricing_errors():
            output = _preview_with_retry(token,claims,organization_header,data)
        return Response(price_response(output))


class DesignBatchPreviewView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_design_batch_preview',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=DesignBatchPreviewRequestSerializer,
                   responses={200:DesignBatchPreviewResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request):
        data = validate(DesignBatchPreviewRequestSerializer,request.data)
        token = verified_request_token(request)
        claims = dict(token.claims)
        organization_header = request.headers.get('X-Organization-ID')
        with public_pricing_errors():
            output = _preview_with_retry(token,claims,organization_header,data,design_batch_preview)
        return Response(json.loads(json_text(output)))


class ApplyView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_apply',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=ApplySerializer,responses={200:PriceResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request,operation_id):
        data = validate(ApplySerializer,request.data)
        with scope(request,('OWNER','ESTIMATOR')) as (token,tenant,org):
            with commercial_backend():
                output = apply_operation(org,token.user_id,tenant.active_organization.role,
                                         operation_id,**data)
        return Response(price_response(output))


class WithdrawView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_withdraw',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=WithdrawSerializer,responses={200:PriceResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request,operation_id):
        data = validate(WithdrawSerializer,request.data)
        with scope(request,('OWNER','ESTIMATOR')) as (token,tenant,org):
            with commercial_backend():
                output = withdraw_operation(org,token.user_id,tenant.active_organization.role,
                                            operation_id,**data)
        return Response(price_response(output))


class OperationsView(APIView):
    @extend_schema(operation_id='pricing_operations',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   responses={200:PriceResponseSerializer(many=True),**ERRORS},tags=['pricing'])
    def get(self,request):
        with scope(request,('OWNER','ESTIMATOR')) as (token,tenant,org):
            with commercial_backend():
                condition = '' if tenant.active_organization.role=='OWNER' else ' AND operation.requested_by=%s'
                parameters = [org] if not condition else [org,token.user_id]
                result = rows('SELECT operation.*,project.code AS project_code,project.name AS project_name,'
                              'project.client_name AS client_name '
                              'FROM public.pricing_operations operation '
                              'JOIN public.projects project ON project.id=operation.project_id '
                              'AND project.org_id=operation.org_id '
                              'WHERE operation.org_id=%s'+condition+
                              ' ORDER BY operation.created_at DESC,operation.id LIMIT 100',parameters)
                output = [price_response(operation_public(item)) for item in result]
        return Response(output)


class DraftView(APIView):
    parser_classes = [DecimalJSONParser]

    @extend_schema(operation_id='pricing_create_draft',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=DraftProjectSerializer,responses={201:DraftResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request):
        data = validate(DraftProjectSerializer,request.data)
        with scope(request,('OWNER','ESTIMATOR')) as (token,_,org):
            audit_reason(data['reason'])
            project = one('INSERT INTO public.projects(org_id,code,name,client_name,created_by) '
                          'VALUES(%s,%s,%s,%s,%s) RETURNING id',
                          [org,data['code'],data['name'],data['client_name'],token.user_id])
            for position in data['positions']:
                try:
                    typology = derive_typology(position['parametric_tree'])
                except ValueError as error:
                    raise contract_error(400,'typology_derivation_failed',
                                         'La apertura o división no permite determinar la tipología comercial.') from error
                if position['typology'] != typology:
                    raise contract_error(400,'typology_mismatch',
                                         'La tipología enviada no coincide con el diseño.')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT private.reserve_catalog_authority(%s,%s)', [position['system_id'],org])
                params = SystemParamsRepository().load_visible(position['system_id'],org)
                arguments = {key:position[key] for key in ('parametric_tree','nominal_width_mm','nominal_height_mm','color')}
                result = calculate_from_api(**arguments,params=params)
                one('INSERT INTO public.project_positions(project_id,org_id,position_index,quantity,typology,'
                    'system_id,width_mm,height_mm,parametric_tree,bom_snapshot,color_interior,color_exterior) '
                    'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s) RETURNING id',
                    [project['id'],org,position['position_index'],position['quantity'],typology,
                     position['system_id'],position['nominal_width_mm'],position['nominal_height_mm'],
                     json_text(position['parametric_tree']),result.model_dump_json(),position['color'],position['color']])
        return Response({'id':str(project['id'])},status=201)


class ImportView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(operation_id='pricing_import_xlsx',parameters=[ACTIVE_ORGANIZATION_HEADER],
                   request=ImportRequestSerializer,
                   responses={200:AdminResponseSerializer,**ERRORS},tags=['pricing'])
    def post(self,request):
        with scope(request) as (_,_,org):
            data = validate(ImportRequestSerializer,request.data)
            upload = data['file']
            parsed = parse_xlsx(upload.read(5*1024*1024+1),data['mapping'],data['decimal_separator'])
            output = import_rows(org,data['cost_list_id'],parsed,data['reason'],data['apply'])
        return Response(json.loads(json_text({'items':output})))
