-- Proof that a user accepted the prospection map terms (CGV article 14):
-- one row per acceptance, never updated. Checked by the backend before any
-- address is returned. Archived in purchase_archive if the account is deleted.

create table if not exists public.terms_acceptances (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    scope text not null check (scope in ('prospection')),
    terms_version text not null,
    accepted_at timestamptz not null default now()
);

create index if not exists terms_acceptances_user_scope_idx
    on public.terms_acceptances (user_id, scope, accepted_at desc);

-- Backend only (service role), like the other tables
alter table public.terms_acceptances enable row level security;

alter table public.purchase_archive drop constraint if exists purchase_archive_kind_check;
alter table public.purchase_archive add constraint purchase_archive_kind_check
    check (kind in ('report', 'subscription', 'prospection_terms'));
