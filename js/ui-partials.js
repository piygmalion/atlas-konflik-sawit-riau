/**
 * Pure HTML partials for Atlas UI — no framework.
 * Loaded before app.js / analytics.js so escape helpers are shared.
 */
(function (global) {
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

  function badge(text, className = "") {
    if (text == null || text === "") return "";
    const cls = className ? ` ${escapeAttr(className)}` : "";
    return `<span class="badge${cls}">${escapeHtml(text)}</span>`;
  }

  function chip(text, { soft = false } = {}) {
    if (!text) return "";
    const cls = soft ? "case-chip case-chip--soft" : "case-chip";
    return `<span class="${cls}">${escapeHtml(text)}</span>`;
  }

  function chipsRow(items) {
    const html = (items || []).filter(Boolean).join("");
    return html ? `<div class="case-card__chips">${html}</div>` : "";
  }

  /**
   * @param {{ label: string, value?: string|number, html?: string, strong?: boolean, badgeText?: string, badgeClass?: string }} item
   */
  function metaItem(item) {
    if (!item) return "";
    const label = escapeHtml(item.label || "");
    let body = item.html;
    if (body == null) {
      const raw = item.value == null || item.value === "" ? "–" : item.value;
      body = item.strong ? `<strong>${escapeHtml(raw)}</strong>` : escapeHtml(raw);
    }
    const badgeHtml = item.badgeText != null && item.badgeText !== ""
      ? ` ${badge(item.badgeText, item.badgeClass || "")}`
      : "";
    return `<div class="meta-item"><label>${label}</label>${body}${badgeHtml}</div>`;
  }

  function metaGrid(items) {
    const rows = (items || []).map(metaItem).filter(Boolean).join("");
    return rows ? `<div class="meta-grid">${rows}</div>` : "";
  }

  function howto(steps) {
    const cells = (steps || [])
      .map((s, i) => {
        const n = s.n != null ? s.n : i + 1;
        const label = s.label || s;
        return `<div><strong>${escapeHtml(n)}</strong><span>${escapeHtml(label)}</span></div>`;
      })
      .join("");
    return cells ? `<div class="howto">${cells}</div>` : "";
  }

  function detailActions(links) {
    const html = (links || [])
      .filter((l) => l && l.href)
      .map((l) => {
        const cls = l.ghost ? "btn-link ghost" : "btn-link";
        return `<a class="${cls}" href="${escapeAttr(l.href)}" target="_blank" rel="noopener"${
          l.title ? ` title="${escapeAttr(l.title)}"` : ""
        }>${escapeHtml(l.label || "Buka")}</a>`;
      })
      .join("");
    return html ? `<p class="detail-actions">${html}</p>` : "";
  }

  function sectionLabel(text) {
    return text ? `<h2 class="section-label">${escapeHtml(text)}</h2>` : "";
  }

  function emptyNote(text) {
    return `<p class="lead">${escapeHtml(text || "Tidak ada data.")}</p>`;
  }

  function listBlock(className, innerHtml, emptyText) {
    const body = innerHtml || emptyNote(emptyText);
    return `<div class="${escapeAttr(className)}">${body}</div>`;
  }

  /**
   * Standard detail panel shell used by kab/polres/titik/etc.
   * @param {{ eyebrow: string, title: string, lead?: string, meta?: object[], bodyHtml?: string }} opts
   */
  function detailShell({ eyebrow = "", title = "", lead = "", meta = [], bodyHtml = "" } = {}) {
    return [
      eyebrow ? `<p class="eyebrow">${escapeHtml(eyebrow)}</p>` : "",
      title ? `<h1>${escapeHtml(title)}</h1>` : "",
      lead ? `<p class="lead">${escapeHtml(lead)}</p>` : "",
      metaGrid(meta),
      bodyHtml || "",
    ].join("\n");
  }

  function caseCardHtml({ title, id, body, chipsHtml, ref, refTitle }) {
    return `<article class="case-card">
    <header class="case-card__head">
      <strong class="case-card__title">${escapeHtml(truncate(title, 78))}</strong>
      ${id ? `<span class="case-card__id">${escapeHtml(id)}</span>` : ""}
    </header>
    ${body ? `<p class="case-card__body">${escapeHtml(truncate(body, 140))}</p>` : ""}
    ${chipsHtml || ""}
    ${
      ref
        ? `<p class="case-card__ref" title="${escapeAttr(refTitle || ref)}">${escapeHtml(ref)}</p>`
        : ""
    }
  </article>`;
  }

  function objCardHtml({ title, chipsHtml }) {
    return `<article class="obj-card">
    <strong class="obj-card__title">${escapeHtml(truncate(title, 72))}</strong>
    ${chipsHtml || ""}
  </article>`;
  }

  function shortCompanyLabel(name) {
    let t = String(name || "").replace(/^\s*PT\.?\s+/i, "").trim();
    return truncate(t, 28);
  }

  function mapPreviewHtml({
    eyebrow = "",
    title = "",
    skor = null,
    level = "",
    metricLabel = "",
    metaLines = [],
    polres = "",
    company = "",
    companyLabel = "",
    cta = "Klik untuk detail",
  } = {}) {
    const hasSkor = skor != null && skor !== "" && !Number.isNaN(Number(skor));
    const companyBtn = company
      ? `<button type="button" class="map-preview__company" data-action="perusahaan" data-perusahaan="${escapeAttr(company)}" title="Buka profil ${escapeAttr(company)}">${escapeHtml(
          companyLabel || shortCompanyLabel(company)
        )}</button>`
      : "";
    const levelBadge = !companyBtn && level ? badge(level, level) : "";
    const scoreBlock = hasSkor
      ? `<div class="map-preview__score">
        <div class="map-preview__score-main">
          <span class="map-preview__score-num">${escapeHtml(fmtNum(skor))}</span>
          ${companyBtn || levelBadge}
        </div>
        ${metricLabel ? `<div class="map-preview__metric">${escapeHtml(metricLabel)}</div>` : ""}
      </div>`
      : companyBtn || levelBadge
        ? `<div class="map-preview__score">${companyBtn || levelBadge}</div>`
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

  const AtlasUI = {
    escapeHtml,
    escapeAttr,
    fmtNum,
    truncate,
    badge,
    chip,
    chipsRow,
    metaItem,
    metaGrid,
    howto,
    detailActions,
    sectionLabel,
    emptyNote,
    listBlock,
    detailShell,
    caseCardHtml,
    objCardHtml,
    mapPreviewHtml,
  };

  global.AtlasUI = AtlasUI;
  // Shared globals for analytics.js / penertiban.js / app.js
  global.escapeHtml = escapeHtml;
  global.escapeAttr = escapeAttr;
  global.fmtNum = fmtNum;
  global.truncate = truncate;
})(typeof window !== "undefined" ? window : globalThis);
