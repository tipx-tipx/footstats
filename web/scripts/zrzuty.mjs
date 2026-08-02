/**
 * `npm run zrzuty` — zrzuty ekranu strony przez Playwright.
 *
 * DLACZEGO NIE `next dev`: serwer deweloperski na tym projekcie rozmnaża
 * workery PostCSS Turbopacka bez opamiętania (2026-07-27: dwa razy tego dnia,
 * ~1900 procesów i 14 GB RAM — patrz scripts/zombie.mjs). Produkcyjny
 * `next start` serwuje gotowy build, jednym procesem, bez Turbopacka.
 * Dlatego podglądy robimy WYŁĄCZNIE na buildzie.
 *
 * Skrypt sam: buduje (o ile nie ma świeżego builda), wstaje na wolnym porcie,
 * robi zrzuty i sprząta po sobie — także gdy coś padnie w środku.
 *
 * Użycie:
 *   npm run zrzuty                    — domyślny zestaw ekranów
 *   npm run zrzuty -- /model /kupony  — wybrane adresy
 *   npm run zrzuty -- --rozwin        — z ROZWINIĘTYMI kartami (domyślnie 3)
 *   npm run zrzuty -- --rozwin=6      — tyle pierwszych kart otwartych
 *
 * DLACZEGO `--rozwin`: skrypt fotografował wyłącznie listę zwiniętą, więc
 * rozwinięcia kart — czyli miejsce, w którym siedzi całe wyjaśnienie typu —
 * przechodziły do produkcji nieobejrzane (2026-08-01). Jeden przełącznik
 * zamiast obietnicy „następnym razem sprawdzę ręcznie".
 */

import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";

const PORT = Number(process.env.PORT_ZRZUTY ?? 3123);
const KATALOG = "zrzuty";
const SZEROKOSCI = [
  { nazwa: "laptop", width: 1440, height: 1200 },
  { nazwa: "telefon", width: 390, height: 1400 },
];
const DOMYSLNE = ["/model", "/model?widok=klient"];

// UWAGA na Git Bash: zamienia argument „/model" na ścieżkę windowsową
// („C:/Program Files/Git/model") — dlatego przyjmujemy TAKŻE zapis bez
// ukośnika (`npm run zrzuty -- model kupony`) i sami go dokładamy.
const adresy = process.argv
  .slice(2)
  .filter((a) => a && !a.startsWith("-") && !/^[A-Za-z]:/.test(a))
  .map((a) => (a.startsWith("/") ? a : `/${a}`));
const strony = adresy.length > 0 ? adresy : DOMYSLNE;

const flagaRozwin = process.argv.slice(2).find((a) => a.startsWith("--rozwin"));
const ILE_ROZWINAC = flagaRozwin
  ? Number(flagaRozwin.split("=")[1] ?? 3) || 3
  : 0;

function uruchom(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, {
      stdio: "inherit",
      shell: process.platform === "win32",
      ...opts,
    });
    p.on("exit", (kod) => (kod === 0 ? resolve() : reject(new Error(`${cmd} → ${kod}`))));
    p.on("error", reject);
  });
}

/**
 * Przewiń stronę od góry do dołu i wróć — żeby odpalić wszystkie animacje
 * wejścia, a potem zrobić zrzut całej (już widocznej) strony. Krok co 70%
 * wysokości okna, z chwilą na animację; na końcu powrót na górę, bo
 * `fullPage` renderuje od bieżącej pozycji przewijania.
 */
