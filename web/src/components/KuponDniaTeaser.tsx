import Link from "next/link";

import { CountUpKurs, PasekSzansy } from "./KuponAnim";
import { fmtDataCzas, fmtKurs, fmtLinia, fmtProc } from "@/lib/format";
import type { Kupon } from "@/lib/types";

const STRONA_ZNAK: Record<string, string> = { powyzej: "+", ponizej: "-" };

/**
 * Miniatura biletu z /kupony na stronę główną: hero obiecuje „składa gotowe
 * kupony", więc główna jeden pokazuje. Ta sama anatomia co pełny bilet
 * (gradientowy nagłówek, kurs dobijający, pasek szansy, perforacja, typy
 * pogrupowane po meczu), żeby całość czytała się jako jeden system.
 */
export function KuponDniaTeaser({ kupon }: { kupon: Kupon }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)">
      {/* nagłówek biletu */}
      <header className="bg-gradient-to-br from-brand-wash via-brand-wash/60 to-card px-4 pb-4 pt-4 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
            <span aria-hidden className="h-px w-5 bg-brand-bright" />
            kupon dnia od modelu
          </p>
          <span className="rounded-full bg-card-soft px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
            {kupon.styl === "value" ? "value" : "pewniaki"}
          </span>
        </div>

        <div className="mt-3.5 flex flex-wrap items-end gap-x-7 gap-y-2.5">
          <div title="Kursy wszystkich typów pomnożone przez siebie: tyle razy rośnie stawka, gdy wejdzie całość">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              kurs łączny
            </p>
            <CountUpKurs
              value={kupon.kurs_laczny}
              prefix="×"
              className="font-data mt-0.5 block text-[1.7rem] font-bold leading-none"
            />
          </div>
          <div title="Prawdopodobieństwo, że wejdą wszystkie typy naraz (wg modelu)">
            <p className="text-[10px] uppercase tracking-wide text-faint">
              szansa modelu
            </p>
            <p className="font-data mt-0.5 text-lg font-semibold leading-tight">
              {fmtProc(kupon.p_model)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              z 10 zł robi się
            </p>
            <p className="font-data mt-0.5 text-lg font-semibold leading-tight">
              {Math.round(kupon.kurs_laczny * 10)} zł
            </p>
          </div>
        </div>
        <PasekSzansy p={kupon.p_model} className="mt-3.5" />
      </header>

      {/* perforacja biletu */}
      <div aria-hidden className="relative">
        <span className="absolute -left-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-hairline bg-paper" />
        <span className="absolute -right-2.5 top-1/2 h-5 w-5 -translate-y-1/2 rounded-full border border-hairline bg-paper" />
        <span className="mx-4 block border-t border-dashed border-hairline-strong sm:mx-5" />
      </div>

      {/* typy zgrupowane po meczu — jak na pełnym bilecie */}
      <div className="flex-1 pb-1">
        {kupon.legi.map((l, li) => {
          const nowyMecz = li === 0 || kupon.legi[li - 1].mecz_id !== l.mecz_id;
          return (
            <div key={`${l.mecz_id}-${l.value_bet_id}-${li}`}>
              {nowyMecz && (
                <p className="flex items-baseline justify-between gap-2 border-b border-hairline bg-card-soft px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-soft sm:px-5">
                  {l.mecz}
                  <span className="font-normal normal-case tracking-normal text-faint">
                    {fmtDataCzas(l.kickoff_ts)}
                  </span>
                </p>
              )}
              <div className="flex items-baseline gap-3 px-4 py-2.5 sm:px-5">
                <p className="min-w-0 flex-1 truncate text-sm">
                  <span className="font-semibold text-ink">{l.podmiot}</span>
                  <span className="ml-1.5 text-muted">
                    {l.rynek.toLowerCase()} {fmtLinia(l.linia)}
                    {STRONA_ZNAK[l.strona] ?? "+"}
                  </span>
                </p>
                <p className="font-data shrink-0 text-sm font-semibold text-brand-deep">
                  @{fmtKurs(l.kurs)}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* odcinek kontrolny: akcja na całą szerokość, symetrycznie z drugą kartą */}
      <Link
        href="/kupony"
        className="font-display group mt-auto flex items-center justify-between gap-2 border-t border-hairline px-4 py-3 text-xs font-semibold uppercase tracking-widest text-brand transition-colors hover:bg-brand-wash/50 hover:text-brand-strong sm:px-5"
      >
        wszystkie kupony i wyższe kursy
        <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
          →
        </span>
      </Link>
    </article>
  );
}
