-- DOC-001: the stamped document's fiscal identity travels on the PDF.
-- The composed "tributario" artifact (fiscal cover + sealed body) is itself
-- immutable evidence stored beside the DTE XML.

ALTER TABLE public.project_dtes
    ADD COLUMN repr_storage_object_key TEXT,
    ADD COLUMN repr_file_sha256 TEXT,
    ADD CONSTRAINT ck_dtes_repr_sha
        CHECK (repr_file_sha256 IS NULL OR repr_file_sha256 ~ '^[0-9a-f]{64}$');
