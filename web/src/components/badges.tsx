import type { Pewnosc, Ryzyko } from "@/lib/types";
import { fmtEV, RYZYKO_LABEL } from "@/lib/format";

/** Plakietka przewagi nad kursem — im wyżej, tym mocniejszy sygnał. */
export function EdgeBadge({ ev }: { ev: number }) {
  const strong = ev >= 10;
  return (
    <span
      className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold ${
        strong
          ? "bg-data-green text-on-brand"
          : "bg-data-green-wash text-data-green-ink"
      }`}
      title="O ile procent kurs jest wyższy, niż wynikałoby z naszej szansy. Przy +8% z każdych postawionych 100 zł średnio 8 zł to zysk — o ile mamy rację."
    >
      {fmtEV(ev)}
    </span>
  );
}

export function PewnoscDots({ level }: { level: Pewnosc }) {
  const filled = level === "wysoka" ? 3 : level === "srednia" ? 2 : 1;
  // rosnące kreski jak wskaźnik zasięgu — czytelniejsze "ile" niż kropki
  const wysokosci = ["h-1.5", "h-2.5", "h-3"];
  return (
    <span aria-hidden className="flex items-end gap-[3px]">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`w-1 rounded-[1px] ${wysokosci[i]} ${
            i < filled ? "bg-current" : "bg-current opacity-25"
          }`}
        />
      ))}
    </span>
  );
}

const RYZYKO_STYLE: Record<Ryzyko, string> = {
  niskie: "text-muted",
  srednie: "text-data-amber-ink",
  wysokie: "text-data-red-ink",
};

/** Zmienność samego zdarzenia — niezależna od pewności modelu. */
export function RiskBadge({ level }: { level: Ryzyko }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs font-medium ${RYZYKO_STYLE[level]}`}
      title="Jak kapryśne jest samo zdarzenie. Rzadkie rzeczy (kartka, gol obrońcy) potrafią nie wejść nawet wtedy, gdy liczby były po naszej stronie."
    >
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
        <path
          d="M5 1 L9 8 L1 8 Z"
          fill={level === "niskie" ? "none" : "currentColor"}
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      </svg>
      ryzyko: {RYZYKO_LABEL[level]}
    </span>
  );
}

/**
 * Chip kontekstowy karty (matchup, świeże składy, miękka linia…) —
 * jeden wygląd dla wszystkich sygnałów, ton dobiera wariant.
 */
export function SignalChip({
  tone,
  title,
  children,
}: {
  tone: "brand" | "amber";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
        tone === "brand"
          ? "bg-brand-wash text-brand-deep"
          : "bg-data-amber-wash text-data-amber-ink"
      }`}
    >
      {children}
    </span>
  );
}
