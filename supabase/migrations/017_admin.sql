-- SPREA's own team: sees every request of the public estimator (/admin),
-- set by hand in the database, never by the API
alter table public.profiles add column if not exists is_admin boolean not null default false;
