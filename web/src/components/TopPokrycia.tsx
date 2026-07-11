"use client";

import { useMemo, useState } from "react";

import { fmtKurs, fmtLinia } from "@/lib/format";
import { RYNEK_LABEL, type WierszPokrycia } from "@/lib/pokrycie";

const LIMIT = 50;

/** Boks jednej gry: wartość + tooltip z rywalem, minutami i typem meczu. */
function Boks({ g, prog }: { g: WierszPokrycia["ostatnie"][number]; prog: number }) {
  const pokryl = g.v >= prog;
  const tytul = `${g.rywal ?? "mecz"} · ${g.minuty}′ · ${
    g.kadra ? "kadra" : "klub"
  } · ${pokryl ? "pokrył" : "nie pokrył"}`;
  return (
    <span
      title={tytul}
      className={`font-data inline-flex h-6 w-6 items-center justify-center rounded text-[11px] font-semibold text-white ${
        pokryl ? "bg-data-green" : "bg-data-red"
      }`}
    >
      {g.v}
    </span>
  );
}

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

  // rynki obecne w danych, w kolejności RYNEK_LABEL
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
  const pokazane = widoczne.slice(0, LIMIT);

  if (wiersze.length === 0) {
    return (
      <p className="mt-5 rounded-xl border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Brak zawodników z pokryciem ≥ 60% w ostatnich 5 meczach — pojawią się,
        gdy zbierze się dość historii (albo po ogłoszeniu składów).
      </p>
    );
  }

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
        <span className="text-faint">
          tylko mecze zaczynane w składzie (≥ 60 min) · najedź na boks, by
          zobaczyć rywala i minuty
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
              <th className="px-4 py-2.5 font-medium">ostatnie 5</th>
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
                  <span className="font-medium">{w.zawodnik}</span>
                  <span className="ml-1.5 text-xs text-faint">{w.druzyna}</span>
                </td>
                <td className="px-4 py-3">
                  <span className="flex gap-1">
                    {w.ostatnie.map((g, gi) => (
                      <Boks key={gi} g={g} prog={w.prog} />
                    ))}
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

      <p className="mt-2 text-xs text-faint">
        {widoczne.length > LIMIT
          ? `Pokazujemy top ${LIMIT} z ${widoczne.length} propozycji.`
          : `${widoczne.length} ${
              widoczne.length === 1 ? "propozycja" : "propozycji"
            }.`}
      </p>
    </div>
  );
}
