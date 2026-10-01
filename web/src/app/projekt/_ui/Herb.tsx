"use client";

import { useId, useState } from "react";

import type { DruzynaV } from "../_dane/przygotuj";

export type TrybHerbow = "tarcza" | "prawdziwy";

/** jasność względna (WCAG) – do wyboru koloru liter na tarczy */
function jasnosc(hex: string): number {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(full.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const TARCZA = "M12 1.2 21.6 4.4V13c0 6.6-4.1 11.2-9.6 13.8C6.5 24.2 2.4 19.6 2.4 13V4.4Z";

/**
 * Tarcza w barwach klubu: górne pole w kolorze głównym, dolny pas w drugim –
 * jak herb „w pas”. Kolory i skrót przychodzą z danych drużyny (statshub),
 * więc każda drużyna ma własny, rozpoznawalny znak bez cudzych logotypów.
 * Skrót pokazujemy dopiero od 26 px – mniejszy byłby plamą.
 */
function Tarcza({ d, rozmiar }: { d: DruzynaV; rozmiar: number }) {
  const id = useId();
  const zLiterami = rozmiar >= 26;
  const litery = jasnosc(d.c1) > 0.45 ? "#0b0f12" : "#ffffff";
  return (
    <svg width={rozmiar} height={rozmiar * (28 / 24)} viewBox="0 0 24 28" aria-hidden>
      <defs>
        <clipPath id={id}>
          <path d={TARCZA} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${id})`}>
        <rect width="24" height="28" fill={d.c1} />
        <rect y={zLiterami ? 19.5 : 16.5} width="24" height="12" fill={d.c2} />
      </g>
      <path d={TARCZA} fill="none" stroke="var(--kreska-mocna)" strokeWidth="1" />
      {zLiterami && (
        <text
          x="12"
          y="14.6"
          textAnchor="middle"
          fill={litery}
          style={{ font: "700 7.4px var(--f-n)", letterSpacing: "0.02em" }}
        >
          {d.kod}
        </text>
      )}
    </svg>
  );
}

export function Herb({
  d,
  rozmiar = 18,
  tryb,
}: {
  d: DruzynaV;
  rozmiar?: number;
  tryb: TrybHerbow;
}) {
  // wariant B (decyzja 30.09): prawdziwy herb LINKOWANY, nie kopiowany do nas;
  // gdy się nie wczyta (brak, blokada źródła), zostaje tarcza w barwach klubu
  const [padl, setPadl] = useState(false);
  const ramka = { width: rozmiar, height: rozmiar * (28 / 24) };
  if (tryb === "prawdziwy" && d.id && !padl) {
    return (
      <span className="p-herb" style={{ width: rozmiar, height: rozmiar }} title={d.nazwa}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`https://img.sofascore.com/api/v1/team/${d.id}/image`}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setPadl(true)}
        />
      </span>
    );
  }
  if (d.flaga) {
    return (
      <span className="p-herb" style={{ width: rozmiar, height: rozmiar }} title={d.nazwa}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          className="p-flaga"
          style={{ width: rozmiar, height: rozmiar }}
          src={`https://cdn.jsdelivr.net/gh/HatScripts/circle-flags@gh-pages/flags/${d.flaga}.svg`}
          alt=""
          loading="lazy"
        />
      </span>
    );
  }
  return (
    <span className="p-herb" style={ramka} title={d.nazwa}>
      <Tarcza d={d} rozmiar={rozmiar} />
    </span>
  );
}

export function FlagaLigi({
  flaga,
  id,
  c1,
  c2,
  tryb,
}: {
  flaga: string | null;
  id: number | null;
  c1: string;
  c2: string;
  tryb: TrybHerbow;
}) {
  if (tryb === "prawdziwy" && id) {
    return (
      <span className="p-herb" style={{ width: 18, height: 18 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={`https://img.sofascore.com/api/v1/unique-tournament/${id}/image`} alt="" loading="lazy" />
      </span>
    );
  }
  if (flaga) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        className="p-flaga"
        src={`https://cdn.jsdelivr.net/gh/HatScripts/circle-flags@gh-pages/flags/${flaga}.svg`}
        alt=""
        loading="lazy"
      />
    );
  }
  // rozgrywki międzynarodowe bez flagi: dwa kolory rozgrywek w kółku
  return (
    <span
      className="p-flaga"
      style={{ background: `conic-gradient(${c1} 0 50%, ${c2} 50% 100%)` }}
      aria-hidden
    />
  );
}
