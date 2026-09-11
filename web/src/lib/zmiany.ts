/**
 * Daty, po których zmieniły się ZASADY SELEKCJI typów.
 *
 * Bez nich kalendarz i liczniki mieszają dwa różne modele w jedną średnią:
 * dzień sprzed zaostrzenia bram opowiada o kodzie, który już nie działa,
 * a użytkownik czyta to jako „bieżącą formę". Znacznik nie chowa starych
 * dni (nic nie znika) – tylko mówi wprost, od kiedy liczby dotyczą tego,
 * co jest w produkcji dzisiaj.
 */
export interface ZmianaZasad {
  /** "YYYY-MM-DD" – pierwszy dzień, którego mecze objęły nowe zasady */
  od: string;
  etykieta: string;
  opis: string;
}

export const ZMIANY_ZASAD: ZmianaZasad[] = [
  {
    od: "2026-07-26",
    etykieta: "nowe bramy",
    opis:
      "o publikacji decyduje ostrożniejsza szansa – średnia z punktowej " +
      "i dolnej granicy przedziału.",
  },
  {
    od: "2026-08-14",
    etykieta: "jedna lista dziennie",
    opis:
      "listę dnia ogłaszamy raz, o 6:00, i nie zmieniamy jej do wieczora. " +
      "Rynki, które tracą, przestały wypadać z publikacji – zamiast tego " +
      "mają ostrzeżenie na karcie i nie wchodzą do kuponów.",
  },
  {
    od: "2026-08-24",
    etykieta: "liczy się trafność",
    opis:
      "zdjęliśmy bramy, które wycinały tanie typy i te, co do których model " +
      "był ostrożny – przy kursach do 1,80 decyduje sama szansa. Model " +
      "patrzy też na to, ile razy dane zdarzenie padało u rywala.",
  },
];

/*
 * ⚑ DLACZEGO TE TRZY DATY, A NIE JEDNA (2026-09-11)
 *
 * Do dziś stał tu jeden wpis z 26.07, a jego opis obiecywał dwie rzeczy,
 * których produkt już nie robi: „znika zgoda na ujemną wartość oczekiwaną"
 * (brama ZDJĘTA 24.08 – karała typy za to, że model był co do nich ostrożny)
 * i „rynek, który traci pieniądze, wypada z publikacji" (kwarantanna
 * przestała zdejmować typy z listy 14.08, decyzja „nic nie blokujemy").
 *
 * Zdanie na Skuteczności czytało się więc jako obietnica blokady, której nie
 * ma – a obok stała lista wstrzymanych rynków, z których typy normalnie
 * wchodziły na listę dnia. To najgorszy rodzaj nieprawdy w tym produkcie:
 * sprawdzalna w trzy sekundy i dotycząca tego, co klient ma przed sobą.
 */

/** Najświeższa zmiana zasad (albo null, gdy lista pusta). */
export const OSTATNIA_ZMIANA: ZmianaZasad | null =
  ZMIANY_ZASAD[ZMIANY_ZASAD.length - 1] ?? null;

/** Czy dzień "YYYY-MM-DD" jest już po ostatniej zmianie zasad. */
export function poZmianie(dzien: string, zmiana = OSTATNIA_ZMIANA): boolean {
  return zmiana ? dzien >= zmiana.od : true;
}
