"use client";

import { fmtLinia } from "@/lib/format";

/**
 * Forma zawodnika: liczba zdarzeń w ostatnich meczach (najnowszy z prawej),
 * jako słupki z kreskowaną linią zakładu.
 *   zielony słupek  = wynik nad linią (zakład "powyżej" by wszedł)
 *   szary słupek    = wynik pod linią
 *   półprzezroczysty = zawodnik grał krótko (<30 min) — wynik mało mówi
 * Nad każdym słupkiem mała liczba — konkretny wynik z tamtego meczu.
 */
export function FormBars({
  counts,
  minutes,
  opponents,
  kadra,
  line,
  height = 56,
}: {
  counts: number[];
  minutes?: number[];
  opponents?: string[];
  kadra?: boolean[];
  line: number;
  height?: number;
}) {
  const values = [...counts].reverse(); // najstarszy z lewej
  const mins = minutes ? [...minutes].reverse() : undefined;
  const opps = opponents ? [...opponents].reverse() : undefined;
  const nt = kadra ? [...kadra].reverse() : undefined;
  const max = Math.max(...values, Math.ceil(line + 0.5), 2);
  const labelH = 14; // miejsce na liczby nad słupkami
  const plotH = height - labelH;
  const lineY = labelH + (1 - line / max) * plotH;

  return (
    <div className="w-full">
      <div
        className="relative w-full"
        style={{ height }}
        role="img"
        aria-label={`Ostatnie ${values.length} meczów (od najstarszego): ${values.join(
          ", ",
        )}. Linia zakładu: ${fmtLinia(line)}.`}
      >
        {/* słupki */}
        <div
          className="absolute inset-x-0 bottom-0 flex gap-1"
          style={{ height: plotH }}
        >
          {values.map((v, i) => {
            const over = v > line;
            const short = mins != null && mins[i] > 0 && mins[i] < 30;
            // zero = cienka kreska przy podstawie (nie udaje słupka)
            const h = v > 0 ? Math.max((v / max) * 100, 8) : 3;
            return (
              // h-full jest kluczowe: wysokość słupka to % wysokości kolumny
              <div key={i} className="relative h-full flex-1" style={{ minWidth: 10 }}>
                <div
                  className="absolute inset-x-0 bottom-0 rounded-t-[5px]"
                  style={{
                    height: `${h}%`,
                    background: over
                      ? "linear-gradient(to top, var(--color-brand), var(--color-data-green))"
                      : "var(--color-hairline-strong)",
                    opacity: short ? 0.45 : 1,
                  }}
                  title={`${v}${opps?.[i] ? ` vs ${opps[i]}` : ""} — ${
                    mins ? `${mins[i]} min gry, ` : ""
                  }${values.length - i} ${values.length - i === 1 ? "mecz" : "mecze/-ów"} temu${
                    nt?.[i] ? " · reprezentacja" : ""
                  }${short ? " (krótki występ)" : ""}`}
                />
                {nt?.[i] && (
                  <span
                    aria-hidden
                    title="Mecz reprezentacji"
                    className="absolute -bottom-[7px] left-1/2 h-[3px] w-[3px] -translate-x-1/2 rounded-full bg-brand"
                  />
                )}
                <span
                  aria-hidden
                  className="font-data absolute inset-x-0 text-center text-[9px]"
                  style={{
                    bottom: `calc(${h}% + 2px)`,
                    color: over ? "var(--color-brand-deep)" : "var(--color-faint)",
                  }}
                >
                  {v}
                </span>
              </div>
            );
          })}
        </div>
        {/* podstawa */}
        <div
          aria-hidden
          className="absolute inset-x-0 bottom-0 h-px bg-hairline"
        />
        {/* kreskowana linia zakładu */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0"
          style={{
            top: lineY,
            borderTop: "1.5px dashed var(--color-ink)",
            opacity: 0.45,
          }}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[10px] text-faint">
        <span>najstarszy →</span>
        <span>
          – – linia <span className="font-data">{fmtLinia(line)}</span>
          {nt?.some(Boolean) && (
            <>
              {" "}
              · <span aria-hidden className="mx-0.5 inline-block h-[3px] w-[3px] rounded-full bg-brand align-middle" />{" "}
              kadra
            </>
          )}{" "}
          · blade = krótki występ
        </span>
      </div>
    </div>
  );
}
