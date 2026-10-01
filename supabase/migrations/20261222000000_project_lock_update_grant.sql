-- FOR UPDATE on public.projects (the concurrency point confirm_delivery
-- locks before sealing the POD) requires an UPDATE privilege on at least one
-- column, on top of the FOR UPDATE row policy from
-- 20261221000200_project_lock_policy.sql. documentary_backend never writes
-- the row — status is granted solely so Postgres admits the lock; any actual
-- write still hits guard_commercial_write and the role-scoped WITH CHECK.
GRANT UPDATE (status) ON public.projects TO documentary_backend;
