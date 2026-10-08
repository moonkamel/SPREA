-- Record which version of the CGV a customer accepted, and when.

alter table public.reports
    add column if not exists terms_accepted_at timestamptz,
    add column if not exists terms_version text;

alter table public.profiles
    add column if not exists terms_accepted_at timestamptz,
    add column if not exists terms_version text;
