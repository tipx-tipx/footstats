"use client";

import { useSyncExternalStore } from "react";

/*
 * Motyw aplikacji – osobny lekki moduł (01.10). Logowanie, 404 i błąd biorą
 * przełącznik stąd, a nie z `SzkieletAplikacji` – tamten ciągnie wyszukiwarkę,
 * menu i pasek połączenia do paczki JS każdej strony systemowej.
 */

/* html[data-theme] jest źródłem prawdy (skrypt w layout.tsx) */

const KLUCZ_MOTYWU = "footstats-motyw";
const subskrybuj = (powiadom: () => void) => {
  const obs = new MutationObserver(powiadom);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
};
const czyCiemny = () => document.documentElement.dataset.theme !== "light";

export function useCiemny() {
  // serwer nie zna motywu – zakładamy ciemny (domyślny), przeglądarka poprawia po hydracji
  return useSyncExternalStore(subskrybuj, czyCiemny, () => true);
}

export function przelaczMotyw() {
  const naCiemny = !czyCiemny();
  document.documentElement.dataset.theme = naCiemny ? "dark" : "light";
  try {
    localStorage.setItem(KLUCZ_MOTYWU, naCiemny ? "dark" : "light");
  } catch {
    /* tryb prywatny – motyw działa do końca wizyty */
  }
}
