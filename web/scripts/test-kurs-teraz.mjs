/**
 * Kurs, którego już nie ma — `npm run test:kurs-teraz`.
 *
 * POWÓD (właściciel 06.10): McGinn, faule wywalczone powyżej 1,5, wisiał
 * w „Najmocniejszych na dziś” z kursem 1,35, choć u bukmachera było już 1,04.
 * Typ poniżej podłogi (1,19) schodzi z list i z puli kuponów, a w Wynikach
 * zostaje z ceną z publikacji (te czytają `typy_wyniki`, nie listę).
 *
 * Najważniejszy jest BEZPIECZNIK: błąd danych nie może wyczyścić strony.
 */

import { bezZjechanych, PODLOGA_KURSU, pulaPoKursieTeraz } from "../src/lib/kursTeraz.ts";

let bledy = 0;
function sprawdz(nazwa, warunek, dodatek = "") {
  console.log(`${warunek ? "  ok  " : "BŁĄD  "}${nazwa}${dodatek ? ` — ${dodatek}` : ""}`);
  if (!warunek) bledy += 1;
}

const typ = (id, kurs, kurs_teraz, bukmacher_teraz) => ({
  id, mecz_id: 1, podmiot: `Z${id}`, rynek_kod: "fouls_won", linia: 1.5, strona: "powyzej",
  kurs, bukmacher: "Superbet",
  ...(kurs_teraz !== undefined ? { kurs_teraz } : {}),
  ...(bukmacher_teraz ? { kurs_teraz_bukmacher: bukmacher_teraz } : {}),
});

// stan z produkcji 06.10: 58 typów, jeden zjechał do 1,04
const lista = [typ(0, 1.35, 1.04), typ(1, 1.62, 1.8), typ(2, 1.21, 1.19), ...Array.from({ length: 55 }, (_, i) => typ(i + 3, 1.5))];
const po = bezZjechanych(lista);
sprawdz("typ przy 1,04 schodzi z listy", !po.some((t) => t.id === 0));
sprawdz("typ, któremu kurs wzrósł, zostaje", po.some((t) => t.id === 1));
sprawdz(`kurs dokładnie na podłodze (${PODLOGA_KURSU}) zostaje`, po.some((t) => t.id === 2));
sprawdz("reszta listy nietknięta", po.length === 57, `${po.length} z 58`);

// typ bez stempla albo ze śmieciem w stemplu nie znika
const dziwne = [typ(1, 1.5, null), typ(2, 1.5, 0), typ(3, 1.5)];
sprawdz("brak / zero w kurs_teraz nie chowa typu", bezZjechanych(dziwne).length === 3);

// BEZPIECZNIK: połowa listy „poniżej podłogi” = błąd danych, nic nie chowamy
const zepsute = Array.from({ length: 20 }, (_, i) => typ(i, 1.5, i < 10 ? 1.05 : undefined));
const blad = console.error;
let krzyk = "";
console.error = (m) => { krzyk = String(m); };
const poZepsutych = bezZjechanych(zepsute);
const pulaZepsuta = pulaPoKursieTeraz(zepsute.map((t) => ({ ...t })), zepsute);
console.error = blad;
sprawdz("bezpiecznik: przy masowym spadku nic nie znika", poZepsutych.length === 20);
sprawdz("bezpiecznik: pula też nietknięta", pulaZepsuta.length === 20 && pulaZepsuta.every((l) => l.kurs === 1.5));
sprawdz("bezpiecznik krzyczy w logu", krzyk.includes("nic nie chowam"));

// małe listy: 1 zjechany z 3 to jeszcze rynek, nie błąd
sprawdz("mała lista: pojedynczy spadek działa", bezZjechanych([typ(0, 1.35, 1.04), typ(1, 1.5), typ(2, 1.5)]).length === 2);

// pula kuponów: leg bez stempla, z kursem po typie o tym samym kluczu
const pula = [
  { ...typ(0, 1.35), id: 100 },                  // McGinn – w puli bez stempla
  { ...typ(1, 1.62), id: 101 },                  // Cerv – 1,62 → 1,80 u Betclica
  { ...typ(7, 1.5), id: 107 },                   // świeży leg, cena bieżąca
];
const typyPuli = [typ(0, 1.35, 1.04), typ(1, 1.62, 1.8, "Betclic"), ...Array.from({ length: 10 }, (_, i) => typ(i + 20, 1.5))];
const poPuli = pulaPoKursieTeraz(pula, typyPuli);
sprawdz("pula: leg przy 1,04 wypada (nie trafi do Kuponu dnia)", !poPuli.some((l) => l.id === 100));
const cerv = poPuli.find((l) => l.id === 101);
sprawdz("pula: leg liczy się po kursie teraz", cerv?.kurs === 1.8, String(cerv?.kurs));
sprawdz("pula: i u bukmachera, który go daje", cerv?.bukmacher === "Betclic", String(cerv?.bukmacher));
sprawdz("pula: leg bez typu-pary zostaje bez zmian", poPuli.find((l) => l.id === 107)?.kurs === 1.5);
sprawdz("pula: wejście nie jest modyfikowane", pula[1].kurs === 1.62);

console.log(bledy ? `\n${bledy} błędów` : "\nWszystko gra.");
process.exit(bledy ? 1 : 0);
