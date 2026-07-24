"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { fmtKurs, fmtProc } from "@/lib/format";
import type { RadarRynek, RadarSezon, RadarSzczebel, RadarWpis } from "@/lib/types";

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

/** Plakietka sygnału — tylko dla wpisów Z SYGNAŁEM (zwykła drabinka bez). */
function sygnalInfo(
  w: RadarWpis,
): { label: string; dioda: string; badge: string; tytul: string } | null {
  if (w.rodzaj === "transfer") {
    return {
      label: "nowy w drużynie",
      dioda: "bg-brand",
      badge: "bg-brand-wash text-brand-deep",
      tytul:
        "Historia zawodnika pochodzi z innej ligi lub innego klubu. Kursy na takich graczy bywają niedograne, bo bukmacher ma mało danych z nowego miejsca.",
    };
  }
  if (w.rodzaj === "debiutant") {
    return {
      label: "debiutant",
      dioda: "bg-data-amber",
      badge: "bg-data-amber-wash text-data-amber-ink",
      tytul:
        "Superbet daje mu pełne kursy, ale w danych nie ma ani jednego jego meczu — rynek wycenia go w ciemno. Sprawdź sam, skąd przyszedł, zanim postawisz.",
    };
  }
  if (w.rodzaj === "forma") {
    return {
      label: "seria formy",
      dioda: "bg-data-green",
      badge: "bg-data-green-wash text-data-green-ink",
      tytul:
        "Zawodnik regularnie przebija linię w ostatnich meczach, wyraźnie ponad swój wcześniejszy poziom. Model celowo nie dolicza formy do szansy — to sygnał dodatkowy.",
    };
  }
  return null;
}

/** Najlepszy grywalny szczebel karty — nagłówkowa statystyka („hero"). */
function heroSzczebel(
  w: RadarWpis,
): { rynek: RadarRynek; s: RadarSzczebel } | null {
  let best: { rynek: RadarRynek; s: RadarSzczebel; q: number } | null = null;
  for (const r of w.rynki) {
    for (const s of r.drabinka) {
      const p = s.pokrycie;
      if (!p || p.z < 5 || s.kurs < 1.45) continue;
      const q = p.traf / p.z + Math.min(s.kurs, 3) / 100; // tiebreak: wyższy kurs
      if (!best || q > best.q) best = { rynek: r, s, q };
    }
  }
  return best ? { rynek: best.rynek, s: best.s } : null;
}

/** Zwinięta zajawka: konkret z danych, nie szablon. */
function zajawka(w: RadarWpis): string {
  const hero = heroSzczebel(w);
  if (hero) {
    const { rynek, s } = hero;
    const p = s.pokrycie!;
    return `${rynek.rynek} ${linLabel(s.linia)} · trafione ${p.traf}/${p.z} ost. · kurs ${fmtKurs(s.kurs)}`;
  }
  if (w.rodzaj === "debiutant") {
    return "Pełne kursy Superbetu bez żadnej historii w danych — rynek zgaduje.";
  }
  if (w.rodzaj === "transfer") {
    return w.stara_liga
      ? `Historia z poprzedniej ligi: ${w.stara_liga}. Kurs może tego nie uwzględniać.`
      : "Świeży transfer — historia z poprzedniego klubu.";
  }
  return "Drabinka kursów z pełną historią występów.";
}

