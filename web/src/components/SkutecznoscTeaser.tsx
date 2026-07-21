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
 * Mini-wykres skuteczności dziennej: kolumna = dzień, zielone wypełnienie
 * = odsetek trafień. Wypełnia treścią przestrzeń, którą karta dostaje od
 * siatki (bliźniak wyższego biletu kuponu) — bez niego środek karty wisiał
 * z pustymi pasami nad i pod osią trafień.
 */
function DniSlupki({ dni }: { dni: SkutecznoscDnia[] }) {
  // dni[0] = najnowszy; na wykresie czas płynie w prawo
  const okno = dni.slice(0, 10).reverse();
  if (okno.length < 3) return null;
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-end">
      <p className="text-[10px] uppercase tracking-wide text-faint">
        skuteczność dzień po dniu
      </p>
      {/* słupki rosną z kartą (bliźniak wyższego biletu kuponu), z sufitem —
          bez tego środek karty wisiał z pustymi pasami */}
      <div className="mt-2 flex min-h-14 flex-1 items-end gap-1.5 [max-height:7.5rem]">
        {okno.map((d) => {
          const r = d.rozliczone > 0 ? d.trafione / d.rozliczone : 0;
          return (
            <div
              key={d.dzien}
              className="relative h-full flex-1"
              title={`${fmtDzien(d.dzien)}: ${d.trafione}/${d.rozliczone} (${fmtProc(r)})`}
            >
              <div className="absolute inset-x-0 bottom-0 h-full rounded-t-[3px] bg-ink/5" />
              <div
                className={`absolute inset-x-0 bottom-0 rounded-t-[3px] ${
                  r >= 0.5 ? "bg-data-green" : "bg-data-red/60"
                }`}
                style={{ height: `${Math.max(r * 100, 5)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-faint">
        <span>{fmtDzien(okno[0].dzien)}</span>
        <span>{fmtDzien(okno[okno.length - 1].dzien)}</span>
      </div>
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
            <div title="Trafione / rozliczone typy od startu modelu">
              <p className="text-[10px] uppercase tracking-wide text-faint">
                łącznie
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
            <div title="Trafione / rozliczone typy od startu modelu">
              <p className="text-[10px] uppercase tracking-wide text-faint">
                łącznie
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

      <div className="flex flex-1 flex-col justify-center gap-5 px-4 pb-3 pt-3.5 sm:px-5">
        <DniSlupki dni={dni} />
        <div>
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
