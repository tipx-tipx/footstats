"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Segmented } from "./Segmented";

/**
 * Owijka aktywnego kuponu z akcjami: pomiń (z powodem), przywróć,
 * przebuduj po składach.
 *
 * Pominięcie zapisuje klucz kuponu w Supabase (API route), który OD RAZU
 * odpala przeliczenie pipeline'u (workflow_dispatch) — slot się zwalnia i
 * powstaje nowy kupon, a pominięty dalej rozlicza się w tle (model uczy się
 * też z niezagranych). Kartę chowamy od razu (localStorage), bo snapshot
 * danych odświeża się co ~60 s. Przywrócenie usuwa klucz — pipeline cofa
 * pominięcie, o ile slot nie został już zajęty nowszym kuponem.
 */

const POWODY = ["nie zagrałem", "słaby zestaw", "za niski kurs"] as const;

export async function akcjaKuponu(body: Record<string, unknown>): Promise<void> {
  const r = await fetch("/api/kupon-pomin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(String(r.status));
}

export function PominKupon({
  klucz,
  pokazPrzebuduj,
  children,
}: {
  klucz?: string;
  /** true dla kuponów dziennych — opcja "przebuduj po składach" */
  pokazPrzebuduj?: boolean;
  children: ReactNode;
}) {
  const [stan, setStan] = useState<
    "aktywny" | "wybor" | "wysylam" | "pominiety" | "blad"
  >("aktywny");
  const [przebudowa, setPrzebudowa] = useState(false);

  useEffect(() => {
    // sprzątanie: wpisy starsze niż 14 dni (pipeline dawno zwolnił slot);
    // wartości sprzed wersji z timestampem ("1") też wypadają
    const teraz = Date.now();
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (!k?.startsWith("kupon-pominiety:") && !k?.startsWith("kupon-przebudowa:"))
        continue;
      const ts = Number(localStorage.getItem(k));
      if (!ts || teraz - ts > 14 * 86_400_000) localStorage.removeItem(k);
    }
    if (klucz && localStorage.getItem(`kupon-pominiety:${klucz}`)) {
      setStan("pominiety");
    }
    if (klucz && localStorage.getItem(`kupon-przebudowa:${klucz}`)) {
      setPrzebudowa(true);
    }
  }, [klucz]);

  if (!klucz) return <>{children}</>;

  const pomin = async (powod: string) => {
    setStan("wysylam");
    try {
      await akcjaKuponu({ klucz, powod });
      localStorage.setItem(`kupon-pominiety:${klucz}`, String(Date.now()));
      setStan("pominiety");
    } catch {
      setStan("blad");
    }
  };

  const przywroc = async () => {
    setStan("wysylam");
    try {
      await akcjaKuponu({ klucz, akcja: "przywroc" });
      localStorage.removeItem(`kupon-pominiety:${klucz}`);
      setStan("aktywny");
    } catch {
      setStan("pominiety");
    }
  };

  const zaplanujPrzebudowe = async () => {
    try {
      await akcjaKuponu({ klucz, akcja: "przebuduj" });
      localStorage.setItem(`kupon-przebudowa:${klucz}`, String(Date.now()));
      setPrzebudowa(true);
    } catch {
      /* przycisk zostaje — można spróbować ponownie */
    }
  };

  if (stan === "pominiety") {
    return (
      <div className="rounded-(--radius-card) border border-dashed border-hairline bg-card-soft/60 px-6 py-8 text-center">
        <p className="text-sm font-medium text-ink">Kupon pominięty</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted">
          Model i tak rozliczy go w tle (do nauki). Zamówiliśmy przeliczenie.
          Nowy kupon w tym przedziale pojawi się w kilka minut, o ile pula ma
          inny sensowny zestaw dla tych widełek kursu.
        </p>
        <button
          onClick={przywroc}
          className="mt-3 rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-ink-soft shadow-(--shadow-card) transition-colors hover:bg-card-soft"
        >
          Cofnij i przywróć kupon
        </button>
      </div>
    );
  }

  return (
    <div>
      {children}
      {przebudowa && (
        <p className="mt-1.5 rounded-(--radius-control) bg-data-amber-wash px-2.5 py-1 text-[11px] text-data-amber-ink">
          ↻ zaplanowano przebudowę: gdy składy wszystkich meczów zostaną
          potwierdzone, model złoży ten kupon od nowa na pewnych XI
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        {pokazPrzebuduj && !przebudowa && stan !== "wybor" && (
          <button
            onClick={zaplanujPrzebudowe}
            className="inline-flex items-center gap-1.5 rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted shadow-(--shadow-card) transition-colors hover:border-data-amber/50 hover:text-data-amber-ink"
            title="Kupon zostanie pominięty i złożony od nowa dopiero, gdy składy WSZYSTKICH jego meczów będą potwierdzone. Mniej zwrotów i anulowań"
          >
            ↻ przebuduj po składach
          </button>
        )}
        {stan === "wybor" ? (
          <span className="flex flex-wrap items-center gap-1.5 rounded-(--radius-control) border border-hairline bg-card px-2 py-1.5 shadow-(--shadow-card)">
            <span className="pl-1 text-xs text-faint">dlaczego pomijasz?</span>
            {POWODY.map((p) => (
              <button
                key={p}
                onClick={() => pomin(p)}
                className="rounded-md bg-card-soft px-2.5 py-1 text-xs font-medium text-ink-soft transition-colors hover:bg-data-red-wash hover:text-data-red-ink"
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setStan("aktywny")}
              className="px-1.5 text-xs text-faint transition-colors hover:text-muted"
              aria-label="anuluj pomijanie"
            >
              ✕
            </button>
          </span>
        ) : (
          <button
            onClick={() => setStan("wybor")}
            disabled={stan === "wysylam"}
            className="inline-flex items-center gap-1.5 rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted shadow-(--shadow-card) transition-colors hover:border-data-red/40 hover:text-data-red-ink disabled:border-hairline disabled:bg-card-soft disabled:text-faint disabled:shadow-none"
            title="Kupon zniknie z aktywnych i zwolni miejsce na nowy; w tle zostanie rozliczony, żeby model się uczył"
          >
            {stan === "blad"
              ? "nie udało się, spróbuj ponownie"
              : stan === "wysylam"
                ? "pomijam…"
                : "✕ Nie zagrałem – pomiń"}
          </button>
        )}
      </div>
    </div>
  );
}

/** Przycisk "zastosuj zamianę" przy alternatywie rentgena. */
export function ZastosujZamiane({ klucz }: { klucz?: string }) {
  const [st, setSt] = useState<"idle" | "sending" | "done" | "err">("idle");
  if (!klucz) return null;
  if (st === "done") {
    return (
      <p className="mt-2 text-xs font-medium text-brand-deep">
        ✓ zamiana zaplanowana. Nowy kupon z wymienionym typem pojawi się przy
        najbliższym przeliczeniu (zwykle w kilka minut)
      </p>
    );
  }
  return (
    <button
      onClick={async () => {
        setSt("sending");
        try {
          await akcjaKuponu({ klucz, akcja: "wymien" });
          setSt("done");
        } catch {
          setSt("err");
        }
      }}
      disabled={st === "sending"}
      className="mt-2 rounded-(--radius-control) border border-brand/40 bg-brand-wash px-2.5 py-1 text-xs font-semibold text-brand-deep transition-colors hover:bg-brand-wash/70 disabled:border-hairline disabled:bg-card-soft disabled:text-faint"
    >
      {st === "err"
        ? "nie udało się, spróbuj ponownie"
        : st === "sending"
          ? "stosuję…"
          : "⇄ Zastosuj zamianę (nowy kupon w tym slocie)"}
    </button>
  );
}

const PROFILE_OPIS: Record<string, string> = {
  bezpieczny: "same kotwice: tylko typy z szansą 58% i wyżej",
  zbalansowany: "domyślny balans pewności i kursu",
  agresywny: "więcej matchupów i wyższych linii, kupon z rodzynkami",
};

/** Charakter buildera kuponów — ustawienie globalne (nowe kupony). */
export function ProfilKuponow() {
  const [profil, setProfil] = useState<string | null>(null);
  const [zapis, setZapis] = useState(false);
  useEffect(() => {
    setProfil(localStorage.getItem("kupony-profil") || "zbalansowany");
  }, []);
  const ustaw = async (p: string) => {
    setZapis(true);
    try {
      await akcjaKuponu({ akcja: "profil", profil: p });
      localStorage.setItem("kupony-profil", p);
      setProfil(p);
    } catch {
      /* zostaje poprzedni */
    }
    setZapis(false);
  };
  return (
    <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
        charakter
      </span>
      <Segmented
        id="profil-kuponow"
        opcje={(["bezpieczny", "zbalansowany", "agresywny"] as const).map(
          (p) => ({ kod: p, label: p }),
        )}
        wartosc={(profil ?? "zbalansowany") as "bezpieczny" | "zbalansowany" | "agresywny"}
        onChange={ustaw}
        disabled={zapis}
      />
      <span
        className="text-[11px] text-faint"
        title="Dotyczy nowych kuponów. Już opublikowane są zamrożone i się nie zmieniają"
      >
        {PROFILE_OPIS[profil ?? "zbalansowany"]}
      </span>
    </div>
  );
}
