"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import { fmtLinia } from "@/lib/format";
import { useSzerokosc } from "@/lib/useSzerokosc";

import type { Strona } from "@/lib/types";

/**
 * Forma zawodnika: liczba zdarzeń w ostatnich meczach (najnowszy z prawej),
 * jako słupki z kreskowaną linią zakładu.
 *   zielony słupek  = typ by wszedł (nad linią przy "powyżej", pod przy "poniżej")
 *   szary słupek    = typ by nie wszedł
 *   półprzezroczysty = zawodnik grał krótko (<30 min) — wynik mało mówi
 *
 * Zamiast systemowego tooltipa: własna karta nad słupkiem (rywal, wynik,
 * minuty, klub/kadra, werdykt), hover na desktopie, tap na dotyku. Etykieta
 * linii siedzi na samej linii w prawej rynience — bez osobnej legendy.
 */
export function FormBars({
  counts,
  minutes,
  opponents,
  kadra,
  line,
  side = "powyzej",
  height = 56,
  rynek,
}: {
  counts: number[];
  minutes?: number[];
  opponents?: string[];
  kadra?: boolean[];
  line: number;
  side?: Strona;
  height?: number;
  /** nazwa rynku małą literą do karty hover, np. "strzały" */
  rynek?: string;
}) {
  const values = [...counts].reverse(); // najstarszy z lewej
  const mins = minutes ? [...minutes].reverse() : undefined;
  const opps = opponents ? [...opponents].reverse() : undefined;
  const nt = kadra ? [...kadra].reverse() : undefined;
  const max = Math.max(...values, Math.ceil(line + 0.5), 2);
  const labelH = 14; // miejsce na liczby nad słupkami
  const plotH = height - labelH;
  const lineY = labelH + (1 - line / max) * plotH;

  const reduced = useReducedMotion();
  const { ref, w } = useSzerokosc();
  const [tip, setTip] = useState<number | null>(null);

  const RYNNA = 44; // prawa rynienka na etykietę linii (px)
  // karta hover: środek nad słupkiem, przycięta do szerokości wykresu
  const tipLeft = (i: number) => {
    const obszar = Math.max(w - RYNNA, 1);
    const x = ((i + 0.5) / values.length) * obszar;
    return Math.min(Math.max(x, 84), Math.max(w - 84, 84));
  };
  // etykieta linii pod linią, chyba że linia leży nisko — wtedy nad nią
  const liniaNisko = lineY > height * 0.55;

  return (
    <div className="w-full">
      <div
        ref={ref}
        className="relative w-full"
        style={{ height }}
        role="img"
        aria-label={`Ostatnie ${values.length} meczów (od najstarszego): ${values.join(
          ", ",
        )}. Linia zakładu: ${fmtLinia(line)}.`}
      >
        {/* karta hover — jedna naraz, nad wykresem */}
        <AnimatePresence>
          {tip != null && (
            <motion.div
              key={tip}
              initial={reduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? undefined : { opacity: 0 }}
              transition={{ duration: 0.14 }}
              className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-(--radius-control) border border-hairline bg-card px-3 py-2 text-xs leading-snug shadow-(--shadow-card-hover)"
              style={{ left: tipLeft(tip), top: -6 }}
            >
              {(opps?.[tip] || nt) && (
                <p className="mb-0.5 text-[9px] uppercase tracking-wide text-faint">
                  {opps?.[tip] ? `vs ${opps[tip]}` : "mecz"}
                  {nt ? (nt[tip] ? " · kadra" : " · klub") : ""}
                </p>
              )}
              <p className="text-ink">
                {rynek ? `${rynek}: ` : ""}
                <span className="font-data text-sm font-semibold">
                  {values[tip]}
                </span>
                {mins?.[tip] != null && (
                  <span className="text-muted"> · {mins[tip]} min gry</span>
                )}
              </p>
              <p
                className={
                  (side === "ponizej" ? values[tip] < line : values[tip] > line)
                    ? "text-data-green-ink"
                    : "text-muted"
                }
              >
                {(side === "ponizej" ? values[tip] < line : values[tip] > line)
                  ? "✓ typ by wszedł"
                  : "✗ typ by nie wszedł"}
                {mins != null && mins[tip] > 0 && mins[tip] < 30 && (
                  <span className="text-data-amber-ink"> · krótki występ</span>
                )}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* słupki (z prawą rynienką na etykietę linii) */}
        <div
          className="absolute bottom-0 left-0 flex gap-1"
          style={{ height: plotH, right: RYNNA }}
        >
          {values.map((v, i) => {
            const over = side === "ponizej" ? v < line : v > line;
            const short = mins != null && mins[i] > 0 && mins[i] < 30;
            // zero = cienka kreska przy podstawie (nie udaje słupka)
            const h = v > 0 ? Math.max((v / max) * 100, 8) : 3;
            return (
              // h-full jest kluczowe: wysokość słupka to % wysokości kolumny
              <div
                key={i}
                className={`relative h-full flex-1 cursor-pointer transition-opacity duration-150 ${
                  tip != null && tip !== i ? "opacity-40" : ""
                }`}
                style={{ minWidth: 10 }}
                onMouseEnter={() => setTip(i)}
                onMouseLeave={() => setTip(null)}
                onClick={() => setTip(tip === i ? null : i)}
              >
                <motion.div
                  className="absolute inset-x-0 bottom-0 rounded-t-[5px]"
                  initial={reduced ? false : { height: 0 }}
                  animate={{ height: `${h}%` }}
                  transition={{
                    duration: 0.45,
                    delay: i * 0.035,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                  style={{
                    background: over
                      ? "linear-gradient(to top, var(--color-brand), var(--color-data-green))"
                      : "var(--color-hairline-strong)",
                    opacity: short ? 0.45 : 1,
                  }}
                />
                {nt?.[i] && (
                  <span
                    aria-hidden
                    className="absolute -bottom-[7px] left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-brand"
                  />
                )}
                <motion.span
                  aria-hidden
                  initial={reduced ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 + i * 0.035, duration: 0.25 }}
                  className="font-data absolute inset-x-0 text-center text-[9px]"
                  style={{
                    bottom: `calc(${h}% + 2px)`,
                    color: over ? "var(--color-brand-deep)" : "var(--color-faint)",
                  }}
                >
                  {v}
                </motion.span>
              </div>
            );
          })}
        </div>
        {/* podstawa */}
        <div
          aria-hidden
          className="absolute bottom-0 left-0 h-px bg-hairline"
          style={{ right: RYNNA }}
        />
        {/* kreskowana linia zakładu + etykieta na linii, w prawej rynience */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0"
          style={{
            top: lineY,
            borderTop: "1.5px dashed var(--color-ink)",
            opacity: 0.45,
          }}
        />
        <span
          aria-hidden
          className="absolute right-0 text-[9px] uppercase tracking-wide text-faint"
          style={{ top: liniaNisko ? lineY - 15 : lineY + 3 }}
        >
          linia <span className="font-data">{fmtLinia(line)}</span>
        </span>
      </div>
      <p className="mt-1.5 text-[10px] text-faint">najstarszy →</p>
    </div>
  );
}
