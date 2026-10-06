/**
 * ⚑ KURS, KTÓREGO JUŻ NIE MA (06.10, właściciel: „przy spadku do 1,04 może
 * znikać, bo bez sensu, żeby taki kurs stał”).
 *
 * Pipeline stempluje typ pokazany wcześniej ceną BIEŻĄCĄ (`kurs_teraz`), gdy
 * ta różni się od ceny z publikacji. Tu dwie rzeczy:
 *   1. typ, którego kurs teraz spadł poniżej podłogi, schodzi z list typów
 *      (Zawodnicy, Drużyny, mecz, wyszukiwarka, wyróżnione karty). Z WYNIKÓW
 *      nie schodzi – te czytają `typy_wyniki` z ceną z publikacji, więc się
 *      rozliczy i policzy w Skuteczności jak każdy pokazany typ;
 *   2. pula kuponów liczy po cenie teraz, a leg poniżej podłogi z niej
 *      wypada – inaczej „Kupon dnia” obiecywał kurs, którego nie ma. Pula
 *      gubi stempel przy zapisie, więc cenę bierzemy z typu o tym samym
 *      kluczu (mecz, podmiot, rynek, linia, strona).
 *
 * BEZPIECZNIK: rynek, który się ruszył, zdejmuje pojedyncze typy (06.10:
 * 1 z 58). Gdy poniżej podłogi ląduje naraz duża część listy, to raczej
 * błąd danych (np. cena innej linii) niż rynek – wtedy nic nie chowamy
 * i głośno logujemy, zamiast wyczyścić stronę.
 */

/** Ta sama podłoga co w pipeline (`betting.MIN_ODDS`): poniżej gra się nie opłaca. */
export const PODLOGA_KURSU = 1.19;

const BEZPIECZNIK_UDZIAL = 0.25;
const BEZPIECZNIK_MIN = 3;

type ZCena = { kurs: number | null; kurs_teraz?: number | null };

export const kursZjechal = (t: ZCena): boolean =>
  typeof t.kurs_teraz === "number" && t.kurs_teraz > 0 && t.kurs_teraz < PODLOGA_KURSU;

/** Czy wolno chować – false, gdy zadziałał bezpiecznik. */
export function wolnoChowac(typy: ZCena[]): boolean {
  const zjechane = typy.filter(kursZjechal).length;
  if (zjechane > Math.max(BEZPIECZNIK_MIN, typy.length * BEZPIECZNIK_UDZIAL)) {
    console.error(
      `[kurs teraz] ${zjechane} z ${typy.length} typów poniżej ${PODLOGA_KURSU} – ` +
        "to wygląda na błąd danych, nie na rynek; nic nie chowam",
    );
    return false;
  }
  return true;
}

/** Lista typów bez tych, których kursu już nie ma. */
export function bezZjechanych<T extends ZCena>(typy: T[]): T[] {
  return wolnoChowac(typy) ? typy.filter((t) => !kursZjechal(t)) : typy;
}

type Klucz = { mecz_id: number; podmiot: string; rynek_kod: string; linia: number; strona: string };
const klucz = (x: Klucz) => `${x.mecz_id}|${x.podmiot}|${x.rynek_kod}|${x.linia}|${x.strona}`;

/** Pula kuponów po cenie teraz; legi poniżej podłogi wypadają. */
export function pulaPoKursieTeraz<L extends Klucz & { kurs: number; bukmacher: string }>(
  pula: L[],
  typy: (Klucz & ZCena & { kurs_teraz_bukmacher?: string })[],
): L[] {
  if (!wolnoChowac(typy)) return pula;
  const teraz = new Map<string, { kurs: number; bukmacher?: string }>();
  for (const t of typy) {
    if (typeof t.kurs_teraz === "number" && t.kurs_teraz > 0) teraz.set(klucz(t), { kurs: t.kurs_teraz, bukmacher: t.kurs_teraz_bukmacher });
  }
  if (!teraz.size) return pula;
  const out: L[] = [];
  for (const l of pula) {
    const t = teraz.get(klucz(l));
    if (!t) {
      out.push(l);
    } else if (t.kurs >= PODLOGA_KURSU) {
      out.push({ ...l, kurs: t.kurs, bukmacher: t.bukmacher ?? l.bukmacher });
    }
  }
  return out;
}
