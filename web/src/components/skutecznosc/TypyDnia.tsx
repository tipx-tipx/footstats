"use client";

import { fmtDzien, fmtKurs, fmtLinia, fmtU, STRONA_LABEL } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";

/**
 * Panel JEDNEGO DNIA — otwiera się pod kalendarzem po kliknięciu w kafelek.
 *
 * Wcześniej te same typy siedziały w osobnej zakładce z własnym pagerem po
 * dniach, więc strona miała dwie nawigacje po tej samej osi czasu: siatkę
 * miesiąca i przewijak „← wcześniej / później →". Kalendarz jest mapą,
 * dzień jest wejściem w szczegół — jedna oś, jedno kliknięcie.
 */

/** Typ rozliczony w tle: dlaczego nie było go na liście typów. */
const POZA_LABEL: Record<string, string> = {
  kwarantanna_rynku:
    "Rynek był wstrzymany (tracił pieniądze), typ rozliczył się w tle",
  limit_meczu:
    "Ponad limit typów z jednego meczu, typ był dostępny tylko w generatorze kuponów",
  stare_dane: "Zawodnik dawno nie grał (stare dane), typ rozliczył się w tle",
};

export function TypyDnia({
  dzien,
  onZamknij,
}: {
  dzien: SkutecznoscDnia;
  onZamknij: () => void;
}) {
  const typy = dzien.typy ?? [];
  const proc = dzien.rozliczone
    ? Math.round((dzien.trafione / dzien.rozliczone) * 100)
    : 0;

  return (
    <div className="rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
        <div>
          <h4 className="font-display text-base font-bold capitalize tracking-tight">
            {fmtDzien(dzien.dzien, true)}
          </h4>
          <p className="mt-0.5 text-xs text-muted">
            <span className="font-data font-semibold text-ink">
              {dzien.trafione}/{dzien.rozliczone}
            </span>{" "}
            trafionych ({proc}%) · bilans{" "}
            <span
              className={`font-data font-semibold ${
                dzien.roi_flat > 0
                  ? "text-data-green"
                  : dzien.roi_flat < 0
                    ? "text-data-red"
                    : "text-ink-soft"
              }`}
            >
              {fmtU(dzien.roi_flat)}
            </span>{" "}
            · {dzien.okazje} z kursem
          </p>
        </div>
        <button
          onClick={onZamknij}
          className="rounded-(--radius-control) border border-hairline px-2.5 py-1 text-xs text-muted transition-colors hover:bg-card-soft hover:text-ink"
        >
          zwiń
        </button>
      </div>

      {(dzien.poza_n ?? 0) > 0 && (
        <p className="mt-3 text-xs leading-relaxed text-faint">
          Do tego {dzien.poza_n}{" "}
          {dzien.poza_n === 1
            ? "typ rozliczył się"
            : "typów rozliczyło się"}{" "}
          w tle (weszło {dzien.poza_trafione ?? 0}) — nie było ich na liście,
          więc nie liczą się do bilansu wyżej. Na liście mają oznaczenie „w tle”.
        </p>
      )}

      {typy.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {typy.map((t, ti) => (
            <li
              key={`${t.podmiot}-${t.rynek_kod}-${t.linia}-${ti}`}
              className={`flex items-center gap-3 rounded-(--radius-control) border border-hairline px-3 py-2 text-sm ${
                t.poza_publikacja ? "bg-card opacity-75" : "bg-card-soft"
              }`}
            >
              <span
                aria-hidden
                className={`h-2 w-2 shrink-0 rounded-full ${
                  t.wynik === "wygrany"
                    ? "bg-data-green"
                    : t.wynik === "przegrany"
                      ? "bg-data-red"
                      : "bg-data-amber"
                }`}
              />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{t.podmiot}</span>{" "}
                <span className="text-muted">
                  {t.rynek.toLowerCase()} {STRONA_LABEL[t.strona]}{" "}
                  {fmtLinia(t.linia)}
                </span>
                {t.kurs != null && (
                  <span
                    className="font-data ml-1.5 whitespace-nowrap text-xs font-semibold text-ink-soft"
                    title="Kurs zamrożony w chwili publikacji typu — z niego liczy się bilans"
                  >
                    @{fmtKurs(t.kurs)}
                  </span>
                )}
                <span className="text-muted"> · {t.mecz}</span>
              </span>
              {t.poza_publikacja && (
                <span
                  className="hidden shrink-0 text-[10px] uppercase tracking-wide text-faint sm:inline"
                  title={POZA_LABEL[t.poza_publikacja] ?? "Typ rozliczony w tle"}
                >
                  w tle
                </span>
              )}
              <span className="font-data shrink-0 text-xs text-muted">
                było: {t.faktyczna != null ? t.faktyczna : "–"}
              </span>
              {t.clv_pct != null && (
                <span
                  className={`font-data hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold sm:inline-flex ${
                    t.clv_pct > 0
                      ? "bg-data-green-wash text-data-green-ink"
                      : t.clv_pct < 0
                        ? "bg-data-red-wash text-data-red-ink"
                        : "bg-card text-muted"
                  }`}
                  title="Closing Line Value: kurs wzięty vs. zamknięcie rynku"
                >
                  CLV {t.clv_pct > 0 ? "+" : ""}
                  {t.clv_pct.toFixed(0)}%
                </span>
              )}
              <span
                className={`shrink-0 text-xs font-semibold ${
                  t.wynik === "wygrany"
                    ? "text-data-green"
                    : t.wynik === "przegrany"
                      ? "text-data-red"
                      : "text-data-amber-ink"
                }`}
              >
                {t.wynik === "wygrany"
                  ? "✓ siadło"
                  : t.wynik === "przegrany"
                    ? "✗ nie"
                    : "zwrot"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-(--radius-control) border border-hairline bg-card-soft px-3.5 py-3 text-sm text-muted">
          Brak rozliczonych typów tego dnia.
        </p>
      )}
    </div>
  );
}
