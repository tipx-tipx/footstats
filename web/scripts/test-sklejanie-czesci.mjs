/**
 * Sklejanie kluczy rozbitych na części — `node scripts/test-sklejanie-czesci.mjs`.
 *
 * POWÓD (zgłoszenie usera 2026-09-11: „nadal mam sierpień"). Strona Skuteczności
 * pokazywała kalendarz zatrzymany na 20 sierpnia, choć w bazie leżały rozliczenia
 * po 11 września. Dane były bez zarzutu — gubił je ODCZYT.
 *
 * `typy_wyniki` jedzie z pipeline'u w 10 częściach, a element cięższy od limitu
 * części pipeline tnie REKURENCYJNIE i owija podkawałki z powrotem w jego własny
 * klucz. Ten sam klucz najwyższego poziomu wraca więc w kilku częściach — na
 * produkcji tak wyglądały akurat dni i strumienie:
 *
 *     cz01 {"skutecznosc_dzienna": [17 dni]}      cz04..cz08 {"skutecznosc_strumienie": {…}}
 *     cz02 {"skutecznosc_dzienna": [3 dni]}
 *     cz03 {"skutecznosc_dzienna": [1 dzień]}
 *
 * `Object.assign` zostawiał z tego OSTATNI kawałek: 1 dzień z 21 (końcówka listy,
 * czyli dni najstarsze) i jeden strumień z pięciu. Pipeline czytał komplet, bo
 * `supa.sklej_czesci` scala w głąb — i to ten sam kontrakt musi trzymać front.
 *
 * DLATEGO OSTATNI TEST JEST NAJWAŻNIEJSZY: bierze prawdziwy podział z Supabase
 * (gdy są sekrety) i porównuje wynik sklejania z sumą tego, co przyszło
 * w częściach. Następny klucz, który przekroczy próg, zgłosi się sam.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { scalWGlab } from "../src/lib/sklejanie.ts";

const KATALOG = path.dirname(fileURLToPath(import.meta.url));
let bledy = 0;

function sprawdz(nazwa, warunek, dodatek = "") {
  console.log(`${warunek ? "  ok  " : "BŁĄD  "}${nazwa}${dodatek ? ` — ${dodatek}` : ""}`);
  if (!warunek) bledy += 1;
}

/** To samo, co robi `sklejCzesci` po dociągnięciu kawałków. */
function sklej(czesci) {
  if (Array.isArray(czesci[0])) return czesci.flat();
  const scalony = {};
  for (const cz of czesci) scalWGlab(scalony, cz ?? {});
  return scalony;
}

/* --- 1. ten sam klucz w kilku częściach: lista musi się ZSZYĆ ------------- */

const dni = sklej([
  { ostatnie: [1, 2], podsumowanie: { rozliczone: 2643 } },
  { skutecznosc_dzienna: [{ dzien: "2026-09-11" }, { dzien: "2026-09-10" }] },
  { skutecznosc_dzienna: [{ dzien: "2026-09-08" }] },
  { skutecznosc_dzienna: [{ dzien: "2026-08-20" }] },
]);

sprawdz("lista z trzech części ma wszystkie dni", dni.skutecznosc_dzienna.length === 4,
  `${dni.skutecznosc_dzienna.length} z 4`);
sprawdz("pierwszy dzień to najnowszy, nie końcówka listy",
  dni.skutecznosc_dzienna[0].dzien === "2026-09-11", dni.skutecznosc_dzienna[0].dzien);
sprawdz("klucze z innych części zostają", dni.podsumowanie?.rozliczone === 2643);

/* --- 2. słownik rozbity na części: scalamy W GŁĄB, nie nadpisujemy -------- */

const strumienie = sklej([
  { skutecznosc_strumienie: { druzyny: { n: 10 } } },
  { skutecznosc_strumienie: { pewniaki: { n: 20 } } },
  { skutecznosc_strumienie: { drabinki: { n: 30 }, zawodnicy: { n: 5 } } },
]);

sprawdz("wszystkie strumienie na miejscu",
  Object.keys(strumienie.skutecznosc_strumienie).sort().join(",") ===
    "drabinki,druzyny,pewniaki,zawodnicy",
  Object.keys(strumienie.skutecznosc_strumienie).join(","));

/* --- 3. części rozłączne (zwykły przypadek) działają jak dotąd ------------ */

const rozlaczne = sklej([{ a: 1 }, { b: [2] }, { c: { d: 3 } }]);
sprawdz("rozłączne części scalają się bez zmian",
  JSON.stringify(rozlaczne) === JSON.stringify({ a: 1, b: [2], c: { d: 3 } }),
  JSON.stringify(rozlaczne));

const listy = sklej([[1, 2], [3]]);
sprawdz("klucz będący listą nadal skleja się po kolei",
  JSON.stringify(listy) === "[1,2,3]", JSON.stringify(listy));

/* --- 4. skalar wygrywa z poprzednim skalarem (ostatnia część rządzi) ----- */

