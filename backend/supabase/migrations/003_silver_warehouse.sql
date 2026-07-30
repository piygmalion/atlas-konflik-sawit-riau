-- Silver warehouse (Fase 3A) — normalisasi penuh + bridge
-- Tidak drop/alter serving_datasets.

create table if not exists public.dim_polres (
  polres text primary key,
  peringkat integer,
  skor double precision,
  kategori text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.dim_perusahaan (
  nama text primary key,
  nama_kanonik text,
  sumber text,
  ada_di_gfw boolean,
  ada_di_atlas boolean,
  ada_izin_2017 boolean,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.fact_kasus (
  id text primary key,
  tipe_entri text,
  kab_kota text,
  polres text,
  tahun text,
  perusahaan text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.fact_konsesi_atlas (
  atlas_id text primary key,
  nama_perusahaan text,
  nama_kanonik text,
  grup text,
  kabupaten text,
  luas_ha double precision,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.bridge_alias (
  nama_mentah text primary key,
  nama_kanonik text not null,
  sumber text,
  confidence text,
  updated_at timestamptz not null default now()
);

create table if not exists public.bridge_atlas_match (
  match_id text primary key,
  atlas_nama text,
  atlas_uid text,
  gfwid text,
  status text,
  match_confidence text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.mart_rantai_agrinas (
  id text primary key default 'baseline',
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.dim_polres enable row level security;
alter table public.dim_perusahaan enable row level security;
alter table public.fact_kasus enable row level security;
alter table public.fact_konsesi_atlas enable row level security;
alter table public.bridge_alias enable row level security;
alter table public.bridge_atlas_match enable row level security;
alter table public.mart_rantai_agrinas enable row level security;

drop policy if exists "dim_polres_public_read" on public.dim_polres;
create policy "dim_polres_public_read" on public.dim_polres for select to anon, authenticated using (true);
drop policy if exists "dim_perusahaan_public_read" on public.dim_perusahaan;
create policy "dim_perusahaan_public_read" on public.dim_perusahaan for select to anon, authenticated using (true);
drop policy if exists "fact_kasus_public_read" on public.fact_kasus;
create policy "fact_kasus_public_read" on public.fact_kasus for select to anon, authenticated using (true);
drop policy if exists "fact_konsesi_atlas_public_read" on public.fact_konsesi_atlas;
create policy "fact_konsesi_atlas_public_read" on public.fact_konsesi_atlas for select to anon, authenticated using (true);
drop policy if exists "bridge_alias_public_read" on public.bridge_alias;
create policy "bridge_alias_public_read" on public.bridge_alias for select to anon, authenticated using (true);
drop policy if exists "bridge_atlas_match_public_read" on public.bridge_atlas_match;
create policy "bridge_atlas_match_public_read" on public.bridge_atlas_match for select to anon, authenticated using (true);
drop policy if exists "mart_rantai_public_read" on public.mart_rantai_agrinas;
create policy "mart_rantai_public_read" on public.mart_rantai_agrinas for select to anon, authenticated using (true);

grant select on public.dim_polres to anon, authenticated;
grant select on public.dim_perusahaan to anon, authenticated;
grant select on public.fact_kasus to anon, authenticated;
grant select on public.fact_konsesi_atlas to anon, authenticated;
grant select on public.bridge_alias to anon, authenticated;
grant select on public.bridge_atlas_match to anon, authenticated;
grant select on public.mart_rantai_agrinas to anon, authenticated;