/** Akapit „dlaczego ta karta" w rozwinięciu — tylko wpisy z sygnałem. */
function opisSygnalu(w: RadarWpis): string {
  if (w.rodzaj === "transfer") {
    if (w.powod === "zmiana_ligi") {
      const liga = w.stara_liga ? ` (${w.stara_liga})` : "";
      const nowa =
        !w.mecze_nowa || w.mecze_nowa === 0
          ? "W nowej lidze jeszcze nie debiutował"
          : `W nowej lidze zagrał dopiero ${w.mecze_nowa} ${w.mecze_nowa === 1 ? "mecz" : w.mecze_nowa < 5 ? "mecze" : "meczów"}`;
      return (
        `Ostatnie ${w.mecze_stara ?? ""} występów zaliczył w poprzedniej lidze${liga}. ` +
        `${nowa}. Liczby niżej pochodzą głównie ze starego adresu — kurs może tego nie uwzględniać.`
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
      `W tej serii średnio ${liczba(f.srednia90_okno)} na 90 minut, wcześniej ${liczba(f.srednia90_baza)}.`
    );
  }
  return "";
}

/** Wiersz szczebla drabinki: linia · kurs · szansa modelu · pokrycie. */
function SzczebelWiersz({ r, s }: { r: RadarRynek; s: RadarSzczebel }) {
  const p = s.pokrycie;
  const udzial = p && p.z > 0 ? p.traf / p.z : null;
  return (
    <div
      className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] items-center gap-x-3 py-1"
      title={
        `${r.rynek}: ${linLabel(s.linia)} po kursie ${fmtKurs(s.kurs)}` +
        (p ? `. Linia trafiona w ${p.traf} z ${p.z} ostatnich meczów` : "") +
        (s.p_model != null
          ? `. Model daje tej linii ${fmtProc(s.p_model)} szans`
          : ". Model nie liczył tej linii")
      }
    >
      <span className="font-data text-xs font-semibold text-ink">
        {linLabel(s.linia)}
      </span>
      <span className="font-data text-xs font-semibold text-brand-deep">
        {fmtKurs(s.kurs)}
      </span>
      <span className="font-data text-[11px] text-muted">
        {s.p_model != null ? fmtProc(s.p_model) : "—"}
      </span>
      {udzial != null ? (
        <span className="flex items-center gap-2">
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-paper">
            <span
              className={`block h-full rounded-full ${
                udzial >= 0.7
                  ? "bg-data-green"
                  : udzial >= 0.4
                    ? "bg-data-amber"
                    : "bg-ink/25"
              }`}
              style={{ width: `${Math.round(udzial * 100)}%` }}
            />
          </span>
          <span className="font-data w-8 shrink-0 text-right text-[11px] text-ink-soft">
            {p!.traf}/{p!.z}
          </span>
        </span>
      ) : (
        <span className="text-[11px] text-faint">brak historii</span>
      )}
    </div>
  );
}

