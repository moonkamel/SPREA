-- Copropriété documents (minutes of general meetings, maintenance log,
-- pre-sale statement) read by Claude for a subscriber (api/copro_docs.py).
-- The files go to the private bucket copro-docs only for the time of the
-- analysis and are deleted right after; only the extracted summary is kept,
-- until the subscriber deletes it or their account. Backend access only.
create table if not exists public.copro_doc_analyses (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    address text,
    status text not null default 'uploading',    -- uploading, done, failed
    files jsonb not null default '[]',            -- [{name, size, type, path}]
    result jsonb,
    error text,
    model text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists copro_doc_analyses_user on public.copro_doc_analyses (user_id, created_at desc);

alter table public.copro_doc_analyses enable row level security;

-- Private bucket: uploads through signed URLs made by the backend
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('copro-docs', 'copro-docs', false, 20971520,
        array['application/pdf', 'image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;
