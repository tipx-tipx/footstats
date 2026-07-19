"use client";

import { motion, useReducedMotion } from "framer-motion";

import { useSzerokosc } from "@/lib/useSzerokosc";

/**
 * OsSzans — jedna oś wyceny 0–100% dla rozwinięcia karty typu.
 *
 * Zastępuje dawny układ „tor + osobna legenda + osobny rządek liczb":
 * liczby siedzą bezpośrednio przy swoich znacznikach (zakotwiczone etykiety
 * nad/pod torem), a przewaga jest podświetlonym odcinkiem z wartością nad
 * środkiem. Dzięki temu ta sama informacja czyta się w jednym spojrzeniu,
 * bez skakania między wykresem a legendą.
 *
 * Kolizje etykiet liczymy w pikselach na zmierzonej szerokości toru
 * (procentowy odstęp zawodził na mobile: 13% z ~350 px to mniej niż
 * szerokość podpisu). Etykieta odsunięta od znacznika dostaje cienką
 * nóżkę, żeby liczba nie odklejała się od swojej kreski; etykietę górną
 * gasimy przy kolizji z etykietą odcinka — znacznik zostaje, liczby
 * ratuje tooltip.
 */

export type OsZnacznik = {
  id: string;
  /** Pozycja jako szansa 0–1. */
  p: number;
  /** Liczba przy znaczniku, np. "78%" albo "9/10". */
  wartosc: string;
  /** Krótki podpis pod liczbą, np. "model", "kurs wycenia". */
  podpis: string;
  /** Kolor i waga znacznika: pełne = głosy główne, duchy = kontekst. */
  ton: "ink" | "brand" | "duch-zielony" | "duch-brand";
  /** Gdzie stoi etykieta z liczbą; "brak" = tylko tooltip. */
  etykieta: "dol" | "gora" | "brak";
  /** Pełne wyjaśnienie w tooltipie. */
  tytul: string;
};

const ZNACZNIK_STYL: Record<OsZnacznik["ton"], { kreska: string; duch: boolean }> = {
  ink: { kreska: "bg-ink", duch: false },
  brand: { kreska: "bg-brand", duch: false },
  "duch-zielony": { kreska: "bg-data-green/70", duch: true },
  "duch-brand": { kreska: "bg-brand/50", duch: true },
};

/** Pozycja na torze z marginesem, żeby znacznik nie uciekał za krawędź. */
const pozNaTorze = (p: number) => Math.min(Math.max(p * 100, 2), 98);

/** Szacunek szerokości etykiety w px: podpis 9 px uppercase, liczba mono 15 px. */
const szerEtykietyPx = (wartosc: string, podpis: string) =>
  Math.max(podpis.length * 6.4, wartosc.length * 9.5, 24);

/**
 * Rozsuwa pozycje etykiet (%) tak, żeby sąsiadki się nie nakładały.
 * Wymagany odstęp pary liczony z realnych szerokości etykiet i zmierzonej
 * szerokości toru; przed pomiarem zapasowe 13 pp.
 */
function rozsunEtykiety(
  pozycje: number[],
  szerokosci: number[],
  torPx: number,
): number[] {
  const gap = (a: number, b: number) =>
    torPx > 0
      ? Math.min((((szerokosci[a] + szerokosci[b]) / 2 + 8) / torPx) * 100, 46)
      : 13;
  // margines krawędzi z realnej szerokości etykiety — żeby tekst nie
  // wystawał poza tor (przed pomiarem zapasowe 5 pp)
  const brzeg = (i: number) =>
    torPx > 0 ? Math.min(((szerokosci[i] / 2 + 2) / torPx) * 100, 30) : 5;
  const idx = pozycje
    .map((p, i) => ({
      p: Math.min(Math.max(p, brzeg(i)), 100 - brzeg(i)),
      i,
    }))
    .sort((a, b) => a.p - b.p);
  for (let k = 1; k < idx.length; k++) {
    const g = gap(idx[k - 1].i, idx[k].i);
    if (idx[k].p - idx[k - 1].p < g) idx[k].p = idx[k - 1].p + g;
  }
  // gdy ogon wyjechał za prawą krawędź, cofamy całą grupę
  const ost = idx[idx.length - 1];
  const nadmiar = ost ? ost.p - (100 - brzeg(ost.i)) : 0;
  if (nadmiar > 0) {
    for (const x of idx) x.p = Math.max(brzeg(x.i), x.p - nadmiar);
  }
  const wynik = new Array<number>(pozycje.length);
  for (const x of idx) wynik[x.i] = x.p;
  return wynik;
}

