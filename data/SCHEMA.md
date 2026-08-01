# Schema serving layer — Atlas Konflik Sawit Riau

Grain, primary keys, and required vs optional fields after DQ remediation (Juli 2026).

## Pipeline

```
bronze (workspace CSV/XLSX)
    → apply_dq_fixes.py (opsional)
    → export_web_data.py  (+ enrich Fase 1–2)
    → build_entity_matches.py  (Matching & Overlay Engine)
    → validate_web_data.py
    → website/data/  (gold blobs)
    → backend/sync_serving.py → Supabase serving_datasets
    → (Fase 2+) silver tables  →  (Fase 3) materialize_serving.py → gold
    → sync_silver.py --warehouse --integration  (dim/fact/bridge/mart)
```

Update berkala: lihat `backend/README.md`. Frontend (`js/data-source.js`) bisa baca Supabase atau fallback ke file lokal.

## Source of truth (SoT) vs bronze twin

Export **hanya** memakai kanon di kolom SoT. File twin XLSX = bronze-only (jangan dual-write).

| Konsep | SoT (dipakai export) | Twin / bronze-only |
|---|---|---|
| Objek Agrinas | `master_list_objek_agrinas_satgas_riau.csv` | `Master_List_Objek_Agrinas_Satgas_Riau.xlsx` |
| Ranking Polres | `ranking_potensi_konflik_per_polres.csv` | `Ranking_Potensi_Konflik_Per_Polres.xlsx` |
| Kepmenhut 36/2025 | `tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv` | XLSX kepmenhut; CSV `…parsial.csv` |
| Alias perusahaan | `dim_perusahaan_alias.csv` | dibangun ulang oleh DQ dari BPS/GFW/Atlas |
| Perusahaan gabungan | `daftar_perusahaan_sawit_riau_gabungan.csv` | `Daftar_…xlsx`, `Normalisasi_…xlsx` |
| Kasus | `master_kasus_sawit_riau.csv` (+ sheet TABEL bila perlu) | `Inventarisasi_…xlsx` (internal) |

### Orphan (bukan defect sync)

Masuk roadmap enrichment; **bukan** kegagalan backend:

- **P0:** alias (sudah SoT), Atlas full CSV, verifikasi/perkiraan sebaran
- **P1:** kunci desa, rekap izin 2017, Master List Fase2
- **P2:** baseline rantai Satgas, agregat grup Atlas
- **SKIP publik:** Template/Rencana perbaikan, inventaris operasional internal

## Entities

### kab_kota (`kab_kota.json`)

| | |
|---|---|
| **Grain** | 1 baris / kabupaten-kota Riau |
| **PK** | `id` (slug) |
| **Wajib** | `id`, `kab_kota`, `cluster`, `skor_komposit`, `kategori_peta`, `polres_proksi` |
| **Opsional** | `hotspot_kecamatan`, `luas_disebut_terbuka`, nested `risiko_register.*` |

### polres (`polres.json`)

| | |
|---|---|
| **Grain** | 1 baris / Polres |
| **PK** | `polres` |
| **Wajib** | `peringkat`, `polres`, `skor`, `kategori`, komponen skor |
| **Opsional** | `tahun` |

### objek_agrinas (`objek_agrinas.json`)

| | |
|---|---|
| **Grain** | 1 baris / objek Agrinas–Satgas (**entity registry**: badan hukum / mitra KSO / unit kelola) |
| **PK** | `id` (`OBJ-###`) |
| **Wajib** | `id`, `nama`, `prioritas`, `kab_primary`, `mappable` |
| **Opsional** | `mitra_pair` (**sumber-null / non-wajib**), `luas_disebut`, `kab_list`, `polres_primary` |

`kab_primary` = satu kab kanonik atau `MULTI`. Agregat choropleth sebaiknya memakai `kab_primary`, bukan string `kab_kota` bebas.

**Policy titik vs objek (bukan gap 1:1):** `objek_agrinas` (≈139) ≠ layer `objek_titik` (≈54 di serving). Titik serving = **proksi spasial plottable**: hotspot OSINT + expand DQ centroid-kab untuk objek `mappable=ya` prioritas Tinggi/Kritis. Placeholder **REF/centroid kab** tetap boleh ada di sumber `proksi_peta_titik_agrinas.geojson` tetapi **tidak** di-inject ke `layers.geojson`. Objek `MULTI` / Mitra KSO agregat **tidak** dipaksa-plot. Metrik benar: coverage mappable (≈34/139), bukan membandingkan titik vs registry 1:1.

Field `perusahaan` pada `objek_titik` (opsional tapi disarankan) = nama perusahaan terkait untuk preview peta / profil detail. Diisi lewat `scripts/enrich_titik_perusahaan.py` (mapping hotspot + fuzzy match `perusahaan.json`) dan diteruskan export/DQ.

### kasus (`kasus.json` / `master_kasus_sawit_riau.csv`)

