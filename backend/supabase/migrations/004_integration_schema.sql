-- Integration schema (Matching & Overlay Engine) - additive di atas 002/003
-- Tidak drop/alter serving_datasets.

-- 1) Katalog sumber & lineage
create table if not exists public.meta_sumber (
  sumber_id text primary key,
  nama text not null,
  akses text not null check (akses in ('terbuka', 'tertutup')),
  tipe_data text not null check (tipe_data in ('tabular', 'spasial')),
  kredibilitas text,
  grain text,
  path_sot text,
  refresh_cadence text,
  status text not null default 'active'
    check (status in ('active', 'planned', 'orphan')),
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.ingest_run (
  run_id uuid primary key default gen_random_uuid(),
  sumber_id text references public.meta_sumber (sumber_id),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  checksum text,
  row_count integer,
  status text not null default 'running'
    check (status in ('running', 'success', 'partial', 'failed')),
  notes text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists ingest_run_sumber_idx on public.ingest_run (sumber_id);
create index if not exists ingest_run_started_idx on public.ingest_run (started_at desc);

-- 2) Perkuat identitas (additive columns)
alter table public.dim_perusahaan
  add column if not exists perusahaan_id text;
alter table public.dim_perusahaan
  add column if not exists nama_normalized text;
alter table public.dim_perusahaan
  add column if not exists provinsi_hint text;
alter table public.dim_perusahaan
  add column if not exists kab_list jsonb not null default '[]'::jsonb;

create unique index if not exists dim_perusahaan_id_uidx
  on public.dim_perusahaan (perusahaan_id)
  where perusahaan_id is not null;

alter table public.bridge_alias
  add column if not exists match_method text;
alter table public.bridge_alias
  add column if not exists geo_validated boolean;
alter table public.bridge_alias
  add column if not exists rejected_reason text;

-- 3) Fakta spasial & legal
create table if not exists public.fact_gfw_konsesi (
  gfwid text primary key,
  company_raw text,
  nama_kanonik text,
  area_ha double precision,
  lon double precision,
  lat double precision,
  in_riau_bbox boolean,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.fact_penertiban_sk36 (
  record_id text primary key,
  nama text,
  nama_kanonik text,
  no integer,
  prioritas text,
  status_proses text,
  rasio_ditolak text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- 4) Bridge entity match (inti Matching Engine)
create table if not exists public.bridge_entity_match (
  match_id text primary key,
  left_source text not null,
  left_id text not null,
  right_source text not null,
  right_id text not null,
  nama_score double precision,
  geo_ok boolean,
  status text not null
    check (status in ('confirmed', 'warning', 'conflict', 'rejected')),
  match_type text
    check (match_type in (
      'gabungan_gfw', 'gfw_only', 'gabungan_only', 'gfw_bbox', 'not_found', 'atlas_gfw'
    )),
  human_verified boolean not null default false,
  evidence jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists bridge_entity_match_left_idx
  on public.bridge_entity_match (left_source, left_id);
create index if not exists bridge_entity_match_right_idx
  on public.bridge_entity_match (right_source, right_id);
create index if not exists bridge_entity_match_status_idx
  on public.bridge_entity_match (status);

-- 5) Mart dossier (protokol OSINT langkah 7)
create table if not exists public.mart_dossier_kasus (
  dossier_id text primary key,
  nama text not null,
  nama_kanonik text,
  kab text,
  luas_loss_ha double precision,
  gambut_ha double precision,
  legal_status text,
  konflik text,
  tautan_atlas text,
  gfwid text,
  status_match text,
  risiko text,
  human_verified boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- Seed 11 sumber blueprint (idempotent)
insert into public.meta_sumber
  (sumber_id, nama, akses, tipe_data, kredibilitas, grain, path_sot, refresh_cadence, status, payload)
values
  ('bps_2021', 'Direktori BPS Riau 2021', 'terbuka', 'tabular', 'tinggi',
   '1 baris / perusahaan', 'daftar_perusahaan_sawit_riau_gabungan.csv', 'tahunan', 'active',
   '{"kuadran":"terbuka_tabular","n_claim":237}'::jsonb),
  ('disbun_riau', 'Disbun Riau (statistik agregat)', 'terbuka', 'tabular', 'sedang',
   'agregat kab/prov', null, 'tahunan', 'planned',
   '{"kuadran":"terbuka_tabular"}'::jsonb),
  ('gfw_greenpeace', 'GFW / Greenpeace oil palm concessions', 'terbuka', 'spasial', 'tinggi',
   '1 poligon / gfwid', 'tabulasi_konsesi_sawit_gfw_bbox_riau.csv', 'periodik', 'active',
   '{"kuadran":"terbuka_spasial","n_claim":287}'::jsonb),
  ('nusantara_atlas', 'Nusantara Atlas', 'terbuka', 'spasial', 'tinggi',
   '1 baris / konsesi Atlas', 'tabulasi_konsesi_sawit_nusantara_atlas_riau.csv', 'periodik', 'active',
   '{"kuadran":"terbuka_spasial","n_claim":311}'::jsonb),
  ('fwi_hutan', 'Peta Hutan FWI', 'terbuka', 'spasial', 'sedang',
   'layer tutupan', null, 'periodik', 'planned',
   '{"kuadran":"terbuka_spasial"}'::jsonb),
  ('atr_bpn', 'ATR/BPN Kanwil (IUP tanpa HGU)', 'tertutup', 'tabular', 'tinggi',
   '1 baris / IUP', null, 'ad-hoc', 'planned',
   '{"kuadran":"tertutup_tabular","n_claim":126}'::jsonb),
  ('pemprov_riau', 'Pemprov Riau daftar perusahaan', 'tertutup', 'tabular', 'tinggi',
   '1 baris / perusahaan', null, 'ad-hoc', 'planned',
   '{"kuadran":"tertutup_tabular","n_claim":273}'::jsonb),
  ('kepmenhut_36_2025', 'Kepmenhut 36/2025 subjek 110A/B', 'tertutup', 'tabular', 'tinggi',
   '1 subjek / record_id', 'tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv', 'ad-hoc', 'active',
   '{"kuadran":"tertutup_tabular","n_claim":118}'::jsonb),
  ('walhi_investigasi', 'Investigasi spesifik WALHI', 'tertutup', 'spasial', 'sedang',
   'kasus investigasi', null, 'ad-hoc', 'planned',
   '{"kuadran":"tertutup_spasial"}'::jsonb),
  ('polda_konflik', 'Daftar Konflik Polda Riau', 'tertutup', 'tabular', 'tinggi',
   '1 entri / kasus', 'master_kasus_sawit_riau.csv', 'berkala', 'active',
   '{"kuadran":"tertutup_tabular"}'::jsonb),
  ('agrinas_satgas', 'Master List Objek Agrinas-Satgas', 'tertutup', 'tabular', 'tinggi',
   '1 objek / OBJ-###', 'master_list_objek_agrinas_satgas_riau.csv', 'berkala', 'active',
   '{"kuadran":"tertutup_tabular"}'::jsonb)
on conflict (sumber_id) do update set
  nama = excluded.nama,
  akses = excluded.akses,
  tipe_data = excluded.tipe_data,
  kredibilitas = excluded.kredibilitas,
  grain = excluded.grain,
  path_sot = excluded.path_sot,
  refresh_cadence = excluded.refresh_cadence,
  status = excluded.status,
  payload = excluded.payload,
  updated_at = now();

-- RLS
alter table public.meta_sumber enable row level security;
alter table public.ingest_run enable row level security;
alter table public.fact_gfw_konsesi enable row level security;
alter table public.fact_penertiban_sk36 enable row level security;
alter table public.bridge_entity_match enable row level security;
alter table public.mart_dossier_kasus enable row level security;

drop policy if exists "meta_sumber_public_read" on public.meta_sumber;
create policy "meta_sumber_public_read"
  on public.meta_sumber for select to anon, authenticated using (true);

drop policy if exists "ingest_run_public_read" on public.ingest_run;
create policy "ingest_run_public_read"
  on public.ingest_run for select to anon, authenticated using (true);

drop policy if exists "fact_gfw_konsesi_public_read" on public.fact_gfw_konsesi;
create policy "fact_gfw_konsesi_public_read"
  on public.fact_gfw_konsesi for select to anon, authenticated using (true);

drop policy if exists "fact_penertiban_sk36_public_read" on public.fact_penertiban_sk36;
create policy "fact_penertiban_sk36_public_read"
  on public.fact_penertiban_sk36 for select to anon, authenticated using (true);

drop policy if exists "bridge_entity_match_public_read" on public.bridge_entity_match;
create policy "bridge_entity_match_public_read"
  on public.bridge_entity_match for select to anon, authenticated using (true);

drop policy if exists "mart_dossier_kasus_public_read" on public.mart_dossier_kasus;
create policy "mart_dossier_kasus_public_read"
  on public.mart_dossier_kasus for select to anon, authenticated using (true);

grant select on public.meta_sumber to anon, authenticated;
grant select on public.ingest_run to anon, authenticated;
grant select on public.fact_gfw_konsesi to anon, authenticated;
grant select on public.fact_penertiban_sk36 to anon, authenticated;
grant select on public.bridge_entity_match to anon, authenticated;
grant select on public.mart_dossier_kasus to anon, authenticated;

comment on table public.meta_sumber is 'Katalog 11 sumber blueprint integrasi';
comment on table public.bridge_entity_match is 'Entity resolution geo-gated; confirmed dilarang jika geo_ok=false';
comment on table public.mart_dossier_kasus is 'Dossier 1-baris protokol OSINT langkah 7';
