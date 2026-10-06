"""Correos transaccionales DEKOPEN — P25 marca.

Cinco plantillas: magic-link (GoTrue, vista previa), cotización enviada
(white-label cliente), aprobación recibida, pago registrado y OT
bloqueada (internas con marca DEKOPEN). Cada correo se materializa en
public.mail_messages antes de enviarse; el proveedor por defecto es
sandbox (registra sin entregar) y SMTP se activa por configuración.
"""
