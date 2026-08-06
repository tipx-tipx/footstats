"use client";

import { useState } from "react";

/**
 * JEDEN UKŁAD ROZWINIĘCIA DLA WSZYSTKICH KART (2026-08-01, część 2 przeglądu).
 *
 * Diagnoza usera: rozwinięcie odpowiadało na pytania, których nikt nie zadał
 * (tabele mnożników, przedziały ufności, rozkłady), a nie odpowiadało na to
 * jedno, które zadaje każdy: DLACZEGO TEN TYP I CZEMU MAM W TO WIERZYĆ.
 * Do tego każda karta opowiadała to inaczej – drabinka wodospadem, drużyna
 * werdyktem i osią, a zawodnik zakładkami – więc nauka jednej karty nie
 * pomagała przy następnej.
 *
 * Stąd ten plik: cztery kroki, zawsze w tej samej kolejności, w każdej karcie.
 *
 *   1. skąd bierzemy tę liczbę   – punkt wyjścia z historii
 *   2. co zmienia ten mecz       – korekty na rywala, sędziego, miejsce gry
 *   3. jak było ostatnio         – surowa historia, mecz po meczu
 *   4. gdzie jest przewaga       – nasza szansa kontra cena bukmachera
 *
 * Krok, dla którego nie mamy materiału, po prostu nie istnieje – zamiast
 * pustego nagłówka „brak danych". Kolejność zostaje ta sama, więc karta
 * z trzema krokami czyta się jak ta z czterema.
 *
 * Wszystko, co potrzebne jest przy diagnozie modelu, a nie przy decyzji
 * o zakładzie, jedzie do `SzczegolyTechniczne` – zwiniętej z domysłu.
 */

export type KrokKod = "skad" | "zmiana" | "ostatnio" | "pokrycie" | "przewaga";

export const KROK_TYTUL: Record<KrokKod, string> = {
  skad: "skąd ta liczba",
  zmiana: "co zmienia ten mecz",
  ostatnio: "jak było ostatnio",
  // pokrycie poprzeczek doszło 2026-08-06 (przebudowa na życzenie usera):
  // fakty z historii mają stać PRZED naszymi korektami i ceną
  pokrycie: "pokrycie poprzeczek",
  przewaga: "gdzie jest przewaga",
};

/**
 * Jeden krok historii. Na szerokim ekranie tytuł stoi w wąskiej kolumnie
 * z lewej (jak notatka na marginesie), a treść trzyma jedną, ciągłą kolumnę
 * tekstu – dzięki temu rozwinięcie czyta się jak akapit, a nie jak cztery
 * osobne panele. Na telefonie tytuł wraca nad treść.
 */
export function Krok({
  kod,
  tytul,
  zwijalny = false,
  children,
}: {
  kod: KrokKod;
  /** nadpisanie tytułu, gdy karta nazywa ten krok trafniej */
  tytul?: string;
  /**
   * KROK NA KLIK, NIE NA ZAWSZE OTWARTY (2026-08-06).
   *
   * Rozwinięta karta drabinki miała ~1000 px na telefonie, a cztery takie
   * karty dawały stronę na 7650 px — nikt nie dochodził do końca. Najdłuższy
   * jest krok „jak było ostatnio": lista dziesięciu meczów, czyli surowy
   * materiał do sprawdzenia NASZEJ liczby, a nie do podjęcia decyzji.
   * Decyzję niosą trzy pozostałe kroki, więc historia czeka pod jednym
   * kliknięciem — nie znika, przestaje tylko zajmować pół ekranu.
   */
  zwijalny?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const naglowek = tytul ?? KROK_TYTUL[kod];
  return (
    <section className="border-t border-hairline py-4 first:border-t-0 first:pt-0 sm:grid sm:grid-cols-[7.5rem_minmax(0,1fr)] sm:gap-x-6">
      {zwijalny ? (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          // `npm run zrzuty --rozwin` klika wszystko, co ma aria-expanded —
          // bez tego znacznika rozwijałby też kroki i zrzut pokazywałby stan,
          // którego użytkownik nigdy nie widzi (patrz scripts/zrzuty.mjs)
          data-rozwiniecie="krok"
          className="mb-1.5 flex items-center gap-1.5 text-left text-[10px] font-semibold uppercase leading-relaxed tracking-[0.12em] text-faint transition-colors hover:text-brand sm:mb-0 sm:items-start"
        >
          {naglowek}
          <span
            aria-hidden
            className={`transition-transform ${open ? "rotate-180" : ""}`}
          >
            ⌄
          </span>
        </button>
      ) : (
        <h4 className="mb-1.5 text-[10px] font-semibold uppercase leading-relaxed tracking-[0.12em] text-faint sm:mb-0">
          {naglowek}
        </h4>
      )}
      {(!zwijalny || open) && <div className="min-w-0">{children}</div>}
    </section>
  );
}

/** Kontener historii – trzyma kroki jednym rytmem odstępów. */
export function Kroki({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>;
}

/**
 * Materiał diagnostyczny: potrzebny, ale dla jednego użytkownika na stu.
 * Zwinięty z domysłu – jeżeli coś stąd jest potrzebne do DECYZJI, to znaczy,
 * że powinno stać w jednym z czterech kroków wyżej, a nie tutaj.
 */
export function SzczegolyTechniczne({
  children,
  etykieta = "Szczegóły techniczne",
}: {
  children: React.ReactNode;
  etykieta?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5 border-t border-hairline pt-4">
      {/* PRZYCISK, NIE SZARY NAPIS (2026-08-06, uwaga usera: „szczegóły
          techniczne powinny być lepiej widoczne"). Etykieta w kolorze `faint`
          ginęła na dole rozwinięcia — jedyne zejście do pełnego rachunku
          wyglądało jak przypis. Ten sam wygląd co „Pokaż pozostałe drabinki":
          pełna szerokość, ramka, hover marki. */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        // to samo co przy `Krok`: zrzuty nie mają otwierać sekcji, które
        // użytkownik zastaje zamknięte (patrz scripts/zrzuty.mjs)
        data-rozwiniecie="szczegoly"
        className="font-display flex w-full items-center justify-center gap-2 rounded-(--radius-control) border border-hairline-strong bg-card px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-soft transition-colors hover:border-brand hover:text-brand"
      >
        {etykieta}
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
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  );
}
