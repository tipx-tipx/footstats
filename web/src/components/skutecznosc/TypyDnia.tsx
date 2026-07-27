"use client";

import { WierszTypu } from "./WierszTypu";
import { fmtDzien, fmtU } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";

/**
 * Panel JEDNEGO DNIA — otwiera się pod kalendarzem po kliknięciu w kafelek.
 *
 * Wcześniej te same typy siedziały w osobnej zakładce z własnym pagerem po
 * dniach, więc strona miała dwie nawigacje po tej samej osi czasu: siatkę
 * miesiąca i przewijak „← wcześniej / później →". Kalendarz jest mapą,
 * dzień jest wejściem w szczegół — jedna oś, jedno kliknięcie. Pełną listę
 * bez wybierania dnia daje zakładka „Co weszło" (ListaTypow).
 */

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
            weszło ({proc}%) · bilans{" "}
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
          Poza tym {dzien.poza_n}{" "}
          {dzien.poza_n === 1 ? "typ policzył się" : "typów policzyło się"}{" "}
          tylko na próbę (weszło {dzien.poza_trafione ?? 0}). Nie było ich na
          stronie, więc nie liczymy ich do bilansu wyżej — na liście mają
          oznaczenie „na próbę”.
        </p>
      )}

      {typy.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {typy.map((t, ti) => (
            <WierszTypu
              key={`${t.podmiot}-${t.rynek_kod}-${t.linia}-${ti}`}
              t={t}
            />
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-(--radius-control) border border-hairline bg-card-soft px-3.5 py-3 text-sm text-muted">
          Tego dnia nic się nie rozliczyło.
        </p>
      )}
    </div>
  );
}