| | |
|---|---|
| **Grain** | 1 baris / entri register |
| **PK** | `id` (`SW-###`) |
| **Wajib (semua)** | `id`, `tipe_entri`, `polres` atau `kab_kota` |
| **Wajib jika `tipe_entri=Kasus operasional`** | `nomor_lp` **atau** `tanpa_lp=true`, plus `status` |
| **Opsional** | `hambatan`, `jenis`, `upaya` (diisi default DQ jika operasional) |

`tipe_entri` hanya: `Kasus operasional` | `Potensi/register`.  
Entri noise (uraian placeholder nihil) **tidak** masuk serving.

### perusahaan (`perusahaan.json`)

| | |
|---|---|
| **Grain** | 1 nama perusahaan kanonik |
| **PK** | `nama` (unik) |
| **Wajib** | `no`, `nama`, `sumber` |
| **Opsional** | `catatan`, `nama_kanonik`, `ada_di_gfw`, `ada_di_atlas`, `ada_izin_2017` |

### perusahaan_alias (`perusahaan_alias.json`)

| | |
|---|---|
| **Grain** | 1 baris alias mentah → kanonik |
| **PK** | `nama_mentah` (unik, case-insensitive) |
| **Wajib** | `nama_mentah`, `nama_kanonik` |
| **Opsional** | `sumber`, `confidence` |

Sumber bronze: `dim_perusahaan_alias.csv`.

### kab_kota (`kab_kota.json`) — field verifikasi (Fase 1C)

| Opsional additive | |
|---|---|
| `verifikasi_status` | status dari workbook verifikasi sebaran |
| `kepercayaan_sebaran` | skor/label kepercayaan |
| `rank_gfw` | peringkat area GFW di kab |
| `rank_sebaran` | peringkat sebaran peta |

### konsesi atlas_match (`konsesi.json::atlas_match`)

| | |
|---|---|
| **Grain** | 1 baris = pasangan match `(atlas, gfw)` |
| **PK** | `match_id` |
| **Wajib** | `match_id`, `atlas_nama` |
| **Opsional** | `gfwid`, `match_confidence`, flags BPS/konflik |

### konsesi atlas_full (`konsesi.json::atlas_full`)

| | |
|---|---|
| **Grain** | 1 baris konsesi Nusantara Atlas (registry penuh) |
| **PK** | `atlas_id` (stabil: `no` atau slug nama+kab) |
| **Wajib** | `atlas_id`, `nama_perusahaan` |
| **Opsional** | `grup`, `kabupaten`, `luas_ha`, `luas_gambut_ha`, `hutan_tersisa_ha`, `tipe_konsesi` |

**Jangan** menimpa `atlas_match` — grain berbeda (match pair vs registry).

### desa_lock (`desa_lock.json`)

| | |
|---|---|
| **Grain** | 1 kunci desa / titik verifikasi |
| **PK** | `id` |
| **Wajib** | `id`, `kabupaten` |
| **Opsional** | `kecamatan`, `desa`, `lon`, `lat`, `kepercayaan`, metadata Sentinel |

### izin_2017 (`izin_2017.json`)

| | |
|---|---|
| **Grain** | 1 baris izin historis (perusahaan × kab, vintage 2017) |
| **PK** | `record_id` |
| **Wajib** | `record_id`, `kab_id` atau `kab_kota`, `nama_mentah` |
| **Opsional** | `nama_kanonik`, atribut kolom sheet asal |

Disclaimer: data vintage 2017 — bukan status izin terkini.

### objek_agrinas — field Fase2 (additive)

| Opsional | |
|---|---|
| `fase2_gap` | flag/catatan gap matching Fase 2 |
| `mitra_eval` | evaluasi mitra KSO bila ada |

Alias mentah → kanonik: `dim_perusahaan_alias.csv`.

### konsesi GFW (`konsesi_gfw_full.json`)

| | |
|---|---|
| **Grain** | 1 poligon |
| **PK** | `gfwid` |
| **Wajib** | `gfwid`, `company` atau `name`, `nama_kanonik` |
| **Sumber-null (bukan gagal DQ)** | `hgu`, `area_hgu_ha`, `legal`, `type` |

`nama_kanonik` diisi export (alias) dan di-sync ulang oleh `build_entity_matches.py` dari `fact_gfw_konsesi`.

### entity_matches (`entity_matches.json`) — serving UI

| | |
|---|---|
| **Grain** | 1 baris resolusi entitas (subset `bridge_entity_match`) |
| **PK** | `match_id` |
| **Wajib** | `match_id`, `status`, `match_type` |
| **Opsional** | `left_*`, `right_*`, `nama_score`, `geo_ok`, `human_verified`, `evidence` |

Silver penuh tetap di `data/silver/bridge_entity_match.json`. Gold UI = subset field di atas.

### dossier (`dossier.json`)

| | |
|---|---|
| **Grain** | 1 baris / konsesi Atlas |
| **PK** | `dossier_id` |
| **Wajib** | `dossier_id`, `nama` |
| **Label UI** | `match_status` = confirmed/warning/rejected; `status_match` = tipe match (`gabungan_gfw`, `gfw_only`, …) |
| **Opsional** | `risiko`, `legal_status`, `luas_loss_ha`, `gambut_ha`, `gfwid`, `tautan_atlas`, `human_verified` |

