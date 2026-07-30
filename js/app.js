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
  compareLast: "all",
  layersDirty: false,
  blendOsint: 0.7, // 0 = 100% register, 0.7 = default, 1 = 100% OSINT
  timelineYearMode: "kejadian", // kejadian | disebut
  gfwFullLoading: null,
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
    hint: "Sinyal Agrinas: warna kab = skor OSINT + koridor proksi + titik objek.",
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

/** Label lapisan ramah pembaca; detail teknis di title/tooltip. */
const LAYER_LABELS = {
  choropleth: { label: "Choropleth kab/kota", title: "" },
  koridor: { label: "Koridor proksi", title: "Hull dari titik objek — bukan koridor resmi" },
  densitas_kasus: { label: "Densitas kasus", title: "Centroid kab/kota sebagai proksi lokasi" },
  objek_titik: { label: "Titik objek Agrinas", title: "" },
  gfw_konsesi: { label: "Konsesi GFW", title: "Overlay TopoJSON (dimuat saat diaktifkan)" },
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

/**
 * Single cache-bust token for all data fetches.
 * Source of truth: <meta name="atlas-asset-ver"> in index.html (keep ?v= on assets in sync).
 */
const ASSET_VER =
  document.querySelector('meta[name="atlas-asset-ver"]')?.getAttribute("content") || "0dbc";

async function loadJSON(path) {
  const url = path.includes("?") ? path : `${path}?v=${ASSET_VER}`;
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Gagal memuat ${path}`);
  return res.json();
}

const BOOT_MANIFEST = [
  { key: "meta", path: "data/meta.json", critical: true },
  { key: "kab", path: "data/kab_kota.json", critical: true },
  { key: "polres", path: "data/polres.json", critical: true },
  { key: "objek", path: "data/objek_agrinas.json", critical: true },
  { key: "kasus", path: "data/kasus.json", critical: true },
  { key: "perusahaan", path: "data/perusahaan.json", critical: false, fallback: { records: [] } },
  { key: "konsesi", path: "data/konsesi.json", critical: false, fallback: { atlas_match: { records: [], total: 0 } } },
  { key: "layers", path: "data/layers.geojson", critical: true },
  { key: "adm2", path: "data/adm2_riau.geojson", critical: true },
  { key: "analytics", path: "data/analytics.json", critical: false, fallback: { timeline: { default_mode: "kejadian" } } },
  { key: "penertiban", path: "data/penertiban.json", critical: false, fallback: { normalized: {} } },
];

function setBooting(on) {
  document.body.classList.toggle("is-booting", on);
  const ov = document.getElementById("bootOverlay");
  if (ov) {
    ov.hidden = !on;
    ov.setAttribute("aria-busy", on ? "true" : "false");
  }
  const stats = document.getElementById("statsGrid");
  if (stats && !on) stats.removeAttribute("aria-busy");
}

function showStatusBanner(message) {
  const banner = document.getElementById("statusBanner");
  const text = document.getElementById("statusBannerText");
  if (!banner || !text) return;
  text.textContent = message;
  banner.hidden = false;
}

function hideStatusBanner() {
  const banner = document.getElementById("statusBanner");
  if (banner) banner.hidden = true;
}

function setupStatusBanner() {
  document.getElementById("statusBannerClose")?.addEventListener("click", hideStatusBanner);
}

function emptyRankHtml(msg) {
  return `<li class="rank-empty" role="status">${escapeHtml(msg)}</li>`;
}

async function loadBootPayload() {
  const settled = await Promise.all(
    BOOT_MANIFEST.map(async (item) => {
      try {
        return { ...item, ok: true, data: await loadJSON(item.path) };
      } catch (err) {
        return { ...item, ok: false, err };
      }
    })
  );

  const failed = settled.filter((r) => !r.ok);
  const criticalFailed = failed.filter((r) => r.critical);
  if (failed.length) {
    const names = failed.map((f) => f.path.replace(/^data\//, "")).join(", ");
    showStatusBanner(
      criticalFailed.length
        ? `Gagal memuat data inti (${names}). Periksa file serving atau jalankan ekspor ulang.`
        : `Sebagian data opsional gagal dimuat (${names}). Peta tetap jalan; modul terkait mungkin kosong.`
    );
  }
  if (criticalFailed.length) {
    const detail = criticalFailed.map((f) => f.err?.message || f.path).join("; ");
    throw new Error(detail || "Data inti belum tersedia");
  }

  const byKey = Object.fromEntries(
    settled.map((r) => [r.key, r.ok ? r.data : structuredClone(r.fallback)])
  );
  return byKey;
}

/** Kartu preview hover peta — satu template untuk semua lapisan. */
const mapPreviewHtml = (...args) => AtlasUI.mapPreviewHtml(...args);

function bindMapPreview(layer, html) {
  // Popup (bukan tooltip sticky) — kartu bisa di-hover & CTA diklik tanpa ikut kursor
  if (layer.getPopup && layer.getPopup()) layer.unbindPopup();
  if (layer.getTooltip && layer.getTooltip()) layer.unbindTooltip();

  layer.bindPopup(html, {
    className: "map-preview-popup",
    closeButton: false,
    autoPan: false,
    closeOnClick: false,
    maxWidth: 300,
    offset: L.point(0, -10),
  });

  const clearClose = () => {
    if (layer._mapPreviewCloseTimer) {
      clearTimeout(layer._mapPreviewCloseTimer);
      layer._mapPreviewCloseTimer = null;
    }
  };
  const scheduleClose = () => {
    clearClose();
    layer._mapPreviewCloseTimer = setTimeout(() => {
      try {
        layer.closePopup();
      } catch (_) {
        /* ignore */
      }
    }, 320);
  };

  layer.off("mouseover.mapPreview mouseout.mapPreview popupopen.mapPreview");
  layer.on("mouseover.mapPreview", () => {
    clearClose();
    layer.openPopup();
  });
  layer.on("mouseout.mapPreview", scheduleClose);
  layer.on("popupopen.mapPreview", (e) => {
    const el = e.popup?.getElement?.();
    if (!el) return;
    L.DomEvent.disableClickPropagation(el);
    L.DomEvent.disableScrollPropagation(el);
    el.addEventListener("mouseenter", clearClose);
    el.addEventListener("mouseleave", scheduleClose);
  });
}

function setupMapPreviewActions() {
  if (setupMapPreviewActions._ready) return;
  setupMapPreviewActions._ready = true;
  document.addEventListener(
    "click",
    (e) => {
      const btn = e.target.closest?.("[data-action='polres']");
      if (
        !btn ||
        !btn.closest(".leaflet-popup.map-preview-popup, .leaflet-tooltip.map-preview, .map-preview__card")
      ) {
        return;
      }
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
  setupStatusBanner();
  setBooting(true);
  const loaded = await loadBootPayload();
  Object.assign(DATA, {
    meta: loaded.meta,
    kab: loaded.kab,
    polres: loaded.polres,
    objek: loaded.objek,
    kasus: loaded.kasus,
    perusahaan: loaded.perusahaan,
    konsesi: loaded.konsesi,
    layers: loaded.layers,
    adm2: loaded.adm2,
    gfw: null,
    analytics: loaded.analytics,
    penertiban: loaded.penertiban,
    gfwFull: null,
  });

  (DATA.meta.layers || []).forEach((l) => {
    state.layerOn[l.id] = !!l.default;
  });

  document.getElementById("updatedAt").textContent =
    `Diperbarui ${formatDate(DATA.meta.updated_at)} · ${DATA.meta.counts?.kasus_konflik ?? "–"} kasus · ${DATA.meta.counts?.objek_agrinas ?? "–"} objek`;

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
  setupMobileChrome();
  syncTimelineYearModeUI();
  syncRailDetailsForViewport();
  window.addEventListener("resize", syncRailDetailsForViewport);
  syncMobileStartCta();
  setBooting(false);
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
  // Prefer meta.counts (updated by DQ/export) over stale polres.coverage snapshot
  const mapped = c.entri_terpetakan ?? cov.total_entri_terpetakan ?? "–";
  const unmapped = c.entri_tidak_terpetakan ?? cov.entri_tidak_terpetakan ?? "–";
  const prioritas = DATA.polres.records.filter((p) => kategoriFromSkor(blendedPolresSkor(p)) === "PRIORITAS").length;
  const grid = document.getElementById("statsGrid");
  if (grid) {
    grid.className = "stat-strip stat-strip--primary";
    grid.innerHTML = `
      <div class="stat"><strong>${c.kasus_konflik ?? "–"}</strong><span>Kasus konflik</span></div>
      <div class="stat"><strong>${prioritas}</strong><span>Polres prioritas</span></div>
      <p class="stat-coverage">${escapeHtml(String(mapped))} terpetakan · ${escapeHtml(String(unmapped))} lintas Riau / n/a</p>
    `;
  }

  const short = "Skor = indeks liputan+objek+register — bukan vonis operasional.";
  const disc =
    DATA.meta?.methodology?.disclaimer ||
    DATA.polres?.model?.catatan ||
    short;
  const summary = document.getElementById("methodNoteSummary");
  const methodEl = document.getElementById("methodNote");
  if (summary) summary.textContent = short;
  if (methodEl) methodEl.textContent = disc;

  // Seed kepmen heading before Analisis tab mounts charts
  const kepmenTotal = document.getElementById("kepmenTotal");
  if (kepmenTotal && (kepmenTotal.textContent || "").trim() === "–") {
    const n =
      DATA.analytics?.kepmenhut?.total ??
      DATA.konsesi?.kepmenhut_36_2025?.total ??
      DATA.konsesi?.kepmenhut_36_2025?.records?.length;
    if (n != null) kepmenTotal.textContent = String(n);
  }
}

function layerDisplay(metaLayer) {
  const id = metaLayer?.id || "";
  const mapped = LAYER_LABELS[id];
  if (mapped) return mapped;
  const raw = String(metaLayer?.label || id);
  return {
    label: raw.replace(/\s*\([^)]*\)\s*$/, "").trim() || raw,
    title: raw,
  };
}

function renderLayers() {
  const list = document.getElementById("layerList");
  list.innerHTML = (DATA.meta.layers || [])
    .map((l) => {
      const d = layerDisplay(l);
      return `
      <label class="layer-item" ${d.title ? `title="${escapeAttr(d.title)}"` : ""}>
        <input type="checkbox" data-layer="${escapeAttr(l.id)}" ${state.layerOn[l.id] ? "checked" : ""} />
        <span>${escapeHtml(d.label)}</span>
      </label>`;
    })
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
      onLayersUserChange();
    });
  });
}

function layersMatchPreset(mode = state.compareLast || state.compare) {
  const preset = COMPARE_PRESETS[mode]?.layers;
  if (!preset) return true;
  return Object.keys(preset).every((k) => !!state.layerOn[k] === !!preset[k]);
}

function onLayersUserChange() {
  const base = state.compareLast || state.compare || "all";
  state.layersDirty = !layersMatchPreset(base);
  syncCompareModeUI();
}

function syncCompareModeUI() {
  const wrap = document.getElementById("compareMode");
  const reset = document.getElementById("compareReset");
  const hint = document.getElementById("compareHint");
  if (!wrap) return;
  if (state.layersDirty) {
    wrap.querySelectorAll(".chip[data-compare]").forEach((c) => c.classList.remove("is-on"));
    if (reset) reset.hidden = false;
    if (hint) hint.textContent = "Lapisan disesuaikan manual — Reset untuk kembali ke preset.";
  } else {
    if (reset) reset.hidden = true;
    wrap.querySelectorAll(".chip[data-compare]").forEach((c) => {
      c.classList.toggle("is-on", c.dataset.compare === state.compare);
    });
    const preset = COMPARE_PRESETS[state.compare];
    if (hint && preset) hint.textContent = preset.hint;
  }
}

function syncBlendVisibility() {
  const section = document.getElementById("blendSection");
  if (!section) return;
  section.hidden = state.compare !== "all";
}

function syncRailDetailsForViewport() {
  const d = document.getElementById("railSecondary");
  if (!d) return;
  // Keep collapsed by default; force-close on narrow viewports to free map space.
  if (window.matchMedia("(max-width: 980px)").matches) d.open = false;
}

function syncFilterHint() {
  const hint = document.getElementById("filterHint");
  if (!hint) return;
  if (state.compare === "all") {
    hint.textContent = `Filter memakai skor yang sedang diurutkan (${blendMetricLabel()}).`;
  } else if (state.compare === "register") {
    hint.textContent = "Filter memakai risiko register yang sedang diurutkan.";
  } else if (state.compare === "agrinas") {
    hint.textContent = "Filter memakai prioritas objek Agrinas pada daftar.";
  } else {
    hint.textContent = "Filter terbatas pada mode ranking Polres / register.";
  }
}

function rankTitleText() {
  const mode = COMPARE_PRESETS[state.compare]?.rank || "polres";
  if (mode === "atlas") return "Cocokan Atlas";
  if (mode === "agrinas") return "Objek Agrinas";
  if (mode === "register") return "Ranking · risiko register";
  const w = Number(state.blendOsint);
  if (w <= 0) return "Ranking Polres · 100% Register";
  if (w >= 1) return "Ranking Polres · 100% OSINT";
  return `Ranking Polres · blend ${Math.round(w * 100)}/${Math.round((1 - w) * 100)}`;
}

function renderPolres() {
  renderRankPanel();
}

function renderRankPanel() {
  const ol = document.getElementById("polresList");
  const title = document.getElementById("rankTitle");
  const mode = COMPARE_PRESETS[state.compare]?.rank || "polres";

  if (mode === "atlas") {
    if (title) title.textContent = rankTitleText();
    const rows = (DATA.konsesi?.atlas_match?.records || [])
      .filter((r) => String(r.status || "").toLowerCase().includes("cocok"))
      .slice(0, 16);
    ol.innerHTML =
      rows
        .map((r, i) => {
          const link = atlasDeepLink(r.atlas_nama || r.nama_lokal);
          return `<li>
          <button type="button" data-atlas="${escapeAttr(r.atlas_nama || "")}" data-lokal="${escapeAttr(r.nama_lokal || "")}" title="Buka detail match Atlas" aria-label="Buka detail ${escapeAttr(r.atlas_nama || "match Atlas")}">
            <span class="n pantau">${i + 1}</span>
            <span>
              <strong>${escapeHtml(r.atlas_nama || "–")}</strong><br/>
              <small>${escapeHtml(r.nama_lokal || r.tipe || "")}</small>
            </span>
            <span class="score"><a class="rank-ext" href="${escapeAttr(link.href)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">↗</a></span>
          </button>
        </li>`;
        })
        .join("") || emptyRankHtml("Tidak ada cocokan Atlas untuk ditampilkan.");
    ol.querySelectorAll("button[data-atlas]").forEach((btn) => {
      btn.addEventListener("click", () => showAtlasMatch(btn.dataset.atlas, btn.dataset.lokal));
    });
    return;
  }

  if (mode === "agrinas") {
    if (title) title.textContent = rankTitleText();
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
    ol.innerHTML =
      rows
        .map(
          (o, i) => `<li>
        <button type="button" data-objek="${escapeAttr(o.id || o.nama || "")}" title="Buka detail objek" aria-label="Buka detail objek ${escapeAttr(o.nama || o.id || "")}">
          <span class="n ${escapeAttr(o.prioritas || "pantau")}">${i + 1}</span>
          <span>
            <strong>${escapeHtml(truncate(o.nama || o.id, 42))}</strong><br/>
            <small>${escapeHtml([o.lapisan, o.kab_primary && o.kab_primary !== "MULTI" ? o.kab_primary : o.kab_kota].filter(Boolean).join(" · "))}</small>
          </span>
          <span class="score">${escapeHtml(o.prioritas || "–")}</span>
        </button>
      </li>`
        )
        .join("") || emptyRankHtml("Tidak ada objek untuk filter ini.");
    ol.querySelectorAll("button[data-objek]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const o = DATA.objek.records.find((x) => x.id === btn.dataset.objek || x.nama === btn.dataset.objek);
        if (o) showTitik({ ...o, nama: o.nama, id: o.id });
      });
    });
    return;
  }

  if (title) title.textContent = rankTitleText();
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
  ol.innerHTML =
    rows
      .map((p, idx) => {
        const primary = Number(mode === "register" ? p.skor_register || p.skor : blendedPolresSkor(p)) || 0;
        const kat = kategoriFromSkor(primary);
        const rankN = idx + 1;
        const shortName = p.polres.replace(/^Polres\s+/i, "");
        return `
      <li>
        <button type="button" data-polres="${escapeAttr(p.polres)}" title="Buka detail Polres ${escapeAttr(shortName)}" aria-label="Buka detail Polres ${escapeAttr(shortName)}">
          <span class="n ${escapeAttr(kat)}">${rankN}</span>
          <span>
            <strong>${escapeHtml(shortName)}</strong><br/>
            <small>OSINT ${fmtNum(p.skor_osint)} · Reg ${fmtNum(p.skor_register)}</small>
          </span>
          <span class="score" title="${mode === "register" ? "Risiko register" : blendMetricLabel()}">${primary.toFixed(0)}</span>
        </button>
      </li>`;
      })
      .join("") || emptyRankHtml("Tidak ada Polres untuk filter ini.");
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
    const polresRaw = p.polres_proksi || "";
    const polresNama =
      (polresRaw &&
        DATA.polres?.records?.find((x) => matchWilayah(x.polres, polresRaw))?.polres) ||
      polresRaw;
    bindMapPreview(
      marker,
      mapPreviewHtml({
        eyebrow: "Objek Agrinas",
        title: p.nama || p.id || "Objek",
        level,
        metaLines: [p.tipe || "Titik proksi", polresNama || p.kab_kota || ""].filter(Boolean),
        polres: polresNama,
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

async function ensureGfwFull() {
  if (DATA.gfwFull?.records) return DATA.gfwFull;
  if (state.gfwFullLoading) return state.gfwFullLoading;
  state.gfwFullLoading = (async () => {
    try {
      DATA.gfwFull = await loadJSON("data/konsesi_gfw_full.json");
    } catch (err) {
      console.error("konsesi_gfw_full gagal dimuat", err);
      DATA.gfwFull = { records: [], total: 0 };
    }
    return DATA.gfwFull;
  })();
  try {
    return await state.gfwFullLoading;
  } finally {
    state.gfwFullLoading = null;
  }
}

async function ensureGfwLayer() {
  // Attribute table is only needed for detail enrichment — load in parallel with overlay.
  ensureGfwFull();
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
        showStatusBanner("Lapisan konsesi GFW tidak tersedia saat ini. Lapisan lain tetap bisa dipakai.");
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
  const panel = document.getElementById("detailPanel");
  panel?.classList.add("is-open");
  // On mobile, collapse rail so map + detail aren't fighting for space
  if (window.matchMedia("(max-width: 980px)").matches) {
    const rail = document.getElementById("railPanel");
    const toggle = document.getElementById("railToggle");
    rail?.classList.remove("is-expanded");
    toggle?.setAttribute("aria-expanded", "false");
  }
  syncMobileStartCta();
}

function closeDetail() {
  document.getElementById("detailPanel")?.classList.remove("is-open");
  syncMobileStartCta();
}

function setDetail(html) {
  document.getElementById("detailContent").innerHTML = html;
  openDetail();
}

function isWelcomeDetail() {
  const eye = document.querySelector("#detailContent .eyebrow");
  return /mulai di sini/i.test(eye?.textContent || "");
}

function syncMobileStartCta() {
  const start = document.getElementById("mobileStart");
  if (!start) return;
  const narrow = window.matchMedia("(max-width: 980px)").matches;
  const onPeta = state.view === "peta";
  const detailOpen = document.getElementById("detailPanel")?.classList.contains("is-open");
  start.hidden = !(narrow && onPeta && isWelcomeDetail() && !detailOpen);
}

function setupMobileChrome() {
  const rail = document.getElementById("railPanel");
  const toggle = document.getElementById("railToggle");
  const start = document.getElementById("mobileStart");

  toggle?.addEventListener("click", () => {
    if (!rail) return;
    const on = rail.classList.toggle("is-expanded");
    toggle.setAttribute("aria-expanded", String(on));
    setTimeout(() => state.map?.invalidateSize(), 300);
  });

  start?.addEventListener("click", () => {
    openDetail();
  });

  const sync = () => {
    if (!window.matchMedia("(max-width: 980px)").matches) {
      rail?.classList.remove("is-expanded");
      toggle?.setAttribute("aria-expanded", "false");
    }
    syncMobileStartCta();
    document.body.classList.toggle("is-map-view", state.view === "peta");
  };
  sync();
  window.addEventListener("resize", sync);
  window.syncMobileStartCta = syncMobileStartCta;
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
  const objek = DATA.objek.records
    .filter(
      (o) =>
        matchWilayah(o.kab_primary, kab.kab_kota) ||
        matchWilayah(o.kab_kota, kab.kab_kota) ||
        String(o.kab_list || "")
          .split("|")
          .some((part) => matchWilayah(part, kab.kab_kota))
    )
    .slice(0, 8);
  const risk = kab.risiko_register || {};
  const polres = findPolresForKab(kab);
  const active = resolveChoroplethMetric(kab.kab_kota);

  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Kabupaten / Kota",
      title: kab.kab_kota,
      lead: kab.catatan_peta || "Metrik peta mengikuti mode bandingkan; angka di bawah adalah kamus lengkap.",
      meta: [
        {
          label: "Metrik aktif (mode)",
          html: `<strong>${escapeHtml(active.label)} ${fmtNum(active.skor)}</strong>`,
          badgeText: active.kategori || choroplethBandLabel(active.skor),
          badgeClass: active.kategori || "",
        },
        { label: METRIC_LABELS.kab_komposit, value: fmtNum(kab.skor_komposit), strong: true },
        {
          label: METRIC_LABELS.polres_blend,
          html: `<strong>${fmtNum(polres?.skor)}</strong>`,
          badgeText: polres?.kategori || "–",
          badgeClass: polres?.kategori || "",
        },
        {
          label: `${METRIC_LABELS.osint} / ${METRIC_LABELS.register}`,
          html: `${fmtNum(polres?.skor_osint)} / ${fmtNum(risk.skor ?? polres?.skor_register)}`,
        },
        { label: "Jumlah kasus (proksi)", value: fmtNum(kab.n_kasus), strong: true },
        { label: "Polres proksi", value: kab.polres_proksi || "–" },
        { label: "Objek sinyal utama", value: kab.objek_sinyal_utama || "–" },
        { label: "Hotspot kecamatan", value: kab.hotspot_kecamatan || "–" },
        { label: "Sawit di KH (ha)", value: fmtNum(kab.klhk_korp_kh_2022_ha) },
      ],
      bodyHtml: `
    ${risk.driver_utama ? `<p><strong>Driver register:</strong> ${escapeHtml(risk.driver_utama)}</p>` : ""}
    ${AtlasUI.sectionLabel("Kasus terkait")}
    ${AtlasUI.listBlock("case-list", kasus.map(caseCard).join(""), "Belum ada kasus terpetakan.")}
    ${AtlasUI.sectionLabel("Objek Agrinas")}
    ${AtlasUI.listBlock("obj-list", objek.map(objCard).join(""), "Tidak ada objek dengan kab/kota eksplisit.")}`,
    })
  );
}

function showPolres(nama) {
  const p =
    DATA.polres.records.find((x) => x.polres === nama) ||
    DATA.polres.records.find((x) => matchWilayah(x.polres, nama));
  if (!p) return;
  const kab = DATA.kab.records.find((k) => matchWilayah(k.polres_proksi, p.polres));
  if (kab?.lat && kab?.lon) state.map.flyTo([kab.lat, kab.lon], 9, { duration: 0.75 });
  const kasus = DATA.kasus.records.filter((k) => matchWilayah(k.polres, p.polres)).slice(0, 10);
  const blendKat = kategoriFromSkor(blendedPolresSkor(p));
  const regKat = kategoriFromSkor(p.skor_register);
  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Early-warning Polres",
      title: p.polres,
      lead: p.alasan || "",
      meta: [
        { label: "Peringkat model", html: `<strong>#${escapeHtml(p.peringkat)}</strong>` },
        {
          label: blendMetricLabel(),
          html: `<strong>${fmtNum(blendedPolresSkor(p))}</strong>`,
          badgeText: blendKat,
          badgeClass: blendKat,
        },
        { label: METRIC_LABELS.osint, value: fmtNum(p.skor_osint), strong: true },
        {
          label: METRIC_LABELS.register,
          html: `<strong>${fmtNum(p.skor_register)}</strong>`,
          badgeText: regKat,
          badgeClass: regKat,
        },
        {
          label: "Aksi massa · Kekerasan",
          html: `${fmtNum(p.n_aksi_massa)} · ${fmtNum(p.n_kekerasan)}`,
        },
        { label: "Objek Agrinas/KSO", value: fmtNum(p.n_agrinas) },
        { label: "Entri 2024+", value: fmtNum(p.n_recent) },
      ],
      bodyHtml: `
    <p class="muted small">${escapeHtml(DATA.polres?.model?.catatan || "Indeks liputan+objek+register — bukan vonis operasional.")}</p>
    ${AtlasUI.sectionLabel("Kasus di wilayah Polres")}
    ${AtlasUI.listBlock("case-list", kasus.map(caseCard).join(""), "Tidak ada kasus terfilter.")}`,
    })
  );
}
window.showPolres = showPolres;

