/* Prioritas 3 — modul Penertiban KH / Tesso Nilo / 27 PT */

const penertibanCharts = {
  kab: null,
};

function destroyPenertibanChart(key) {
  if (penertibanCharts[key]) {
    penertibanCharts[key].destroy();
    penertibanCharts[key] = null;
  }
}

function renderPenertibanModule() {
  if (!DATA.penertiban) return;
  renderPenertibanStats();
  renderPenertibanKabChart();
  renderGelombangTable("all");
  renderTessoCards();
  renderKronologiPenertiban();
  requestAnimationFrame(() => penertibanCharts.kab?.resize?.());
}

function renderPenertibanStats() {
  const el = document.getElementById("penertibanStats");
  if (!el) return;
  const n = DATA.penertiban.normalized || {};
  const kabN = n.sebaran_kab_korporasi_kh?.total || 0;
  const ptN = n.gelombang1_27_pt?.total || 0;
  const skN = n.sk36_2025_110a?.total || 0;
  const top = [...(n.sebaran_kab_korporasi_kh?.records || [])].sort(
    (a, b) => (Number(b.luas_ha) || 0) - (Number(a.luas_ha) || 0)
  )[0];
  const tesso = (DATA.penertiban.sections?.operasi_tesso_nilo?.records || []).find((r) =>
    String(r["Peristiwa / indikator"] || "").toLowerCase().includes("luas kawasan")
  );
  el.innerHTML = [
    { v: kabN, l: "Kab korporasi di KH" },
    { v: ptN, l: "PT gelombang 1" },
    { v: skN, l: "Subjek SK36 110A" },
    {
      v: top ? fmtNum(top.luas_ha) : "–",
      l: top ? `Top: ${String(top.kab_kota || "").replace(/^Kab\.?\s*/i, "")}` : "Top kab",
    },
    {
      v: tesso?.["Luas / jumlah"] || "~81.793 ha",
      l: "TN Tesso Nilo",
    },
  ]
    .map(
      (x) => `<div class="flow-stat"><strong>${escapeHtml(String(x.v))}</strong><span>${escapeHtml(x.l)}</span></div>`
    )
    .join("");
}

function renderPenertibanKabChart() {
  const canvas = document.getElementById("chartPenertibanKab");
  if (!canvas || !window.Chart) return;
  destroyPenertibanChart("kab");
  const rows = [...(DATA.penertiban.normalized?.sebaran_kab_korporasi_kh?.records || [])]
    .filter((r) => Number(r.luas_ha) > 0)
    .sort((a, b) => (Number(b.luas_ha) || 0) - (Number(a.luas_ha) || 0));
  const labels = rows.map((r) => String(r.kab_kota || "").replace(/^Kab\.?\s*/i, "").replace(/^Kota\s*/i, ""));
  penertibanCharts.kab = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Luas korporasi di KH (ha)",
          data: rows.map((r) => Number(r.luas_ha) || 0),
          backgroundColor: rows.map((_, i) => (i < 3 ? "#c45620" : i < 6 ? "#d09218" : "#5b7c65")),
          borderWidth: 0,
          borderRadius: 5,
          barPercentage: 0.72,
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
              return [`Porsi ${row.porsi || "–"}`, row.catatan || ""].filter(Boolean);
            },
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: "rgba(20,32,25,0.06)" },
          title: { display: true, text: "Hektar" },
        },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
      onClick: (_evt, els) => {
        if (!els.length) return;
        const row = rows[els[0].index];
        openKabFromPenertiban(row?.kab_kota);
      },
    },
  });
}

function openKabFromPenertiban(nama) {
  if (!nama || typeof window.showKabupaten !== "function") return;
  document.querySelector('.nav-btn[data-view="peta"]')?.click();
  setTimeout(() => window.showKabupaten(nama), 140);
}

