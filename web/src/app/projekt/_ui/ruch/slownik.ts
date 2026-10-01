/**
 * Etap 6 – słownik ruchu. Zamiast 16 sprężyn i 15 czasów z etapów 2–5:
 * TRZY czasy, TRZY krzywe, TRZY sprężyny – każde z jednym zastosowaniem.
 * Przy składaniu (etap 7) zatwierdzony charakter wchodzi do wszystkich
 * komponentów przez ten jeden plik.
 *
 * Zasady (z wytycznych): ruch tylko tam, gdzie zmienia się dana (kurs,
 * wynik, wybór, rozliczenie); nic nie wjeżdża przy przewijaniu; ograniczony
 * ruch = zmiana natychmiast, bez przesunięć.
 */

export type Charakter = "ok" | "a" | "b";

export type Slownik = {
  nazwa: string;
  czas: { szybki: number; zwykly: number; wolny: number };
  krzywa: { hamuje: [number, number, number, number]; rusza: [number, number, number, number]; rysuje: [number, number, number, number] };
  sprezyna: {
    /** znacznik wyboru (kreska menu, tło przełącznika) */
    znacznik: { type: "spring"; stiffness: number; damping: number };
    /** panel, arkusz, rozwinięcie */
    panel: { type: "spring"; stiffness: number; damping: number };
    /** mały element, który „wskakuje”: ✓, kropka, licznik */
    wyskok: { type: "spring"; stiffness: number; damping: number };
    /** radosny wyskok – TYLKO dolot do kuponu i ✓ trafionego typu (decyzja 01.10) */
    radosc: { type: "spring"; stiffness: number; damping: number };
  };
  /** rozwinięcia: A – płynny czas, B – sprężyna panelu */
  rozwiniecie: "czas" | "sprezyna";
  /** lot kropki do kuponu: czas i czy ląduje z odbiciem */
  lot: { czas: number; odbicie: boolean };
  /** liczba „przelicza się” od starej do nowej */
  licznik: number;
};

const PRECYZYJNY: Slownik = {
  nazwa: "Precyzyjny",
  czas: { szybki: 0.14, zwykly: 0.22, wolny: 0.4 },
  krzywa: { hamuje: [0.22, 1, 0.36, 1], rusza: [0.4, 0, 1, 1], rysuje: [0.65, 0, 0.35, 1] },
  sprezyna: {
    znacznik: { type: "spring", stiffness: 500, damping: 38 },
    panel: { type: "spring", stiffness: 380, damping: 36 },
    wyskok: { type: "spring", stiffness: 520, damping: 30 },
    radosc: { type: "spring", stiffness: 520, damping: 30 },
  },
  rozwiniecie: "czas",
  lot: { czas: 0.5, odbicie: false },
  licznik: 0.5,
};

/**
 * ZATWIERDZONY 01.10: Precyzyjny wszędzie, a odbicie ze Sprężystego tylko
 * w dwóch momentach, które cieszą – dolot do kuponu i ✓ trafionego typu.
 */
export const RUCH: Slownik = {
  ...PRECYZYJNY,
  nazwa: "Precyzyjny + radość",
  sprezyna: { ...PRECYZYJNY.sprezyna, radosc: { type: "spring", stiffness: 620, damping: 15 } },
  lot: { czas: 0.55, odbicie: true },
};

export const SLOWNIKI: Record<Charakter, Slownik> = {
  ok: RUCH,
  a: PRECYZYJNY,
  b: {
    nazwa: "Sprężysty",
    czas: { szybki: 0.16, zwykly: 0.26, wolny: 0.5 },
    krzywa: { hamuje: [0.22, 1, 0.36, 1], rusza: [0.4, 0, 1, 1], rysuje: [0.65, 0, 0.35, 1] },
    sprezyna: {
      znacznik: { type: "spring", stiffness: 420, damping: 26 },
      panel: { type: "spring", stiffness: 300, damping: 24 },
      wyskok: { type: "spring", stiffness: 620, damping: 15 },
      radosc: { type: "spring", stiffness: 620, damping: 15 },
    },
    rozwiniecie: "sprezyna",
    lot: { czas: 0.62, odbicie: true },
    licznik: 0.8,
  },
};
