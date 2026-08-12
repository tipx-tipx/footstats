"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { wyplata } from "@/lib/podatek";
import Link from "next/link";
import { useEffect, useState } from "react";

import { fmtKurs, fmtProc, opisZakladu } from "@/lib/format";
import type { ValueBet } from "@/lib/types";

const wejscie = {
  hidden: { opacity: 0, y: 18 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: 0.07 * i, duration: 0.55, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

/**
 * DOKĄD PROWADZI KARTA Z NAGŁÓWKA — musi trafiać w zakładkę, która ten typ
 * POKAŻE (naprawione 2026-08-04).
 *
 * Zgłoszenie usera: „skąd ten typ Nahuel Banegas, jak nigdzie go nie widać".
 * Nie widać go było dosłownie. Link prowadził do `?rodzaj=okazje`, a strona
 * zna wyłącznie `pewniaki | value | radar | wszystko` — parametr leciał do
 * kosza, otwierała się pierwsza niepusta zakładka (Drabinki), a kotwica
 * `#bet-N` nie wskazywała na nic. Ten sam błąd miały sugestie STS
 * (`?rodzaj=sugestie`). Oba kody zostały po starym układzie zakładek.
 *
 * Zwykły typ zawodniczy NIE MA dziś własnej listy na stronie głównej — od
 * 1 sierpnia jest tam tylko „Wysokie szanse", a te wymagają flagi pewniaka.
 * Więc dla takiego typu jedyne uczciwe miejsce to STRONA MECZU, gdzie stoi
 * razem z pokryciami i kursami. Lepiej odesłać tam, niż udawać zakładkę,
 * która go nie pokaże.
 */
function hrefPozycji(b: ValueBet): string {
  // typ drużynowy ma własną stronę i tam jest jego karta z rozpisanym
  // rachunkiem; strona meczu pokazałaby go jako jeden wiersz wśród pokryć
  if (b.podmiot_typ === "druzyna") return "/druzyny";
  if (b.sugestia) return `/?rodzaj=value#bet-${b.id}`;
  if (b.pewniak) return `/?rodzaj=pewniaki#bet-${b.id}`;
  return `/mecze/${b.mecz_id}`;
}

/** Napis pod kartą MUSI zgadzać się z tym, dokąd ona prowadzi (2026-08-04).
 *
 * Link naprawiliśmy 03.08 („karta z nagłówka prowadzi tam, gdzie typ naprawdę
 * jest"), ale napis został stary i przy typie, który nie jest ani pewniakiem,
 * ani sugestią, obiecywał „niżej", a otwierał stronę meczu. Zmierzone na
 * produkcji 04.08: jedyny typ zawodniczy dnia był dokładnie taki, więc kafelek
 * kłamał przy KAŻDYM wejściu na stronę główną. */
function etykietaLinku(b: ValueBet): string {
  if (b.podmiot_typ === "druzyna") return "zobacz typy na drużyny →";
  return b.sugestia || b.pewniak
    ? "zobacz szczegóły niżej →"
    : "zobacz analizę meczu →";
}

/** „1 typ", „3 typy", „8 typów" – trzy formy, nie dwie. */
function odmienTypy(n: number): string {
  if (n === 1) return "typ";
  const r10 = n % 10;
  const r100 = n % 100;
  return r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? "typy" : "typów";
}

/** „1 meczu", „3 meczach", „8 meczach" – po „w" idzie miejscownik. */
function odmienMecze(n: number): string {
  return n === 1 ? "meczu" : "meczach";
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
 * bukmacher przepłaca. Kieszonkowa wersja toru dowodu z BetCard
 * (bez historii – w hero liczy się 2-sekundowa czytelność).
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
      title={`Kurs ${fmtKurs(kurs)} wycenia tę szansę na ${fmtProc(implied)} (z marżą bukmachera), a my dajemy ${fmtProc(model)}. Gdy nasza liczba stoi wyżej niż wycena kursu, bukmacher płaci więcej, niż powinien.`}
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
          <dt className="text-[11px] text-faint">nasza szansa</dt>
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
      /* PUSTY STAN MA PROWADZIĆ DALEJ, NIE TŁUMACZYĆ RYNKU (2026-08-06).
         Stało tu „STAN RYNKU / Rynek wycenia blisko modelu" — nasze
         słownictwo, a do tego zdanie nieprawdziwe w najczęstszym przypadku:
         listy zwykle nie ma nie dlatego, że bukmacher nie przepłaca, tylko
         dlatego, że nie wystawił jeszcze kursów na zawodników albo część
         rynków mamy wstrzymanych. Zamiast diagnozy — jedno zdanie i wyjście. */
      <div className="glow-pop">
      <div className="cut-corner relative border border-hairline bg-card p-6 text-center">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-faint">
          dziś na zawodników
        </p>
        <p className="mt-3 font-display text-lg font-bold">
          Nic, co warto zagrać
        </p>
        <p className="mx-auto mt-1.5 max-w-xs text-sm leading-relaxed text-muted">
          Kursy na statystyki piłkarzy bukmacher wystawia zwykle dzień przed
          meczem. Typy na całe drużyny mamy gotowe cały czas.
        </p>
        <Link
          href="/druzyny"
          className="font-display mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-brand transition-colors hover:text-brand-strong"
        >
          Zobacz typy na drużyny →
        </Link>
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
      {/* celownik HUD – narożniki „namierzają" kartę przy każdej zmianie */}
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
            chowa go CSS (motion-reduce) – warunek w JS dawałby inny HTML na
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
                  {/* ETYKIETA MA OPISYWAĆ, A NIE ŁADNIE BRZMIEĆ (2026-08-04).
                      „najpewniejszy typ teraz" był FALLBACKIEM dla typów BEZ
                      przewagi po podatku — czyli słowo „najpewniejszy" trafiało
                      dokładnie tam, gdzie nie było czym się chwalić. Zmierzone
                      na Nahuelu Banegasie: nagłówek strony obiecywał
                      „najpewniejszy typ teraz", a rekord miał wartość netto
                      −10,8%, własną pewność „niska" i był wznowiony z księgi
                      bez pełnej analizy. Do tego karta pokazywała wyłącznie
                      pochlebne liczby (szansa 80%), więc nic tego nie
                      prostowało. */}
                  {/* MÓWIMY PO LUDZKU, NIE PO NASZEMU (06.08). „Namierzone
                      przez skan" to nasze wewnętrzne słownictwo — pierwszy
                      napis, jaki widzi ktoś wchodzący na stronę, nie może
                      wymagać znajomości tego, jak działa nasz pipeline. */}
                  {/* ETYKIETA NIE ZALEŻY JUŻ OD ZNAKU WARTOŚCI (2026-08-13).
                      Gałąź „nasz typ na dziś" odpalała się przy wartości
                      netto > 0, a odkąd karta pokazuje szansę ściągniętą do
                      uczciwej ceny, ta wartość jest ujemna przy każdym typie —
                      więc nagłówek zawsze schodził do fallbacku. Etykieta ma
                      mówić, CZYM jest typ, a nie jaki ma znak przy liczbie,
                      która opisuje marżę bukmachera. */}
                  {idx === 0
                    ? bet.sugestia
                      ? "nasz typ dnia · kurs w STS"
                      : bet.pewniak
                        ? "największa szansa na dziś"
                        : "pierwszy z naszej listy"
                    : `nasz typ ${idx + 1} z ${bets.length}`}
                </p>
                <p className="mt-3.5 font-display text-[1.7rem] font-bold leading-tight tracking-tight">
                  {bet.podmiot}
                </p>
                {/* ZDANIE SKŁADA `opisZakladu`, NIE TA KARTA (2026-08-06).
                    Tu stało „powyżej" wpisane na sztywno — nieszkodliwe,
                    dopóki karta widziała wyłącznie typy zawodnicze (te są
                    praktycznie zawsze „powyżej"). Od dziś trafiają tu też
                    drużynowe, a wśród nich „gole drużyny PONIŻEJ 0,5" —
                    karta ogłaszałaby zakład odwrotny do tego, który stawiamy.
                    `opisZakladu` zna też rynek „kto więcej", który nie ma
                    ani linii, ani kierunku. */}
                <p className="mt-1 text-sm text-muted">
                  {opisZakladu(bet)} · {bet.mecz}
                </p>
              </div>

              {/* separator sekcji karty (motyw biletu z perforacją został
                  wyłącznie na kuponach – tam ma sens) */}
              <div aria-hidden className="mx-6 border-t border-dashed border-hairline-strong" />

              <div className="px-6 pb-1 pt-4">
                <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
                  {bet.kurs != null ? (
                    /* KURS NA PIERWSZYM PLANIE, KWOTA POD SPODEM (06.08).
                       Jedna zasada na całą stronę: główną liczbą jest zawsze
                       kurs albo mnożnik, bo nie ma w sobie skali — „3,90"
                       wygląda tak samo mocno przy stawce 10 i 500 zł.
                       Złotówki wyjaśniają, co to znaczy, ale nie ustawiają
                       wrażenia: przy małej stawce zawsze brzmią jak drobne. */
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        kurs ({bet.bukmacher})
                      </p>
                      <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                        {fmtKurs(bet.kurs)}
                      </p>
                      <p className="mt-1 text-[11px] text-faint">
                        z 10 zł → {Math.round(wyplata(bet.kurs, 10, bet.tryb_podatku))} zł
                      </p>
                    </div>
                  ) : (
                    <>
                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-faint">nasza szansa</p>
                        <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                          {fmtProc(bet.p_model)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-wide text-faint">
                          dobry kurs od
                        </p>
                        <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                          ~{fmtKurs(bet.fair_kurs * 1.05)}
                        </p>
                      </div>
                    </>
                  )}
                  {/* „+81,0% bukmacher przepłaca" ZDJĘTE 06.08. Liczba była
                      prawdziwa w naszej arytmetyce, ale czyta się jak
                      obietnica 81% zysku — a to nasza ocena różnicy zdań
                      z bukmacherem, nie fakt o wypłacie. W dodatku dublowała
                      tor niżej, który tę samą rzecz pokazuje dwiema liczbami,
                      jakie każdy rozumie: ile dajemy my, ile wycenia kurs. */}
                  {bet.kurs != null && (
                    <div title="Tyle szans dajemy temu zdarzeniu po naszych wyliczeniach">
                      <p className="text-[10px] uppercase tracking-wide text-faint">
                        nasza szansa
                      </p>
                      <p className="font-data mt-0.5 text-2xl font-semibold text-ink">
                        {fmtProc(bet.p_model)}
                      </p>
                      {/* porównanie z wyceną kursu robi tor niżej — tu byłoby
                          trzecią kopią tej samej liczby na jednej karcie */}
                    </div>
                  )}
                </div>
                {bet.kurs != null && <TorWyceny model={bet.p_model} kurs={bet.kurs} />}
              </div>
              <p className="px-6 pb-5 pt-3">
                <span className="inline-flex items-center gap-1 text-sm font-medium text-brand transition-transform group-hover:translate-x-0.5">
                  {etykietaLinku(bet)}
                </span>
              </p>
            </Link>
          </motion.div>
        </AnimatePresence>

        {/* strzałki + licznik w belce karty (obok „zobacz szczegóły") –
            nad Linkiem (z-10), więc klik nie otwiera pozycji */}
        {bets.length > 1 && (
          <div className="absolute bottom-3.5 right-4 z-10 flex items-center gap-1.5">
            <button
              onClick={() => setIdx((i) => (i - 1 + bets.length) % bets.length)}
              aria-label="Poprzednia pozycja"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-hairline bg-card/80 text-ink-soft backdrop-blur transition-colors hover:border-brand hover:text-brand sm:h-7 sm:w-7"
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
              className="flex h-9 w-9 items-center justify-center rounded-full border border-hairline bg-card/80 text-ink-soft backdrop-blur transition-colors hover:border-brand hover:text-brand sm:h-7 sm:w-7"
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
 * Blueprint boiska – techniczny rysunek połowy boiska cienką kreską
 * (tablica taktyczna), wtopiony w tło hero za kartą podglądu.
 * Kolor z tokenu marki, wygaszany maską – piłka nożna bez kiczu.
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
      className="flex shrink-0 items-center pr-2"
    >
      {lista.map((b, i) => (
        <li key={`${b.id}-${i}`} className="flex shrink-0 items-center">
          {/* czysty tekst zamiast chipów-naklejek: feed jak pasek notowań */}
          <Link
            href={hrefPozycji(b)}
            tabIndex={ariaHidden ? -1 : undefined}
            className="group/poz flex items-center gap-2 whitespace-nowrap py-1 text-sm transition-colors"
          >
            <span className="font-medium text-ink transition-colors group-hover/poz:text-brand">
              {b.podmiot}
            </span>
            {/* pasek pokazuje CAŁY skan od 04.08, więc „0,5+" kłamało przy
                każdym typie „poniżej" — a te są dziś większością drużynowych */}
            <span className="text-muted">{opisZakladu(b, true)}</span>
            <span className="font-data font-semibold text-brand-deep">
              {b.kurs != null ? `@${fmtKurs(b.kurs)}` : fmtProc(b.p_model)}
            </span>
          </Link>
          <span aria-hidden className="mx-4 h-3.5 w-px rotate-12 bg-hairline-strong" />
        </li>
      ))}
    </ul>
  );
  return (
    <div className="relative mt-10 flex items-center gap-5 border-y border-hairline py-2.5">
      {/* stała plakietka – nie jedzie z feedem */}
      <span className="font-display flex shrink-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-brand-deep">
        <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-data-green" />
        dziś typujemy
      </span>
      <div
        className="ticker relative flex-1"
        // „pełna lista niżej" przestało być prawdą 2026-08-04: pasek pokazuje
        // CAŁY skan (zawodnicy + drużyny), a lista niżej tylko zawodników
        title="Żywe pozycje z bieżącego skanu — zawodnicy i drużyny"
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
  liczbaOkazji,
  spotlightBets,
  tickerBets = [],
  konkrety,
}: {
  liga: string;
  sezon: string;
  liczbaOkazji: number;
  spotlightBets: ValueBet[];
  tickerBets?: ValueBet[];
  /** co użytkownik dostaje DZIŚ (fakt, nie obietnica) — rozbite na dwa
   *  produkty, bo prowadzą do różnych miejsc */
  konkrety?: { zawodnicze: number; druzynowe: number; meczow: number };
}) {
  return (
    <section className="relative mb-12 pt-8 sm:pt-14">
      {/* aurora marki – oddychające tło hero; pełna szerokość OKNA
          (kalkulacja 50%−50vw), żeby kolor nigdy nie ucinał się na
          krawędzi kontenera treści */}
      <div
        aria-hidden
        className="aurora pointer-events-none absolute -bottom-6 -top-28"
        style={{ left: "calc(50% - 50vw)", right: "calc(50% - 50vw)" }}
      />

      {/* blueprint boiska – taktyczny rysunek wtopiony za prawą kolumną */}
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
            {/* GÓRA STRONY BYŁA ZAGRACONA (06.08). Nad nagłówkiem stały dwie
                rzeczy naraz: nadtytuł „Typy na dziś · Piłka klubowa 2026/27"
                i plakietka „ostatnie sprawdzenie · 14:40" — czyli dwie linijki
                drobnego tekstu, zanim czytelnik dojdzie do zdania, po które
                przyszedł. Godzina i tak stoi w pasku na górze („kursy z 14:40")
                i jest widoczna z każdej strony, więc tutaj była trzecim
                powtórzeniem tej samej informacji.
                Zostaje sam sezon, drobnym drukiem — kontekst, nie nagłówek. */}
            <p className="text-xs font-medium uppercase tracking-widest text-faint">
              {liga} {sezon}
            </p>
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
            {/* OBIETNICA MA PASOWAĆ DO TEGO, CO DZIŚ JEST (2026-08-06).
                Zdanie mówiło wyłącznie o piłkarzach, a typy zawodnicze to
                dziś jeden na dwadzieścia — bukmacher kwotuje ich statystyki
                niemal tylko w Ameryce Południowej. Ktoś, kto wchodzi po raz
                pierwszy, czytał obietnicę o piłkarzach i widział pod nią
                jedną pozycję. */}
            Liczy prawdziwe szanse – gole, rożne i kartki całych drużyn oraz
            strzały i faule pojedynczych piłkarzy. Wybiera najpewniejsze typy
            i składa z nich gotowe kupony. A gdy bukmacher zawyży kurs –
            pokazuje, gdzie masz przewagę.
          </motion.p>

          {/* CO DOSTAJESZ — trzy liczby zamiast obietnicy (2026-08-04).
              Przegląd pod sprzedaż: nigdzie na stronie nie było odpowiedzi na
              pierwsze pytanie kogoś, kto ma zapłacić — ile typów, na czym
              i jak często. To są FAKTY Z DZIŚ, nie deklaracja („dziś 28
              typów"), więc jutrzejsza inna liczba niczemu nie przeczy. */}
          {konkrety && konkrety.zawodnicze + konkrety.druzynowe > 0 && (
            <motion.div
              variants={wejscie}
              initial="hidden"
              animate="show"
              custom={3.5}
              className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted"
            >
              {/* ZERA NIE OGŁASZAMY (2026-08-06). Strumień zawodniczy bywa
                  pusty całymi dniami — Superbet kwotuje propsy niemal tylko
                  w Ameryce Południowej. „0 typów na zawodników" jako PIERWSZA
                  liczba na stronie brzmiało jak awaria, choć obok stało
                  dwadzieścia typów drużynowych. Nie chowamy niczego: brak
                  pozycji znaczy brak, a nie „mamy, ale nie pokażemy". */}
              {konkrety.zawodnicze > 0 && (
                <>
                  <span>
                    <strong className="font-data font-semibold text-ink">
                      {konkrety.zawodnicze}
                    </strong>{" "}
                    {odmienTypy(konkrety.zawodnicze)} na zawodników
                  </span>
                  <span aria-hidden className="h-3.5 w-px bg-hairline-strong" />
                </>
              )}
              {/* KLIKALNE, bo to zwykle NAJWIĘKSZA liczba na tej stronie,
                  a jedyne przejście do tych typów stało dotąd pod listą,
                  drobnym drukiem — poniżej pierwszego ekranu telefonu */}
              <Link
                href="/druzyny"
                className="underline decoration-hairline-strong underline-offset-4 transition-colors hover:text-brand hover:decoration-brand"
              >
                <strong className="font-data font-semibold text-ink">
                  {konkrety.druzynowe}
                </strong>{" "}
                na drużyny
              </Link>
              <span aria-hidden className="h-3.5 w-px bg-hairline-strong" />
              <span>
                w{" "}
                <strong className="font-data font-semibold text-ink">
                  {konkrety.meczow}
                </strong>{" "}
                {odmienMecze(konkrety.meczow)}
              </span>
              <span aria-hidden className="h-3.5 w-px bg-hairline-strong" />
              <span>przeliczane co godzinę</span>
            </motion.div>
          )}

          <motion.div
            variants={wejscie}
            initial="hidden"
            animate="show"
            custom={4}
            className="mt-7 flex flex-wrap items-center gap-3"
          >
            {/* GŁÓWNY PRZYCISK MA PROWADZIĆ DO CZEGOŚ (2026-08-06).
                Przy zerze typów zawodniczych „Zobacz dzisiejsze typy ↓"
                przewijało do pustej listy — jedyna wyraźna akcja na ekranie
                kończyła się komunikatem o braku. Gdy tu nic nie ma, przycisk
                prowadzi tam, gdzie towar jest. */}
            <span className="glow-drop inline-flex transition-transform hover:-translate-y-0.5">
              {liczbaOkazji > 0 ? (
                <a
                  href="#okazje"
                  className="cut-corner-sm font-display inline-flex items-center gap-2 bg-brand px-6 py-3 text-sm font-semibold uppercase tracking-wide text-on-brand transition-colors hover:bg-brand-strong"
                >
                  Zobacz {odmienOkazje(liczbaOkazji)}
                  <span aria-hidden>↓</span>
                </a>
              ) : (
                <Link
                  href="/druzyny"
                  className="cut-corner-sm font-display inline-flex items-center gap-2 bg-brand px-6 py-3 text-sm font-semibold uppercase tracking-wide text-on-brand transition-colors hover:bg-brand-strong"
                >
                  Zobacz typy na drużyny
                  <span aria-hidden>→</span>
                </Link>
              )}
            </span>
            <Link
              href="/jak-to-dziala"
              className="font-display inline-flex items-center gap-1.5 px-2 py-3 text-sm font-medium uppercase tracking-wide text-ink-soft transition-colors hover:text-brand"
            >
              Jak to działa?
              <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
            </Link>
          </motion.div>

        </div>

        {/* prawa: żywy podgląd skanera; poniżej lg (kolumny w stosie) karta
            nie rozjeżdża się na pełną szerokość – bilet, nie baner */}
        <motion.div
          variants={wejscie}
          initial="hidden"
          animate="show"
          custom={3}
          className="relative mx-auto w-full max-w-xl lg:mx-0 lg:max-w-none"
        >
          {/* Poświata jest DEKORACJĄ, więc nie wolno jej ruszać układu.
              `-inset-16` (64 px na stronę) mieści się na desktopie w marginesach
              kontenera, ale na telefonie karta zajmuje prawie całą szerokość –
              i te 64 px wypychały CAŁĄ stronę w bok o 48 px (wykryte
              `npm run audyt`, 2026-07-27). Na wąskim ekranie poświata jest
              odpowiednio węższa. */}
          <div
            aria-hidden
            className="glow-brand pointer-events-none absolute -inset-3 sm:-inset-16"
          />
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
