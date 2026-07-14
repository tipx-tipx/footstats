import type { Pewnosc, Ryzyko } from "@/lib/types";
import { fmtEV, PEWNOSC_LABEL, RYZYKO_LABEL } from "@/lib/format";

/** Badge wartości zakładu (EV%) — im wyższa wartość, tym mocniejszy sygnał. */
export function EdgeBadge({ ev }: { ev: number }) {
  const strong = ev >= 10;
  return (
    <span
      className={`font-data inline-flex items-center rounded-md px-2 py-0.5 text-sm font-semibold ${
        strong
          ? "bg-data-green text-on-brand"
          : "bg-data-green-wash text-brand-deep"
      }`}
      title="Wartość oczekiwana zakładu: o ile procent kurs jest lepszy, niż być powinien według modelu"
    >
      {fmtEV(ev)}
    </span>
  );
}

const PEWNOSC_STYLE: Record<Pewnosc, string> = {
  wysoka: "bg-data-green-wash text-brand-deep",
  srednia: "bg-data-amber-wash text-data-amber-ink",
  niska: "bg-paper text-muted",
};

/** Ile ufamy tej predykcji (próba, minuty, precyzja). */
export function ConfidenceBadge({ level }: { level: Pewnosc }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${PEWNOSC_STYLE[level]}`}
      title="Pewność modelu: ile danych i jak stabilnych stoi za tą predykcją"
    >
      <PewnoscDots level={level} />
      pewność: {PEWNOSC_LABEL[level]}
    </span>
  );
}

export function PewnoscDots({ level }: { level: Pewnosc }) {
  const filled = level === "wysoka" ? 3 : level === "srednia" ? 2 : 1;
  return (
    <span aria-hidden className="flex items-center gap-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${
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
  wysokie: "text-data-red",
};

/** Zmienność samego zdarzenia — niezależna od pewności modelu. */
export function RiskBadge({ level }: { level: Ryzyko }) {
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${RYZYKO_STYLE[level]}`}
      title="Ryzyko: jak kapryśne jest samo zdarzenie (rzadkie zdarzenia = duża loteria nawet przy dobrym modelu)"
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