const skalar = sklej([{ ts: 1 }, { ts: 2 }]);
sprawdz("skalar nadpisuje się ostatnią wartością", skalar.ts === 2, String(skalar.ts));

/* --- 5. PRAWDZIWY PODZIAŁ Z SUPABASE — najważniejszy test ---------------- */

const env = { ...process.env };
for (const plik of [path.join(KATALOG, "..", ".env.local"),
                    path.join(KATALOG, "..", "..", "pipeline", ".env")]) {
  if (!fs.existsSync(plik)) continue;
  for (const linia of fs.readFileSync(plik, "utf8").split(/\r?\n/)) {
    const m = linia.match(/^\s*([A-Z_]+)\s*=\s*(.*)$/);
    if (m && !env[m[1]]) env[m[1]] = m[2].trim();
  }
}
const URL_S = env.SUPABASE_URL ?? env.NEXT_PUBLIC_SUPABASE_URL;
const KLUCZ = env.SUPABASE_ANON_KEY ?? env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!URL_S || !KLUCZ) {
  console.log("  --  podział z Supabase pominięty (brak SUPABASE_URL / ANON_KEY)");
} else {
  const naglowki = { apikey: KLUCZ, Authorization: `Bearer ${KLUCZ}` };
  const pobierz = async (k) => {
    const res = await fetch(
      `${URL_S}/rest/v1/app_data?select=payload&key=eq.${k}`, { headers: naglowki });
    if (!res.ok) return undefined;
    return (await res.json())[0]?.payload;
  };

  for (const key of ["typy_wyniki", "players", "odrzucenia"]) {
    const marker = await pobierz(key);
    const ile = typeof marker?.__czesci === "number" ? marker.__czesci : null;
    if (!ile) {
      console.log(`  --  '${key}' nie jest teraz dzielony — nic do sprawdzenia`);
      continue;
    }
    const czesci = [];
    for (let i = 0; i < ile; i += 1) {
      czesci.push(await pobierz(`${key}__cz${String(i).padStart(2, "0")}`));
    }
    if (czesci.some((cz) => cz === undefined)) {
      sprawdz(`'${key}': wszystkie ${ile} części widoczne kluczem anon`, false,
        "migracja 0005 (RLS dla '__czNN') wgrana?");
      continue;
    }
    if (Array.isArray(czesci[0])) {
      const suma = czesci.reduce((s, cz) => s + cz.length, 0);
      sprawdz(`'${key}': sklejona lista ma tyle, ile przyszło`,
        sklej(czesci).length === suma, `${suma}`);
      continue;
    }
    // ⚑ TU BYŁ BŁĄD: element rozbity na kilka części gubił się cały poza
    // ostatnim kawałkiem. Dla LIST żądamy sumy długości, dla SŁOWNIKÓW — unii
    // kluczy. Sumy kluczy słownika NIE wolno liczyć: rekurencja schodzi głębiej
    // i ten sam klucz wraca w kilku częściach (na produkcji
    // `skutecznosc_strumienie.druzyny` jest rozbity na trzy).
    // ⚑ OCZEKIWANIA LICZYMY PRZED SKLEJENIEM (sklejanie nie ma prawa ruszać
    // kawałków, ale to właśnie ten test ma pilnować).
    const sumyList = {};
    const unieKluczy = {};
    for (const cz of czesci) {
      for (const [k, v] of Object.entries(cz)) {
        if (Array.isArray(v)) sumyList[k] = (sumyList[k] ?? 0) + v.length;
        else if (v && typeof v === "object") {
          unieKluczy[k] = new Set([...(unieKluczy[k] ?? []), ...Object.keys(v)]);
        }
      }
    }
    const calosc = sklej(czesci);
    if (Array.isArray(calosc)) {
      const suma = czesci.reduce((s, cz) => s + cz.length, 0);
      sprawdz(`'${key}': sklejona lista ma tyle, ile przyszło`, calosc.length === suma,
        `${calosc.length} z ${suma}`);
      continue;
    }
    for (const [k, ile_wierszy] of Object.entries(sumyList)) {
      const v = calosc[k];
      const mam = Array.isArray(v) ? v.length : -1;
      sprawdz(`'${key}.${k}': lista w komplecie`, mam === ile_wierszy,
        mam === ile_wierszy ? `${mam}` :
          `${mam} z ${ile_wierszy} (jeśli pipeline pisał w trakcie odczytu — powtórz)`);
    }
    for (const [k, klucze] of Object.entries(unieKluczy)) {
      const v = calosc[k];
      const brak = [...klucze].filter((kk) => !(v && kk in v));
      sprawdz(`'${key}.${k}': wszystkie klucze na miejscu`, brak.length === 0,
        brak.length ? `brakuje ${brak.join(", ")}` : `${klucze.size}`);
    }
  }
}

console.log(bledy === 0 ? "\nWszystko zielone." : `\n${bledy} błędów.`);
process.exit(bledy === 0 ? 0 : 1);
