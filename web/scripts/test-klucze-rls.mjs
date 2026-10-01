/**
 * Lista kluczy w polityce RLS MUSI się zgadzać z `BUNDLE_KEYS` w lib/data.ts.
 *
 * Po co osobny test: rozjazd tych dwóch list jest CICHY. PostgREST nie zwraca
 * błędu, gdy RLS odfiltruje wiersz — po prostu go nie ma w odpowiedzi.
 * `fetchBundle` widzi wtedy brak klucza i podstawia pod niego dane DEMO, więc
 * strona wygląda na sprawną, a pokazuje wymyślone mecze. Bez tego testu
 * dowiedzielibyśmy się o tym od użytkownika, i to nieprędko.
 *
 *     node --experimental-strip-types scripts/test-klucze-rls.mjs
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const tu = dirname(fileURLToPath(import.meta.url));
const SQL = join(tu, "..", "..", "supabase", "migrations", "0009_app_data_lekkie_klucze.sql");
const DATA_TS = join(tu, "..", "src", "lib", "data.ts");

function kluczeZSql(tekst) {
  // Wyrażenie w `using (...)` bywa opakowane (0005 obcina sufiks `__czNN`,
  // zanim porówna nazwę z listą), więc nie przywiązujemy się do jego kształtu
  // — bierzemy literały z bloku `in ( ... )`.
  const m = tekst.match(/using\s*\([\s\S]*?in\s*\(([\s\S]*?)\)\s*\)/i);
  if (!m) throw new Error("nie znalazłem listy kluczy w polityce RLS");
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
}

/**
 * DWIE ŚCIEŻKI ODCZYTU, JEDNA LISTA UPRAWNIEŃ (od 2026-08-06).
 *
 * Strona czyta klucze na dwa sposoby: bazowy `BUNDLE_KEYS` (jedno zapytanie
 * przy każdym renderze) oraz `fetchKlucz("nazwa", …)` — trzy najcięższe
 * klucze dociągane dopiero, gdy strona ich zażąda. Dla RLS to bez różnicy:
 * jedno i drugie idzie kluczem anon, więc polityka musi przepuszczać oba
 * zbiory. Gdyby ten test znał tylko `BUNDLE_KEYS`, kazałby usunąć z migracji
 * `players`, `typy_wyniki` i `odrzucenia` — a wtedy Skuteczność, Zawodnicy
 * i „czego nie typujemy" po cichu pokazałyby dane demo.
 */
function kluczeZKodu(tekst) {
  const m = tekst.match(/const BUNDLE_KEYS = \[([\s\S]*?)\] as const/);
  if (!m) throw new Error("nie znalazłem BUNDLE_KEYS w lib/data.ts");
  const bazowe = [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
  const leniwe = [...tekst.matchAll(/fetchKlucz<[^>]*>\(\s*"([^"]+)"/g)].map(
    (x) => x[1],
  );
  if (leniwe.length === 0) {
    throw new Error(
      "nie znalazłem ani jednego fetchKlucz() — jeśli leniwe pobieranie zniknęło, " +
        "usuń ten fragment testu razem z nim",
    );
  }
  return [...new Set([...bazowe, ...leniwe])];
}

const sql = kluczeZSql(readFileSync(SQL, "utf8"));
const kod = kluczeZKodu(readFileSync(DATA_TS, "utf8"));

const brakWSql = kod.filter((k) => !sql.includes(k));
const nadmiarWSql = sql.filter((k) => !kod.includes(k));

let bledy = 0;
if (brakWSql.length) {
  console.error(
    `BŁĄD: strona czyta klucze, których RLS nie przepuszcza: ${brakWSql.join(", ")}\n` +
      "       -> te sekcje pokażą DANE DEMO zamiast produkcji, bez żadnego błędu.",
  );
  bledy++;
}
if (nadmiarWSql.length) {
  console.error(
    `BŁĄD: RLS wystawia anonimowo klucze, których strona nie czyta: ${nadmiarWSql.join(", ")}\n` +
      "       -> to darmowy wyciek; usuń je z migracji 0004.",
  );
  bledy++;
}

// KOSZYKI ZAWODNIKÓW (2026-09-18): `players_d${nr}` składane w kodzie, więc
// nie ma ich wśród literałów — pilnujemy wzorca w polityce osobno.
// Od 0009 (lekkie klucze, 2026-10-01) trzy rodziny koszyków w jednym wzorcu
// `~ '^(players_d|zaw_k|kursy_m)[0-9]{2}$'`.
const sqlTekst = readFileSync(SQL, "utf8");
const dataTekst = readFileSync(DATA_TS, "utf8");
const wzorzec = sqlTekst.match(/~ '\^\(([a-z_|]+)\)\[0-9\]\{2\}\$'/);
const rodzinySql = wzorzec ? wzorzec[1].split("|") : [];
for (const [rodzina, skutek] of [
  ["players_d", "strona meczu wróci do pełnego `players` (~44 MB transferu)"],
  ["zaw_k", "strona zawodnika wróci do koszyków całych drużyn"],
  ["kursy_m", "strona meczu wróci do `odds_superbet` (jedna cena bez nazwy bukmachera)"],
]) {
  const czyta = dataTekst.includes("`" + rodzina + "${");
  if (czyta && !rodzinySql.includes(rodzina)) {
    console.error(`BŁĄD: strona czyta koszyki \`${rodzina}NN\`, a RLS ich nie przepuszcza.\n       -> ${skutek}.`);
    bledy++;
  }
  if (!czyta && rodzinySql.includes(rodzina)) {
    console.error(`BŁĄD: RLS wystawia koszyki \`${rodzina}NN\`, których strona nie czyta – usuń je z migracji.`);
    bledy++;
  }
}

if (bledy) process.exit(1);
console.log(`OK — ${sql.length} kluczy, polityka RLS zgadza się z BUNDLE_KEYS.`);
