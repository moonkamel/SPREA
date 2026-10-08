-- DPE alerts: zones watched by Pro agents, and the new DPE found in them
-- (ADEME open data). Checked every morning by /api/cron/alerts (Vercel Cron).
-- Results are kept 6 months.

create table if not exists public.alert_zones (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    name text not null,
    lat double precision not null,
    lon double precision not null,
    radius_m integer not null check (radius_m between 200 and 3000),
    labels text not null default 'E,F,G',
    kind text check (kind in ('maison', 'appartement', 'immeuble')),
    email boolean not null default true,
    active boolean not null default true,
    last_checked_on date,
    created_at timestamptz not null default now()
);
create index if not exists alert_zones_user_idx on public.alert_zones (user_id);

create table if not exists public.alert_hits (
    id uuid primary key default gen_random_uuid(),
    zone_id uuid not null references public.alert_zones (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    dpe_number text not null,
    address text,
    label text,
    kind text,
    surface real,
    dpe_date date,
    received_on date,
    period text,
    detail text,
    created_at timestamptz not null default now(),
    unique (zone_id, dpe_number)
);
create index if not exists alert_hits_user_created_idx on public.alert_hits (user_id, created_at desc);

alter table public.alert_zones enable row level security;
alter table public.alert_hits enable row level security;

select cron.schedule('purge-alert-hits', '37 3 * * *',
    $$delete from public.alert_hits where created_at < now() - interval '6 months'$$);
