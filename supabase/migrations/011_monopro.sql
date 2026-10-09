-- Whole buildings held by a single owner (monopropriétés), from the BDNB open
-- data (CSTB, Licence Ouverte 2.0): at least 3 dwellings, not registered as a
-- copropriété, not social housing, not owned by a public body. Loaded per
-- department by .github/workflows/monopro-import.yml
-- (scripts/monopro/import_bdnb.py). Backend access only (RLS, no policy).

-- Owners: companies only (personnes morales of the land registry). The
-- identity of private owners is not public and is not stored.
create table if not exists public.monopro_owners (
    siren text primary key,
    name text,
    legal_form text,                       -- SCI, SAS, SARL...
    postcode text,                         -- registered office
    city text,
    imported_on date not null default current_date
);

create table if not exists public.monopro_buildings (
    id text primary key,                   -- BDNB batiment_groupe_id
    dep text not null,
    insee text,
    address text,
    lat double precision not null,
    lon double precision not null,
    nb_log integer not null,               -- dwellings (land registry)
    levels integer,
    year_built integer,
    owner_siren text,                      -- null: owner not identified (private person most likely)
    owner_share real,                      -- units held by the owner / dwellings
    dpe_label text,                        -- representative DPE of the building
    dpe_date date,
    dpe_count integer,                     -- DPE published for its dwellings
    dpe_fg integer,                        -- of which F or G
    last_sale_date date,                   -- last sale (DVF) involving the building
    last_sale_price bigint,
    last_sale_units integer,
    imported_on date not null default current_date
);

create index if not exists monopro_buildings_lat_lon on public.monopro_buildings (lat, lon);
create index if not exists monopro_buildings_owner on public.monopro_buildings (owner_siren);
create index if not exists monopro_buildings_dep on public.monopro_buildings (dep, imported_on);

alter table public.monopro_owners enable row level security;
alter table public.monopro_buildings enable row level security;
