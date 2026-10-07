"""Ajustes por dominio — la lectura y escritura agrupada que la página de
secciones consume. Cada sección valida y escribe lo suyo; la composición
`settings_snapshot` es el payload único de `GET /organization/settings/`.

Las escrituras reusan los caminos ya probados: la fila de org va por
`org_branding._save_branding`/`documentary_backend` (misma política RLS que
branding) y las reglas comerciales por `pricing.repository.admin_write`
(`pricing_backend` + auditoría en price_audit_logs)."""

from __future__ import annotations


from django.db import transaction

from authentication.errors import contract_error
from documents.repository import documentary_backend
from pricing.repository import admin_write, commercial_backend, one, rows
from projects import org_branding
from rut import rut_mod11_valid

_ORG_FIELDS = (
    "name, tax_id, commercial_name, giro, brand_address, brand_phone,"
    " brand_email, brand_color, brand_logo_key, currency, country,"
    " doc_paper_size, doc_dekopen_credit, doc_terms, doc_validity_days,"
    " vano_spread_tolerance_mm, remnant_alert_days, workshop_label_format,"
    " require_totp, created_at"
)

_RULE_FIELDS = (
    "tax_rate_pct",
    "default_margin_pct",
    "margin_min_pct",
    "margin_max_pct",
    "discount_approval_threshold_pct",
)

_CURRENCIES = ("CLP", "USD", "UF")


def _organization(org_id) -> dict:
    return one(
        f"SELECT {_ORG_FIELDS} FROM public.tenancy_organizations WHERE id=%s",
        [str(org_id)],
        "organization_not_found",
    )


def _rules(org_id) -> dict:
    found = rows(
        "SELECT id,tax_rate_pct,default_margin_pct,margin_min_pct,margin_max_pct,"
        "discount_approval_threshold_pct,pricing_mode FROM public.pricing_rules "
        "WHERE org_id=%s",
        [str(org_id)],
    )
    return found[0] if found else {}


def settings_snapshot(org_id) -> dict:
    with documentary_backend():
        org = _organization(org_id)
    with commercial_backend():
        rules = _rules(org_id)
    terms = org.get("doc_terms") if isinstance(org.get("doc_terms"), dict) else {}
    return {
        "company": {
            "name": org.get("name") or "",
            "tax_id": org.get("tax_id") or "",
            "commercial_name": org.get("commercial_name") or "",
            "giro": org.get("giro") or "",
            "brand_address": org.get("brand_address") or "",
            "brand_phone": org.get("brand_phone") or "",
            "brand_email": org.get("brand_email") or "",
            "brand_color": org.get("brand_color") or "",
            "has_logo": bool(org.get("brand_logo_key")),
        },
        "commercial": {
            "currency": org.get("currency") or "CLP",
            "tax_rate_pct": str(rules.get("tax_rate_pct", "")) if rules else "",
            "default_margin_pct": (
                str(rules.get("default_margin_pct", "")) if rules else ""
            ),
            "margin_min_pct": str(rules.get("margin_min_pct", "")) if rules else "",
            "margin_max_pct": str(rules.get("margin_max_pct", "")) if rules else "",
            "discount_approval_threshold_pct": (
                str(rules.get("discount_approval_threshold_pct", "")) if rules else ""
            ),
            "rules_configured": bool(rules),
            "doc_validity_days": int(org.get("doc_validity_days") or 15),
        },
        "documents": {
            "doc_paper_size": org.get("doc_paper_size") or "LETTER",
            "doc_terms": org_branding._doc_terms(terms),
            "doc_dekopen_credit": bool(org.get("doc_dekopen_credit")),
        },
        "production": {
            "vano_spread_tolerance_mm": (
                None
                if org.get("vano_spread_tolerance_mm") is None
                else str(org["vano_spread_tolerance_mm"])
            ),
            "remnant_alert_days": int(org.get("remnant_alert_days") or 30),
            "workshop_label_format": org.get("workshop_label_format") or "GRID",
        },
        "security": {"require_totp": bool(org.get("require_totp"))},
        "updated_at": None,
    }


