/* Atlas Konflik Sawit Riau — map-first interactive viewer (P1 spatial layers) */

const DATA = {
  meta: null,
  kab: null,
  polres: null,
  objek: null,
  kasus: null,
  perusahaan: null,
  konsesi: null,
  layers: null,
  adm2: null,
  gfw: null,
  analytics: null,
  penertiban: null,
  gfwFull: null,
};

const state = {
  view: "peta",
  priority: "all",
  compare: "all",
  blendOsint: 0.7, // 0 = 100% register, 0.7 = default, 1 = 100% OSINT
  timelineYearMode: "kejadian", // kejadian | disebut
  layerOn: {
    choropleth: true,
    koridor: false,
    densitas_kasus: false,
    objek_titik: true,
    gfw_konsesi: false,
  },
  map: null,
  layerGroups: {},
  selected: null,
};

const COMPARE_PRESETS = {
  all: {
    hint: "Gabungan hemat: choropleth + titik Agrinas. Aktifkan koridor/densitas dari lapisan bila perlu.",
    layers: { choropleth: true, koridor: false, densitas_kasus: false, objek_titik: true, gfw_konsesi: false },
    rank: "polres",
    choroMetric: "polres_blend",
  },
  register: {
    hint: "Register konflik: warna kab = risiko register + densitas kasus (centroid).",
    layers: { choropleth: true, koridor: false, densitas_kasus: true, objek_titik: false, gfw_konsesi: false },
    rank: "register",
    choroMetric: "register",
  },
  agrinas: {
    hint: "Sinyal Agrinas: warna kab = skor OSINT + koridor bbox proksi + titik objek.",
    layers: { choropleth: true, koridor: true, densitas_kasus: false, objek_titik: true, gfw_konsesi: false },
    rank: "agrinas",
    choroMetric: "osint",
  },
  atlas: {
    hint: "Deforestasi Atlas: overlay GFW + cocokan nama. Deep-link ke Nusantara Atlas.",
    layers: { choropleth: false, koridor: false, densitas_kasus: false, objek_titik: false, gfw_konsesi: true },
    rank: "atlas",
    choroMetric: null,
  },
};

/** Kamus metrik — jangan pakai kata “skor” tanpa konteks di UI. */
const METRIC_LABELS = {
  polres_blend: "Skor Polres (blend)",
  register: "Risiko register",
  osint: "Skor OSINT Agrinas",
  kab_komposit: "Skor kab (komposit peta)",
};

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

const colorFor = (level) => {
  const t = String(level || "").toUpperCase();
  if (t.includes("PRIORITAS") || t.includes("SANGAT")) return "#c45620";
  if (t.includes("WASPADA") || t.includes("TINGGI")) return "#d09218";
  return "#2f6a4c";
};

/** Choropleth fill for skor 0–100. Bands match PRIORITAS/WASPADA/PANTAU. */
const CHORO_BREAKS = { high: 70, mid: 40 };

const choroplethColor = (skor) => {
  const s = Number(skor) || 0;
  if (s >= CHORO_BREAKS.high) return "#c45620";
  if (s >= CHORO_BREAKS.mid) return "#d09218";
  return "#2f6a4c";
};

const choroplethBandLabel = (skor) => {
  const s = Number(skor) || 0;
  if (s >= CHORO_BREAKS.high) return `tinggi (≥${CHORO_BREAKS.high})`;
  if (s >= CHORO_BREAKS.mid) return `sedang (${CHORO_BREAKS.mid}–${CHORO_BREAKS.high - 1})`;
  return `rendah (<${CHORO_BREAKS.mid})`;
};

const kategoriFromSkor = (skor) => {
  const s = Number(skor) || 0;
  if (s >= CHORO_BREAKS.high) return "PRIORITAS";
  if (s >= CHORO_BREAKS.mid) return "WASPADA";
  return "PANTAU";
};

const densitasLevelFromSkor = (skor) => {
  const s = Number(skor) || 0;
  if (s >= CHORO_BREAKS.high) return "TINGGI";
  if (s >= CHORO_BREAKS.mid) return "SEDANG";
  return "RENDAH";
};

function findKabByName(nama) {
  const key = String(nama || "").toLowerCase();
  return (
    DATA.kab?.records?.find((k) => (k.kab_kota || "").toLowerCase() === key) ||
    DATA.kab?.records?.find((k) => matchWilayah(k.kab_kota, nama)) ||
    null
  );
}

function findPolresForKab(kab) {
  if (!kab) return null;
  return (
    DATA.polres?.records?.find((p) => matchWilayah(p.polres, kab.polres_proksi)) ||
    DATA.polres?.records?.find((p) => matchWilayah(kab.polres_proksi, p.polres)) ||
    null
  );
}

/** Metrik choropleth mengikuti mode bandingkan — satu sumber kebenaran per view. */
function resolveChoroplethMetric(nama) {
  const kab = findKabByName(nama);
  const polres = findPolresForKab(kab);
  const risk = kab?.risiko_register || {};
  const metricKey = COMPARE_PRESETS[state.compare]?.choroMetric || "polres_blend";

  if (metricKey === "register") {
    const skor = Number(risk.skor ?? polres?.skor_register) || 0;
    return {
      skor,
      metricKey,
      label: METRIC_LABELS.register,
      kategori: risk.level || kategoriFromSkor(skor),
      kab,
      polres,
    };
  }
  if (metricKey === "osint") {
    const skor = Number(polres?.skor_osint) || Number(kab?.sinyal_agrinas) * 20 || 0;
    return {
      skor,
      metricKey,
      label: METRIC_LABELS.osint,
      kategori: kategoriFromSkor(skor),
      kab,
      polres,
    };
  }
  // Gabungan default: skor Polres blend terproyeksi ke kab (mengikuti bobot UI)
  const skor = polres ? blendedPolresSkor(polres) : Number(kab?.skor_komposit) || 0;
  return {
    skor,
    metricKey: "polres_blend",
    label: blendMetricLabel(),
    kategori: kategoriFromSkor(skor),
    kab,
    polres,
  };
}

