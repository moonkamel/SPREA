-- Minimal purchase records kept after an account is deleted: proof of the
-- accepted CGV and payment references (no email, address or simulation).
-- Retention: 5 years after deletion (limitation period), then purge, e.g.
--   delete from public.purchase_archive where account_deleted_at < now() - interval '5 years';
-- (can be scheduled with the pg_cron extension).

create table if not exists public.purchase_archive (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('report', 'subscription')),
    stripe_customer_id text,
    stripe_session_id text unique,
    subscription_id text,
    terms_version text,
    terms_accepted_at timestamptz,
    amount_paid integer,
    currency text,
    paid_at timestamptz,
    account_deleted_at timestamptz not null default now()
);

alter table public.purchase_archive enable row level security;
