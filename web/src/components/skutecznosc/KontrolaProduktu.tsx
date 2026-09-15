"use client";

import { useEffect, useState } from "react";

import type { SprawdzenieKontroli, TypyWyniki } from "@/lib/types";

/**
 * KONTROLA PRODUKTU – panel wyłącznie dla admina (2026-09-13).
 *
 * Każda usterka ostatnich tygodni wyszła dopiero wtedy, gdy właściciel sam ją
 * zobaczył na stronie: karty Drabinek liczone jako „próby”, typy ze strony bez
 * zapisu do rozliczenia, faule zawodników ginące na zwrotach. Backend liczy
 * teraz po każdym rozliczeniu pięć sprawdzeń (`rozliczanie.kontrola_produktu`),
 * a szóste – czy cykl żyje – liczymy tu, z czasu wygenerowania danych.
 *
 * Zielono: jedna linijka, nie zabiera miejsca. Czerwono: lista konkretów.
 */

const NAZWY: Record<string, string> = {
  cykl: "Cykl aktualizuje stronę",
  zapis_pokazanych: "Zapis tego, co było na stronie",
  strona_bez_rekordu: "Typy ze strony mają zapis do rozliczenia",
  zaleglosc_rozliczen: "Rozliczenia na bieżąco",
  strona_bez_wiersza: "Każdy typ ze strony ma wiersz w Skuteczności",
  bez_danych: "Typy ze strony zamykane z wynikiem",
  wagi_modelu: "Nocny trening modelu",
};

/** Po tylu godzinach bez nowego cyklu uznajemy, że strona stoi. */
const CYKL_MAX_H = 3;

export function KontrolaProduktu({
  kontrola,
  wygenerowanoTs,
}: {
  kontrola: TypyWyniki["kontrola"];
  /** `meta.wygenerowano_ts` – kiedy cykl ostatnio wystawił dane (sekundy) */
  wygenerowanoTs?: number;
}) {
  // zegar czytamy PO zamontowaniu (jak świeżość STS w ValueBoard) – odczyt
  // w renderze rozjechałby SSR z hydracją; do tego czasu cykl „nie wiadomo”
  const [teraz, setTeraz] = useState<number | null>(null);
  useEffect(() => {
    setTeraz(Math.floor(Date.now() / 1000));
  }, []);
  if (!kontrola) return null;
  const wiekCykluH =
    wygenerowanoTs && teraz !== null ? (teraz - wygenerowanoTs) / 3600 : null;
  const cykl: SprawdzenieKontroli = {
    kod: "cykl",
    // przed zamontowaniem nie alarmujemy – brak zegara to nie awaria cyklu
    ok: teraz === null || (wiekCykluH !== null && wiekCykluH <= CYKL_MAX_H),
    liczba: wiekCykluH === null ? null : Math.round(wiekCykluH * 10) / 10,
    opis:
      teraz === null
        ? "sprawdzam…"
        : wiekCykluH === null
        ? "brak znacznika czasu ostatniego cyklu"
        : `ostatni cykl ${Math.round(wiekCykluH * 60)} min temu`,
  };
  const wszystkie = [cykl, ...kontrola.sprawdzenia];
  const zle = wszystkie.filter((s) => !s.ok);

  if (zle.length === 0) {
    return (
      <p className="max-w-3xl rounded-(--radius-control) border border-hairline bg-card px-4 py-2.5 text-xs text-muted">
        <span
          aria-hidden
          className="mr-2 inline-block size-1.5 rounded-full bg-data-green align-middle"
        />
        <strong className="font-semibold text-ink">Kontrola: wszystko się zgadza</strong>{" "}
        ({wszystkie.length} z {wszystkie.length} sprawdzeń)
      </p>
    );
  }

  return (
    <div className="max-w-3xl rounded-(--radius-card) border border-data-red/40 bg-card px-4 py-3.5">
      <p className="text-sm">
        <strong className="text-data-red-ink">
          Kontrola: {zle.length} z {wszystkie.length} sprawdzeń nie przechodzi
        </strong>
      </p>
      <ul className="mt-2.5 space-y-2">
        {wszystkie.map((s) => (
          <li key={s.kod} className="flex gap-2 text-sm">
            <span
              aria-hidden
              className={`mt-2 inline-block size-1.5 shrink-0 rounded-full ${
                s.ok ? "bg-data-green" : "bg-data-red"
              }`}
            />
            <div className="min-w-0">
              <span className="font-medium">{NAZWY[s.kod] ?? s.kod}</span>
              <p
                className={`mt-0.5 break-words text-[13px] ${
                  s.ok ? "text-faint" : "text-data-red-ink"
                }`}
              >
                {s.opis}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
