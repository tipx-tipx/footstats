"use client";

import { useMemo, useState } from "react";

import { fmtKurs } from "@/lib/format";
import {
  RYNEK_LABEL,
  type GraForma,
  type WierszPokrycia,
} from "@/lib/pokrycie";

const LIMIT = 40;

type Tip = { x: number; y: number; g: GraForma } | null;

function dataMeczu(ts: number): string {
  if (!ts) return "–";
  return new Intl.DateTimeFormat("pl-PL", {
    day: "numeric",
    month: "short",
  }).format(new Date(ts * 1000));
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
      className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "border-brand bg-brand text-on-brand shadow-(--shadow-card)"
          : "border-hairline bg-card text-muted hover:bg-card-soft hover:text-ink"
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
  const [bezKursu, setBezKursu] = useState(false);
  const [rozwin, setRozwin] = useState(false);
  const [tip, setTip] = useState<Tip>(null);

  // domyślnie chowamy rynki bez kursu Superbet (niecelne/zablokowane = „—")
  const zKursem = useMemo(
    () => (bezKursu ? wiersze : wiersze.filter((w) => w.maKurs)),
    [wiersze, bezKursu],
  );
  const rynki = useMemo(() => {
    const obecne = new Set(zKursem.map((w) => w.rynek_kod));
    return Object.keys(RYNEK_LABEL).filter((k) => obecne.has(k));
  }, [zKursem]);

  const widoczne = useMemo(
    () =>
      zKursem.filter(
        (w) =>
          (druzyna === null || w.druzyna === druzyna) &&
          (rynek === null || w.rynek_kod === rynek),
      ),
    [zKursem, druzyna, rynek],
  );
  const pokazane = rozwin ? widoczne : widoczne.slice(0, LIMIT);

  if (wiersze.length === 0) {
    return (
      <p className="mt-5 rounded-(--radius-card) border border-hairline bg-card px-4 py-3.5 text-sm text-muted shadow-(--shadow-card)">
        Brak zawodników z pokryciem w ostatnich 5 startach. Pojawią się, gdy
        zbierze się dość historii (albo po ogłoszeniu składów).
      </p>
    );
  }

  const boks = (g: GraForma, key: number) => {
    const zaliczyl = g.v >= 1;
    const opis = `${g.rywal ? `vs ${g.rywal}` : "mecz"}, ${dataMeczu(g.ts)}, ${g.minuty} minut, ${
      g.kadra ? "reprezentacja" : "klub"
    }`;
    const pokaz = (e: { currentTarget: HTMLElement }) => {
      const r = e.currentTarget.getBoundingClientRect();
      setTip({ x: r.left + r.width / 2, y: r.top, g });
    };
    return (
      <span
        key={key}
        tabIndex={0}
        aria-label={opis}
        onMouseEnter={pokaz}
        onMouseLeave={() => setTip(null)}
        onFocus={pokaz}
        onBlur={() => setTip(null)}
        // dotyk: tap pokazuje tooltip (mobile nie ma hover) — zostaje widoczny
        // do kolejnego tapnięcia gdzie indziej (proste, bez wyścigu ze
        // zdarzeniami mouseenter, które przeglądarki syntetyzują po dotyku)
        onClick={pokaz}
        className={`font-data inline-flex h-6 w-6 cursor-default items-center justify-center rounded-md text-[11px] font-semibold transition-transform hover:scale-110 ${
          zaliczyl
            ? "bg-data-green text-on-brand"
            : "border border-hairline-strong bg-card-soft text-muted"
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
        <span>
          Na górze <strong className="font-semibold text-ink">regularni w kadrze</strong>{" "}
          (pokrycie z reprezentacji).
        </span>
        <span className="flex items-center gap-1.5">
          <span className="rounded-full bg-data-amber-wash px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink">
            forma klubowa
          </span>
          rezerwa kadry, liczone z klubu (niżej)
        </span>
        <span className="text-faint">
          1+/2+/3+ = pokrycie linii · najedź na boks: rywal, minuty, data
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-data font-semibold text-data-green-ink">+%</span>
          <span>
            wartość: ile płaci kurs względem pokrycia (zgrubnie, próba 5;{" "}
            <span className="text-data-green-ink">zielony</span> = opłaca się,{" "}
            <span className="text-faint">szary</span> = znikomo)
          </span>
        </span>
      </div>

      {/* filtry */}
      <div className="mt-3.5 flex flex-col gap-2">
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
          <button
            onClick={() => setBezKursu((v) => !v)}
            className={`ml-1 whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              bezKursu
                ? "border-brand/40 bg-brand-wash text-brand-deep"
                : "border-hairline bg-card text-faint hover:bg-card-soft hover:text-ink"
            }`}
            title="Rynki, których Superbet nie kwotuje (niecelne, zablokowane), zawsze bez kursu"
          >
            {bezKursu ? "✓ rynki bez kursu" : "+ rynki bez kursu"}
          </button>
        </div>
      </div>

      {/* tabela — przewija się w kontenerze (poziomo na mobile),
          nagłówek kolumn przyklejony u góry */}
      <div className="mt-3.5 max-h-[75vh] overflow-auto rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-faint">
              <th className="sticky top-0 z-[1] border-b border-hairline bg-card px-4 py-2.5 font-medium">
                rynek
              </th>
              <th className="sticky top-0 z-[1] border-b border-hairline bg-card px-4 py-2.5 font-medium">
                zawodnik
              </th>
              <th className="sticky top-0 z-[1] border-b border-hairline bg-card px-4 py-2.5 font-medium">
                ostatnie 5 startów
              </th>
              <th className="sticky top-0 z-[1] border-b border-hairline bg-card px-4 py-2.5 font-medium">
                pokrycie · kurs · wartość
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {pokazane.map((w, i) => (
              <tr
                key={`${w.player_id}-${w.rynek_kod}-${i}`}
                className="align-top transition-colors even:bg-card-soft hover:bg-brand-wash/40"
              >
                <td className="whitespace-nowrap px-4 py-3 font-medium">
                  {w.rynek}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
                    <span className="font-medium">{w.zawodnik}</span>
                    <span className="text-xs text-faint">{w.druzyna}</span>
                    {!w.kadraRegularny && (
                      <span
                        className="inline-flex rounded-full bg-data-amber-wash px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-amber-ink"
                        title="Zawodnik nie ma 5 startów w reprezentacji w dostępnej historii. Rezerwa kadry, statystyki liczone z klubu. Na mecz reprezentacji traktuj ostrożnie."
                      >
                        forma klubowa
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[11px] text-faint">
                    {w.kadraBasis ? "starty w kadrze" : "starty (klub)"} · ost.
                    mecz {dataMeczu(w.ostatniMeczTs)}
                  </p>
                </td>
                <td className="px-4 py-3">
                  <span className="flex gap-1">
                    {w.ostatnie.map((g, gi) => boks(g, gi))}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className="flex flex-wrap gap-1.5">
                    {w.linie.map((l) => (
                      <span
                        key={l.linia}
                        className="inline-flex items-stretch overflow-hidden rounded-(--radius-control) border border-hairline bg-card text-xs"
                      >
                        <span className="font-data flex items-center bg-card-soft px-2 py-1 font-semibold text-ink-soft">
                          {l.prog}+
                        </span>
                        <span
                          className={`font-data flex items-center border-l border-hairline px-2 py-1 font-semibold ${
                            l.pokryte === w.probka
                              ? "text-data-green-ink"
                              : "text-ink"
                          }`}
                        >
                          {l.pokryte}/{w.probka}
                        </span>
                        {l.kurs != null && (
                          <span className="font-data flex items-center border-l border-hairline px-2 py-1 text-muted">
                            @{fmtKurs(l.kurs)}
                          </span>
                        )}
                        {l.evPct != null && (
                          <span
                            title="Zgrubny sygnał wartości: ile dałby ten zakład, gdyby surowe pokrycie było prawdziwą szansą (pokrycie × kurs − 1). To NIE jest przewaga silnika, bo próba to tylko 5 startów, bez kalibracji i kontekstu. Odsiewa kursy typu „5/5 @1,01”."
                            className={`font-data flex items-center border-l border-hairline px-2 py-1 font-semibold ${
                              l.evPct >= 8
                                ? "bg-data-green-wash text-data-green-ink"
                                : l.evPct < 0
                                  ? "bg-data-red-wash text-data-red-ink"
                                  : "text-faint"
                            }`}
                          >
                            {l.evPct > 0 ? "+" : l.evPct < 0 ? "−" : "±"}
                            {Math.abs(l.evPct)}%
                          </span>
                        )}
                      </span>
                    ))}
                  </span>
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
            className="rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-card-soft hover:text-ink"
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
        className={`pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-full rounded-lg bg-ink px-2.5 py-1.5 text-paper shadow-(--shadow-pop) transition-all duration-150 ease-out ${
          tip ? "opacity-100" : "translate-y-[calc(-100%+4px)] opacity-0"
        }`}
        style={tip ? { left: tip.x, top: tip.y - 8 } : { left: -9999, top: -9999 }}
      >
        {tip && (
          <>
            <span className="block text-[11px] font-semibold">
              {tip.g.rywal ? `vs ${tip.g.rywal}` : "mecz"}
            </span>
            <span className="block text-[10px] text-paper/70">
              {dataMeczu(tip.g.ts)} · {tip.g.minuty}′ ·{" "}
              {tip.g.kadra ? "reprezentacja" : "klub"}
            </span>
            <span className="absolute left-1/2 top-full h-2 w-2 -translate-x-1/2 -translate-y-1 rotate-45 bg-ink" />
          </>
        )}
      </div>
    </div>
  );
}
