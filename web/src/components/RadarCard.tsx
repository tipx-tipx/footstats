"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { fmtDataCzas, fmtKurs, fmtProc } from "@/lib/format";
import type { RadarRynek, RadarSezon, RadarWpis } from "@/lib/types";

/** Linia 0,5 to po ludzku „1 lub więcej" — tak mówi też Superbet. */
const linLabel = (linia: number) => `${Math.ceil(linia)}+`;

/** Krótkie polskie etykiety rynków w wierszach sezonowych. */
const SEZON_RYNKI_PL: Record<string, string> = {
  shots: "strzały",
  sot: "celne",
  shots_outside_box: "zza pola",
  fouls_committed: "faule",
  fouls_won: "faule wyw.",
  offsides: "spalone",
  tackles: "odbiory",
  interceptions: "przechwyty",
  shots_blocked: "zablokowane",
};

const liczba = (v: number) => String(v).replace(".", ",");

/** Etykieta i kolor diody per rodzaj sygnału. */
function rodzajInfo(w: RadarWpis): { label: string; dioda: string; tytul: string } {
  if (w.rodzaj === "transfer") {
    return {
      label: "nowy w drużynie",
      dioda: "bg-brand",
      tytul:
        "Historia zawodnika pochodzi z innej ligi lub innego klubu. Kursy na takich graczy bywają niedograne, bo bukmacher ma mało danych z nowego miejsca.",
    };
  }
  if (w.rodzaj === "debiutant") {
    return {
      label: "kursy w ciemno",
      dioda: "bg-data-amber",
      tytul:
        "Superbet kwotuje tego zawodnika, ale w danych nie ma jeszcze żadnej jego historii meczowej. Rynek wycenia go w ciemno.",
    };
  }
  if (w.rodzaj === "forma") {
    return {
      label: "seria formy",
      dioda: "bg-data-green",
      tytul:
        "Zawodnik regularnie przebija linię w ostatnich meczach, wyraźnie ponad swój wcześniejszy poziom. Model celowo nie dolicza formy do szansy, to sygnał dodatkowy.",
    };
  }
  return {
    label: "drabinka",
    dioda: "bg-ink/30",
    tytul:
      "Pełna drabinka kursów Superbetu z historią występów, formą i średnimi sezonowymi. Bez osobnego sygnału — materiał do własnej analizy.",
  };
}

/** Jedno zdanie „dlaczego tu jest" — proste, bez żargonu. */
function opisWpisu(w: RadarWpis): string {
  if (w.rodzaj === "transfer") {
    if (w.powod === "zmiana_ligi") {
      const liga = w.stara_liga ? `: ${w.stara_liga}` : "";
      return (
        `Z ostatnich meczów ${w.mecze_stara ?? "większość"} zagrał w poprzedniej lidze${liga}. ` +
        `W nowej ma dopiero ${w.mecze_nowa ?? 0}. ` +
        "Liczby niżej pochodzą głównie ze starego adresu, a kurs może tego nie uwzględniać."
      );
    }
    return (
      "W ostatnich tygodniach grał przeciw swojej obecnej drużynie, czyli zmienił klub w ramach ligi. " +
      "Nowa rola może zmienić jego liczby w obie strony."
    );
  }
  if (w.rodzaj === "debiutant") {
    const p = w.profil;
    const czesci = [
      p?.wiek != null ? `${p.wiek} lat` : null,
      p?.wzrost != null ? `${p.wzrost} cm` : null,
      p?.kraj ? `kraj: ${p.kraj[0].toUpperCase()}${p.kraj.slice(1)}` : null,
    ].filter(Boolean);
    return (
      "Superbet daje mu pełne linie, ale nie mamy ani jednego jego meczu w danych (świeży nabytek). " +
      (czesci.length ? `Profil: ${czesci.join(", ")}. ` : "") +
      "Sprawdź sam, skąd przyszedł i ile może zagrać, zanim postawisz."
    );
  }
  if (w.rodzaj === "forma") {
    const f = w.forma;
    if (!f) return "";
    return (
      `Przebił ${linLabel(f.linia)} w ${f.trafienia} z ${f.okno} ostatnich meczów. ` +
      `W tej serii średnio ${liczba(f.srednia90_okno)} na 90 minut, ` +
      `wcześniej ${liczba(f.srednia90_baza)}.`
    );
  }
  // drabinka: krótka zajawka z najbogatszego rynku + sezonów
  const zHistoria = w.rynki.find((r) => r.ostatnie && r.ostatnie.length > 0);
  const czesci: string[] = [];
  if (zHistoria?.srednia90 != null) {
    czesci.push(
      `${zHistoria.rynek.toLowerCase()}: śr. ${liczba(zHistoria.srednia90)}/90`,
    );
  }
  if (w.sezony?.length) {
    czesci.push(`średnie z ${w.sezony.length} sezonów niżej`);
  }
  return (
    "Kursy Superbetu i pełna historia występów. " +
    (czesci.length ? `${czesci.join(" · ")}.` : "")
  );
}

