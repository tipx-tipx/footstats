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

const adresy = process.argv.slice(2).filter((a) => a.startsWith("/"));
const strony = adresy.length > 0 ? adresy : DOMYSLNE;

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
      const plik = path.join(
        KATALOG,
        `${adres.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "start"}--${nazwa}.png`,
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
