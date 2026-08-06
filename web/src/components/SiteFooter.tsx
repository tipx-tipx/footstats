import Link from "next/link";

import { Logo } from "./Logo";

/**
 * Stopka produktu. Renderowana WYŁĄCZNIE w app/(app)/layout.tsx – /login żyje
 * poza tą grupą tras (server component, bez "use client").
 *
 * PRZEBUDOWANA 2026-08-06. Poprzednia wersja była tablicą diagnostyczną:
 * „Dane: statshub (statystyki i historia) + Superbet (kursy)", „Meczów
 * w bazie: 163", „Aktualizacja: 6 sierpnia 12:13". To są nasze wewnętrzne
 * fakty — „statshub" jest nazwą API, nie marką, którą ktokolwiek zna, a „163"
 * nie odpowiada na żadne pytanie, jakie ma człowiek wchodzący na stronę.
 *
 * Stopka ma robić to, co robi w każdym dojrzałym produkcie: dawać drugą
 * nawigację, powiedzieć czym to jest w jednym zdaniu i załatwić sprawy
 * formalne (wiek, odpowiedzialna gra, brak gwarancji). Nic więcej.
 */

const PRODUKT: { href: string; label: string }[] = [
  { href: "/", label: "Zawodnicy" },
  { href: "/druzyny", label: "Drużyny" },
  { href: "/kupony", label: "Kupony" },
  { href: "/mecze", label: "Mecze" },
];

const ZAUFANIE: { href: string; label: string }[] = [
  { href: "/model", label: "Nasza skuteczność" },
  { href: "/jak-to-dziala", label: "Jak to działa" },
];

function Kolumna({
  tytul,
  linki,
}: {
  tytul: string;
  linki: { href: string; label: string }[];
}) {
  return (
    <div>
      <p className="font-display text-[10px] font-semibold uppercase tracking-wider text-faint">
        {tytul}
      </p>
      <ul className="mt-2.5 space-y-1.5">
        {linki.map((l) => (
          <li key={l.href}>
            <Link
              href={l.href}
              className="text-xs text-ink-soft transition-colors hover:text-brand"
            >
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SiteFooter({
  liga,
  sezon,
  aktualizacja,
}: {
  liga: string;
  sezon: string;
  /** „6 sierpnia, 12:13" — kiedy ostatnio sprawdzaliśmy kursy */
  aktualizacja: string;
}) {
  const rok = new Date().getFullYear();
  return (
    <footer className="border-t border-hairline bg-card">
      <div className="mx-auto max-w-6xl px-4 py-9 sm:px-6">
        <div className="flex flex-col gap-8 md:flex-row md:justify-between">
          <div className="max-w-xs">
            <Logo wysokosc={36} />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              Liczymy szanse na gole, rożne, kartki i statystyki piłkarzy,
              a potem pokazujemy, gdzie kurs bukmachera jest naszym zdaniem
              za wysoki. Ty wybierasz i obstawiasz tam, gdzie zwykle.
            </p>
            <p className="mt-3 text-[11px] leading-relaxed text-faint">
              {liga} {sezon} · kursy sprawdzone {aktualizacja}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-x-10 gap-y-7 sm:grid-cols-3 md:gap-x-14">
            <Kolumna tytul="Typy" linki={PRODUKT} />
            <Kolumna tytul="Sprawdź nas" linki={ZAUFANIE} />
            <div>
              <p className="font-display text-[10px] font-semibold uppercase tracking-wider text-faint">
                Zasady
              </p>
              {/* „Gramy dla rozrywki, nie na zarobek" zdjęte (06.08):
                  brzmiało jak zaprzeczenie sensu produktu, który ma pomagać
                  wygrywać. Zostaje to, co naprawdę trzeba powiedzieć —
                  wiek, legalność i to, że typ nie jest gwarancją. */}
              <ul className="mt-2.5 space-y-1.5 text-xs leading-relaxed text-ink-soft">
                <li>Tylko dla pełnoletnich (18+)</li>
                <li>Obstawiaj u legalnych bukmacherów</li>
                <li>Stawiaj tyle, ile możesz stracić</li>
              </ul>
            </div>
          </div>
        </div>

        {/* dolny pasek: prawne minimum, ta sama kreska co w całym produkcie */}
        <div className="mt-8 flex flex-col gap-2 border-t border-hairline pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[11px] text-faint">
            © {rok} FootStats. Wszystkie szanse to nasze wyliczenia, nie
            gwarancja wyniku – żaden typ nie jest pewny.
          </p>
          <p className="text-[11px] font-medium text-faint">
            Grasz? Rób to odpowiedzialnie.
          </p>
        </div>
      </div>
    </footer>
  );
}
