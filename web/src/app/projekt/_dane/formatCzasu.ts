/**
 * Formatowanie czasu (Europe/Warsaw) – osobny moduł BEZ danych.
 *
 * ⚑ Komponenty przeglądarki mogą importować TYLKO stąd, nie z `przygotuj.ts`:
 * tamten moduł ładuje migawkę warsztatu (`zrodlo.ts`: typy, wyniki, dane
 * Kontroli), a jeden import funkcji wciągał ją całą do paczki JS każdej strony
 * – także publicznej `/login` (wykryte przed wdrożeniem 01.10, 1,5 MB).
 */

export const DZIEN_FMT = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" });
export const GODZ_FMT = new Intl.DateTimeFormat("pl-PL", {
  timeZone: "Europe/Warsaw",
  hour: "2-digit",
  minute: "2-digit",
});
// skróty jak w kalendarzu ściennym – Intl daje „niedz.”, „czw.”, a to czyta się gorzej
export const TYDZ = ["Nd", "Pn", "Wt", "Śr", "Czw", "Pt", "Sob"];

export const dzienTs = (ts: number) => DZIEN_FMT.format(new Date(ts * 1000));

/** „Dziś”, „Jutro”, dalej „Sob 3.10” – klucze RRRR-MM-DD w czasie polskim */
export function etykietaDnia(klucz: string, dzis: string): string {
  const d = new Date(`${klucz}T12:00:00Z`);
  const roznica = Math.round((d.getTime() - new Date(`${dzis}T12:00:00Z`).getTime()) / 86400000);
  if (roznica === 0) return "Dziś";
  if (roznica === 1) return "Jutro";
  return `${TYDZ[d.getUTCDay()]} ${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}
