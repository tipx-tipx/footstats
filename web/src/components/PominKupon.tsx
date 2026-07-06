"use client";

import { useEffect, useState, type ReactNode } from "react";

/**
 * Owijka aktywnego kuponu z przyciskiem "nie zagrałem — pomiń".
 *
 * Pominięcie zapisuje klucz kuponu w Supabase (API route) — pipeline
 * w następnym cyklu zwalnia slot i buduje nowy kupon, a pominięty dalej
 * rozlicza się w tle (model uczy się też z niezagranych). Kartę chowamy
 * od razu (localStorage), bo snapshot danych odświeża się do ~15 minut.
 */
export function PominKupon({
  klucz,
  children,
}: {
  klucz?: string;
  children: ReactNode;
}) {
  const [stan, setStan] = useState<
    "aktywny" | "wysylam" | "pominiety" | "blad"
  >("aktywny");

  useEffect(() => {
    // sprzątanie: wpisy starsze niż 14 dni (pipeline dawno zwolnił slot);
    // wartości sprzed wersji z timestampem ("1") też wypadają
    const teraz = Date.now();
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (!k?.startsWith("kupon-pominiety:")) continue;
      const ts = Number(localStorage.getItem(k));
      if (!ts || teraz - ts > 14 * 86_400_000) localStorage.removeItem(k);
    }
    if (klucz && localStorage.getItem(`kupon-pominiety:${klucz}`)) {
      setStan("pominiety");
    }
  }, [klucz]);

  if (!klucz) return <>{children}</>;

  const pomin = async () => {
    // nieodwracalne (globalny stan pipeline'u) — jeden klik to za mało
    if (
      !window.confirm(
        "Pominąć ten kupon? Zniknie z aktywnych, a w jego miejsce po następnym cyklu powstanie nowy.",
      )
    ) {
      return;
    }
    setStan("wysylam");
    try {
      const r = await fetch("/api/kupon-pomin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ klucz }),
      });
      if (!r.ok) throw new Error(String(r.status));
      localStorage.setItem(`kupon-pominiety:${klucz}`, String(Date.now()));
      setStan("pominiety");
    } catch {
      setStan("blad");
    }
  };

  if (stan === "pominiety") {
    return (
      <div className="rounded-2xl border border-dashed border-hairline bg-paper/60 px-6 py-8 text-center">
        <p className="text-sm font-medium text-ink">Kupon pominięty</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted">
          Model i tak rozliczy go w tle (do nauki), a nowy kupon w tym
          przedziale pojawi się po następnym cyklu — zwykle do ~30 minut.
        </p>
      </div>
    );
  }

  return (
    <div>
      {children}
      <div className="mt-1.5 flex justify-end">
        <button
          onClick={pomin}
          disabled={stan === "wysylam"}
          className="rounded px-1 text-xs text-faint underline-offset-2 transition-colors hover:text-muted hover:underline disabled:opacity-50"
          title="Kupon zniknie z aktywnych i zwolni miejsce na nowy; w tle zostanie rozliczony, żeby model się uczył"
        >
          {stan === "blad"
            ? "nie udało się — spróbuj ponownie"
            : stan === "wysylam"
              ? "pomijam…"
              : "Nie zagrałem — pomiń i wygeneruj nowy"}
        </button>
      </div>
    </div>
  );
}