def save_company(org_id, data: dict) -> dict:
    """Empresa: razón social, RUT legal (módulo 11 como en clientes),
    identidad de marca y datos de contacto que los documentos imprimen."""
    payload = {}
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            raise contract_error(
                400, "organization_name_invalid", "La razón social es obligatoria."
            )
        payload["name"] = name[:255]
    if "tax_id" in data:
        rut = str(data.get("tax_id") or "").strip()
        if rut and not rut_mod11_valid(rut):
            raise contract_error(
                400, "organization_tax_id_invalid", "El RUT de la empresa no es válido."
            )
        payload["tax_id"] = rut or None
    for field in (
        "commercial_name",
        "giro",
        "brand_address",
        "brand_phone",
        "brand_email",
        "brand_color",
    ):
        if field in data:
            payload[field] = data.get(field)
    with transaction.atomic(), documentary_backend():
        updated = org_branding._save_branding(org_id=org_id, data=payload)
        row = _organization(org_id)
    return {"company": _company_public(row), "branding": updated}


def save_commercial(org_id, data: dict) -> dict:
    """Comercial: moneda y vigencia/condiciones viven en la fila de org;
    IVA, margen y umbral de descuento en pricing_rules (con auditoría)."""
    org_payload = {}
    if "currency" in data:
        currency = str(data.get("currency") or "").strip().upper()
        if currency not in _CURRENCIES:
            raise contract_error(
                400, "currency_invalid", "La moneda debe ser CLP, USD o UF."
            )
        org_payload["currency"] = currency
    if "doc_validity_days" in data:
        org_payload["doc_validity_days"] = data.get("doc_validity_days")
    # null = mantener el valor actual: las columnas de margen son NOT NULL, así
    # que "limpiar" no existe — un None nunca debe llegar a admin_write.
    rule_payload = {
        key: data[key]
        for key in _RULE_FIELDS
        if key in data and data[key] is not None
    }
    if rule_payload:
        for key in ("tax_rate_pct", "discount_approval_threshold_pct"):
            if key in rule_payload:
                value = _fraction(rule_payload[key], key)
                if not 0 < value <= 1:
                    raise contract_error(
                        400,
                        "commercial_rule_invalid",
                        f"{key} debe ser una fracción entre 0 y 1.",
                    )
        for key in ("default_margin_pct", "margin_min_pct", "margin_max_pct"):
            if key in rule_payload and rule_payload[key] is not None:
                _fraction(rule_payload[key], key)
        if "margin_min_pct" in rule_payload or "margin_max_pct" in rule_payload:
            with commercial_backend():
                current = _rules(org_id)
            lower = rule_payload.get("margin_min_pct", current.get("margin_min_pct"))
            upper = rule_payload.get("margin_max_pct", current.get("margin_max_pct"))
            if lower is not None and upper is not None:
                if _fraction(lower, "margin_min_pct") > _fraction(upper, "margin_max_pct"):
                    raise contract_error(
                        400,
                        "margin_band_invalid",
                        "El margen mínimo no puede superar al máximo.",
                    )
        with transaction.atomic(), commercial_backend():
            admin_write(
                "rules", org_id, rule_payload, "ajustes_comercial", _rules(org_id)["id"]
            )
    if org_payload:
        with transaction.atomic(), documentary_backend():
            org_branding._save_branding(org_id=org_id, data=org_payload)
    return settings_snapshot(org_id)["commercial"]


def save_documents(org_id, data: dict) -> dict:
    payload = {
        key: data.get(key)
        for key in ("doc_paper_size", "doc_dekopen_credit", "doc_terms")
        if key in data
    }
    with transaction.atomic(), documentary_backend():
        org_branding._save_branding(org_id=org_id, data=payload)
    return settings_snapshot(org_id)["documents"]


def save_production(org_id, data: dict) -> dict:
    payload = {
        key: data.get(key)
        for key in (
            "vano_spread_tolerance_mm",
            "remnant_alert_days",
            "workshop_label_format",
        )
        if key in data
    }
    with transaction.atomic(), documentary_backend():
        org_branding._save_branding(org_id=org_id, data=payload)
    return settings_snapshot(org_id)["production"]


def save_security(org_id, data: dict) -> dict:
    with transaction.atomic(), documentary_backend():
        row = one(
            "UPDATE public.tenancy_organizations SET require_totp=%s,"
            " updated_at=now() WHERE id=%s RETURNING require_totp",
            [bool(data.get("require_totp")), str(org_id)],
            "organization_not_found",
        )
    return {"require_totp": bool(row["require_totp"])}


