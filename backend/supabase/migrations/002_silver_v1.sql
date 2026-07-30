-- Silver v1 (Fase 2A) — entity baru tanpa mengubah serving_datasets
-- Jalankan setelah 001_serving_schema.sql

create table if not exists public.dim_perusahaan_alias (
  nama_mentah text primary key,
  nama_kanonik text not null,
  sumber text,
  confidence text,
  updated_at timestamptz not null default now()
);

create table if not exists public.dim_kab_kota (
  id text primary key,
  kab_kota text not null,
  cluster text,
  skor_komposit double precision,
  kategori_peta text,
  polres_proksi text,
  verifikasi_status text,
  kepercayaan_sebaran text,
  rank_gfw text,
  rank_sebaran text,
  n_izin_2017 integer,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.desa_lock (
  id text primary key,
  kabupaten text,
  kecamatan text,
  desa text,
  desa_utama text,
  lon double precision,
  lat double precision,
  kepercayaan text,
  sent_scene text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.izin_2017 (
  record_id text primary key,
  kab_id text,
  kab_kota text,
  nama_mentah text not null,
  nama_kanonik text,
  izin_lokasi_ha double precision,
  iup_ha double precision,
  pelepasan_kh_ha double precision,
  hgu_ha double precision,
  vintage integer not null default 2017,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists dim_perusahaan_alias_kanonik_idx
  on public.dim_perusahaan_alias (nama_kanonik);
create index if not exists izin_2017_kab_idx
  on public.izin_2017 (kab_id);
create index if not exists desa_lock_kab_idx
  on public.desa_lock (kabupaten);

alter table public.dim_perusahaan_alias enable row level security;
alter table public.dim_kab_kota enable row level security;
alter table public.desa_lock enable row level security;
alter table public.izin_2017 enable row level security;

drop policy if exists "dim_perusahaan_alias_public_read" on public.dim_perusahaan_alias;
create policy "dim_perusahaan_alias_public_read"
  on public.dim_perusahaan_alias for select to anon, authenticated using (true);

drop policy if exists "dim_kab_kota_public_read" on public.dim_kab_kota;
create policy "dim_kab_kota_public_read"
  on public.dim_kab_kota for select to anon, authenticated using (true);

drop policy if exists "desa_lock_public_read" on public.desa_lock;
create policy "desa_lock_public_read"
  on public.desa_lock for select to anon, authenticated using (true);

drop policy if exists "izin_2017_public_read" on public.izin_2017;
create policy "izin_2017_public_read"
  on public.izin_2017 for select to anon, authenticated using (true);

grant select on public.dim_perusahaan_alias to anon, authenticated;
grant select on public.dim_kab_kota to anon, authenticated;
grant select on public.desa_lock to anon, authenticated;
grant select on public.izin_2017 to anon, authenticated;

comment on table public.dim_perusahaan_alias is 'Silver: alias perusahaan mentah→kanonik';
comment on table public.desa_lock is 'Silver: kunci desa verifikasi spasial';
comment on table public.izin_2017 is 'Silver: rekap izin perkebunan vintage 2017';
