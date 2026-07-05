"use client";

import { useState } from "react";

import type { KubelekKalibracji } from "@/lib/types";
import { fmtProc } from "@/lib/format";

/**
 * Wykres kalibracji (reliability): przewidywana szansa vs rzeczywista częstość.
 * Idealny model leży na przekątnej. Punkty = kubełki predykcji.
 */
export function CalibrationChart({
  bins,
  size = 260,
}: {
  bins: KubelekKalibracji[];
  size?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const pad = 42;
  const inner = size - pad - 12;
  const x = (v: number) => pad + v * inner;
  const y = (v: number) => size - pad - v * inner;
  const maxN = Math.max(...bins.map((b) => b.n), 1);

  return (
    <div className="relative inline-block w-full" style={{ maxWidth: size }}>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-auto w-full"
        role="img"
        aria-label="Wykres kalibracji: przewidywana szansa na osi poziomej, rzeczywista częstość na pionowej"
      >
        {/* siatka */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line
              x1={x(t)} y1={y(0)} x2={x(t)} y2={y(1)}
              stroke="var(--color-hairline)" strokeWidth="1"
            />
            <line
              x1={x(0)} y1={y(t)} x2={x(1)} y2={y(t)}
              stroke="var(--color-hairline)" strokeWidth="1"
            />
            <text
              x={x(t)} y={size - pad + 16} textAnchor="middle"
              className="fill-(--color-faint)" fontSize="10"
            >
              {Math.round(t * 100)}%
            </text>
            <text
              x={pad - 8} y={y(t) + 3} textAnchor="end"
              className="fill-(--color-faint)" fontSize="10"
            >
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        {/* przekątna ideału */}
        <line
          x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)}
          stroke="var(--color-hairline-strong)" strokeWidth="1.5"
          strokeDasharray="5 4"
        />
        <text
          x={x(0.63)}
          y={y(0.63) - 7}
          textAnchor="middle"
          fontSize="9"
          className="fill-(--color-faint)"
          transform={`rotate(-45 ${x(0.63)} ${y(0.63) - 7})`}
        >
          ideał
        </text>
        {/* punkty kubełków */}
        {bins.map((b, i) => (
          <circle
            key={i}
            cx={x(b.p_pred)}
            cy={y(b.p_real)}
            r={5 + 5 * Math.sqrt(b.n / maxN)}
            fill="var(--color-data-green)"
            fillOpacity={hover === i ? 0.95 : 0.75}
            stroke="var(--color-card)"
            strokeWidth="2"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}
        {/* podpisy osi */}
        <text
          x={x(0.5)} y={size - 4} textAnchor="middle"
          className="fill-(--color-muted)" fontSize="11"
        >
          model przewidywał
        </text>
        <text
          x={10} y={y(0.5)} textAnchor="middle" fontSize="11"
          className="fill-(--color-muted)"
          transform={`rotate(-90 10 ${y(0.5)})`}
        >
          tak było naprawdę
        </text>
      </svg>
      {hover !== null && bins[hover] && (
        <div
          className="pointer-events-none absolute rounded-lg border border-hairline bg-card px-2.5 py-1.5 text-xs shadow-(--shadow-card-hover)"
          style={{
            left: Math.min(x(bins[hover].p_pred) + 10, size - 190),
            top: Math.max(y(bins[hover].p_real) - 34, 2),
          }}
        >
          <span className="font-data">
            przewidywane {fmtProc(bins[hover].p_pred)} → realnie{" "}
            {fmtProc(bins[hover].p_real)}
          </span>
          <span className="ml-1.5 text-faint">({bins[hover].n} predykcji)</span>
        </div>
      )}
    </div>
  );
}