def numbering(org_id) -> dict:
    """Prefijos y siguiente número — solo lectura. Los folios salen del
    contador real en cada emisión; aquí se anticipa lo que toca, nunca se
    reserva ni se salta."""
    with documentary_backend():
        counts = one(
            "SELECT"
            " (SELECT COUNT(*) FROM public.projects WHERE org_id=%s) AS projects,\n"
            " (SELECT COUNT(*) FROM public.orders WHERE org_id=%s AND order_type <> 'WORKSHOP_OT') AS orders,\n"
            " (SELECT COUNT(*) FROM public.orders WHERE org_id=%s AND order_type = 'WORKSHOP_OT') AS workshop_orders,\n"
            " (SELECT COUNT(*) FROM public.inventory_remnants WHERE org_id=%s) AS remnants,\n"
            " (SELECT COUNT(*) FROM public.order_receipts WHERE org_id=%s) AS receipts,\n"
            " (SELECT COUNT(*) FROM public.dispatch_notes WHERE org_id=%s) AS dispatch_notes,\n"
            " (SELECT COUNT(*) FROM public.project_invoices WHERE org_id=%s) AS invoices,\n"
            " (SELECT COUNT(*) FROM public.payment_receipts WHERE org_id=%s) AS payment_receipts,\n"
            " (SELECT COUNT(*) FROM public.project_credit_notes WHERE org_id=%s) AS credit_notes",
            [str(org_id)] * 9,
            "numbering_unavailable",
        )
    return {
        "items": [
            {"kind": "projects", "prefix": "P-", "next": int(counts["projects"]) + 1,
             "pattern": "P-000123"},
            {"kind": "workshop_orders", "prefix": "OT-",
             "next": int(counts["workshop_orders"]) + 1,
             "pattern": "OT-<proyecto>-<revisión>-<nn>"},
            {"kind": "purchase_orders", "prefix": "OC-",
             "next": int(counts["orders"]) + 1, "pattern": "OC-000123"},
            {"kind": "remnants", "prefix": "RT-",
             "next": int(counts["remnants"]) + 1, "pattern": "RT-000123"},
            {"kind": "order_receipts", "prefix": "REC-",
             "next": int(counts["receipts"]) + 1, "pattern": "REC-000123"},
            {"kind": "dispatch_notes", "prefix": "GD-",
             "next": int(counts["dispatch_notes"]) + 1, "pattern": "GD-0123"},
            {"kind": "invoices", "prefix": "FAC-",
             "next": int(counts["invoices"]) + 1, "pattern": "FAC-0123"},
            {"kind": "payment_receipts", "prefix": "RC-",
             "next": int(counts["payment_receipts"]) + 1, "pattern": "RC-0123"},
            {"kind": "credit_notes", "prefix": "NC-",
             "next": int(counts["credit_notes"]) + 1, "pattern": "NC-0123"},
        ],
        "read_only": True,
    }


def _integrations(org_id) -> dict:
    """Estado declarado de cada integración diferida — nunca un secreto.
    Los pasos citan las secciones reales de docs/operations/ACTIVACION.md."""
    from mail import service as mail_service
    from projects import payment_links, sii_envio

    flow = payment_links.get_integration(org_id=org_id)
    sii = sii_envio.integration_state(org_id=org_id)
    mail = mail_service.tray_status(org_id=org_id)
    try:
        from ai_gateway.status import provider_status

        ai = provider_status()
    except Exception:
        ai = {"mode": None}
    return {
        "items": [
            {
                "key": "flow",
                "name": "Flow (cobros)",
                "state": "configured" if flow.get("configured") else "not_configured",
                "detail": (
                    f"Modo {flow.get('provider_mode')}"
                    + (f" · {flow.get('api_url')}" if flow.get("api_url") else "")
                ),
                "activation": "ACTIVACION.md › Flow",
            },
            {
                "key": "sii",
                "name": "SII / DTE",
                "state": (
                    "configured"
                    if sii.get("certified")
                    else "partial"
                    if sii.get("certificate") or sii.get("caf_available")
                    else "not_configured"
                ),
                "detail": (
                    f"Adaptador {sii.get('adapter')} · "
                    f"certificado {'vigente' if sii.get('certificate') else 'pendiente'} · "
                    f"CAF {'disponible' if sii.get('caf_available') else 'sin folios'}"
                ),
                "activation": "ACTIVACION.md › SII / DTE",
            },
            {
                "key": "mail",
                "name": "Correo",
                "state": (
                    "configured"
                    if mail.get("provider") not in (None, "sandbox")
                    else "not_configured"
                ),
                "detail": f"Proveedor {mail.get('provider') or 'sandbox'}",
                "activation": "ACTIVACION.md › Correo con dominio propio",
            },
            {
                "key": "ai",
                "name": "Proveedor de IA",
                "state": (
                    "configured" if ai.get("mode") and ai.get("mode") != "mock"
                    else "partial" if ai.get("mode") == "mock"
                    else "not_configured"
                ),
                "detail": f"Modo {ai.get('mode') or '—'}",
                "activation": "ACTIVACION.md › Proveedor de IA",
            },
            {
                "key": "webhooks",
                "name": "Webhooks",
                "state": "not_configured",
                "detail": "Endpoints y firma pendientes de ambiente productivo",
                "activation": "ACTIVACION.md › Webhooks productivos",
            },
            {
                "key": "railway",
                "name": "Hosting (Railway)",
                "state": "not_configured",
                "detail": "Despliegue por runbook; este programa corre local",
                "activation": "ACTIVACION.md › Railway / hosting",
            },
        ],
        "runbook": "docs/operations/ACTIVACION.md",
    }