function blendedPolresSkor(p) {
  if (!p) return 0;
  const w = Number(state.blendOsint);
  const o = Number(p.skor_osint) || 0;
  const r = Number(p.skor_register) || 0;
  if (Number.isNaN(w)) return Number(p.skor) || 0;
  return w * o + (1 - w) * r;
}

function blendMetricLabel() {
  const w = Number(state.blendOsint);
  if (w >= 0.99) return "Skor OSINT (100%)";
  if (w <= 0.01) return "Skor register (100%)";
  return `Skor Polres (blend ${Math.round(w * 100)}/${Math.round((1 - w) * 100)})`;
}

window.blendedPolresSkor = blendedPolresSkor;
window.getBlendOsint = () => state.blendOsint;

/** Cache-bust for GitHub Pages / local static server so meta+layers refresh with UI. */
const DATA_VER = "f3b";

async function loadJSON(path) {
  const url = path.includes("?") ? path : `${path}?v=${DATA_VER}`;
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Gagal memuat ${path}`);
  return res.json();
}

/** Kartu preview hover peta — satu template untuk semua lapisan. */
function mapPreviewHtml({
  eyebrow = "",
  title = "",
  skor = null,
  level = "",
  metricLabel = "",
  metaLines = [],
  polres = "",
  cta = "Klik untuk detail",
} = {}) {
  const hasSkor = skor != null && skor !== "" && !Number.isNaN(Number(skor));
  const scoreBlock = hasSkor
    ? `<div class="map-preview__score">
        <div class="map-preview__score-main">
          <span class="map-preview__score-num">${escapeHtml(fmtNum(skor))}</span>
          ${level ? `<span class="badge ${escapeAttr(level)}">${escapeHtml(level)}</span>` : ""}
        </div>
        ${metricLabel ? `<div class="map-preview__metric">${escapeHtml(metricLabel)}</div>` : ""}
      </div>`
    : level
      ? `<div class="map-preview__score"><span class="badge ${escapeAttr(level)}">${escapeHtml(level)}</span></div>`
      : "";
  const metas = (metaLines || [])
    .filter(Boolean)
    .map((line) => `<div class="map-preview__meta">${escapeHtml(line)}</div>`)
    .join("");
  const polresBtn = polres
    ? `<button type="button" class="map-preview__link" data-action="polres" data-polres="${escapeAttr(polres)}">Buka Polres</button>`
    : "";
  return `<div class="map-preview__card">
    ${eyebrow ? `<p class="map-preview__eyebrow">${escapeHtml(eyebrow)}</p>` : ""}
    <p class="map-preview__title">${escapeHtml(title)}</p>
    ${scoreBlock}
    ${metas}
    <div class="map-preview__footer"><span>${escapeHtml(cta)}</span>${polresBtn}</div>
  </div>`;
}

function bindMapPreview(layer, html) {
  if (layer.getTooltip && layer.getTooltip()) layer.unbindTooltip();
  layer.bindTooltip(html, {
    className: "map-preview",
    direction: "top",
    opacity: 1,
    sticky: true,
    interactive: true,
  });
}

function setupMapPreviewActions() {
  if (setupMapPreviewActions._ready) return;
  setupMapPreviewActions._ready = true;
  document.addEventListener(
    "click",
    (e) => {
      const btn = e.target.closest?.("[data-action='polres']");
      if (!btn || !btn.closest(".leaflet-tooltip.map-preview, .map-preview__card")) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof L !== "undefined") L.DomEvent.stop(e);
      const nama = btn.dataset.polres;
      if (nama) showPolres(nama);
    },
    true
  );
}

async function boot() {
  const [meta, kab, polres, objek, kasus, perusahaan, konsesi, layers, adm2, analytics, penertiban, gfwFull] =
    await Promise.all([
      loadJSON("data/meta.json"),
      loadJSON("data/kab_kota.json"),
      loadJSON("data/polres.json"),
      loadJSON("data/objek_agrinas.json"),
      loadJSON("data/kasus.json"),
      loadJSON("data/perusahaan.json"),
      loadJSON("data/konsesi.json"),
      loadJSON("data/layers.geojson"),
      loadJSON("data/adm2_riau.geojson"),
      loadJSON("data/analytics.json"),
      loadJSON("data/penertiban.json"),
      loadJSON("data/konsesi_gfw_full.json"),
    ]);
  Object.assign(DATA, {
    meta,
    kab,
    polres,
    objek,
    kasus,
    perusahaan,
    konsesi,
    layers,
    adm2,
    gfw: null,
    analytics,
    penertiban,
    gfwFull,
  });

  (meta.layers || []).forEach((l) => {
    state.layerOn[l.id] = !!l.default;
  });

  document.getElementById("updatedAt").textContent =
    `Diperbarui ${formatDate(meta.updated_at)} · ${meta.counts.kasus_konflik} kasus · ${meta.counts.objek_agrinas} objek`;

  state.timelineYearMode = DATA.analytics?.timeline?.default_mode || "kejadian";

  renderStats();
  renderLayers();
  renderRankPanel();
  initMap();
  renderStory();
  setupSearch();
  setupNav();
  setupFilters();
  setupCompareMode();
  setupBlendWeight();
  setupMapPreviewActions();
  setupDataTables();
  setupAnalyticsControls?.();
  setupPenertibanControls?.();
  syncTimelineYearModeUI();
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function renderStats() {
  const c = DATA.meta.counts || {};
  const cov = DATA.polres?.coverage || {};
  const mapped = cov.total_entri_terpetakan ?? c.entri_terpetakan ?? "–";
  const unmapped = cov.entri_tidak_terpetakan ?? c.entri_tidak_terpetakan ?? "–";
  const prioritas = DATA.polres.records.filter((p) => kategoriFromSkor(blendedPolresSkor(p)) === "PRIORITAS").length;
  document.getElementById("statsGrid").innerHTML = [
    ["kasus", "Kasus konflik", c.kasus_konflik],
    ["map", "Terpetakan Polres", mapped],
    ["unmap", "Lintas Riau / n/a", unmapped],
    ["prio", "Polres prioritas*", prioritas],
  ]
    .map(([, label, val]) => `<div class="stat"><strong>${val ?? "–"}</strong><span>${label}</span></div>`)
    .join("");

  const methodEl = document.getElementById("methodNote");
  if (methodEl) {
    const disc =
      DATA.meta?.methodology?.disclaimer ||
      DATA.polres?.model?.catatan ||
      "Skor = indeks liputan+objek+register — bukan vonis operasional.";
    methodEl.textContent = disc;
  }
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
    el.addEventListener("change", async () => {
      state.layerOn[el.dataset.layer] = el.checked;
      if (el.dataset.layer === "gfw_konsesi" && el.checked) {
        el.disabled = true;
        try {
          await ensureGfwLayer();
        } finally {
          el.disabled = false;
        }
      }
      refreshLayerVisibility();
    });
  });
}

function renderPolres() {
  renderRankPanel();
}

function renderRankPanel() {
  const ol = document.getElementById("polresList");
  const title = document.getElementById("rankTitle");
  const mode = COMPARE_PRESETS[state.compare]?.rank || "polres";

  if (mode === "atlas") {
    if (title) title.textContent = "Cocokan Atlas";
    const rows = (DATA.konsesi?.atlas_match?.records || [])
      .filter((r) => String(r.status || "").toLowerCase().includes("cocok"))
      .slice(0, 16);
    ol.innerHTML = rows
      .map((r, i) => {
        const link = atlasDeepLink(r.atlas_nama || r.nama_lokal);
        return `<li>
          <button type="button" data-atlas="${escapeAttr(r.atlas_nama || "")}" data-lokal="${escapeAttr(r.nama_lokal || "")}">
            <span class="n pantau">${i + 1}</span>
            <span>
              <strong>${escapeHtml(r.atlas_nama || "–")}</strong><br/>
              <small>${escapeHtml(r.nama_lokal || r.tipe || "")}</small>
            </span>
            <span class="score"><a class="rank-ext" href="${escapeAttr(link.href)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">↗</a></span>
          </button>
        </li>`;
      })
      .join("");
    ol.querySelectorAll("button[data-atlas]").forEach((btn) => {
      btn.addEventListener("click", () => showAtlasMatch(btn.dataset.atlas, btn.dataset.lokal));
    });
    return;
  }

  if (mode === "agrinas") {
    if (title) title.textContent = "Objek Agrinas";
    const rows = [...DATA.objek.records]
      .filter((o) => {
        const p = String(o.prioritas || "").toUpperCase();
        return state.priority === "all" || p.includes(state.priority) || (state.priority === "PRIORITAS" && p.includes("KRITIS"));
      })
      .sort((a, b) => {
        const wa = String(a.prioritas || "").toLowerCase().includes("kritis") ? 0 : 1;
        const wb = String(b.prioritas || "").toLowerCase().includes("kritis") ? 0 : 1;
        return wa - wb;
      })
      .slice(0, 16);
    ol.innerHTML = rows
      .map(
        (o, i) => `<li>
        <button type="button" data-objek="${escapeAttr(o.id || o.nama || "")}">
          <span class="n ${escapeAttr(o.prioritas || "pantau")}">${i + 1}</span>
          <span>
            <strong>${escapeHtml(truncate(o.nama || o.id, 42))}</strong><br/>
            <small>${escapeHtml([o.lapisan, o.kab_kota].filter(Boolean).join(" · "))}</small>
          </span>
          <span class="score">${escapeHtml(o.prioritas || "–")}</span>
        </button>
      </li>`
      )
      .join("");
    ol.querySelectorAll("button[data-objek]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const o = DATA.objek.records.find((x) => x.id === btn.dataset.objek || x.nama === btn.dataset.objek);
        if (o) showTitik({ ...o, nama: o.nama, id: o.id });
      });
    });
    return;
  }

  if (title) title.textContent = mode === "register" ? "Ranking register" : "Ranking Polres";
  let rows = [...DATA.polres.records];
  if (mode === "register") {
    rows.sort(
      (a, b) =>
        (Number(b.skor_register) || Number(b.n_recent) || 0) - (Number(a.skor_register) || Number(a.n_recent) || 0)
    );
  } else {
    rows.sort((a, b) => blendedPolresSkor(b) - blendedPolresSkor(a));
  }
  rows = rows.filter((p) => {
    if (state.priority === "all") return true;
    const primary = mode === "register" ? Number(p.skor_register) || 0 : blendedPolresSkor(p);
    return kategoriFromSkor(primary) === state.priority || p.kategori === state.priority;
  });
  ol.innerHTML = rows
    .map((p, idx) => {
      const primary = Number(mode === "register" ? p.skor_register || p.skor : blendedPolresSkor(p)) || 0;
      const kat = kategoriFromSkor(primary);
      const rankN = idx + 1;
      return `
      <li>
        <button type="button" data-polres="${escapeAttr(p.polres)}">
          <span class="n ${escapeAttr(kat)}">${rankN}</span>
          <span>
            <strong>${escapeHtml(p.polres.replace(/^Polres\s+/i, ""))}</strong><br/>
            <small>OSINT ${fmtNum(p.skor_osint)} · Reg ${fmtNum(p.skor_register)}</small>
          </span>
          <span class="score" title="${mode === "register" ? "Risiko register" : blendMetricLabel()}">${primary.toFixed(0)}</span>
        </button>
      </li>`;
    })
    .join("");
  ol.querySelectorAll("button[data-polres]").forEach((btn) => {
    btn.addEventListener("click", () => showPolres(btn.dataset.polres));
  });
}

function initMap() {
  const [lon, lat] = DATA.meta.center;
  state.map = L.map("map", { zoomControl: false, attributionControl: true }).setView(
    [lat, lon],
    DATA.meta.zoom || 8
  );
  L.control.zoom({ position: "topright" }).addTo(state.map);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(state.map);

  state.layerGroups = {
    choropleth: L.layerGroup(),
    koridor: L.layerGroup(),
    densitas_kasus: L.layerGroup(),
    objek_titik: L.layerGroup(),
    gfw_konsesi: L.layerGroup(),
  };

  // Choropleth ADM2 — warna mengikuti mode bandingkan (refreshChoroplethForMode)
  state.choroplethLayers = [];
  L.geoJSON(DATA.adm2, {
    style: (f) => {
      const m = resolveChoroplethMetric((f.properties || {}).nama);
      return {
        color: "#163528",
        weight: 1.1,
        fillColor: choroplethColor(m.skor),
        fillOpacity: 0.55,
      };
    },
    onEachFeature: (f, layer) => {
      const p = f.properties || {};
      state.choroplethLayers.push({ layer, nama: p.nama });
      const bindChoroTooltip = () => {
        const m = resolveChoroplethMetric(p.nama);
        const level = m.kategori || kategoriFromSkor(m.skor);
        const polresNama = m.polres?.polres || m.kab?.polres_proksi || "";
        bindMapPreview(
          layer,
          mapPreviewHtml({
            eyebrow: "Kab/kota",
            title: p.nama || "",
            skor: m.skor,
            level,
            metricLabel: m.label,
            metaLines: [polresNama ? String(polresNama) : ""].filter(Boolean),
            polres: polresNama,
          })
        );
      };
      bindChoroTooltip();
      layer.on({
        mouseover: (e) => e.target.setStyle({ weight: 2.2, fillOpacity: 0.72 }),
        mouseout: (e) => {
          const m = resolveChoroplethMetric(p.nama);
          e.target.setStyle({
            weight: 1.1,
            fillOpacity: 0.55,
            fillColor: choroplethColor(m.skor),
          });
        },
        click: () => showKabupaten(p.nama),
      });
      layer._bindChoroTooltip = bindChoroTooltip;
      state.layerGroups.choropleth.addLayer(layer);
    },
  });
  updateMapLegend();

  // GFW overlay is lazy-loaded (TopoJSON) when toggled on
  state.gfwReady = false;
  state.gfwLoading = null;

  // Point / corridor layers from layers.geojson
  (DATA.layers.features || []).forEach((f) => {
    const p = f.properties || {};
    const layerId = p.layer || "objek_titik";

    if (layerId === "koridor" && (f.geometry?.type === "Polygon" || f.geometry?.type === "MultiPolygon")) {
      const poly = L.geoJSON(f, {
        style: {
          color: "#163528",
          weight: 1.6,
          fillColor: "#163528",
          fillOpacity: 0.08,
          dashArray: "5 4",
        },
      });
      poly.on("click", () => showKoridor(p));
      const geomLabel = String(p.geom_source || "hull").replace(/_/g, " ");
      bindMapPreview(
        poly,
        mapPreviewHtml({
          eyebrow: "Koridor proksi",
          title: p.nama || "Koridor",
          level: p.prioritas || "",
          metaLines: [
            `${geomLabel} · ${fmtNum(p.n_titik)} titik`,
            p.polres_proksi || "",
          ],
          polres: p.polres_proksi || "",
        })
      );
      state.layerGroups.koridor.addLayer(poly);
      return;
    }

    if (f.geometry?.type !== "Point") return;
    const [x, y] = f.geometry.coordinates;

    // Defense: jangan render centroid REF meski masih ada di data lama
    if (
      layerId === "objek_titik" &&
      (String(p.prioritas || "").toUpperCase().includes("REF") ||
        /centroid/i.test(String(p.tipe || "")) ||
        /centroid/i.test(String(p.nama || "")))
    ) {
      return;
    }

    if (layerId === "densitas_kasus") {
      const n = Number(p.n_kasus) || 1;
      const skorKab = Number(p.skor) || 0;
      const level = densitasLevelFromSkor(skorKab);
      const radius = Math.max(10, Math.min(42, 8 + Math.sqrt(n) * 6));
      const marker = L.circleMarker([y, x], {
        radius,
        color: choroplethColor(skorKab),
        weight: 1.5,
        fillColor: "rgba(196,86,32,0.28)",
        fillOpacity: 0.7,
      });
      const kab = findKabByName(p.nama);
      const polresRec = findPolresForKab(kab);
      const polresNama = polresRec?.polres || kab?.polres_proksi || p.polres_proksi || "";
      bindMapPreview(
        marker,
        mapPreviewHtml({
          eyebrow: "Densitas kasus",
          title: p.nama || "",
          skor: skorKab,
          level,
          metricLabel: "Skor densitas (skor kab)",
          metaLines: [
            `${n} kasus · proksi centroid`,
            polresNama ? polresNama.replace(/^Polres\s+/i, "Polres ") : "",
          ].filter(Boolean),
          polres: polresNama,
        })
      );
      marker.on("click", () => showKabupaten(p.nama));
      state.layerGroups.densitas_kasus.addLayer(marker);
      return;
    }

    const level = p.prioritas || p.level_risiko || p.kategori || "PANTAU";
    const marker = L.circleMarker([y, x], {
      radius: 7,
      color: "#fff",
      weight: 1.5,
      fillColor: colorFor(level),
      fillOpacity: 0.92,
    });
    bindMapPreview(
      marker,
      mapPreviewHtml({
        eyebrow: "Objek Agrinas",
        title: p.nama || p.id || "Objek",
        level,
        metaLines: [p.tipe || "Titik proksi", p.polres_proksi || p.kab_kota || ""].filter(Boolean),
        polres: p.polres_proksi || "",
      })
    );
    marker.on("click", () => showTitik(p));
    (state.layerGroups[layerId] || state.layerGroups.objek_titik).addLayer(marker);
  });

  refreshLayerVisibility();
  setTimeout(() => state.map.invalidateSize(), 120);
}

function refreshLayerVisibility() {
  // draw order: gfw under choropleth under points
  const order = ["gfw_konsesi", "choropleth", "koridor", "densitas_kasus", "objek_titik"];
  order.forEach((id) => {
    const group = state.layerGroups[id];
    if (!group) return;
    if (state.map.hasLayer(group)) state.map.removeLayer(group);
    if (state.layerOn[id]) group.addTo(state.map);
  });
}

function updateMapLegend() {
  const el = document.getElementById("mapLegend");
  if (!el) return;
  const metricKey = COMPARE_PRESETS[state.compare]?.choroMetric;
  const metricName = metricKey ? METRIC_LABELS[metricKey] : "Skor kab";
  el.innerHTML = `
    <strong>Legenda</strong>
    <div class="legend-metric">${escapeHtml(metricName)}</div>
    <div><span class="swatch choro high"></span> Tinggi (≥${CHORO_BREAKS.high})</div>
    <div><span class="swatch choro mid"></span> Sedang (${CHORO_BREAKS.mid}–${CHORO_BREAKS.high - 1})</div>
    <div><span class="swatch choro low"></span> Rendah (&lt;${CHORO_BREAKS.mid})</div>
    <div><span class="swatch densitas"></span> Densitas kasus</div>
    <div><span class="swatch koridor"></span> Koridor proksi (hull)</div>
    <div><span class="swatch gfw"></span> Konsesi GFW</div>
  `;
}

function refreshChoroplethForMode() {
  (state.choroplethLayers || []).forEach(({ layer, nama }) => {
    const m = resolveChoroplethMetric(nama);
    layer.setStyle({
      color: "#163528",
      weight: 1.1,
      fillColor: choroplethColor(m.skor),
      fillOpacity: 0.55,
    });
    if (typeof layer._bindChoroTooltip === "function") layer._bindChoroTooltip();
  });
  updateMapLegend();
}

async function ensureGfwLayer() {
  if (state.gfwReady) return;
  if (state.gfwLoading) return state.gfwLoading;

  state.gfwLoading = (async () => {
    let geo = null;
    try {
      const topo = await loadJSON("data/gfw_konsesi.topojson");
      const objName = Object.keys(topo.objects || {})[0];
      if (!objName || typeof topojson?.feature !== "function") {
        throw new Error("TopoJSON client/object missing");
      }
      geo = topojson.feature(topo, topo.objects[objName]);
    } catch (err) {
      console.warn("TopoJSON GFW gagal, coba GeoJSON:", err);
      try {
        geo = await loadJSON("data/gfw_konsesi.geojson");
      } catch (err2) {
        console.error("Overlay GFW tidak tersedia", err2);
        return;
      }
    }
    DATA.gfw = geo;

    L.geoJSON(geo, {
      style: {
        color: "#5b7c65",
        weight: 0.55,
        fillColor: "#6f8f78",
        fillOpacity: 0.2,
      },
      onEachFeature: (f, layer) => {
        const p = f.properties || {};
        bindMapPreview(
          layer,
          mapPreviewHtml({
            eyebrow: "Konsesi GFW",
            title: p.name || p.company || "Konsesi",
            metaLines: [`${fmtNum(p.area_ha)} ha`, p.group || p.type || ""].filter(Boolean),
            cta: "Klik untuk detail",
          })
        );
        layer.on("click", () => showGfw(p));
        state.layerGroups.gfw_konsesi.addLayer(layer);
      },
    });
    state.gfwReady = true;
  })();

  try {
    await state.gfwLoading;
  } finally {
    state.gfwLoading = null;
  }
}

function openDetail() {
  document.getElementById("detailPanel").classList.add("is-open");
}

function setDetail(html) {
  document.getElementById("detailContent").innerHTML = html;
  openDetail();
}

function showKabupaten(nama) {
  const kab =
    DATA.kab.records.find((k) => (k.kab_kota || "").toLowerCase() === String(nama || "").toLowerCase()) ||
    DATA.kab.records.find((k) => matchWilayah(k.kab_kota, nama));
  if (!kab) return;
  state.selected = { type: "kab", id: kab.id };
  if (kab.lat && kab.lon) state.map.flyTo([kab.lat, kab.lon], 9, { duration: 0.75 });

  const kasus = DATA.kasus.records
    .filter((k) => matchWilayah(k.kab_kota, kab.kab_kota) || matchWilayah(k.polres, kab.polres_proksi))
    .slice(0, 8);
  const objek = DATA.objek.records.filter((o) => matchWilayah(o.kab_kota, kab.kab_kota)).slice(0, 8);
  const risk = kab.risiko_register || {};
  const polres = findPolresForKab(kab);
  const active = resolveChoroplethMetric(kab.kab_kota);

  setDetail(`
    <p class="eyebrow">Kabupaten / Kota</p>
    <h1>${escapeHtml(kab.kab_kota)}</h1>
    <p class="lead">${escapeHtml(kab.catatan_peta || "Metrik peta mengikuti mode bandingkan; angka di bawah adalah kamus lengkap.")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Metrik aktif (mode)</label><strong>${escapeHtml(active.label)} ${fmtNum(active.skor)}</strong> <span class="badge ${escapeAttr(active.kategori || "")}">${escapeHtml(active.kategori || choroplethBandLabel(active.skor))}</span></div>
      <div class="meta-item"><label>${escapeHtml(METRIC_LABELS.kab_komposit)}</label><strong>${fmtNum(kab.skor_komposit)}</strong></div>
      <div class="meta-item"><label>${escapeHtml(METRIC_LABELS.polres_blend)}</label><strong>${fmtNum(polres?.skor)}</strong> <span class="badge ${escapeAttr(polres?.kategori || "")}">${escapeHtml(polres?.kategori || "–")}</span></div>
      <div class="meta-item"><label>${escapeHtml(METRIC_LABELS.osint)} / ${escapeHtml(METRIC_LABELS.register)}</label>${fmtNum(polres?.skor_osint)} / ${fmtNum(risk.skor ?? polres?.skor_register)}</div>
      <div class="meta-item"><label>Jumlah kasus (proksi)</label><strong>${fmtNum(kab.n_kasus)}</strong></div>
      <div class="meta-item"><label>Polres proksi</label>${escapeHtml(kab.polres_proksi || "–")}</div>
      <div class="meta-item"><label>Objek sinyal utama</label>${escapeHtml(kab.objek_sinyal_utama || "–")}</div>
      <div class="meta-item"><label>Hotspot kecamatan</label>${escapeHtml(kab.hotspot_kecamatan || "–")}</div>
      <div class="meta-item"><label>Sawit di KH (ha)</label>${fmtNum(kab.klhk_korp_kh_2022_ha)}</div>
    </div>
    ${risk.driver_utama ? `<p><strong>Driver register:</strong> ${escapeHtml(risk.driver_utama)}</p>` : ""}
    <h2 class="section-label">Kasus terkait</h2>
    <div class="case-list">${kasus.map(caseCard).join("") || "<p class='lead'>Belum ada kasus terpetakan.</p>"}</div>
    <h2 class="section-label">Objek Agrinas</h2>
    <div class="obj-list">${objek.map(objCard).join("") || "<p class='lead'>Tidak ada objek dengan kab/kota eksplisit.</p>"}</div>
  `);
}

function showPolres(nama) {
  const p =
    DATA.polres.records.find((x) => x.polres === nama) ||
    DATA.polres.records.find((x) => matchWilayah(x.polres, nama));
  if (!p) return;
  const kab = DATA.kab.records.find((k) => matchWilayah(k.polres_proksi, p.polres));
  if (kab?.lat && kab?.lon) state.map.flyTo([kab.lat, kab.lon], 9, { duration: 0.75 });
  const kasus = DATA.kasus.records.filter((k) => matchWilayah(k.polres, p.polres)).slice(0, 10);
  setDetail(`
    <p class="eyebrow">Early-warning Polres</p>
    <h1>${escapeHtml(p.polres)}</h1>
    <p class="lead">${escapeHtml(p.alasan || "")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Peringkat model</label><strong>#${p.peringkat}</strong></div>
      <div class="meta-item"><label>${escapeHtml(blendMetricLabel())}</label><strong>${fmtNum(blendedPolresSkor(p))}</strong> <span class="badge ${escapeAttr(kategoriFromSkor(blendedPolresSkor(p)))}">${escapeHtml(kategoriFromSkor(blendedPolresSkor(p)))}</span></div>
      <div class="meta-item"><label>${escapeHtml(METRIC_LABELS.osint)}</label><strong>${fmtNum(p.skor_osint)}</strong></div>
      <div class="meta-item"><label>${escapeHtml(METRIC_LABELS.register)}</label><strong>${fmtNum(p.skor_register)}</strong> <span class="badge ${escapeAttr(kategoriFromSkor(p.skor_register))}">${escapeHtml(kategoriFromSkor(p.skor_register))}</span></div>
      <div class="meta-item"><label>Aksi massa · Kekerasan</label>${fmtNum(p.n_aksi_massa)} · ${fmtNum(p.n_kekerasan)}</div>
      <div class="meta-item"><label>Objek Agrinas/KSO</label>${fmtNum(p.n_agrinas)}</div>
      <div class="meta-item"><label>Entri 2024+</label>${fmtNum(p.n_recent)}</div>
    </div>
    <p class="muted small">${escapeHtml(DATA.polres?.model?.catatan || "Indeks liputan+objek+register — bukan vonis operasional.")}</p>
    <h2 class="section-label">Kasus di wilayah Polres</h2>
    <div class="case-list">${kasus.map(caseCard).join("") || "<p class='lead'>Tidak ada kasus terfilter.</p>"}</div>
  `);
}
window.showPolres = showPolres;

function showTitik(p) {
  const latlng = findFeatureLatLng(p.id) || findFeatureLatLng(p.nama);
  if (latlng) state.map.flyTo(latlng, 10, { duration: 0.65 });
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
    <p class="eyebrow">Koridor proksi (hull/bbox)</p>
    <h1>${escapeHtml(p.nama || "Koridor")}</h1>
    <p class="lead">${escapeHtml(p.karakter || "Hull/envelope dari titik objek — bukan koridor geografis resmi.")}</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Anggota kab</label>${escapeHtml(p.anggota_kab || "–")}</div>
      <div class="meta-item"><label>Polres</label>${escapeHtml(p.polres_proksi || "–")}</div>
      <div class="meta-item"><label>Geometri</label>${escapeHtml(p.geom_source || "proksi")} · ${fmtNum(p.n_titik)} titik</div>
      <div class="meta-item"><label>Prioritas peta</label><span class="badge ${escapeAttr(p.prioritas || "")}">${escapeHtml(p.prioritas || "–")}</span></div>
      <div class="meta-item"><label>Catatan</label>${escapeHtml(p.catatan || "Tetap proksi OSINT.")}</div>
    </div>
  `);
}

function showGfw(p) {
  const atlas = findAtlasMatch(p.name || p.company);
  const gfw = findGfwRecord(p.name || p.company) || p;
  const link = atlasDeepLink(atlas?.atlas_nama || p.name || p.company, gfw);
  setDetail(`
    <p class="eyebrow">Overlay konsesi GFW</p>
    <h1>${escapeHtml(p.name || p.company || "Konsesi")}</h1>
    <p class="lead">Poligon industri tersederhanakan dari dataset GFW Riau — bukan sertifikat HGU tunggal.</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Perusahaan</label>${escapeHtml(p.company || "–")}</div>
      <div class="meta-item"><label>Grup</label>${escapeHtml(p.group || "–")}</div>
      <div class="meta-item"><label>Luas (ha)</label>${fmtNum(p.area_ha)}</div>
      <div class="meta-item"><label>Tipe / HGU</label>${escapeHtml([p.type, p.hgu].filter(Boolean).join(" · ") || "–")}</div>
      <div class="meta-item"><label>Match Atlas</label>${escapeHtml(atlas?.atlas_nama || "Belum tercocokkan")}</div>
      <div class="meta-item"><label>Nama lokal</label>${escapeHtml(atlas?.nama_lokal || "–")}</div>
    </div>
    <p class="detail-actions">
      <a class="btn-link" href="${escapeAttr(link.href)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>
      ${
        Number.isFinite(Number(gfw.lat)) && Number.isFinite(Number(gfw.lon))
          ? `<a class="btn-link ghost" href="https://www.openstreetmap.org/?mlat=${Number(gfw.lat)}&mlon=${Number(gfw.lon)}#map=12/${Number(gfw.lat)}/${Number(gfw.lon)}" target="_blank" rel="noopener">Lokasi proksi</a>`
          : ""
      }
    </p>
    <p class="muted small">Cari nama konsesi di bilah pencarian Nusantara Atlas untuk bukti satelit/deforestasi.</p>
  `);
}

function showAtlasMatch(atlasNama, namaLokal) {
  const row = findAtlasMatch(atlasNama) || findAtlasMatch(namaLokal);
  const gfw = findGfwRecord(namaLokal || atlasNama) || findGfwRecord(atlasNama);
  if (gfw?.lat && gfw?.lon) {
    state.map?.flyTo([Number(gfw.lat), Number(gfw.lon)], 10, { duration: 0.7 });
  }
  const link = atlasDeepLink(row?.atlas_nama || atlasNama, gfw);
  setDetail(`
    <p class="eyebrow">Mode Deforestasi Atlas</p>
    <h1>${escapeHtml(row?.atlas_nama || atlasNama || "Konsesi")}</h1>
    <p class="lead">Jembatan nama antara Nusantara Atlas dan register lokal workspace.</p>
    <div class="meta-grid">
      <div class="meta-item"><label>Nama lokal</label>${escapeHtml(row?.nama_lokal || namaLokal || "–")}</div>
      <div class="meta-item"><label>Status match</label>${escapeHtml(row?.status || "–")}</div>
      <div class="meta-item"><label>Tipe / tahun</label>${escapeHtml([row?.tipe, row?.tahun].filter(Boolean).join(" · ") || "–")}</div>
      <div class="meta-item"><label>Area (ha)</label>${fmtNum(row?.area_ha || gfw?.area_ha)}</div>
      <div class="meta-item"><label>Di BPS</label>${escapeHtml(row?.ada_di_bps || "–")}</div>
      <div class="meta-item"><label>Di konflik Polda</label>${escapeHtml(row?.ada_di_konflik_polda || "–")}</div>
    </div>
    <p class="detail-actions">
      <a class="btn-link" href="${escapeAttr(link.href)}" target="_blank" rel="noopener">${escapeHtml(link.label)}</a>
    </p>
  `);
}
window.showAtlasMatch = showAtlasMatch;
window.showKabupaten = showKabupaten;

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
    return p.id === idOrName || String(p.nama || "").toLowerCase() === String(idOrName).toLowerCase();
  });
  if (f?.geometry?.type === "Point") {
    const [x, y] = f.geometry.coordinates;
    return [y, x];
  }
  return null;
}

