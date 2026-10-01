"use client";

import { createContext, useContext } from "react";

import { TERAZ_MIGAWKI } from "../_dane/czasMigawki";

/*
 * „Teraz” dla komponentów (etap 7). Warsztat: chwila migawki (domyślnie).
 * Aplikacja: czas renderu z serwera, podany przez <CzasProvider> – serwer
 * i przeglądarka widzą tę samą wartość, więc nie ma rozjazdu przy hydracji.
 */

const CzasContext = createContext<number>(TERAZ_MIGAWKI);

export function CzasProvider({ teraz, children }: { teraz: number; children: React.ReactNode }) {
  return <CzasContext.Provider value={teraz}>{children}</CzasContext.Provider>;
}

/** „teraz” w sekundach */
export const useTeraz = () => useContext(CzasContext);

const DZIEN_PL = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" });
export const kluczDnia = (ts: number) => DZIEN_PL.format(new Date(ts * 1000));

/** „dziś” po polsku (YYYY-MM-DD) */
export const useDzis = () => kluczDnia(useTeraz());
