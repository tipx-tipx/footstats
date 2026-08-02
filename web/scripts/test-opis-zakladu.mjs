/**
 * Opis zakładu — `node scripts/test-opis-zakladu.mjs`.
 *
 * POWÓD (zgłoszenie usera 2026-08-02: „czemu jest strzały undefined"). Sklejanie
 * `rynek + strona + linia` było przepisane w OŚMIU komponentach i każda kopia
 * zakładała, że strona to „powyżej/poniżej", a linia zawsze coś znaczy. Rynek
 * „kto więcej", dodany 30 lipca, łamie oba założenia — i przez cztery dni
 * wyświetlał się jako:
 *
 *     Newell's Old Boys · 22:00 z Newell's Old Boys
 *     więcej: strzały undefined 0,0
 *
 * Trzy błędy naraz: `undefined` z brakującej etykiety, „0,0" z linii, której ten
 * rynek nie ma, i nazwa GOSPODARZA przy zakładzie na gościa.
 *
 * OSTATNI TEST JEST NAJWAŻNIEJSZY: nie sprawdza wpisanych na sztywno rynków,
 * tylko przechodzi po WSZYSTKICH `rynek_kod`, jakie naprawdę są w danych.
 * Dzięki temu następny nowy rynek zgłosi się sam, zanim zobaczy go user.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  nazwaPodmiotu,
  opisZakladu,
  rywalWZakladzie,
  stronaLinii,
} from "../src/lib/format.ts";

const KATALOG = path.dirname(fileURLToPath(import.meta.url));
let bledy = 0;

function sprawdz(nazwa, warunek, dodatek = "") {
  console.log(`${warunek ? "  ok  " : "BŁĄD  "}${nazwa}${dodatek ? ` — ${dodatek}` : ""}`);
  if (!warunek) bledy += 1;
}

/* --- 1. „kto więcej": nazwa drużyny, kierunek zakładu, zero linii --------- */

const gosc = {
  rynek: "Więcej: strzały",
  rynek_kod: "wiecej_shots",
  strona: "gosc",
  linia: 0,
  podmiot: "Newell's Old Boys",   // zawsze gospodarz — tak wymaga rozliczanie
  druzyna: "Boca Juniors",
  przeciwnik: "Newell's Old Boys",
  mecz: "Newell's Old Boys – Boca Juniors",
};

sprawdz(
  "przy zakładzie na gościa wiersz nazywa GOŚCIA, nie gospodarza",
  nazwaPodmiotu(gosc) === "Boca Juniors",
  nazwaPodmiotu(gosc),
);
sprawdz(
  "opis mówi, o co chodzi, bez linii i bez „undefined”",
  opisZakladu(gosc) === "więcej strzałów niż Newell's Old Boys",
  opisZakladu(gosc),
);

// ten sam rekord bez pól `druzyna`/`przeciwnik` — tak wygląda typ ROZLICZONY
// w Skuteczności, gdzie księga niesie wyłącznie `podmiot` i `mecz`
const goscZKsiegi = {
  rynek: "Więcej: strzały",
  rynek_kod: "wiecej_shots",
  strona: "gosc",
  linia: 0,
  podmiot: "Newell's Old Boys",
  mecz: "Newell's Old Boys – Boca Juniors",
};
sprawdz(
  "bez pola `druzyna` nazwa wylicza się z meczu i strony",
  nazwaPodmiotu(goscZKsiegi) === "Boca Juniors",
  nazwaPodmiotu(goscZKsiegi),
);

/* --- 2. suma meczowa: zakład jest o mecz, więc rywal z nazwy meczu -------- */

const suma = {
  rynek: "Rzuty rożne w meczu",
  rynek_kod: "match_corners",
  strona: "ponizej",
  linia: 9.5,
  podmiot: "River Plate",
  przeciwnik: "",                 // pipeline zostawia puste — zakład o cały mecz
  mecz: "River Plate – Rosario Central",
};
sprawdz(
  "suma meczowa opisuje się normalnie",
  opisZakladu(suma) === "rzuty rożne w meczu poniżej 9,5",
  opisZakladu(suma),
);
sprawdz(
  "rywal wyliczony z meczu — bez tego wiersz gubił GODZINĘ",
  rywalWZakladzie(suma) === "Rosario Central",
  rywalWZakladzie(suma),
);