function tokensFor(name) {
  const raw = String(name || "").toLowerCase().trim();
  if (!raw) return [];
  const out = new Set([
    raw,
    raw.replace(/^polres\s+/, ""),
    raw.replace(/^kab\.?\s+/, ""),
    raw.replace(/^kota\s+/, ""),
  ]);
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
  document.getElementById("storyGrid").innerHTML = [
    {
      t: "Koridor panas",
      h: top.map((p) => p.polres.replace(/^Polres\s+/i, "")).join(", "),
      p: "Tiga Polres teratas early-warning menggabungkan densitas objek Agrinas/KSO, liputan konflik baru, dan aksi massa.",
    },
    {
      t: "Penertiban KH",
      h: `${DATA.penertiban?.normalized?.gelombang1_27_pt?.total || 27} PT gelombang 1`,
      p: "Modul penertiban memuat sebaran korporasi di KH, operasi TN Tesso Nilo, dan daftar target Satgas PKH per kabupaten.",
    },
    {
      t: "Mode bandingkan",
      h: "Register · Agrinas · Atlas",
      p: "Di peta, pilih lensa untuk menonjolkan densitas kasus, sinyal Agrinas–KSO, atau overlay deforestasi/konsesi Atlas–GFW.",
    },
    {
      t: "Jembatan ke Atlas",
      h: `${atlasHits || DATA.konsesi.atlas_match.total} nama tercocokkan`,
      p: "Setiap cocokan punya deep-link ke Nusantara Atlas sebagai bukti satelit; workspace ini memegang aktor dan konflik.",
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

function setupNav() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.view = btn.dataset.view;
      const stage = document.getElementById("mapStage") || document.querySelector(".stage");
      const story = document.getElementById("storyView");
      const data = document.getElementById("dataView");
      const analisis = document.getElementById("analisisView");
      if (stage) stage.hidden = state.view !== "peta";
      if (story) story.hidden = state.view !== "cerita";
      if (data) data.hidden = state.view !== "data";
      if (analisis) analisis.hidden = state.view !== "analisis";
      document.body.classList.toggle("is-scroll", state.view !== "peta");
      if (state.view === "peta") setTimeout(() => state.map?.invalidateSize(), 80);
      if (state.view === "analisis") {
        setTimeout(() => {
          if (typeof window.renderAnalytics === "function") window.renderAnalytics();
          if (typeof window.renderPenertibanModule === "function") {
            window.setupPenertibanControls?.();
            window.renderPenertibanModule();
          }
        }, 120);
      }
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
    renderRankPanel();
  });
}

