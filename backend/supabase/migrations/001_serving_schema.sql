-- Atlas Konflik Sawit Riau — serving layer di Supabase
-- Jalankan di SQL Editor proyek Supabase (atau via CLI migration).

create extension if not exists pgcrypto;

-- Snapshot JSON/GeoJSON serving (satu baris per dataset)
create table if not exists public.serving_datasets (
  dataset text primary key,
  content_type text not null default 'application/json',
  payload jsonb not null,
  checksum text not null,
  byte_size integer not null default 0,
  source_path text,
  updated_at timestamptz not null default now(),
  synced_at timestamptz not null default now()
);

create index if not exists serving_datasets_updated_at_idx
  on public.serving_datasets (updated_at desc);

-- Riwayat sync berkala
create table if not exists public.sync_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running'
    check (status in ('running', 'success', 'partial', 'failed')),
  trigger_source text not null default 'manual',
  datasets_ok text[] not null default '{}',
  datasets_failed text[] not null default '{}',
  message text,
  meta jsonb not null default '{}'::jsonb
);

create index if not exists sync_runs_started_at_idx
  on public.sync_runs (started_at desc);

-- Meta ringkas untuk UI (mirror meta.json + status sync)
create or replace view public.serving_status as
select
  (select payload->>'updated_at' from public.serving_datasets where dataset = 'meta') as data_updated_at,
  (select synced_at from public.serving_datasets where dataset = 'meta') as synced_at,
  (select count(*) from public.serving_datasets) as dataset_count,
  (
    select jsonb_object_agg(dataset, jsonb_build_object(
      'updated_at', updated_at,
      'synced_at', synced_at,
      'byte_size', byte_size,
      'checksum', checksum
    ))
    from public.serving_datasets
  ) as datasets;

alter table public.serving_datasets enable row level security;
alter table public.sync_runs enable row level security;

-- Baca publik (anon) untuk frontend
drop policy if exists "serving_datasets_public_read" on public.serving_datasets;
create policy "serving_datasets_public_read"
  on public.serving_datasets
  for select
  to anon, authenticated
  using (true);

drop policy if exists "sync_runs_public_read" on public.sync_runs;
create policy "sync_runs_public_read"
  on public.sync_runs
  for select
  to anon, authenticated
  using (true);

-- Tulis hanya via service_role (bypass RLS). Jangan buat policy insert/update untuk anon.

grant select on public.serving_datasets to anon, authenticated;
grant select on public.sync_runs to anon, authenticated;
grant select on public.serving_status to anon, authenticated;

comment on table public.serving_datasets is
  'Serving layer Atlas: payload JSON/GeoJSON siap konsumsi frontend.';
comment on table public.sync_runs is
  'Log sync berkala dari pipeline export → Supabase.';
