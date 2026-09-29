-- portal_quote() reads the live payment link under SET LOCAL ROLE
-- portal_backend; the table was never granted to it, so every public
-- proposal link returned 409 portal_transaction_rejected.
GRANT SELECT ON public.project_payment_links TO portal_backend;
