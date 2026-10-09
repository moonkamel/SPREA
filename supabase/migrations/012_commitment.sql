-- 12-month commitment of the subscriptions taken from October 2026: end of
-- the commitment, copied from Stripe (subscription start + metadata
-- commitment_months) by the webhook. Null: no commitment.
alter table public.profiles add column if not exists subscription_commitment_end timestamptz;
alter table public.organizations add column if not exists subscription_commitment_end timestamptz;
