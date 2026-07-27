"use client";

import { fmtKurs, fmtLinia, STRONA_LABEL } from "@/lib/format";
import type { TypRozliczony } from "@/lib/types";

/**
 * Jeden rozliczony typ w liście — wspólny wiersz dla panelu dnia
 * (TypyDnia) i pełnej listy produktu (ListaTypow). Dwa różne widoki tej
 * samej rzeczy muszą wyglądać identycznie, więc markup jest jeden.
 */

/** Typ rozliczony w tle: czemu nie było go na liście. Po ludzku, bez żargonu. */
export const POZA_LABEL: Record<string, string> = {
  kwarantanna_rynku:
    "Ten rynek był chwilowo wstrzymany, bo tracił pieniądze — typ policzył się tylko na próbę",
  kwarantanna_kategorii:
    "Ten powód typowania był chwilowo wstrzymany, bo tracił pieniądze — typ policzył się tylko na próbę",
  limit_meczu:
    "Z jednego meczu pokazujemy ograniczoną liczbę typów; ten się nie zmieścił",
  stare_dane: "Zawodnik dawno nie grał, więc typ policzył się tylko na próbę",
  za_pozno:
    "Powstał za blisko pierwszego gwizdka — nie zdążyłbyś go obstawić",
};

export function WierszTypu({ t }: { t: TypRozliczony }) {
  const wygral = t.wynik === "wygrany";
  const przegral = t.wynik === "przegrany";
  return (
    <li
      className={`flex items-center gap-3 rounded-(--radius-control) border border-hairline px-3 py-2 text-sm ${
        t.poza_publikacja ? "bg-card opacity-75" : "bg-card-soft"
      }`}
    >
      <span
        aria-hidden
        className={`h-2 w-2 shrink-0 rounded-full ${
          wygral ? "bg-data-green" : przegral ? "bg-data-red" : "bg-data-amber"
        }`}
      />
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{t.podmiot}</span>{" "}
        <span className="text-muted">
          {t.rynek.toLowerCase()} {STRONA_LABEL[t.strona]} {fmtLinia(t.linia)}
        </span>
        {t.kurs != null && (
          <span
            className="font-data ml-1.5 whitespace-nowrap text-xs font-semibold text-ink-soft"
            title="Kurs z chwili, gdy typ pojawił się na stronie — z niego liczymy bilans"
          >
            @{fmtKurs(t.kurs)}
          </span>
        )}
        <span className="text-muted"> · {t.mecz}</span>
      </span>
      {t.klasa && (
        <span
          className="hidden shrink-0 rounded-full bg-brand-wash px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand-deep sm:inline"
          title="Ocena karty w dniu publikacji"
        >
          {t.klasa}
        </span>
      )}
      {t.poza_publikacja && (
        <span
          className="hidden shrink-0 text-[10px] uppercase tracking-wide text-faint sm:inline"
          title={POZA_LABEL[t.poza_publikacja] ?? "Typ policzony tylko na próbę"}
        >
          na próbę
        </span>
      )}
      <span
        className="font-data shrink-0 text-xs text-muted"
        title="Ile zawodnik (albo drużyna) faktycznie zanotował w tym meczu"
      >
        było: {t.faktyczna != null ? t.faktyczna : "–"}
      </span>
      <span
        className={`shrink-0 text-xs font-semibold ${
          wygral
            ? "text-data-green"
            : przegral
              ? "text-data-red"
              : "text-data-amber-ink"
        }`}
      >
        {wygral ? "✓ weszło" : przegral ? "✗ nie weszło" : "zwrot"}
      </span>
    </li>
  );
}