function showTitik(p) {
  const latlng = findFeatureLatLng(p.id) || findFeatureLatLng(p.nama);
  if (latlng) state.map.flyTo(latlng, 10, { duration: 0.65 });
  const objek = DATA.objek.records.find(
    (o) => o.id === p.id || (o.nama || "").toLowerCase() === String(p.nama || "").toLowerCase()
  );
  const prioritas = p.prioritas || objek?.prioritas || "–";
  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Titik objek / proksi",
      title: p.nama || objek?.nama || "Objek",
      lead: p.catatan || objek?.kaitan_agrinas || "Titik proksi analisis, bukan poligon legal.",
      meta: [
        { label: "Kab/Kota", value: p.kab_kota || objek?.kab_kota || "–" },
        { label: "Kab primer", value: objek?.kab_primary || p.kab_kota || "–" },
        { label: "Tipe", value: p.tipe || objek?.lapisan || "–" },
        {
          label: "Prioritas",
          html: AtlasUI.badge(prioritas, p.prioritas || objek?.prioritas || ""),
        },
        { label: "Polres", value: p.polres_proksi || objek?.polres_primary || "–" },
        { label: "Mappable", value: objek?.mappable || "–" },
        { label: "Kredibilitas", value: objek?.status_kredibilitas || "–" },
        { label: "Sumber", value: p.sumber || objek?.sumber || "–" },
      ],
    })
  );
}

