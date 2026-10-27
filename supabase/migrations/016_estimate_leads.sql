-- Requests to be called back left by owners on the public estimator
-- (/estimation), with their consent, routed to the subscriber whose alert
-- zone covers the address (assigned_user_id), or kept unassigned.
create table if not exists public.estimate_leads (
    id uuid primary key default gen_random_uuid(),
    address text not null,
    postcode text,
    insee text not null,
    city text,
    lat double precision,
    lon double precision,
    kind text not null check (kind in ('appartement', 'maison')),
    surface real not null,
    details jsonb not null default '{}'::jsonb,
    value integer,
    low integer,
    high integer,
    name text not null,
    phone text,
    email text,
    project text not null check (project in ('vendre_3m', 'vendre_12m', 'reflexion', 'curiosite')),
    consent_text text not null,
    consent_at timestamptz not null default now(),
    source text,
    assigned_user_id uuid references auth.users (id) on delete set null,
    status text not null default 'new' check (status in ('new', 'contacted', 'closed')),
    created_at timestamptz not null default now()
);

create index if not exists estimate_leads_assigned_idx on public.estimate_leads (assigned_user_id, created_at desc);
create index if not exists estimate_leads_insee_idx on public.estimate_leads (insee, created_at desc);

-- Server-side access only (service role), like the other lead tables
alter table public.estimate_leads enable row level security;
