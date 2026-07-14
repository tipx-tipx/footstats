"use client";

import { useSyncExternalStore } from "react";

/**
 * Przełącznik jasny/ciemny. Źródłem prawdy jest data-theme na <html>
 * (ustawiany bez mignięcia przez skrypt inline w layout.tsx); komponent
 * subskrybuje ten atrybut przez MutationObserver, więc każda instancja
 * przełącznika jest zawsze zsynchronizowana. Wybór usera trafia do
 * localStorage — brak zapisu = podążaj za motywem systemu.
 */
const KLUCZ_MOTYWU = "footstats-motyw";

function subskrybujMotyw(powiadom: () => void): () => void {
  const obs = new MutationObserver(powiadom);
  obs.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => obs.disconnect();
}

function czyCiemny(): boolean {
  return document.documentElement.dataset.theme === "dark";
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  // na serwerze zakładamy jasny — po hydracji dociąga się prawdziwa wartość
  const ciemny = useSyncExternalStore(subskrybujMotyw, czyCiemny, () => false);

  const przelacz = () => {
    const naCiemny = !czyCiemny();
    document.documentElement.dataset.theme = naCiemny ? "dark" : "light";
    try {
      localStorage.setItem(KLUCZ_MOTYWU, naCiemny ? "dark" : "light");
    } catch {
      // tryb prywatny / zablokowany storage — motyw i tak działa do końca sesji
    }
  };

  const opis = ciemny ? "Przełącz na jasny motyw" : "Przełącz na ciemny motyw";
  return (
    <button
      onClick={przelacz}
      title={opis}
      aria-label={opis}
      className={`shrink-0 rounded-lg p-2.5 text-faint transition-colors hover:bg-paper hover:text-ink ${className}`}
    >
      {ciemny ? (
        // słońce — wracamy do jasnego
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        // księżyc — przejście na ciemny
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path
            d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  );
}
