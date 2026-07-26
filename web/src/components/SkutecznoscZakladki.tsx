"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

/**
 * Zakładki zamiast siedmiu sekcji jedna pod drugą.
 *
 * Strona kontroli jakości puchła przez dokładanie kolejnych dowodów: typy,
 * kalendarz, strumienie, kupony, kronika wygranych, kalibracja. Każda z tych
 * rzeczy jest potrzebna, ale nie NARAZ — czytelnik przewijał półtora ekranu,
 * zanim trafił na to, po co przyszedł. Panele przychodzą gotowe z serwera
 * (renderowane jako `panel`), więc przełączanie jest natychmiastowe i nie
 * kosztuje ani jednego zapytania.
 */
export interface Zakladka {
  id: string;
  label: string;
  /** krótka liczba przy nazwie — od razu widać, gdzie w ogóle są dane */
  licznik?: string;
  panel: React.ReactNode;
}

export function SkutecznoscZakladki({ zakladki }: { zakladki: Zakladka[] }) {
  const [aktywna, setAktywna] = useState(zakladki[0]?.id);
  const reduced = useReducedMotion();
  const wybrana = zakladki.find((z) => z.id === aktywna) ?? zakladki[0];
  if (!wybrana) return null;

  return (
    <div>
      {/* pasek zakładek: przewijalny w poziomie na wąskich ekranach, żeby
          nigdy nie zawijał się w dwie linie i nie skakał układem */}
      <div
        role="tablist"
        aria-label="Sekcje skuteczności"
        className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1"
      >
        {zakladki.map((z) => {
          const active = z.id === wybrana.id;
          return (
            <button
              key={z.id}
              role="tab"
              id={`zakladka-${z.id}`}
              aria-selected={active}
              aria-controls={`panel-${z.id}`}
              onClick={() => setAktywna(z.id)}
              className={`relative shrink-0 rounded-(--radius-control) px-3.5 py-2 text-sm transition-colors ${
                active
                  ? "font-semibold text-brand-deep"
                  : "text-muted hover:bg-paper hover:text-ink"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="pastylka-skutecznosc"
                  aria-hidden
                  transition={
                    reduced
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 520, damping: 42 }
                  }
                  className="absolute inset-0 rounded-(--radius-control) bg-brand-wash"
                />
              )}
              <span className="relative whitespace-nowrap">
                {z.label}
                {z.licznik && (
                  <span
                    className={`font-data ml-1.5 text-xs ${
                      active ? "text-brand" : "text-faint"
                    }`}
                  >
                    {z.licznik}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`panel-${wybrana.id}`}
        aria-labelledby={`zakladka-${wybrana.id}`}
        className="mt-5"
      >
        {wybrana.panel}
      </div>
    </div>
  );
}
