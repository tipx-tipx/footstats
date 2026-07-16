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
 * Splity kontekstowe z formy: hit-rate linii w podpróbkach, które dane
 * uczciwie wspierają (kadra vs klub, pełne występy 60+ min). Pokazujemy
 * split dopiero od 3 meczów — mniejsza próba myli bardziej, niż pomaga.
 */
function splityFormy(forma: FormaRynku, linia: number) {
  const gry = forma.ostatnie.map((v, i) => ({
    v,
    min: forma.minuty[i] ?? 0,
    kadra: forma.kadra?.[i] ?? false,
  }));
  const licz = (xs: { v: number }[]) => ({
    traf: xs.filter((x) => x.v > linia).length,
    n: xs.length,
  });
  const zagrane = gry.filter((g) => g.min > 0);
  const wynik: { label: string; opis: string; traf: number; n: number }[] = [];
  const kadra = licz(zagrane.filter((g) => g.kadra));
  const klub = licz(zagrane.filter((g) => !g.kadra));
  // splity kadra/klub tylko gdy OBA mają próbę — inaczej to zwykłe "razem"
  if (kadra.n >= 3 && klub.n >= 3) {
    wynik.push(
      { label: "kadra", opis: "mecze reprezentacji w próbce", ...kadra },
      { label: "klub", opis: "mecze klubowe w próbce", ...klub },
    );
  }
  const pelne = licz(zagrane.filter((g) => g.min >= 60));
  if (pelne.n >= 3 && pelne.n < zagrane.length) {
    wynik.push({
      label: "pełne występy",
      opis: "mecze z co najmniej 60 minutami gry",
      ...pelne,
    });
  }
  return wynik;
}

/**
 * Odznaki przewagi — policzalny system sygnałów typu (wzorzec Linemate:
 * każdy typ nosi 0–4 odznaki). Jedno źródło prawdy dla wiersza karty
 * (chipy) i rozwinięcia (lista z wyjaśnieniami).
 */
function odznakiPrzewagi(bet: ValueBet): {
  znak: string;
  label: string;
  opis: string;
  tone: "brand" | "amber";
}[] {
  const o: ReturnType<typeof odznakiPrzewagi> = [];
  if (!bet.sugestia && bet.ev_uk != null && bet.ev_uk >= 4) {
    o.push({
      znak: "↑",
      label: `+${Math.round(bet.ev_uk)}% vs UK`,
      opis: `Uczciwa cena wg bukmacherów UK (po zdjęciu marży) to ~${fmtKurs(bet.kurs_novig ?? 0)}, a Superbet płaci +${bet.ev_uk.toFixed(1).replace(".", ",")}% ponad ten poziom`,
      tone: "brand",
    });
  } else if (
    !bet.sugestia &&
    bet.kurs != null &&
    bet.kurs_ref != null &&
    bet.kurs >= bet.kurs_ref * 1.12
  ) {
    o.push({
      znak: "↑",
      label: "odstaje od rynku",
      opis: `Bukmacherzy w UK płacą za to średnio ${fmtKurs(bet.kurs_ref)}, a kurs Superbetu wyraźnie odstaje w górę`,
      tone: "brand",
    });
  }
  if (bet.matchup) {
    o.push({
      znak: "◎",
      label: "matchup",
      opis: "Profil rywala wyraźnie sprzyja temu rynkowi (co ta drużyna dopuszcza zawodnikom z tej formacji). Liczby w czynniku „Profil rywala”",
      tone: "brand",
    });
  }
  if (bet.miekka_linia) {
    o.push({
      znak: "↗",
      label: "miękka linia",
      opis: `Z pozostałych linii Superbetu na ten rynek wynika kurs ~${(bet.kurs_oczekiwany ?? 0).toFixed(2).replace(".", ",")}, a ta linia płaci wyraźnie więcej (niespójność siatki bukmachera)`,
      tone: "brand",
    });
  }
  if (bet.rotacja) {
    o.push({
      znak: "↥",
      label: "wchodzi do składu",
      opis: "Pierwszy występ w XI na tym turnieju, rynek często nie zdążył dograć jego linii",
      tone: "amber",
    });
  }
  if (bet.swieze_sklady) {
    o.push({
      znak: "◷",
      label: "świeże składy",
      opis: "Składy potwierdzono w ostatnich ~45 minutach, więc kursy bywają jeszcze sprzed ogłoszenia XI",
      tone: "amber",
    });
  }
  return o;
}

