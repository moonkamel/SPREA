-- Registered office and officers of the owning company, as last read from the
-- Annuaire des entreprises (api/monopro.py company_for): used when the Annuaire
-- refuses a request (429), so that a dossier never loses them.
alter table public.monopro_owners add column if not exists company jsonb;
alter table public.monopro_owners add column if not exists company_at timestamptz;
