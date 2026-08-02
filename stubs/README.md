# Stub SoT — sumber planned

File di folder ini adalah **placeholder kontrak**, bukan data operasional.

| sumber_id | File | Akses | Status |
|---|---|---|---|
| `disbun_riau` | `disbun_riau_agregat.csv` | terbuka | planned |
| `fwi_hutan` | `fwi_hutan_layer.csv` | terbuka | planned |
| `atr_bpn` | `atr_bpn_iup.csv` | tertutup | planned |
| `pemprov_riau` | `pemprov_riau_perusahaan.csv` | tertutup | planned |
| `walhi_investigasi` | `walhi_investigasi.csv` | tertutup | planned |

Saat file SoT sungguhan tiba: ganti isi (pertahankan header grain), pindahkan ke root workspace bila perlu, lalu update `path_sot` + `status=active` di `META_SUMBER` (`website/scripts/build_entity_matches.py`) dan jalankan export + `sync_silver.py --integration`.

Jangan mengisi stub dengan data spekulatif untuk menaikkan count UI.
