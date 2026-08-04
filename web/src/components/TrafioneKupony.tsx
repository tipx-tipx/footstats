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
 * Ostatnie ROZLICZONE kupony — trafione i nietrafione, z prawdziwym licznikiem.
 *
 * BYŁO DO 2026-08-04: sekcja „ostatnio trafione" filtrowała `wynik ===
 * "wygrany"` i pokazywała sześć zielonych kart z rzędu. Na zrzucie wyglądało
 * to jak witryna oszusta — sześć kuponów, sześć trafionych, ×20,01, ×15,18.
 * Link „pełna historia i bilans" był, ale pierwsze wrażenie jest tym, co
 * decyduje, a ono było nieprawdziwe.
 *
 * DLACZEGO ZMIANA POMAGA SPRZEDAŻY, a nie szkodzi: „6 z 6" czyta się jak
 * reklama i nikt w to nie wierzy. „4 z 6" czyta się jak wynik i buduje
 * zaufanie do WSZYSTKICH pozostałych liczb na stronie. Cel produktu ustalony
 * z userem brzmi „przekaz realny z rzeczywistością" — to jest dokładnie to
 * miejsce, w którym się rozjeżdżał.
 *
 * Zwroty i anulowane pomijamy: to nie jest ani trafienie, ani pudło, a
 * dokładanie trzeciego stanu do sześciu kafelków tylko zaciemnia obraz.
 */
export function TrafioneKupony({
  kupony,
  roi,
}: {
  kupony: KuponHistoria[];
  /** bilans per horyzont z PEŁNEGO logu (nie tylko z 21 dni w `kupony`) */
  roi?: Record<string, { n: number; wygrane: number; roi_j: number }>;
}) {
  const rozliczone = kupony
    .filter((k) => k.wynik === "wygrany" || k.wynik === "przegrany")
    .filter((k) => !k.pominiety)
    .sort((a, b) => (b.dzien < a.dzien ? -1 : 1))
    .slice(0, 6);
  if (rozliczone.length === 0) return null;

  // BILANS Z CAŁOŚCI, NIE Z SZEŚCIU POKAZANYCH (2026-08-04). Licznik liczony
  // z widocznych kart potrafił pokazać „0 z 6" przy prawdziwym „5 z 77" —
  // sześć ostatnich kuponów to za mała próba, żeby cokolwiek znaczyła,
  // a przy złej passie wygląda gorzej niż rzeczywistość. `kupony_roi` idzie
  // z pełnego logu, więc nagłówek mówi prawdę o całym okresie.
  const suma = Object.values(roi ?? {}).reduce(
    (a, r) => ({ n: a.n + r.n, wygrane: a.wygrane + r.wygrane }),
    { n: 0, wygrane: 0 },
  );
  const maBilans = suma.n > 0;

  return (
    <section aria-label="Ostatnie rozliczone kupony" className="mt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-brand">
          <span aria-hidden className="h-px w-5 bg-brand-bright" />
          ostatnio rozliczone
          {maBilans && (
            <span className="font-data font-semibold normal-case tracking-normal text-muted">
              wszystkich: {suma.wygrane} z {suma.n} trafionych
            </span>
          )}
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
        {rozliczone.map((k) => {
          const wygrany = k.wynik === "wygrany";
          return (
            <article
              key={k.klucz ?? `${k.dzien}-${k.cel_label ?? k.cel}`}
              className="overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card)"
            >
              <div
                className={`flex items-center justify-between gap-2 border-b border-dashed border-hairline-strong px-4 py-2.5 ${
                  wygrany
                    ? "bg-gradient-to-br from-data-green-wash/70 to-card"
                    : "bg-card-soft/60"
                }`}
              >
                <p
                  className={`font-data text-lg font-bold leading-none ${
                    wygrany ? "" : "text-muted"
                  }`}
                >
                  {fmtMnoznik(k.kurs_rozliczony ?? k.kurs_laczny)}
                  {wygrany &&
                    k.kurs_rozliczony != null &&
                    k.kurs_rozliczony < k.kurs_laczny && (
                      <span
                        className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted"
                        title="Część typów zakończyła się zwrotem, kurs rozliczony jest niższy od pełnego"
                      >
                        po zwrotach
                      </span>
                    )}
                </p>
                <span
                  className={`flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide ${
                    wygrany ? "text-data-green-ink" : "text-muted"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`h-1.5 w-1.5 rounded-full ${
                      wygrany ? "bg-data-green" : "bg-data-red/70"
                    }`}
                  />
                  {wygrany ? "trafiony" : "nietrafiony"}
                </span>
              </div>
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-4 py-2.5 text-xs text-muted">
                <span>
                  {fmtDzien(k.dzien)} · {ZAKRES_LABEL[k.horyzont ?? "value"]}
                </span>
                <span className="font-data">
                  {k.legi_trafione ?? (wygrany ? k.legi.length : 0)}/
                  {k.legi.length} typów
                </span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