### Frontend boot vs lazy

| Boot (app start) | Lazy (setelah paint / tab Analisis) |
|---|---|
| meta, kab, polres, objek, kasus, layers, adm2 | `perusahaan_alias`, `desa_lock`, `izin_2017`, `rantai_agrinas` |
| perusahaan, konsesi, dossier, entity_matches, analytics, penertiban | |

Serving-only (tidak di-boot UI): `dq_report`.

Lapisan peta: `choropleth`, `koridor`, `densitas_kasus`, `objek_titik`, `hotspot_verifikasi`, `gfw_konsesi`.  
`meta.counts.fitur_spasial` harus = `len(layers.features)`; `hotspot_verifikasi` wajib di `meta.layers` bila ada fitur.

### penertiban SK36 (`penertiban.json::sk36_2025_110a`)

| | |
|---|---|
| **Grain** | 1 subjek / status setelah DQ |
| **PK** | `record_id` |
| **Wajib** | `record_id`, `nama`, `no` (sequential post-DQ) |
| **Opsional** | `prioritas`, `rasio_ditolak`, `status_proses` |

Sumber kepmenhut tabular: **`tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv`** (bukan parsial).

### layers (`layers.geojson`)

Heterogen per `properties.layer`. Lihat `schema_by_layer` di file. Field koridor (`anggota_kab`, …) **tidak** wajib pada `objek_titik`. Hanya hotspot georef terverifikasi yang di-inject (bukan REF/centroid placeholder). Layer `hotspot_verifikasi` = titik dari workbook verifikasi sebaran dengan status Terkonfirmasi/Terverifikasi.

## Sumber-null (dilarang dihitung sebagai gagal DQ)

- Atlas: `ispo`, `nomor_izin`, `luas_izin_ha`, `status_izin`
- GFW: atribut HGU jika sumber tidak menyediakan
- Objek: `mitra_pair`

## Integrasi (Matching & Overlay Engine)

Kontrak di atas silver warehouse (`004_integration_schema.sql`). Skrip: `scripts/build_entity_matches.py`.

### Aturan matching

1. Normalisasi nama via `company_normalize.py` (strip PT/CV + alias).
2. Candidate match: alias + exact norm; wajib cek kab/provinsi / bbox Riau.
3. **Nama cocok + wilayah beda ⇒ `conflict`/`rejected`, bukan `confirmed`.**
4. `status=confirmed` hanya jika `geo_ok` bukan `false` (validate hard-fail jika dilanggar).
5. `match_type`: `gabungan_gfw` | `gfw_only` | `gabungan_only` | `gfw_bbox` | `not_found` | `atlas_gfw`.
6. `human_verified` default `false` — data algoritmik bukan instrumen penindakan tunggal.
7. Sumber-null (HGU, ISPO, dll.) tetap tidak dihitung gagal DQ.

### meta_sumber (`silver/meta_sumber.json`)

| | |
|---|---|
| **Grain** | 1 baris / sumber blueprint (11) |
| **PK** | `sumber_id` |
| **Wajib** | `sumber_id`, `nama`, `akses` (`terbuka`\|`tertutup`), `tipe_data` (`tabular`\|`spasial`), `status` |
| **Opsional** | `path_sot`, `kredibilitas`, `grain`, `refresh_cadence` |

### bridge_entity_match (`silver/bridge_entity_match.json`)

| | |
|---|---|
| **Grain** | 1 pasangan `(left_source, left_id) ↔ (right_source, right_id)` |
| **PK** | `match_id` |
| **Wajib** | `match_id`, `left_source`, `left_id`, `right_source`, `right_id`, `status` |
| **Opsional** | `nama_score`, `geo_ok`, `match_type`, `evidence`, `human_verified` |

### fact_gfw_konsesi / fact_penertiban_sk36

| | fact_gfw | fact_sk36 |
|---|---|---|
| **PK** | `gfwid` | `record_id` |
| **Wajib** | `gfwid` | `record_id`, `nama` |
| **Geo** | `lon`/`lat`/`in_riau_bbox` | — |

### dossier (`dossier.json` / `mart_dossier_kasus`)

| | |
|---|---|
| **Grain** | 1 baris / konsesi Atlas (protokol OSINT langkah 7) |
| **PK** | `dossier_id` (`DOS-{atlas_id}`) |
| **Wajib** | `dossier_id`, `nama` |
| **Kolom ringkas** | `kab`, `luas_loss_ha`, `gambut_ha`, `legal_status`, `konflik`, `tautan_atlas`, `gfwid`, `status_match`, `risiko` |

### perusahaan — field integrasi (additive)

| Opsional | |
|---|---|
| `perusahaan_id` | slug stabil `PER-{norm}` |
| `nama_normalized` | bentuk tampilan tanpa token legal |
| `provinsi_hint` | default `RIAU` |
| `kab_list` | daftar kab terkait (array) |
