# Schema serving layer — Atlas Konflik Sawit Riau

Grain, primary keys, and required vs optional fields after DQ remediation (Juli 2026).

## Pipeline

```
root CSV/XLSX  →  apply_dq_fixes.py (opsional)  →  export_web_data.py  →  validate_web_data.py  →  website/data/
                                                                                                      ↓
                                                                              backend/sync_serving.py → Supabase serving_datasets
```

Update berkala: lihat `backend/README.md`. Frontend (`js/data-source.js`) bisa baca Supabase atau fallback ke file lokal.

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
| **Opsional** | `catatan`, `nama_kanonik`, `ada_di_gfw`, `ada_di_atlas` |

Alias mentah → kanonik: `dim_perusahaan_alias.csv`.

### konsesi GFW (`konsesi_gfw_full.json`)

| | |
|---|---|
| **Grain** | 1 poligon |
| **PK** | `gfwid` |
| **Wajib** | `gfwid`, `company` atau `name` |
| **Sumber-null (bukan gagal DQ)** | `hgu`, `area_hgu_ha`, `legal`, `type` |

### konsesi atlas_match (`konsesi.json::atlas_match`)

| | |
|---|---|
| **Grain** | 1 baris = pasangan match `(atlas, gfw)` |
| **PK** | `match_id` |
| **Wajib** | `match_id`, `atlas_nama` |
| **Opsional** | `gfwid`, `match_confidence`, flags BPS/konflik |

### penertiban SK36 (`penertiban.json::sk36_2025_110a`)

| | |
|---|---|
| **Grain** | 1 subjek / status setelah DQ |
| **PK** | `record_id` |
| **Wajib** | `record_id`, `nama`, `no` (sequential post-DQ) |
| **Opsional** | `prioritas`, `rasio_ditolak`, `status_proses` |

Sumber kepmenhut tabular: **`tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv`** (bukan parsial).

### layers (`layers.geojson`)

Heterogen per `properties.layer`. Lihat `schema_by_layer` di file. Field koridor (`anggota_kab`, …) **tidak** wajib pada `objek_titik`.

## Sumber-null (dilarang dihitung sebagai gagal DQ)

- Atlas: `ispo`, `nomor_izin`, `luas_izin_ha`, `status_izin`
- GFW: atribut HGU jika sumber tidak menyediakan
- Objek: `mitra_pair`
