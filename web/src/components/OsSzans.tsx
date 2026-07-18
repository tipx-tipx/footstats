"use client";

import { motion, useReducedMotion } from "framer-motion";

/**
 * OsSzans — jedna oś wyceny 0–100% dla rozwinięcia karty typu.
 *
 * Zastępuje dawny układ „tor + osobna legenda + osobny rządek liczb":
 * liczby siedzą bezpośrednio przy swoich znacznikach (zakotwiczone etykiety
 * nad/pod torem), a przewaga jest podświetlonym odcinkiem z wartością nad
 * środkiem. Dzięki temu ta sama informacja czyta się w jednym spojrzeniu,
 * bez skakania między wykresem a legendą.
 *
 * Etykiety dolne rozsuwamy algorytmicznie (realne dane potrafią zejść się
 * na 1–2 pp), etykietę górną gasimy przy kolizji z etykietą przewagi —
 * znacznik zostaje, liczby ratuje tooltip.
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

/** Rozsuwa pozycje etykiet (%) tak, żeby sąsiadki dzieliło min. minGap pp. */
function rozsunEtykiety(pozycje: number[], minGap: number): number[] {
  const idx = pozycje
    .map((p, i) => ({ p: Math.min(Math.max(p, 5), 95), i }))
    .sort((a, b) => a.p - b.p);
  for (let k = 1; k < idx.length; k++) {
    if (idx[k].p - idx[k - 1].p < minGap) idx[k].p = idx[k - 1].p + minGap;
  }
  // gdy ogon wyjechał za prawą krawędź, cofamy całą grupę
  const nadmiar = idx.length > 0 ? idx[idx.length - 1].p - 95 : 0;
  if (nadmiar > 0) {
    for (const x of idx) x.p = Math.max(5, x.p - nadmiar);
  }
  const wynik = new Array<number>(pozycje.length);
  for (const x of idx) wynik[x.i] = x.p;
  return wynik;
}

export function OsSzans({
  znaczniki,
  przewaga,
  przewagaWartosc,
  przewagaPodpis,
  ariaLabel,
}: {
  znaczniki: OsZnacznik[];
  /** Podświetlony odcinek przewagi, w szansach 0–1. */
  przewaga?: { od: number; do: number } | null;
  /** Liczba nad odcinkiem przewagi, np. "+13%". */
  przewagaWartosc?: string;
  /** Podpis nad liczbą przewagi, np. "twoja przewaga". */
  przewagaPodpis?: string;
  ariaLabel: string;
}) {
  const reduced = useReducedMotion();

  const seg =
    przewaga && przewaga.do > przewaga.od
      ? { od: pozNaTorze(przewaga.od), do: pozNaTorze(przewaga.do) }
      : null;
  const segSrodek = seg
    ? Math.min(Math.max((seg.od + seg.do) / 2, 12), 88)
    : null;
  const pokazPrzewage = seg != null && przewagaWartosc != null;

  // etykiety dolne: rozsunięte, żeby bliskie wyceny się nie nakładały
  const dolne = znaczniki.filter((z) => z.etykieta === "dol");
  const dolneX = rozsunEtykiety(
    dolne.map((z) => pozNaTorze(z.p)),
    13,
  );

  // etykiety górne: gasną przy kolizji z etykietą przewagi (znacznik zostaje)
  const gorne = znaczniki
    .filter((z) => z.etykieta === "gora")
    .filter(
      (z) =>
        !pokazPrzewage ||
        segSrodek == null ||
        Math.abs(pozNaTorze(z.p) - segSrodek) >= 16,
    );

  const wjazd = reduced
    ? { initial: false as const }
    : { initial: { opacity: 0 } };

  return (
    <div role="img" aria-label={ariaLabel}>
      {/* nad torem: przewaga jako liczba nad swoim odcinkiem + duchy kontekstu */}
      {(pokazPrzewage || gorne.length > 0) && (
        <div className="relative h-9">
          {pokazPrzewage && (
            <motion.span
              {...wjazd}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.45, duration: 0.3 }}
              className="absolute bottom-0 -translate-x-1/2 text-center leading-none"
              style={{ left: `${segSrodek}%` }}
            >
              {przewagaPodpis && (
                <span className="block whitespace-nowrap text-[9px] uppercase tracking-wide text-faint">
                  {przewagaPodpis}
                </span>
              )}
              <span className="font-data mt-0.5 block whitespace-nowrap text-sm font-bold text-data-green-ink">
                {przewagaWartosc}
              </span>
            </motion.span>
          )}
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
        {seg && (
          <motion.span
            aria-hidden
            initial={reduced ? false : { width: 0 }}
            animate={{ width: `${seg.do - seg.od}%` }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-data-green/45"
            style={{ left: `${seg.od}%` }}
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

      {/* pod torem: liczby zakotwiczone przy znacznikach */}
      <div className="relative mt-1 h-10">
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
