-- §17 OPERATOR role — a station-level identity distinct from WORKSHOP_MANAGER.
-- Operators log in to run step transitions and read production/inventory;
-- they cannot optimize plans, dispatch orders, or touch inventory writes.
ALTER TYPE public.org_role ADD VALUE IF NOT EXISTS 'OPERATOR';
