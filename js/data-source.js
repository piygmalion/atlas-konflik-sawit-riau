/**
 * Data source: lokal / Supabase PostgREST / FastAPI.
 * Dipakai app.js lewat window.AtlasData.
 */
(function (global) {
  const PATH_TO_DATASET = {
    "data/meta.json": "meta",
    "data/kab_kota.json": "kab_kota",
    "data/polres.json": "polres",
    "data/objek_agrinas.json": "objek_agrinas",
    "data/kasus.json": "kasus",
    "data/perusahaan.json": "perusahaan",
    "data/perusahaan_alias.json": "perusahaan_alias",
    "data/konsesi.json": "konsesi",
    "data/konsesi_gfw_full.json": "konsesi_gfw_full",
    "data/analytics.json": "analytics",
    "data/penertiban.json": "penertiban",
    "data/dq_report.json": "dq_report",
    "data/desa_lock.json": "desa_lock",
    "data/izin_2017.json": "izin_2017",
    "data/rantai_agrinas.json": "rantai_agrinas",
    "data/dossier.json": "dossier",
    "data/layers.geojson": "layers",
    "data/adm2_riau.geojson": "adm2",
    "data/gfw_konsesi.topojson": "gfw_konsesi",
    "data/gfw_konsesi.geojson": "gfw_konsesi",
  };

  function cfg() {
    return global.ATLAS_CONFIG || { dataSource: "local" };
  }

  function normalizePath(path) {
    const bare = String(path || "").split("?")[0];
    return bare.replace(/^\.\//, "");
  }

  function datasetFor(path) {
    return PATH_TO_DATASET[normalizePath(path)] || null;
  }

  async function fetchWithTimeout(url, options, ms) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    try {
      return await fetch(url, { ...options, signal: ctrl.signal });
    } finally {
      clearTimeout(t);
    }
  }

  async function loadLocal(path, assetVer) {
    const url = path.includes("?") ? path : `${path}?v=${assetVer || "0"}`;
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`Gagal memuat lokal ${path}`);
    return { data: await res.json(), source: "local" };
  }

  async function loadFromSupabase(dataset, conf) {
    if (!conf.supabaseUrl || !conf.supabaseAnonKey) {
      throw new Error("Supabase URL/anon key belum diisi di js/config.js");
    }
    const base = conf.supabaseUrl.replace(/\/$/, "");
    const url =
      `${base}/rest/v1/serving_datasets` +
      `?dataset=eq.${encodeURIComponent(dataset)}&select=payload,synced_at,checksum`;
    const res = await fetchWithTimeout(
      url,
      {
        headers: {
          apikey: conf.supabaseAnonKey,
          Authorization: `Bearer ${conf.supabaseAnonKey}`,
          Accept: "application/json",
        },
        cache: "no-cache",
      },
      conf.remoteTimeoutMs || 8000
    );
    if (!res.ok) throw new Error(`Supabase ${dataset}: HTTP ${res.status}`);
    const rows = await res.json();
    if (!rows?.length || rows[0].payload == null) {
      throw new Error(`Supabase: dataset ${dataset} kosong`);
    }
    return {
      data: rows[0].payload,
      source: "supabase",
      syncedAt: rows[0].synced_at,
      checksum: rows[0].checksum,
    };
  }

  async function loadFromApi(dataset, path, conf) {
    if (!conf.apiBaseUrl) throw new Error("apiBaseUrl belum diisi");
    const base = conf.apiBaseUrl.replace(/\/$/, "");
    const url = `${base}/api/v1/datasets/${encodeURIComponent(dataset)}?source=auto`;
    const res = await fetchWithTimeout(
      url,
      { cache: "no-cache" },
      conf.remoteTimeoutMs || 8000
    );
    if (!res.ok) throw new Error(`API ${dataset}: HTTP ${res.status}`);
    return {
      data: await res.json(),
      source: res.headers.get("X-Atlas-Source") || "api",
    };
  }

  /**
   * @param {string} path e.g. data/kasus.json
   * @param {string} assetVer cache-bust lokal
   */
  async function loadJSON(path, assetVer) {
    const conf = cfg();
    const mode = conf.dataSource || "local";
    const dataset = datasetFor(path);
    const tryRemote = mode === "auto" || mode === "supabase" || mode === "api";
    const mustRemote = mode === "supabase" || mode === "api";

    if (tryRemote && dataset) {
      try {
        if (mode === "api" || (mode === "auto" && conf.apiBaseUrl)) {
          return await loadFromApi(dataset, path, conf);
        }
        if (conf.supabaseUrl && conf.supabaseAnonKey) {
          return await loadFromSupabase(dataset, conf);
        }
        if (mustRemote) {
          throw new Error(`Mode ${mode} membutuhkan kredensial remote`);
        }
      } catch (err) {
        if (mustRemote) throw err;
        // auto → fallback lokal
        console.warn(`[AtlasData] remote gagal (${dataset}), fallback lokal:`, err.message || err);
      }
    }

    return loadLocal(path, assetVer);
  }

  global.AtlasData = {
    PATH_TO_DATASET,
    loadJSON,
    datasetFor,
  };
})(window);
