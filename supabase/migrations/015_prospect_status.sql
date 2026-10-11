-- Follow-up of prospected addresses (map, "Biens à fort potentiel"): where
-- the agent stands with each dwelling (letter sent, reminder, appointment,
-- mandate, not interested). Shared by the whole agency: scope is the
-- organization's id, or the user's own id outside an agency.

create table if not exists public.prospect_status (
    id uuid primary key default gen_random_uuid(),
    scope uuid not null,
    dpe_number text not null,
    status text not null check (status in ('courrier', 'relance', 'rendez_vous', 'mandat', 'ecarte')),
    address text,
    user_id uuid not null references auth.users (id) on delete cascade,
    updated_at timestamptz not null default now(),
    unique (scope, dpe_number)
);
create index if not exists prospect_status_scope_idx on public.prospect_status (scope);

alter table public.prospect_status enable row level security;