function setupBlendWeight() {
  const wrap = document.getElementById("blendWeight");
  if (!wrap) return;
  const apply = (w) => {
    state.blendOsint = Number(w);
    wrap.querySelectorAll(".chip").forEach((c) => {
      c.classList.toggle("is-on", Number(c.dataset.blend) === state.blendOsint);
    });
    const hint = document.getElementById("blendHint");
    if (hint) hint.textContent = blendMetricLabel() + " — ranking & choropleth Gabungan ikut berubah.";
    renderStats();
    renderRankPanel();
    refreshChoroplethForMode();
    if (state.view === "analisis" && typeof window.renderAnalytics === "function") {
      window.renderAnalytics();
    }
  };
  wrap.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    apply(btn.dataset.blend);
  });
  apply(state.blendOsint);
}

function syncTimelineYearModeUI() {
  const wrap = document.getElementById("timelineYearMode");
  if (!wrap) return;
  wrap.querySelectorAll(".chip").forEach((c) => {
    c.classList.toggle("is-on", c.dataset.yearMode === state.timelineYearMode);
  });
  const note = document.getElementById("timelineBiasNote");
  if (note) {
    note.innerHTML =
      state.timelineYearMode === "kejadian"
        ? `Mode <strong>tahun kejadian</strong> (dari uraian/LP). Spike tetap bisa bias liputan — bandingkan dengan mode “tahun disebut”.`
        : `Mode <strong>tahun disebut</strong> di Tahun_Referensi. Spike 2026 sering mencerminkan pengumpulan/liputan baru, bukan ledakan konflik mentah.`;
  }
}

