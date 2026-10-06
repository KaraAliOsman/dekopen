-- P09 — Canal del enlace de aprobación: EMAIL (rota en cada re-envío) vs
-- DOCUMENT (vive en el QR sellado dentro del PDF DOC-01). El documento es
-- evidencia inmutable: su QR tiene que seguir resolviendo aunque el correo
-- rote, así que la revocación por re-share solo toca los enlaces de email.
ALTER TABLE public.customer_approvals
    ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'EMAIL'
        CONSTRAINT customer_approvals_channel_values
        CHECK (channel IN ('EMAIL', 'DOCUMENT'));

COMMENT ON COLUMN public.customer_approvals.channel IS
    'EMAIL: enlace enviado por correo — se revoca al compartir de nuevo. '
    'DOCUMENT: enlace impreso en el DOC-01 — solo muere por decisión, '
    'revocación manual o expiración.';
