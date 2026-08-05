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
const SQL = join(tu, "..", "..", "supabase", "migrations", "0004_app_data_rls.sql");
const DATA_TS = join(tu, "..", "src", "lib", "data.ts");

function kluczeZSql(tekst) {
  const m = tekst.match(/using\s*\(\s*key\s+in\s*\(([\s\S]*?)\)\s*\)/i);
  if (!m) throw new Error("nie znalazłem listy kluczy w polityce RLS");
  return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
}

function kluczeZKodu(tekst) {
  const m = tekst.match(/const BUNDLE_KEYS = \[([\s\S]*?)\] as const/);
  if (!m) throw new Error("nie znalazłem BUNDLE_KEYS w lib/data.ts");
  return [...m[1].matchAll(/"([^"]+)"/g)].map((x) => x[1]);
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

if (bledy) process.exit(1);
console.log(`OK — ${sql.length} kluczy, polityka RLS zgadza się z BUNDLE_KEYS.`);
