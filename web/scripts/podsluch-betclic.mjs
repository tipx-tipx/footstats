/**
 * `node scripts/podsluch-betclic.mjs [adres]` — rozpoznanie API Betclica.
 *
 * DLACZEGO: kursy Betclica nie siedzą w surowym HTML strony meczu — strona
 * dokleja je w przeglądarce (rozpoznanie 2026-07-27). Ten skrypt otwiera
 * stronę Playwrightem i spisuje, co realnie leci po sieci.
 *
 * USTALONE 2026-07-28: Betclic wcale nie mówi JSON-em. Oferta idzie przez
 * **gRPC-Web** na `offering.begmedia.com/web/offering.access.api/
 * offering.access.api.MatchService/{Metoda}` — treść to binarny protobuf,
 * więc zapisujemy surowe bajty zapytania i odpowiedzi do rozbioru w Pythonie.
 *
 * Nic nie kupuje, nie loguje się i nie klika w zakłady — czyta publiczną
 * ofertę, tak jak zwykły odwiedzający.
 *
 * Wynik: zrzuty/betclic-podsluch.json (spis) + zrzuty/betclic/*.bin (treści).
 */

import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const KATALOG = "zrzuty/betclic";
const START = process.argv[2] ?? "https://www.betclic.pl/pilka-nozna-s1";
const CZEKAJ_MS = 8000;

function bezpiecznaNazwa(url) {
  return url
    .replace(/^https?:\/\//, "")
    .replace(/[^a-zA-Z0-9._-]+/g, "_")
    .slice(0, 100);
}

const zapytania = [];
let licznik = 0;

async function main() {
  await mkdir(KATALOG, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    locale: "pl-PL",
    viewport: { width: 1440, height: 1200 },
  });
  const page = await ctx.newPage();

  page.on("response", async (res) => {
    const url = res.url();
    if (!/begmedia\.com\/web\/|api|graphql/i.test(url)) return;
    if (/dam\.begmedia|rox\.begmedia|analytics|pixel/i.test(url)) return;

    const req = res.request();
    const nr = String(++licznik).padStart(3, "0");
    const baza = path.join(KATALOG, `${nr}-${bezpiecznaNazwa(url)}`);

    // wpis dopisujemy OD RAZU: część odpowiedzi to strumienie serwerowe
    // (…WithNotifications), których `body()` nie kończy się, dopóki strona
    // żyje — czekanie na nie gubiło właśnie te najciekawsze.
    const wpis = {
      url,
      metoda: req.method(),
      status: res.status(),
      typ: (res.headers()["content-type"] ?? "").split(";")[0],
      bajty: null,
      naglowki_zapytania: req.headers(),
      plik_odp: null,
      plik_zap: null,
    };
    zapytania.push(wpis);

    const dane = req.postDataBuffer();
    if (dane) {
      await writeFile(`${baza}.zap.bin`, dane);
      wpis.plik_zap = `${baza}.zap.bin`;
    }

    const buf = await Promise.race([
      res.body().catch(() => null),
      new Promise((r) => setTimeout(() => r(null), 6000)),
    ]);
    if (buf) {
      wpis.bajty = buf.length;
      await writeFile(`${baza}.odp.bin`, buf);
      wpis.plik_odp = `${baza}.odp.bin`;
    }
  });

  console.log(`otwieram ${START}`);
  await page.goto(START, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(CZEKAJ_MS);

  for (const tekst of ["Akceptuję", "Akceptuj", "Zgadzam się", "OK"]) {
    const btn = page.getByRole("button", { name: tekst, exact: false }).first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click().catch(() => {});
      await page.waitForTimeout(1500);
      break;
    }
  }

  // najpierw spróbuj wejść w rozgrywki, które realnie liczymy — rynki
  // zawodnicze bukmacherzy wystawiają tylko w bogatszych ligach
  const liga = await page
    .$$eval("a[href]", (as) =>
      as
        .map((a) => a.getAttribute("href"))
        .find((h) => h && /ekstraklasa|premier-league|laliga|la-liga|serie-a|bundesliga/i.test(h)),
    )
    .catch(() => null);
  if (liga) {
    const celLigi = new URL(liga, "https://www.betclic.pl").toString();
    console.log(`wchodzę w rozgrywki: ${celLigi}`);
    await page.goto(celLigi, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(CZEKAJ_MS);
  }

  const linki = await page.$$eval("a[href*='-m']", (as) =>
    as.map((a) => a.getAttribute("href")).filter((h) => h && /-m\d{6,}/.test(h)),
  );
  const unikalne = [...new Set(linki)];
  console.log(`znalezione linki meczów: ${unikalne.length}`);

  const wybrany =
    unikalne.find((h) => /ekstraklasa|premier-league|laliga|serie-a|bundesliga/i.test(h)) ??
    unikalne[0];

  if (wybrany) {
    const cel = new URL(wybrany, "https://www.betclic.pl").toString();
    console.log(`wchodzę w mecz: ${cel}`);
    await page.goto(cel, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(CZEKAJ_MS);

    // spis zakładek z rynkami — chcemy wiedzieć, czy jest sekcja zawodnicza
    const zakladki = await page
      .$$eval("[role='tab'], nav a, button", (els) =>
        els
          .map((e) => (e.textContent ?? "").trim())
          .filter((t) => t.length > 1 && t.length < 40),
      )
      .catch(() => []);
    console.log("zakładki na stronie meczu:", [...new Set(zakladki)].slice(0, 40).join(" | "));

    for (const tekst of ["Zawodnicy", "Zawodnik", "Strzelcy", "Statystyki", "Wszystkie"]) {
      const tab = page.getByText(tekst, { exact: false }).first();
      if (await tab.isVisible().catch(() => false)) {
        console.log(`klikam zakładkę: ${tekst}`);
        await tab.click().catch(() => {});
        await page.waitForTimeout(3500);
      }
    }
    await page.screenshot({ path: path.join(KATALOG, "mecz.png"), fullPage: true });
  }

  await writeFile(
    "zrzuty/betclic-podsluch.json",
    JSON.stringify({ start: START, linki: unikalne.slice(0, 20), zapytania }, null, 2),
    "utf8",
  );

  console.log(`\nzapytań ofertowych zapisanych: ${zapytania.length}`);
  for (const z of zapytania) {
    console.log(`  ${z.status} ${String(z.bajty ?? "-").padStart(8)} B  ${z.typ}  ${z.url.slice(0, 150)}`);
  }

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