def integrations(org_id) -> dict:
    return _integrations(org_id)


def list_members(org_id) -> dict:
    members = rows(
        "SELECT * FROM private.org_members(%s::uuid)",
        [str(org_id)],
    )
    invitations = rows(
        "SELECT id,email,role,status,invited_label,created_at "
        "FROM public.org_invitations WHERE org_id=%s "
        "ORDER BY created_at DESC, id DESC LIMIT 100",
        [str(org_id)],
    )
    return {
        "members": [
            {
                "membership_id": str(item["membership_id"]),
                "user_id": str(item["user_id"]),
                "email": item["email"],
                "role": item["role"],
                "is_active": item["is_active"],
                "totp_enabled": item["totp_enabled"],
                "created_at": item["created_at"].isoformat(),
            }
            for item in members
        ],
        "invitations": [
            {
                "id": str(item["id"]),
                "email": item["email"],
                "role": item["role"],
                "status": item["status"],
                "invited_label": item["invited_label"],
                "created_at": item["created_at"].isoformat(),
            }
            for item in invitations
        ],
    }


def invite_member(org_id, email: str, role: str, actor_id, actor_label) -> dict:
    email = (email or "").strip().lower()
    if "@" not in email or len(email) > 255:
        raise contract_error(400, "invitation_email_invalid", "Correo de invitación inválido.")
    if role not in ("ESTIMATOR", "WORKSHOP_MANAGER", "OPERATOR", "INSTALLER"):
        raise contract_error(
            400,
            "invitation_role_invalid",
            "El rol invitado no puede ser OWNER — los dueños se nombran, no se invitan.",
        )
    with transaction.atomic():
        invitation = one(
            "INSERT INTO public.org_invitations(org_id,email,role,invited_by,invited_label) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            [str(org_id), email, role, str(actor_id), actor_label],
            "invitation_failed",
        )
        target = one(
            "SELECT private.user_id_by_email(%s) AS uid",
            [email],
            "invitation_user_lookup_failed",
        )["uid"]
        if target is not None:
            one(
                "SELECT private.claim_org_invitations(%s, %s::uuid) AS n",
                [email, str(target)],
                "invitation_claim_failed",
            )
        found = rows(
            "SELECT id,email,role,status,invited_label,created_at "
            "FROM public.org_invitations WHERE id=%s",
            [invitation["id"]],
        )
    row = found[0]
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "role": row["role"],
        "status": row["status"],
        "invited_label": row["invited_label"],
        "created_at": row["created_at"].isoformat(),
    }


def update_member(org_id, membership_id, data, actor_id) -> dict:
    members = rows(
        "SELECT * FROM private.org_members(%s::uuid)", [str(org_id)]
    )
    target = next(
        (item for item in members if str(item["membership_id"]) == str(membership_id)),
        None,
    )
    if target is None:
        raise contract_error(404, "membership_not_found", "La membresía no existe.")
    new_role = data.get("role", target["role"])
    new_active = bool(data.get("is_active", target["is_active"]))
    if str(target["user_id"]) == str(actor_id) and new_active is False:
        raise contract_error(
            409, "membership_self_deactivate", "No puedes desactivarte a ti mismo."
        )
    owners = [
        item
        for item in members
        if item["role"] == "OWNER" and item["is_active"]
    ]
    demotes_owner = (
        target["role"] == "OWNER" and (new_role != "OWNER" or not new_active)
    )
    if demotes_owner and len(owners) <= 1:
        raise contract_error(
            409,
            "membership_last_owner",
            "La organización necesita al menos un dueño activo.",
        )
    one(
        "SELECT private.set_membership(%s::uuid,%s::uuid,%s::public.org_role,%s)",
        [str(org_id), str(membership_id), new_role, new_active],
        "membership_update_failed",
    )
    refreshed = rows(
        "SELECT * FROM private.org_members(%s::uuid)", [str(org_id)]
    )
    return {
        "members": [
            {
                "membership_id": str(item["membership_id"]),
                "user_id": str(item["user_id"]),
                "email": item["email"],
                "role": item["role"],
                "is_active": item["is_active"],
                "totp_enabled": item["totp_enabled"],
                "created_at": item["created_at"].isoformat(),
            }
            for item in refreshed
        ]
    }


