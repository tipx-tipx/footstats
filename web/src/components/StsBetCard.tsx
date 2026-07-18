"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { PewnoscDots } from "./badges";
import { fmtDataCzas, fmtEV, fmtKurs, fmtProc, PEWNOSC_LABEL } from "@/lib/format";
import type { StsAlert } from "@/lib/types";

/** Pozycja na torze 0–100% z marginesem, żeby znacznik nie uciekał za krawędź. */
const pozNaTorze = (p: number) => Math.min(Math.max(p * 100, 2), 98);

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
      } — czyli sam Superbet „w środku" wycenia to drożej, niż płaci STS.`,
    },
    {
      label: "ponad tło meczu",
      opis: `STS bywa globalnie luźniejszy, ale ta selekcja odstaje ×${a.nadwyzka_vs_baseline
        .toFixed(2)
        .replace(".", ",")} ponad typową różnicę STS/Superbet w tym meczu — to nie sama ogólna luźność.`,
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

/** Werdykt: dwie wyceny obok siebie + o ile STS przepłaca. Bohater rozwinięcia. */
function Werdykt({ a }: { a: StsAlert }) {
  const pola = [
    { label: "superbet płaci", val: fmtKurs(a.kurs_superbet), kolor: "text-ink" },
    { label: "sts płaci", val: fmtKurs(a.kurs_sts), kolor: "text-brand-deep" },
    {
      label: "przepłaca",
      val: `+${przeplaca(a)}%`,
      kolor: "text-data-green-ink",
    },
  ];
  return (
    <div>
      <dl className="flex max-w-xl items-stretch">
        {pola.map((p, i) => (
          <div
            key={p.label}
            className={`flex flex-1 flex-col ${
              i > 0 ? "border-l border-hairline pl-4 sm:pl-5" : ""
            } ${i < pola.length - 1 ? "pr-4 sm:pr-5" : ""}`}
          >
            <dt className="text-[10px] uppercase tracking-wide text-faint">{p.label}</dt>
            <dd
              className={`font-data mt-auto pt-1 text-2xl font-semibold leading-none tracking-tight ${p.kolor}`}
            >
              {p.val}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 max-w-prose text-sm leading-relaxed text-ink-soft">
        Superbet wycenia to zdarzenie na{" "}
        <span className="font-data text-ink">{fmtKurs(a.kurs_superbet)}</span>, a STS płaci{" "}
        <span className="font-data font-semibold text-brand-deep">{fmtKurs(a.kurs_sts)}</span>{" "}
        na dokładnie to samo. Ta sama rzecz do wykręcenia, o{" "}
        <span className="font-semibold text-data-green-ink">{przeplaca(a)}%</span> wyżej wyceniona.
      </p>
    </div>
  );
}

/**
 * Tor: gdzie sytuują się dwie wyceny i model na jednej skali szans 0–100%.
 * Historia STS: kurs STS wycenia zdarzenie NISKO (długi kurs = mała szansa),
 * a Superbet i nasz model dają wyraźnie wyżej — ta odległość to wartość.
 */
function TorWyceny({ a }: { a: StsAlert }) {
  const pSts = 1 / a.kurs_sts;
  const pSb = 1 / a.kurs_superbet;
  const model = a.ma_model && a.p_model != null ? a.p_model : null;
  // prawy koniec przewagi = model (jeśli jest) albo wycena Superbetu
  const gora = model ?? pSb;
  const przewaga = gora > pSts ? { od: pozNaTorze(pSts), do: pozNaTorze(gora) } : null;
  const etykieta =
    a.value_potwierdzony && a.ev_model_pct != null
      ? `${fmtEV(a.ev_model_pct)} wg modelu`
      : `STS przepłaca`;

  const znaczniki = [
    {
      p: pSts,
      label: "kurs STS wycenia",
      klasa: "bg-ink",
      tytul: `Kurs ${fmtKurs(a.kurs_sts)} odpowiada szansie ${fmtProc(pSts)} — tyle „daje" STS. Jeśli realna szansa jest wyższa, kurs jest za wysoki (dla ciebie dobry).`,
    },
    {
      p: pSb,
      label: "Superbet wycenia",
      klasa: "bg-brand/60",
      tytul: `Kurs Superbetu ${fmtKurs(a.kurs_superbet)} odpowiada szansie ${fmtProc(pSb)} (z marżą buka) — drugi bukmacher widzi to zdarzenie znacznie częściej niż STS.`,
    },
    ...(model != null
      ? [
          {
            p: model,
            label: "szansa wg modelu",
            klasa: "bg-brand",
            tytul: `Model FootStats daje temu ${fmtProc(model)} szans${
              a.oczekiwane_minuty != null
                ? ` przy przewidywanych ${Math.round(a.oczekiwane_minuty)} min`
                : ""
            } — niezależnie od obu bukmacherów.`,
          },
        ]
      : []),
  ];

  return (
    <div>
      <div className="mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-faint">
          Gdzie leży wartość
        </h4>
      </div>

      <div className="relative h-4">
        {przewaga && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.5, duration: 0.3 }}
            className="font-data absolute -translate-x-1/2 whitespace-nowrap text-[10px] font-semibold text-data-green-ink"
            style={{
              left: `${Math.min(Math.max((przewaga.od + przewaga.do) / 2, 14), 86)}%`,
            }}
          >
            {etykieta}
          </motion.span>
        )}
      </div>

      <div className="relative h-6">
        <span
          aria-hidden
          className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-hairline"
        />
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
            className={`absolute top-1/2 h-5 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full ${z.klasa}`}
          />
        ))}
      </div>

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
              className={`inline-block h-[3px] w-3 translate-y-[-2px] rounded-full ${z.klasa}`}
            />
            <dt className="text-[11px] text-faint">{z.label}</dt>
            <dd className="font-data text-sm font-semibold text-ink">{fmtProc(z.p)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
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
  const lista = potwierdzenia(a);

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
                  potw
                    ? "Pełny value bet STS: model potwierdza i STS przepłaca"
                    : "Różnica kursowa STS vs Superbet (model nie ocenił tej selekcji)"
                }
                className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
              >
                <span
                  aria-hidden
                  className={`absolute -inset-1 rounded-full opacity-20 ${potw ? "bg-brand" : "bg-data-amber"}`}
                />
                <span
                  aria-hidden
                  className={`h-2 w-2 rounded-full ${potw ? "bg-brand" : "bg-data-amber"}`}
                />
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

        {/* meta: status + znaczniki + pewność + detale */}
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 px-4 pb-3.5 sm:pl-[4.75rem] sm:pr-5">
          <span
            className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              potw ? "bg-brand-wash text-brand-deep" : "bg-data-amber-wash text-data-amber-ink"
            }`}
            title={
              potw
                ? "Model potwierdza tę selekcję i STS płaci ponad wartość"
                : "Sama różnica kursowa STS vs Superbet — bez potwierdzenia modelu"
            }
          >
            {potw ? "★ value potwierdzony" : "różnica kursowa"}
          </span>

          {a.ma_model && a.ev_model_pct != null && (
            <span
              className="inline-flex items-center gap-1 px-1 text-[11px] font-medium text-brand-deep"
              title={`Wartość wg NIEZALEŻNEJ wyceny modelu: przy szansie ${
                a.p_model != null ? fmtProc(a.p_model) : "modelu"
              } kurs STS ${fmtKurs(a.kurs_sts)} daje ${fmtEV(a.ev_model_pct)} przewagi`}
            >
              <span aria-hidden className="font-data">◎</span> model {fmtEV(a.ev_model_pct)}
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
              {/* akt 1: ile STS przepłaca */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.04 }}
              >
                <Werdykt a={a} />
              </motion.div>

              {/* akt 2: gdzie leży wartość — dwie wyceny + model na jednej skali */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                className="mt-6"
              >
                <TorWyceny a={a} />
              </motion.div>

              {/* akt 3: dlaczego temu wierzyć + kontekst */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.16 }}
                className="mt-7 grid gap-x-10 gap-y-7 sm:grid-cols-2"
              >
                {/* lewa: potwierdzenia cross-book */}
                <div>
                  <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-faint">
                    Dlaczego to nie przypadek ({a.sygnaly}/3)
                  </h4>
                  <ul className="space-y-2">
                    {lista.map((p) => (
                      <li key={p.label} className="flex items-start gap-2.5 text-sm">
                        <span
                          aria-hidden
                          className={`font-data mt-px shrink-0 ${
                            p.on ? "text-brand" : "text-faint"
                          }`}
                        >
                          {p.on ? "✓" : "·"}
                        </span>
                        <span className={p.on ? "" : "opacity-55"}>
                          <span className="font-medium">{p.label}:</span>{" "}
                          <span className="text-ink-soft">{p.opis}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* prawa: model + kontekst rynku */}
                <div className="space-y-5">
                  <div>
                    <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-faint">
                      Strona modelu
                    </h4>
                    {a.ma_model && a.p_model != null ? (
                      <p className="text-sm leading-relaxed text-ink-soft">
                        Model FootStats daje temu zdarzeniu{" "}
                        <span className="font-data font-semibold text-ink">
                          {fmtProc(a.p_model)}
                        </span>{" "}
                        szans
                        {a.oczekiwane_minuty != null && (
                          <>
                            {" "}
                            przy przewidywanych{" "}
                            <span className="font-data text-ink">
                              {Math.round(a.oczekiwane_minuty)}
                            </span>{" "}
                            minutach
                          </>
                        )}
                        . Na kursie STS {fmtKurs(a.kurs_sts)} to{" "}
                        <span className="font-semibold text-data-green-ink">
                          {a.ev_model_pct != null ? fmtEV(a.ev_model_pct) : "dodatnia"}
                        </span>{" "}
                        przewagi — niezależnie od tego, co robi Superbet.
                      </p>
                    ) : (
                      <p className="text-sm leading-relaxed text-ink-soft">
                        Model nie ocenił tej selekcji (za mało danych albo poza jego rynkami),
                        więc to sama różnica kursowa STS vs Superbet. Sygnał słabszy niż przy
                        typach z potwierdzeniem modelu.
                      </p>
                    )}
                  </div>

                  {a.z_dogrywka && (
                    <div>
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
                        Dogrywka + SuperZmiana
                      </h4>
                      <p className="text-sm leading-relaxed text-ink-soft">
                        Ten rynek STS rozlicza się z dogrywką i ma SuperZmianę: jeśli zawodnik
                        zejdzie, zakład przechodzi na zmiennika. Znika największe ryzyko typów na
                        zawodnika (czy w ogóle zagra), a dogrywka dokłada czasu na „powyżej".
                        Realna szansa jest więc jeszcze wyższa, niż liczymy.
                      </p>
                    </div>
                  )}
                </div>
              </motion.div>

              {/* akcja: kurs bywa ulotny */}
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.22 }}
                className="mt-7 flex flex-col gap-3 border-t border-hairline pt-5 sm:flex-row sm:items-center sm:justify-between"
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
