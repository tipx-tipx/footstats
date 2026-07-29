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
 *   4. token po terminie nie działa niezależnie od roli.
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

// --- CO KLIENT DOSTAJE W PROPSACH ---
// Sam token to połowa kontraktu. Druga połowa: dane dla klienta muszą wyjść
// z serwera BEZ kuchni modelu — scena jest komponentem klienckim, więc
// wszystko, co dostanie w propsach, ląduje w źródle strony, nawet jeśli nic
// tego nie renderuje. Każde nowe pole diagnostyczne trzeba tu dopisać.
const { okrojDlaKlienta } = await import("../src/lib/okrojDlaKlienta.ts");

const pelne = {
  podsumowanie: null,
  po_rynku: [{ rynek_kod: "shots", rynek: "Strzały", n: 40, trafione: 23,
               sr_p_model: 0.71, czestosc: 0.575, bias: 0.8 }],
  ostatnie: [],
  diagnostyka: { kategorie: {} },
  kupony_diag: {},
  prog_drabinek: { opublikowane: { n: 12 }, pod_progiem: { n: 0 } },
  raport_uczenia: { pewniaki: { paczki: [{ n: 40, luka: -0.13 }] } },
};
const dlaKlienta = okrojDlaKlienta(pelne);
const wSzkielecie = JSON.stringify(dlaKlienta);

for (const pole of ["diagnostyka", "kupony_diag", "prog_drabinek",
                    "raport_uczenia"]) {
  sprawdz(`klient nie dostaje pola „${pole}"`,
    dlaKlienta[pole] === undefined);
}
sprawdz("klient nie dostaje tabeli rynków", dlaKlienta.po_rynku.length === 0);
// twardy dowód, że nic z kuchni nie przecieka bocznym wejściem: liczby
// z raportu uczenia nie mogą się pojawić NIGDZIE w wysyłanym obiekcie
sprawdz("żadna liczba z raportu uczenia nie zostaje w payloadzie",
  !wSzkielecie.includes("-0.13") && !wSzkielecie.includes("0.575"));

console.log(bledy === 0 ? "\nWszystko gra." : `\n${bledy} błędów.`);
process.exit(bledy === 0 ? 0 : 1);
