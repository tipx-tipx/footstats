"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type OpcjaFiltra = { value: string; label: string; n?: number };

/**
 * Dopracowany wybór z listą (zamiast natywnego selecta, którego nie da
 * się ostylować): podkreślenie rośnie od lewej przy hoverze/otwarciu,
 * panel wjeżdża z animacją, wybrana opcja ma znacznik, liczniki po
 * prawej. Klawiatura: Enter/spacja otwiera, strzałki chodzą po liście,
 * Esc zamyka i wraca na przycisk.
 */
export function FilterDropdown({
  label,
  value,
  options,
  onChange,
  className = "",
}: {
  label: string;
  value: string;
  options: OpcjaFiltra[];
  onChange: (v: string) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  // panel jest szerszy od przycisku (w-max); przy prawej kolumnie na wąskim
  // ekranie wyjeżdżałby poza viewport — wtedy dosuwamy go do prawej
  const [odPrawej, setOdPrawej] = useState(false);
  const kontener = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLUListElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  useLayoutEffect(() => {
    if (!open || !panel.current || !kontener.current) return;
    const lewa = kontener.current.getBoundingClientRect().left;
    const szer = panel.current.offsetWidth;
    setOdPrawej(lewa + szer > document.documentElement.clientWidth - 8);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const klik = (e: PointerEvent) => {
      if (!kontener.current?.contains(e.target as Node)) setOpen(false);
    };
    const klawisz = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", klik);
    document.addEventListener("keydown", klawisz);
    return () => {
      document.removeEventListener("pointerdown", klik);
      document.removeEventListener("keydown", klawisz);
    };
  }, [open]);

  const wybrana = options.find((o) => o.value === value);
  const przesunFokus = (kierunek: 1 | -1) => {
    const przyciski = Array.from(
      panel.current?.querySelectorAll("button") ?? [],
    );
    if (przyciski.length === 0) return;
    const i = przyciski.indexOf(document.activeElement as HTMLButtonElement);
    przyciski[(i + kierunek + przyciski.length) % przyciski.length]?.focus();
  };

  return (
    <div ref={kontener} className={`relative min-w-0 ${className}`}>
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && open) {
            e.preventDefault();
            przesunFokus(1);
          }
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="group flex w-full flex-col items-start gap-1 text-left"
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
          {label}
        </span>
        <span className="relative flex w-full items-center justify-between gap-2 pb-1.5">
          <span className="truncate text-sm font-medium text-ink">
            {wybrana?.label ?? "–"}
            {wybrana?.n != null && (
              <span className="font-data text-xs text-faint"> ({wybrana.n})</span>
            )}
          </span>
          <svg
            aria-hidden
            width="12"
            height="12"
            viewBox="0 0 14 14"
            className={`shrink-0 transition-transform duration-200 ${
              open ? "rotate-180 text-brand" : "text-faint"
            }`}
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
          {/* podkreślenie: baza hairline + linia brand rosnąca od lewej */}
          <span aria-hidden className="absolute inset-x-0 bottom-0 h-px bg-hairline" />
          <span
            aria-hidden
            className={`absolute inset-x-0 bottom-0 h-px origin-left bg-brand transition-transform duration-300 ${
              open ? "scale-x-100" : "scale-x-0 group-hover:scale-x-100"
            }`}
          />
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.ul
            ref={panel}
            role="listbox"
            aria-label={label}
            initial={{ opacity: 0, y: -6, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.99 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                przesunFokus(1);
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                przesunFokus(-1);
              }
            }}
            className={`absolute top-full z-30 mt-2 max-h-80 w-max min-w-full max-w-[calc(100vw-2rem)] overflow-auto rounded-xl border border-hairline bg-card py-1.5 shadow-(--shadow-pop) ${
              odPrawej ? "right-0" : "left-0"
            }`}
          >
            {options.map((o) => {
              const aktywna = o.value === value;
              return (
                <li key={o.value}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={aktywna}
                    onClick={() => {
                      onChange(o.value);
                      setOpen(false);
                      trigger.current?.focus();
                    }}
                    className={`flex w-full items-center justify-between gap-6 px-3.5 py-2 text-left text-sm transition-colors hover:bg-brand-wash ${
                      aktywna ? "font-medium text-brand-deep" : "text-ink"
                    }`}
                  >
                    <span className="truncate">{o.label}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      {o.n != null && (
                        <span className="font-data text-xs text-faint">{o.n}</span>
                      )}
                      {aktywna && (
                        <svg
                          aria-hidden
                          width="12"
                          height="12"
                          viewBox="0 0 14 14"
                          className="text-brand"
                        >
                          <path
                            d="M2.5 7.5 L5.5 10.5 L11.5 3.5"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
