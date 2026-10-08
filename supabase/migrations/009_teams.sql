-- Teams: agencies (Agence offer, billed per agent) and networks (Réseau offer,
-- contract on quote). A Solo subscription stays on the profile.
--
-- Access rule (api/accounts.py, is_pro): a user has access if their own
-- subscription is active, or if their organization's subscription, or the one
-- of its parent network, is active. Backend access only (RLS, no policy).
--
-- A network is created by SPREA after the quote is signed, for example:
--   insert into public.organizations (name, kind, seats, subscription_status)
--   values ('Réseau Exemple', 'reseau', 40, 'active') returning id;
--   insert into public.memberships (org_id, user_id, role) values ('<network id>', '<user id>', 'owner');
--   update public.organizations set parent_id = '<network id>' where id in ('<agency id>', ...);

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(name) between 2 and 120),
    kind text not null check (kind in ('agence', 'reseau')),
    -- Agency belonging to a network
    parent_id uuid references public.organizations (id) on delete set null,
    -- Number of users paid for (Stripe subscription quantity)
    seats integer not null default 2 check (seats between 1 and 5000),
    stripe_subscription_id text unique,
    subscription_status text,
    subscription_current_period_end timestamptz,
    created_at timestamptz not null default now()
);
create index if not exists organizations_parent_idx on public.organizations (parent_id);

-- One organization per user
create table if not exists public.memberships (
    user_id uuid primary key references public.profiles (id) on delete cascade,
    org_id uuid not null references public.organizations (id) on delete cascade,
    role text not null default 'agent' check (role in ('owner', 'admin', 'agent')),
    created_at timestamptz not null default now()
);
create index if not exists memberships_org_idx on public.memberships (org_id);

create table if not exists public.invitations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    email text not null,
    role text not null default 'agent' check (role in ('admin', 'agent')),
    -- SHA-256 of the token sent in the link: the token itself is never stored
    token_hash text not null unique,
    invited_by uuid references public.profiles (id) on delete set null,
    expires_at timestamptz not null,
    accepted_at timestamptz,
    created_at timestamptz not null default now(),
    unique (org_id, email)
);

alter table public.organizations enable row level security;
alter table public.memberships enable row level security;
alter table public.invitations enable row level security;

-- Invitations not accepted: deleted 30 days after they expire
select cron.schedule('purge-expired-invitations', '47 3 * * *',
    $$delete from public.invitations where accepted_at is null and expires_at < now() - interval '30 days'$$);
