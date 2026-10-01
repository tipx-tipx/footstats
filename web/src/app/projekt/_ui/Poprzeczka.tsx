"use client";

import { fmtLinia } from "@/lib/format";

/**
 * „Poprzeczka” – ostatnie mecze zawodnika jako kropki połączone linią
 * (ten sam znak co wykres w logo), na tle linii bukmachera. Kropka pełna =
 * mecz ponad linią, pusta = pod. Jedno spojrzenie mówi to, co dziś wymaga
 * rozwinięcia karty i przeczytania tabelki.
 */
export function Poprzeczka({
  historia,
  rywale,
  linia,
  strona,
}: {
  historia: number[];
  rywale: string[];
  linia: number;
  strona: string;
}) {
  const W = 300;
  const H = 68;
  const gora = 7;
  const dol = 46;
  const max = Math.max(linia + 1, ...historia);
  const y = (v: number) => dol - (v / max) * (dol - gora);
  const krok = W / historia.length;
  const x = (i: number) => krok * i + krok / 2;
  const trafione = historia.filter((v) => (strona === "ponizej" ? v < linia : v > linia)).length;
  const punkty = historia.map((v, i) => `${x(i)},${y(v)}`).join(" ");

  return (
    <div className="p-poprzeczka">
      <div className="p-poprzeczka-opis">
        <span>
          ostatnie {historia.length} meczów · linia {fmtLinia(linia)}
        </span>
        <span>
          <b>{trafione}</b> z {historia.length} {strona === "ponizej" ? "pod linią" : "ponad linią"}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${trafione} z ${historia.length} meczów ponad linią`}>
        <line className="p-pp-linia" x1="0" x2={W} y1={y(linia)} y2={y(linia)} />
        <polyline className="p-pp-trasa" points={punkty} pathLength={1} />
        {historia.map((v, i) => {
          const ponad = strona === "ponizej" ? v < linia : v > linia;
          return (
            <g key={i}>
              <circle
                className={`p-pp-kropka ${ponad ? "p-pp-ponad" : "p-pp-pod"}`}
                style={{ ["--i" as string]: i }}
                cx={x(i)}
                cy={y(v)}
                r={ponad ? 4.2 : 3.6}
              >
                <title>{`${rywale[i] ?? "mecz"}: ${v}`}</title>
              </circle>
              <text className="p-pp-liczba" x={x(i)} y={H - 3}>
                {v}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
