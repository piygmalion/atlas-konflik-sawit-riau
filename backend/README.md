# Backend — Atlas Konflik Sawit Riau

API + pipeline sync yang menyimpan serving layer (`website/data/*`) ke **Supabase**, supaya frontend bisa diperbarui berkala tanpa redeploy penuh.

## Arsitektur

```
CSV/XLSX workspace
    → scripts/export_web_data.py
    → website/data/*.json|geojson
    → backend/sync_serving.py
    → Supabase table serving_datasets (jsonb)
    → frontend (js/data-source.js)  [atau FastAPI /api/v1/datasets/*]
```

| Komponen | Peran |
|---|---|
| `supabase/migrations/001_serving_schema.sql` | Tabel `serving_datasets`, `sync_runs`, RLS baca publik |
| `sync_serving.py` | Upsert semua dataset ke Supabase |
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

`meta`, `kab_kota`, `polres`, `objek_agrinas`, `kasus`, `perusahaan`, `konsesi`, `konsesi_gfw_full`, `analytics`, `penertiban`, `dq_report`, `layers`, `adm2`, `gfw_konsesi`.

Baca langsung lewat PostgREST:

```
GET {SUPABASE_URL}/rest/v1/serving_datasets?dataset=eq.kasus&select=payload
Headers: apikey + Authorization: Bearer {ANON_KEY}
```
