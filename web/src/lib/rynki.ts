/**
 * Reguły domenowe rynków — jedno miejsce dla całego frontu.
 *
 * Rynki DRUŻYNOWE mają TRZY przedrostki, nie jeden.
 *
 * `match_` (suma meczowa) i `wiecej_` („kto więcej") doszły 2026-07-30.
 * Skuteczność sprawdzała wyłącznie `team_`, więc rożne CAŁYCH MECZÓW liczyły
 * się jako typy zawodnicze — stąd zgłoszenie usera 2026-08-02 („w Skuteczności
 * są jakieś typy z niedzieli, mimo że nic nie pokazywało"). Backend ma tę listę
 * od 2026-08-01 (`betting.PRZEDROSTKI_DRUZYNOWE`) i to z nią trzymamy parytet.
 *
 * Plik powstał 2026-08-04, gdy tej samej reguły potrzebowała scena Kuponów
 * (ostrzeżenie o składach ma sens tylko przy typach zawodniczych). Import
 * komponentu z komponentu ciągnąłby całą scenę Skuteczności do paczki Kuponów.
 */

export const PRZEDROSTKI_DRUZYNOWE = ["team_", "match_", "wiecej_"];

/** Czy ten kod rynku dotyczy CAŁEJ DRUŻYNY (a nie pojedynczego zawodnika). */
export function czyDruzynowy(kod: string | undefined | null): boolean {
  if (!kod) return false;
  return PRZEDROSTKI_DRUZYNOWE.some((p) => kod.startsWith(p));
}
