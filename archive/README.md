# Archive — bronze twin / legacy

Folder ini menampung workbook yang **bukan SoT export**.

## Aturan

- Twin XLSX di root workspace = bronze-only (referensi manusia). Export memakai CSV SoT.
- Jangan dual-write: ubah SoT CSV dulu, regenerasi twin hanya bila perlu dokumentasi.
- Kepmenhut tabular: hanya `tabulasi_konsesi_sawit_kepmenhut_36_2025_riau_rapi.csv` (bukan `…parsial.csv`).
- Alias perusahaan: `dim_perusahaan_alias.csv` — jangan mengandalkan `Normalisasi_Perusahaan_*.xlsx`.

## Isi

| File | Alasan archive |
|---|---|
| `Normalisasi_Perusahaan_Sawit_Riau.xlsx` | Legacy v1; digantikan `dim_perusahaan_alias.csv` + `Normalisasi_…_v2.xlsx` (bronze) |

`Normalisasi_Perusahaan_Sawit_Riau_v2.xlsx` tetap di root sebagai twin bronze opsional; SoT tetap `dim_perusahaan_alias.csv`.