function showKoridor(p) {
  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Koridor proksi (hull/bbox)",
      title: p.nama || "Koridor",
      lead: p.karakter || "Hull/envelope dari titik objek — bukan koridor geografis resmi.",
      meta: [
        { label: "Anggota kab", value: p.anggota_kab || "–" },
        { label: "Polres", value: p.polres_proksi || "–" },
        {
          label: "Geometri",
          html: `${escapeHtml(p.geom_source || "proksi")} · ${fmtNum(p.n_titik)} titik`,
        },
        {
          label: "Prioritas peta",
          html: AtlasUI.badge(p.prioritas || "–", p.prioritas || ""),
        },
        { label: "Catatan", value: p.catatan || "Tetap proksi OSINT." },
      ],
    })
  );
}

async function showGfw(p) {
  await ensureGfwFull();
  const atlas = findAtlasMatch(p.name || p.company);
  const gfw = findGfwRecord(p.name || p.company) || p;
  const link = atlasDeepLink(atlas?.atlas_nama || p.name || p.company, gfw);
  const osm =
    Number.isFinite(Number(gfw.lat)) && Number.isFinite(Number(gfw.lon))
      ? {
          href: `https://www.openstreetmap.org/?mlat=${Number(gfw.lat)}&mlon=${Number(gfw.lon)}#map=12/${Number(gfw.lat)}/${Number(gfw.lon)}`,
          label: "Lokasi proksi",
          ghost: true,
        }
      : null;
  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Overlay konsesi GFW",
      title: p.name || p.company || "Konsesi",
      lead: "Poligon industri tersederhanakan dari dataset GFW Riau — bukan sertifikat HGU tunggal.",
      meta: [
        { label: "Perusahaan", value: p.company || "–" },
        { label: "Grup", value: p.group || "–" },
        { label: "Luas (ha)", value: fmtNum(p.area_ha) },
        { label: "Tipe / HGU", value: [p.type, p.hgu].filter(Boolean).join(" · ") || "–" },
        { label: "Match Atlas", value: atlas?.atlas_nama || "Belum tercocokkan" },
        { label: "Nama lokal", value: atlas?.nama_lokal || "–" },
      ],
      bodyHtml: `
    ${AtlasUI.detailActions([{ href: link.href, label: link.label }, osm].filter(Boolean))}
    <p class="muted small">Cari nama konsesi di bilah pencarian Nusantara Atlas untuk bukti satelit/deforestasi.</p>`,
    })
  );
}

