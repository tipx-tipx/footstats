/**
 * Oznaczenia typów na karcie (pipeline `OZNACZENIA_TYPU`, 18.10) – kody i krótkie
 * teksty (właściciel: „krótsze teksty”). Osobny moduł bez danych: importuje go
 * komponent przeglądarki (karta), a `_dane` są tylko po stronie serwera.
 */
export const OZNACZENIA_TYPU = {
  perla: { tekst: "Perełka", opis: "Wyższy kurs, linia weszła w 8 z 10 ostatnich, a nasza szansa jest co najmniej taka jak w kursie" },
  nad_kursem: { tekst: "Nad kursem", opis: "Liczymy szansę wyraźnie wyżej niż bukmacher (o 15 pkt proc. i więcej)" },
  seria: { tekst: "Seria 9/10", opis: "Linia weszła w co najmniej 9 z 10 ostatnich meczów" },
} as const;

export type OznaczenieTypu = keyof typeof OZNACZENIA_TYPU;

export const czyOznaczenie = (k: string): k is OznaczenieTypu => k in OZNACZENIA_TYPU;
