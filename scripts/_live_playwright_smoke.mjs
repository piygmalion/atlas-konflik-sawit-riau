/**
 * Live Pages UI smoke — map boot, layers, compare atlas ranking, detail CTA.
 */
import { chromium } from "playwright";

const BASE = "https://piygmalion.github.io/atlas-konflik-sawit-riau/";
const errors = [];
const notes = [];

function ok(label, cond, detail = "") {
  if (cond) notes.push(`PASS ${label}${detail ? " — " + detail : ""}`);
  else errors.push(`FAIL ${label}${detail ? " — " + detail : ""}`);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
page.setDefaultTimeout(45000);

try {
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !document.body.classList.contains("is-booting"), {
    timeout: 60000,
  });
  ok("boot complete", true);

  const assetVer = await page.locator('meta[name="atlas-asset-ver"]').getAttribute("content");
  ok("asset ver 0dc3", assetVer === "0dc3", `got ${assetVer}`);

  ok("map container", (await page.locator("#map").count()) === 1);

  // Layer list lives inside collapsed <details>
  const rail = page.locator("#railSecondary");
  if ((await rail.count()) === 1) {
    await rail.evaluate((el) => {
      el.open = true;
    });
    await page.waitForTimeout(200);
  }

  await page.waitForSelector("#layerList input[data-layer]", { timeout: 15000 });
  const hotspotToggle = page.locator('#layerList input[data-layer="hotspot_verifikasi"]');
  ok("hotspot layer toggle", (await hotspotToggle.count()) === 1);

  const gfwToggle = page.locator('#layerList input[data-layer="gfw_konsesi"]');
  ok("gfw toggle exists", (await gfwToggle.count()) === 1);
  if ((await gfwToggle.count()) === 1 && !(await gfwToggle.isChecked())) {
    await gfwToggle.check({ force: true });
    await page.waitForTimeout(2500);
  }

  const atlasChip = page.locator('.chip[data-compare="atlas"]');
  ok("atlas compare chip", (await atlasChip.count()) >= 1);
  if ((await atlasChip.count()) >= 1) {
    await atlasChip.first().click();
    await page.waitForTimeout(1000);
    const rankTitle = ((await page.locator("#rankTitle").textContent()) || "").trim();
    ok("atlas rank title dossier", /dossier|matching/i.test(rankTitle), rankTitle);
    const dossierBtns = page.locator("#polresList button[data-dossier]");
    const n = await dossierBtns.count();
    ok("dossier rank rows", n > 0, `n=${n}`);
    if (n > 0) {
      await dossierBtns.first().click();
      await page.waitForTimeout(700);
      const eyebrow = ((await page.locator("#detailContent .eyebrow").first().textContent()) || "").trim();
      const title = ((await page.locator("#detailContent h1").first().textContent()) || "").trim();
      ok("dossier detail opens", /dossier|matching/i.test(eyebrow) || title.length > 0, `${eyebrow} | ${title}`);
      const statusMatch = await page.locator("#detailContent").evaluate((el) =>
        /Status match/i.test(el.textContent || "")
      );
      ok("detail shows Status match", statusMatch);
    }
  }

  // Data tab
  const dataNav = page.locator('.nav-btn[data-view="data"]');
  ok("data nav", (await dataNav.count()) >= 1);
  if ((await dataNav.count()) >= 1) {
    await dataNav.first().click();
    await page.waitForTimeout(700);
    const dossierTab = page.locator('#tableTabs button[data-id="dossier"]');
    ok("data tab dossier chip", (await dossierTab.count()) === 1);
    if ((await dossierTab.count()) === 1) {
      await dossierTab.click();
      await page.waitForTimeout(500);
      const rows = await page.locator("#dataTable tbody tr").count();
      ok("dossier table rows", rows > 0, `rows=${rows}`);
    }
    ok(
      "data tab entity_matches chip",
      (await page.locator('#tableTabs button[data-id="entity_matches"]').count()) === 1
    );
  }

  // Analisis enrichment
  const analisisNav = page.locator('.nav-btn[data-view="analisis"]');
  if ((await analisisNav.count()) >= 1) {
    await analisisNav.first().click();
    await page.waitForTimeout(2500);
    ok("enrichment block", (await page.locator("#enrichmentBlock").count()) === 1);
    const izinText = ((await page.locator("#izinKabSummary").textContent()) || "").trim();
    ok(
      "izin summary loaded",
      /izin/i.test(izinText) && !/Menunggu muat/i.test(izinText),
      izinText.slice(0, 100)
    );
    const desaText = ((await page.locator("#desaLockSummary").textContent()) || "").trim();
    ok("desa summary loaded", desaText.length > 0 && !/Menunggu muat/i.test(desaText), desaText.slice(0, 80));
  }

  // Back to map — click kab choropleth via JS DATA if available
  const petaNav = page.locator('.nav-btn[data-view="peta"]');
  if ((await petaNav.count()) >= 1) {
    await petaNav.first().click();
    await page.waitForTimeout(500);
    const kabOpened = await page.evaluate(() => {
      if (typeof window.showKabupaten !== "function") return "no-fn";
      window.showKabupaten("Kampar");
      return "ok";
    });
    ok("showKabupaten callable", kabOpened === "ok", String(kabOpened));
    if (kabOpened === "ok") {
      await page.waitForTimeout(500);
      const body = (await page.locator("#detailContent").textContent()) || "";
      ok(
        "kab detail enrichment fields",
        /Verifikasi sebaran|N izin 2017|Kepercayaan sebaran/i.test(body),
        body.includes("Kampar") ? "Kampar detail" : "unexpected"
      );
    }
  }
} catch (err) {
  errors.push(`EXCEPTION ${err?.message || err}`);
} finally {
  await browser.close();
}

console.log("--- LIVE UI SMOKE ---");
for (const n of notes) console.log(n);
for (const e of errors) console.log(e);
console.log(errors.length ? "RESULT: FAIL" : "RESULT: PASS");
process.exit(errors.length ? 1 : 0);
