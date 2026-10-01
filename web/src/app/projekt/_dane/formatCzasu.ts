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