def claim_own_invitations(email: str, user_id) -> int:
    """Auto-reclamo al iniciar sesión: invitaciones pendientes del correo
    verificado se convierten en membresías activas."""
    if not email:
        return 0
    try:
        result = one(
            "SELECT private.claim_org_invitations(%s, %s::uuid) AS n",
            [email, str(user_id)],
            "invitation_claim_failed",
        )
        return int(result["n"] or 0)
    except Exception:
        return 0


def document_preview(org_id, draft: dict) -> str:
    """Momento de firma §8: vista previa real del papel. Compone la mini
    hoja DOC-01 con el mismo `_CSS` y `_brand_block` que imprime el PDF y
    el mismo markup `.terms` del render — cambios de marca o condiciones
    se ven al instante, antes de sellar nada."""
    from documents.renderers import _brand_block, _CSS_EMBEDDED

    org = get_branding(org_id=org_id)
    merged = dict(org)
    for key, value in draft.items():
        if value not in (None, ""):
            merged[key] = value
    terms = merged.get("doc_terms") if isinstance(merged.get("doc_terms"), dict) else {}
    term_labels = (
        ("plazo_entrega", "Plazo de entrega"),
        ("instalacion", "Instalación"),
        ("exclusiones", "Exclusiones"),
        ("garantia", "Garantía"),
        ("jurisdiccion", "Jurisdicción"),
    )
    legal_rows = "".join(
        f'<p><span class="tlabel">{_escape_html(label)}</span><br>'
        f"{_escape_html(str(terms[key_name]))}</p>"
        for key_name, label in term_labels
        if isinstance(terms.get(key_name), str) and terms[key_name].strip()
    )
    issuer_parts = [
        part
        for part in (
            merged.get("name"),
            f"RUT {merged.get('tax_id')}" if merged.get("tax_id") else "",
            merged.get("giro"),
            merged.get("brand_address"),
            merged.get("brand_phone"),
            merged.get("brand_email"),
        )
        if part
    ]
    footer = (
        '<div class="cover-foot">' + _escape_html(" \u00b7 ".join(issuer_parts)) + "</div>"
        if issuer_parts
        else ""
    )
    body = (
        '<div class="doc-preview-sheet"><div class="dochead">'
        f'<div class="cover-top">{_brand_block(merged)}'
        '<div class="cover-doc"><strong>Propuesta comercial</strong>'
        "COT-2026-0107<br>Revisión A \u00b7 07-10-2026</div></div>"
        '<p class="kicker">Preparado para</p>'
        '<h1 class="cover-client">Constructora Ejemplo Ltda.</h1>'
        '<p class="cover-project">Casa de muestra \u00b7 P-000000</p>'
        '<div class="cover-invest"><div class="inv-cell inv-total"><span>Total</span>'
        "<strong>$1.435.471</strong></div>"
        '<div class="inv-cell"><span>Plazo de entrega</span>'
        f"<strong>{_escape_html(str(terms.get('plazo_entrega') or '—'))}</strong></div>"
        '<div class="inv-cell"><span>Válida hasta</span><strong>22-10-2026</strong></div>'
        "</div>"
        + (f'<div class="terms">{legal_rows}</div>' if legal_rows else "")
        + footer
        + "</div></div>"
    )
    return f"<style>{_CSS_EMBEDDED}</style>{body}"


def _escape_html(value: str) -> str:
    from html import escape

    return escape(value)


def get_branding(org_id):
    return org_branding.get_branding(org_id=org_id)


def _fraction(value, key):
    from decimal import Decimal, InvalidOperation

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise contract_error(
            400, "commercial_rule_invalid", f"{key} debe ser numérico."
        ) from None
    return parsed


def _company_public(row: dict) -> dict:
    return {
        "name": row.get("name") or "",
        "tax_id": row.get("tax_id") or "",
        "commercial_name": row.get("commercial_name") or "",
        "giro": row.get("giro") or "",
        "brand_address": row.get("brand_address") or "",
        "brand_phone": row.get("brand_phone") or "",
        "brand_email": row.get("brand_email") or "",
        "brand_color": row.get("brand_color") or "",
        "has_logo": bool(row.get("brand_logo_key")),
    }
