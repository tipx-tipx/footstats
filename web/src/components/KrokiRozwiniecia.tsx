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

export type KrokKod = "skad" | "zmiana" | "ostatnio" | "przewaga";

export const KROK_TYTUL: Record<KrokKod, string> = {
  skad: "skąd ta liczba",
  zmiana: "co zmienia ten mecz",
  ostatnio: "jak było ostatnio",
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
  children,
}: {
  kod: KrokKod;
  /** nadpisanie tytułu, gdy karta nazywa ten krok trafniej */
  tytul?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-hairline py-4 first:border-t-0 first:pt-0 sm:grid sm:grid-cols-[7.5rem_minmax(0,1fr)] sm:gap-x-6">
      <h4 className="mb-1.5 text-[10px] font-semibold uppercase leading-relaxed tracking-[0.12em] text-faint sm:mb-0">
        {tytul ?? KROK_TYTUL[kod]}
      </h4>
      <div className="min-w-0">{children}</div>
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
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-faint transition-colors hover:text-ink"
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