async function showAtlasMatch(atlasNama, namaLokal) {
  await ensureGfwFull();
  const row = findAtlasMatch(atlasNama) || findAtlasMatch(namaLokal);
  const gfw = findGfwRecord(namaLokal || atlasNama) || findGfwRecord(atlasNama);
  if (gfw?.lat && gfw?.lon) {
    state.map?.flyTo([Number(gfw.lat), Number(gfw.lon)], 10, { duration: 0.7 });
  }
  const link = atlasDeepLink(row?.atlas_nama || atlasNama, gfw);
  setDetail(
    AtlasUI.detailShell({
      eyebrow: "Mode Deforestasi Atlas",
      title: row?.atlas_nama || atlasNama || "Konsesi",
      lead: "Jembatan nama antara Nusantara Atlas dan register lokal workspace.",
      meta: [
        { label: "Match ID", value: row?.match_id || "–" },
        { label: "Nama lokal", value: row?.nama_lokal || namaLokal || "–" },
        { label: "Status match", value: row?.status || "–" },
        { label: "Confidence", value: row?.match_confidence || "–" },
        { label: "Tipe / tahun", value: [row?.tipe, row?.tahun].filter(Boolean).join(" · ") || "–" },
        { label: "Area (ha)", value: fmtNum(row?.area_ha || gfw?.area_ha) },
        { label: "Di BPS", value: row?.ada_di_bps || "–" },
        { label: "Di konflik Polda", value: row?.ada_di_konflik_polda || "–" },
      ],
      bodyHtml: AtlasUI.detailActions([{ href: link.href, label: link.label }]),
    })
  );
}
window.showAtlasMatch = showAtlasMatch;
window.showKabupaten = showKabupaten;

