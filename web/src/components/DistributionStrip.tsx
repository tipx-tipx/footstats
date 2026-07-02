"use client";

import { fmtProc } from "@/lib/format";

/**
 * Pasek rozkładu — element-sygnatura FootStats.
 *
 * Pokazuje pełny rozkład prawdopodobieństwa liczby zdarzeń (0, 1, 2, ...)
 * jako poziomy pasek, z kredową kreską w miejscu linii bukmachera.
 * Zielona część = scenariusze "powyżej linii", szara = "poniżej".
 * Szerokość segmentu = prawdopodobieństwo.
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

  let acc = 0;
  const segments = norm.map((p, k) => {
    const seg = { k, p, x: acc };
    acc += p;
    return seg;
  });
  const lineX = segments
    .slice(0, threshold)
    .reduce((a, s) => a + s.p, 0);

  return (
    <div className="w-full">
      <div
        className="relative w-full overflow-hidden rounded-md"
        style={{ height }}
        role="img"
        aria-label={`Rozkład prawdopodobieństwa liczby zdarzeń; linia ${line
          .toFixed(1)
          .replace(".", ",")}`}
      >
        {segments.map(({ k, p, x }) => {
          const over = k >= threshold;
          const isLast = k === norm.length - 1;
          return (
            <div
              key={k}
              className="group absolute top-0 h-full"
              style={{
                left: `${x * 100}%`,
                width: `calc(${p * 100}% - 2px)`,
                background: over ? "var(--color-data-green)" : "#d5ded8",
                opacity: over ? 0.55 + 0.45 * Math.min(p / 0.35, 1) : 0.8,
                borderRadius: 3,
              }}
              title={`${isLast ? `${k}+` : k} ${
                k === 1 ? "zdarzenie" : "zdarzeń"
              }: ${fmtProc(p, 1)}`}
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
        {/* kredowa kreska linii bukmachera */}
        <div
          aria-hidden
          className="absolute top-0 h-full w-0.5"
          style={{
            left: `calc(${lineX * 100}% - 1px)`,
            background:
              "repeating-linear-gradient(to bottom, var(--color-ink) 0 3px, transparent 3px 5px)",
          }}
        />
      </div>
      {side && (
        <div className="mt-1 flex justify-between text-[10px] text-faint">
          <span>← poniżej linii</span>
          <span className="font-medium text-brand-deep">powyżej linii →</span>
        </div>
      )}
    </div>
  );
}
