-- P11 follow-up: emit_dte seals the rendered tributario PDF into storage and
-- records its object key + sha on the DTE row (sii.py::_seal_repr). The repr_*
-- columns were added by 20261208_dte_tributario.sql but 20261016's grant only
-- covers SELECT, INSERT — the seal UPDATE hits SQLSTATE 42501 and the request
-- surfaces as a 409. The failure was latent: the PDF417 encode crashed first.
GRANT UPDATE (repr_storage_object_key, repr_file_sha256)
    ON public.project_dtes TO documentary_backend;
