import Link from "next/link";

import { fmtKurs, fmtLinia, fmtProc } from "@/lib/format";
import type { SkutecznoscDnia, TypRozliczony } from "@/lib/types";

/** Data "YYYY-MM-DD" po polsku, np. "18 lip". */
function fmtDzien(d: string): string {
  return new Date(`${d}T12:00:00`).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "short",
  });
}

const WYNIK_LABEL: Record<string, string> = {
  wygrany: "trafiony",
  przegrany: "nietrafiony",
  zwrot: "zwrot",
};

/**
 * Oś trafień: sejsmograf ostatnich rozliczonych typów. Kreska nad linią
 * (zielona) = trafiony, pod linią (czerwona) = nietrafiony, kropka na
 * linii = zwrot. Czas płynie w prawo, jak na wykresach formy.
 */
function OsTrafien({ typy }: { typy: TypRozliczony[] }) {
  return (
    <div className="relative">
      <span
        aria-hidden
        className="absolute inset-x-0 top-1/2 h-px bg-hairline-strong"
      />
      <ul className="relative flex items-center justify-between">
        {typy.map((t, i) => (
          <li
            key={`${t.podmiot}-${t.rynek_kod}-${t.linia}-${i}`}
            title={`${t.podmiot}, ${t.rynek.toLowerCase()} ${fmtLinia(t.linia)}+${
              t.kurs != null ? ` @${fmtKurs(t.kurs)}` : ""
            }: ${WYNIK_LABEL[t.wynik ?? ""] ?? "?"}`}
            className="relative h-10 w-[7px]"
          >
            {t.wynik === "wygrany" ? (
              <span className="absolute bottom-1/2 left-1/2 mb-px h-3.5 w-[5px] -translate-x-1/2 rounded-full bg-data-green" />
            ) : t.wynik === "przegrany" ? (
              <span className="absolute left-1/2 top-1/2 mt-px h-3.5 w-[5px] -translate-x-1/2 rounded-full bg-data-red" />
            ) : (
              <span className="absolute left-1/2 top-1/2 h-[5px] w-[5px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-hairline-strong" />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Dowód trafień na stronie głównej, bliźniak biletu kuponu (ta sama
 * anatomia karty: nagłówek ze statystykami, pasek, treść, akcja na dole).
 * Liczby są prawdziwe w obie strony. To celowe: transparentność jest tezą
 * produktu, a pełen rozkład dzień po dniu czeka na Skuteczności.
 */
export function SkutecznoscTeaser({
  ostatnie,
  dni,
  trafione,
  rozliczone,
}: {
  ostatnie: TypRozliczony[];
  dni: SkutecznoscDnia[];
  trafione: number;
  rozliczone: number;
}) {
  // tylko opublikowane typy z wynikiem; najnowszy po prawej (jak oś czasu)
  const kropki = ostatnie
    .filter((t) => t.wynik != null && !t.poza_publikacja)
    .slice(0, 18)
    .reverse();
  const ostatniDzien = dni[0];
  const trafialnosc = rozliczone > 0 ? trafione / rozliczone : 0;

  if (kropki.length === 0 || rozliczone === 0) return null;

  return (
    <article className="flex h-full flex-col overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
      <header className="bg-gradient-to-br from-card-soft via-card-soft/60 to-card px-4 pb-4 pt-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-5 bg-brand-bright" />
            jak trafia model
          </p>
          <span className="rounded-full bg-card px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted shadow-(--shadow-card)">
            rozliczane automatycznie
          </span>
        </div>

        <div className="mt-3.5 flex flex-wrap items-end gap-x-7 gap-y-2.5">
          {ostatniDzien ? (
            <div
              title={`Trafione / rozliczone typy z meczów ${fmtDzien(ostatniDzien.dzien)}`}
            >
              <p className="text-[10px] uppercase tracking-wide text-faint">
                ostatni dzień ({fmtDzien(ostatniDzien.dzien)})
              </p>
              <p className="font-data mt-0.5 text-[1.7rem] font-bold leading-none">
                {ostatniDzien.trafione}
                <span className="text-lg font-semibold text-muted">
                  /{ostatniDzien.rozliczone}
                </span>
              </p>
            </div>
          ) : (
            <div title="Trafione / rozliczone typy w całym turnieju">
              <p className="text-[10px] uppercase tracking-wide text-faint">
                cały turniej
              </p>
              <p className="font-data mt-0.5 text-[1.7rem] font-bold leading-none">
                {trafione}
                <span className="text-lg font-semibold text-muted">
                  /{rozliczone}
                </span>
              </p>
            </div>
          )}
          {ostatniDzien && (
            <div title="Trafione / rozliczone typy w całym turnieju">
              <p className="text-[10px] uppercase tracking-wide text-faint">
                cały turniej
              </p>
              <p className="font-data mt-0.5 text-lg font-semibold leading-tight">
                {trafione}/{rozliczone}
              </p>
            </div>
          )}
          <div title="Odsetek trafionych wśród wszystkich rozliczonych typów">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              trafialność
            </p>
            <p className="font-data mt-0.5 text-lg font-semibold leading-tight text-data-green">
              {fmtProc(trafialnosc)}
            </p>
          </div>
        </div>

        <div
          className="mt-3.5 h-1.5 w-full overflow-hidden rounded-full bg-ink/10"
          role="img"
          aria-label={`trafialność ${fmtProc(trafialnosc)}`}
        >
          <div
            className="h-full rounded-full bg-gradient-to-r from-data-green/60 to-data-green"
            style={{ width: `${Math.round(trafialnosc * 100)}%` }}
          />
        </div>
      </header>

      <div className="flex flex-1 flex-col justify-center px-4 pb-3 pt-3.5 sm:px-5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] uppercase tracking-wide text-faint">
            ostatnie rozliczone typy
          </p>
          <p className="flex items-center gap-3 text-[10px] text-faint">
            <span className="flex items-center gap-1">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-green" />
              trafiony
            </span>
            <span className="flex items-center gap-1">
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-data-red" />
              nietrafiony
            </span>
          </p>
        </div>
        <div className="mt-2">
          <OsTrafien typy={kropki} />
        </div>
        <p aria-hidden className="mt-1 text-[10px] text-faint">
          najstarszy →
        </p>
      </div>

      <Link
        href="/model"
        className="font-display group mt-auto flex items-center justify-between gap-2 border-t border-hairline px-4 py-3 text-xs font-semibold uppercase tracking-widest text-brand transition-colors hover:bg-brand-wash/50 hover:text-brand-strong sm:px-5"
      >
        pełna skuteczność dzień po dniu
        <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
          →
        </span>
      </Link>
    </article>
  );
}
