"use client";

import { useMemo, useState } from "react";

import { fmtDzien, fmtGodzina, fmtLinia, STRONA_LABEL } from "@/lib/format";
import type { SkutecznoscDnia } from "@/lib/types";

/** Ile kart pokazujemy przed rozwinięciem pełnej listy. */
const NA_START = 15;

const KLASA_STYL: Record<string, string> = {
  top: "bg-data-green-wash text-data-green-ink",
  mocny: "bg-brand-wash text-brand-deep",
  solidny: "bg-card text-muted",
};

/**
 * Kronika ROZLICZONYCH KART DRABINEK: jedna linia na kartę, najnowsze u góry,
 * z werdyktem „siadło / nie".
 *
 * Dlaczego osobno od `SkutecznoscDzienna`: tamten widok to pager po dniach,
 * zaprojektowany pod kilkadziesiąt typów dziennie. Drabinek jest kilka na dobę,
 * więc przewijanie dzień po dniu ukrywało dokładnie to, o co się pyta przy tej
 * zakładce — KTÓRA karta weszła, a która nie. Tu widać to ciągiem, razem z
 * klasą karty i deklarowaną szansą, więc od razu wiadomo, czy przegrała karta
 * oznaczona jako „top", czy ta z końca rankingu.
 */
export function KartyDrabinek({ dni }: { dni: SkutecznoscDnia[] }) {
  const [wszystkie, setWszystkie] = useState(false);

  // dni przychodzą najnowszym do przodu, ale typy w dniu są posortowane
  // trafionymi do góry — w kronice chcemy porządku czasu, nie wyniku
  const karty = useMemo(
    () =>
      dni.flatMap((d) =>
        (d.typy ?? [])
          .slice()
          .sort((a, b) => (b.kickoff_ts ?? 0) - (a.kickoff_ts ?? 0))
          .map((t) => ({ typ: t, dzien: d.dzien })),
      ),
    [dni],
  );

  if (!karty.length) return null;

  const widoczne = wszystkie ? karty : karty.slice(0, NA_START);

  return (
    <div className="mt-5 max-w-3xl rounded-(--radius-card) border border-hairline bg-card p-4 shadow-(--shadow-card) sm:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display font-semibold tracking-tight">
          Karty rozliczone
        </h3>
        <span className="font-data text-xs text-faint">
          {karty.length} {karty.length === 1 ? "karta" : "kart"}
        </span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-muted">
        Szczebel, który zdecydował o karcie — ten sam, który widziałeś w jej
        nagłówku. „Było” to faktyczna wartość zawodnika w regularnym czasie gry.
      </p>

      <ul className="mt-4 space-y-1.5">
        {widoczne.map(({ typ: t, dzien }, i) => {
          // nagłówek dnia tylko przy zmianie daty — porównanie z poprzednią
          // pozycją listy, bez zmiennej przenoszonej między iteracjami
          // (mutowanie zmiennej w trakcie renderu psuje kolejne przebiegi)
          const nowyDzien = i === 0 || widoczne[i - 1].dzien !== dzien;
          return (
            <li key={`${dzien}-${t.podmiot}-${t.rynek_kod}-${t.linia}-${i}`}>
              {nowyDzien && (
                <p className="mb-1.5 mt-3 text-[10px] uppercase tracking-wide text-faint first:mt-0">
                  {fmtDzien(dzien)}
                </p>
              )}
              <div
                className={`flex items-center gap-2.5 rounded-(--radius-control) border border-hairline px-3 py-2 text-sm sm:gap-3 ${
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
                <span className="font-data hidden shrink-0 text-xs text-faint sm:inline">
                  {fmtGodzina(t.kickoff_ts)}
                </span>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{t.podmiot}</span>{" "}
                  <span className="text-muted">
                    {t.rynek.toLowerCase()} {STRONA_LABEL[t.strona]}{" "}
                    {fmtLinia(t.linia)}
                  </span>
                  <span className="block truncate text-xs text-faint">
                    {t.mecz}
                  </span>
                </span>
                {t.klasa && (
                  <span
                    className={`font-data hidden shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide sm:inline-flex ${
                      KLASA_STYL[t.klasa] ?? "bg-card text-muted"
                    }`}
                    title="Klasa karty zamrożona przy publikacji — sprawdzian, czy oznaczenia się bronią"
                  >
                    {t.klasa}
                  </span>
                )}
                <span
                  className="font-data hidden shrink-0 text-xs text-faint md:inline"
                  title="Szansa deklarowana przez kartę przy publikacji (pokrycie linii po korekcie kontekstowej)"
                >
                  {Math.round(t.p_model * 100)}%
                </span>
                <span className="font-data shrink-0 text-xs text-muted">
                  było: {t.faktyczna != null ? t.faktyczna : "–"}
                </span>
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
              </div>
            </li>
          );
        })}
      </ul>

      {karty.length > NA_START && (
        <button
          onClick={() => setWszystkie((v) => !v)}
          className="mt-3 rounded-(--radius-control) border border-hairline bg-card px-3 py-1.5 text-xs text-muted transition-colors hover:bg-card-soft hover:text-ink"
        >
          {wszystkie
            ? "pokaż mniej"
            : `pokaż wszystkie (${karty.length})`}
        </button>
      )}
    </div>
  );
}
