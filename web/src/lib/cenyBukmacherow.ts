/**
 * ⚑ CENA U DRUGIEGO BUKMACHERA NA KARCIE TYPU (06.10, właściciel: „po
 * rozwinięciu też kurs na drugim bukmacherze … jak nie da się sczytać, to się
 * nie wyświetla … dopracuj pod każdą sytuację”).
 *
 * Pipeline stempluje typ zawodniczy `kursy_bukmacherow = {Superbet, Betclic}`
 * tylko wtedy, gdy zna OBIE ceny tej samej linii, a Betclic nie liczy tej
 * statystyki inaczej (`lekkie_klucze.stempluj_ceny_bukmacherow`). Tu ostatnie
 * sito – porównanie wychodzi WYŁĄCZNIE, gdy wszystko się zgadza; w każdej
 * wątpliwej sytuacji karta nie pokazuje nic (nigdy „–” ani zgadywanej ceny):
 *
 *   • brak stempla albo któraś cena nie jest liczbą > 1      → nic
 *   • gruby kurs karty od bukmachera spoza tej pary           → nic
 *   • cena tego bukmachera w stemplu rozjeżdża się z grubym
 *     kursem karty o > 10% (dwa źródła mówią co innego)      → nic
 *   • cena drugiego bukmachera poniżej podłogi 1,19            → nic
 *   • ceny różnią się o > 50% (raczej inna statystyka/linia)  → nic
 *
 * Cena bukmachera z grubego kafelka to ZAWSZE liczba z kafelka (ta sama na
 * karcie i po rozwinięciu), drugiego – ze stempla. Kolejność stała:
 * Superbet, Betclic – układ nie skacze między kartami.
 */

/** = `PODLOGA_KURSU` z kursTeraz.ts (= `betting.MIN_ODDS`). Osobna stała, bo
 *  testy uruchamia goły Node bez rozwiązywania importów – równość pilnuje
 *  `npm run test:ceny-bukmacherow`. */
export const PODLOGA_DRUGIEJ_CENY = 1.19;

export const BUKMACHERZY = ["Superbet", "Betclic"] as const;
export type Bukmacher = (typeof BUKMACHERZY)[number];
export type CenyBukmacherow = Partial<Record<Bukmacher, number>>;

export type PozycjaCeny = { bukmacher: Bukmacher; kurs: number; lepszy: boolean };

const ROZJAZD_ZRODEL = 0.1;
const ROZJAZD_CEN = 1.5;
const ROWNE = 0.005;

const jestCena = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x) && x > 1;
const jakoBukmacher = (s: string | undefined): Bukmacher | null =>
  (BUKMACHERZY as readonly string[]).includes(s ?? "") ? (s as Bukmacher) : null;

export function porownanieCen(t: {
  kurs: number | null;
  bukmacher: string;
  kursTeraz?: number | null;
  kursTerazBukmacher?: string;
  kursyBukmacherow?: CenyBukmacherow | null;
}): PozycjaCeny[] | null {
  const ceny = t.kursyBukmacherow;
  if (!ceny || !jestCena(ceny.Superbet) || !jestCena(ceny.Betclic)) return null;
  const terazJest = jestCena(t.kursTeraz) && (t.kurs === null || Math.abs(t.kursTeraz - t.kurs) >= ROWNE);
  const gruby = terazJest ? t.kursTeraz! : t.kurs;
  const grubyBuk = jakoBukmacher(terazJest ? (t.kursTerazBukmacher ?? t.bukmacher) : t.bukmacher);
  if (!jestCena(gruby) || !grubyBuk) return null;
  const inny: Bukmacher = grubyBuk === "Superbet" ? "Betclic" : "Superbet";
  const swojaZeStempla = ceny[grubyBuk]!;
  const innaCena = ceny[inny]!;
  if (Math.abs(swojaZeStempla - gruby) / gruby > ROZJAZD_ZRODEL) return null;
  if (innaCena < PODLOGA_DRUGIEJ_CENY) return null;
  if (Math.max(gruby, innaCena) / Math.min(gruby, innaCena) > ROZJAZD_CEN) return null;
  const kurs: Record<Bukmacher, number> = { [grubyBuk]: gruby, [inny]: innaCena } as Record<Bukmacher, number>;
  const top = Math.max(gruby, innaCena);
  const rowne = Math.abs(gruby - innaCena) < ROWNE;
  return BUKMACHERZY.map((b) => ({ bukmacher: b, kurs: kurs[b], lepszy: !rowne && kurs[b] === top }));
}