/** Blok jednego rynku: nagłówek, drabinka-tabela, ostatnie mecze, kontekst. */
function RynekBlok({ r }: { r: RadarRynek }) {
  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-xs font-semibold text-ink">{r.rynek}</span>
        <span className="flex items-baseline gap-3">
          {r.forma && (
            <span
              className="font-data text-[11px]"
              title="Średnia na 90 minut z 6 ostatnich meczów vs wcześniejsza baza"
            >
              <span
                className={
                  r.forma.okno90 > r.forma.baza90
                    ? "font-semibold text-data-green-ink"
                    : r.forma.okno90 < r.forma.baza90
                      ? "font-semibold text-data-amber-ink"
                      : "text-muted"
                }
              >
                {r.forma.okno90 > r.forma.baza90
                  ? "forma ↑"
                  : r.forma.okno90 < r.forma.baza90
                    ? "forma ↓"
                    : "forma ="}{" "}
                {liczba(r.forma.okno90)}/90
              </span>{" "}
              <span className="text-faint">
                (baza {liczba(r.forma.baza90)})
              </span>
            </span>
          )}
          {r.srednia90 != null && (
            <span
              className="font-data text-[11px] text-muted"
              title="Średnia liczba zdarzeń na 90 minut z całej dostępnej historii"
            >
              śr. {liczba(r.srednia90)}/90
            </span>
          )}
        </span>
      </div>

      {/* drabinka: linia · kurs · model · pokrycie ostatnich */}
      <div className="mt-2">
        <div className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] gap-x-3 border-b border-hairline pb-1 text-[9px] uppercase tracking-wide text-faint">
          <span>linia</span>
          <span>kurs</span>
          <span title="Szansa modelu na przebicie tej linii">model</span>
          <span title="Ile z ostatnich meczów przebiło tę linię">
            trafienia w ost. meczach
          </span>
        </div>
        {r.drabinka.map((s) => (
          <SzczebelWiersz key={s.linia} r={r} s={s} />
        ))}
      </div>

      {r.ostatnie && r.ostatnie.length > 0 && (
        <div className="mt-2.5">
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-[9px] uppercase tracking-wide text-faint">
              ostatnie
            </span>
            {r.ostatnie.map((c, i) => (
              <span
                key={i}
                title={`${c} vs ${r.rywale?.[i] ?? "?"}${
                  r.minuty?.[i] != null ? ` (${r.minuty[i]} min)` : ""
                }`}
                className={`font-data inline-flex h-5 min-w-5 items-center justify-center rounded px-1 text-[11px] font-semibold ${
                  c > 0 ? "bg-brand-wash text-brand-deep" : "bg-paper text-faint"
                }`}
              >
                {c}
              </span>
            ))}
          </div>
          {r.rywale && r.rywale.length > 0 && (
            <p className="mt-1 truncate text-[10px] text-faint">
              od najnowszego: vs {r.rywale.slice(0, 4).join(", vs ")}
              {r.rywale.length > 4 ? "…" : ""}
            </p>
          )}
        </div>
      )}

      {r.rywal?.srednia != null && (
        <p
          className="mt-2 text-[11px] text-muted"
          title="Ile najbliższy rywal średnio oddaje przeciwnikom na tym rynku i które miejsce zajmuje na tle ligi (wyższa pozycja = hojniejszy rywal)"
        >
          rywal puszcza śr.{" "}
          <span className="font-data font-semibold text-ink-soft">
            {liczba(r.rywal.srednia)}
          </span>
          {r.rywal.rank != null && r.rywal.z != null && (
            <span className="text-faint">
              {" "}
              (#{r.rywal.rank} z {r.rywal.z} w lidze)
            </span>
          )}
          {r.rywal.liga != null && (
            <span className="text-faint">
              {" "}
              · śr. ligi {liczba(r.rywal.liga)}
            </span>
          )}
        </p>
      )}
    </div>
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

/** memo: przy zmianie filtrów listy karty się nie przerenderowują wszystkie. */
export const RadarCard = memo(function RadarCard({
  w,
}: {
  w: RadarWpis;
  rank?: number;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const sygnal = sygnalInfo(w);
  const opis = opisSygnalu(w);

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
        {/* wiersz główny: kto · info · plakietki */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-1.5 pt-3.5 sm:px-5">
          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {sygnal && (
                <span
                  title={sygnal.tytul}
                  className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
                >
                  <span
                    aria-hidden
                    className={`absolute -inset-1 rounded-full opacity-20 ${sygnal.dioda}`}
                  />
                  <span
                    aria-hidden
                    className={`h-2 w-2 rounded-full ${sygnal.dioda}`}
                  />
                </span>
              )}
              <span className="truncate font-semibold">{w.podmiot}</span>
              <span className="text-sm text-muted">
                {w.druzyna}
                {w.pozycja && w.pozycja !== "?" ? ` · ${w.pozycja}` : ""}
              </span>
            </span>
            <span className="mt-0.5 block truncate text-xs text-faint">
              vs {w.przeciwnik}
              {w.minuty_sr6 != null && ` · gra śr. ${w.minuty_sr6} min`}
            </span>
          </span>

          <span className="flex flex-col items-end justify-center gap-1">
            {sygnal && (
              <span
                title={sygnal.tytul}
                className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${sygnal.badge}`}
              >
                {sygnal.label}
              </span>
            )}
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

        {/* zajawka z konkretem + rozwinięcie */}
        <span className="flex items-center gap-x-2.5 px-4 pb-3.5 sm:px-5">
          <span className="min-w-0 truncate text-[11px] font-medium text-ink-soft">
            {zajawka(w)}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
            {open ? "zwiń" : "analiza"}
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

      {/* rozwinięcie: opis sygnału + rynki + sezony */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          >
            <div className="border-t border-hairline bg-paper/50 px-4 py-4 sm:px-6">
              {opis && (
                <p className="mb-4 max-w-prose text-sm leading-relaxed text-ink-soft">
                  {opis}
                </p>
              )}

              <div className="space-y-2.5">
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
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
