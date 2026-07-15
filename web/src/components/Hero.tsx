"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Link from "next/link";
import { useEffect, useState } from "react";

import { fmtKurs, fmtLinia, fmtProc } from "@/lib/format";
import type { ValueBet } from "@/lib/types";

const wejscie = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.07 * i, duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

function hrefPozycji(b: ValueBet): string {
  return b.sugestia
    ? `/?rodzaj=sugestie#bet-${b.id}`
    : b.pewniak
      ? `/?rodzaj=pewniaki#bet-${b.id}`
      : `/?rodzaj=okazje#bet-${b.id}`;
}

/** Poprawna polska odmiana: "1 okazję", "3 okazje", "8 okazji", "22 okazje". */
function odmienOkazje(n: number): string {
  if (n === 1) return "1 okazję";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "okazje" : "okazji"}`;
}

/**
 * Teza produktu jednym spojrzeniem: wycena kursu (1/kurs) i szansa modelu
 * na wspólnym torze 0–100%; zielony odcinek między znacznikami = o ile
 * bukmacher przepłaca. Kieszonkowa wersja PorownanieWycen z BetCard
 * (bez historii — w hero liczy się 2-sekundowa czytelność).
 */
function TorWyceny({ model, kurs }: { model: number; kurs: number }) {
  if (kurs <= 1) return null;
  const implied = 1 / kurs;
  const poz = (p: number) => Math.min(Math.max(p * 100, 2), 98);
  const lewy = poz(Math.min(implied, model));
  const prawy = poz(Math.max(implied, model));
  return (
    <div
      className="mt-4"
      title={`Kurs ${fmtKurs(kurs)} wycenia tę szansę na ${fmtProc(implied)} (z marżą bukmachera), model daje ${fmtProc(model)}. Gdy model stoi wyżej niż wycena kursu, bukmacher płaci więcej, niż powinien.`}
    >
      <div className="relative h-4">
        <span className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-hairline" />
        {model > implied && (
          <span
            className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-data-green/45"
            style={{ left: `${lewy}%`, width: `${prawy - lewy}%` }}
          />
        )}
        <span
          className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink"
          style={{ left: `${poz(implied)}%` }}
        />
        <span
          className="absolute top-1/2 h-4 w-[3px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand"
          style={{ left: `${poz(model)}%` }}
        />
      </div>
      <dl className="mt-1.5 flex flex-wrap items-baseline gap-x-5 gap-y-1">
        <div className="flex items-baseline gap-1.5">
          <span aria-hidden className="inline-block h-2 w-2 translate-y-px rounded-full bg-ink" />
          <dt className="text-[11px] text-faint">kurs wycenia</dt>
          <dd className="font-data text-sm font-semibold text-ink">{fmtProc(implied)}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span aria-hidden className="inline-block h-2 w-2 translate-y-px rounded-full bg-brand" />
          <dt className="text-[11px] text-faint">model daje</dt>
          <dd className="font-data text-sm font-semibold text-ink">{fmtProc(model)}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * Żywy podgląd skanera: karta-bilet rotująca po top-okazjach co ~5 s
 * z pierścieniem „namierzenia" przy każdej zmianie. Pauza na hover
 * i w ukrytej karcie przeglądarki; przy ograniczonym ruchu stoi na
 * najlepszej pozycji (kropki dalej działają ręcznie).
 */
function ZywyPodglad({ bets }: { bets: ValueBet[] }) {
  const reduced = useReducedMotion();
  const [idx, setIdx] = useState(0);
  const [wstrzymany, setWstrzymany] = useState(false);

  useEffect(() => {
    if (reduced || wstrzymany || bets.length < 2) return;
    const t = setInterval(() => {
      if (document.hidden) return;
      setIdx((i) => (i + 1) % bets.length);
    }, 5200);
    return () => clearInterval(t);
  }, [reduced, wstrzymany, bets.length]);

  if (bets.length === 0) {
    return (
      <div className="glow-pop">
      <div className="cut-corner relative border border-hairline bg-card p-6 text-center">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">
          stan rynku
        </p>
        <p className="mt-3 font-display text-lg font-bold">
          Rynek wycenia blisko modelu
        </p>
        <p className="mx-auto mt-1.5 max-w-xs text-sm leading-relaxed text-muted">
          W tej chwili bukmacher nie przepłaca za żadne zdarzenie. Skan trwa,
          a strona odświeży się sama po każdym przeliczeniu kursów.
        </p>
      </div>
      </div>
    );
  }

  const bet = bets[idx];

  return (
    <div
      onMouseEnter={() => setWstrzymany(true)}
      onMouseLeave={() => setWstrzymany(false)}
      className="relative"
    >
      {/* celownik HUD — narożniki „namierzają" kartę przy każdej zmianie */}
      <span aria-hidden className="pointer-events-none absolute -inset-2.5">
        {[
          "left-0 top-0 border-l-2 border-t-2",
          "right-0 top-0 border-r-2 border-t-2",
          "bottom-0 left-0 border-b-2 border-l-2",
          "bottom-0 right-0 border-b-2 border-r-2",
        ].map((rog) => (
          <motion.span
            key={`${rog}-${idx}`}
            initial={{ opacity: 0.3, scale: 1.25 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className={`absolute h-5 w-5 border-brand-bright ${rog}`}
          />
        ))}
      </span>

      <div className="glow-pop">
      <div className="cut-corner relative overflow-hidden border border-brand/25 bg-card">
        {/* pasek postępu do następnego namierzenia; przy ograniczonym ruchu
            chowa go CSS (motion-reduce) — warunek w JS dawałby inny HTML na
            serwerze niż u klienta (hydration mismatch) */}
        {bets.length > 1 && (
          <span
            key={`postep-${idx}`}
            aria-hidden
            className="postep-skanu absolute inset-x-0 bottom-0 z-10 h-0.5 bg-gradient-to-r from-brand to-brand-bright motion-reduce:hidden"
            style={{ animationPlayState: wstrzymany ? "paused" : "running" }}
          />
        )}
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div
            key={bet.id}
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <Link href={hrefPozycji(bet)} className="group block">
              <div className="bg-gradient-to-br from-brand-wash via-brand-wash/60 to-card px-6 pb-5 pt-5">
                <p className="font-display text-[11px] font-semibold uppercase tracking-widest text-brand">
                  {idx === 0
                    ? bet.sugestia
                      ? "najmocniejszy typ dnia · kurs w STS"
                      : bet.ev_pct != null && bet.ev_pct > 0
                        ? "najlepsza okazja teraz"
                        : "najpewniejszy typ teraz"
                    : `namierzone przez skan · ${idx + 1} z ${bets.length}`}
                </p>
                <p className="mt-3.5 font-display text-[1.7rem] font-bold leading-tight tracking-tight">
                  {bet.podmiot}
                </p>
                <p className="mt-1 text-sm text-muted">
                  {bet.rynek.toLowerCase()} powyżej{" "}
                  {fmtLinia(bet.linia)} · {bet.mecz}
                </p>
              </div>

              {/* separator sekcji karty (motyw biletu z perforacją został
                  wyłącznie na kuponach — tam ma sens) */}
              <div aria-hidden className="mx-6 border-t border-dashed border-hairline-strong" />

              <div className="px-6 pb-1 pt-4">
                <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                  {bet.kurs != null ? (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        kurs ({bet.bukmacher})
                      </p>
                      <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                        {fmtKurs(bet.kurs)}
                      </p>
                    </div>
                  ) : (
                    <>
                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-faint">szansa modelu</p>
                        <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                          {fmtProc(bet.p_model)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-faint">
                          opłaca się od kursu
                        </p>
                        <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                          ~{fmtKurs(bet.fair_kurs * 1.05)}
                        </p>
                      </div>
                    </>
                  )}
                  {bet.kurs != null && bet.ev_pct != null && bet.ev_pct > 0 && (
                    <div title="O tyle wypłata z kursu przebija realną szansę zdarzenia. To nadwyżka, którą bukmacher płaci ponad uczciwą wycenę">
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        bukmacher przepłaca
                      </p>
                      <p className="font-data mt-0.5 text-2xl font-semibold text-data-green">
                        +{bet.ev_pct.toFixed(1).replace(".", ",")}%
                      </p>
                    </div>
                  )}
                </div>
                {bet.kurs != null && <TorWyceny model={bet.p_model} kurs={bet.kurs} />}
              </div>
              <p className="px-6 pb-5 pt-3">
                <span className="inline-flex items-center gap-1 text-sm font-medium text-brand transition-transform group-hover:translate-x-0.5">
                  zobacz szczegóły niżej →
                </span>
              </p>
            </Link>
          </motion.div>
        </AnimatePresence>

        {/* strzałki + licznik w belce karty (obok „zobacz szczegóły") —
            nad Linkiem (z-10), więc klik nie otwiera pozycji */}
        {bets.length > 1 && (
          <div className="absolute bottom-3.5 right-4 z-10 flex items-center gap-1.5">
            <button
              onClick={() => setIdx((i) => (i - 1 + bets.length) % bets.length)}
              aria-label="Poprzednia pozycja"
              className="flex h-7 w-7 items-center justify-center rounded-full border border-hairline bg-card/80 text-ink-soft backdrop-blur transition-colors hover:border-brand hover:text-brand"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
                <path d="M15 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <span
              className="font-data min-w-7 text-center text-xs text-faint"
              aria-live="polite"
            >
              {idx + 1}/{bets.length}
            </span>
            <button
              onClick={() => setIdx((i) => (i + 1) % bets.length)}
              aria-label="Następna pozycja"
              className="flex h-7 w-7 items-center justify-center rounded-full border border-hairline bg-card/80 text-ink-soft backdrop-blur transition-colors hover:border-brand hover:text-brand"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden>
                <path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}

/**
 * Blueprint boiska — techniczny rysunek połowy boiska cienką kreską
 * (tablica taktyczna), wtopiony w tło hero za kartą podglądu.
 * Kolor z tokenu marki, wygaszany maską — piłka nożna bez kiczu.
 */
function BlueprintBoiska({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 420 560"
      fill="none"
      aria-hidden
      className={className}
      style={{ stroke: "color-mix(in oklab, var(--color-brand) 30%, transparent)" }}
    >
      <g strokeWidth="1.6">
        {/* obrys połowy boiska */}
        <rect x="10" y="10" width="400" height="540" rx="2" />
        {/* pole karne i bramkowe */}
        <rect x="95" y="10" width="230" height="118" />
        <rect x="152" y="10" width="116" height="44" />
        {/* punkt karny i łuk pola karnego */}
        <circle cx="210" cy="90" r="2.6" fill="color-mix(in oklab, var(--color-brand) 30%, transparent)" strokeWidth="0" />
        <path d="M158 128 A 62 62 0 0 0 262 128" />
        {/* koło środkowe przecięte linią połowy */}
        <path d="M118 550 A 92 92 0 0 1 302 550" />
        <circle cx="210" cy="550" r="2.6" fill="color-mix(in oklab, var(--color-brand) 30%, transparent)" strokeWidth="0" />
        {/* łuki rożne */}
        <path d="M10 26 A 16 16 0 0 0 26 10" />
        <path d="M394 10 A 16 16 0 0 0 410 26" />
      </g>
    </svg>
  );
}

/**
 * Feed skanu: żywe pozycje suną powoli jako klikalne chipy w języku HUD
 * (ścięty róg), za stałą plakietką „skan na żywo". Hover/fokus pauzuje.
 */
function TickerRynkow({ bets }: { bets: ValueBet[] }) {
  if (bets.length === 0) return null;
  // za krótka lista = dziury w pętli; powielaj aż tor ma sensowną długość
  let lista = bets;
  while (lista.length < 8) lista = [...lista, ...bets];
  const tor = (ariaHidden: boolean) => (
    <ul
      aria-hidden={ariaHidden || undefined}
      className="flex shrink-0 items-center gap-3 pr-3"
    >
      {lista.map((b, i) => (
        <li key={`${b.id}-${i}`} className="shrink-0">
          <Link
            href={hrefPozycji(b)}
            tabIndex={ariaHidden ? -1 : undefined}
            className="cut-corner-sm group/chip flex items-center gap-3 whitespace-nowrap border border-hairline bg-card/70 py-2 pl-3.5 pr-4 backdrop-blur-sm transition-colors hover:border-brand/50 hover:bg-brand-wash/60"
          >
            <span className="text-sm">
              <span className="font-medium text-ink">{b.podmiot}</span>{" "}
              <span className="text-muted">
                {b.rynek.toLowerCase()} {fmtLinia(b.linia)}+
              </span>
            </span>
            {b.kurs != null ? (
              <span className="font-data text-sm font-semibold text-brand">
                @{fmtKurs(b.kurs)}
              </span>
            ) : (
              <span className="font-data text-sm font-semibold text-brand">
                {fmtProc(b.p_model)}
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
  return (
    <div className="relative mt-10 flex items-center gap-4">
      {/* stała plakietka — nie jedzie z feedem */}
      <span className="cut-corner-sm font-display flex shrink-0 items-center gap-2 border border-brand/30 bg-brand-wash/70 px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-widest text-brand-deep">
        <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-data-green" />
        skan na żywo
      </span>
      <div
        className="ticker relative flex-1"
        title="Żywe pozycje z bieżącego skanu, pełna lista niżej"
      >
        <div className="ticker-tor">
          {tor(false)}
          {tor(true)}
        </div>
      </div>
    </div>
  );
}

export function Hero({
  liga,
  sezon,
  aktualizacja,
  liczbaOkazji,
  spotlightBets,
  tickerBets = [],
}: {
  liga: string;
  sezon: string;
  aktualizacja: string;
  liczbaOkazji: number;
  spotlightBets: ValueBet[];
  tickerBets?: ValueBet[];
}) {
  return (
    <section className="relative mb-12 pt-8 sm:pt-14">
      {/* aurora marki — oddychające tło hero; pełna szerokość OKNA
          (kalkulacja 50%−50vw), żeby kolor nigdy nie ucinał się na
          krawędzi kontenera treści */}
      <div
        aria-hidden
        className="aurora pointer-events-none absolute -bottom-6 -top-28"
        style={{ left: "calc(50% - 50vw)", right: "calc(50% - 50vw)" }}
      />

      {/* blueprint boiska — taktyczny rysunek wtopiony za prawą kolumną */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-40 -top-16 hidden lg:block"
        style={{
          WebkitMaskImage:
            "radial-gradient(80% 75% at 45% 40%, black 20%, transparent 74%)",
          maskImage:
            "radial-gradient(80% 75% at 45% 40%, black 20%, transparent 74%)",
        }}
      >
        <BlueprintBoiska className="h-[620px] w-auto" />
      </div>

      <div className="relative grid items-center gap-9 lg:grid-cols-[1.3fr_1fr] lg:gap-10">
        {/* lewa: obietnica → liczba → zaufanie → akcja */}
        <div>
          <motion.div
            variants={wejscie}
            initial="hidden"
            animate="show"
            custom={0}
            className="flex flex-wrap items-center gap-3"
          >
            <p className="flex items-center gap-2.5 text-xs font-semibold uppercase tracking-widest text-brand">
              <span aria-hidden className="h-px w-6 bg-brand-bright" />
              Skan rynków · {liga} {sezon}
            </p>
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-card px-2.5 py-1 text-[11px] text-muted shadow-(--shadow-card)"
              title="Cykl w chmurze pobiera statystyki i kursy, przelicza model i odświeża tę stronę"
            >
              <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-data-green" />
              żywe dane · {aktualizacja}
            </span>
          </motion.div>

          <motion.h1
            variants={wejscie}
            initial="hidden"
            animate="show"
            custom={1}
            className="mt-6 max-w-2xl text-balance text-[2.7rem] font-bold leading-[1.06] tracking-tight sm:text-[3.5rem]"
          >
            Model, który <span className="text-brand">typuje za Ciebie</span>
          </motion.h1>

          <motion.p
            variants={wejscie}
            initial="hidden"
            animate="show"
            custom={3}
            className="mt-6 max-w-xl text-base leading-relaxed text-muted"
          >
            Liczy prawdziwe szanse piłkarzy na strzały, faule czy odbiory,
            wybiera najpewniejsze typy i składa z nich gotowe kupony. A gdy
            bukmacher zawyży kurs – pokazuje, gdzie masz przewagę.
          </motion.p>

          <motion.div
            variants={wejscie}
            initial="hidden"
            animate="show"
            custom={4}
            className="mt-7 flex flex-wrap items-center gap-3"
          >
            <span className="glow-drop inline-flex transition-transform hover:-translate-y-0.5">
              <a
                href="#okazje"
                className="cut-corner-sm font-display inline-flex items-center gap-2 bg-brand px-6 py-3 text-sm font-semibold uppercase tracking-wide text-on-brand transition-colors hover:bg-brand-strong"
              >
                Zobacz{" "}
                {liczbaOkazji > 0 ? odmienOkazje(liczbaOkazji) : "dzisiejsze typy"}
                <span aria-hidden>↓</span>
              </a>
            </span>
            <Link
              href="/jak-to-dziala"
              className="cut-corner-sm font-display inline-flex items-center gap-2 border border-hairline-strong bg-card/60 px-6 py-3 text-sm font-medium uppercase tracking-wide text-ink-soft backdrop-blur transition-colors hover:border-brand hover:text-brand"
            >
              Jak to działa?
            </Link>
          </motion.div>

        </div>

        {/* prawa: żywy podgląd skanera */}
        <motion.div
          variants={wejscie}
          initial="hidden"
          animate="show"
          custom={3}
          className="relative"
        >
          <div aria-hidden className="glow-brand pointer-events-none absolute -inset-16" />
          <ZywyPodglad bets={spotlightBets} />
        </motion.div>
      </div>

      {/* ticker: żywy skan rynków */}
      <motion.div
        variants={wejscie}
        initial="hidden"
        animate="show"
        custom={6}
      >
        <TickerRynkow bets={tickerBets} />
      </motion.div>
    </section>
  );
}
