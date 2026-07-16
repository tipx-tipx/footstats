"use client";

import { motion, useReducedMotion } from "framer-motion";

import { fmtLinia, fmtProc } from "@/lib/format";

/**
 * Wizualizacje szans FootStats.
 *
 * ChanceBar — kompaktowy pasek w wierszu okazji: zielone wypełnienie =
 *   szansa modelu na "powyżej linii", z procentem i podpisem.
 * OutcomeColumns — rozwinięcie: kolumnowy mini-wykres możliwych wyników
 *   (0, 1, 2, 3+ zdarzeń), zielone kolumny = scenariusze "powyżej linii",
 *   kreskowana linia bukmachera między kolumnami, procenty nad słupkami.
 */

export function ChanceBar({
  p,
  line,
  side = "powyzej",
}: {
  p: number; // szansa modelu na wybraną stronę
  line: number;
  side?: "powyzej" | "ponizej";
}) {
  const strona = side === "powyzej" ? "powyżej" : "poniżej";
  const poz = (x: number) => Math.min(Math.max(x * 100, 2), 98);
  return (
    <div
      className="w-full"
      title={`Szansa modelu na ${strona} ${fmtLinia(line)}: ${fmtProc(p)}. Kreska na środku toru to 50%, rzut monetą`}
    >
      <div className="flex items-center gap-2.5">
        {/* tor szansy w języku karty hero: gładki tor, delikatne
            wypełnienie i znacznik modelu dojeżdżający animacją */}
        <div
          className="relative h-4 flex-1"
          role="img"
          aria-label={`Szansa modelu na ${strona} ${fmtLinia(line)}: ${fmtProc(p)}`}
        >
          <span
            aria-hidden
            className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-hairline"
          />
          {/* delikatne wypełnienie do szansy modelu — czytanie wielkości */}
          <motion.span
            aria-hidden
            initial={{ width: 0 }}
            animate={{ width: `${poz(p)}%` }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-brand/20"
          />
          {/* znacznik 50% — punkt odniesienia rzutu monetą */}
          <span
            aria-hidden
            className="absolute left-1/2 top-1/2 h-3 w-px -translate-y-1/2 bg-hairline-strong"
          />
          {/* znacznik modelu — dojeżdża na miejsce razem z wypełnieniem */}
          <motion.span
            aria-hidden
            initial={{ left: "2%", opacity: 0 }}
            animate={{ left: `${poz(p)}%`, opacity: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="absolute top-1/2 h-3.5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand"
          />
        </div>
        <span className="font-data shrink-0 text-[15px] font-semibold leading-none text-brand-deep">
          {fmtProc(p)}
        </span>
      </div>
      <p className="mt-1.5 text-[10px] leading-tight text-faint">
        szansa na {strona} {fmtLinia(line)} wg modelu
      </p>
    </div>
  );
}

export function OutcomeColumns({
  dist,
  line,
  side,
  height = 96,
}: {
  dist: number[];
  line: number;
  side?: "powyzej" | "ponizej";
  height?: number;
}) {
  const reduced = useReducedMotion();
  const total = dist.reduce((a, b) => a + b, 0) || 1;
  const norm = dist.map((p) => p / total);
  const threshold = Math.floor(line) + 1; // "powyżej 1,5" = X >= 2
  const maxP = Math.max(...norm, 0.001);
  const pPonizej = norm.slice(0, threshold).reduce((a, b) => a + b, 0);
  const pPowyzej = 1 - pPonizej;
  const labelH = 16;
  const axisH = 16;
  const plotH = height - labelH - axisH;

  return (
    <div className="w-full">
      <div
        className="relative flex items-end gap-[3px]"
        style={{ height: labelH + plotH }}
        role="img"
        aria-label={`Możliwe wyniki i ich szanse. Powyżej linii ${fmtLinia(line)}: ${fmtProc(
          pPowyzej,
        )}, poniżej: ${fmtProc(pPonizej)}.`}
      >
        {norm.map((p, k) => {
          const over = k >= threshold;
          const h = Math.max((p / maxP) * plotH, p > 0.001 ? 3 : 1.5);
          return (
            <div key={k} className="relative flex-1" style={{ minWidth: 14 }}>
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: h }}
                transition={{
                  delay: reduced ? 0 : 0.04 * k,
                  duration: 0.5,
                  ease: [0.22, 1, 0.36, 1],
                }}
                className="absolute inset-x-0 bottom-0 rounded-t-[4px]"
                style={{
                  background: over
                    ? "var(--color-data-green)"
                    : "var(--color-hairline-strong)",
                }}
                title={`${k === norm.length - 1 ? `${k}+` : k}: szansa ${fmtProc(p, 1)}`}
              />
              {p >= 0.04 && (
                <span
                  aria-hidden
                  className="font-data absolute inset-x-0 text-center text-[9px] font-medium"
                  style={{
                    bottom: h + 3,
                    color: over ? "var(--color-brand-deep)" : "var(--color-faint)",
                  }}
                >
                  {fmtProc(p)}
                </span>
              )}
            </div>
          );
        })}
        {/* kreskowana linia bukmachera między "poniżej" a "powyżej" */}
        <div
          aria-hidden
          className="absolute bottom-0 top-1"
          style={{
            left: `calc(${(threshold / norm.length) * 100}% - 1.5px)`,
            width: 0,
            borderLeft: "2px dashed var(--color-ink)",
            opacity: 0.35,
          }}
        />
      </div>
      {/* oś: liczba zdarzeń */}
      <div className="flex gap-[3px] border-t border-hairline pt-1">
        {norm.map((_, k) => (
          <span
            key={k}
            className="font-data flex-1 text-center text-[10px] text-faint"
            style={{ minWidth: 14 }}
          >
            {k === norm.length - 1 ? `${k}+` : k}
          </span>
        ))}
      </div>
      {/* podsumowanie stron */}
      <div className="mt-2 flex items-center justify-between text-[11px]">
        <span
          className={
            side === "ponizej" ? "font-semibold text-ink" : "text-muted"
          }
        >
          poniżej {fmtLinia(line)}:{" "}
          <span className="font-data font-medium">{fmtProc(pPonizej)}</span>
        </span>
        <span
          className={
            side === "ponizej" ? "text-muted" : "font-semibold text-brand-deep"
          }
        >
          powyżej {fmtLinia(line)}:{" "}
          <span className="font-data font-medium">{fmtProc(pPowyzej)}</span>
        </span>
      </div>
    </div>
  );
}
