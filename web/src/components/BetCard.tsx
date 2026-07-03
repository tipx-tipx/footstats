"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { ConfidenceBadge, DataPill, EdgeBadge, RiskBadge } from "./badges";
import { DistributionStrip } from "./DistributionStrip";
import { FormBars } from "./Sparkline";
import { addZakladFromBet, isTracked, onZakladyChange } from "@/lib/tracker";
import {
  fmtDataCzas,
  fmtKurs,
  fmtLinia,
  fmtMnoznik,
  fmtPP,
  fmtProc,
  STRONA_LABEL,
} from "@/lib/format";
import type { ValueBet, Zawodnik } from "@/lib/types";

export function BetCard({
  bet,
  rank,
  zawodnik,
}: {
  bet: ValueBet;
  rank: number;
  zawodnik?: Zawodnik;
}) {
  const [open, setOpen] = useState(false);
  const [tracked, setTracked] = useState(false);
  const reduced = useReducedMotion();

  useEffect(() => {
    setTracked(isTracked(bet.id));
    return onZakladyChange(() => setTracked(isTracked(bet.id)));
  }, [bet.id]);

  const forma = zawodnik?.forma[bet.rynek_kod];

  return (
    <motion.article
      layout={!reduced}
      className="overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)"
    >
      {/* wiersz główny */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-2 px-4 py-3 text-left sm:grid-cols-[auto_1.4fr_1fr_auto_auto]"
      >
        <span
          aria-hidden
          className="font-data hidden w-7 text-right text-sm text-faint sm:block"
        >
          {rank}
        </span>

        <span className="min-w-0">
          <span className="block truncate font-semibold">
            {bet.podmiot}
            <span className="ml-2 font-normal text-muted">
              {bet.rynek.toLowerCase()} {STRONA_LABEL[bet.strona]}{" "}
              {fmtLinia(bet.linia)}
            </span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-faint">
            {bet.mecz} · {fmtDataCzas(bet.kickoff_ts)}
          </span>
        </span>

        <span className="hidden min-w-0 items-center gap-3 sm:flex">
          <span className="w-full max-w-44">
            {bet.rozklad ? (
              <DistributionStrip dist={bet.rozklad} line={bet.linia} height={16} />
            ) : (
              <span className="text-xs text-faint">
                szansa: {fmtProc(bet.p_model)}
              </span>
            )}
          </span>
        </span>

        <span className="flex flex-col items-end gap-0.5">
          <span className="font-data text-base font-semibold">
            {bet.kurs != null ? fmtKurs(bet.kurs) : fmtProc(bet.p_model)}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-faint">
            {bet.kurs != null ? bet.bukmacher : "szansa modelu"}
          </span>
        </span>

        <span className="flex items-center justify-end gap-2">
          {bet.sugestia || bet.ev_pct == null ? (
            <span
              className="inline-flex items-center rounded-md bg-data-amber-wash px-2 py-0.5 text-xs font-semibold text-[#8a5613]"
              title="Rynek dostępny w STS — sprawdź kurs ręcznie"
            >
              sprawdź w STS
            </span>
          ) : (
            <EdgeBadge ev={bet.ev_pct} />
          )}
          <svg
            aria-hidden
            width="14"
            height="14"
            viewBox="0 0 14 14"
            className={`text-faint transition-transform ${open ? "rotate-180" : ""}`}
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
        </span>
      </button>

      {/* szczegóły */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          >
            <div className="grid gap-6 border-t border-hairline bg-paper/50 px-4 py-5 sm:grid-cols-2 sm:px-6">
              {/* lewa: liczby i uzasadnienie */}
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
                  <DataPill
                    label="szansa wg modelu"
                    value={fmtProc(bet.p_model)}
                    emphasis
                  />
                  {bet.sugestia ? (
                    <DataPill
                      label="uczciwy kurs (szacunek)"
                      value={fmtKurs(bet.fair_kurs)}
                    />
                  ) : (
                    <>
                      {bet.p_rynku != null && (
                        <DataPill label="kurs mówi" value={fmtProc(bet.p_rynku)} />
                      )}
                      <DataPill label="uczciwy kurs" value={fmtKurs(bet.fair_kurs)} />
                      {bet.edge_pp != null && (
                        <DataPill
                          label="przewaga"
                          value={fmtPP(bet.edge_pp)}
                          emphasis
                        />
                      )}
                    </>
                  )}
                </div>
                {bet.sugestia ? (
                  <p className="rounded-lg border border-data-amber/40 bg-data-amber-wash px-3 py-2 text-xs leading-relaxed text-[#6d4410]">
                    <strong>Sugestia bez kursu.</strong> Ten rynek (niecelne /
                    zablokowane) jest w STS, ale STS nie działa z chmury. Model
                    szacuje szansę z „strzały − celne" — <strong>sprawdź kurs w
                    STS ręcznie</strong> i oceń, czy jest wartość.
                  </p>
                ) : (
                  bet.ci[0] != null && (
                    <p className="text-xs text-muted">
                      Widełki szansy:{" "}
                      <span className="font-data">
                        {fmtProc(bet.ci[0])}–{fmtProc(bet.ci[1] as number)}
                      </span>{" "}
                      — im węższe, tym stabilniejsza predykcja.
                    </p>
                  )
                )}
                <div className="flex flex-wrap items-center gap-3">
                  <ConfidenceBadge level={bet.pewnosc} />
                  <RiskBadge level={bet.ryzyko} />
                </div>

                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                    Dlaczego ten zakład
                  </h4>
                  <ul className="space-y-1.5">
                    {bet.uzasadnienie.czynniki.map((c) => (
                      <li
                        key={c.nazwa}
                        className="flex items-start justify-between gap-3 text-sm"
                      >
                        <span>
                          <span className="font-medium">{c.nazwa}:</span>{" "}
                          <span className="text-ink-soft">{c.opis}</span>
                        </span>
                        {c.mnoznik !== null && (
                          <span
                            className={`font-data shrink-0 rounded px-1.5 py-0.5 text-xs ${
                              c.mnoznik > 1.02
                                ? "bg-data-green-wash text-brand-deep"
                                : c.mnoznik < 0.98
                                  ? "bg-data-red-wash text-data-red"
                                  : "bg-paper text-muted"
                            }`}
                          >
                            {fmtMnoznik(c.mnoznik)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* prawa: wykresy */}
              <div className="space-y-5">
                {bet.rozklad && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Możliwe wyniki i ich szanse
                    </h4>
                    <DistributionStrip
                      dist={bet.rozklad}
                      line={bet.linia}
                      side={bet.strona}
                      height={30}
                      showLabels
                    />
                  </div>
                )}
                {forma && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Ostatnie mecze ({bet.rynek.toLowerCase()}) — linia{" "}
                      {fmtLinia(bet.linia)}
                    </h4>
                    <FormBars
                      counts={forma.ostatnie}
                      minutes={forma.minuty}
                      line={bet.linia}
                    />
                    <p className="mt-1.5 text-xs text-faint">
                      Średnio {forma.srednia90.toFixed(2).replace(".", ",")} na 90
                      minut · przewidywane minuty:{" "}
                      {bet.oczekiwane_minuty != null
                        ? Math.round(bet.oczekiwane_minuty)
                        : "—"}
                    </p>
                  </div>
                )}
                {bet.sugestia ? (
                  <p className="rounded-lg border border-hairline bg-card px-3 py-2.5 text-center text-xs text-muted">
                    Otwórz STS, znajdź ten rynek dla zawodnika i sprawdź kurs.
                    Jeśli jest wartość — dodasz w „Moich zakładach".
                  </p>
                ) : (
                  <button
                    onClick={() => addZakladFromBet(bet, null)}
                    disabled={tracked}
                    className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
                      tracked
                        ? "cursor-default bg-brand-wash text-brand"
                        : "bg-brand text-white hover:bg-brand-deep"
                    }`}
                  >
                    {tracked ? "✓ W moich zakładach" : "Dodaj do moich zakładów"}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}
