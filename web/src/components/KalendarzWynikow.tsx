"use client";

import { useMemo, useState } from "react";

import { fmtU } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";
import { OSTATNIA_ZMIANA, poZmianie } from "@/lib/zmiany";

/**
 * Kalendarz wyników — mapa miesiąca: bilans każdego dnia w jednostkach stawki.
 *
 * Kafelek niesie DWIE rzeczy (numer dnia + bilans), nie trzy. Trafienia,
 * typy i CLV pokazuje panel dnia po kliknięciu — na kwadracie 40 px trzecia
 * liczba i tak zlewała się w plamę, a na telefonie była nieczytelna.
 *
 * Wybór produktu (zawodnicy / drużyny / drabinki) NIE należy do tego
 * komponentu: filtr jest jeden na całą stronę, a kalendarz dostaje już
 * przefiltrowane dni. Wcześniej ten sam przełącznik stał w dwóch miejscach
 * z niezależnym stanem i mylił bardziej niż pomagał.
 */

const DNI_TYGODNIA = ["pn", "wt", "śr", "cz", "pt", "so", "nd"];
const MIESIACE = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];

/** "YYYY-MM-DD" → [rok, miesiąc 0-11, dzień] bez pułapek stref czasowych. */
function rozbijDate(dzien: string): [number, number, number] {
  const [r, m, d] = dzien.split("-").map(Number);
  return [r, m - 1, d];
}

export function KalendarzWynikow({
  dni,
  wszystkieDni,
  wybrany,
  onWybierz,
}: {
  /** dni PO filtrze produktu — to one rysują kafelki */
  dni: SkutecznoscDnia[];
  /** pełny zbiór dni — wyznacza dostępne miesiące, żeby filtr nie zabierał
   *  strzałek nawigacji */
  wszystkieDni?: SkutecznoscDnia[];
  wybrany?: string | null;
  onWybierz?: (dzien: string) => void;
}) {
  const mapa = useMemo(() => {
    const m = new Map<string, SkutecznoscDnia>();
    for (const d of dni) if (d.rozliczone > 0) m.set(d.dzien, d);
    return m;
  }, [dni]);

  const miesiace = useMemo(() => {
    const zbior = new Set<number>();
    for (const d of wszystkieDni ?? dni) {
      if (d.rozliczone > 0) {
        const [r, m] = rozbijDate(d.dzien);
        zbior.add(r * 12 + m);
      }
    }
    return [...zbior].sort((a, b) => a - b);
  }, [wszystkieDni, dni]);

  const [widok, setWidok] = useState<number | null>(
    () => miesiace[miesiace.length - 1] ?? null,
  );

  if (widok == null || miesiace.length === 0) return null;

  const rok = Math.floor(widok / 12);
  const mies = widok % 12;
  const dniWMiesiacu = new Date(rok, mies + 1, 0).getDate();
  // poniedziałek = 0 (getDay: niedziela = 0)
  const start = (new Date(rok, mies, 1).getDay() + 6) % 7;

  const miesieczne = [...mapa.values()].filter((d) => {
    const [r, m] = rozbijDate(d.dzien);
    return r === rok && m === mies;
  });
  const bilans = miesieczne.reduce((s, d) => s + d.roi_flat, 0);
  const rozliczonych = miesieczne.reduce((s, d) => s + d.rozliczone, 0);

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
          · {rozliczonych} rozliczonych
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
          const swiezy = poZmianie(k.dzien);
          const aktywny = wybrany === k.dzien;
          return (
            <button
              key={i}
              onClick={() => onWybierz?.(k.dzien)}
              aria-pressed={aktywny}
              title={`${k.dzien}: ${k.trafione}/${k.rozliczone} trafionych · bilans ${fmtU(k.roi_flat)}${
                swiezy ? "" : " · stare zasady selekcji"
              } — kliknij, żeby zobaczyć typy`}
              className={`flex aspect-square flex-col items-center justify-center gap-1 rounded-(--radius-control) border text-xs transition-transform hover:scale-[1.06] ${
                zysk
                  ? "border-data-green/30 bg-data-green-wash text-data-green-ink"
                  : strata
                    ? "border-data-red/25 bg-data-red-wash text-data-red-ink"
                    : "border-hairline bg-card-soft text-ink-soft"
              } ${swiezy ? "" : "opacity-55"} ${
                aktywny ? "ring-2 ring-brand ring-offset-1 ring-offset-card" : ""
              }`}
            >
              <span className="text-[10px] opacity-70">{nrDnia}</span>
              <span className="font-data text-[11px] font-semibold leading-none">
                {fmtU(k.roi_flat)}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mt-3 space-y-1.5 text-[11px] leading-relaxed text-faint">
        <p>
          Kliknij dzień, żeby zobaczyć jego typy. Puste pola = brak rozliczeń;
          każdy dzień zostaje w kalendarzu, także stratny.
        </p>
        {OSTATNIA_ZMIANA && (
          <p>
            <span
              aria-hidden
              className="mr-1.5 inline-block h-2.5 w-2.5 rounded-[3px] border border-hairline bg-card-soft align-[-1px] opacity-55"
            />
            Wyblakłe dni są sprzed{" "}
            {new Date(`${OSTATNIA_ZMIANA.od}T12:00:00`).toLocaleDateString(
              "pl-PL",
              { day: "numeric", month: "long" },
            )}
            , czyli sprzed zmiany zasad selekcji — opisują model, którego już
            nie ma w produkcji.
          </p>
        )}
      </div>
    </div>
  );
}
