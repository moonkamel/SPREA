-- SPREA accounts & billing
-- Run once in the Supabase SQL editor (or with `supabase db push`).
-- Users themselves live in auth.users (Supabase Auth).

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    stripe_customer_id text unique,
    subscription_id text,
    -- Stripe subscription status: active, trialing, past_due, canceled, ...
    subscription_status text,
    subscription_current_period_end timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.reports (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    -- pending: waiting for payment, paid: bought alone, included: Pro subscription
    status text not null default 'pending' check (status in ('pending', 'paid', 'included')),
    address text not null,
    meta jsonb not null,
    -- SimulationInput (api/simulation.py): every figure is recomputed from it
    simulation jsonb not null,
    -- AI narrative, generated once at first download
    narrative text,
    stripe_session_id text unique,
    amount_paid integer,
    currency text,
    paid_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists reports_user_created_idx on public.reports (user_id, created_at desc);

create or replace function public.touch_updated_at() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at before update on public.profiles
    for each row execute procedure public.touch_updated_at();

-- Only the backend (service role) reads and writes these tables:
-- RLS enabled without any policy blocks every access through the anon key.
alter table public.profiles enable row level security;
alter table public.reports enable row level security;
