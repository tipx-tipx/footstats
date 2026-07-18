"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState, type ReactNode } from "react";

/**
 * Sygnaly — argumenty za typem w jednej linii, wyjaśnienie na klik.
 *
 * Zastępuje dawną listę „Przewagi tego typu", w której każdy sygnał leżał
 * na ekranie z pełnym opisem: sumarycznie ściana tekstu. Tu na ekranie są
 * tylko krótkie etykiety, a opis otwiera się pod linią dopiero po kliknięciu
 * (jeden naraz). Ton "cichy" = neutralny kontekst, nie argument.
 */

export type Sygnal = {
  id: string;
  /** Krótki glif identyfikujący sygnał (↑ ◎ ↗ ✓ ⚠ …). */
  znak: string;
  label: string;
  opis: ReactNode;
  ton: "brand" | "amber" | "czerwony" | "cichy";
};

const TON_PRZYCISK: Record<Sygnal["ton"], { znak: string; aktywny: string }> = {
  brand: { znak: "text-brand", aktywny: "bg-brand-wash text-brand-deep" },
  amber: {
    znak: "text-data-amber-ink",
    aktywny: "bg-data-amber-wash text-data-amber-ink",
  },
  czerwony: {
    znak: "text-data-red-ink",
    aktywny: "bg-data-red-wash text-data-red-ink",
  },
  cichy: { znak: "text-faint", aktywny: "bg-card-soft text-ink-soft" },
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
  const [otwarty, setOtwarty] = useState<string | null>(null);
  const reduced = useReducedMotion();
  if (sygnaly.length === 0) return null;
  const aktywny = sygnaly.find((s) => s.id === otwarty) ?? null;

  return (
    <div>
      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-faint">
        {naglowek}
      </h4>
      <div className="-ml-2 flex flex-wrap items-center gap-x-0.5 gap-y-1">
        {sygnaly.map((s) => {
          const ton = TON_PRZYCISK[s.ton];
          const jestOtwarty = otwarty === s.id;
          return (
            <button
              key={s.id}
              type="button"
              aria-expanded={jestOtwarty}
              title={jestOtwarty ? undefined : "Kliknij po wyjaśnienie"}
              onClick={() => setOtwarty(jestOtwarty ? null : s.id)}
              className={`inline-flex items-center gap-1.5 rounded-(--radius-control) px-2 py-1 text-[13px] font-medium transition-colors ${
                jestOtwarty
                  ? ton.aktywny
                  : s.ton === "cichy"
                    ? "text-faint hover:bg-card-soft hover:text-ink-soft"
                    : "text-ink-soft hover:bg-card-soft hover:text-ink"
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
              className={`mt-2 max-w-prose border-l-2 pl-3 text-sm leading-relaxed text-ink-soft ${TON_KRESKA[aktywny.ton]}`}
            >
              {aktywny.opis}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
