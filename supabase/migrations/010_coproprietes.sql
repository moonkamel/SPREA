-- Copropriétés: the public national registry (RNIC, ANAH open data, Licence
-- Ouverte), reduced to what the building sheet shows. Loaded every month by
-- .github/workflows/copro-import.yml (scripts/copro/import_rnic.py).
-- Backend access only (RLS, no policy).

create table if not exists public.coproprietes (
    immat text primary key,                -- numéro d'immatriculation
    name text,                             -- nom d'usage
    address text,
    postcode text,
    insee text,                            -- commune (arrondissement for Paris, Lyon, Marseille)
    lat double precision,
    lon double precision,
    lots_total integer,
    lots_main integer,                     -- lots d'habitation, de bureaux ou de commerces
    lots_housing integer,
    lots_parking integer,
    period text,                           -- période de construction (AVANT_1949, DE_1949_A_1960…)
    rules_date date,                       -- date du règlement de copropriété
    syndic_type text,                      -- professionnel, bénévole, non connu
    syndic_name text,                      -- professional syndics only
    syndic_siret text,
    mandate_end date,
    aided boolean,                         -- copropriété aidée
    in_pdp boolean,                        -- plan de sauvegarde / dispositif public
    qpv text,                              -- quartier prioritaire (2024)
    registry_updated date,
    imported_on date not null default current_date
);

create index if not exists coproprietes_lat_lon on public.coproprietes (lat, lon);

alter table public.coproprietes enable row level security;
