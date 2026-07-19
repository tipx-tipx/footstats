"use client";

import { motion, useReducedMotion } from "framer-motion";

/**
 * Segmentowany przełącznik w języku produktu: aktywna opcja to pastylka,
 * która PŁYNIE między pozycjami (layoutId, jak w nawigacji), zamiast
 * skakać. Jeden wygląd dla charakteru kuponów, trybu liczby typów itd.
 */
export function Segmented<T extends string>({
  id,
  opcje,
  wartosc,
  onChange,
  disabled,
}: {
  /** unikalny w obrębie strony — spina layoutId pastylki */
  id: string;
  opcje: { kod: T; label: string; title?: string }[];
  wartosc: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  const reduced = useReducedMotion();
  return (
    <div
      role="radiogroup"
      className="inline-flex max-w-full flex-wrap rounded-(--radius-control) border border-hairline bg-paper p-0.5"
    >
      {opcje.map((o) => {
        const active = wartosc === o.kod;
        return (
          <button
            key={o.kod}
            role="radio"
            aria-checked={active}
            disabled={disabled}
            title={o.title}
            onClick={() => onChange(o.kod)}
            className={`relative rounded-lg px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed ${
              active
                ? "font-semibold text-ink"
                : "font-medium text-muted hover:text-ink"
            }`}
          >
            {active && (
              <motion.span
                layoutId={`segmented-${id}`}
                aria-hidden
                transition={
                  reduced
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 520, damping: 42 }
                }
                className="absolute inset-0 rounded-lg bg-card shadow-(--shadow-card)"
              />
            )}
            <span className="relative">{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}
