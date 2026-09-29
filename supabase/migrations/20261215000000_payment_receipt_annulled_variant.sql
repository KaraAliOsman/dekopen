-- Payment receipt annulled variant: a voided payment's sealed payload stays
-- immutable (payload_json + original storage_object_key/file_sha256 untouched);
-- the ANULADO-marked render is stored alongside and served on access.
ALTER TABLE public.payment_receipts
    ADD COLUMN IF NOT EXISTS annulled_object_key TEXT,
    ADD COLUMN IF NOT EXISTS annulled_file_sha256 TEXT
        CHECK (annulled_file_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN IF NOT EXISTS annulled_byte_size BIGINT
        CHECK (annulled_byte_size > 0);

GRANT UPDATE (annulled_object_key, annulled_file_sha256, annulled_byte_size)
    ON public.payment_receipts TO documentary_backend;
