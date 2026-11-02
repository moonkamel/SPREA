-- Access offered by SPREA (founder, partner), without a subscription; set
-- by hand in the database, never by the API
alter table public.profiles add column if not exists free_access boolean not null default false;
