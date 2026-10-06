/**
 * Cena u drugiego bukmachera na karcie – `npm run test:ceny-bukmacherow`.
 *
 * Właściciel 06.10: „jak nie da się sczytać, to się nie wyświetla …
 * dopracuj pod każdą sytuację”. Każdy przypadek niżej to sytuacja, w której
 * karta ma pokazać porównanie albo NIC – nigdy „–” i nigdy zgadywaną cenę.
 */

import { PODLOGA_DRUGIEJ_CENY, porownanieCen } from "../src/lib/cenyBukmacherow.ts";
import { PODLOGA_KURSU } from "../src/lib/kursTeraz.ts";

let bledy = 0;
function sprawdz(nazwa, warunek, dodatek = "") {
  console.log(`${warunek ? "  ok  " : "BŁĄD  "}${nazwa}${dodatek ? ` — ${dodatek}` : ""}`);
  if (!warunek) bledy += 1;
}

const karta = (kw) => ({ kurs: 1.62, bukmacher: "Superbet", kursTeraz: null, kursyBukmacherow: { Superbet: 1.62, Betclic: 1.8 }, ...kw });
const opis = (c) => (c ? c.map((x) => `${x.bukmacher} ${x.kurs}${x.lepszy ? "*" : ""}`).join(" | ") : "nic");

sprawdz("podłoga ta sama co przy znikaniu typów", PODLOGA_DRUGIEJ_CENY === PODLOGA_KURSU);

// 1. zwykły przypadek: obie ceny, wyższa wyróżniona, kolejność stała
let c = porownanieCen(karta({}));
sprawdz("obie ceny → porównanie", opis(c) === "Superbet 1.62 | Betclic 1.8*", opis(c));

// 2. gruby kurs od Betclica – kolejność dalej Superbet, Betclic
c = porownanieCen(karta({ kurs: 1.8, bukmacher: "Betclic" }));
sprawdz("kafelek u Betclica → ta sama kolejność", opis(c) === "Superbet 1.62 | Betclic 1.8*", opis(c));

// 3. cena bukmachera z kafelka = liczba z kafelka (kurs teraz), nie ze stempla
c = porownanieCen(karta({ kurs: 1.62, kursTeraz: 1.85, kursTerazBukmacher: "Betclic", kursyBukmacherow: { Superbet: 1.6, Betclic: 1.8 } }));
sprawdz("kurs teraz z kafelka wygrywa ze stemplem", opis(c) === "Superbet 1.6 | Betclic 1.85*", opis(c));

// 4. równe ceny – bez wyróżnienia
c = porownanieCen(karta({ kursyBukmacherow: { Superbet: 1.62, Betclic: 1.62 } }));
sprawdz("równe ceny → nic nie wyróżnione", c && c.every((x) => !x.lepszy), opis(c));

// 5. nic do porównania
sprawdz("brak stempla → nic", porownanieCen(karta({ kursyBukmacherow: undefined })) === null);
sprawdz("null zamiast stempla → nic", porownanieCen(karta({ kursyBukmacherow: null })) === null);
sprawdz("tylko jedna cena → nic", porownanieCen(karta({ kursyBukmacherow: { Superbet: 1.62 } })) === null);
sprawdz("zero / 1,00 / tekst → nic", [0, 1, "1.5", NaN].every((x) => porownanieCen(karta({ kursyBukmacherow: { Superbet: 1.62, Betclic: x } })) === null));

// 6. źródła się kłócą: stempel mówi 1,40 u Superbetu, kafelek 1,62
sprawdz("stempel i kafelek rozjechane > 10% → nic", porownanieCen(karta({ kursyBukmacherow: { Superbet: 1.4, Betclic: 1.8 } })) === null);
sprawdz("drobny rozjazd (1,60 vs 1,62) → porównanie", porownanieCen(karta({ kursyBukmacherow: { Superbet: 1.6, Betclic: 1.8 } })) !== null);

// 7. druga cena poniżej podłogi – nie ma czego proponować
sprawdz("druga cena 1,10 → nic", porownanieCen(karta({ kurs: 1.25, kursyBukmacherow: { Superbet: 1.25, Betclic: 1.1 } })) === null);

// 8. ceny różnią się o ponad połowę – raczej inna statystyka/linia
sprawdz("1,40 vs 2,30 → nic", porownanieCen(karta({ kurs: 1.4, kursyBukmacherow: { Superbet: 1.4, Betclic: 2.3 } })) === null);
sprawdz("1,23 vs 1,50 (Tate Johnson 06.10) → porównanie", porownanieCen(karta({ kurs: 1.5, bukmacher: "Betclic", kursyBukmacherow: { Superbet: 1.23, Betclic: 1.5 } })) !== null);

// 9. bukmacher spoza pary / brak kursu na kafelku
sprawdz("kafelek od innego bukmachera → nic", porownanieCen(karta({ bukmacher: "STS" })) === null);
sprawdz("kafelek bez kursu → nic", porownanieCen(karta({ kurs: null })) === null);

// 10. kurs teraz = kurs publikacji (różnica < 0,005) – liczy się jak bez ruchu
c = porownanieCen(karta({ kursTeraz: 1.622, kursTerazBukmacher: "Betclic" }));
sprawdz("kurs teraz bez realnej zmiany nie przestawia bukmachera", opis(c) === "Superbet 1.62 | Betclic 1.8*", opis(c));

console.log(bledy ? `\n${bledy} błędów` : "\nWszystko gra.");
process.exit(bledy ? 1 : 0);
