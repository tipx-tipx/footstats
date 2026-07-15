"use client";

import { useMemo, useState } from "react";

import type { SkutecznoscDnia } from "@/lib/types";

/**
 * Kalendarz wyników — widok miesiąca dzień po dniu (wzorzec zaufania:
 * codzienny bilans w jednostkach, nic nie znika). Server component nie
 * wystarczy: przełącznik miesięcy. Komponent samowystarczalny — do
 * ponownego użycia na przyszłym landingu bez zmian.
 *
 * ROI dnia = roi_flat (stawka 1 j. na okazję), kolor: zysk/strata/zero.
 * Dni bez rozliczonych typów są puste (nie mylić z zerem).
 */

const DNI_TYGODNIA = ["pn", "wt", "śr", "cz", "pt", "so", "nd"];
const MIESIACE = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];

function fmtU(v: number): string {
  const s = v.toFixed(2).replace(".", ",").replace(/,?0+$/, "");
  return `${v > 0 ? "+" : ""}${s === "" || s === "-" ? "0" : s}u`;
}

/** "YYYY-MM-DD" → [rok, miesiąc 0-11, dzień] bez pułapek stref czasowych. */
function rozbijDate(dzien: string): [number, number, number] {
  const [r, m, d] = dzien.split("-").map(Number);
  return [r, m - 1, d];
}

export function KalendarzWynikow({ dni }: { dni: SkutecznoscDnia[] }) {
  // mapa dzień → dane + lista miesięcy (rok*12+m) obecnych w danych
  const { mapa, miesiace } = useMemo(() => {
    const mapa = new Map<string, SkutecznoscDnia>();
    const zbior = new Set<number>();
    for (const d of dni) {
      if (d.rozliczone > 0) {
        mapa.set(d.dzien, d);
        const [r, m] = rozbijDate(d.dzien);
        zbior.add(r * 12 + m);
      }
    }
    return { mapa, miesiace: [...zbior].sort((a, b) => a - b) };
  }, [dni]);

  const [widok, setWidok] = useState<number | null>(
    () => miesiace[miesiace.length - 1] ?? null,
  );

  if (widok == null || mapa.size === 0) return null;

  const rok = Math.floor(widok / 12);
  const mies = widok % 12;
  const dniWMiesiacu = new Date(rok, mies + 1, 0).getDate();
  // poniedziałek = 0 (getDay: niedziela = 0)
  const start = (new Date(rok, mies, 1).getDay() + 6) % 7;

  // bilans miesiąca
  let bilans = 0;
  let rozliczonych = 0;
  for (const [dzien, d] of mapa) {
    const [r, m] = rozbijDate(dzien);
    if (r === rok && m === mies) {
      bilans += d.roi_flat;
      rozliczonych += d.rozliczone;
    }
  }

  const idx = miesiace.indexOf(widok);

  const komorki: (SkutecznoscDnia | null | "pusta")[] = [
    ...Array<"pusta">(start).fill("pusta"),
    ...Array.from({ length: dniWMiesiacu }, (_, i) => {
      const klucz = `${rok}-${String(mies + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
      return mapa.get(klucz) ?? null;
    }),
  ];

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => idx > 0 && setWidok(miesiace[idx - 1])}
            disabled={idx <= 0}
            aria-label="Poprzedni miesiąc"
            className="flex h-8 w-8 items-center justify-center rounded-(--radius-control) border border-hairline text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-default disabled:opacity-35 disabled:hover:border-hairline disabled:hover:text-ink-soft"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
              <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <h3 className="font-display min-w-36 text-center text-base font-bold capitalize">
            {MIESIACE[mies]} {rok}
          </h3>
          <button
            onClick={() => idx < miesiace.length - 1 && setWidok(miesiace[idx + 1])}
            disabled={idx >= miesiace.length - 1}
            aria-label="Następny miesiąc"
            className="flex h-8 w-8 items-center justify-center rounded-(--radius-control) border border-hairline text-ink-soft transition-colors hover:border-brand hover:text-brand disabled:cursor-default disabled:opacity-35 disabled:hover:border-hairline disabled:hover:text-ink-soft"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden>
              <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <p className="text-xs text-faint">
          bilans miesiąca:{" "}
          <span
            className={`font-data text-sm font-semibold ${
              bilans > 0
                ? "text-data-green"
                : bilans < 0
                  ? "text-data-red-ink"
                  : "text-ink-soft"
            }`}
          >
            {fmtU(bilans)}
          </span>{" "}
          · {rozliczonych} rozliczonych (stawka 1 j. na typ)
        </p>
      </div>

      <div className="grid grid-cols-7 gap-1.5">
        {DNI_TYGODNIA.map((d) => (
          <span
            key={d}
            className="pb-1 text-center text-[10px] font-semibold uppercase tracking-wide text-faint"
          >
            {d}
          </span>
        ))}
        {komorki.map((k, i) => {
          if (k === "pusta") return <span key={`p-${i}`} aria-hidden />;
          const nrDnia = i - start + 1;
          if (k === null) {
            return (
              <span
                key={i}
                className="flex aspect-square flex-col items-center justify-center rounded-(--radius-control) border border-hairline/60 text-xs text-faint/60"
                title="Brak rozliczonych typów tego dnia"
              >
                {nrDnia}
              </span>
            );
          }
          const zysk = k.roi_flat > 0.005;
          const strata = k.roi_flat < -0.005;
          return (
            <span
              key={i}
              title={`${k.dzien}: ${k.trafione}/${k.rozliczone} trafionych · bilans ${fmtU(k.roi_flat)}`}
              className={`flex aspect-square flex-col items-center justify-center gap-0.5 rounded-(--radius-control) border text-xs ${
                zysk
                  ? "border-data-green/30 bg-data-green-wash text-data-green-ink"
                  : strata
                    ? "border-data-red/25 bg-data-red-wash text-data-red-ink"
                    : "border-hairline bg-card-soft text-ink-soft"
              }`}
            >
              <span className="text-[10px] opacity-70">{nrDnia}</span>
              <span className="font-data text-[11px] font-semibold leading-none">
                {fmtU(k.roi_flat)}
              </span>
              <span className="font-data text-[9px] opacity-70">
                {k.trafione}/{k.rozliczone}
              </span>
            </span>
          );
        })}
      </div>

      <p className="mt-3 text-[11px] leading-relaxed text-faint">
        Każdy dzień zostaje w kalendarzu — także stratny. Puste pola = brak
        rozliczonych typów.
      </p>
    </div>
  );
}
