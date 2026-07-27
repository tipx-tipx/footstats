"use client";

import { fmtKurs, fmtLinia, STRONA_LABEL } from "@/lib/format";
import type { TypRozliczony } from "@/lib/types";

/**
 * Jeden rozliczony typ — WIERSZ TABELI, nie karta.
 *
 * Karta jest dobra dla trzech rzeczy naraz. Przy kilkunastu typach dziennie
 * (a rozliczonych jest ponad trzysta) oko musi jechać w dół KOLUMNY, nie
 * czytać każdego wiersza od nowa — stąd stałe kolumny i wyrównanie liczb.
 *
 * Kolumny są celowo nierówne wagą: nazwisko czyta się pierwsze, rynek jest
 * przygaszony, a wynik trzyma prawą krawędź, żeby dało się przelecieć samą
 * kolumnę wyników bez czytania reszty.
 */

/** Typ rozliczony w tle: czemu nie było go na liście. Po ludzku, bez żargonu. */
export const POZA_LABEL: Record<string, string> = {
  kwarantanna_rynku:
    "Ten rynek był chwilowo wstrzymany, bo tracił pieniądze — typ policzył się tylko na próbę",
  kwarantanna_kategorii:
    "Ten powód typowania był chwilowo wstrzymany, bo tracił pieniądze — typ policzył się tylko na próbę",
  rozjazd_z_rynkiem:
    "Nasza szansa za mocno rozjeżdżała się z kursem — typ policzył się tylko na próbę",
  limit_meczu:
    "Z jednego meczu pokazujemy ograniczoną liczbę typów; ten się nie zmieścił",
  stare_dane: "Zawodnik dawno nie grał, więc typ policzył się tylko na próbę",
  za_pozno: "Powstał za blisko pierwszego gwizdka — nie zdążyłbyś go obstawić",
};

export function WierszTypu({
  t,
  pelnyWglad = true,
}: {
  t: TypRozliczony;
  /** false = widok klienta: bez kuchni (oznaczeń „na próbę", klas kart) */
  pelnyWglad?: boolean;
}) {
  const wygral = t.wynik === "wygrany";
  const przegral = t.wynik === "przegrany";
  return (
    <tr
      className={`border-t border-hairline transition-colors hover:bg-brand-wash/30 ${
        t.poza_publikacja ? "opacity-60" : ""
      }`}
    >
      <td className="py-2 pl-3 pr-2 align-top">
        <span
          aria-hidden
          className={`inline-block h-2 w-2 shrink-0 translate-y-px rounded-full ${
            wygral ? "bg-data-green" : przegral ? "bg-data-red" : "bg-data-amber"
          }`}
        />
      </td>
      <td className="max-w-0 py-2 pr-3 align-top">
        <span className="block truncate font-medium">{t.podmiot}</span>
        <span className="block truncate text-xs text-faint">{t.mecz}</span>
      </td>
      <td className="hidden py-2 pr-3 align-top text-muted sm:table-cell">
        <span className="block truncate">
          {t.rynek.toLowerCase()} {STRONA_LABEL[t.strona]} {fmtLinia(t.linia)}
        </span>
        {pelnyWglad && t.poza_publikacja && (
          <span
            className="text-[10px] uppercase tracking-wide text-faint"
            title={POZA_LABEL[t.poza_publikacja] ?? "Typ policzony tylko na próbę"}
          >
            na próbę
          </span>
        )}
      </td>
      <td
        className="font-data py-2 pr-3 text-right align-top tabular-nums text-ink-soft"
        title="Kurs z chwili, gdy typ pojawił się na stronie"
      >
        {t.kurs != null ? fmtKurs(t.kurs) : "–"}
      </td>
      {pelnyWglad && (
        <td
          className="font-data hidden py-2 pr-3 text-right align-top tabular-nums text-muted md:table-cell"
          title="Ile zawodnik albo drużyna faktycznie zanotowali w tym meczu"
        >
          {t.faktyczna != null ? t.faktyczna : "–"}
        </td>
      )}
      <td
        className={`py-2 pr-3 text-right align-top text-xs font-semibold whitespace-nowrap ${
          wygral
            ? "text-data-green"
            : przegral
              ? "text-data-red"
              : "text-data-amber-ink"
        }`}
      >
        {wygral ? "✓ weszło" : przegral ? "✗ nie" : "zwrot"}
      </td>
    </tr>
  );
}

/** Nagłówek tabeli — jeden na wszystkie miejsca, gdzie leci WierszTypu. */
export function NaglowekTypow({ pelnyWglad = true }: { pelnyWglad?: boolean }) {
  return (
    <thead>
      <tr className="text-left text-[10px] uppercase tracking-wide text-faint">
        <th className="w-6 pb-1.5 pl-3" />
        <th className="pb-1.5 pr-3 font-medium">kto</th>
        <th className="hidden pb-1.5 pr-3 font-medium sm:table-cell">typ</th>
        <th className="pb-1.5 pr-3 text-right font-medium">kurs</th>
        {pelnyWglad && (
          <th className="hidden pb-1.5 pr-3 text-right font-medium md:table-cell">
            było
          </th>
        )}
        <th className="pb-1.5 pr-3 text-right font-medium">wynik</th>
      </tr>
    </thead>
  );
}
