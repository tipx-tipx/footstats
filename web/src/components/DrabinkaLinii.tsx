"use client";

import { fmtKurs, fmtLinia, fmtProc, STRONA_LABEL } from "@/lib/format";
import { charakterSzczebla } from "@/lib/slownik";
import { odmienLinie } from "@/lib/warianty";
import type { ValueBet } from "@/lib/types";

/**
 * DRABINKA LINII NA KARCIE TYPU (2026-08-01, zgłoszenie usera).
 *
 * Gdy model typuje tę samą drużynę i ten sam rynek na kilku poprzeczkach
 * (rożne poniżej 4,5 · 5,5 · 6,5), lista pokazywała TRZY karty pod rząd –
 * wyglądało to jak trzy niezależne pomysły. To jest jeden pomysł wyceniony
 * trzy razy, więc dostaje jedną kartę i wybór szczebla, dokładnie tak jak
 * karty Drabinek.
 *
 * Klikalne szczeble muszą stać POZA przyciskiem rozwijającym kartę (przycisk
 * w przycisku to nieprawidłowy HTML i klik i tak trafiałby w rozwinięcie),
 * dlatego to osobny pasek pod wierszem głównym.
 */
export function DrabinkaLinii({
  warianty,
  wybrany,
  onWybor,
  className = "px-4 pb-3 sm:pl-[4.75rem] sm:pr-5",
}: {
  warianty: ValueBet[];
  /** id aktualnie tłumaczonego typu */
  wybrany: number;
  onWybor: (id: number) => void;
  /** wcięcie dopasowane do gospodarza: karta ma kolumnę numeru, wiersz nie */
  className?: string;
}) {
  if (warianty.length < 2) return null;
  const b0 = warianty[0];
  return (
    <div className={className}>
      <div className="rounded-(--radius-control) border border-hairline bg-card-soft/70 p-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-ink-soft">
          {odmienLinie(warianty.length)} tego samego typu
          <span className="ml-2 font-normal normal-case tracking-normal text-faint">
            wyżej postawiona poprzeczka = wyższy kurs i niższa szansa
          </span>
        </p>
        <div className="flex flex-wrap gap-1.5">
          {warianty.map((b) => {
            const aktywny = b.id === wybrany;
            return (
              <button
                key={b.id}
                type="button"
                onClick={() => onWybor(b.id)}
                aria-pressed={aktywny}
                className={`flex w-[84px] flex-col items-center rounded-md px-1 py-2 text-center transition-colors sm:w-[92px] ${
                  aktywny
                    ? "bg-card shadow-(--shadow-card) ring-1 ring-brand"
                    : "bg-card/60 hover:bg-card"
                }`}
              >
                <span
                  className={`font-data text-[12px] font-semibold ${
                    aktywny ? "text-brand" : "text-ink-soft"
                  }`}
                >
                  {STRONA_LABEL[b.strona] ?? b.strona} {fmtLinia(b.linia)}
                </span>
                <span
                  className={`font-data tabular-nums ${
                    aktywny
                      ? "text-[17px] font-bold leading-tight text-ink"
                      : "text-[13px] font-semibold text-ink-soft"
                  }`}
                >
                  {b.kurs != null ? fmtKurs(b.kurs) : "–"}
                </span>
                <span
                  className={`font-data text-[11px] tabular-nums ${
                    aktywny ? "text-brand-deep" : "text-faint"
                  }`}
                >
                  {fmtProc(b.p_model)}
                </span>
                <span className="mt-0.5 text-[9px] uppercase leading-tight tracking-tight text-faint">
                  {charakterSzczebla(b.kurs) ?? ""}
                </span>
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-muted">
          Poniżej tłumaczymy wybrany szczebel
          {b0.podmiot_typ === "druzyna" ? "" : " tego zawodnika"}. Kliknij inny,
          żeby zobaczyć jego rachunek.
        </p>
      </div>
    </div>
  );
}