async function przewinCalosc(page) {
  const wysokoscOkna = page.viewportSize()?.height ?? 900;
  const krok = Math.round(wysokoscOkna * 0.7);
  let y = 0;
  for (let i = 0; i < 60; i++) {
    const koniec = await page.evaluate(
      ([y, krok]) => {
        window.scrollTo(0, y + krok);
        return window.scrollY + window.innerHeight >= document.body.scrollHeight - 2;
      },
      [y, krok],
    );
    y += krok;
    await page.waitForTimeout(220);
    if (koniec) break;
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(500);
}

/**
 * Rozwiń pierwsze `ile` kart na stronie. Karty rozwijają się przyciskiem
 * z `aria-expanded` — to samo w BetCard, RadarCard, BetRow i StsBetCard,
 * więc jeden selektor łapie wszystkie rodzaje list.
 */
async function rozwinKarty(page, ile) {
  // TYLKO karty (`article`) i wiersze TABELI, nie każdy `aria-expanded` na
  // stronie: filtry i przełączniki widoku też je mają i zjadały wszystkie
  // kliknięcia.
  //
  // TABELA DOSZŁA 2026-08-03. Skuteczność zwija poprzeczki jednego zakładu
  // w jeden wiersz (`WierszTypu`), a rozwinięcie siedzi w `<tbody>`, nie
  // w `<article>` — więc wpadało dokładnie w tę lukę, przed którą ten skrypt
  // miał chronić: user zobaczył je pierwszy i zgłosił jako nieczytelne.
  const SEL =
    'article button[aria-expanded="false"], table button[aria-expanded="false"]';
  const n = Math.min(await page.locator(SEL).count(), ile);
  for (let i = 0; i < n; i++) {
    // lista przelicza się po każdym kliknięciu (layout framer-motion),
    // więc za każdym razem bierzemy PIERWSZY zwinięty przycisk
    const p = page.locator(SEL).first();
    try {
      await p.scrollIntoViewIfNeeded({ timeout: 2000 });
      await p.click({ timeout: 2000 });
      await page.waitForTimeout(350);
    } catch {
      break; // przycisk zniknął albo zasłonięty — nie blokujemy zrzutu
    }
  }
  return n;
}

async function czekajNaSerwer(url, sekundy = 60) {
  for (let i = 0; i < sekundy * 2; i++) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      if (r.status > 0) return;
    } catch {
      /* jeszcze nie wstał */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("serwer nie wstał na czas");
}

let serwer = null;

async function sprzataj() {
  if (serwer && !serwer.killed) {
    // drzewo procesów: `next start` odpala potomka, samo SIGTERM na rodzicu
    // zostawiłoby port zajęty
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(serwer.pid), "/t", "/f"], {
        stdio: "ignore",
      });
    } else {
      serwer.kill("SIGTERM");
    }
  }
}
process.on("SIGINT", async () => {
  await sprzataj();
  process.exit(130);
});

try {
  if (!existsSync(".next/BUILD_ID")) {
    console.log("Brak builda — buduję (to potrwa chwilę)...");
    await uruchom("npx", ["next", "build"]);
  } else {
    console.log("Używam istniejącego builda (usuń .next, żeby przebudować).");
  }

  console.log(`Startuję serwer produkcyjny na :${PORT}...`);
  serwer = spawn("npx", ["next", "start", "-p", String(PORT)], {
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  await czekajNaSerwer(`http://localhost:${PORT}/model`);

  const { chromium } = await import("playwright");
  const browser = await chromium.launch();
  await rm(KATALOG, { recursive: true, force: true });
  await mkdir(KATALOG, { recursive: true });

  for (const { nazwa, width, height } of SZEROKOSCI) {
    const ctx = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: 1,
    });
    const page = await ctx.newPage();
    for (const adres of strony) {
      await page.goto(`http://localhost:${PORT}${adres}`, {
        waitUntil: "networkidle",
      });
      // animacje wejścia (framer-motion) — bez tego łapiemy je w połowie
      await page.waitForTimeout(900);
      // PRZEWIŃ CAŁĄ STRONĘ przed zrzutem. `Reveal` startuje z opacity 0
      // i pojawia się dopiero `whileInView` (IntersectionObserver), a
      // `fullPage: true` NIE przewija — renderuje wysoką klatkę z pozycji 0.
      // Efekt: wszystko poniżej pierwszego ekranu wychodziło NIEWIDOCZNE, a
      // zrzut wyglądał jak strona z brakującą treścią (zmierzone 2026-07-31
      // na „Jak to działa": widać 4 kroki z 10 i pół ekranu pustki).
      // To była wada NARZĘDZIA, nie strony — ale narzędzie jest jedynym
      // sposobem, w jaki oglądamy własne UI, więc kłamało nam do oczu.
      await przewinCalosc(page);
      if (ILE_ROZWINAC > 0) {
        const otwarte = await rozwinKarty(page, ILE_ROZWINAC);
        console.log(`  (rozwinięte karty: ${otwarte})`);
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(400);
      }
      const plik = path.join(
        KATALOG,
        `${adres.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "start"}${
          ILE_ROZWINAC > 0 ? "-rozwiniete" : ""
        }--${nazwa}.png`,
      );
      await page.screenshot({ path: plik, fullPage: true });
      console.log(`  ${plik}`);
    }
    await ctx.close();
  }
  await browser.close();
  console.log(`\nGotowe — zrzuty w web/${KATALOG}/`);
} finally {
  await sprzataj();
}
