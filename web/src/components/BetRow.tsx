"use client";

import { memo, useState } from "react";

import { SzczegolyTypu } from "./BetCard";
import { KROPKA_STYL, przewagaKropki } from "@/lib/slownik";
import { DrabinkaLinii } from "./DrabinkaLinii";
import {
  fmtKurs,
  fmtProc,
  nazwaPodmiotu,
  opisZakladu,
  rywalWZakladzie,
} from "@/lib/format";
import type { FormaRynku, ValueBet } from "@/lib/types";
import { odmienLinie } from "@/lib/warianty";

/**
 * Gęsty wiersz ceduły typów – jednostka tablicy /druzyny przy skali sezonu
 * (setki typów dziennie): jedna linia z diodą, drużyną, rynkiem, szansą
 * i kursem. Klik otwiera pełne rozwinięcie karty (SzczegolyTypu) – wiersz
 * dosłownie "staje się" kartą, lista wraca do gęstej ceduły po zwinięciu.
 */

/**
 * SIATKA WIERSZA — jedna definicja dla wiersza i dla nagłówka kolumn.
 *
 * Nagłówek musi stać DOKŁADNIE nad swoimi kolumnami, więc gdyby trzymał własną
 * kopię tego napisu, pierwsza zmiana szerokości rozjechałaby podpisy z danymi
 * i nikt by tego nie zauważył poza zrzutem. Ta sama zasada, co przy słowniku
 * powodów i przy przedziałach kursowych kuponów.
 */
export const GRID_WIERSZA =
  "grid w-full grid-cols-[minmax(0,1fr)_auto_auto] gap-x-3" +
  " sm:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_auto_auto_auto]" +
  " md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_7rem_auto_auto_auto]";

/**
 * NAGŁÓWKI KOLUMN (2026-08-05, przegląd sprzedażowy).
 *
 * Wiersz to: nazwa → rynek → pasek → `91%` → `1,34`. Nigdzie nie było
 * napisane, że pierwsza liczba to nasza szansa, a druga kurs bukmachera —
 * czytelnik musiał zgadnąć, i to przy dwóch liczbach, które wyglądają
 * podobnie i znaczą coś zupełnie innego.
 *
 * Wersaliki 10 px i kolor `faint`: to ma być podpis, nie kolejny element
 * krzyczący o uwagę. Na telefonie znika razem z kolumnami, które opisuje
 * (tam rynek stoi pod nazwą, a nie w osobnej kolumnie).
 */
export function BetRowNaglowek() {
  return (
    <div
      aria-hidden
      className={`${GRID_WIERSZA} hidden items-end px-2 pb-1 pt-1 text-[10px] uppercase tracking-wide text-faint sm:grid sm:px-3`}
    >
      <span>drużyna</span>
      <span>zakład</span>
      <span className="hidden md:block" />
      <span className="w-11 text-right">szansa</span>
      <span className="w-12 text-right">kurs</span>
      <span className="w-3" />
    </div>
  );
}

