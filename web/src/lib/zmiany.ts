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
      "o publikacji decyduje ostrożniejsza szansa (średnia z punktowej " +
      "i dolnej granicy przedziału), znika zgoda na ujemną wartość " +
      "oczekiwaną, a rynek, który traci pieniądze, wypada z publikacji do " +
      "czasu, aż przestanie tracić.",
  },
];

/** Najświeższa zmiana zasad (albo null, gdy lista pusta). */
export const OSTATNIA_ZMIANA: ZmianaZasad | null =
  ZMIANY_ZASAD[ZMIANY_ZASAD.length - 1] ?? null;

/** Czy dzień "YYYY-MM-DD" jest już po ostatniej zmianie zasad. */
export function poZmianie(dzien: string, zmiana = OSTATNIA_ZMIANA): boolean {
  return zmiana ? dzien >= zmiana.od : true;
}
