"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useEffect, useState } from "react";

import { ConfidenceBadge, EdgeBadge, PewnoscDots, RiskBadge } from "./badges";
import { ChanceBar, OutcomeColumns } from "./DistributionStrip";
import { FormBars } from "./FormBars";
import { addZakladFromBet, isTracked, onZakladyChange } from "@/lib/tracker";
import {
  fmtDataCzas,
  fmtEV,
  fmtKurs,
  fmtLinia,
  fmtMnoznik,
  fmtProc,
  PEWNOSC_LABEL,
  STRONA_LABEL,
} from "@/lib/format";
import type { FormaRynku, ValueBet, Zawodnik } from "@/lib/types";

/** Hit-rate linii w oknach czasowych (mecze z minutami, od najnowszych). */
function oknaFormy(forma: FormaRynku, linia: number) {
  const zagrane = forma.ostatnie
    .map((v, i) => ({ v, min: forma.minuty[i] ?? 0 }))
    .filter((x) => x.min > 0);
  const okno = (n: number) => {
    const w = zagrane.slice(0, n);
    return { traf: w.filter((x) => x.v > linia).length, n: w.length };
  };
  return {
    zagrane: zagrane.length,
    l5: okno(5),
    l10: okno(10),
    all: okno(zagrane.length),
  };
}

/**
 * Sygnalizacja świetlna (wzorzec Outlier): triage wzrokiem bez czytania.
 * zielony = historia (L10) i model zgodnie wysoko; czerwony = historia
 * przeczy linii; bursztyn = środek; null = za mała próba (bez paska).
 */
function swiatloTypu(
  forma: FormaRynku | undefined,
  linia: number,
  pModel: number,
): "green" | "amber" | "red" | null {
  if (!forma) return null;
  const o = oknaFormy(forma, linia);
  if (o.zagrane < 5) return null;
  const hr = o.l10.traf / Math.max(o.l10.n, 1);
  if (hr >= 0.65 && pModel >= 0.55) return "green";
  if (hr < 0.45) return "red";
  return "amber";
}

const SWIATLO_STYL = {
  green: {
    pasek: "bg-data-green",
    opis: "Zielone światło: linia przebijana w ≥65% ostatnich 10 meczów, a model daje wysoką szansę",
  },
  amber: {
    pasek: "bg-data-amber",
    opis: "Żółte światło: historia i model nie mówią jednym głosem — przeczytaj szczegóły",
  },
  red: {
    pasek: "bg-data-red",
    opis: "Czerwone światło: linia przebita w mniej niż 45% ostatnich 10 meczów — historia przeczy typowi",
  },
} as const;

/**
 * Oznaczenie typu z puli pewniaków wg szansy modelu. Sama etykieta "pewniak"
 * przy 55% wprowadzała w błąd — pula zawiera typy od ~42% (perełki) do 90%+.
 * Progi: ≥75% pewniak, 62–74% mocny typ, 52–61% umiarkowany, <52% perełka
 * (do puli poniżej 52% wchodzą tylko typy z kursem 1,9+).
 */
function tierPewniaka(bet: ValueBet): {
  label: string;
  cls: string;
  opis: string;
} {
  if (bet.wyzsza_linia) {
    if (bet.p_model < 0.52) {
      return {
        label: "✦ opcja ryzykowna",
        cls: "bg-data-amber-wash text-[#8a5613]",
        opis: "Wyższa linia przy szansie 40–52% i kursie 1,9+ — świadomie ryzykowny wariant typu bazowego, nie pewniak",
      };
    }
    return {
      label: "✦ wyższa linia",
      cls: "bg-data-amber-wash text-[#8a5613]",
      opis: "Perełka: wyższa linia (1,5+) przy wciąż solidnej szansie — wyraźnie lepszy kurs niż na linii 0,5",
    };
  }
  if (bet.p_model < 0.52) {
    if ((bet.kurs ?? 0) >= 1.9) {
      return {
        label: "◆ perełka",
        cls: "bg-data-amber-wash text-[#8a5613]",
        opis: "Wyższy kurs (1,9+) przy wciąż sensownej szansie — okazjonalny rodzynek na kupon, nie pewniak",
      };
    }
    return {
      label: "ryzykowny",
      cls: "bg-paper text-muted",
      opis: "Szansa modelu poniżej 52% bez wysokiego kursu — najsłabsza kategoria, traktuj ostrożnie",
    };
  }
  if (bet.p_model >= 0.75) {
    return {
      label: "★ pewniak",
      cls: "bg-brand-wash text-brand-deep",
      opis: "Szansa modelu 75%+ — najmocniejsza kategoria typów",
    };
  }
  if (bet.p_model >= 0.62) {
    return {
      label: "mocny typ",
      cls: "bg-data-green-wash text-brand-deep",
      opis: "Szansa modelu 62–74% — solidny typ, ale jeszcze nie pewniak",
    };
  }
  return {
    label: "umiarkowany",
    cls: "bg-paper text-muted",
    opis: "Szansa modelu 52–61% — niewiele ponad 50/50, traktuj ostrożnie",
  };
}