function godzinaMeczu(ts: number): string {
  return new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

export const BetRow = memo(function BetRow({
  bet: glowny,
  forma: formaGlownego,
  pokazGodzine = false,
  liga,
  warianty,
}: {
  bet: ValueBet;
  forma?: FormaRynku;
  /** tryb "wg godziny": godzina jako wyrównana kolumna z przodu wiersza */
  pokazGodzine?: boolean;
  /** nazwa rozgrywek w metadanych – dla list płaskich, bez sekcji lig */
  liga?: string;
  /** pozostałe linie tego samego typu – jeden wiersz zamiast trzech */
  warianty?: ValueBet[];
}) {
  const [open, setOpen] = useState(false);
  const [wybranyId, setWybranyId] = useState(glowny.id);
  const bet = warianty?.find((b) => b.id === wybranyId) ?? glowny;
  // forma jest per rynek, a warianty dzielą rynek – ten sam wykres pasuje
  const forma = formaGlownego;
  const kropka = przewagaKropki(bet);
  const opisRynku = opisZakladu(bet, true);
  const poz = Math.min(Math.max(bet.p_model * 100, 2), 98);
  // rywala liczymy z nazwy meczu, gdy rekord go nie niesie: przy sumach
  // meczowych pipeline zostawia `przeciwnik` pusty, a wtedy wiersz gubił
  // nie tylko rywala, ale i GODZINĘ — bo obie wisiały na jednym warunku
  const rywal = rywalWZakladzie(bet);
  const meta = (
    pokazGodzine
      ? [rywal ? `z ${rywal}` : null, liga]
      : [
          rywal
            ? `${godzinaMeczu(bet.kickoff_ts)} z ${rywal}`
            : godzinaMeczu(bet.kickoff_ts),
          liga,
        ]
  )
    .filter(Boolean)
    .join(" · ");

  return (
    <article
      className={
        open
          ? "my-2.5 overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)"
          : "border-b border-hairline transition-colors hover:bg-card-soft"
      }
    >
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={`${GRID_WIERSZA} items-center px-2 py-2 text-left sm:px-3`}
      >
        {/* kto gra: dioda formy + drużyna, obok cicho godzina i rywal */}
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            {pokazGodzine && (
              <span className="font-data w-10 shrink-0 text-xs tabular-nums text-muted">
                {godzinaMeczu(bet.kickoff_ts)}
              </span>
            )}
            {/* KROPKA = O ILE KURS BIJE NASZĄ WYCENĘ (2026-08-02, patrz
                `przewagaKropki`). Wcześniej pokazywała zgodność z historią
                i przez to była pusta w 11 przypadkach na 16, a gdy świeciła
                na czerwono — podważała typ, który sami polecamy. Teraz jest
                zawsze i mówi to, co decyduje o obecności typu na liście.
                Lampka formy nie znika: schodzi do rozwinięcia, gdzie jest
                dowodem obok wykresu, a nie wyrokiem w kolumnie. */}
            <span
              aria-hidden
              title={`${kropka.label} – ${kropka.opis}`}
              className={`h-2 w-2 shrink-0 rounded-full ${KROPKA_STYL[kropka.kod]}`}
            />
            <span className="min-w-0 truncate">
              <span className="text-sm font-semibold">
                {nazwaPodmiotu(bet)}
              </span>
              {meta && (
                <span className="ml-2 text-[11px] text-faint">{meta}</span>
              )}
            </span>
          </span>
          {/* mobile: rynek schodzi pod nazwę, wciąż zwarty dwuwiersz */}
          <span
            className={`mt-0.5 block truncate text-[11px] text-muted sm:hidden ${
              pokazGodzine ? "pl-16" : "pl-4"
            }`}
          >
            {opisRynku}
          </span>
        </span>

        <span className="hidden min-w-0 truncate text-sm text-muted sm:block">
          {opisRynku}
          {warianty && warianty.length > 1 && (
            <span className="font-data ml-2 rounded-full bg-paper px-1.5 py-0.5 text-[10px] text-faint">
              +{odmienLinie(warianty.length - 1)}
            </span>
          )}
        </span>

        {/* tor szansy: znacznik modelu na skali 0–100, kreska = rzut monetą */}
        {/* bez dymka: sam procent stoi w następnej kolumnie, a pasek jest
            tylko jego obrazkiem (przegląd kart 2026-08-01) */}
        <span aria-hidden className="relative hidden h-4 md:block">
          <span className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-hairline" />
          <span
            className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand/25"
            style={{ width: `${poz}%` }}
          />
          <span className="absolute left-1/2 top-1/2 h-2.5 w-px -translate-y-1/2 bg-hairline-strong" />
          <span
            className="absolute top-1/2 h-3 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand"
            style={{ left: `${poz}%` }}
          />
        </span>

        <span className="font-data w-11 text-right text-sm font-semibold text-brand-deep">
          {fmtProc(bet.p_model)}
        </span>

        <span className="font-data w-12 text-right text-sm font-semibold">
          {bet.kurs != null ? fmtKurs(bet.kurs) : `~${fmtKurs(bet.fair_kurs * 1.05)}`}
        </span>

        <svg
          aria-hidden
          width="12"
          height="12"
          viewBox="0 0 14 14"
          className={`hidden shrink-0 text-faint transition-transform sm:block ${open ? "rotate-180" : ""}`}
        >
          <path
            d="M3 5.5 L7 9.5 L11 5.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && warianty && warianty.length > 1 && (
        <DrabinkaLinii
          warianty={warianty}
          wybrany={bet.id}
          onWybor={setWybranyId}
          className="border-t border-hairline px-2 pb-3 pt-3 sm:px-3"
        />
      )}

      <SzczegolyTypu bet={bet} forma={forma} open={open} />
    </article>
  );
});