function caseCard(k) {
  const title = cleanText(k.jenis || k.kategori || k.tipe_entri || k.id || "Kasus");
  const body = cleanText(k.uraian || k.lokasi || "");
  const years = formatCaseYears(k);
  const company = firstCompanyName(k.perusahaan);
  const tema = cleanText(String(k.tema || "").split(";")[0] || "");
  const ref = formatCaseRef(k);
  const showId = k.id && cleanText(k.id) !== title;

  return AtlasUI.caseCardHtml({
    title,
    id: showId ? k.id : "",
    body,
    chipsHtml: AtlasUI.chipsRow([
      k.tipe_entri ? AtlasUI.chip(String(k.tipe_entri).startsWith("Kasus") ? "Operasional" : "Potensi") : "",
      years ? AtlasUI.chip(years) : "",
      company ? AtlasUI.chip(company) : "",
      tema ? AtlasUI.chip(truncate(tema, 32), { soft: true }) : "",
      k.polres ? AtlasUI.chip(shortPolresLabel(k.polres), { soft: true }) : "",
    ]),
    ref,
    refTitle: cleanText(k.nomor_lp || k.status || ""),
  });
}

function objCard(o) {
  const title = cleanText(o.nama || o.id || "Objek");
  const kabLabel = o.kab_primary && o.kab_primary !== "MULTI" ? o.kab_primary : o.kab_kota;
  const meta = [o.lapisan, kabLabel, o.prioritas, o.mappable === "ya" ? "mappable" : null, o.status_kredibilitas]
    .map(cleanText)
    .filter(Boolean);
  return AtlasUI.objCardHtml({
    title,
    chipsHtml: AtlasUI.chipsRow(meta.map((m) => AtlasUI.chip(m, { soft: true }))),
  });
}

