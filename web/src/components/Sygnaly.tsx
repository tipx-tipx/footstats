"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState, type ReactNode } from "react";

/**
 * Sygnaly — argumenty za typem jako rząd kafelków, opis pod spodem.
 *
 * Pierwszy sygnał startuje otwarty: sekcja od razu coś mówi, zamiast czekać
 * na klik. Kafelki mają ramkę (czytelne „to się klika"), aktywny dostaje
 * wash i ramkę w swoim tonie. Jeden opis naraz. Ton "cichy" = neutralny
 * kontekst, nie argument.
 */

export type Sygnal = {
  id: string;
  /** Krótki glif identyfikujący sygnał (XI ↑ ◎ ✓ …). */
  znak: string;
  label: string;
  opis: ReactNode;
  ton: "brand" | "amber" | "czerwony" | "cichy";
};

const TON_KAFELKA: Record<Sygnal["ton"], { znak: string; aktywny: string }> = {
  brand: {
    znak: "text-brand",
    aktywny: "border-brand/45 bg-brand-wash text-brand-deep",
  },
  amber: {
    znak: "text-data-amber-ink",
    aktywny: "border-data-amber/60 bg-data-amber-wash text-data-amber-ink",
  },
  czerwony: {
    znak: "text-data-red-ink",
    aktywny: "border-data-red/50 bg-data-red-wash text-data-red-ink",
  },
  cichy: {
    znak: "text-faint",
    aktywny: "border-hairline-strong bg-card-soft text-ink-soft",
  },
};

const TON_KRESKA: Record<Sygnal["ton"], string> = {
  brand: "border-brand-bright",
  amber: "border-data-amber",
  czerwony: "border-data-red",
  cichy: "border-hairline-strong",
};

export function Sygnaly({
  naglowek,
  sygnaly,
}: {
  naglowek: ReactNode;
  sygnaly: Sygnal[];
}) {
  // pierwszy sygnał otwarty od wejścia — sekcja mówi bez klikania
  const [otwarty, setOtwarty] = useState<string | null>(
    sygnaly[0]?.id ?? null,
  );
  const reduced = useReducedMotion();
  if (sygnaly.length === 0) return null;
  const aktywny = sygnaly.find((s) => s.id === otwarty) ?? null;

  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
        {naglowek}
      </h4>
      <div className="flex flex-wrap items-center gap-1.5">
        {sygnaly.map((s) => {
          const ton = TON_KAFELKA[s.ton];
          const jestOtwarty = otwarty === s.id;
          return (
            <button
              key={s.id}
              type="button"
              aria-expanded={jestOtwarty}
              title={jestOtwarty ? undefined : "Kliknij po wyjaśnienie"}
              onClick={() => setOtwarty(jestOtwarty ? null : s.id)}
              className={`inline-flex items-center gap-1.5 rounded-(--radius-control) border px-2.5 py-1.5 text-[13px] font-medium transition-colors ${
                jestOtwarty
                  ? ton.aktywny
                  : s.ton === "cichy"
                    ? "border-hairline text-faint hover:border-hairline-strong hover:text-ink-soft"
                    : "border-hairline text-ink-soft hover:border-brand/40 hover:text-ink"
              }`}
            >
              <span aria-hidden className={`font-data ${ton.znak}`}>
                {s.znak}
              </span>
              {s.label}
            </button>
          );
        })}
      </div>
      <AnimatePresence initial={false}>
        {aktywny && (
          <motion.div
            key={aktywny.id}
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.25, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <p
              className={`mt-2.5 max-w-prose border-l-2 pl-3 text-sm leading-relaxed text-ink-soft ${TON_KRESKA[aktywny.ton]}`}
            >
              {aktywny.opis}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
