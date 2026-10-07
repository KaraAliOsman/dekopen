"""Django settings for the SHOT-04 authentication and API boundary."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from corsheaders.defaults import default_headers
import structlog

from config.production import validate_production, is_production

validate_production(os.environ)
PRODUCTION = is_production()
REDIS_URL = os.environ.get('REDIS_URL', '')
RELEASE_SHA = os.environ.get('RAILWAY_GIT_COMMIT_SHA', os.environ.get('RELEASE_SHA', 'local'))

BASE_DIR = Path(__file__).resolve().parent.parent


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _database_config() -> dict[str, object]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }

    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use postgres or postgresql")
    options = dict(parse_qsl(parsed.query))
    config: dict[str, object] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 0,
    }
    if options:
        config["OPTIONS"] = options
    return config


SECRET_KEY = os.environ.get("SECRET_KEY", "shot-04-local-only-change-me")
DEBUG = os.environ.get("DEBUG", "False").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "authentication.apps.AuthenticationConfig",
    "engine_api.apps.EngineApiConfig",
    "documents.apps.DocumentsConfig",
    "purchasing.apps.PurchasingConfig",
    "jobs.apps.JobsConfig",
    "inventory.apps.InventoryConfig",
    "production.apps.ProductionConfig",
    "analytics.apps.AnalyticsConfig",
    "portal.apps.PortalConfig",
    "billing.apps.BillingConfig",
    "ai_gateway.apps.AiGatewayConfig",
    "ingest.apps.IngestConfig",
    "search.apps.SearchConfig",
    "automations.apps.AutomationsConfig",
    "mail.apps.MailConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "config.observability.RequestLogMiddleware",
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if PRODUCTION else None
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_REDIRECT_EXEMPT = [r'^health/live/$', r'^health/ready/$']
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SESSION_COOKIE_SECURE = PRODUCTION
CSRF_COOKIE_SECURE = PRODUCTION

DATABASES = {"default": _database_config()}

LANGUAGE_CODE = "en-us"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = _csv_env("CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173")
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = (*default_headers, "x-organization-id")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:25321").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_STORAGE_BUCKET_DOCS = os.environ.get("SUPABASE_STORAGE_BUCKET_DOCS", "documents")
if SUPABASE_STORAGE_BUCKET_DOCS != "documents":
    raise ValueError("SUPABASE_STORAGE_BUCKET_DOCS must be the immutable documents bucket")
SUPABASE_JWT_VERIFY_MODE = os.environ.get("SUPABASE_JWT_VERIFY_MODE", "auth_server")
SUPABASE_JWT_HTTP_TIMEOUT_SECONDS = 5

FLOW_API_URL = os.environ.get('FLOW_API_URL', 'https://sandbox.flow.cl/api')
FLOW_API_KEY = os.environ.get('FLOW_API_KEY', '')
FLOW_SECRET_KEY = os.environ.get('FLOW_SECRET_KEY', '')

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": ["config.throttling.ProductionRateThrottle"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "authentication.backends.SupabaseJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "authentication.errors.contract_exception_handler",
    "UNAUTHENTICATED_USER": None,
}

SPECTACULAR_SETTINGS = {
    "ENUM_NAME_OVERRIDES": {
        "CatalogProfileRoleEnum": ["FRAME", "SASH", "MULLION_V", "MULLION_H", "INVERSOR", "GLAZING_BEAD", "COUPLER", "ADDITIONAL", "THRESHOLD"],
        "RoleEnum": ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER"],
        "MembershipRoleEnum": [
            "OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "INSTALLER", "OPERATOR",
        ],
        "AiAgentHistoryRoleEnum": ["user", "agent"],
        # §IA3 — distinct 'mode' enums across AI serializers would otherwise
        # collide: the run mode, the per-route serving mode and the overall
        # provider mode are three different value sets.
        "AiAgentRunModeEnum": ["new", "resume"],
        "AiRouteModeEnum": ["live", "test", "unconfigured"],
        "AiProviderModeEnum": ["live", "test", "partial", "unconfigured"],
        "QcResultEnum": ["PASS", "FAIL"],
        "UnitEnum": ["kit"],
        "PurchaseUnitEnum": ["BAR"],
        "MaterialEnum": ["PVC", "ALUMINIUM"],
        "ExtraKindEnum": [
            "SILL", "FRAME_EXTENSION", "COVER_TRIM", "MOSQUITO_SCREEN",
            "VENTILATOR",
        ],
        "ServiceKindEnum": [
            "INSTALLATION", "SEALING", "REMOVAL", "SCAFFOLDING", "FREIGHT",
        ],
        "SystemFamilyEnum": [
            "CASEMENT", "SLIDING", "LIFT_SLIDE", "DOOR", "FACADE_FIXED",
        ],
        "EdgesEnum": ["top", "right", "bottom", "left"],
        "PieceOriginEnum": ["PRODUCT", "EXTRA"],
        "CutMaterialEnum": ["PVC", "ALUMINIUM", "STEEL"],
        "InspectorRuleIdEnum": [f"R{i:02d}" for i in range(1, 15)],
        "DrainFixRuleIdEnum": ["R07"],
        "ColorEnum": ["WHITE", "FOILED"],
        "WhiteColorEnum": ["WHITE"],
        "PaymentStatusEnum": ["NO_DEAL", "PENDING", "PARTIAL", "PAID"],
        "PaymentKindEnum": ["ANTICIPO", "PARCIAL", "SALDO"],
        "VerticalReferenceEnum": ["OUTER_TOP", "OUTER_BOTTOM", "LEAF_TOP", "LEAF_BOTTOM"],
        # P05 — sliding travel and door handedness share the LEFT/RIGHT
        # value set: keep one component name for both serializer fields.
        "SlidingTravelEnum": ["LEFT", "RIGHT"],
        "KitOpeningTypeEnum": [
            "AWNING", "BOTTOM_HUNG", "DOOR", "FALLEBA", "SLIDING", "TILT",
            "TILT_TURN", "TURN",
        ],
        "ImportOpeningTypeEnum": [
            "AWNING", "DOOR_ENTRY", "FIXED", "SLIDING_2L",
            "TILT_TURN_LEFT", "TILT_TURN_RIGHT", "TURN_LEFT", "TURN_RIGHT",
        ],
        # P11 — «aceptado con reparos» es un veredicto propio del SII, no un
        # detalle: lo lleva el enum del envío.
        "SiiEnvioStatusEnum": ["PENDING", "ACCEPTED", "OBSERVED", "REJECTED"],
        "OrderStatusEnum": [
            "DRAFT",
            "SENT",
            "PARTIALLY_RECEIVED",
            "FULFILLED",
            "CANCELLED",
        ],
        "StockKindEnum": ["BAR", "SHEET"],
        "SectionSourceEnum": ["POLYGON", "DXF_REFERENCE"],
        "BarAuthoritySourceEnum": ["PROFILE", "REINFORCEMENT"],
        "WorkCenterKindEnum": ["CUT", "ASSEMBLY", "GLAZING", "QC", "PACK"],
        # P18 — 'code' también choca entre reglas de montaje y separadores;
        # y los enums térmicos comparten nombres entre write/response.
        "MountingRuleCodeEnum": ["EN_VANO", "PREMARCO", "SOBRE_VANO", "TRASLAPADO", "RENOVACION"],
        "SpacerCodeEnum": ["ALUMINIUM", "WARM_EDGE"],
        "FrameMemberGroupEnum": ["ALL", "FRAME", "SASH", "MULLION", "COUPLER", "THRESHOLD"],
        "ThermalZoneEnum": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
        "ThermalUseEnum": ["RESIDENTIAL", "EQUIPMENT"],
        "ThermalOrientationEnum": ["N", "OP", "S", "OGT", "ROOF"],
        # 'orientation' chocaría con el OrientationEnum de montaje
        # (EXTERIOR_*) — nombre propio para el grupo cardinal OGUC.
        "OrientationGroupEnum": ["N", "OP", "S", "OGT"],
        "ThermalVerdictEnum": ["COMPLIES", "FAILS", "INSUFFICIENT_DATA", "NO_REQUIREMENT"],
        "UwStatusEnum": ["OK", "UNKNOWN"],
        "ThermalAlternativeKindEnum": ["GLASS", "SYSTEM"],
    },
    "TITLE": "Dekopen API",
    "DESCRIPTION": "Authenticated tenant and engine API boundary.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

structlog.configure(processors=[structlog.contextvars.merge_contextvars,
                               structlog.processors.TimeStamper(fmt='iso', utc=True),
                               structlog.processors.JSONRenderer()])

BILLING_CALLBACK_ORIGIN = os.environ.get('BILLING_CALLBACK_ORIGIN', '')
BILLING_FRONTEND_ORIGIN = os.environ.get('BILLING_FRONTEND_ORIGIN', '')
FLOW_MERCHANT_TIMEZONE = os.environ.get('FLOW_MERCHANT_TIMEZONE', '')
