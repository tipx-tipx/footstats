import { przygotujFundamenty } from "../_dane/przygotuj";
import { Fundamenty, type KonfigWarsztatu, type StartFundamentow } from "../_ui/Fundamenty";

/*
 * Etap 1b – dopracowanie wyborów z 30.09: paleta B (Atrament / Papier),
 * font Barlow, herby prawdziwe. Pierwsza pozycja każdej listy to wersja
 * wyjściowa z etapu 1, żeby każda poprawka miała punkt odniesienia.
 */
const KONFIG: KonfigWarsztatu = {
  etap: "Etap 1b",
  podtytul: "dopracowanie palety B i Barlow",
  palety: {
    ciemny: [
      { id: "b", nazwa: "Wyjściowy", opis: "Atrament z etapu 1 – punkt odniesienia." },
      {
        id: "b1",
        nazwa: "B1 · Noc",
        opis: "mniej niebieskiego, bliżej Sofascore; atrament ledwie wyczuwalny, najspokojniejszy dla oczu.",
      },
      {
        id: "b2",
        nazwa: "B2 · Granat logo",
        opis: "karty dokładnie w kolorze atramentu z logo (#0f1d28); wyraźnie granatowo, najbardziej „nasze”.",
      },
      {
        id: "b3",
        nazwa: "B3 · Butelka",
        opis: "atrament z zielonym podbiciem – szkło butelki z logo; zieleń marki zlewa się z tłem w jedną całość.",
      },
    ],
    jasny: [
      { id: "b", nazwa: "Wyjściowy", opis: "Papier z etapu 1 – punkt odniesienia." },
      {
        id: "p1",
        nazwa: "P1 · Jaśniejszy",
        opis: "mniej żółci, papier bliżej bieli; ciepło zostaje, ale nie wygląda na stary.",
      },
      {
        id: "p2",
        nazwa: "P2 · Kontrast",
        opis: "białe karty na ciemniejszym papierze – warstwy widać od razu, bez cieni (jak u Superbetu).",
      },
      {
        id: "p3",
        nazwa: "P3 · Gazeta",
        opis: "neutralny papier gazetowy, ciemniejszy atrament, głębsza zieleń; najmniej ciepła.",
      },
    ],
  },
  fonty: [
    {
      id: "2a",
      nazwa: "Półwąski",
      opis: "nagłówki Barlow Semi Condensed (jak w etapie 1), tekst Barlow.",
    },
    {
      id: "2b",
      nazwa: "Wąski + wersaliki",
      opis: "nagłówki Barlow Condensed, tytuły stron wersalikami – jak tablica wyników na stadionie.",
    },
    {
      id: "2c",
      nazwa: "Pełny",
      opis: "nagłówki zwykłym Barlow – spokojniej i szerzej, mniej „sportowo”.",
    },
  ],
  przelacznikHerbow: false,
};

export default async function DopracowaniePage({
  searchParams,
}: {
  searchParams: Promise<StartFundamentow>;
}) {
  return <Fundamenty dane={przygotujFundamenty()} start={await searchParams} konfig={KONFIG} />;
}
