/**
 * Kontrakt ról — `node scripts/test-rol.mjs`.
 *
 * Nie ma tu frameworka testowego (web go nie ma), a to jest jedyne miejsce
 * w aplikacji, gdzie błąd znaczy „klient zewnętrzny widzi kuchnię modelu".
 * Sprawdzamy cztery rzeczy, które muszą być prawdziwe:
 *
 *   1. token klienta czyta się jako klient,
 *   2. PODMIANA roli w ciasteczku unieważnia podpis (nie da się awansować),
 *   3. token sprzed podziału na role dalej działa i znaczy admin
 *      (wdrożenie nie wylogowuje nikogo w środku pracy),
 *   4. token po terminie nie działa niezależnie od roli,
 *   5. kuchnia modelu (Kontrola, typy w tle) nie jest liczona dla klienta.
 */

import { createSessionToken, verifySessionRole } from "../src/lib/auth.ts";

const S = "sekret-do-testu";
let bledy = 0;

function sprawdz(nazwa, warunek) {
  console.log(`${warunek ? "  ok  " : "BŁĄD  "}${nazwa}`);
  if (!warunek) bledy += 1;
}

const admin = await createSessionToken(S, "admin");
const klient = await createSessionToken(S, "klient");

sprawdz("token admina czyta się jako admin", (await verifySessionRole(admin, S)) === "admin");
sprawdz("token klienta czyta się jako klient", (await verifySessionRole(klient, S)) === "klient");

// awans przez podmianę pola w ciasteczku — podpis liczony z obu pól, więc pada
const podrobiony = klient.replace(".klient.", ".admin.");
sprawdz("podmiana roli w ciasteczku NIE awansuje na admina",
  (await verifySessionRole(podrobiony, S)) === null);

// inny sekret = inny podpis
sprawdz("token z cudzym sekretem odpada",
  (await verifySessionRole(admin, "inny-sekret")) === null);

// format sprzed podziału na role: "<ts>.<podpis>"
const { createHmac } = await import("node:crypto");
const exp = Date.now() + 3600_000;
const stary = `${exp}.${createHmac("sha256", S).update(String(exp)).digest("hex")}`;
sprawdz("stary token (sprzed ról) działa i znaczy admin",
  (await verifySessionRole(stary, S)) === "admin");

// po terminie
const wygasly = `${Date.now() - 1000}.admin.${createHmac("sha256", S).update(`${Date.now() - 1000}.admin`).digest("hex")}`;
sprawdz("token po terminie odpada", (await verifySessionRole(wygasly, S)) === null);

sprawdz("brak ciasteczka = brak roli", (await verifySessionRole(undefined, S)) === null);
sprawdz("śmieci w ciasteczku odpadają", (await verifySessionRole("abc", S)) === null);
sprawdz("nieznana rola odpada", (await verifySessionRole(`${exp}.krol.xxx`, S)) === null);

// --- CO KLIENT DOSTAJE W PROPSACH (redesign, 01.10) ---
// Sam token to połowa kontraktu. Druga połowa: kuchnia modelu (Kontrola,
// diagnostyka, typy w tle) nie może wyjść z serwera do klienta – strony są
// komponentami klienckimi, więc wszystko w propsach ląduje w źródle strony.
// Stara warstwa `okrojDlaKlienta` zniknęła razem ze starymi stronami; teraz
// kuchnia w ogóle NIE JEST LICZONA dla klienta. Czytamy źródła stron, żeby
// test nie trzymał własnej kopii reguły (ta sama zasada co przy matcherze).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const czytaj = (...czesci) => readFileSync(join(SRC, ...czesci), "utf8");

const wynikiSrc = czytaj("app", "(app)", "model", "page.tsx");
sprawdz("Wyniki: rola z ciasteczka, pełny wgląd tylko admina",
  /const admin = czyPelnyWglad\(rola\)/.test(wynikiSrc));
