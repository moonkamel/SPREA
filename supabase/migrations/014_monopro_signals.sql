-- Sale signals of the companies owning whole buildings, read in the BODACC
-- (DILA open data) by scripts/monopro/signals.py (weekly workflow): score,
-- events (kind, date, link to the notice; no names), and the explanation
-- written by Claude when an agent opens the building sheet (summary, valid
-- while summary_key matches the events). Backend access only.
create table if not exists public.monopro_signals (
    siren text primary key,
    score integer not null,
    level text,                          -- fort, moyen, faible
    events jsonb not null default '[]',
    checked_on date not null,
    summary jsonb,
    summary_key text
);

alter table public.monopro_signals enable row level security;

-- Copied on the buildings, for the map filter and the order of the list
alter table public.monopro_buildings add column if not exists signal_score integer;
alter table public.monopro_buildings add column if not exists signal_level text;
create index if not exists monopro_buildings_signal on public.monopro_buildings (signal_score) where signal_score is not null;
