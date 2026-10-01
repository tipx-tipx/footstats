import { przygotujFundamenty } from "../_dane/przygotuj";
import { Fundamenty, type KonfigWarsztatu, type StartFundamentow } from "../_ui/Fundamenty";

/* Etap 1 w pierwotnej postaci – zostaje jako punkt odniesienia dla dopracowań. */
const KONFIG: KonfigWarsztatu = {
  etap: "Etap 1",
  podtytul: "fundamenty",
  palety: {
    ciemny: [
      {
        id: "a",
        nazwa: "A · Grafit",
        opis: "neutralny grafit jak w Sofascore; przyciski w kolorze kredy z linii boiska, zieleń tylko dla marki i „weszło”.",
      },
      {
        id: "b",
        nazwa: "B · Atrament",
        opis: "tło z atramentu logo (niebieskawy grafit); przyciski i akcenty w butelkowej zieleni marki.",
      },
    ],
    jasny: [
      {
        id: "a",
        nazwa: "A · Biel",
        opis: "chłodna biel jak jasny Sofascore; sterowanie w atramencie logo, zieleń tylko dla marki i wyników.",
      },
      {
        id: "b",
        nazwa: "B · Papier",
        opis: "ciepły papier programu meczowego; atrament logo i przyciski w butelkowej zieleni.",
      },
    ],
  },
  fonty: [
    {
      id: "1",
      nazwa: "1 · Archivo",
      opis: "jedna rodzina z osią szerokości: nagłówki rozciągnięte jak litery logo, tekst w zwykłej szerokości.",
    },
    {
      id: "2",
      nazwa: "2 · Barlow",
      opis: "krój z rodu DIN – tablice i oznakowanie stadionów; nagłówki półwąskie, dużo treści na ekranie.",
    },
    {
      id: "3",
      nazwa: "3 · Schibsted",
      opis: "krój skandynawskiej prasy; ciężkie, ciasne nagłówki jak w dzienniku sportowym.",
    },
  ],
  przelacznikHerbow: true,
};

export default async function FundamentyPage({
  searchParams,
}: {
  searchParams: Promise<StartFundamentow>;
}) {
  return <Fundamenty dane={przygotujFundamenty()} start={await searchParams} konfig={KONFIG} />;
}