sprawdz("Wyniki: dane kuchni (zKuchnia) pobierane TYLKO dla admina",
  /admin \? await zKuchnia\(/.test(wynikiSrc) && (wynikiSrc.match(/zKuchnia\(/g) ?? []).length === 1);
sprawdz("Wyniki: Kontrola liczona TYLKO dla admina",
  /admin \? przygotujKontrole\(\) : undefined/.test(wynikiSrc) && (wynikiSrc.match(/przygotujKontrole\(\)/g) ?? []).length === 1);

// żadna inna strona aplikacji nie sięga po kuchnię
for (const strona of [["page.tsx"], ["druzyny", "page.tsx"], ["mecze", "page.tsx"], ["mecze", "[id]", "page.tsx"],
                      ["kupony", "page.tsx"], ["jak-to-dziala", "page.tsx"], ["zawodnik", "[id]", "page.tsx"]]) {
  const src = czytaj("app", "(app)", ...strona);
  sprawdz(`/${strona.join("/")} nie pobiera kuchni`, !/zKuchnia|przygotujKontrole|getKalibracja/.test(src));
}

// KOMPONENTY PRZEGLĄDARKI NIE IMPORTUJĄ DANYCH (wykryte przed wdrożeniem
// 01.10): jeden import funkcji daty z `_dane/przygotuj.ts` wciągał migawkę
// warsztatu (typy, wyniki, dane Kontroli – `admin.json`) do paczki JS każdej
// strony, także publicznej `/login`. Z `_dane` wolno brać w przeglądarce tylko
// typy (`import type`) i dwa moduły bez danych.
{
  const { readdirSync, statSync } = await import("node:fs");
  const pliki = [];
  const zbierz = (k) => {
    for (const n of readdirSync(k)) {
      const p = join(k, n);
      if (statSync(p).isDirectory()) zbierz(p);
      else if (/\.(ts|tsx)$/.test(n)) pliki.push(p);
    }
  };
  zbierz(SRC);
  const wolne = /_dane\/(formatCzasu|czasMigawki)$/;
  const zle = [];
  for (const p of pliki) {
    const src = readFileSync(p, "utf8");
    const kliencki = /^\s*["']use client["']/.test(src) || p.includes(join("projekt", "_ui"));
    if (!kliencki) continue;
    for (const m of src.matchAll(/import\s+(type\s+)?(\{[^}]*\}|[\w*\s,]+?)\s*from\s*["']([^"']+)["']/g)) {
      const [, tylkoTyp, nazwy, skad] = m;
      const dane = /_dane\//.test(skad) && !wolne.test(skad);
      const baza = /@\/lib\/data$|\/data\/demo\//.test(skad);
      if (!(dane || baza) || tylkoTyp) continue;
      const wartosci = nazwy.replace(/[{}]/g, "").split(",").map((x) => x.trim()).filter((x) => x && !x.startsWith("type "));
      if (wartosci.length) zle.push(`${p.slice(SRC.length + 1)} ← ${skad}: ${wartosci.join(", ")}`);
    }
  }
  sprawdz("komponenty przeglądarki nie importują danych (migawka, Kontrola, baza)", zle.length === 0);
  for (const z of zle) console.log("        " + z);
}

// typy w tle (nigdy niepokazane) nie liczą się do Wyników żadnej roli
sprawdz("Wyniki bez typów spoza publikacji",
  czytaj("app", "projekt", "_dane", "skutecznosc.ts").includes("!t.poza_publikacja"));

/* ------------------------------------------------------------------ *
 * BRAMKA DOSTĘPU — regex matchera z proxy.ts
 *
 * Matcher to jedno wyrażenie, w którym literówka po cichu otwiera CAŁĄ
 * aplikację (albo zamyka ping crona i pipeline przestaje chodzić). Nic tego
 * nie sprawdzało, a od 05.08 lista wyjątków ma trzy pozycje zamiast dwóch.
 * Czytamy regex z pliku, żeby test nie trzymał własnej kopii — to ta sama
 * zasada co przy RLS i BUNDLE_KEYS (patrz test-klucze-rls.mjs).
 * ------------------------------------------------------------------ */
const proxySrc = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "src", "proxy.ts"),
  "utf8",
);
const mMatcher = proxySrc.match(/matcher:\s*\["([^"]+)"\]/);
sprawdz("matcher da się odczytać z proxy.ts", Boolean(mMatcher));
if (mMatcher) {
  const re = new RegExp(`^${mMatcher[1].replace(/\\\\/g, "\\")}$`);
  const chronione = ["/", "/model", "/kupony", "/druzyny", "/mecze/123",
                     "/zawodnik/123", "/jak-to-dziala", "/api/szukaj", "/zaklady"];
  for (const p of chronione) {
    sprawdz(`bramka chroni ${p}`, re.test(p));
  }
  for (const p of ["/login", "/api/login", "/api/tick"]) {
    sprawdz(`bramka PRZEPUSZCZA ${p}`, !re.test(p));
  }
}

console.log(bledy === 0 ? "\nWszystko gra." : `\n${bledy} błędów.`);
process.exit(bledy === 0 ? 0 : 1);
