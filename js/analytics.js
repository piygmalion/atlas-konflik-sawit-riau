/* Analytics charts — Polres + timeline kasus (enhanced) */

const charts = {
  polres: null,
  timeline: null,
  kepmen: null,
};

const chartState = {
  polresMode: "skor",
  timelineMode: "jenis",
};

const P2_COLORS = {
  brand: "#163528",
  accent: "#c45620",
  waspada: "#d09218",
  pantau: "#2f6a4c",
  soft: "#7a9a4a",
  ink: "#5a675f",
  series: [
    "#c45620",
    "#d09218",
    "#2f6a4c",
    "#5b7c65",
    "#8aa090",
    "#6a8f7a",
    "#a0673a",
    "#3d5c4a",
    "#c4891a",
    "#4f7a62",
    "#8b5a3c",
    "#5a7a5a",
  ],
};

const POLRES_ALIAS = {
  rohul: "Rokan Hulu",
  rohil: "Rokan Hilir",
  inhu: "Indragiri Hulu",
  inhil: "Indragiri Hilir",
  kuansing: "Kuantan Singingi",
  "kepulauan meranti": "Kepulauan Meranti",
  meranti: "Kepulauan Meranti",
};

function destroyChart(key) {
  if (charts[key]) {
    charts[key].destroy();
    charts[key] = null;
  }
}

function kategoriColor(kat) {
  const t = String(kat || "").toUpperCase();
  if (t.includes("PRIORITAS")) return P2_COLORS.accent;
  if (t.includes("WASPADA")) return P2_COLORS.waspada;
  return P2_COLORS.pantau;
}

function normalizePolresLabel(name) {
  let s = String(name || "").replace(/^Polres\s+/i, "").trim();
  const key = s.toLowerCase();
  return POLRES_ALIAS[key] || s;
}

function renderAnalytics() {
  if (!DATA.analytics) return;
  renderPolresChart();
  renderAgrinasFlow();
  renderAtlasFlow();
  renderTimelineChart();
  renderKepmenDonut();
  renderKepmenTable("all");
  requestAnimationFrame(() => {
    Object.values(charts).forEach((c) => c?.resize?.());
  });
}

function renderPolresChart() {
  const canvas = document.getElementById("chartPolres");
  if (!canvas || !window.Chart) return;
  destroyChart("polres");
  const rows = [...(DATA.analytics.polres_komponen || [])].sort(
    (a, b) => (a.peringkat || 99) - (b.peringkat || 99)
  );
  if (chartState.polresMode === "komponen") {
    renderPolresKomponen(canvas, rows);
  } else {
    renderPolresSkor(canvas, rows);
  }
}

function renderPolresSkor(canvas, rows) {
  charts.polres = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.label),
      datasets: [
        {
          label: "Skor komposit",
          data: rows.map((r) => Number(r.skor) || 0),
          backgroundColor: rows.map((r) => kategoriColor(r.kategori)),
          borderWidth: 0,
          borderRadius: 6,
          barPercentage: 0.7,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterBody(items) {
              const row = rows[items[0]?.dataIndex];
              if (!row) return "";
              const k = row.komponen || {};
              return [
                `${row.kategori}`,
                `Liputan ${fmtNum(k.liputan)} · Aksi ${fmtNum(k.aksi)} · Objek ${fmtNum(k.objek)}`,
                `Status ${fmtNum(k.status)} · Adat ${fmtNum(k.adat)}`,
              ];
            },
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          max: 100,
          grid: { color: "rgba(20,32,25,0.06)" },
          title: { display: true, text: "Skor 0–100" },
        },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
      onClick: (_evt, elements) => {
        if (!elements.length) return;
        openPolresFromChart(rows[elements[0].index]);
      },
    },
  });
}

