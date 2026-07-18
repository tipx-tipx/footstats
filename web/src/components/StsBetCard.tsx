"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { PewnoscDots } from "./badges";
import { OsSzans, type OsZnacznik } from "./OsSzans";
import { Sygnaly, type Sygnal } from "./Sygnaly";
import { fmtDataCzas, fmtEV, fmtKurs, fmtProc } from "@/lib/format";
import type { StsAlert } from "@/lib/types";

/** Nadwyżka kursu STS nad Superbetem w %: (ratio − 1) × 100. */
const przeplaca = (a: StsAlert) => Math.round((a.ratio - 1) * 100);

/**
 * Trzy niezależne potwierdzenia cross-book (backend: pole `sygnaly`). Kolejność
 * i treść lustrzane do sts_value.py — karta tłumaczy je po ludzku i pokazuje,
 * ile z nich realnie zaszło (sygnaly = ich liczba).
 */
function potwierdzenia(a: StsAlert): { label: string; opis: string; on: boolean }[] {
  const lista = [
    {
      label: "siatka Superbetu",
      opis: `Z pozostałych linii Superbetu na ten rynek wynika kurs ~${
        a.fair_kurs_siatka != null ? fmtKurs(a.fair_kurs_siatka) : "podobny do oferowanego"
      }. Czyli sam Superbet „w środku" wycenia to drożej, niż płaci STS.`,
    },
    {
      label: "ponad tło meczu",
      opis: `STS bywa globalnie luźniejszy, ale ta selekcja odstaje ×${a.nadwyzka_vs_baseline
        .toFixed(2)
        .replace(".", ",")} ponad typową różnicę STS/Superbet w tym meczu. To nie sama ogólna luźność.`,
    },
    {
      label: "pełna drabinka linii",
      opis:
        "STS ma komplet linii tego rynku (kurs świeży, nie osierocona/zawieszona pozycja), więc wartość jest wiarygodna.",
    },
  ];
  // sygnaly = ile z 3 zaszło; zapalamy pierwsze `sygnaly` (kolejność jak backend)
  return lista.map((p, i) => ({ ...p, on: i < a.sygnaly }));
}

/**
 * Sygnały rozwinięcia: potwierdzenia cross-book + głos modelu + SuperZmiana.
 * Jedna linia etykiet, opisy na klik (komponent Sygnaly) — zamiast dwóch
 * kolumn pełnych akapitów.
 */
function sygnalyAlertu(a: StsAlert): Sygnal[] {
  const s: Sygnal[] = potwierdzenia(a).map((p) => ({
    id: p.label,
    znak: p.on ? "✓" : "·",
    label: p.label,
    ton: p.on ? "brand" : "cichy",
    opis: p.on ? p.opis : `Tego potwierdzenia zabrakło przy tym skanie. ${p.opis}`,
  }));

  if (a.model_odrzucil) {
    s.push({
      id: "model",
      znak: "⚠",
      label: "model ostrzega",
      ton: "czerwony",
      opis: `Własne sito modelu odrzuciło tę parę zawodnik+rynek: ${a.odrzucenie_powod}. Nie traktuj jej jak potwierdzoną, to sama różnica kursowa STS vs Superbet. Graj ostrożnie albo odpuść.`,
    });
  } else if (a.ma_model && a.p_model != null) {
    s.push({
      id: "model",
      znak: "◎",
      label:
        a.ev_model_pct != null
          ? `model potwierdza ${fmtEV(a.ev_model_pct)}`
          : "model potwierdza",
      ton: "brand",
      opis: `Model FootStats daje temu zdarzeniu ${fmtProc(a.p_model)} szans${
        a.oczekiwane_minuty != null
          ? ` przy przewidywanych ${Math.round(a.oczekiwane_minuty)} minutach`
          : ""
      }. Na kursie STS ${fmtKurs(a.kurs_sts)} to ${
        a.ev_model_pct != null ? fmtEV(a.ev_model_pct) : "dodatnia"
      } przewagi, niezależnie od tego, co robi Superbet.`,
    });
  } else {
    s.push({
      id: "model",
      znak: "·",
      label: "bez oceny modelu",
      ton: "cichy",
      opis: "Model nie ocenił tej selekcji (za mało danych albo poza jego rynkami), więc to sama różnica kursowa STS vs Superbet. Sygnał słabszy niż przy typach z potwierdzeniem modelu.",
    });
  }

  if (a.z_dogrywka) {
    s.push({
      id: "dogrywka",
      znak: "⏱",
      label: "z dogrywką, SuperZmiana",
      ton: "amber",
      opis: "Ten rynek STS rozlicza się z dogrywką i ma SuperZmianę: jeśli zawodnik zejdzie, zakład przechodzi na zmiennika. Znika największe ryzyko typów na zawodnika (czy w ogóle zagra), a dogrywka dokłada czasu. Realna szansa jest więc jeszcze wyższa, niż liczymy.",
    });
  }
  return s;
}