/** Odcinek na torze (przewaga = zielony, przepłata = bursztyn). */
type Odcinek = { od: number; do: number } | null | undefined;

export function OsSzans({
  znaczniki,
  przewaga,
  przewagaWartosc,
  przewagaPodpis,
  przeplata,
  przeplataWartosc,
  przeplataPodpis,
  przeplataTytul,
  ariaLabel,
}: {
  znaczniki: OsZnacznik[];
  /** Podświetlony odcinek przewagi, w szansach 0–1. */
  przewaga?: Odcinek;
  /** Liczba nad odcinkiem przewagi, np. "+13%". */
  przewagaWartosc?: string;
  /** Podpis nad liczbą przewagi, np. "twoja przewaga". */
  przewagaPodpis?: string;
  /** Odcinek przepłaty (kurs wycenia wyżej niż model), w szansach 0–1. */
  przeplata?: Odcinek;
  /** Liczba nad odcinkiem przepłaty, np. "+8 pp". */
  przeplataWartosc?: string;
  /** Podpis nad liczbą przepłaty, np. "przepłata". */
  przeplataPodpis?: string;
  /** Pełne wyjaśnienie przepłaty w tooltipie. */
  przeplataTytul?: string;
  ariaLabel: string;
}) {
  const reduced = useReducedMotion();
  const { ref: torRef, w: torPx } = useSzerokosc();

  const segmenty = [
    przewaga && przewaga.do > przewaga.od
      ? {
          id: "przewaga",
          od: pozNaTorze(przewaga.od),
          do: pozNaTorze(przewaga.do),
          wartosc: przewagaWartosc,
          podpis: przewagaPodpis,
          tytul: undefined as string | undefined,
          kolorTor: "bg-data-green/45",
          kolorTekst: "text-data-green-ink",
          kolorPodpis: "text-data-green-ink/90",
        }
      : null,
    przeplata && przeplata.do > przeplata.od
      ? {
          id: "przeplata",
          od: pozNaTorze(przeplata.od),
          do: pozNaTorze(przeplata.do),
          wartosc: przeplataWartosc,
          podpis: przeplataPodpis,
          tytul: przeplataTytul,
          kolorTor: "bg-data-amber/40",
          kolorTekst: "text-data-amber-ink",
          kolorPodpis: "text-data-amber-ink/90",
        }
      : null,
  ].filter((s) => s != null);

  const etykietySegmentow = segmenty
    .filter((s) => s.wartosc != null || s.podpis != null)
    .map((s) => ({
      ...s,
      x: Math.min(Math.max((s.od + s.do) / 2, 12), 88),
      szer: szerEtykietyPx(s.wartosc ?? "", s.podpis ?? ""),
    }));

  // etykiety dolne: rozsunięte na realnych szerokościach, z nóżką przy odsunięciu
  const dolne = znaczniki.filter((z) => z.etykieta === "dol");
  const dolneX = rozsunEtykiety(
    dolne.map((z) => pozNaTorze(z.p)),
    dolne.map((z) => szerEtykietyPx(z.wartosc, z.podpis)),
    torPx,
  );

  // etykiety górne: gasną przy kolizji z etykietą odcinka (znacznik zostaje)
  const gorne = znaczniki
    .filter((z) => z.etykieta === "gora")
    .filter((z) =>
      etykietySegmentow.every((s) => {
        const wymagany =
          torPx > 0
            ? (((szerEtykietyPx(z.wartosc, z.podpis) + s.szer) / 2 + 8) / torPx) * 100
            : 16;
        return Math.abs(pozNaTorze(z.p) - s.x) >= wymagany;
      }),
    );

  const wjazd = reduced
    ? { initial: false as const }
    : { initial: { opacity: 0 } };

  return (
    <div role="img" aria-label={ariaLabel} ref={torRef}>
      {/* nad torem: wartości odcinków nad ich środkiem + duchy kontekstu */}
      {(etykietySegmentow.length > 0 || gorne.length > 0) && (
        <div className="relative h-9">
          {etykietySegmentow.map((s) => (
            <motion.span
              key={s.id}
              {...wjazd}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.45, duration: 0.3 }}
              title={s.tytul}
              className="absolute bottom-0 -translate-x-1/2 text-center leading-none"
              style={{ left: `${s.x}%` }}
            >
              {s.podpis && (
                <span
                  className={`block whitespace-nowrap text-[9px] uppercase tracking-wide ${
                    s.wartosc != null ? "text-faint" : s.kolorPodpis
                  }`}
                >
                  {s.podpis}
                </span>
              )}
              {s.wartosc != null && (
                <span
                  className={`font-data mt-0.5 block whitespace-nowrap text-sm font-bold ${s.kolorTekst}`}
                >
                  {s.wartosc}
                </span>
              )}
            </motion.span>
          ))}
          {gorne.map((z) => (
            <motion.span
              key={z.id}
              {...wjazd}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.45, duration: 0.3 }}
              title={z.tytul}
              className="absolute bottom-0 -translate-x-1/2 text-center leading-none"
              style={{ left: `${pozNaTorze(z.p)}%` }}
            >
              <span className="block whitespace-nowrap text-[9px] uppercase tracking-wide text-faint">
                {z.podpis}
              </span>
              <span
                className={`font-data mt-0.5 block whitespace-nowrap text-xs font-semibold ${
                  z.ton === "duch-zielony" ? "text-data-green-ink/85" : "text-muted"
                }`}
              >
                {z.wartosc}
              </span>
            </motion.span>
          ))}
        </div>
      )}

      {/* tor */}
      <div className="relative h-6">
        <span
          aria-hidden
          className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-full bg-hairline"
        />
        {segmenty.map((s) => (
          <motion.span
            key={s.id}
            aria-hidden
            initial={reduced ? false : { width: 0 }}
            animate={{ width: `${s.do - s.od}%` }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className={`absolute top-1/2 h-2 -translate-y-1/2 rounded-full ${s.kolorTor}`}
            style={{ left: `${s.od}%` }}
          />
        ))}
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
        {znaczniki.map((z) => {
          const styl = ZNACZNIK_STYL[z.ton];
          return (
            <motion.span
              key={z.id}
              title={z.tytul}
              initial={reduced ? false : { left: "2%", opacity: 0 }}
              animate={{ left: `${pozNaTorze(z.p)}%`, opacity: 1 }}
              transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
              className={`absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ${
                styl.duch ? "h-3.5 w-[2px]" : "h-5 w-[3px]"
              } ${styl.kreska}`}
            />
          );
        })}
      </div>

      {/* nóżki: cienka linia od znacznika do odsuniętej etykiety */}
      <svg
        aria-hidden
        className="block h-2 w-full"
        viewBox="0 0 100 8"
        preserveAspectRatio="none"
      >
        {dolne.map((z, i) => {
          const od = pozNaTorze(z.p);
          if (Math.abs(dolneX[i] - od) < 1.5) return null;
          return (
            <motion.line
              key={z.id}
              {...wjazd}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.35, duration: 0.3 }}
              x1={od}
              y1={0.5}
              x2={dolneX[i]}
              y2={7.5}
              stroke="var(--color-hairline-strong)"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>

      {/* pod torem: liczby zakotwiczone przy znacznikach */}
      <div className="relative h-10">
        {dolne.map((z, i) => (
          <motion.span
            key={z.id}
            {...wjazd}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.35, duration: 0.3 }}
            title={z.tytul}
            className="absolute top-0 -translate-x-1/2 text-center leading-none"
            style={{ left: `${dolneX[i]}%` }}
          >
            <span
              className={`font-data block whitespace-nowrap text-[15px] font-bold ${
                z.ton === "brand" ? "text-brand-deep" : "text-ink"
              }`}
            >
              {z.wartosc}
            </span>
            <span className="mt-1 block whitespace-nowrap text-[9px] uppercase tracking-wide text-faint">
              {z.podpis}
            </span>
          </motion.span>
        ))}
      </div>

      {/* skala — bez niej znaczniki wiszą w próżni */}
      <div className="font-data relative h-3 text-[9px] text-faint">
        <span className="absolute left-0">0</span>
        <span className="absolute left-1/2 -translate-x-1/2">50%</span>
        <span className="absolute right-0">100%</span>
      </div>
    </div>
  );
}
