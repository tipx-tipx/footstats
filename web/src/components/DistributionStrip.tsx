"use client";

import { fmtLinia, fmtProc } from "@/lib/format";

/**
 * Pasek rozkładu — element-sygnatura FootStats.
 *
 * Pokazuje pełny rozkład prawdopodobieństwa liczby zdarzeń (0, 1, 2, ...)
 * jako poziomy pasek: szerokość segmentu = szansa tego wyniku.
 * Zielone segmenty = scenariusze "powyżej linii" (te, na które gramy),
 * szare = "poniżej". Kreskowana pionowa kreska = linia bukmachera.
 */
export function DistributionStrip({
  dist,
  line,
  side,
  height = 22,
  showLabels = false,
}: {
  dist: number[];
  line: number;
  side?: "powyzej" | "ponizej";
  height?: number;
  showLabels?: boolean;
}) {
  const total = dist.reduce((a, b) => a + b, 0) || 1;
  const norm = dist.map((p) => p / total);
  const threshold = Math.floor(line) + 1; // "powyżej 1,5" = X >= 2

  const segments: { k: number; p: number; x: number }[] = [];
  norm.reduce((x, p, k) => {
    segments.push({ k, p, x });
    return x + p;
  }, 0);
  const pPonizej = segments.slice(0, threshold).reduce((a, s) => a + s.p, 0);
  const pPowyzej = 1 - pPonizej;

  return (
    <div className="w-full">
      <div
        className="relative w-full"
        style={{ height }}
        role="img"
        aria-label={`Rozkład możliwych wyników. Powyżej linii ${fmtLinia(line)}: ${fmtProc(
          pPowyzej,
        )}, poniżej: ${fmtProc(pPonizej)}.`}
      >
        {segments.map(({ k, p, x }) => {
          const over = k >= threshold;
          const isLast = k === norm.length - 1;
          return (
            <div
              key={k}
              className="absolute top-0 h-full"
              style={{
                left: `${x * 100}%`,
                width: `calc(${p * 100}% - 2px)`,
                background: over
                  ? "var(--color-data-green)"
                  : "var(--color-hairline)",
                borderRadius: 4,
              }}
              title={`${isLast ? `${k}+` : k} — szansa ${fmtProc(p, 1)}`}
            >
              {showLabels && p > 0.09 && (
                <span
                  className="font-data absolute inset-0 flex items-center justify-center text-[10px] font-medium"
                  style={{ color: over ? "#fff" : "var(--color-muted)" }}
                >
                  {isLast ? `${k}+` : k}
                </span>
              )}
            </div>
          );
        })}
        {/* kredowa kreska: linia bukmachera */}
        <div
          aria-hidden
          className="absolute -top-0.5 h-[calc(100%+4px)] w-0.5"
          title={`Linia bukmachera: ${fmtLinia(line)}`}
          style={{
            left: `calc(${pPonizej * 100}% - 1px)`,
            background:
              "repeating-linear-gradient(to bottom, var(--color-ink) 0 3px, transparent 3px 5px)",
          }}
        />
      </div>
      {showLabels && (
        <div className="mt-1.5 flex items-baseline justify-between text-[11px]">
          <span className="text-muted">
            poniżej {fmtLinia(line)}:{" "}
            <span className="font-data font-medium">{fmtProc(pPonizej)}</span>
          </span>
          <span
            className={
              side === "powyzej" || side == null
                ? "font-semibold text-brand-deep"
                : "text-muted"
            }
          >
            powyżej {fmtLinia(line)}:{" "}
            <span className="font-data font-medium">{fmtProc(pPowyzej)}</span>
          </span>
        </div>
      )}
    </div>
  );
}