window.getTimelineYearMode = () => state.timelineYearMode;
window.setTimelineYearMode = (mode) => {
  state.timelineYearMode = mode === "disebut" ? "disebut" : "kejadian";
  syncTimelineYearModeUI();
};

async function applyCompareMode(mode) {
  const preset = COMPARE_PRESETS[mode] || COMPARE_PRESETS.all;
  state.compare = mode;
  Object.assign(state.layerOn, preset.layers);
  const hint = document.getElementById("compareHint");
  if (hint) hint.textContent = preset.hint;
  if (preset.layers.gfw_konsesi) {
    await ensureGfwLayer();
  }
  renderLayers();
  refreshLayerVisibility();
  refreshChoroplethForMode();
  renderRankPanel();
}

function setupCompareMode() {
  const wrap = document.getElementById("compareMode");
  if (!wrap) return;
  wrap.addEventListener("click", async (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    wrap.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
    btn.classList.add("is-on");
    await applyCompareMode(btn.dataset.compare || "all");
  });
}

function normalizeName(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/\b(pt\.?|cv\.?|ud\.?|tbk\.?)\b/g, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function nameScore(a, b) {
  const A = normalizeName(a);
  const B = normalizeName(b);
  if (!A || !B) return 0;
  if (A === B) return 100;
  if (A.includes(B) || B.includes(A)) return 80;
  const ta = new Set(A.split(" ").filter((t) => t.length > 2));
  const tb = new Set(B.split(" ").filter((t) => t.length > 2));
  if (!ta.size || !tb.size) return 0;
  let hit = 0;
  ta.forEach((t) => {
    if (tb.has(t)) hit += 1;
  });
  return (hit / Math.max(ta.size, tb.size)) * 60;
}

function findAtlasMatch(name) {
  const rows = DATA.konsesi?.atlas_match?.records || [];
  let best = null;
  let score = 0;
  rows.forEach((r) => {
    const s = Math.max(nameScore(name, r.atlas_nama), nameScore(name, r.nama_lokal));
    if (s > score) {
      score = s;
      best = r;
    }
  });
  return score >= 40 ? best : null;
}

function findGfwRecord(name) {
  const rows = DATA.gfwFull?.records || [];
  let best = null;
  let score = 0;
  rows.forEach((r) => {
    const s = Math.max(nameScore(name, r.company), nameScore(name, r.name));
    if (s > score) {
      score = s;
      best = r;
    }
  });
  return score >= 40 ? best : null;
}

function atlasDeepLink(name, gfw) {
  const label = String(name || gfw?.company || gfw?.name || "konsesi").trim();
  // Nusantara Atlas state IDs are opaque; open the map and guide search by name.
  const href = "https://map.nusantara-atlas.org/";
  return {
    href,
    label: `Buka Nusantara Atlas · ${label}`,
    title: `Cari “${label}” di Nusantara Atlas`,
  };
}

window.findAtlasMatch = findAtlasMatch;
window.findGfwRecord = findGfwRecord;
window.atlasDeepLink = atlasDeepLink;

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
      box.innerHTML =
        hits
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
    { id: "kab", label: "Kab/Kota", rows: () => DATA.kab.records, cols: ["kab_kota", "kategori_peta", "skor_komposit", "n_kasus", "polres_proksi", "objek_sinyal_utama"] },
    { id: "atlas", label: "Cocokan Atlas", rows: () => DATA.konsesi.atlas_match.records, cols: ["atlas_nama", "tahun", "tipe", "status", "nama_lokal", "area_ha"] },
    {
      id: "gfwfull",
      label: "GFW bbox 287",
      rows: () => DATA.gfwFull?.records || [],
      cols: ["no", "company", "name", "group", "area_ha", "hgu", "gfwid", "lon", "lat"],
    },
    {
      id: "penertiban",
      label: "Penertiban KH",
      rows: () => DATA.penertiban?.normalized?.gelombang1_27_pt?.records || [],
      cols: ["no", "perusahaan", "kabupaten", "afiliasi", "catatan"],
    },
    {
      id: "sk36",
      label: "SK36 110A",
      rows: () => DATA.penertiban?.normalized?.sk36_2025_110a?.records || [],
      cols: ["no", "nama", "dimohon_ha", "berproses_ha", "ditolak_ha", "rasio_ditolak", "prioritas"],
    },
  ];
  const tabBar = document.getElementById("tableTabs");
  let active = tabs[0];
  const paintTabs = () => {
    tabBar.innerHTML = tabs
      .map((t) => `<button class="chip ${t.id === active.id ? "is-on" : ""}" data-id="${t.id}">${t.label}</button>`)
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
    document.querySelector("#dataTable thead").innerHTML = `<tr>${active.cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
    document.querySelector("#dataTable tbody").innerHTML = rows
      .map(
        (r) =>
          `<tr>${active.cols
            .map((c) => {
              let v = r[c];
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
