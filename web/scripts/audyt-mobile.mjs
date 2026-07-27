/**
 * `npm run audyt` — szuka miejsc, w których strona ucieka w bok na telefonie.
 *
 * Poziome przewijanie na komórce to najbardziej irytująca wada układu i
 * jednocześnie najtrudniejsza do wypatrzenia okiem: wystarczy jeden element
 * szerszy od ekranu, żeby CAŁA strona zaczęła się bujać lewo-prawo. Zamiast
 * zgadywać, pytamy przeglądarki wprost — który element wystaje poza szerokość
 * okna i o ile.
 *
 * Uwaga na dwa rodzaje przewijania:
 *   ZŁE  — przewija się CAŁA strona (document.scrollWidth > innerWidth),
 *   DOBRE — przewija się pojedynczy kontener, który świadomie na to pozwala
 *           (szeroka tabela w `overflow-x-auto`). Tego nie zgłaszamy.
 *
 * Jedzie na buildzie produkcyjnym (`next start`), nigdy na `next dev` —
 * patrz scripts/zombie.mjs.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";

const PORT = Number(process.env.PORT_AUDYT ?? 3124);
const SZEROKOSC = 390; // iPhone 14/15
const STRONY = ["/", "/druzyny", "/kupony", "/mecze", "/zaklady", "/model", "/jak-to-dziala", "/login"];

let serwer = null;
const sprzataj = () => {
  if (serwer && !serwer.killed) {
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(serwer.pid), "/t", "/f"], { stdio: "ignore" });
    } else serwer.kill("SIGTERM");
  }
};
process.on("SIGINT", () => { sprzataj(); process.exit(130); });

async function czekaj(url, sekundy = 60) {
  for (let i = 0; i < sekundy * 2; i++) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      if (r.status > 0) return;
    } catch { /* wstaje */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("serwer nie wstał");
}

try {
  if (!existsSync(".next/BUILD_ID")) {
    console.error("Brak builda — uruchom najpierw `npm run build`.");
    process.exit(1);
  }
  serwer = spawn("npx", ["next", "start", "-p", String(PORT)], {
    stdio: "ignore",
    shell: process.platform === "win32",
  });
  await czekaj(`http://localhost:${PORT}/`);

  const { chromium } = await import("playwright");
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: SZEROKOSC, height: 900 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await ctx.newPage();

  let problemy = 0;
  for (const adres of STRONY) {
    await page.goto(`http://localhost:${PORT}${adres}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(600);

    const wynik = await page.evaluate((szer) => {
      const przewijaSie = document.documentElement.scrollWidth > szer + 1;
      if (!przewijaSie) return { przewijaSie, winni: [], szerokosc: document.documentElement.scrollWidth };
      const winni = [];
      for (const el of document.querySelectorAll("body *")) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        const wystaje = Math.round(r.right - szer);
        if (wystaje <= 1) continue;
        // element W ŚRODKU świadomie przewijalnego kontenera jest w porządku —
        // to jego rodzic bierze na siebie przewijanie, nie strona
        let rodzic = el.parentElement;
        let wSwiadomymKontenerze = false;
        while (rodzic && rodzic !== document.body) {
          const st = getComputedStyle(rodzic);
          if (st.overflowX === "auto" || st.overflowX === "scroll" || st.overflowX === "hidden") {
            wSwiadomymKontenerze = true;
            break;
          }
          rodzic = rodzic.parentElement;
        }
        if (wSwiadomymKontenerze) continue;
        winni.push({
          tag: el.tagName.toLowerCase(),
          klasy: String(el.className || "").slice(0, 110),
          tekst: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60),
          wystaje,
          szerokosc: Math.round(r.width),
        });
      }
      // najgłębsze/najszersze najpierw, bez duplikatów rodzic-dziecko
      winni.sort((a, b) => b.wystaje - a.wystaje);
      return { przewijaSie, winni: winni.slice(0, 6), szerokosc: document.documentElement.scrollWidth };
    }, SZEROKOSC);

    // DRUGA CZĘŚĆ: kontenery, które przewijają się w bok świadomie.
    // Nie są błędem same z siebie, ale każdy z nich to miejsce, w którym user
    // musi przesuwać palcem — więc mają być tylko tam, gdzie naprawdę trzeba
    // (szeroka tabela, pasek zakładek). Wypisujemy je do oceny, nie do alarmu.
    const przewijalne = await page.evaluate(() => {
      const out = [];
      for (const el of document.querySelectorAll("body *")) {
        const st = getComputedStyle(el);
        if (st.overflowX !== "auto" && st.overflowX !== "scroll") continue;
        if (el.scrollWidth <= el.clientWidth + 1) continue;
        out.push({
          tag: el.tagName.toLowerCase(),
          klasy: String(el.className || "").slice(0, 70),
          widac: el.clientWidth,
          jest: el.scrollWidth,
          tekst: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 45),
        });
      }
      return out;
    });

    if (!wynik.przewijaSie) {
      console.log(`  ok    ${adres}`);
      for (const s of przewijalne) {
        console.log(`         · przesuw w bok: <${s.tag}> ${s.widac}→${s.jest}px  "${s.tekst}"`);
      }
      continue;
    }
    problemy += 1;
    console.log(`  UCIEKA ${adres} — strona ma ${wynik.szerokosc}px zamiast ${SZEROKOSC}px`);
    for (const w of wynik.winni) {
      console.log(`         +${w.wystaje}px  <${w.tag}> ${w.szerokosc}px  "${w.tekst}"`);
      console.log(`                  ${w.klasy}`);
    }
  }

  await browser.close();
  console.log(
    problemy === 0
      ? `\nCzysto — żadna strona nie ucieka w bok przy ${SZEROKOSC}px.`
      : `\n${problemy} stron ucieka w bok.`,
  );
  process.exitCode = problemy === 0 ? 0 : 1;
} finally {
  sprzataj();
}