function renderPolresKomponen(canvas, rows) {
  const keys = ["liputan", "aksi", "objek", "status", "adat"];
  const keyLabel = {
    liputan: "Liputan",
    aksi: "Aksi",
    objek: "Objek",
    status: "Status",
    adat: "Adat",
  };
  charts.polres = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.label),
      datasets: keys.map((k, i) => ({
        label: keyLabel[k],
        data: rows.map((r) => Number((r.komponen || {})[k]) || 0),
        backgroundColor: P2_COLORS.series[i],
        borderWidth: 0,
        borderRadius: 3,
        barPercentage: 0.85,
        categoryPercentage: 0.72,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 10, font: { family: "Instrument Sans", size: 11 } },
        },
        tooltip: {
          callbacks: {
            afterBody(items) {
              const row = rows[items[0]?.dataIndex];
              if (!row) return "";
              return `Skor ${Number(row.skor).toFixed(1)} · ${row.kategori}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { maxRotation: 45, minRotation: 30, font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { stepSize: 20 },
          grid: { color: "rgba(20,32,25,0.06)" },
        },
      },
      onClick: (_evt, elements) => {
        if (!elements.length) return;
        openPolresFromChart(rows[elements[0].index]);
      },
    },
  });
}

function openPolresFromChart(row) {
  if (!row?.polres || typeof window.showPolres !== "function") return;
  document.querySelector('.nav-btn[data-view="peta"]')?.click();
  setTimeout(() => window.showPolres(row.polres), 140);
}

function renderTimelineChart() {
  const canvas = document.getElementById("chartTimeline");
  if (!canvas || !window.Chart) return;
  destroyChart("timeline");
  if (chartState.timelineMode === "polres") {
    renderTimelineByPolres(canvas);
  } else {
    renderTimelineByJenis(canvas);
  }
}

function renderTimelineByJenis(canvas) {
  const tl = DATA.analytics.timeline || {};
  const years = tl.years || [];
  const cats = tl.categories || [];
  charts.timeline = new Chart(canvas, {
    type: "bar",
    data: {
      labels: years,
      datasets: cats.map((cat, i) => ({
        label: cat,
        data: years.map((y) => Number((tl.by_jenis?.[y] || {})[cat]) || 0),
        backgroundColor: P2_COLORS.series[i % P2_COLORS.series.length],
        borderWidth: 0,
        borderRadius: 4,
        stack: "kasus",
      })),
    },
    options: stackedTimelineOptions("Jumlah kasus (tahun disebut pada entri)"),
  });
}

function renderTimelineByPolres(canvas) {
  const tl = DATA.analytics.timeline || {};
  const years = tl.years || [];
  const byPolres = tl.by_polres || {};

  // Aggregate aliases into canonical labels; keep Polda separate
  const totals = {};
  years.forEach((y) => {
    Object.entries(byPolres[y] || {}).forEach(([raw, n]) => {
      const label = normalizePolresLabel(raw);
      totals[label] = (totals[label] || 0) + Number(n || 0);
    });
  });

  // Prefer ranking order for known Polres; then others by volume
  const ranked = (DATA.analytics.polres_komponen || []).map((p) => p.label);
  const ordered = [
    ...ranked.filter((l) => totals[l]),
    ...Object.keys(totals)
      .filter((l) => !ranked.includes(l))
      .sort((a, b) => totals[b] - totals[a]),
  ].slice(0, 12);

  charts.timeline = new Chart(canvas, {
    type: "bar",
    data: {
      labels: years,
      datasets: ordered.map((label, i) => ({
        label,
        data: years.map((y) => {
          const bag = byPolres[y] || {};
          let sum = 0;
          Object.entries(bag).forEach(([raw, n]) => {
            if (normalizePolresLabel(raw) === label) sum += Number(n || 0);
          });
          return sum;
        }),
        backgroundColor: P2_COLORS.series[i % P2_COLORS.series.length],
        borderWidth: 0,
        borderRadius: 3,
        stack: "polres",
      })),
    },
    options: stackedTimelineOptions("Jumlah kasus per Polres / unit (tahun disebut)"),
  });
}

function stackedTimelineOptions(yTitle) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: "bottom",
        labels: { boxWidth: 10, font: { family: "Instrument Sans", size: 11 } },
      },
    },
    scales: {
      x: { stacked: true, grid: { display: false } },
      y: {
        stacked: true,
        beginAtZero: true,
        grid: { color: "rgba(20,32,25,0.06)" },
        title: { display: true, text: yTitle },
      },
    },
  };
}

function renderKepmenDonut() {
  const canvas = document.getElementById("chartKepmen");
  if (!canvas || !window.Chart) return;
  destroyChart("kepmen");
  const buckets = DATA.analytics.kepmenhut?.buckets || [];
  const colors = {
    Berproses: P2_COLORS.pantau,
    Ditolak: P2_COLORS.accent,
    Campuran: P2_COLORS.waspada,
    Lainnya: P2_COLORS.soft,
  };
  charts.kepmen = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: buckets.map((b) => b.label),
      datasets: [
        {
          data: buckets.map((b) => b.value),
          backgroundColor: buckets.map((b) => colors[b.label] || P2_COLORS.ink),
          borderWidth: 0,
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 10, font: { family: "Instrument Sans", size: 11 } },
        },
      },
      onClick: (_evt, elements) => {
        if (!elements.length) return;
        const label = buckets[elements[0].index]?.label || "all";
        renderKepmenTable(label);
        document.querySelectorAll("#kepmenFilters .chip").forEach((c) => {
          c.classList.toggle("is-on", c.dataset.kepmen === label);
        });
      },
    },
  });
  const totalEl = document.getElementById("kepmenTotal");
  if (totalEl) {
    totalEl.textContent = String(
      DATA.analytics.kepmenhut?.total ?? buckets.reduce((s, b) => s + b.value, 0)
    );
  }
}

function renderKepmenTable(filterLabel) {
  const tbody = document.querySelector("#kepmenTable tbody");
  if (!tbody) return;
  const rows = DATA.analytics.kepmenhut?.records || [];
  const filtered = rows.filter((r) => {
    if (!filterLabel || filterLabel === "all") return true;
    const s = String(r.status || "").toLowerCase();
    if (filterLabel === "Berproses") return s.includes("berproses") && !s.includes("campuran");
    if (filterLabel === "Ditolak") return s.includes("ditolak") && !s.includes("berproses") && !s.includes("campuran");
    if (filterLabel === "Campuran") return s.includes("campuran");
    return true;
  });
  tbody.innerHTML = filtered
    .slice(0, 80)
    .map(
      (r) => `<tr>
        <td>${escapeHtml(r.nama || "")}</td>
        <td>${escapeHtml(r.status || "")}</td>
        <td>${fmtNum(r.luas_permohonan_ha)}</td>
        <td>${fmtNum(r.luas_berproses_ha)}</td>
        <td>${fmtNum(r.luas_ditolak_ha)}</td>
        <td>${escapeHtml(r.kelengkapan || "")}</td>
      </tr>`
    )
    .join("");
  const countEl = document.getElementById("kepmenFilterCount");
  if (countEl) countEl.textContent = `${filtered.length} subjek`;
}

function renderFlowSvg(containerId, links, titleNodes) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const nodeSet = [];
  const seen = new Set();
  links.forEach((l) => {
    if (!seen.has(l.source)) {
      seen.add(l.source);
      nodeSet.push(l.source);
    }
    if (!seen.has(l.target)) {
      seen.add(l.target);
      nodeSet.push(l.target);
    }
  });
  const ordered = (titleNodes || []).filter((n) => seen.has(n));
  const rest = nodeSet.filter((n) => !ordered.includes(n));
  const nodes = [...ordered, ...rest];
  if (!nodes.length) {
    el.innerHTML = `<p class="lead">Belum ada tautan alur.</p>`;
    return;
  }

  const width = Math.max(720, el.clientWidth || 720);
  const height = Math.max(220, nodes.length * 42);
  const leftX = 20;
  const rightX = width - 20;
  const midX = width / 2;
  const sources = new Set(links.map((l) => l.source));
  const targets = new Set(links.map((l) => l.target));
  const colOf = (n) => {
    const isSrc = sources.has(n);
    const isTgt = targets.has(n);
    if (isSrc && !isTgt) return 0;
    if (isTgt && !isSrc) return 2;
    return 1;
  };
  const cols = [[], [], []];
  nodes.forEach((n) => cols[colOf(n)].push(n));
  const pos = {};
  cols.forEach((col, ci) => {
    const x = ci === 0 ? leftX + 110 : ci === 1 ? midX : rightX - 110;
    col.forEach((n, i) => {
      pos[n] = { x, y: ((i + 1) / (col.length + 1)) * height };
    });
  });

  const maxV = Math.max(...links.map((l) => l.value), 1);
  const paths = links
    .map((l) => {
      const a = pos[l.source];
      const b = pos[l.target];
      if (!a || !b) return "";
      const sw = 2 + (l.value / maxV) * 18;
      const c1x = a.x + (b.x - a.x) * 0.45;
      const c2x = a.x + (b.x - a.x) * 0.55;
      return `<path d="M${a.x},${a.y} C${c1x},${a.y} ${c2x},${b.y} ${b.x},${b.y}" stroke="rgba(22,53,40,0.28)" stroke-width="${sw}" fill="none">
        <title>${escapeHtml(l.source)} → ${escapeHtml(l.target)}: ${l.value}${l.note ? " · " + escapeHtml(l.note) : ""}</title>
      </path>`;
    })
    .join("");

  const nodeSvg = nodes
    .map((n) => {
      const p = pos[n];
      const label = n.length > 28 ? n.slice(0, 27) + "…" : n;
      return `<g>
        <circle cx="${p.x}" cy="${p.y}" r="8" fill="#163528"></circle>
        <text x="${p.x}" y="${p.y - 14}" text-anchor="middle" font-size="11" fill="#142019" font-family="Instrument Sans, sans-serif">${escapeHtml(label)}</text>
      </g>`;
    })
    .join("");

  el.innerHTML = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" role="img" aria-label="Diagram alur">${paths}${nodeSvg}</svg>`;
}

function renderAgrinasFlow() {
  const flow = DATA.analytics.agrinas_flow || {};
  const counts = flow.counts || {};
  const strip = document.getElementById("agrinasCountStrip");
  if (strip) {
    strip.innerHTML = Object.entries(counts)
      .filter(([, v]) => v)
      .map(([k, v]) => `<div class="flow-stat"><strong>${v}</strong><span>${escapeHtml(k)}</span></div>`)
      .join("");
  }
  renderFlowSvg("agrinasFlow", flow.links || [], [
    "A. Pengelola",
    "B. Eks pengelola",
    "C. Mitra KSO",
    "D. Eks lahan (via KSO)",
    "E. Gelombang 1 Satgas",
    "F. Objek kawasan",
  ]);
}

function renderAtlasFlow() {
  const flow = DATA.analytics.atlas_flow || {};
  renderFlowSvg("atlasFlow", flow.links || [], [
    "Nusantara Atlas",
    "cocok",
    "ada di konflik",
    "tidak di konflik",
  ]);
}

function setupAnalyticsControls() {
  const kepmen = document.getElementById("kepmenFilters");
  if (kepmen) {
    kepmen.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      kepmen.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
      btn.classList.add("is-on");
      renderKepmenTable(btn.dataset.kepmen || "all");
    });
  }

  const polresMode = document.getElementById("polresChartMode");
  if (polresMode) {
    polresMode.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      polresMode.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
      btn.classList.add("is-on");
      chartState.polresMode = btn.dataset.mode || "skor";
      renderPolresChart();
    });
  }

  const timelineMode = document.getElementById("timelineChartMode");
  if (timelineMode) {
    timelineMode.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      timelineMode.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
      btn.classList.add("is-on");
      chartState.timelineMode = btn.dataset.mode || "jenis";
      renderTimelineChart();
    });
  }
}

window.renderAnalytics = renderAnalytics;
window.setupAnalyticsControls = setupAnalyticsControls;
window.renderKepmenTable = renderKepmenTable;
