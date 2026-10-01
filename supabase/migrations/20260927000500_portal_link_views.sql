-- Proposal view tracking: a shared link that the client opens is the sales
-- signal the estimator acts on ("opened twice today" → call them now).
-- Counters live on the link row; the portal role's existing scoped UPDATE
-- policy already covers the write.

ALTER TABLE public.customer_approvals
    ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0
        CHECK (view_count >= 0),
    ADD COLUMN first_viewed_at TIMESTAMPTZ,
    ADD COLUMN last_viewed_at TIMESTAMPTZ;
