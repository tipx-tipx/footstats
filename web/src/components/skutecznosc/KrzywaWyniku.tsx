"use client";

import { useBilans } from "../useBilans";
import type { SkutecznoscDnia } from "@/lib/types";
import { OSTATNIA_ZMIANA } from "@/lib/zmiany";

/**
 * KRZYWA WYNIKU — narastający bilans dzień po dniu.
 *
 * Kalendarz odpowiada „jak było w piątek". Nie odpowiada na pytanie, po które
 * się tu wchodzi: czy to w ogóle idzie w dobrą stronę. Siedem zielonych
 * kafelków rozsypanych między dwunastoma czerwonymi nie układa się w głowie
 * w żaden trend — krzywa układa się w jeden rzut oka.
 *
 * Pionowa kreska w dniu zmiany zasad selekcji dzieli wykres na „to był inny
 * model" i „to jest ten, który dziś gra". Za dwa tygodnie ta kreska odpowie,
 * czy zaostrzenie bram cokolwiek dało — kalendarz tego nie pokaże nigdy.
 */

const W = 640;
// Wyższy wykres od 2026-07-27: krzywa stoi w siatce obok kalendarza, który
// jest dwa razy wyższy — przy 150 px zostawała pod nią pusta kolumna. Przy
// okazji łagodne spadki są w ogóle widoczne, a nie zlane w płaską kreskę.
const H = 260;
const M = { gora: 12, dol: 20, lewo: 4, prawo: 4 };

export function KrzywaWyniku({
  dni,
  pelnyWglad = true,
}: {
  dni: SkutecznoscDnia[];
  /** false = widok klienta: bilans w złotówkach zamiast jednostek stawki */
  pelnyWglad?: boolean;
}) {
  const { bilans } = useBilans(pelnyWglad);
  // dni przychodzą najnowszy pierwszy — krzywa idzie od najstarszego
  const rosnaco = [...dni]
    .filter((d) => d.rozliczone > 0)
    .sort((a, b) => a.dzien.localeCompare(b.dzien));
  if (rosnaco.length < 2) return null;

  let suma = 0;
  const punkty = rosnaco.map((d) => {
    suma += d.roi_flat;
    return { dzien: d.dzien, wartosc: suma };
  });

  const wartosci = punkty.map((p) => p.wartosc);
  const maks = Math.max(0, ...wartosci);
  const min = Math.min(0, ...wartosci);
  const rozpietosc = maks - min || 1;

  const x = (i: number) =>
    M.lewo + (i / (punkty.length - 1)) * (W - M.lewo - M.prawo);
  const y = (v: number) =>
    M.gora + ((maks - v) / rozpietosc) * (H - M.gora - M.dol);

  const linia = punkty.map((p, i) => `${x(i)},${y(p.wartosc)}`).join(" ");
  const powierzchnia = `${M.lewo},${y(0)} ${linia} ${x(punkty.length - 1)},${y(0)}`;

  const koncowy = punkty[punkty.length - 1].wartosc;
  const dodatni = koncowy >= 0;
  const kolor = dodatni ? "var(--color-data-green)" : "var(--color-data-red)";

  // kreska zmiany zasad — między ostatnim dniem starych i pierwszym nowych
  const odKiedy = OSTATNIA_ZMIANA?.od;
  const iZmiany = odKiedy
    ? punkty.findIndex((p) => p.dzien >= odKiedy)
    : -1;
  const xZmiany = iZmiany > 0 ? (x(iZmiany) + x(iZmiany - 1)) / 2 : null;

  const etykietaDnia = (dzien: string) => {
    const [, m, d] = dzien.split("-");
    return `${Number(d)}.${m}`;
  };

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-base font-bold tracking-tight">Krzywa wyniku</h3>
        <p className="text-xs text-faint">
          narastająco od {etykietaDnia(punkty[0].dzien)} ·{" "}
          <span
            className={`font-data text-sm font-semibold ${
              dodatni ? "text-data-green" : "text-data-red"
            }`}
          >
            {bilans(koncowy)}
          </span>
        </p>
      </div>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="mt-3 w-full"
        style={{ height: "auto" }}
        role="img"
        aria-label={`Narastający bilans: ${bilans(koncowy)} po ${punkty.length} dniach z rozliczeniami`}
      >
        <defs>
          <linearGradient id="krzywa-wypelnienie" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={kolor} stopOpacity="0.22" />
            <stop offset="100%" stopColor={kolor} stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* linia zera — punkt odniesienia „ani zysku, ani straty" */}
        <line
          x1={M.lewo}
          x2={W - M.prawo}
          y1={y(0)}
          y2={y(0)}
          stroke="currentColor"
          className="text-hairline-strong"
          strokeWidth="1"
          strokeDasharray="3 4"
        />
        <text
          x={M.lewo + 2}
          y={y(0) - 4}
          className="fill-current text-[9px] text-faint"
        >
          0u
        </text>

        <polygon points={powierzchnia} fill="url(#krzywa-wypelnienie)" />
        <polyline
          points={linia}
          fill="none"
          stroke={kolor}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {xZmiany != null && (
          <>
            <line
              x1={xZmiany}
              x2={xZmiany}
              y1={M.gora - 6}
              y2={H - M.dol}
              stroke="currentColor"
              className="text-brand"
              strokeWidth="1.5"
              strokeDasharray="4 3"
            />
            <text
              x={Math.min(xZmiany + 5, W - 96)}
              y={M.gora}
              className="fill-current text-[9px] font-semibold text-brand"
            >
              {OSTATNIA_ZMIANA?.etykieta}
            </text>
          </>
        )}

        {/* punkt końcowy — gdzie jesteśmy dzisiaj */}
        <circle
          cx={x(punkty.length - 1)}
          cy={y(koncowy)}
          r="3.5"
          fill={kolor}
          stroke="var(--color-card)"
          strokeWidth="2"
        />

        <text
          x={M.lewo}
          y={H - 4}
          className="fill-current text-[9px] text-faint"
        >
          {etykietaDnia(punkty[0].dzien)}
        </text>
        <text
          x={W - M.prawo}
          y={H - 4}
          textAnchor="end"
          className="fill-current text-[9px] text-faint"
        >
          {etykietaDnia(punkty[punkty.length - 1].dzien)}
        </text>
      </svg>

      {xZmiany != null && (
        <p className="mt-1 text-[11px] leading-relaxed text-faint">
          Kreska to zmiana zasad selekcji. Wszystko na lewo opisuje model,
          którego już nie ma w produkcji — porównuj nachylenie po prawej,
          nie sam poziom.
        </p>
      )}
    </div>
  );
}
