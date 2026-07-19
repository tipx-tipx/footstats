import Link from "next/link";

import { fmtMnoznik } from "@/lib/format";
import type { KuponHistoria } from "@/lib/types";

/** Data "YYYY-MM-DD" po polsku, np. "17 lip". */
function fmtDzien(d: string): string {
  return new Date(`${d}T12:00:00`).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "short",
  });
}

const ZAKRES_LABEL: Record<string, string> = {
  dzienny: "na dziś",
  dlugoterminowy: "na kilka dni",
  value: "value",
};

/**
 * Dowód w miejscu decyzji: półka ostatnio trafionych kuponów (trwały log,
 * wygrane nigdy nie znikają). Mini-bilety w jednym rzędzie, zieleń danych
 * tylko jako akcent wyniku. Pełna historia i ROI czekają na Skuteczności.
 */
export function TrafioneKupony({ kupony }: { kupony: KuponHistoria[] }) {
  const wygrane = kupony
    .filter((k) => k.wynik === "wygrany")
    .sort((a, b) => (b.dzien < a.dzien ? -1 : 1))
    .slice(0, 6);
  if (wygrane.length === 0) return null;

  return (
    <section aria-label="Ostatnio trafione kupony" className="mt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-5 bg-brand-bright" />
          ostatnio trafione
        </p>
        <Link
          href="/model"
          className="font-display inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted transition-colors hover:text-brand"
        >
          pełna historia i bilans
          <span aria-hidden>→</span>
        </Link>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {wygrane.map((k) => (
          <article
            key={k.klucz ?? `${k.dzien}-${k.cel_label ?? k.cel}`}
            className="overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)"
          >
            <div className="flex items-center justify-between gap-2 border-b border-dashed border-hairline-strong bg-gradient-to-br from-data-green-wash/70 to-card px-4 py-2.5">
              <p className="font-data text-lg font-bold leading-none">
                {fmtMnoznik(k.kurs_rozliczony ?? k.kurs_laczny)}
                {k.kurs_rozliczony != null &&
                  k.kurs_rozliczony < k.kurs_laczny && (
                    <span
                      className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted"
                      title="Część typów zakończyła się zwrotem, kurs rozliczony jest niższy od pełnego"
                    >
                      po zwrotach
                    </span>
                  )}
              </p>
              <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-data-green-ink">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-green" />
                trafiony
              </span>
            </div>
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 py-2.5 text-xs text-muted">
              <span>
                {fmtDzien(k.dzien)} · {ZAKRES_LABEL[k.horyzont ?? "value"]}
              </span>
              <span className="font-data">
                {k.legi_trafione ?? k.legi.length}/{k.legi.length} typów
              </span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