function cleanText(s) {
  return String(s || "")
    .replace(/\s+/g, " ")
    .trim();
}

function formatCaseYears(k) {
  const fromArr = Array.isArray(k.tahun_kejadian) && k.tahun_kejadian.length ? k.tahun_kejadian : null;
  const raw = fromArr || String(k.tahun || "").split(/[,;/]+/);
  const years = [...new Set(raw.map((y) => cleanText(y)).filter((y) => /^\d{4}$/.test(y)))];
  return years.join(", ");
}

function firstCompanyName(perusahaan) {
  if (!perusahaan) return "";
  const parts = String(perusahaan)
    .split(/[;|]/)
    .map((p) => cleanText(p))
    .filter(Boolean);
  const extracted = [];
  parts.forEach((p) => {
    const matches = p.match(/\b(?:PT\.?|CV\.?)\s+[A-Za-z][A-Za-z0-9.&-]*(?:\s+[A-Za-z][A-Za-z0-9.&-]*){0,4}/gi) || [];
    matches.forEach((m) => {
      const cleaned = cleanText(m)
        .replace(/\bPT\.?\s+PT\.?\s+/i, "PT. ")
        .replace(/\s+/g, " ");
      // Buang ekor lokasi/kecamatan yang nyangkut
      const core = cleaned.split(/\s+(?:Kec\.?|Kab\.?|Desa|Kel\.?|Di|Pada|Masyarakat)\b/i)[0];
      if (core && core.length >= 5) extracted.push(core);
    });
  });
  if (!extracted.length) return "";
  extracted.sort((a, b) => a.length - b.length);
  return truncate(extracted[0], 40);
}