/**
 * Historia vs model vs wycena kursu na JEDNEJ skali — kotwica zaufania
 * (standard kategorii: props.cash). Trzy znaczniki na wspólnym torze
 * 0–100% + wartości pod spodem. Wycena kursu = 1/kurs (z marżą — uczciwie
 * opisane w tooltipie).
 */
function PorownanieWycen({
  historia,
  model,
  kurs,
}: {
  historia: { traf: number; n: number } | null;
  model: number;
  kurs: number | null;
}) {
  const hist = historia && historia.n >= 3 ? historia.traf / historia.n : null;
  const implied = kurs != null && kurs > 1 ? 1 / kurs : null;
  if (implied == null && hist == null) return null;
  const znaczniki = [
    ...(hist != null
      ? [{ p: hist, label: `historia ${historia!.traf}/${historia!.n}`, kolor: "var(--color-data-green)" }]
      : []),
    { p: model, label: "model", kolor: "var(--color-brand)" },
    ...(implied != null
      ? [{ p: implied, label: "kurs wycenia", kolor: "var(--color-ink)" }]
      : []),
  ];
  return (
    <div
      className="rounded-(--radius-control) border border-hairline bg-card p-3.5"
      title="Trzy spojrzenia na tę samą szansę: jak często wchodziło w ostatnich meczach, ile daje model i na ile wycenia to kurs bukmachera (wycena z kursu zawiera marżę, więc realna opinia rynku jest odrobinę niższa). Gdy historia i model stoją WYŻEJ niż wycena kursu, bukmacher płaci za dużo."
    >
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-wide text-faint">
        Historia · model · wycena kursu
      </h4>
      <div className="relative mx-1 h-6">
        {/* tor */}
        <span className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-hairline" />
        {/* znacznik 50% */}
        <span className="absolute left-1/2 top-1/2 h-3.5 w-px -translate-y-1/2 bg-hairline-strong" />
        {znaczniki.map((z) => (
          <span
            key={z.label}
            className="absolute top-1/2 h-6 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ left: `${Math.min(Math.max(z.p * 100, 2), 98)}%`, background: z.kolor }}
          />
        ))}
      </div>
      <dl className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
        {znaczniki.map((z) => (
          <div key={z.label} className="flex items-baseline gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2 w-2 translate-y-px rounded-full"
              style={{ background: z.kolor }}
            />
            <dt className="text-[11px] text-faint">{z.label}</dt>
            <dd className="font-data text-sm font-semibold text-ink">
              {fmtProc(z.p)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
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
    opis: "Żółte światło: historia i model nie mówią jednym głosem. Przeczytaj szczegóły",
  },
  red: {
    pasek: "bg-data-red",
    opis: "Czerwone światło: linia przebita w mniej niż 45% ostatnich 10 meczów. Historia przeczy typowi",
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
        cls: "bg-data-amber-wash text-data-amber-ink",
        opis: "Wyższa linia przy szansie 40–52% i kursie 1,9+: świadomie ryzykowny wariant typu bazowego, nie pewniak",
      };
    }
    return {
      label: "✦ wyższa linia",
      cls: "bg-data-amber-wash text-data-amber-ink",
      opis: "Perełka: wyższa linia (1,5+) przy wciąż solidnej szansie i wyraźnie lepszym kursie niż na linii 0,5",
    };
  }
  if (bet.p_model < 0.52) {
    if ((bet.kurs ?? 0) >= 1.9) {
      return {
        label: "◆ perełka",
        cls: "bg-data-amber-wash text-data-amber-ink",
        opis: "Wyższy kurs (1,9+) przy wciąż sensownej szansie: okazjonalny rodzynek na kupon, nie pewniak",
      };
    }
    return {
      label: "ryzykowny",
      cls: "bg-paper text-muted",
      opis: "Szansa modelu poniżej 52% bez wysokiego kursu to najsłabsza kategoria, traktuj ostrożnie",
    };
  }
  if (bet.p_model >= 0.75) {
    return {
      label: "★ pewniak",
      cls: "bg-brand-wash text-brand-deep",
      opis: "Szansa modelu 75%+ to najmocniejsza kategoria typów",
    };
  }
  if (bet.p_model >= 0.62) {
    return {
      label: "mocny typ",
      cls: "bg-data-green-wash text-data-green-ink",
      opis: "Szansa modelu 62–74% to solidny typ, ale jeszcze nie pewniak",
    };
  }
  return {
    label: "umiarkowany",
    cls: "bg-paper text-muted",
    opis: "Szansa modelu 52–61% to niewiele ponad 50/50, traktuj ostrożnie",
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
  const odznaki = odznakiPrzewagi(bet);
  const okna = forma ? oknaFormy(forma, bet.linia) : null;
  // historia do porównania wycen: L10 gdy jest sensowna próba, inaczej całość
  const historiaOkno =
    okna == null ? null : okna.l10.n >= 5 ? okna.l10 : okna.all;

  return (
    <motion.article
      layout={!reduced}
      className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-[border-color,box-shadow] duration-200 hover:border-brand/30 hover:shadow-(--shadow-card-hover)"
    >
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group w-full text-left"
      >
        {/* wiersz główny: numer z koszulki · kto i co · szansa · kurs */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-3 pt-3.5 sm:grid-cols-[auto_1.4fr_1fr_auto] sm:px-5">
          {/* ghost-numer jak nadruk na koszulce — orientacja w rankingu bez
              kolejnego "pudełka"; przy hoverze nabiera koloru marki */}
          <span
            aria-hidden
            className="font-display hidden w-10 shrink-0 text-center text-[1.7rem] font-bold leading-none text-ink/15 transition-colors group-hover:text-brand/40 sm:block"
          >
            {rank}
          </span>

          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {/* dioda formy: historia vs model jednym rzutem oka (zamiast
                  paska na krawędzi, który ginął przy zielonych miernikach) */}
              {swiatlo && (
                <span
                  title={SWIATLO_STYL[swiatlo].opis}
                  className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
                >
                  <span
                    aria-hidden
                    className={`absolute -inset-1 rounded-full opacity-20 ${SWIATLO_STYL[swiatlo].pasek}`}
                  />
                  <span
                    aria-hidden
                    className={`h-2 w-2 rounded-full ${SWIATLO_STYL[swiatlo].pasek}`}
                  />
                </span>
              )}
              <span className="truncate font-semibold">{bet.podmiot}</span>
              <span className="text-sm text-muted">
                {bet.rynek.toLowerCase()} {STRONA_LABEL[bet.strona]}{" "}
                {fmtLinia(bet.linia)}
              </span>
            </span>
            <span className="mt-1 block truncate text-xs text-faint">
              {bet.mecz} · {fmtDataCzas(bet.kickoff_ts)}
            </span>
            {/* pasek szansy na mobile — pod nazwą, żeby triage działał też kciukiem */}
            <span className="mt-2 block max-w-56 sm:hidden">
              <ChanceBar p={bet.p_model} line={bet.linia} side={bet.strona} />
            </span>
          </span>

          <span className="hidden min-w-0 items-center sm:flex">
            <span className="w-full max-w-48">
              <ChanceBar p={bet.p_model} line={bet.linia} side={bet.strona} />
            </span>
          </span>

          {/* rubryka kursu za gradientową linią — liczba, nie przycisk;
              bez kursu: od jakiego kursu w STS typ jest wart zagrania */}
          <span
            className="relative flex flex-col items-end justify-center gap-1 self-stretch justify-self-end pl-5 sm:pl-6"
            title={
              bet.kurs == null
                ? `Otwórz STS i porównaj: kurs ~${fmtKurs(bet.fair_kurs * 1.05)} lub wyższy = warto grać, niższy = odpuść`
                : undefined
            }
          >
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 hidden w-px bg-gradient-to-b from-transparent via-hairline-strong to-transparent sm:block"
            />
            <span className="font-data text-xl font-semibold leading-none tracking-tight">
              {bet.kurs != null ? fmtKurs(bet.kurs) : `~${fmtKurs(bet.fair_kurs * 1.05)}`}
            </span>
            <span className="text-[9px] uppercase tracking-wide text-faint">
              {bet.kurs != null ? bet.bukmacher : "dobry kurs od"}
            </span>
          </span>
        </span>

        {/* linia meta: ocena typu + odznaki przewagi + pewność + detale —
            bez własnego pudełka, wcięta do kolumny nazwiska */}
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5 px-4 pb-3.5 sm:pl-[4.75rem] sm:pr-5">
          {bet.pewniak ? (
            (() => {
              const t = tierPewniaka(bet);
              return (
                <span
                  className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${t.cls}`}
                  title={t.opis}
                >
                  {t.label}
                </span>
              );
            })()
          ) : bet.sugestia || bet.ev_pct == null ? (
            <span
              className="inline-flex items-center rounded-full bg-data-amber-wash px-2.5 py-0.5 text-xs font-semibold text-data-amber-ink"
              title="Rynek dostępny w STS, sprawdź kurs ręcznie"
            >
              sprawdź w STS
            </span>
          ) : (
            <EdgeBadge ev={bet.ev_pct} />
          )}
          {/* odznaki przewagi — tekstowe odczyty HUD zamiast kolejnych
              chipów; jedno źródło prawdy (odznakiPrzewagi) */}
          {odznaki.map((o) => (
            <span
              key={o.label}
              title={o.opis}
              className={`inline-flex items-center gap-1 px-1 text-[11px] font-medium ${
                o.tone === "brand" ? "text-brand-deep" : "text-data-amber-ink"
              }`}
            >
              <span aria-hidden className="font-data">{o.znak}</span> {o.label}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-3">
            <span
              className="flex items-center gap-1 text-[10px] text-faint"
              title="Pewność modelu: ile danych i jak stabilnych stoi za tą predykcją"
            >
              <PewnoscDots level={bet.pewnosc} />
              {PEWNOSC_LABEL[bet.pewnosc]} pewność
            </span>
            <span className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
              {open ? "zwiń" : "detale"}
              <svg
                aria-hidden
                width="12"
                height="12"
                viewBox="0 0 14 14"
                className={`transition-transform ${open ? "rotate-180" : ""}`}
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
            </span>
          </span>
        </span>
      </button>

      {/* szczegóły */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          >
            <div className="grid gap-6 border-t border-hairline bg-paper/50 px-4 py-5 sm:grid-cols-2 sm:px-6">
              {/* lewa: podsumowanie po ludzku i uzasadnienie */}
              <div className="space-y-4">
                {bet.sugestia ? (
                  <div className="rounded-lg border border-data-amber/40 bg-data-amber-wash px-3.5 py-3 text-sm leading-relaxed text-data-amber-ink-strong">
                    Model daje temu zdarzeniu{" "}
                    <strong className="font-data">{fmtProc(bet.p_model)}</strong>{" "}
                    szans, czyli uczciwy kurs to{" "}
                    <strong className="font-data">{fmtKurs(bet.fair_kurs)}</strong>.
                    <span className="mt-1.5 block">
                      Kursu nie pobieramy automatycznie (rynek tylko w STS).{" "}
                      <strong>
                        Wartość jest, gdy STS płaci więcej niż ~
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
                      {bet.kurs != null ? fmtKurs(bet.kurs) : "–"}
                    </strong>
                    {bet.ev_pct != null && bet.ev_pct >= 1 && (
                      <>
                        , czyli o <strong className="font-data">{fmtEV(bet.ev_pct)}</strong>{" "}
                        więcej, niż wynosi uczciwa wycena. To jest matematyczna
                        przewaga tego typu
                      </>
                    )}
                    {bet.ev_pct != null &&
                      bet.ev_pct > -1 &&
                      bet.ev_pct < 1 && (
                        <>, czyli niemal dokładnie tyle, ile wynosi uczciwa wycena</>
                      )}
                    {bet.ev_pct != null && bet.ev_pct <= -1 && (
                      <>
                        , czyli o{" "}
                        <strong className="font-data">
                          {Math.abs(bet.ev_pct).toFixed(1).replace(".", ",")}%
                        </strong>{" "}
                        mniej, niż wynosi uczciwa wycena. Kurs nie daje
                        matematycznej przewagi. Ten typ jest na liście dla
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
                            . Superbet daje{" "}
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
                              . <strong>Superbet wyraźnie odstaje w górę</strong>.
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
                    </span>
                    . Im węższe, tym stabilniejsza predykcja.
                  </p>
                )}

                {/* kotwica zaufania: trzy wyceny na jednej skali */}
                <PorownanieWycen
                  historia={historiaOkno}
                  model={bet.p_model}
                  kurs={bet.kurs}
                />

                <div className="flex flex-wrap items-center gap-3">
                  <ConfidenceBadge level={bet.pewnosc} />
                  <RiskBadge level={bet.ryzyko} />
                </div>

                {/* przewagi tego typu — pełna lista z wyjaśnieniami */}
                {odznaki.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                      Przewagi tego typu ({odznaki.length})
                    </h4>
                    <ul className="space-y-1.5">
                      {odznaki.map((o) => (
                        <li key={o.label} className="flex items-start gap-2.5 text-sm">
                          <span
                            aria-hidden
                            className={`font-data mt-px shrink-0 ${
                              o.tone === "brand" ? "text-brand" : "text-data-amber-ink"
                            }`}
                          >
                            {o.znak}
                          </span>
                          <span>
                            <span className="font-medium">{o.label}:</span>{" "}
                            <span className="text-ink-soft">{o.opis}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

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
                            className={`font-data shrink-0 rounded-full px-1.5 py-0.5 text-xs ${
                              c.mnoznik > 1.02
                                ? "bg-data-green-wash text-data-green-ink"
                                : c.mnoznik < 0.98
                                  ? "bg-data-red-wash text-data-red-ink"
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
                          Ostatnie mecze: {bet.rynek.toLowerCase()}
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
                                      ? "bg-data-green-wash text-data-green-ink"
                                      : c.n >= 3 && r < 0.45
                                        ? "bg-data-red-wash text-data-red-ink"
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
                            : "–"}
                        </span>
                      </p>
                      {/* splity kontekstowe — jak linia wchodzi w podpróbkach */}
                      {(() => {
                        const splity = splityFormy(forma, bet.linia);
                        if (splity.length === 0) return null;
                        return (
                          <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-hairline pt-3">
                            <span className="mr-0.5 text-[10px] font-semibold uppercase tracking-wide text-faint">
                              splity
                            </span>
                            {splity.map((s) => {
                              const r = s.traf / s.n;
                              return (
                                <span
                                  key={s.label}
                                  title={`${s.opis}: linia ${fmtLinia(bet.linia)} przebita w ${s.traf} z ${s.n} meczów`}
                                  className={`font-data inline-flex items-baseline gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                                    r >= 0.6
                                      ? "bg-data-green-wash text-data-green-ink"
                                      : r < 0.45
                                        ? "bg-data-red-wash text-data-red-ink"
                                        : "bg-paper text-muted"
                                  }`}
                                >
                                  <span className="text-[9px] font-medium uppercase opacity-70">
                                    {s.label}
                                  </span>
                                  {s.traf}/{s.n}
                                </span>
                              );
                            })}
                          </div>
                        );
                      })()}
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
                    ? Jest wartość. Dodaj zakład w „Moich zakładach”.
                  </p>
                ) : (
                  <button
                    onClick={() => addZakladFromBet(bet, null)}
                    disabled={tracked}
                    className={`w-full rounded-(--radius-control) px-4 py-2.5 text-sm font-semibold transition-colors ${
                      tracked
                        ? "cursor-default bg-brand-wash text-brand"
                        : "bg-brand text-on-brand shadow-(--shadow-card) hover:bg-brand-strong"
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
