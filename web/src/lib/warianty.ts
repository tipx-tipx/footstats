import type { ValueBet } from "./types";

/**
 * WARIANTY LINII: kilka poziomów tego samego typu na jednej karcie.
 *
 * Zgłoszenie usera (2026-08-01): „gdy na jeden mecz sugerujesz np. na tę samą
 * drużynę 4,5 / 5,5 / 6,5, może na jednej karcie to lepiej zrobić niż trzy
 * osobne". I tak jest – trzy karty pod rząd z tą samą drużyną i tym samym
 * rynkiem wyglądały jak trzy różne pomysły, a to jest JEDEN pomysł wyceniony
 * na trzech poprzeczkach. Dokładnie to, co karta drabinki pokazuje od zawsze.
 *
 * Grupujemy po (mecz, podmiot, rynek, STRONA). Strona jest w kluczu celowo:
 * „powyżej 4,5" i „poniżej 4,5" to dwa przeciwne zakłady, nie dwa szczeble
 * jednej drabinki.
 */

/** „1 linia" / „2 linie" / „5 linii" – polska odmiana po liczbie. */
export function odmienLinie(n: number): string {
  if (n === 1) return "1 linia";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "linie" : "linii"}`;
}

export const kluczWariantu = (b: ValueBet) =>
  `${b.mecz_id}:${b.podmiot_id}:${b.rynek_kod}:${b.strona}`;

export interface GrupaWariantow {
  /** typ, który reprezentuje grupę – pierwszy w kolejności wejściowej,
   *  czyli najwyżej oceniony przez aktualne sortowanie listy */
  glowny: ValueBet;
  /** wszystkie linie grupy (z głównym włącznie), po linii rosnąco */
  warianty: ValueBet[];
}

/**
 * Zwraca grupy w KOLEJNOŚCI WEJŚCIOWEJ: grupa staje tam, gdzie stał jej
 * najlepszy typ. Dzięki temu scalanie nie miesza w rankingu ani w żadnym
 * sortowaniu wybranym przez użytkownika.
 */
export function grupujWarianty(bets: ValueBet[]): GrupaWariantow[] {
  const wg = new Map<string, ValueBet[]>();
  const kolejnosc: string[] = [];
  for (const b of bets) {
    const k = kluczWariantu(b);
    const lista = wg.get(k);
    if (lista) lista.push(b);
    else {
      wg.set(k, [b]);
      kolejnosc.push(k);
    }
  }
  return kolejnosc.map((k) => {
    const lista = wg.get(k)!;
    return {
      glowny: lista[0],
      warianty: [...lista].sort((a, b) => a.linia - b.linia),
    };
  });
}
