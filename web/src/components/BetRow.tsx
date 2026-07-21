"use client";

import { memo, useState } from "react";

import { SWIATLO_STYL, swiatloTypu, SzczegolyTypu } from "./BetCard";
import { fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";
import type { FormaRynku, ValueBet } from "@/lib/types";

/**
 * Gęsty wiersz ceduły typów — jednostka tablicy /druzyny przy skali sezonu
 * (setki typów dziennie): jedna linia z diodą, drużyną, rynkiem, szansą
 * i kursem. Klik otwiera pełne rozwinięcie karty (SzczegolyTypu) — wiersz
 * dosłownie "staje się" kartą, lista wraca do gęstej ceduły po zwinięciu.
 */

function godzinaMeczu(ts: number): string {
  return new Intl.DateTimeFormat("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

/** "Gole drużyny" → "gole": w wierszu liczy się rytm skanowania, nie pełna nazwa. */
const rynekKrotko = (rynek: string) =>
  rynek.toLowerCase().replace(/\s*drużyny\s*/g, " ").trim();

export const BetRow = memo(function BetRow({
  bet,
  forma,
  pokazGodzine = false,
  liga,
}: {
  bet: ValueBet;
  forma?: FormaRynku;
  /** tryb "wg godziny": godzina jako wyrównana kolumna z przodu wiersza */
  pokazGodzine?: boolean;
  /** nazwa rozgrywek w metadanych — dla list płaskich, bez sekcji lig */
  liga?: string;
}) {
  const [open, setOpen] = useState(false);
  const swiatlo = swiatloTypu(forma, bet.linia, bet.p_model, bet.strona);
  const opisRynku = `${rynekKrotko(bet.rynek)} ${STRONA_LABEL[bet.strona]} ${fmtLinia(bet.linia)}`;
  const poz = Math.min(Math.max(bet.p_model * 100, 2), 98);
  const meta = (
    pokazGodzine
      ? [bet.przeciwnik ? `z ${bet.przeciwnik}` : null, liga]
      : [
          bet.przeciwnik
            ? `${godzinaMeczu(bet.kickoff_ts)} z ${bet.przeciwnik}`
            : null,
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
        className="grid w-full grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 px-2 py-2 text-left sm:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_auto_auto_auto] sm:px-3 md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_7rem_auto_auto_auto]"
      >
        {/* kto gra: dioda formy + drużyna, obok cicho godzina i rywal */}
        <span className="min-w-0">
          <span className="flex min-w-0 items-center gap-2">
            {pokazGodzine && (
              <span className="font-data w-10 shrink-0 text-xs tabular-nums text-muted">
                {godzinaMeczu(bet.kickoff_ts)}
              </span>
            )}
            {swiatlo ? (
              <span
                title={SWIATLO_STYL[swiatlo].opis}
                className="relative inline-flex h-2 w-2 shrink-0 items-center justify-center"
              >
                <span
                  aria-hidden
                  className={`absolute -inset-1 rounded-full opacity-20 ${SWIATLO_STYL[swiatlo].pasek}`}
                />
                <span
                  aria-hidden
                  className={`h-2 w-2 rounded-full ${SWIATLO_STYL[swiatlo].pasek}`}
                />
              </span>
            ) : (
              <span aria-hidden className="h-2 w-2 shrink-0 rounded-full bg-hairline-strong/60" />
            )}
            <span className="min-w-0 truncate">
              <span className="text-sm font-semibold">{bet.podmiot}</span>
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
        </span>

        {/* tor szansy: znacznik modelu na skali 0–100, kreska = rzut monetą */}
        <span
          aria-hidden
          className="relative hidden h-4 md:block"
          title={`Szansa modelu: ${fmtProc(bet.p_model)} (kreska na środku toru to 50%)`}
        >
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

        <span
          className="font-data w-12 text-right text-sm font-semibold"
          title={
            bet.kurs == null
              ? `Kurs sprawdzasz ręcznie: od ~${fmtKurs(bet.fair_kurs * 1.05)} w górę warto grać`
              : `Kurs ${bet.bukmacher}`
          }
        >
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

      <SzczegolyTypu bet={bet} forma={forma} open={open} />
    </article>
  );
});