/* --- 3. zwykłe rynki bez zmian ------------------------------------------- */

const zwykly = {
  rynek: "Gole drużyny",
  rynek_kod: "team_goals",
  strona: "ponizej",
  linia: 1.5,
  podmiot: "Cracovia",
  mecz: "Cracovia – Pogoń Szczecin",
};
sprawdz("rynek drużynowy bez zmian", opisZakladu(zwykly) === "gole drużyny poniżej 1,5");
sprawdz(
  "wersja krótka do ceduły ucina „drużyny”",
  opisZakladu(zwykly, true) === "gole poniżej 1,5",
  opisZakladu(zwykly, true),
);
sprawdz(
  "poprzeczka rysuje się tylko tam, gdzie istnieje",
  stronaLinii("ponizej") === "ponizej" && stronaLinii("gosc") === undefined,
);

/* --- 4. SIATKA NA PRZYSZŁOŚĆ: wszystkie rynki z prawdziwych danych -------- */

function wczytaj(nazwa) {
  const p = path.join(KATALOG, "..", "src", "data", "demo", nazwa);
  return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf8")) : null;
}

/**
 * Najpierw ŻYWY snapshot z Supabase, potem bundlowane demo.
 *
 * Demo zamraża się przy buildzie, więc nowy rynek nie pojawi się w nim nigdy —
 * a to właśnie nowy rynek jest tu niebezpieczny. Odczyt jest tylko do odczytu
 * i ma krótki limit czasu: bez sieci albo bez kluczy test leci dalej na demo,
 * tyle że mówi wprost, na czym się oparł.
 */
async function zZywych() {
  const env = path.join(KATALOG, "..", ".env.local");
  if (!fs.existsSync(env)) return null;
  const konf = Object.fromEntries(
    fs.readFileSync(env, "utf8").split(/\r?\n/).filter(Boolean).map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
    }),
  );
  const url = konf.SUPABASE_URL, klucz = konf.SUPABASE_ANON_KEY;
  if (!url || !klucz) return null;
  try {
    const res = await fetch(
      `${url}/rest/v1/app_data?select=key,payload&key=in.(value_bets,kupony,typy_wyniki)`,
      { headers: { apikey: klucz, Authorization: `Bearer ${klucz}` },
        signal: AbortSignal.timeout(15_000) },
    );
    if (!res.ok) return null;
    const mapa = Object.fromEntries((await res.json()).map((r) => [r.key, r.payload]));
    const dni = mapa.typy_wyniki?.skutecznosc_dzienna ?? [];
    return [
      ...(mapa.value_bets ?? []),
      ...((mapa.kupony ?? []).flatMap((k) => k.legi ?? [])),
      ...dni.flatMap((d) => d.typy ?? []),      // rynki JUŻ ROZLICZONE
    ];
  } catch {
    return null;
  }
}

const zywe = await zZywych();
const zrodla = zywe ?? [
  ...(wczytaj("value_bets.json") ?? []),
  ...(wczytaj("legi_pool.json") ?? []),
  ...((wczytaj("kupony.json") ?? []).flatMap((k) => k.legi ?? [])),
];
console.log(`\n  źródło rynków: ${zywe ? "żywy snapshot z Supabase" : "bundlowane demo"}`);

const rynki = new Map();
for (const b of zrodla) {
  if (!b?.rynek || b.strona == null) continue;
  if (!rynki.has(b.rynek_kod ?? b.rynek)) rynki.set(b.rynek_kod ?? b.rynek, b);
}

const zle = [];
for (const [kod, b] of rynki) {
  const opis = `${nazwaPodmiotu(b)} — ${opisZakladu(b)} / ${opisZakladu(b, true)}`;
  if (opis.includes("undefined") || opis.includes("NaN")) zle.push([kod, opis]);
}
sprawdz(
  `żaden z ${rynki.size} rynków w danych nie drukuje „undefined”`,
  zle.length === 0,
  zle.map(([k, o]) => `${k}: ${o}`).join(" | "),
);

console.log(
  bledy ? `\n${bledy} błędów` : `\nWszystko gra (${rynki.size} rynków z danych)`,
);
process.exit(bledy ? 1 : 0);
