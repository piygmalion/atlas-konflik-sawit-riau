# Atlas Konflik Sawit Riau

Peta interaktif konflik dan permasalahan sawit di Provinsi Riau — objek Agrinas–Satgas, ranking Polres, kasus agraria, dan celahan legal.

**Live preview:** https://piygmalion.github.io/atlas-konflik-sawit-riau/

## Fitur

- Peta spasial penuh (Leaflet) dengan lapisan kab/kota, titik objek, dan koridor
- Ranking early-warning Polres + filter Prioritas / Waspada / Pantau
- Panel detail kasus & objek saat fitur diklik
- Tab Cerita & Data untuk narasi dan audit tabel
- Data JSON terpisah — update berkala tanpa mengubah UI

## Update data

Dari workspace sumber (folder induk yang berisi workbook/CSV):

```bash
# 1) (Opsional) terapkan perbaikan kualitas data ke CSV/JSON
python website/scripts/apply_dq_fixes.py

# 2) Ekspor serving layer
python website/scripts/export_web_data.py

# 3) Gate validasi (juga dipanggil di akhir export)
python website/scripts/validate_web_data.py

# 4) Audit + laporan DQ
python website/scripts/write_dq_report.py
```

Commit & push perubahan di `website/data/` hanya jika `validate_web_data.py` **PASS**.

Ambang lulus utama:

- 0 duplikat PK: `kasus.id`, `objek.id`, `kab.id`, `polres`, `gfwid`, `match_id`, `record_id` SK36
- `meta.counts` selaras dengan `len(records)`
- Kasus operasional tanpa `nomor_lp` (dan tanpa flag `tanpa_lp`) ≤ 50%

Lihat [SCHEMA.md](data/SCHEMA.md) dan `data/dq_report.json`.

## Pengembangan lokal

```bash
cd website
python -m http.server 8080
```

Buka http://127.0.0.1:8080/

## Batasan

Koordinat bersifat proksi OSINT, bukan batas legal HGU/IUP. Bandingkan bukti satelit di [Nusantara Atlas](https://map.nusantara-atlas.org/).
