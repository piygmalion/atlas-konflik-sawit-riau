# Backend — Atlas Konflik Sawit Riau

API + pipeline sync yang menyimpan serving layer (`website/data/*`) ke **Supabase**, supaya frontend bisa diperbarui berkala tanpa redeploy penuh.

## Arsitektur

```
bronze (workspace CSV/XLSX)
    → apply_dq_fixes.py / export_web_data.py
    → build_entity_matches.py  (Matching & Overlay Engine)
    → website/data/*          (gold blobs + dossier)
    → sync_serving.py         → serving_datasets
    → sync_silver.py [--warehouse] [--integration] → dim_*/fact_*/bridge_*/mart_*
    → materialize_serving.py → gold dari silver
    → frontend js/data-source.js
```

**SoT:** CSV kanonik di folder workspace (lihat `data/SCHEMA.md`). XLSX twin = bronze-only. Orphan workbook masuk roadmap P0–P2, bukan defect sync.

| Komponen | Peran |
|---|---|
| `supabase/migrations/001_serving_schema.sql` | Tabel `serving_datasets`, `sync_runs`, RLS baca publik |
| `supabase/migrations/002_silver_v1.sql` | Silver: alias, kab, desa_lock, izin_2017 |
| `supabase/migrations/003_silver_warehouse.sql` | Silver penuh + bridge |
| `supabase/migrations/004_integration_schema.sql` | Matching Engine: meta_sumber, bridge_entity_match, fact_gfw, sk36, dossier |
| `sync_serving.py` | Upsert gold blobs ke Supabase |
| `sync_silver.py` | Backfill silver dari bronze/gold |
| `scripts/build_entity_matches.py` | Entity resolution geo-gated + dossier mart |
| `materialize_serving.py` | Gold dari silver (Fase 3) + panggil matching engine |
| `app/main.py` (FastAPI) | Health, list/get dataset, trigger sync |
| `js/config.js` + `js/data-source.js` | Frontend: Supabase / API / lokal |

## Setup Supabase (sekali)

1. Buat project di [supabase.com](https://supabase.com).
2. SQL Editor → jalankan isi `supabase/migrations/001_serving_schema.sql`.
3. Project Settings → API, salin:
   - **Project URL**
   - **service_role** (rahasia, hanya server/CI)
   - **anon public** (aman untuk frontend)
4. Di repo ini:

```bash
cd backend
copy .env.example .env   # Windows
# isi SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
pip install -r requirements.txt
python sync_serving.py --dry-run
python sync_serving.py
```

5. Frontend — edit `js/config.js`:

```js
window.ATLAS_CONFIG = {
  dataSource: "auto",
  supabaseUrl: "https://xxxx.supabase.co",
  supabaseAnonKey: "eyJhbGciOi...",
  apiBaseUrl: "",
};
```

Mode `auto`: coba Supabase dulu, gagal → fallback `data/` lokal.

## API lokal

```bash
cd backend
python run_api.py
# → http://127.0.0.1:8787/docs
```

Endpoint utama:

- `GET /health`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{name}?source=auto|supabase|local`
- `POST /api/v1/sync` (header `X-API-Key` jika `SYNC_API_KEY` di-set)
- `GET /api/v1/sync/latest`

## Update berkala

### Manual

```bash
python scripts/apply_dq_fixes.py   # opsional
python scripts/export_web_data.py
python scripts/validate_web_data.py
python backend/sync_serving.py --trigger manual
```

### GitHub Actions

Workflow `.github/workflows/sync-supabase.yml`:

- Jadwal: **Senin 01:00 UTC**
- Juga saat push ke `data/**` atau `backend/**`
- Secrets repo yang wajib:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`

## Dataset yang di-sync

`meta`, `kab_kota`, `polres`, `objek_agrinas`, `kasus`, `perusahaan`, `perusahaan_alias`, `konsesi`, `konsesi_gfw_full`, `analytics`, `penertiban`, `dq_report`, `desa_lock`, `izin_2017`, `rantai_agrinas`, `dossier`, `layers`, `adm2`, `gfw_konsesi`.

Silver (Fase 2+): `python sync_silver.py` lalu `python sync_silver.py --warehouse` setelah migration `002`/`003`.  
Integrasi (Matching Engine): `python sync_silver.py --warehouse --integration` setelah migration `004`.

`sync_silver.py` exit codes: `0` sukses, `2` Supabase belum dikonfigurasi, `3` silver schema belum di-apply (PGRST205 — jalankan migration `002`/`003`/`004` di SQL Editor).
Materialize gold: `python ../scripts/materialize_serving.py` (ikut menjalankan `build_entity_matches.py`).

Baca langsung lewat PostgREST:

```
GET {SUPABASE_URL}/rest/v1/serving_datasets?dataset=eq.kasus&select=payload
Headers: apikey + Authorization: Bearer {ANON_KEY}
```
