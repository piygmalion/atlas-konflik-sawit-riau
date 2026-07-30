/* Atlas Konflik Sawit Riau — map-first interactive viewer */

const DATA = {
  meta: null,
  kab: null,
  polres: null,
  objek: null,
  kasus: null,
  perusahaan: null,
  konsesi: null,
  layers: null,
};

const state = {
  view: "peta",
  priority: "all",
  layerOn: { kab_centroid: true, objek_titik: true, koridor: true },
  map: null,
  layerGroups: {},
  selected: null,
};

const colorFor = (level) => {
  const t = String(level || "").toUpperCase();
  if (t.includes("PRIORITAS") || t.includes("SANGAT")) return "#b34a1e";
  if (t.includes("WASPADA") || t.includes("TINGGI")) return "#c4891a";
  return "#3d6b52";
};

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Gagal memuat ${path}`);
  return res.json();
}

async function boot() {
  const [meta, kab, polres, objek, kasus, perusahaan, konsesi, layers] = await Promise.all([
    loadJSON("data/meta.json"),
    loadJSON("data/kab_kota.json"),
    loadJSON("data/polres.json"),
    loadJSON("data/objek_agrinas.json"),
    loadJSON("data/kasus.json"),
    loadJSON("data/perusahaan.json"),
    loadJSON("data/konsesi.json"),
    loadJSON("data/layers.geojson"),
  ]);
  Object.assign(DATA, { meta, kab, polres, objek, kasus, perusahaan, konsesi, layers });

  document.getElementById("updatedAt").textContent =
    `Diperbarui ${formatDate(meta.updated_at)} · ${meta.counts.kasus_konflik} kasus · ${meta.counts.objek_agrinas} objek`;

  renderStats();
  renderLayers();
  renderPolres();
  initMap();
  renderStory();
  setupTabs();
  setupSearch();
  setupNav();
  setupFilters();
  setupDataTables();
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString("id-ID", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function renderStats() {
  const c = DATA.meta.counts;
  const prioritas = DATA.polres.records.filter((p) => p.kategori === "PRIORITAS").length;
  document.getElementById("statsGrid").innerHTML = [
    ["kasus_konflik", "Kasus konflik", c.kasus_konflik],
    ["objek_agrinas", "Objek Agrinas", c.objek_agrinas],
    ["polres", "Polres terpetakan", c.polres],
    ["prioritas", "Polres prioritas", prioritas],
  ]
    .map(
      ([, label, val]) =>
        `<div class="stat"><strong>${val ?? "–"}</strong><span>${label}</span></div>`
    )
    .join("");
}

function renderLayers() {
  const list = document.getElementById("layerList");
  list.innerHTML = (DATA.meta.layers || [])
    .map(
      (l) => `
      <label class="layer-item">
        <input type="checkbox" data-layer="${l.id}" ${state.layerOn[l.id] ? "checked" : ""} />
        <span>${l.label}</span>
      </label>`
    )
    .join("");
  list.querySelectorAll("input").forEach((el) => {
    el.addEventListener("change", () => {
      state.layerOn[el.dataset.layer] = el.checked;
      refreshLayerVisibility();
    });
  });
}

function renderPolres() {
  const ol = document.getElementById("polresList");
  const rows = DATA.polres.records.filter(
    (p) => state.priority === "all" || p.kategori === state.priority
  );
  ol.innerHTML = rows
    .map(
      (p) => `
      <li>
        <button type="button" data-polres="${escapeAttr(p.polres)}">
          <span class="n ${p.kategori}">${p.peringkat}</span>
          <span>
            <strong>${escapeHtml(p.polres.replace(/^Polres\s+/i, ""))}</strong><br/>
            <small>${escapeHtml(p.kategori)}</small>
          </span>
          <span class="score">${Number(p.skor).toFixed(0)}</span>
        </button>
      </li>`
    )
    .join("");
  ol.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => showPolres(btn.dataset.polres));
  });
}

function initMap() {
  const [lon, lat] = DATA.meta.center;
  state.map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
  }).setView([lat, lon], DATA.meta.zoom || 8);

  L.control.zoom({ position: "topright" }).addTo(state.map);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(state.map);

  state.layerGroups = {
    kab_centroid: L.layerGroup().addTo(state.map),
    objek_titik: L.layerGroup().addTo(state.map),
    koridor: L.layerGroup().addTo(state.map),
  };

  const feats = DATA.layers.features || [];
  feats.forEach((f) => {
    const p = f.properties || {};
    const layerId = p.layer || "objek_titik";
    if (f.geometry?.type === "Polygon") {
      const poly = L.geoJSON(f, {
        style: {
          color: "#1f3d2d",
          weight: 1.5,
          fillColor: "#1f3d2d",
          fillOpacity: 0.12,
          dashArray: "4 4",
        },
      });
      poly.on("click", () => showKoridor(p));
      poly.bindTooltip(p.nama || "Koridor");
      state.layerGroups.koridor.addLayer(poly);
      return;
    }
    if (f.geometry?.type !== "Point") return;
    const [x, y] = f.geometry.coordinates;
    const level = p.level_risiko || p.prioritas || p.kategori || "PANTAU";
    const color = colorFor(level);
    const radius = layerId === "kab_centroid" ? 11 : 7;
    const marker = L.circleMarker([y, x], {
      radius,
      color: "#fff",
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.92,
    });
    if (String(level).toUpperCase().includes("PRIORITAS") || String(level).toUpperCase().includes("SANGAT")) {
      marker.setStyle({ className: "pulse-ring" });
    }
    marker.bindTooltip(
      `<strong>${escapeHtml(p.nama || p.id || "")}</strong><br/><span>${escapeHtml(layerId === "kab_centroid" ? "Kab/Kota" : p.tipe || "Objek")}</span>`
    );
    marker.on("click", () => {
      if (layerId === "kab_centroid") showKabupaten(p.nama || p.id);
      else showTitik(p);
    });
    (state.layerGroups[layerId] || state.layerGroups.objek_titik).addLayer(marker);
  });

  refreshLayerVisibility();
  setTimeout(() => state.map.invalidateSize(), 100);
}

function refreshLayerVisibility() {
  Object.entries(state.layerGroups).forEach(([id, group]) => {
    if (state.layerOn[id]) {
      if (!state.map.hasLayer(group)) group.addTo(state.map);
    } else if (state.map.hasLayer(group)) {
      state.map.removeLayer(group);
    }
  });
}

function openDetail() {
  document.getElementById("detailPanel").classList.add("is-open");
}

function setDetail(html) {
  document.getElementById("detailContent").innerHTML = html;
  openDetail();
}

function showKabupaten(nama) {
  const kab = DATA.kab.records.find(
    (k) => (k.kab_kota || "").toLowerCase() === String(nama || "").toLowerCase()
  );
  if (!kab) return;
  state.selected = { type: "kab", id: kab.id };
  if (kab.lat && kab.lon) state.map.flyTo([kab.lat, kab.lon], 9, { duration: 0.8 });

  const kasus = DATA.kasus.records
    .filter((k) => matchWilayah(k.kab_kota, kab.kab_kota) || matchWilayah(k.polres, kab.polres_proksi))
    .slice(0, 8);
  const objek = DATA.objek.records
    .filter((o) => matchWilayah(o.kab_kota, kab.kab_kota))
    .slice(0, 8);
  const risk = kab.risiko_register || {};

  setDetail(`
    <p class="eyebrow">Kabupaten / Kota</p>
    <h1>${escapeHtml(kab.kab_kota)}</h1>
    <p class="lead">${escapeHtml(kab.catatan_peta || "Cluster spasial Agrinas–Satgas dan risiko konflik register.")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Kategori peta</label><span class="badge ${escapeAttr(kab.kategori_peta || "")}">${escapeHtml(kab.kategori_peta || "–")}</span></div>
      <div class="meta-item"><label>Skor komposit</label><strong>${fmtNum(kab.skor_komposit)}</strong></div>
      <div class="meta-item"><label>Risiko register</label><span class="badge" data-level="${escapeAttr(risk.level || "")}">${escapeHtml(risk.level || "–")} · ${fmtNum(risk.skor)}</span></div>
      <div class="meta-item"><label>Polres proksi</label>${escapeHtml(kab.polres_proksi || "–")}</div>
      <div class="meta-item"><label>Objek sinyal utama</label>${escapeHtml(kab.objek_sinyal_utama || "–")}</div>
      <div class="meta-item"><label>Hotspot kecamatan (perkiraan)</label>${escapeHtml(kab.hotspot_kecamatan || "–")}</div>
      <div class="meta-item"><label>Sawit di KH (KLHK 2022, ha)</label>${fmtNum(kab.klhk_korp_kh_2022_ha)}</div>
      <div class="meta-item"><label>Ketidakpastian</label>${escapeHtml(kab.ketidakpastian || "–")}</div>
    </div>
    ${risk.driver_utama ? `<p><strong>Driver utama:</strong> ${escapeHtml(risk.driver_utama)}</p>` : ""}
    ${risk.rekomendasi ? `<p><strong>Rekomendasi:</strong> ${escapeHtml(risk.rekomendasi)}</p>` : ""}
    <h2 style="font-size:0.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);margin:1.2rem 0 .5rem">Kasus terkait</h2>
    <div class="case-list">${kasus.map(caseCard).join("") || "<p class='lead'>Belum ada kasus terpetakan untuk wilayah ini.</p>"}</div>
    <h2 style="font-size:0.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);margin:1.2rem 0 .5rem">Objek Agrinas</h2>
    <div class="obj-list">${objek.map(objCard).join("") || "<p class='lead'>Tidak ada objek dengan kab/kota eksplisit.</p>"}</div>
  `);
}

function showPolres(nama) {
  const p = DATA.polres.records.find((x) => x.polres === nama);
  if (!p) return;
  const kab = DATA.kab.records.find((k) => matchWilayah(k.polres_proksi, p.polres));
  if (kab?.lat && kab?.lon) state.map.flyTo([kab.lat, kab.lon], 9, { duration: 0.8 });

  const kasus = DATA.kasus.records.filter((k) => matchWilayah(k.polres, p.polres)).slice(0, 10);
  setDetail(`
    <p class="eyebrow">Early-warning Polres</p>
    <h1>${escapeHtml(p.polres)}</h1>
    <p class="lead">${escapeHtml(p.alasan || "")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Peringkat</label><strong>#${p.peringkat}</strong></div>
      <div class="meta-item"><label>Skor</label><strong>${fmtNum(p.skor)}</strong> <span class="badge ${escapeAttr(p.kategori)}">${escapeHtml(p.kategori)}</span></div>
      <div class="meta-item"><label>OSINT / Register</label>${fmtNum(p.skor_osint)} / ${fmtNum(p.skor_register)}</div>
      <div class="meta-item"><label>Aksi massa · Kekerasan</label>${fmtNum(p.n_aksi_massa)} · ${fmtNum(p.n_kekerasan)}</div>
      <div class="meta-item"><label>Objek Agrinas/KSO</label>${fmtNum(p.n_agrinas)}</div>
      <div class="meta-item"><label>Entri 2024+</label>${fmtNum(p.n_recent)}</div>
    </div>
    <div class="meta-grid">
      ${Object.entries(p.komponen || {})
        .map(
          ([k, v]) =>
            `<div class="meta-item"><label>Komponen ${escapeHtml(k)}</label><strong>${fmtNum(v)}</strong></div>`
        )
        .join("")}
    </div>
    <h2 style="font-size:0.75rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-soft);margin:1.2rem 0 .5rem">Kasus di wilayah Polres</h2>
    <div class="case-list">${kasus.map(caseCard).join("") || "<p class='lead'>Tidak ada kasus terfilter.</p>"}</div>
  `);
}

function showTitik(p) {
  if (p.geometry) {
    /* noop */
  }
  const latlng = findFeatureLatLng(p.id) || findFeatureLatLng(p.nama);
  if (latlng) state.map.flyTo(latlng, 10, { duration: 0.7 });
  const objek = DATA.objek.records.find(
    (o) => o.id === p.id || (o.nama || "").toLowerCase() === String(p.nama || "").toLowerCase()
  );
  setDetail(`
    <p class="eyebrow">Titik objek / proksi</p>
    <h1>${escapeHtml(p.nama || objek?.nama || "Objek")}</h1>
    <p class="lead">${escapeHtml(p.catatan || objek?.kaitan_agrinas || "Titik proksi analisis, bukan poligon legal.")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Kab/Kota</label>${escapeHtml(p.kab_kota || objek?.kab_kota || "–")}</div>
      <div class="meta-item"><label>Tipe</label>${escapeHtml(p.tipe || objek?.lapisan || "–")}</div>
      <div class="meta-item"><label>Prioritas</label><span class="badge ${escapeAttr(p.prioritas || objek?.prioritas || "")}">${escapeHtml(p.prioritas || objek?.prioritas || "–")}</span></div>
      <div class="meta-item"><label>Polres</label>${escapeHtml(p.polres_proksi || "–")}</div>
      <div class="meta-item"><label>Kredibilitas</label>${escapeHtml(objek?.status_kredibilitas || "–")}</div>
      <div class="meta-item"><label>Sumber</label>${escapeHtml(p.sumber || objek?.sumber || "–")}</div>
    </div>
  `);
}

function showKoridor(p) {
  setDetail(`
    <p class="eyebrow">Koridor spasial</p>
    <h1>${escapeHtml(p.nama || "Koridor")}</h1>
    <p class="lead">${escapeHtml(p.karakter || "Agregat kab/kota dengan sinyal Agrinas–Satgas yang saling terkait.")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Anggota kab</label>${escapeHtml(p.anggota_kab || "–")}</div>
      <div class="meta-item"><label>Polres</label>${escapeHtml(p.polres_proksi || "–")}</div>
      <div class="meta-item"><label>Prioritas peta</label><span class="badge ${escapeAttr(p.prioritas || "")}">${escapeHtml(p.prioritas || "–")}</span></div>
    </div>
  `);
}

function caseCard(k) {
  return `<article class="case-card">
    <strong>${escapeHtml(k.jenis || k.kategori || k.id || "Kasus")}</strong>
    <p>${escapeHtml(truncate(k.uraian || k.lokasi || "", 160))}</p>
    <p style="margin-top:.35rem"><small>${escapeHtml([k.tahun, k.perusahaan, k.status].filter(Boolean).join(" · "))}</small></p>
  </article>`;
}

function objCard(o) {
  return `<article class="obj-card">
    <strong>${escapeHtml(o.nama || o.id)}</strong>
    <p>${escapeHtml([o.lapisan, o.prioritas, o.status_kredibilitas].filter(Boolean).join(" · "))}</p>
  </article>`;
}

function findFeatureLatLng(idOrName) {
  if (!idOrName) return null;
  const f = (DATA.layers.features || []).find((x) => {
    const p = x.properties || {};
    return (
      p.id === idOrName ||
      String(p.nama || "").toLowerCase() === String(idOrName).toLowerCase()
    );
  });
  if (f?.geometry?.type === "Point") {
    const [x, y] = f.geometry.coordinates;
    return [y, x];
  }
  return null;
}

const ALIAS = {
  "polres rokan hulu": ["polres rohul", "rohul", "rokan hulu"],
  "polres rokan hilir": ["polres rohil", "rohil", "rokan hilir"],
  "polres indragiri hulu": ["polres inhu", "inhu", "indragiri hulu"],
  "polres indragiri hilir": ["polres inhil", "inhil", "indragiri hilir"],
  "polres kuantan singingi": ["polres kuansing", "kuansing", "kuantan singingi"],
  "polres kepulauan meranti": ["polres meranti", "kepulauan meranti", "kep. meranti"],
  "polres bengkalis": ["bengkalis"],
  "polres kampar": ["kampar"],
  "polres pelalawan": ["pelalawan"],
  "polres siak": ["siak"],
  "polres dumai": ["dumai"],
  "polres pekanbaru": ["pekanbaru"],
};

function tokensFor(name) {
  const raw = String(name || "").toLowerCase().trim();
  if (!raw) return [];
  const out = new Set([raw, raw.replace(/^polres\s+/, ""), raw.replace(/^kab\.?\s+/, ""), raw.replace(/^kota\s+/, "")]);
  Object.entries(ALIAS).forEach(([canon, aliases]) => {
    if (raw === canon || aliases.some((a) => raw.includes(a) || a.includes(raw))) {
      out.add(canon);
      aliases.forEach((a) => out.add(a));
    }
  });
  return [...out];
}

function matchWilayah(a, b) {
  if (!a || !b) return false;
  const A = tokensFor(a);
  const B = tokensFor(b);
  return A.some((x) => B.some((y) => x.includes(y) || y.includes(x)));
}

function renderStory() {
  const top = DATA.polres.records.slice(0, 3);
  const atlasHits = (DATA.konsesi.atlas_match.records || []).filter((r) =>
    String(r.status || "").toLowerCase().includes("cocok")
  ).length;
  const kritis = DATA.objek.records.filter((o) =>
    String(o.prioritas || "").toLowerCase().includes("kritis")
  ).length;
  document.getElementById("storyGrid").innerHTML = [
    {
      t: "Koridor panas",
      h: top.map((p) => p.polres.replace(/^Polres\s+/i, "")).join(", "),
      p: "Tiga Polres teratas early-warning menggabungkan densitas objek Agrinas/KSO, liputan konflik baru, dan aksi massa.",
    },
    {
      t: "Objek prioritas",
      h: `${kritis || "Beberapa"} objek kritis`,
      p: "Master list Agrinas–Satgas memisahkan pengelola, mitra KSO, eks lahan, dan kawasan (termasuk sinyal TNTN).",
    },
    {
      t: "Celah legal–spasial",
      h: `${DATA.konsesi.kepmenhut_36_2025.total} subjek Kepmenhut`,
      p: "Tabulasi 36/2025 + match GFW/BPS menjelaskan siapa yang berproses, ditolak, atau belum lengkap — terpisah dari bukti deforestasi Atlas.",
    },
    {
      t: "Jembatan ke Atlas",
      h: `${atlasHits || DATA.konsesi.atlas_match.total} nama tercocokkan`,
      p: "Lapisan konsesi Nusantara Atlas dipakai sebagai bukti satelit; workspace ini memegang aktor, konflik, dan status penanganan.",
    },
  ]
    .map(
      (s, i) => `
      <article class="story-card" style="animation-delay:${i * 0.08}s">
        <p class="eyebrow">${s.t}</p>
        <h3>${escapeHtml(s.h)}</h3>
        <p>${escapeHtml(s.p)}</p>
      </article>`
    )
    .join("");
}

function setupTabs() {
  /* data tables handled separately */
}

function setupNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.view = btn.dataset.view;
      const stage = document.getElementById("mapStage") || document.querySelector(".stage");
      const story = document.getElementById("storyView");
      const data = document.getElementById("dataView");
      stage.hidden = state.view !== "peta";
      story.hidden = state.view !== "cerita";
      data.hidden = state.view !== "data";
      document.body.classList.toggle("is-scroll", state.view !== "peta");
      if (state.view === "peta") setTimeout(() => state.map?.invalidateSize(), 80);
    });
  });
  document.getElementById("detailClose").addEventListener("click", () => {
    document.getElementById("detailPanel").classList.remove("is-open");
  });
}

function setupFilters() {
  document.getElementById("priorityFilters").addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    document.querySelectorAll("#priorityFilters .chip").forEach((c) => c.classList.remove("is-on"));
    btn.classList.add("is-on");
    state.priority = btn.dataset.priority;
    renderPolres();
  });
}

function setupSearch() {
  const input = document.getElementById("searchInput");
  const box = document.getElementById("searchResults");
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = input.value.trim().toLowerCase();
      if (q.length < 2) {
        box.hidden = true;
        return;
      }
      const hits = [];
      DATA.kab.records.forEach((k) => {
        if ((k.kab_kota || "").toLowerCase().includes(q))
          hits.push({ type: "kab", label: k.kab_kota, sub: "Kabupaten/Kota", ref: k.kab_kota });
      });
      DATA.polres.records.forEach((p) => {
        if ((p.polres || "").toLowerCase().includes(q))
          hits.push({ type: "polres", label: p.polres, sub: `Skor ${p.skor}`, ref: p.polres });
      });
      DATA.objek.records.slice(0, 200).forEach((o) => {
        if ((o.nama || "").toLowerCase().includes(q))
          hits.push({ type: "objek", label: o.nama, sub: o.kab_kota || o.lapisan, ref: o.id });
      });
      box.innerHTML = hits
        .slice(0, 12)
        .map(
          (h) =>
            `<button type="button" data-type="${h.type}" data-ref="${escapeAttr(h.ref)}"><strong>${escapeHtml(h.label)}</strong><small>${escapeHtml(h.sub || "")}</small></button>`
        )
        .join("") || `<button type="button">Tidak ada hasil</button>`;
      box.hidden = false;
      box.querySelectorAll("button").forEach((b) => {
        b.addEventListener("click", () => {
          box.hidden = true;
          input.value = "";
          if (b.dataset.type === "kab") showKabupaten(b.dataset.ref);
          if (b.dataset.type === "polres") showPolres(b.dataset.ref);
          if (b.dataset.type === "objek") {
            const o = DATA.objek.records.find((x) => x.id === b.dataset.ref);
            showTitik({ ...o, nama: o?.nama, id: o?.id });
          }
        });
      });
    }, 160);
  });
}

function setupDataTables() {
  const tabs = [
    { id: "kasus", label: "Kasus konflik", rows: () => DATA.kasus.records, cols: ["id", "kab_kota", "polres", "tahun", "jenis", "perusahaan", "status", "uraian"] },
    { id: "objek", label: "Objek Agrinas", rows: () => DATA.objek.records, cols: ["id", "nama", "lapisan", "kab_kota", "prioritas", "status_kredibilitas", "kaitan_agrinas"] },
    { id: "polres", label: "Ranking Polres", rows: () => DATA.polres.records, cols: ["peringkat", "polres", "skor", "kategori", "n_agrinas", "n_aksi_massa", "alasan"] },
    { id: "kab", label: "Kab/Kota", rows: () => DATA.kab.records, cols: ["kab_kota", "kategori_peta", "skor_komposit", "polres_proksi", "objek_sinyal_utama", "ketidakpastian"] },
    { id: "atlas", label: "Cocokan Atlas", rows: () => DATA.konsesi.atlas_match.records, cols: ["atlas_nama", "tahun", "tipe", "status", "nama_lokal", "area_ha"] },
  ];
  const tabBar = document.getElementById("tableTabs");
  let active = tabs[0];
  const paintTabs = () => {
    tabBar.innerHTML = tabs
      .map(
        (t) =>
          `<button class="chip ${t.id === active.id ? "is-on" : ""}" data-id="${t.id}">${t.label}</button>`
      )
      .join("");
    tabBar.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => {
        active = tabs.find((t) => t.id === b.dataset.id);
        paintTabs();
        paintTable();
      })
    );
  };
  const paintTable = () => {
    const rows = active.rows().slice(0, 400);
    const thead = document.querySelector("#dataTable thead");
    const tbody = document.querySelector("#dataTable tbody");
    thead.innerHTML = `<tr>${active.cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
    tbody.innerHTML = rows
      .map(
        (r) =>
          `<tr>${active.cols
            .map((c) => {
              let v = r[c];
              if (c.includes(".") || (typeof v === "object" && v)) {
                /* nested optional */
              }
              if (c === "uraian" || c === "alasan" || c === "kaitan_agrinas") v = truncate(v, 120);
              return `<td>${escapeHtml(v ?? "")}</td>`;
            })
            .join("")}</tr>`
      )
      .join("");
  };
  paintTabs();
  paintTable();
}

function fmtNum(v) {
  if (v === null || v === undefined || v === "") return "–";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function truncate(s, n) {
  const t = String(s || "");
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

boot().catch((err) => {
  console.error(err);
  document.getElementById("updatedAt").textContent = "Gagal memuat data — jalankan skrip ekspor.";
  document.getElementById("detailContent").innerHTML = `
    <p class="eyebrow">Error</p>
    <h1>Data belum tersedia</h1>
    <p class="lead">${escapeHtml(err.message)}</p>
    <code class="cmd">python website/scripts/export_web_data.py</code>`;
});