/** memo: przy zmianie filtrów listy karty się nie przerenderowują wszystkie. */
export const StsBetCard = memo(function StsBetCard({
  a,
  rank,
}: {
  a: StsAlert;
  rank: number;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();

  const nazwa = a.zawodnik_nazwa || a.zawodnik;
  const potw = a.value_potwierdzony;
  // trzy stany: pełny value bet / model ostrzega (weto z odrzuceń) / sama różnica
  const stan = potw ? "potw" : a.model_odrzucil ? "ostrzega" : "roznica";
  const diodaBg =
    stan === "potw" ? "bg-brand" : stan === "ostrzega" ? "bg-data-red" : "bg-data-amber";
  const sygnaly = sygnalyAlertu(a);

  // oś szans: obie wyceny + model na jednej skali, liczby przy znacznikach
  const pSts = 1 / a.kurs_sts;
  const pSb = 1 / a.kurs_superbet;
  const model = a.ma_model && a.p_model != null ? a.p_model : null;
  const gora = model ?? pSb;
  const znaczniki: OsZnacznik[] = [
    {
      id: "sb",
      p: pSb,
      wartosc: fmtProc(pSb),
      podpis: "superbet",
      ton: "duch-brand",
      // bez modelu Superbet jest drugim głosem osi — wtedy dostaje etykietę
      etykieta: model != null ? "gora" : "dol",
      tytul: `Kurs Superbetu ${fmtKurs(a.kurs_superbet)} odpowiada szansie ${fmtProc(
        pSb,
      )} (z marżą buka). Drugi bukmacher widzi to zdarzenie znacznie częściej niż STS`,
    },
    ...(model != null
      ? [
          {
            id: "model",
            p: model,
            wartosc: fmtProc(model),
            podpis: "model",
            ton: "brand" as const,
            etykieta: "dol" as const,
            tytul: `Model FootStats daje temu ${fmtProc(model)} szans${
              a.oczekiwane_minuty != null
                ? ` przy przewidywanych ${Math.round(a.oczekiwane_minuty)} min`
                : ""
            }, niezależnie od obu bukmacherów`,
          },
        ]
      : []),
    {
      id: "sts",
      p: pSts,
      wartosc: fmtProc(pSts),
      podpis: "sts wycenia",
      ton: "ink",
      etykieta: "dol",
      tytul: `Kurs ${fmtKurs(a.kurs_sts)} odpowiada szansie ${fmtProc(
        pSts,
      )}, tyle „daje" STS. Jeśli realna szansa jest wyższa, kurs jest za wysoki (dla ciebie dobry)`,
    },
  ];
  const przewaga = gora > pSts ? { od: pSts, do: gora } : null;

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
        {/* wiersz główny: numer · kto i co · przepłaca · kurs STS vs Superbet */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-3 pt-3.5 sm:grid-cols-[auto_1.5fr_auto_auto] sm:px-5">
          <span
            aria-hidden
            className="font-display hidden w-10 shrink-0 text-center text-[1.7rem] font-bold leading-none text-ink/15 transition-colors group-hover:text-brand/40 sm:block"
          >
            {rank}
          </span>

          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {/* dioda: pełny value bet (model + cross-book) = marka; sam
                  cross-book = bursztyn */}
              <span
                title={
                  stan === "potw"
                    ? "Pełny value bet STS: model potwierdza i STS przepłaca"
                    : stan === "ostrzega"
                      ? "Model odrzucił tę selekcję — sama różnica kursowa, ostrożnie"
                      : "Różnica kursowa STS vs Superbet (model nie ocenił tej selekcji)"
                }
                className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
              >
                <span
                  aria-hidden
                  className={`absolute -inset-1 rounded-full opacity-20 ${diodaBg}`}
                />
                <span aria-hidden className={`h-2 w-2 rounded-full ${diodaBg}`} />
              </span>
              <span className="truncate font-semibold">{nazwa}</span>
              <span className="text-sm text-muted">
                {a.rynek.toLowerCase()}, {a.linia_opis}
              </span>
            </span>
            <span className="mt-1 block truncate text-xs text-faint">
              {a.mecz}
              {a.mecz_ts != null ? ` · ${fmtDataCzas(a.mecz_ts)}` : ""}
            </span>
          </span>

          {/* ile STS przepłaca — sygnał gapu na pierwszy rzut oka */}
          <span className="hidden flex-col items-end justify-center sm:flex">
            <span className="font-data text-lg font-semibold leading-none text-data-green-ink">
              +{przeplaca(a)}%
            </span>
            <span className="mt-1 text-[9px] uppercase tracking-wide text-faint">
              STS płaci więcej
            </span>
          </span>

          {/* rubryka kursu za gradientową linią: STS duże, Superbet jako odniesienie */}
          <span className="relative flex flex-col items-end justify-center gap-1 self-stretch justify-self-end pl-5 sm:pl-6">
            <span
              aria-hidden
              className="absolute inset-y-0 left-0 hidden w-px bg-gradient-to-b from-transparent via-hairline-strong to-transparent sm:block"
            />
            <span className="font-data text-xl font-semibold leading-none tracking-tight text-brand-deep">
              {fmtKurs(a.kurs_sts)}
            </span>
            <span className="text-[9px] uppercase tracking-wide text-faint">
              STS · vs {fmtKurs(a.kurs_superbet)}
            </span>
          </span>
        </span>

        {/* meta: status + pewność + detale */}
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 px-4 pb-3.5 sm:pl-[4.75rem] sm:pr-5">
          <span
            className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              stan === "potw"
                ? "bg-brand-wash text-brand-deep"
                : stan === "ostrzega"
                  ? "bg-data-red-wash text-data-red-ink"
                  : "bg-data-amber-wash text-data-amber-ink"
            }`}
            title={
              stan === "potw"
                ? "Model potwierdza tę selekcję i STS płaci ponad wartość"
                : stan === "ostrzega"
                  ? `Model odrzucił tę selekcję: ${a.odrzucenie_powod}. To sama różnica kursowa — ostrożnie.`
                  : "Sama różnica kursowa STS vs Superbet — bez potwierdzenia modelu"
            }
          >
            {stan === "potw"
              ? "★ value potwierdzony"
              : stan === "ostrzega"
                ? "⚠ model ostrzega"
                : "różnica kursowa"}
          </span>

          {a.ma_model && a.ev_model_pct != null && !a.model_odrzucil && (
            <span
              className="inline-flex items-center gap-1 px-1 text-[11px] font-medium text-brand-deep"
              title={`Wartość wg NIEZALEŻNEJ wyceny modelu: przy szansie ${
                a.p_model != null ? fmtProc(a.p_model) : "modelu"
              } kurs STS ${fmtKurs(a.kurs_sts)} daje ${fmtEV(a.ev_model_pct)} przewagi`}
            >
              <span aria-hidden className="font-data">◎</span> model {fmtEV(a.ev_model_pct)}
            </span>
          )}

          {a.model_odrzucil && a.odrzucenie_powod && (
            <span
              className="inline-flex items-center gap-1 px-1 text-[11px] font-medium text-data-red-ink"
              title={`Własne sito modelu odrzuciło tę parę zawodnik+rynek: ${a.odrzucenie_powod}`}
            >
              <span aria-hidden className="font-data">⚠</span> {a.odrzucenie_powod}
            </span>
          )}

          {a.z_dogrywka && (
            <span
              className="inline-flex items-center gap-1 px-1 text-[11px] font-medium text-data-amber-ink"
              title="Rynek rozliczany z dogrywką, a STS daje tu SuperZmianę: jeśli zawodnik zejdzie, zakład przechodzi na zmiennika. Znika ryzyko minut, a dogrywka dokłada czasu."
            >
              <span aria-hidden className="font-data">⏱</span> z dogrywką · SuperZmiana
            </span>
          )}

          <span className="ml-auto flex items-center gap-3">
            <span
              className="flex items-center gap-1 text-[10px] text-faint"
              title="Ile z 3 niezależnych potwierdzeń cross-book zaszło (siatka Superbetu, ponad tło meczu, pełna drabinka linii)"
            >
              <PewnoscDots level={a.pewnosc} />
              {a.sygnaly}/3 potwierdzenia
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

      {/* rozwinięcie: pojedynek kursów → oś szans → sygnały → akcja */}
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
              {/* moment 1: pojedynek dwóch wycen tego samego zdarzenia,
                  liczby raz (duże), interpretacja jednym zdaniem pod spodem */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.04 }}
              >
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-faint">
                  werdykt
                </span>
                <div className="mt-2.5 grid max-w-md grid-cols-[1fr_auto_1fr] items-end gap-x-5">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      superbet wycenia
                    </p>
                    <p className="font-data mt-1 text-[1.7rem] font-bold leading-none tracking-tight text-ink">
                      {fmtKurs(a.kurs_superbet)}
                    </p>
                  </div>
                  <div className="pb-0.5 text-center">
                    <span
                      aria-hidden
                      className="block text-[10px] leading-none text-data-green"
                    >
                      ▲
                    </span>
                    <span className="font-data mt-0.5 block text-base font-bold leading-none text-data-green-ink">
                      +{przeplaca(a)}%
                    </span>
                    <span className="mt-1 block text-[9px] uppercase tracking-wide text-faint">
                      sts płaci więcej
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-wide text-faint">
                      sts płaci
                    </p>
                    <p className="font-data mt-1 text-[1.7rem] font-bold leading-none tracking-tight text-brand-deep">
                      {fmtKurs(a.kurs_sts)}
                    </p>
                  </div>
                </div>
                <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-soft">
                  Dokładnie to samo zdarzenie, dwie ceny.{" "}
                  {stan === "potw" && a.p_model != null ? (
                    <>
                      Model daje mu{" "}
                      <span className="font-data font-semibold text-ink">
                        {fmtProc(a.p_model)}
                      </span>{" "}
                      szans, więc kurs STS niesie{" "}
                      <span className="font-semibold text-data-green-ink">
                        {a.ev_model_pct != null ? fmtEV(a.ev_model_pct) : "dodatnią"}
                      </span>{" "}
                      przewagi niezależnie od Superbetu.
                    </>
                  ) : stan === "ostrzega" ? (
                    <span className="text-data-red-ink">
                      Model odrzucił tę selekcję ({a.odrzucenie_powod}), więc to
                      sama różnica kursowa. Graj ostrożnie albo odpuść.
                    </span>
                  ) : (
                    <>
                      Model nie ocenił tej selekcji, więc to sama różnica
                      kursowa między bukmacherami.
                    </>
                  )}
                </p>
              </motion.div>

              {/* moment 2: ta sama różnica na skali szans (jak w Pewniakach) */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                className="mt-5"
              >
                <OsSzans
                  znaczniki={znaczniki}
                  przewaga={przewaga}
                  przewagaWartosc={
                    potw && a.ev_model_pct != null
                      ? fmtEV(a.ev_model_pct)
                      : undefined
                  }
                  przewagaPodpis="wg modelu"
                  ariaLabel={`Oś szans: ${znaczniki
                    .map((z) => `${z.podpis} ${z.wartosc}`)
                    .join(", ")}`}
                />
              </motion.div>

              {/* moment 3: sygnały w jednej linii, opis na klik */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.16 }}
                className="mt-5 border-t border-hairline pt-4"
              >
                <Sygnaly
                  naglowek={
                    stan === "ostrzega" ? "Za i przeciw" : "Dlaczego to nie przypadek"
                  }
                  sygnaly={sygnaly}
                />
              </motion.div>

              {/* akcja: kurs bywa ulotny */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.22 }}
                className="mt-6 flex flex-col gap-3 border-t border-hairline pt-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <p className="text-xs leading-relaxed text-muted">
                  Taki kurs bywa krótko: STS zwykle koryguje go w dół albo zdejmuje linię, gdy
                  zauważy różnicę. Widzisz go teraz w STS?{" "}
                  <span className="font-semibold text-ink">Bierz, zanim zniknie.</span>
                </p>
                <span className="font-data shrink-0 whitespace-nowrap text-[10px] uppercase tracking-wide text-faint">
                  kurs sprawdzasz w STS
                </span>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
