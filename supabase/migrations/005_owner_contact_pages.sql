-- Owner contact pages: an agent sends a letter with a QR code to a dwelling;
-- the owner opens /l/<code>, sees the simulation of the dwelling and may ask
-- to be called back. The agent is the controller of these requests; SPREA
-- stores them on its behalf (processor). Backend access only (RLS, no policy).

create table if not exists public.agent_pages (
    user_id uuid primary key references auth.users (id) on delete cascade,
    agency_name text not null,
    agent_name text,
    phone text,
    email text,
    updated_at timestamptz not null default now()
);

create table if not exists public.prospect_links (
    code text primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    dpe_number text not null,
    address text not null,
    label text,
    created_at timestamptz not null default now(),
    visits integer not null default 0,
    last_visit_at timestamptz,
    unique (user_id, dpe_number)
);

create table if not exists public.leads (
    id uuid primary key default gen_random_uuid(),
    code text not null references public.prospect_links (code) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    phone text,
    email text,
    message text,
    consent_text text not null,
    consent_at timestamptz not null default now(),
    status text not null default 'new' check (status in ('new', 'contacted', 'closed')),
    created_at timestamptz not null default now()
);

create index if not exists leads_user_created_idx on public.leads (user_id, created_at desc);

alter table public.agent_pages enable row level security;
alter table public.prospect_links enable row level security;
alter table public.leads enable row level security;