/** Wiersz jednego sezonu: liga, rok, mecze i średnie per rynek. */
function SezonWiersz({ s }: { s: RadarSezon }) {
  const wpisy = Object.entries(s.na_mecz).filter(
    ([mk]) => SEZON_RYNKI_PL[mk],
  );
  if (!wpisy.length) return null;
  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-xs font-semibold text-ink">
          {s.turniej} {s.rok}
        </span>
        <span className="font-data text-[11px] text-muted">
          {s.mecze} meczów · {s.minuty} min
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {wpisy.map(([mk, v]) => (
          <span
            key={mk}
            className="font-data text-[11px] text-ink-soft"
            title={
              s.na90[mk] != null
                ? `${SEZON_RYNKI_PL[mk]}: ${liczba(v)} na mecz, ${liczba(s.na90[mk])} na 90 minut`
                : `${SEZON_RYNKI_PL[mk]}: ${liczba(v)} na mecz`
            }
          >
            <span className="text-faint">{SEZON_RYNKI_PL[mk]}</span>{" "}
            <span className="font-semibold">{liczba(v)}</span>
            <span className="text-faint">/mecz</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Blok jednego rynku: ostatnie występy + drabinka kursów Superbetu. */
function RynekBlok({ r }: { r: RadarRynek }) {
  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-xs font-semibold text-ink">{r.rynek}</span>
        {r.srednia90 != null && (
          <span
            className="font-data text-[11px] text-muted"
            title="Średnia liczba zdarzeń w przeliczeniu na 90 minut, z całej dostępnej historii"
          >
            śr. {String(r.srednia90).replace(".", ",")} / 90 min
          </span>
        )}
      </div>

      {r.ostatnie && r.ostatnie.length > 0 && (
        <div
          className="mt-2 flex flex-wrap items-center gap-1"
          title={
            r.rywale && r.rywale.length
              ? `Ostatnie mecze (od najnowszego): ${r.ostatnie
                  .map(
                    (c, i) =>
                      `${c}${r.rywale?.[i] ? ` vs ${r.rywale[i]}` : ""}${
                        r.minuty?.[i] != null ? ` (${r.minuty[i]} min)` : ""
                      }`,
                  )
                  .join(", ")}`
              : "Ostatnie mecze, od najnowszego"
          }
        >
          <span className="mr-1 text-[9px] uppercase tracking-wide text-faint">
            ostatnie
          </span>
          {r.ostatnie.map((c, i) => (
            <span
              key={i}
              className={`font-data inline-flex h-5 min-w-5 items-center justify-center rounded px-1 text-[11px] font-semibold ${
                c > 0 ? "bg-brand-wash text-brand-deep" : "bg-paper text-faint"
              }`}
            >
              {c}
            </span>
          ))}
        </div>
      )}

      {(r.forma || r.rywal?.srednia != null) && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
          {r.forma && (
            <span
              title="Średnia na 90 minut z 6 ostatnich meczów vs wcześniejsza baza — czy liczby idą w górę, czy w dół"
            >
              forma:{" "}
              <span
                className={`font-data font-semibold ${
                  r.forma.okno90 > r.forma.baza90
                    ? "text-data-green-ink"
                    : r.forma.okno90 < r.forma.baza90
                      ? "text-data-amber-ink"
                      : "text-ink-soft"
                }`}
              >
                {String(r.forma.okno90).replace(".", ",")}
              </span>
              /90 ost. 6{" "}
              <span className="text-faint">
                (wcześniej {String(r.forma.baza90).replace(".", ",")})
              </span>
            </span>
          )}
          {r.rywal?.srednia != null && (
            <span title="Ile rywal średnio oddaje przeciwnikom na tym rynku i które miejsce zajmuje na tle ligi (wyższa pozycja = hojniejszy rywal)">
              rywal puszcza śr.{" "}
              <span className="font-data font-semibold text-ink-soft">
                {String(r.rywal.srednia).replace(".", ",")}
              </span>
              {r.rywal.rank != null && r.rywal.z != null && (
                <span className="text-faint">
                  {" "}
                  (#{r.rywal.rank}/{r.rywal.z})
                </span>
              )}
            </span>
          )}
        </div>
      )}

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {r.drabinka.map((s) => (
          <span
            key={s.linia}
            className="inline-flex items-baseline gap-1.5 rounded-(--radius-control) border border-hairline bg-paper px-2 py-1"
            title={
              `${r.rynek}: ${linLabel(s.linia)} po kursie ${fmtKurs(s.kurs)}` +
              (s.p_model != null
                ? `. Model daje tej linii ${fmtProc(s.p_model)} szans`
                : ". Model nie liczył tej linii")
            }
          >
            <span className="font-data text-[11px] font-semibold text-ink">
              {linLabel(s.linia)}
            </span>
            <span className="font-data text-xs font-semibold text-brand-deep">
              {fmtKurs(s.kurs)}
            </span>
            {s.p_model != null && (
              <span className="font-data text-[10px] text-muted">
                {fmtProc(s.p_model)}
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

/** memo: przy zmianie filtrów listy karty się nie przerenderowują wszystkie. */
export const RadarCard = memo(function RadarCard({
  w,
  rank,
}: {
  w: RadarWpis;
  rank: number;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const info = rodzajInfo(w);

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
        {/* wiersz główny: numer · dioda · kto · rodzaj · mecz */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-3 pt-3.5 sm:grid-cols-[auto_1.5fr_auto] sm:px-5">
          <span
            aria-hidden
            className="font-display hidden w-10 shrink-0 text-center text-[1.7rem] font-bold leading-none text-ink/15 transition-colors group-hover:text-brand/40 sm:block"
          >
            {rank}
          </span>

          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span
                title={info.tytul}
                className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
              >
                <span
                  aria-hidden
                  className={`absolute -inset-1 rounded-full opacity-20 ${info.dioda}`}
                />
                <span aria-hidden className={`h-2 w-2 rounded-full ${info.dioda}`} />
              </span>
              <span className="truncate font-semibold">{w.podmiot}</span>
              <span className="text-sm text-muted">
                {w.druzyna}
                {w.pozycja && w.pozycja !== "?" ? ` · ${w.pozycja}` : ""}
              </span>
            </span>
            <span className="mt-1 block truncate text-xs text-faint">
              {w.mecz} · {fmtDataCzas(w.kickoff_ts)}
            </span>
          </span>

          <span className="flex flex-col items-end justify-center gap-1">
            <span
              title={info.tytul}
              className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                w.rodzaj === "transfer"
                  ? "bg-brand-wash text-brand-deep"
                  : w.rodzaj === "debiutant"
                    ? "bg-data-amber-wash text-data-amber-ink"
                    : w.rodzaj === "forma"
                      ? "bg-data-green-wash text-data-green-ink"
                      : "border border-hairline bg-paper text-muted"
              }`}
            >
              {info.label}
            </span>
            {w.xi === true && (
              <span
                className="text-[9px] uppercase tracking-wide text-faint"
                title="Zawodnik jest w przewidywanym lub potwierdzonym pierwszym składzie"
              >
                w składzie
              </span>
            )}
          </span>
        </span>

        {/* pasek meta: skrót powodu + rozwinięcie */}
        <span className="flex items-center gap-x-2.5 px-4 pb-3.5 sm:pl-[4.75rem] sm:pr-5">
          <span className="min-w-0 truncate text-[11px] text-muted">
            {open ? "" : opisWpisu(w)}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
            {open ? "zwiń" : "kursy i liczby"}
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
      </button>

      {/* rozwinięcie: pełny opis + rynki z drabinkami */}
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
              <p className="max-w-prose text-sm leading-relaxed text-ink-soft">
                {opisWpisu(w)}
              </p>

              <div className="mt-4 space-y-2.5">
                {w.rynki.map((r) => (
                  <RynekBlok key={r.rynek_kod} r={r} />
                ))}
              </div>

              {w.sezony && w.sezony.length > 0 && (
                <div className="mt-4">
                  <p
                    className="mb-2 text-[10px] uppercase tracking-wide text-faint"
                    title="Średnie z całych sezonów (bieżący i poprzednie) — także z poprzedniego klubu i ligi, jeśli zawodnik zmienił barwy"
                  >
                    średnie sezonowe
                  </p>
                  <div className="space-y-2">
                    {w.sezony.map((s, i) => (
                      <SezonWiersz key={`${s.turniej}-${s.rok}-${i}`} s={s} />
                    ))}
                  </div>
                </div>
              )}

              <p className="mt-4 border-t border-hairline pt-3 text-xs leading-relaxed text-muted">
                Drabinka kursów Superbetu z pełnym kontekstem: ostatnie mecze,
                forma, hojność rywala i średnie sezonowe. Tam, gdzie przy
                kursie widzisz procent, model policzył szansę tej linii.
                Resztę oceń sam, zanim postawisz.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