function formatCaseRef(k) {
  const lp = cleanText(k.nomor_lp || "");
  if (lp) {
    // Ambil nomor LP inti, buang baris tanggal/uraian tambahan
    const core = lp.split(/(?=TGL\b)|(?=TTG\b)/i)[0].replace(/\s+/g, " ").trim();
    return truncate(core, 56);
  }
  const status = cleanText(k.status || "");
  if (!status) return "";
  // Jangan dump status panjang yang mengulang perusahaan
  if (status.length > 72 || /PT\.?\s/i.test(status)) return truncate(status.split(/TGL\b|TTG\b/i)[0], 48);
  return truncate(status, 48);
}

function shortPolresLabel(nama) {
  return cleanText(nama).replace(/^Polres\s+/i, "Polres ");
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
  const atlasHits = (DATA.konsesi?.atlas_match?.records || []).filter((r) =>
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
      h: `${atlasHits || DATA.konsesi?.atlas_match?.total || 0} nama tercocokkan`,
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
      document.body.classList.toggle("is-map-view", state.view === "peta");
      if (state.view === "peta") setTimeout(() => state.map?.invalidateSize(), 80);
      syncMobileStartCta();
      if (state.view === "data") {
        requestAnimationFrame(() => syncTablePaneScrollHints(document.getElementById("dataView") || document));
      }
      if (state.view === "analisis") {
        setTimeout(() => {
          if (typeof window.renderAnalytics === "function") window.renderAnalytics();
          if (typeof window.renderPenertibanModule === "function") {
            window.setupPenertibanControls?.();
            window.renderPenertibanModule();
          }
          syncTablePaneScrollHints(document.getElementById("analisisView") || document);
        }, 120);
      }
    });
  });
  document.getElementById("detailClose").addEventListener("click", () => {
    closeDetail();
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
    syncFilterHint();
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
  syncBlendVisibility();
}

async function applyCompareMode(mode) {
  const key = mode || "all";
  const preset = COMPARE_PRESETS[key] || COMPARE_PRESETS.all;
  state.compare = key;
  state.compareLast = key;
  state.layersDirty = false;
  Object.assign(state.layerOn, preset.layers);
  if (preset.layers.gfw_konsesi) {
    await ensureGfwLayer();
  }
  renderLayers();
  refreshLayerVisibility();
  refreshChoroplethForMode();
  renderRankPanel();
  syncCompareModeUI();
  syncBlendVisibility();
  syncFilterHint();
}

function setupCompareMode() {
  const wrap = document.getElementById("compareMode");
  if (!wrap) return;
  wrap.addEventListener("click", async (e) => {
    const btn = e.target.closest(".chip[data-compare]");
    if (!btn) return;
    await applyCompareMode(btn.dataset.compare || "all");
  });
  const reset = document.getElementById("compareReset");
  if (reset) {
    reset.addEventListener("click", async () => {
      await applyCompareMode(state.compareLast || "all");
    });
  }
  syncCompareModeUI();
  syncBlendVisibility();
  syncFilterHint();
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
      if (!DATA.kab?.records || !DATA.polres?.records || !DATA.objek?.records) {
        box.innerHTML = `<p class="search-empty" role="status">Data pencarian belum siap. Tunggu sebentar…</p>`;
        box.hidden = false;
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
      if (!hits.length) {
        box.innerHTML = `<p class="search-empty" role="status">Tidak ada hasil untuk “${escapeHtml(input.value.trim())}”. Coba nama kab/kota, Polres, atau objek.</p>`;
        box.hidden = false;
        return;
      }
      box.innerHTML = hits
        .slice(0, 12)
        .map(
          (h) =>
            `<button type="button" data-type="${h.type}" data-ref="${escapeAttr(h.ref)}"><strong>${escapeHtml(h.label)}</strong><small>${escapeHtml(h.sub || "")}</small></button>`
        )
        .join("");
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

function syncTablePaneScrollHints(root = document) {
  root.querySelectorAll(".table-pane").forEach((pane) => {
    const scroller = pane.querySelector(".table-scroll");
    const hint = pane.querySelector(".table-scroll-hint");
    if (!scroller) return;
    // Card stack at ≤640px does not need a horizontal hint
    const stackMode = window.matchMedia("(max-width: 640px)").matches;
    const overflow = !stackMode && scroller.scrollWidth > scroller.clientWidth + 4;
    pane.classList.toggle("is-scrollable", overflow);
    if (hint) hint.hidden = !overflow;
  });
}

window.syncTablePaneScrollHints = syncTablePaneScrollHints;

function setupDataTables() {
  const tabs = [
    { id: "kasus", label: "Kasus konflik", rows: () => DATA.kasus.records, cols: ["id", "tipe_entri", "kab_kota", "polres", "tahun", "nomor_lp", "perusahaan", "status", "uraian"] },
    { id: "objek", label: "Objek Agrinas", rows: () => DATA.objek.records, cols: ["id", "nama", "lapisan", "kab_primary", "kab_kota", "mappable", "prioritas", "status_kredibilitas", "kaitan_agrinas"] },
    { id: "polres", label: "Ranking Polres", rows: () => DATA.polres.records, cols: ["peringkat", "polres", "skor", "kategori", "n_agrinas", "n_aksi_massa", "alasan"] },
    { id: "kab", label: "Kab/Kota", rows: () => DATA.kab.records, cols: ["kab_kota", "kategori_peta", "skor_komposit", "n_kasus", "polres_proksi", "objek_sinyal_utama"] },
    { id: "atlas", label: "Cocokan Atlas", rows: () => DATA.konsesi?.atlas_match?.records || [], cols: ["match_id", "atlas_nama", "tahun", "tipe", "status", "match_confidence", "nama_lokal", "area_ha"] },
  {
      id: "gfwfull",
      label: "GFW bbox 287",
      rows: () => DATA.gfwFull?.records || [],
      cols: ["no", "company", "nama_kanonik", "name", "group", "area_ha", "hgu", "gfwid", "lon", "lat"],
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
      cols: ["record_id", "no", "nama", "status_proses", "dimohon_ha", "berproses_ha", "ditolak_ha", "prioritas"],
    },
  ];
  const tabBar = document.getElementById("tableTabs");
  let active = tabs[0];
  const paintTabs = () => {
    tabBar.innerHTML = tabs
      .map((t) => `<button class="chip ${t.id === active.id ? "is-on" : ""}" data-id="${t.id}">${t.label}</button>`)
      .join("");
    tabBar.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", async () => {
        active = tabs.find((t) => t.id === b.dataset.id);
        if (active?.id === "gfwfull") await ensureGfwFull();
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
              return `<td data-label="${escapeAttr(c)}">${escapeHtml(v ?? "")}</td>`;
            })
            .join("")}</tr>`
      )
      .join("");
    requestAnimationFrame(() => syncTablePaneScrollHints(document.getElementById("dataView") || document));
  };
  paintTabs();
  paintTable();
  window.addEventListener("resize", () => {
    if (state.view === "data" || state.view === "analisis") syncTablePaneScrollHints();
  });
}

boot().catch((err) => {
  console.error(err);
  setBooting(false);
  document.getElementById("updatedAt").textContent = "Gagal memuat data — jalankan skrip ekspor.";
  showStatusBanner("Data inti gagal dimuat. Chrome tetap tampil; perbaiki file data lalu muat ulang.");
  const content = document.getElementById("detailContent");
  if (content) {
    content.innerHTML = AtlasUI.detailShell({
      eyebrow: "Error",
      title: "Data belum tersedia",
      lead: err.message,
      bodyHtml: `<code class="cmd">python website/scripts/export_web_data.py</code>`,
    });
  }
  openDetail();
});