function renderGelombangTable(kabFilter) {
  const tbody = document.querySelector("#gelombangTable tbody");
  const note = document.getElementById("gelombangFilterCount");
  if (!tbody) return;
  const rows = DATA.penertiban.normalized?.gelombang1_27_pt?.records || [];
  const filtered =
    kabFilter && kabFilter !== "all"
      ? rows.filter((r) => matchWilayah(r.kabupaten, kabFilter) || String(r.kabupaten || "").toLowerCase().includes(String(kabFilter).toLowerCase()))
      : rows;
  if (note) note.textContent = `${filtered.length} dari ${rows.length} PT gelombang 1`;
  tbody.innerHTML = filtered
    .map((r) => {
      const atlas = findAtlasMatch(r.perusahaan);
      const gfw = findGfwRecord(r.perusahaan);
      const link = atlasDeepLink(atlas?.atlas_nama || r.perusahaan, gfw);
      return `<tr>
        <td>${escapeHtml(r.no ?? "")}</td>
        <td>
          <strong>${escapeHtml(r.perusahaan || "")}</strong>
          <div class="row-actions">
            <button type="button" class="text-btn" data-kab="${escapeAttr(r.kabupaten || "")}">Peta kab</button>
            <a class="text-btn" href="${escapeAttr(link.href)}" target="_blank" rel="noopener" title="${escapeAttr(link.title)}">Atlas</a>
          </div>
        </td>
        <td>${escapeHtml(r.kabupaten || "")}</td>
        <td>${escapeHtml(r.afiliasi || "–")}</td>
        <td>${escapeHtml(r.catatan || "–")}</td>
      </tr>`;
    })
    .join("");
  tbody.querySelectorAll("button[data-kab]").forEach((btn) => {
    btn.addEventListener("click", () => openKabFromPenertiban(btn.dataset.kab));
  });
}

function renderTessoCards() {
  const el = document.getElementById("tessoCards");
  if (!el) return;
  const rows = (DATA.penertiban.sections?.operasi_tesso_nilo?.records || []).filter(
    (r) => r["Peristiwa / indikator"] && !String(r["Peristiwa / indikator"]).startsWith("col_")
  );
  const pick = rows.slice(0, 8);
  el.innerHTML = pick
    .map(
      (r) => `<article class="mini-card">
        <p class="eyebrow">${escapeHtml(r.Periode || "Operasi")}</p>
        <h3>${escapeHtml(r["Peristiwa / indikator"] || "")}</h3>
        <p><strong>${escapeHtml(r["Luas / jumlah"] || "–")}</strong> · ${escapeHtml(r.Lokasi || "")}</p>
        <p class="muted">${escapeHtml(r.Aktor || "")}${r.Sumber ? ` · ${escapeHtml(r.Sumber)}` : ""}</p>
      </article>`
    )
    .join("");
}

function renderKronologiPenertiban() {
  const el = document.getElementById("kronologiPenertiban");
  if (!el) return;
  const rows = (DATA.penertiban.sections?.kronologi?.records || []).filter((r) => r["Tanggal / periode"]);
  el.innerHTML = rows
    .map(
      (r) => `<li>
        <time>${escapeHtml(r["Tanggal / periode"])}</time>
        <div>
          <strong>${escapeHtml(r.Peristiwa || "")}</strong>
          <span>${escapeHtml(r.Skala || "")}</span>
          <p>${escapeHtml(r["Implikasi untuk Riau"] || "")}</p>
        </div>
      </li>`
    )
    .join("");
}

function setupPenertibanControls() {
  const filters = document.getElementById("gelombangKabFilters");
  if (!filters || filters.dataset.bound) return;
  filters.dataset.bound = "1";
  const kabs = [
    "all",
    ...new Set(
      (DATA.penertiban?.normalized?.gelombang1_27_pt?.records || [])
        .map((r) => r.kabupaten)
        .filter(Boolean)
    ),
  ];
  filters.innerHTML = kabs
    .map(
      (k, i) =>
        `<button class="chip ${i === 0 ? "is-on" : ""}" data-kab="${escapeAttr(k)}">${
          k === "all" ? "Semua kab" : escapeHtml(k)
        }</button>`
    )
    .join("");
  filters.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    filters.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-on"));
    btn.classList.add("is-on");
    renderGelombangTable(btn.dataset.kab || "all");
  });
}

window.renderPenertibanModule = renderPenertibanModule;
window.setupPenertibanControls = setupPenertibanControls;
