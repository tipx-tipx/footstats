"use client";

/**
 * Forma zawodnika: liczba zdarzeń w ostatnich meczach (najnowszy z prawej),
 * jako słupki z zaznaczoną linią zakładu. Słupek nad linią = zielony.
 */
export function FormBars({
  counts,
  minutes,
  line,
  height = 44,
}: {
  counts: number[];
  minutes?: number[];
  line: number;
  height?: number;
}) {
  const values = [...counts].reverse(); // najstarszy z lewej
  const mins = minutes ? [...minutes].reverse() : undefined;
  const max = Math.max(...values, Math.ceil(line + 0.5), 2);
  const lineY = 1 - line / max;

  return (
    <div
      className="relative flex w-full items-end gap-[3px]"
      style={{ height }}
      role="img"
      aria-label={`Ostatnie ${values.length} meczów: ${values.join(", ")}`}
    >
      {values.map((v, i) => {
        const over = v > line;
        const h = Math.max((v / max) * 100, 4);
        return (
          <div
            key={i}
            className="relative flex-1 rounded-t-[3px]"
            style={{
              height: `${h}%`,
              background: over ? "var(--color-data-green)" : "#cdd8d1",
              minWidth: 6,
            }}
            title={`${v} (${mins ? `${mins[i]} min` : "mecz"} ${
              values.length - i
            } temu)`}
          />
        );
      })}
      {/* linia zakładu */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0"
        style={{
          top: `${lineY * 100}%`,
          borderTop: "1.5px dashed var(--color-ink)",
          opacity: 0.5,
        }}
      />
    </div>
  );
}
