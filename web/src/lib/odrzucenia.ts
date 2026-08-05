/**
 * POWODY, DLA KTÓRYCH MODEL CZEGOŚ NIE WYSTAWIŁ — po polsku, w jednym miejscu.
 *
 * Mieszkało to w `app/(app)/mecze/[id]/page.tsx`, ale od 05.08 ten sam słownik
 * jest potrzebny w trzech miejscach (strona meczu, werdykt w TOP POKRYCIA,
 * sekcja na Drużynach). Trzy kopie tej listy rozjechałyby się przy pierwszym
 * nowym powodzie z pipeline'u — a rozjazd jest CICHY: brakujący klucz nie
 * rzuca błędem, tylko drukuje surową nazwę zmiennej w polskim zdaniu.
 *
 * Dokładnie tak wyszło 05.08: `wartosc_ujemna_przy_ostroznym`, `za_malo_minut`
 * i `kwarantanna_strony` (233 z 4126 odrzuceń) od zawsze wypisywały się jako
 * „wartosc ujemna przy ostroznym". Nikt tego nie widział, dopóki napis siedział
 * w zwiniętej sekcji na dole strony.
 */

import type { Odrzucenie } from "./types";

export const POWOD_LABEL: Record<string, string> = {
  tylko_w_puli: "Dostępne w generatorze kuponów",
  kwarantanna_rynku: "Rynek chwilowo wstrzymany (tracił pieniądze)",
  kwarantanna_strony: "Ta strona zakładu jest chwilowo wstrzymana (traciła)",
  kwarantanna_kategorii: "Ten powód wejścia na listę jest chwilowo wstrzymany",
  stare_dane: "Zawodnik dawno nie grał, czekamy na świeże mecze",
  za_stara_historia: "Dane o zawodniku są nieaktualne",
  brak_kursu: "Superbet nie kwotuje tego rynku",
  za_malo_zdarzen: "Model oczekuje za mało zdarzeń",
  za_malo_historii: "Za mało meczów w historii",
  za_malo_minut: "Zawodnik gra za mało minut, żeby to liczyć",
  krotka_historia: "Za krótka historia",
  chwiejna_predykcja: "Model sam nie jest pewny swojej liczby",
  rozjazd_z_rynkiem: "Model za daleko od kursu bukmachera",
  kurs_lub_szansa_poza_widelkami: "Kurs i szansa nie składają się w grywalny typ",
  // ten sam warunek rozbity na trzy (2026-07-27) – dla rynków drużynowych to
  // najczęstszy powód braku typu, a jedna etykieta nie mówiła, co konkretnie
  // zawiodło: cena bukmachera, nasza szansa czy sam rachunek opłacalności
  kurs_poza_widelkami: "Kurs poza widełkami, w jakich gramy",
  szansa_za_niska: "Szansa za niska jak na ten kurs",
  wartosc_ujemna: "Przy ostrożnym liczeniu to nie wychodzi na plus",
  wartosc_ujemna_przy_ostroznym: "Przy ostrożnym liczeniu wychodzi na minus",
  poza_skladem: "Zawodnika nie ma w składzie na ten mecz",
  za_pozno: "Za blisko pierwszego gwizdka, żeby wystawić typ",
  limit_meczu: "Z tego meczu mamy już tyle typów, ile publikujemy",
  // brama uzasadnień (2026-08-05) — patrz betting.PROG_POLKI_PEWNE
  bez_uzasadnienia:
    "Nie umiemy rozpisać, skąd ta liczba — przy niższej szansie tego nie wystawiamy",
};

/** Etykieta powodu; nieznany kod pokazujemy czytelnie, nie jako `nazwa_zmiennej`. */
export function etykietaPowodu(powod: string): string {
  return POWOD_LABEL[powod] ?? powod.replace(/_/g, " ");
}

/** Grupuj wpisy po powodzie, w kolejności z POWOD_LABEL (reszta na końcu). */
export function grupyOdrzucen(wpisy: Odrzucenie[]): [string, Odrzucenie[]][] {
  const m = new Map<string, Odrzucenie[]>();
  for (const w of wpisy) {
    const g = m.get(w.powod) ?? [];
    g.push(w);
    m.set(w.powod, g);
  }
  const kolejnosc = Object.keys(POWOD_LABEL);
  return [...m.entries()].sort(
    (a, b) =>
      ((kolejnosc.indexOf(a[0]) + 99) % 99) - ((kolejnosc.indexOf(b[0]) + 99) % 99),
  );
}
