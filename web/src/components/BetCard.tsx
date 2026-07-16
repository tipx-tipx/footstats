"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useEffect, useState } from "react";

import { EdgeBadge, PewnoscDots, RiskBadge } from "./badges";
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
import type { FormaRynku, Strona, ValueBet, Zawodnik } from "@/lib/types";

/** Czy wynik z meczu wszedłby w ten typ (strona typu, nie zawsze „powyżej”). */
const wchodzi = (v: number, linia: number, strona: Strona) =>
  strona === "ponizej" ? v < linia : v > linia;

/** Hit-rate linii w oknach czasowych (mecze z minutami, od najnowszych). */
function oknaFormy(forma: FormaRynku, linia: number, strona: Strona) {
  const zagrane = forma.ostatnie
    .map((v, i) => ({ v, min: forma.minuty[i] ?? 0 }))
    .filter((x) => x.min > 0);
  const okno = (n: number) => {
    const w = zagrane.slice(0, n);
    return { traf: w.filter((x) => wchodzi(x.v, linia, strona)).length, n: w.length };
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
function splityFormy(forma: FormaRynku, linia: number, strona: Strona) {
  const gry = forma.ostatnie.map((v, i) => ({
    v,
    min: forma.minuty[i] ?? 0,
    kadra: forma.kadra?.[i] ?? false,
  }));
  const licz = (xs: { v: number }[]) => ({
    traf: xs.filter((x) => wchodzi(x.v, linia, strona)).length,
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

/** Pozycja na torze 0–100% z marginesem, żeby znacznik nie uciekał za krawędź. */
const pozNaTorze = (p: number) => Math.min(Math.max(p * 100, 2), 98);

/**
 * Werdykt: trzy liczby, po które user w ogóle otwiera detale. Gołe liczby
 * za pionowymi liniami (język kolumny kursu z wiersza), nie wash-box z prozą.
 */
function Werdykt({ bet }: { bet: ValueBet }) {
  const brakKursu = bet.sugestia || bet.kurs == null;
  const ev = bet.ev_pct;
  const pola: { label: string; val: string; kolor: string }[] = brakKursu
    ? [
        { label: "uczciwy kurs", val: fmtKurs(bet.fair_kurs), kolor: "text-ink" },
        {
          label: "dobry kurs od",
          val: `~${fmtKurs(bet.fair_kurs * 1.05)}`,
          kolor: "text-brand-deep",
        },
      ]
    : [
        { label: "uczciwy kurs", val: fmtKurs(bet.fair_kurs), kolor: "text-ink" },
        {
          label: `${bet.bukmacher.toLowerCase()} płaci`,
          val: fmtKurs(bet.kurs as number),
          kolor: "text-ink",
        },
        ...(ev != null
          ? [
              {
                label: ev >= 1 ? "twoja przewaga" : "przewaga",
                val: fmtEV(ev),
                kolor:
                  ev >= 1
                    ? "text-data-green-ink"
                    : ev <= -1
                      ? "text-data-red-ink"
                      : "text-muted",
              },
            ]
          : []),
      ];

  return (
    <div>
      {/* liczby rozdzielone pionową kreską — bez pudełek, jak rubryka kursu;
          max-w trzyma je jako jedną grupę zamiast rozrzucać po całej karcie */}
      <dl className="flex max-w-xl items-stretch">
        {pola.map((p, i) => (
          // flex-col + mt-auto: gdy label łamie się na dwie linie (mobile),
          // liczby i tak stoją na jednej linii bazowej
          <div
            key={p.label}
            className={`flex flex-1 flex-col ${
              i > 0 ? "border-l border-hairline pl-4 sm:pl-5" : ""
            } ${i < pola.length - 1 ? "pr-4 sm:pr-5" : ""}`}
          >
            <dt className="text-[10px] uppercase tracking-wide text-faint">
              {p.label}
            </dt>
            <dd
              className={`font-data mt-auto pt-1 text-2xl font-semibold leading-none tracking-tight ${p.kolor}`}
            >
              {p.val}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-soft">
        {zdanieWerdyktu(bet)}
      </p>
      {!brakKursu && bet.kurs_ref != null && <LiniaUK bet={bet} />}
    </div>
  );
}

/** Werdykt po ludzku: jedno zdanie zamiast akapitu żargonu. */
function zdanieWerdyktu(bet: ValueBet): string {
  const p = fmtProc(bet.p_model);
  if (bet.sugestia || bet.kurs == null) {
    return `Model daje temu zdarzeniu ${p} szans, więc uczciwa cena to ${fmtKurs(
      bet.fair_kurs,
    )}. Kursu nie pobieramy automatycznie, bo ten rynek jest tylko w STS. Jeśli STS płaci powyżej ~${fmtKurs(
      bet.fair_kurs * 1.05,
    )}, masz przewagę. Im wyżej, tym lepiej.`;
  }
  const wycena = fmtProc(1 / bet.kurs);
  const ev = bet.ev_pct;
  if (ev != null && ev >= 1) {
    return `Model daje temu zdarzeniu ${p} szans, a kurs ${fmtKurs(
      bet.kurs,
    )} wycenia je na ${wycena}. Bukmacher płaci więcej, niż powinien, i ta różnica jest twoją przewagą.`;
  }
  if (ev != null && ev <= -1) {
    return `Model daje temu zdarzeniu ${p} szans, a kurs ${fmtKurs(
      bet.kurs,
    )} wycenia je aż na ${wycena}. Ten kurs nie daje przewagi. Typ jest na liście za wysoką szansę trafienia, nie za wartość.`;
  }
  return `Model daje temu zdarzeniu ${p} szans, a kurs ${fmtKurs(
    bet.kurs,
  )} wycenia je na ${wycena}. Cena jest praktycznie uczciwa, bez przewagi po żadnej stronie.`;
}

/** Niezależny dowód: co za ten sam typ płaci rynek brytyjski. */
function LiniaUK({ bet }: { bet: ValueBet }) {
  const odstaje =
    bet.kurs != null && bet.kurs_ref != null && bet.kurs >= bet.kurs_ref * 1.12;
  return (
    <p className="mt-2 max-w-prose text-xs leading-relaxed text-faint">
      Bukmacherzy w UK płacą za to średnio{" "}
      <span className="font-data text-ink-soft">{fmtKurs(bet.kurs_ref as number)}</span>
      {bet.kurs_novig != null && (
        <>
          , a uczciwa cena po zdjęciu ich marży to{" "}
          <span className="font-data text-ink-soft">{fmtKurs(bet.kurs_novig)}</span>
        </>
      )}
      .{" "}
      {bet.ev_uk != null && bet.ev_uk >= 4 ? (
        <>
          {bet.bukmacher} daje{" "}
          <span className="font-data font-semibold text-data-green-ink">
            +{bet.ev_uk.toFixed(1).replace(".", ",")}%
          </span>{" "}
          ponad ten poziom, czyli jego linia jest miękka.
        </>
      ) : (
        odstaje && (
          <span className="text-data-green-ink">
            {bet.bukmacher} wyraźnie odstaje w górę.
          </span>
        )
      )}
    </p>
  );
}

/**
 * Dowód: historia, model i wycena kursu na JEDNEJ skali 0–100% (kotwica
 * zaufania, standard kategorii). Bez ramki, bo to bohater rozwinięcia:
 *   zielony odcinek  = ile bukmacher przepłaca (teza produktu jako odległość),
 *   znaczniki        = trzy spojrzenia dojeżdżające animacją przy otwarciu.
 *
 * Świadomie BEZ strefy `ci` na torze: ci to przedział szansy przy
 * przewidywanych minutach (engine.py liczy go dla mm.expected_minutes),
 * a p_model to mieszanka po scenariuszach minut (minutes.p_over_mixture),
 * więc ci NIE jest przedziałem wokół p_model i bywa całkiem obok niego
 * (w demo 11/39 typów). Narysowany jako strefa wyglądałby na błąd —
 * liczby zostają w tooltipie znacznika, uczciwie opisane.
 */
function TorDowodu({
  bet,
  historia,
}: {
  bet: ValueBet;
  historia: { traf: number; n: number } | null;
}) {
  const hist = historia && historia.n >= 3 ? historia.traf / historia.n : null;
  const implied = bet.kurs != null && bet.kurs > 1 ? 1 / bet.kurs : null;
  const model = bet.p_model;
  const ci = bet.ci[0] != null ? ([bet.ci[0], bet.ci[1]] as [number, number]) : null;
  if (implied == null && hist == null) return null;

  const przewaga =
    implied != null && model > implied
      ? { od: pozNaTorze(implied), do: pozNaTorze(model) }
      : null;
  const pokazEtykiete = przewaga != null && bet.ev_pct != null && bet.ev_pct >= 1;

  // historia jest „duchem”: cieńsza i przygaszona, żeby dwie zielenie
  // (brand modelu i data-green historii) nie konkurowały ze sobą na torze
  const znaczniki = [
    ...(hist != null
      ? [
          {
            p: hist,
            label: `historia ${historia!.traf}/${historia!.n}`,
            klasa: "bg-data-green/70",
            slaby: true,
            tytul: `W ${historia!.traf} z ostatnich ${historia!.n} meczów ten typ by wszedł`,
          },
        ]
      : []),
    {
      p: model,
      label: "szansa wg modelu",
      klasa: "bg-brand",
      slaby: false,
      tytul: ci
        ? `Model daje ${fmtProc(model)}. Gdyby zawodnik zagrał przewidywane ${
            bet.oczekiwane_minuty != null ? Math.round(bet.oczekiwane_minuty) : "wszystkie"
          } minut, szansa mieściłaby się w ${fmtProc(ci[0])}–${fmtProc(
            ci[1],
          )}. Model podaje ostrożniejszą liczbę, bo wlicza też ryzyko, że zagra krócej`
        : `Model daje ${fmtProc(model)}`,
    },
    ...(implied != null
      ? [
          {
            p: implied,
            label: "kurs wycenia",
            klasa: "bg-ink",
            slaby: false,
            tytul: `Kurs ${fmtKurs(bet.kurs as number)} odpowiada szansie ${fmtProc(
              implied,
            )} (z marżą bukmachera, więc realna opinia rynku jest odrobinę niższa)`,
          },
        ]
      : []),
  ];

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
          Trzy spojrzenia na tę samą szansę
        </h4>
        <RiskBadge level={bet.ryzyko} />
      </div>

      {/* etykieta przewagi siedzi nad swoim odcinkiem, nie w legendzie */}
      <div className="relative h-4">
        {pokazEtykiete && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.3 }}
            className="font-data absolute -translate-x-1/2 whitespace-nowrap text-[10px] font-semibold text-data-green-ink"
            style={{
              left: `${Math.min(Math.max((przewaga!.od + przewaga!.do) / 2, 12), 88)}%`,
            }}
          >
            {fmtEV(bet.ev_pct as number)} wartości
          </motion.span>
        )}
      </div>

      <div className="relative h-6">
        {/* tor */}
        <span
          aria-hidden
          className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-hairline"
        />
        {/* ile bukmacher przepłaca */}
        {przewaga && (
          <motion.span
            aria-hidden
            initial={{ width: 0 }}
            animate={{ width: `${przewaga.do - przewaga.od}%` }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-data-green/45"
            style={{ left: `${przewaga.od}%` }}
          />
        )}
        {/* podziałki: 50% mocniej (rzut monetą), ćwiartki subtelnie */}
        {[25, 50, 75].map((x) => (
          <span
            key={x}
            aria-hidden
            className={`absolute top-1/2 w-px -translate-y-1/2 ${
              x === 50 ? "h-4 bg-hairline-strong" : "h-2.5 bg-hairline-strong/60"
            }`}
            style={{ left: `${x}%` }}
          />
        ))}
        {znaczniki.map((z) => (
          <motion.span
            key={z.label}
            title={z.tytul}
            initial={{ left: "2%", opacity: 0 }}
            animate={{ left: `${pozNaTorze(z.p)}%`, opacity: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ${
              z.slaby ? "h-3.5 w-[2px]" : "h-5 w-[3px]"
            } ${z.klasa}`}
          />
        ))}
      </div>

      {/* skala — bez niej znaczniki wiszą w próżni */}
      <div className="relative mt-1 h-3 text-[9px] text-faint">
        <span className="absolute left-0">0</span>
        <span className="absolute left-1/2 -translate-x-1/2">50%</span>
        <span className="absolute right-0">100%</span>
      </div>

      <dl className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
        {znaczniki.map((z) => (
          <div key={z.label} className="flex items-baseline gap-1.5" title={z.tytul}>
            <span
              aria-hidden
              className={`inline-block w-3 translate-y-[-2px] rounded-full ${
                z.slaby ? "h-[2px]" : "h-[3px]"
              } ${z.klasa}`}
            />
            <dt className="text-[11px] text-faint">{z.label}</dt>
            <dd className="font-data text-sm font-semibold text-ink">{fmtProc(z.p)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * Odczyt okna formy (L5 · L10 · razem, splity): kolor niesie ton, tekst
 * niesie treść. Bez washa i pastylki — chipów zostaje na karcie tylko status.
 */
function OdczytOkna({
  label,
  traf,
  n,
  tytul,
}: {
  label: string;
  traf: number;
  n: number;
  tytul?: string;
}) {
  const r = n > 0 ? traf / n : 0;
  const kolor =
    n >= 3 && r >= 0.6
      ? "text-data-green-ink"
      : n >= 3 && r < 0.45
        ? "text-data-red-ink"
        : "text-muted";
  return (
    <span className={`font-data text-[11px] font-semibold ${kolor}`} title={tytul}>
      <span className="mr-1 text-[9px] font-medium uppercase opacity-70">{label}</span>
      {traf}/{n}
    </span>
  );
}

/**
 * Historia zawodnika na tym rynku: słupki, okna hit-rate i splity. Bez karty
 * (de-boxing) — nagłówek, wykres i odczyty niosą się same.
 */
function SekcjaFormy({ bet, forma }: { bet: ValueBet; forma: FormaRynku }) {
  const okna = oknaFormy(forma, bet.linia, bet.strona);
  const zagrane = okna.zagrane;
  // okna jak w Props.cash/StatsHub: forma TERAZ vs średnia — L5 wykrywa
  // trend, którego jedna suma nie pokaże
  const odczyty = [
    ...(zagrane >= 3 ? [{ label: "L5", ...okna.l5 }] : []),
    ...(zagrane >= 7 ? [{ label: "L10", ...okna.l10 }] : []),
    { label: "razem", ...okna.all },
  ];
  const splity = splityFormy(forma, bet.linia, bet.strona);
  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
          Ostatnie mecze: {bet.rynek.toLowerCase()}
        </h4>
        {zagrane > 0 && (
          <span
            className="flex items-center gap-2"
            title="Jak często ten typ by wszedł: w ostatnich 5 / 10 / wszystkich meczach z minutami"
          >
            {odczyty.map((c) => (
              <OdczytOkna key={c.label} {...c} />
            ))}
          </span>
        )}
      </div>
      <FormBars
        counts={forma.ostatnie}
        minutes={forma.minuty}
        opponents={forma.rywale}
        kadra={forma.kadra}
        line={bet.linia}
        side={bet.strona}
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
          {bet.oczekiwane_minuty != null ? Math.round(bet.oczekiwane_minuty) : "–"}
        </span>
      </p>
      {/* splity kontekstowe — jak typ wchodzi w podpróbkach */}
      {splity.length > 0 && (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-hairline pt-2.5">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
            splity
          </span>
          {splity.map((s) => (
            <OdczytOkna
              key={s.label}
              {...s}
              tytul={`${s.opis}: ten typ wszedłby w ${s.traf} z ${s.n} meczów`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Odchylenie czynnika od neutralnego 1,00 jako kreska w lewo/prawo od osi.
 * Pełne wychylenie = ±15% — realne czynniki mieszczą się w ~0,85–1,15,
 * więc szersza skala robiła z każdego z nich niewidoczną drobinkę.
 */
function MnoznikBar({ m }: { m: number }) {
  const neutralny = Math.abs(m - 1) < 0.005;
  const odch = Math.min(Math.abs(m - 1) / 0.15, 1);
  return (
    <span aria-hidden className="relative block h-2.5 w-10 shrink-0">
      <span className="absolute left-1/2 top-0 h-full w-px bg-hairline-strong" />
      {!neutralny && (
        <span
          className={`absolute top-1/2 h-[3px] min-w-[3px] -translate-y-1/2 rounded-full ${
            m > 1 ? "left-1/2 bg-data-green" : "right-1/2 bg-data-red"
          }`}
          style={{ width: `${odch * 50}%` }}
        />
      )}
    </span>
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
  strona: Strona,
): "green" | "amber" | "red" | null {
  if (!forma) return null;
  const o = oknaFormy(forma, linia, strona);
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
  const swiatlo = swiatloTypu(forma, bet.linia, bet.p_model, bet.strona);
  const odznaki = odznakiPrzewagi(bet);
  const okna = forma ? oknaFormy(forma, bet.linia, bet.strona) : null;
  // historia do porównania wycen: L10 gdy jest sensowna próba, inaczej całość
  const historiaOkno =
    okna == null ? null : okna.l10.n >= 5 ? okna.l10 : okna.all;

  // rozkład (i „inne linie”) liczą się przy przewidywanych minutach, p_model
  // dokłada do tego scenariusze rotacji — te dwie liczby potrafią się rozjechać
  // o kilkanaście pp, więc karta musi powiedzieć wprost, skąd różnica
  const przyMinutach =
    bet.oczekiwane_minuty != null ? Math.round(bet.oczekiwane_minuty) : null;
  const pLiniiZRozkladu = (() => {
    if (!bet.rozklad) return null;
    const total = bet.rozklad.reduce((a, b) => a + b, 0) || 1;
    const over =
      bet.rozklad.slice(Math.floor(bet.linia) + 1).reduce((a, b) => a + b, 0) / total;
    return bet.strona === "ponizej" ? 1 - over : over;
  })();
  const rozjazdMinut =
    pLiniiZRozkladu != null && Math.abs(pLiniiZRozkladu - bet.p_model) >= 0.03;

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
            <div className="border-t border-hairline bg-paper/50 px-4 py-5 sm:px-6">
              {/* akt 1: ile to jest warte */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.04 }}
              >
                <Werdykt bet={bet} />
              </motion.div>

              {/* akt 2: dowód na jednej skali */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                className="mt-6"
              >
                <TorDowodu bet={bet} historia={historiaOkno} />
              </motion.div>

              {/* akt 3: dlaczego model tak uważa */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.16 }}
                className="mt-7 grid gap-x-10 gap-y-7 sm:grid-cols-2"
              >
                <div className="space-y-6">
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
                  <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-faint">
                    Dlaczego ten typ
                  </h4>
                  <ul className="space-y-2">
                    {bet.uzasadnienie.czynniki.map((c) => (
                      <li key={c.nazwa} className="flex items-start gap-3 text-sm">
                        <span className="flex-1">
                          <span className="font-medium">{c.nazwa}:</span>{" "}
                          <span className="text-ink-soft">{c.opis}</span>
                        </span>
                        {c.mnoznik !== null && (
                          <span
                            className="flex shrink-0 items-center gap-2 pt-1"
                            title={`Ten czynnik ${
                              c.mnoznik > 1.02
                                ? "podnosi"
                                : c.mnoznik < 0.98
                                  ? "obniża"
                                  : "praktycznie nie rusza"
                            } przewidywaną liczbę zdarzeń (1,00 = bez wpływu)`}
                          >
                            <MnoznikBar m={c.mnoznik} />
                            <span
                              className={`font-data w-12 text-right text-xs font-semibold ${
                                c.mnoznik > 1.02
                                  ? "text-data-green-ink"
                                  : c.mnoznik < 0.98
                                    ? "text-data-red-ink"
                                    : "text-faint"
                              }`}
                            >
                              {fmtMnoznik(c.mnoznik)}
                            </span>
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* historia to też „dlaczego” — i domyka wysokość kolumny */}
                {forma && <SekcjaFormy bet={bet} forma={forma} />}
                </div>

                {/* prawa: co z modelu wychodzi */}
                <div className="space-y-6">
                {bet.rozklad && (
                  <div>
                    <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
                        Możliwe wyniki i ich szanse
                      </h4>
                      {przyMinutach && (
                        <span className="text-[10px] uppercase tracking-wide text-faint">
                          przy {przyMinutach} min
                        </span>
                      )}
                    </div>
                    <OutcomeColumns
                      dist={bet.rozklad}
                      line={bet.linia}
                      side={bet.strona}
                    />
                    {/* rozkład liczy się przy przewidywanych minutach, a p_model
                        wlicza jeszcze ryzyko rotacji — bez tego zdania user widzi
                        dwie różne liczby na tej samej karcie i traci zaufanie */}
                    {rozjazdMinut && (
                      <p className="mt-2 text-xs leading-relaxed text-faint">
                        Model daje temu typowi{" "}
                        <span className="font-data text-ink-soft">
                          {fmtProc(bet.p_model)}
                        </span>
                        , czyli mniej, bo wlicza też ryzyko, że zawodnik zagra
                        krócej albo w ogóle nie wyjdzie.
                      </p>
                    )}
                  </div>
                )}
                {bet.rozklad && (
                  <div>
                    <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-x-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
                        Szanse na inne linie
                      </h4>
                      {przyMinutach && (
                        <span className="text-[10px] uppercase tracking-wide text-faint">
                          przy {przyMinutach} min
                        </span>
                      )}
                    </div>
                    {/* podkreślenie zamiast kafelka — linia tego typu czyta się
                        jak aktywna zakładka */}
                    <div className="flex items-end gap-3">
                      {[0.5, 1.5, 2.5, 3.5].map((l) => {
                        const total =
                          bet.rozklad!.reduce((a, b) => a + b, 0) || 1;
                        const pOver =
                          bet.rozklad!
                            .slice(Math.floor(l) + 1)
                            .reduce((a, b) => a + b, 0) / total;
                        const p = bet.strona === "ponizej" ? 1 - pOver : pOver;
                        const aktualna = Math.abs(l - bet.linia) < 0.01;
                        if (p < 0.02 && !aktualna) return null;
                        const skrot = bet.strona === "ponizej" ? "pon." : "pow.";
                        return (
                          <div
                            key={l}
                            className={`flex-1 border-b-2 pb-1.5 ${
                              aktualna ? "border-brand" : "border-hairline"
                            }`}
                            title={
                              aktualna
                                ? "Linia tego typu"
                                : `Szansa modelu na ${
                                    bet.strona === "ponizej" ? "poniżej" : "powyżej"
                                  } ${fmtLinia(l)}`
                            }
                          >
                            <p className="text-[10px] uppercase tracking-wide text-faint">
                              {skrot} {fmtLinia(l)}
                            </p>
                            <p
                              className={`font-data mt-0.5 text-base font-semibold leading-none ${
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
                </div>
              </motion.div>

              {/* akcja domyka narrację: ile → dowód → dlaczego → zagraj */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.22 }}
                className="mt-7 flex flex-col gap-3 border-t border-hairline pt-5 sm:flex-row sm:items-center sm:justify-between"
              >
                {bet.sugestia ? (
                  <>
                    <p className="text-xs leading-relaxed text-muted">
                      Znajdź ten rynek w STS. Płacą powyżej{" "}
                      <span className="font-data font-semibold text-ink">
                        ~{fmtKurs(bet.fair_kurs * 1.05)}
                      </span>
                      ? Masz przewagę, dodaj zakład w „Moich zakładach”.
                    </p>
                    <span className="font-data shrink-0 text-[10px] uppercase tracking-wide text-faint">
                      kurs sprawdzasz ręcznie
                    </span>
                  </>
                ) : (
                  <>
                    <p className="text-xs leading-relaxed text-muted">
                      Zapisz typ u siebie, a rozliczymy go automatycznie po meczu.
                    </p>
                    <button
                      onClick={() => addZakladFromBet(bet, null)}
                      disabled={tracked}
                      className={`w-full shrink-0 rounded-(--radius-control) px-5 py-2.5 text-sm font-semibold transition-colors sm:w-auto ${
                        tracked
                          ? "cursor-default bg-brand-wash text-brand"
                          : "bg-brand text-on-brand shadow-(--shadow-card) hover:bg-brand-strong"
                      }`}
                    >
                      {tracked ? "✓ W moich zakładach" : "Dodaj do moich zakładów"}
                    </button>
                  </>
                )}
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
