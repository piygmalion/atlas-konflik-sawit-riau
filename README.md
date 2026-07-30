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

Dari workspace sumber (folder induk yang berisi workbook):

```bash
python scripts/export_web_data.py
```

Lalu commit & push perubahan di `data/`.

## Pengembangan lokal

```bash
python -m http.server 8080
```

Buka http://127.0.0.1:8080/

## Batasan

Koordinat bersifat proksi OSINT, bukan batas legal HGU/IUP. Bandingkan bukti satelit di [Nusantara Atlas](https://map.nusantara-atlas.org/).
