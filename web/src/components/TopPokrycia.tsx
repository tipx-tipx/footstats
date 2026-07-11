"use client";

import { useMemo, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import {
  RYNEK_LABEL,
  type GraForma,
  type WierszPokrycia,
} from "@/lib/pokrycie";

const LIMIT = 50;

type Tip = { x: number; y: number; g: GraForma } | null;

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-brand text-white"
          : "bg-card text-muted hover:bg-paper hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

export function TopPokrycia({
  wiersze,
  druzyny,
}: {
  wiersze: WierszPokrycia[];
  /** [gospodarz, gość] — do filtra drużyn */
  druzyny: [string, string];
}) {
  const [druzyna, setDruzyna] = useState<string | null>(null);
  const [rynek, setRynek] = useState<string | null>(null);
  const [rozwin, setRozwin] = useState(false);
  const [tip, setTip] = useState<Tip>(null);

  const rynki = useMemo(() => {
    const obecne = new Set(wiersze.map((w) => w.rynek_kod));
    return Object.keys(RYNEK_LABEL).filter((k) => obecne.has(k));
  }, [wiersze]);

  const widoczne = useMemo(
    () =>
      wiersze.filter(
        (w) =>
          (druzyna === null || w.druzyna === druzyna) &&
          (rynek === null || w.rynek_kod === rynek),
      ),
    [wiersze, druzyna, rynek],
  );
  const pokazane = rozwin ? widoczne : widoczne.slice(0, LIMIT);

  if (wiersze.length === 0) {
    return (
      <p className="mt-5 rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Brak zawodników z pokryciem w ostatnich 5 startach — pojawią się, gdy
        zbierze się dość historii (albo po ogłoszeniu składów).
      </p>
    );
  }

  const boks = (g: GraForma, prog: number, key: number) => {
    const pokryl = g.v >= prog;
    return (
      <span
        key={key}
        onMouseEnter={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setTip({ x: r.left + r.width / 2, y: r.top, g });
        }}
        onMouseLeave={() => setTip(null)}
        className={`font-data inline-flex h-6 w-6 cursor-default items-center justify-center rounded text-[11px] font-semibold text-white transition-transform hover:scale-110 ${
          pokryl ? "bg-data-green" : "bg-data-red"
        }`}
      >
        {g.v}
      </span>
    );
  };

  return (
    <div className="mt-5">
      {/* legenda */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3.5 w-3.5 rounded bg-data-green" />
          pokrył linię
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-3.5 w-3.5 rounded bg-data-red" />
          nie pokrył
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded bg-brand-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-brand-deep">
            XI
          </span>
          przewidywany skład (na górze)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded bg-data-amber-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#8a5613]">
            rzadko w kadrze
          </span>
          forma z klubu, nie z reprezentacji (niżej)
        </span>
      </div>

      {/* filtry */}
      <div className="mt-3 flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] uppercase tracking-wide text-faint">
            drużyna
          </span>
          <Chip active={druzyna === null} onClick={() => setDruzyna(null)}>
            wszyscy
          </Chip>
          {druzyny.map((d) => (
            <Chip
              key={d}
              active={druzyna === d}
              onClick={() => setDruzyna(druzyna === d ? null : d)}
            >
              {d}
            </Chip>
          ))}
        </div>
        {rynki.length > 1 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[11px] uppercase tracking-wide text-faint">
              rynek
            </span>
            <Chip active={rynek === null} onClick={() => setRynek(null)}>
              wszystkie
            </Chip>
            {rynki.map((k) => (
              <Chip
                key={k}
                active={rynek === k}
                onClick={() => setRynek(rynek === k ? null : k)}
              >
                {RYNEK_LABEL[k]}
              </Chip>
            ))}
          </div>
        )}
      </div>

      {/* tabela */}
      <div className="mt-3 overflow-x-auto rounded-2xl border border-hairline bg-card shadow-(--shadow-card)">
        <table className="w-full min-w-[680px] text-sm">
          <thead>
            <tr className="border-b border-hairline text-left text-[11px] uppercase tracking-wide text-faint">
              <th className="px-4 py-2.5 font-medium">rynek</th>
              <th className="px-4 py-2.5 font-medium">zawodnik</th>
              <th className="px-4 py-2.5 font-medium">ostatnie 5 startów</th>
              <th className="px-4 py-2.5 font-medium">pokrycie</th>
              <th className="px-4 py-2.5 font-medium">linia</th>
              <th className="px-4 py-2.5 text-right font-medium">Superbet</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {pokazane.map((w, i) => (
              <tr
                key={`${w.player_id}-${w.rynek_kod}-${w.linia}-${i}`}
                className="transition-colors hover:bg-paper/50"
              >
                <td className="whitespace-nowrap px-4 py-3 font-medium">
                  {w.rynek}
                </td>
                <td className="px-4 py-3">
                  {w.xi && (
                    <span
                      className="mr-2 inline-flex rounded bg-brand-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-brand-deep"
                      title="W przewidywanym pierwszym składzie"
                    >
                      XI
                    </span>
                  )}
                  <span className="font-medium">{w.zawodnik}</span>
                  <span className="ml-1.5 text-xs text-faint">{w.druzyna}</span>
                  {!w.xi && w.kadraLiczba <= 1 && (
                    <span
                      className="ml-2 inline-flex rounded bg-data-amber-wash px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-[#8a5613]"
                      title="Ostatnie starty głównie w klubie, nie w reprezentacji — w kadrze gra rzadko, może nie wejść do składu. Statystyki to forma klubowa."
                    >
                      rzadko w kadrze
                    </span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className="flex gap-1">
                    {w.ostatnie.map((g, gi) => boks(g, w.prog, gi))}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`font-data font-semibold ${
                      w.pokryte === w.probka
                        ? "text-data-green"
                        : "text-brand-deep"
                    }`}
                  >
                    {w.pokryte}/{w.probka}
                  </span>
                </td>
                <td className="font-data whitespace-nowrap px-4 py-3">
                  +{fmtLinia(w.linia)}
                </td>
                <td className="font-data px-4 py-3 text-right">
                  {w.kurs != null ? (
                    <span className="font-semibold">{fmtKurs(w.kurs)}</span>
                  ) : (
                    <span className="text-faint">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-faint">
          {widoczne.length}{" "}
          {widoczne.length === 1 ? "propozycja" : "propozycji"}
          {!rozwin &&
            widoczne.length > LIMIT &&
            ` · na górze regularni w kadrze, rezerwa niżej`}
        </p>
        {widoczne.length > LIMIT && (
          <button
            onClick={() => setRozwin((v) => !v)}
            className="rounded-lg border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-paper hover:text-ink"
          >
            {rozwin
              ? "Zwiń listę"
              : `Pokaż pozostałe (${widoczne.length - LIMIT})`}
          </button>
        )}
      </div>

      {/* płynny tooltip kafelka (fixed — nigdy nieprzycięty przez tabelę) */}
      <div
        aria-hidden
        className={`pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-full rounded-lg bg-ink px-2.5 py-1.5 text-white shadow-lg transition-all duration-150 ease-out ${
          tip ? "opacity-100" : "translate-y-[calc(-100%+4px)] opacity-0"
        }`}
        style={
          tip
            ? { left: tip.x, top: tip.y - 8 }
            : { left: -9999, top: -9999 }
        }
      >
        {tip && (
          <>
            <span className="block text-[11px] font-semibold">
              {tip.g.rywal ? `vs ${tip.g.rywal}` : "mecz"}
            </span>
            <span className="block text-[10px] text-white/70">
              {tip.g.minuty}′ · {tip.g.kadra ? "reprezentacja" : "klub"}
            </span>
            <span className="absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1 rotate-45 bg-ink" />
          </>
        )}
      </div>
    </div>
  );
}