/** memo: przy zmianie filtrów listy nie przerenderowują się wszystkie karty */
export const BetCard = memo(function BetCard({
  bet,
  rank,
  zawodnik,
}: {
  bet: ValueBet;
  rank: number;
  zawodnik?: Zawodnik;
}) {
  const [open, setOpen] = useState(false);
  const [tracked, setTracked] = useState(false);
  const reduced = useReducedMotion();

  useEffect(() => {
    setTracked(isTracked(bet.id));
    return onZakladyChange(() => setTracked(isTracked(bet.id)));
  }, [bet.id]);

  const forma = zawodnik?.forma[bet.rynek_kod];
  const swiatlo = swiatloTypu(forma, bet.linia, bet.p_model);

  return (
    <motion.article
      layout={!reduced}
      className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-shadow hover:shadow-(--shadow-card-hover)"
    >
      {/* sygnalizacja świetlna — triage wzrokiem przy przewijaniu listy */}
      {swiatlo && (
        <span
          aria-hidden
          title={SWIATLO_STYL[swiatlo].opis}
          className={`absolute inset-y-0 left-0 z-10 w-1 ${SWIATLO_STYL[swiatlo].pasek}`}
        />
      )}
      {/* wiersz główny */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-x-3 gap-y-2 px-3.5 py-3 text-left sm:grid-cols-[auto_1.4fr_1fr_auto_auto] sm:gap-x-4 sm:px-4"
      >
        <span
          aria-hidden
          className="font-data hidden w-7 text-right text-sm text-faint sm:block"
        >
          {rank}
        </span>

        <span className="min-w-0">
          <span className="block truncate font-semibold">
            {bet.podmiot}
            <span className="ml-2 font-normal text-muted">
              {bet.rynek.toLowerCase()} {STRONA_LABEL[bet.strona]}{" "}
              {fmtLinia(bet.linia)}
            </span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-faint">
            {bet.mecz} · {fmtDataCzas(bet.kickoff_ts)}
          </span>
        </span>

        <span className="hidden min-w-0 items-center gap-3 sm:flex">
          <span className="w-full max-w-48">
            <ChanceBar p={bet.p_model} line={bet.linia} side={bet.strona} />
          </span>
        </span>

        <span className="flex flex-col items-end gap-0.5">
          <span className="font-data text-base font-semibold">
            {bet.kurs != null ? fmtKurs(bet.kurs) : fmtProc(bet.p_model)}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-faint">
            {bet.kurs != null ? bet.bukmacher : "szansa modelu"}
          </span>
        </span>

        <span className="flex items-center justify-end gap-2.5">
          <span className="flex flex-col items-end gap-1">
            {bet.pewniak ? (
              (() => {
                const t = tierPewniaka(bet);
                return (
                  <span
                    className={`font-data inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${t.cls}`}
                    title={t.opis}
                  >
                    {t.label} · {fmtProc(bet.p_model)}
                  </span>
                );
              })()
            ) : bet.sugestia || bet.ev_pct == null ? (
              <span
                className="inline-flex items-center rounded-md bg-data-amber-wash px-2 py-0.5 text-xs font-semibold text-[#8a5613]"
                title="Rynek dostępny w STS — sprawdź kurs ręcznie"
              >
                sprawdź w STS
              </span>
            ) : (
              <EdgeBadge ev={bet.ev_pct} />
            )}
            {!bet.sugestia && bet.ev_uk != null && bet.ev_uk >= 4 ? (
              <span
                className="hidden rounded-md bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep sm:inline-flex"
                title={`Uczciwa cena wg no-vig UK (mediana buków po zdjęciu marży) to ~${fmtKurs(bet.kurs_novig ?? 0)}. Superbet płaci +${bet.ev_uk.toFixed(1).replace(".", ",")}% wartości ponad ten benchmark — to sygnał miękkiej linii.`}
              >
                ↑ +{Math.round(bet.ev_uk)}% vs UK
              </span>
            ) : !bet.sugestia &&
              bet.kurs != null &&
              bet.kurs_ref != null &&
              bet.kurs >= bet.kurs_ref * 1.12 ? (
              <span
                className="hidden rounded-md bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep sm:inline-flex"
                title={`Bukmacherzy w UK płacą za to średnio ${fmtKurs(bet.kurs_ref)} — kurs Superbetu wyraźnie odstaje w górę`}
              >
                ↑ odstaje od rynku
              </span>
            ) : null}
            {bet.matchup && (
              <span
                className="inline-flex rounded-md bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep"
                title="Profil rywala wyraźnie sprzyja temu rynkowi (co ta drużyna dopuszcza zawodnikom z tej formacji) — liczby w rozwinięciu karty, czynnik „Profil rywala”"
              >
                🎯 matchup
              </span>
            )}
            {bet.rotacja && (
              <span
                className="inline-flex rounded-md bg-data-amber-wash px-1.5 py-0.5 text-[10px] font-semibold text-[#8a5613]"
                title="Pierwszy występ w XI na tym turnieju — rynek często nie zdążył dograć jego linii; baza modelu z sezonu klubowego"
              >
                ⬆ wchodzi do składu
              </span>
            )}
            {bet.swieze_sklady && (
              <span
                className="inline-flex rounded-md bg-data-amber-wash px-1.5 py-0.5 text-[10px] font-semibold text-[#8a5613]"
                title="Składy tego meczu potwierdzono w ostatnich ~45 minutach — kursy bywają jeszcze sprzed ogłoszenia XI"
              >
                🕐 świeże składy
              </span>
            )}
            {bet.miekka_linia && (
              <span
                className="inline-flex rounded-md bg-brand-wash px-1.5 py-0.5 text-[10px] font-semibold text-brand-deep"
                title={`Z pozostałych linii Superbetu na ten rynek wynika kurs ~${(bet.kurs_oczekiwany ?? 0).toFixed(2).replace(".", ",")} — ta linia płaci wyraźnie więcej (niespójność siatki bukmachera)`}
              >
                ↑ miękka linia
              </span>
            )}
            <span
              className="hidden items-center gap-1 text-[10px] text-faint sm:flex"
              title="Pewność modelu: ile danych i jak stabilnych stoi za tą predykcją"
            >
              <PewnoscDots level={bet.pewnosc} />
              {PEWNOSC_LABEL[bet.pewnosc]} pewność
            </span>
          </span>
          <span className="flex flex-col items-center gap-0.5">
            <svg
              aria-hidden
              width="14"
              height="14"
              viewBox="0 0 14 14"
              className={`text-faint transition-transform ${open ? "rotate-180" : ""}`}
            >
              <path
                d="M3 5.5 L7 9.5 L11 5.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="hidden text-[9px] uppercase tracking-wide text-faint sm:block">
              {open ? "zwiń" : "detale"}
            </span>
          </span>
        </span>
      </button>

      {/* szczegóły */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          >
            <div className="grid gap-6 border-t border-hairline bg-paper/50 px-4 py-5 sm:grid-cols-2 sm:px-6">
              {/* lewa: podsumowanie po ludzku i uzasadnienie */}
              <div className="space-y-4">
                {bet.sugestia ? (
                  <div className="rounded-lg border border-data-amber/40 bg-data-amber-wash px-3.5 py-3 text-sm leading-relaxed text-[#6d4410]">
                    Model daje temu zdarzeniu{" "}
                    <strong className="font-data">{fmtProc(bet.p_model)}</strong>{" "}
                    szans, czyli uczciwy kurs to{" "}
                    <strong className="font-data">{fmtKurs(bet.fair_kurs)}</strong>.
                    <span className="mt-1.5 block">
                      Kursu nie pobieramy automatycznie (rynek tylko w STS) —{" "}
                      <strong>
                        wartość jest, gdy STS płaci więcej niż ~
                        <span className="font-data">
                          {fmtKurs(bet.fair_kurs * 1.05)}
                        </span>
                      </strong>
                      . Im wyższy kurs, tym lepsza okazja.
                    </span>
                  </div>
                ) : (
                  <div className="rounded-lg border border-brand/20 bg-brand-wash px-3.5 py-3 text-sm leading-relaxed text-brand-deep">
                    Model daje temu zdarzeniu{" "}
                    <strong className="font-data">{fmtProc(bet.p_model)}</strong>{" "}
                    szans, czyli uczciwy kurs to{" "}
                    <strong className="font-data">{fmtKurs(bet.fair_kurs)}</strong>.{" "}
                    {bet.bukmacher} płaci{" "}
                    <strong className="font-data">
                      {bet.kurs != null ? fmtKurs(bet.kurs) : "—"}
                    </strong>
                    {bet.ev_pct != null && bet.ev_pct >= 1 && (
                      <>
                        {" "}
                        — o <strong className="font-data">{fmtEV(bet.ev_pct)}</strong>{" "}
                        więcej, niż wynosi uczciwa wycena. To jest matematyczna
                        przewaga tego typu
                      </>
                    )}
                    {bet.ev_pct != null &&
                      bet.ev_pct > -1 &&
                      bet.ev_pct < 1 && (
                        <> — niemal dokładnie tyle, ile wynosi uczciwa wycena</>
                      )}
                    {bet.ev_pct != null && bet.ev_pct <= -1 && (
                      <>
                        {" "}
                        — o{" "}
                        <strong className="font-data">
                          {Math.abs(bet.ev_pct).toFixed(1).replace(".", ",")}%
                        </strong>{" "}
                        mniej, niż wynosi uczciwa wycena. Kurs nie daje
                        matematycznej przewagi — ten typ jest na liście dla
                        wysokiej szansy trafienia, nie dla wartości
                      </>
                    )}
                    .
                    {bet.kurs_ref != null && (
                      <span className="mt-1.5 block text-xs text-muted">
                        Bukmacherzy w UK płacą za to średnio{" "}
                        <span className="font-data font-medium text-ink-soft">
                          {fmtKurs(bet.kurs_ref)}
                        </span>
                        {bet.kurs_novig != null && (
                          <>
                            {" "}
                            (uczciwa cena po zdjęciu marży ~
                            <span className="font-data font-medium text-ink-soft">
                              {fmtKurs(bet.kurs_novig)}
                            </span>
                            )
                          </>
                        )}
                        {bet.ev_uk != null && bet.ev_uk >= 4 ? (
                          <>
                            {" "}
                            — Superbet daje{" "}
                            <strong className="font-data">
                              +{bet.ev_uk.toFixed(1).replace(".", ",")}%
                            </strong>{" "}
                            wartości ponad ten no-vig benchmark, to sygnał miękkiej
                            linii.
                          </>
                        ) : (
                          bet.kurs != null &&
                          bet.kurs_ref != null &&
                          bet.kurs >= bet.kurs_ref * 1.12 && (
                            <>
                              {" "}
                              — <strong>Superbet wyraźnie odstaje w górę</strong>.
                            </>
                          )
                        )}
                      </span>
                    )}
                  </div>
                )}
                {!bet.sugestia && bet.ci[0] != null && (
                  <p className="text-xs text-muted">
                    Widełki szansy:{" "}
                    <span className="font-data">
                      {fmtProc(bet.ci[0])}–{fmtProc(bet.ci[1] as number)}
                    </span>{" "}
                    — im węższe, tym stabilniejsza predykcja.
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-3">
                  <ConfidenceBadge level={bet.pewnosc} />
                  <RiskBadge level={bet.ryzyko} />
                </div>

                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                    Dlaczego ten zakład
                  </h4>
                  <ul className="space-y-1.5">
                    {bet.uzasadnienie.czynniki.map((c) => (
                      <li
                        key={c.nazwa}
                        className="flex items-start justify-between gap-3 text-sm"
                      >
                        <span>
                          <span className="font-medium">{c.nazwa}:</span>{" "}
                          <span className="text-ink-soft">{c.opis}</span>
                        </span>
                        {c.mnoznik !== null && (
                          <span
                            className={`font-data shrink-0 rounded px-1.5 py-0.5 text-xs ${
                              c.mnoznik > 1.02
                                ? "bg-data-green-wash text-brand-deep"
                                : c.mnoznik < 0.98
                                  ? "bg-data-red-wash text-data-red"
                                  : "bg-paper text-muted"
                            }`}
                          >
                            {fmtMnoznik(c.mnoznik)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* prawa: wykresy */}
              <div className="space-y-5">
                {bet.rozklad && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Możliwe wyniki i ich szanse
                    </h4>
                    <OutcomeColumns
                      dist={bet.rozklad}
                      line={bet.linia}
                      side={bet.strona}
                    />
                  </div>
                )}
                {bet.rozklad && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Szanse na inne linie wg modelu
                    </h4>
                    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                      {[0.5, 1.5, 2.5, 3.5].map((l) => {
                        const total =
                          bet.rozklad!.reduce((a, b) => a + b, 0) || 1;
                        const p =
                          bet.rozklad!
                            .slice(Math.floor(l) + 1)
                            .reduce((a, b) => a + b, 0) / total;
                        const aktualna = Math.abs(l - bet.linia) < 0.01;
                        if (p < 0.02 && !aktualna) return null;
                        return (
                          <div
                            key={l}
                            className={`rounded-lg border px-2.5 py-2 text-center ${
                              aktualna
                                ? "border-brand/40 bg-brand-wash"
                                : "border-hairline bg-card"
                            }`}
                            title={
                              aktualna
                                ? "Linia tego typu"
                                : `Szansa modelu na powyżej ${fmtLinia(l)}`
                            }
                          >
                            <p className="text-[10px] uppercase tracking-wide text-faint">
                              pow. {fmtLinia(l)}
                            </p>
                            <p
                              className={`font-data text-sm font-semibold ${
                                aktualna ? "text-brand-deep" : "text-ink"
                              }`}
                            >
                              {fmtProc(p)}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {forma && (() => {
                  const okna = oknaFormy(forma, bet.linia);
                  const zagrane = okna.zagrane;
                  // okna jak w Props.cash/StatsHub: forma TERAZ vs średnia —
                  // L5 wykrywa trend, którego jedna suma nie pokaże
                  const chipy = [
                    ...(zagrane >= 3 ? [{ label: "L5", ...okna.l5 }] : []),
                    ...(zagrane >= 7 ? [{ label: "L10", ...okna.l10 }] : []),
                    { label: "razem", ...okna.all },
                  ];
                  return (
                    <div className="rounded-xl border border-hairline bg-card p-4">
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5">
                        <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
                          Ostatnie mecze — {bet.rynek.toLowerCase()}
                        </h4>
                        {zagrane > 0 && (
                          <span
                            className="flex items-center gap-1"
                            title={`Jak często linia ${fmtLinia(bet.linia)} była przebijana: w ostatnich 5 / 10 / wszystkich meczach z minutami`}
                          >
                            {chipy.map((c) => {
                              const r = c.n > 0 ? c.traf / c.n : 0;
                              return (
                                <span
                                  key={c.label}
                                  className={`font-data inline-flex items-baseline gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${
                                    c.n >= 3 && r >= 0.6
                                      ? "bg-data-green-wash text-brand-deep"
                                      : c.n >= 3 && r < 0.45
                                        ? "bg-data-red-wash text-data-red"
                                        : "bg-paper text-muted"
                                  }`}
                                >
                                  <span className="text-[9px] font-medium uppercase opacity-70">
                                    {c.label}
                                  </span>
                                  {c.traf}/{c.n}
                                </span>
                              );
                            })}
                          </span>
                        )}
                      </div>
                      <FormBars
                        counts={forma.ostatnie}
                        minutes={forma.minuty}
                        opponents={forma.rywale}
                        kadra={forma.kadra}
                        line={bet.linia}
                        height={64}
                      />
                      <p className="mt-2 text-xs text-faint">
                        Średnio{" "}
                        <span className="font-data text-ink-soft">
                          {forma.srednia90.toFixed(2).replace(".", ",")}
                        </span>{" "}
                        na 90 minut{" "}
                        <span title="Liczba ostatnich meczów z minutami, z których policzona jest średnia (klub + reprezentacja)">
                          (próba: {zagrane}{" "}
                          {zagrane === 1 ? "mecz" : zagrane < 5 ? "mecze" : "meczów"})
                        </span>{" "}
                        · przewidywane minuty:{" "}
                        <span className="font-data text-ink-soft">
                          {bet.oczekiwane_minuty != null
                            ? Math.round(bet.oczekiwane_minuty)
                            : "—"}
                        </span>
                      </p>
                    </div>
                  );
                })()}
                {bet.sugestia ? (
                  <p className="rounded-lg border border-hairline bg-card px-3 py-2.5 text-center text-xs leading-relaxed text-muted">
                    Otwórz STS → wyszukaj zawodnika → sprawdź kurs tego rynku.
                    Kurs powyżej{" "}
                    <span className="font-data font-semibold text-ink">
                      ~{fmtKurs(bet.fair_kurs * 1.05)}
                    </span>
                    ? Jest wartość — dodaj zakład w „Moich zakładach”.
                  </p>
                ) : (
                  <button
                    onClick={() => addZakladFromBet(bet, null)}
                    disabled={tracked}
                    className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
                      tracked
                        ? "cursor-default bg-brand-wash text-brand"
                        : "bg-brand text-white hover:bg-brand-deep"
                    }`}
                  >
                    {tracked ? "✓ W moich zakładach" : "Dodaj do moich zakładów"}
                  </button>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
