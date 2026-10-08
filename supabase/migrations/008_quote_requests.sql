-- Quote requests for the Agence and Réseau offers (pricing page).
-- Only the backend (service key) reads and writes it: RLS without policy.

create table if not exists public.quote_requests (
    id uuid primary key default gen_random_uuid(),
    offer text not null check (offer in ('agence', 'reseau')),
    name text not null,
    company text not null,
    email text not null,
    phone text,
    agents integer not null check (agents between 1 and 5000),
    message text,
    status text not null default 'new' check (status in ('new', 'contacted', 'won', 'lost')),
    created_at timestamptz not null default now()
);

create index if not exists quote_requests_created_at on public.quote_requests (created_at desc);

alter table public.quote_requests enable row level security;

-- Prospects without follow-up: deleted after 3 years (privacy policy)
select cron.schedule('purge-quote-requests', '37 3 * * *',
    $$delete from public.quote_requests where created_at < now() - interval '3 years'$$);
