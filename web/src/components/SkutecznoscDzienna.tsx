"use client";

import { useMemo, useState } from "react";

import type { SkutecznoscDnia } from "@/lib/types";

/** "2026-07-10" -> "czw, 10 lip" (bez skoków stref: południe lokalne). */
function etykietaDnia(dzien: string, dlugo = false): string {
  const d = new Date(`${dzien}T12:00:00`);
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: dlugo ? "long" : "short",
    day: "numeric",
    month: dlugo ? "long" : "short",
  }).format(d);
}

/**
 * Skuteczność realnych typów DZIEŃ PO DNIU z przełącznikiem: strzałki
 * wcześniej/później + pasek klikalnych dni. `dni` przychodzi posortowane
 * malejąco (najnowszy pierwszy).
 */
export function SkutecznoscDzienna({ dni }: { dni: SkutecznoscDnia[] }) {
  const [i, setI] = useState(0);
  const dzien = dni[i];

  // pasek dni: pokazujemy do 14 najświeższych, najstarszy z lewej
  const pasek = useMemo(() => dni.slice(0, 14).slice().reverse(), [dni]);

  if (!dzien) return null;

  const proc = dzien.rozliczone
    ? Math.round((dzien.trafione / dzien.rozliczone) * 100)
    : 0;

  return (
    <div className="mt-4 max-w-3xl rounded-2xl border border-hairline bg-card p-4 shadow-(--shadow-card)">
      {/* nawigacja: wcześniej / dzień / później */}
      <div className="flex items-center justify-between gap-3">
        <button
          onClick={() => setI((v) => Math.min(v + 1, dni.length - 1))}
          disabled={i >= dni.length - 1}
          className="rounded-lg border border-hairline px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-paper hover:text-ink disabled:opacity-40"
          aria-label="Wcześniejszy dzień"
        >
          ← wcześniej
        </button>
        <p className="text-center">
          <span className="block font-semibold capitalize">
            {etykietaDnia(dzien.dzien, true)}
          </span>
          <span className="text-xs text-faint">
            {i === 0 ? "najświeższy rozliczony dzień" : `${i} dni wstecz`}
          </span>
        </p>
        <button
          onClick={() => setI((v) => Math.max(v - 1, 0))}
          disabled={i <= 0}
          className="rounded-lg border border-hairline px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-paper hover:text-ink disabled:opacity-40"
          aria-label="Późniejszy dzień"
        >
          później →
        </button>
      </div>

      {/* kafelki dnia */}
      <dl className="mt-4 grid grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-hairline bg-paper px-3.5 py-3">
          <dd className="font-data text-xl font-semibold">
            {dzien.trafione}/{dzien.rozliczone}
            <span className="ml-1 text-sm font-normal text-muted">({proc}%)</span>
          </dd>
          <dt className="mt-0.5 text-[11px] leading-tight text-faint">
            trafionych
          </dt>
        </div>
        <div className="rounded-xl border border-hairline bg-paper px-3.5 py-3">
          <dd
            className={`font-data text-xl font-semibold ${
              dzien.roi_flat > 0
                ? "text-data-green"
                : dzien.roi_flat < 0
                  ? "text-data-red"
                  : ""
            }`}
          >
            {dzien.roi_flat >= 0 ? "+" : ""}
            {dzien.roi_flat.toFixed(2).replace(".", ",")} j.
          </dd>
          <dt className="mt-0.5 text-[11px] leading-tight text-faint">
            ROI (stawka 1 j./okazję)
          </dt>
        </div>
        <div className="rounded-xl border border-hairline bg-paper px-3.5 py-3">
          <dd className="font-data text-xl font-semibold">{dzien.okazje}</dd>
          <dt className="mt-0.5 text-[11px] leading-tight text-faint">
            okazji z kursem
          </dt>
        </div>
      </dl>

      {/* pasek klikalnych dni */}
      {pasek.length > 1 && (
        <div className="mt-4 flex items-end gap-1 overflow-x-auto pb-1">
          {pasek.map((d) => {
            const idx = dni.indexOf(d);
            const aktywny = idx === i;
            const p = d.rozliczone ? d.trafione / d.rozliczone : 0;
            return (
              <button
                key={d.dzien}
                onClick={() => setI(idx)}
                title={`${etykietaDnia(d.dzien, true)} — ${d.trafione}/${d.rozliczone} trafionych`}
                className={`flex shrink-0 flex-col items-center gap-1 rounded-lg px-2 py-1.5 transition-colors ${
                  aktywny ? "bg-brand-wash" : "hover:bg-paper"
                }`}
              >
                {/* mini-słupek trafień dnia */}
                <span
                  aria-hidden
                  className="flex h-10 w-2.5 items-end overflow-hidden rounded-full bg-hairline"
                >
                  <span
                    className={`w-full rounded-full ${
                      d.roi_flat >= 0 ? "bg-data-green" : "bg-data-red"
                    }`}
                    style={{ height: `${Math.max(8, Math.round(p * 100))}%` }}
                  />
                </span>
                <span
                  className={`font-data text-[10px] leading-none ${
                    aktywny ? "font-semibold text-brand-deep" : "text-faint"
                  }`}
                >
                  {Number(d.dzien.slice(8, 10))}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
