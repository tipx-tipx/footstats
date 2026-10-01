"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";

import "../atomy.css";
import "../atomy2.css";
import "../elementy.css";

import type { DaneElementow } from "../_dane/elementy";
import { Sekcja, type WariantAtomu } from "./atomy/wspolne";
import { ScenaDrabinki } from "./elementy/drabinka";
import { ScenaKarty } from "./elementy/karta";
import { ScenaKoszyka, ScenaKuponu } from "./elementy/kupon";
import { ScenaMeczu } from "./elementy/mecz";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

const ELEMENTY: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "mecz",
    nr: "3.1",
    tytul: "Wiersz meczu",
    opis: "Lista meczów z typami. Pytanie gracza: „w które mecze warto wejść?”.",
    warianty: [
      { id: "a", nazwa: "A · Lista", opis: "jak w Sofascore: godzina, dwie drużyny z herbami, z prawej najwyższa szansa i liczba typów. Najgęściej, najszybciej się przegląda." },
      { id: "b", nazwa: "B · Z typem na wierzchu", opis: "pod meczem od razu najmocniejszy typ z kursem do kliknięcia. Wiersz sam „sprzedaje” mecz, można dodać do kuponu bez wchodzenia." },
      { id: "c", nazwa: "C · Kafle", opis: "duże herby, godzina, liczba typów i mini-słupki szans. Najbardziej wizualne, dobre jako przegląd dnia." },
    ],
  },
  {
    klucz: "karta",
    nr: "3.2",
    tytul: "Karta typu",
    opis: "Jedna rodzina dla zawodników i drużyn (zamiast dzisiejszych 7 rodzajów kart). Powody przepisane po ludzku – to próbka nowych tekstów.",
    warianty: [
      { id: "a", nazwa: "A · Wiersz rozwijany", opis: "na liście sam wiersz (kto, zakład, szansa, kurs); kliknięcie rozwija historię i powody. Najgęściej – pierwsza karta jest otwarta." },
      { id: "b", nazwa: "B · Karta pełna", opis: "wszystko ważne od razu: duża szansa, kurs, kratki i jeden główny powód; reszta pod „Skąd ta liczba”." },
      { id: "c", nazwa: "C · Powody na wierzchu", opis: "karta najpierw mówi DLACZEGO (lista „za”), a „przeciw” jest pod przyciskiem. Najbardziej sprzedażowa." },
    ],
  },
  {
    klucz: "drabinka",
    nr: "3.3",
    tytul: "Drabinka",
    opis: "Jeden zawodnik, kilka linii. We wszystkich wariantach wybór linii przebarwia kratki historii – widać, w ilu meczach ta linia by weszła.",
    warianty: [
      { id: "a", nazwa: "A · Suwak linii", opis: "jak w Polymarket: przystanki z linią, kursem i trafieniami, znacznik przesuwa się sprężyście; strzałki na klawiaturze." },
      { id: "b", nazwa: "B · Schody", opis: "każda linia to stopień – im wyżej, tym więcej płaci; wypełnienie pokazuje, jak często wchodziła." },
      { id: "c", nazwa: "C · Tabela szczebli", opis: "wiersz na linię: trafienia, szansa, kurs do kliknięcia. Najgęściej, najlepiej na telefon." },
    ],
  },
  {
    klucz: "kupon",
    nr: "3.4",
    tytul: "Kupon gotowy",
    opis: "Kupony, które składa model. Przycisk pod spodem pokazuje stan w trakcie (część nóg rozliczona).",
    warianty: [
      { id: "a", nazwa: "A · Bilet", opis: "kurs łączny na górze, perforacja, nogi z kursem i godziną, „najsłabsze ogniwo”, wypłata z 10 zł." },
      { id: "b", nazwa: "B · Oś meczów", opis: "nogi ułożone na osi czasu – widać, kiedy gra każda część kuponu; w trakcie kropki się zapełniają." },
      { id: "c", nazwa: "C · Kompakt", opis: "najmniejszy: kurs, liczba typów, szansa i nogi w liniach – do list wielu kuponów." },
    ],
  },
  {
    klucz: "koszyk",
    nr: "3.5",
    tytul: "Twój kupon",
    opis: "Kupon składany kliknięciami w kursy. Jedna propozycja do oceny.",
    warianty: [
      {
        id: "a",
        nazwa: "Propozycja",
        opis: "komputer: panel z boku, który jedzie za przewijaniem; telefon: pastylka przyklejona do dołu (liczba typów, kurs, wygrana), po dotknięciu arkusz. Kurs łączny błyska przy zmianie, szybkie kwoty 10/20/50/100 zł.",
      },
    ],
  },
];

export type StartElementow = Record<string, string | undefined>;

export function Elementy({ dane, start }: { dane: DaneElementow; start: StartElementow }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [szer, setSzer] = useState<"pelna" | "telefon">(start.s === "telefon" ? "telefon" : "pelna");
  const [wybory, setWybory] = useState<Record<string, string>>(() =>
    Object.fromEntries(ELEMENTY.map((e) => [e.klucz, e.warianty.some((w) => w.id === start[e.klucz]) ? start[e.klucz]! : e.warianty[0].id])),
  );

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, s: szer, ...wybory })}`);
  }, [motyw, szer, wybory]);

  const telefon = szer === "telefon";
  const scena = (klucz: string, w: string) => {
    switch (klucz) {
      case "mecz":
        return <ScenaMeczu wariant={w} mecze={dane.meczeE} />;
      case "karta":
        return <ScenaKarty wariant={w} karty={dane.karty} />;
      case "drabinka":
        return <ScenaDrabinki wariant={w} d={dane.drabinka} />;
      case "kupon":
        return <ScenaKuponu wariant={w} kupony={dane.kupony} />;
      default:
        return <ScenaKoszyka typy={dane.wszystkie} telefon={telefon} />;
    }
  };

  const ekran = (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
      <div className="p-tresc" style={{ maxWidth: 920 }}>
        {ELEMENTY.map((e) => (
          <Sekcja
            key={e.klucz}
            nr={e.nr}
            tytul={e.tytul}
            opis={e.opis}
            warianty={e.warianty}
            wybrany={wybory[e.klucz]}
            zmien={(id) => setWybory((x) => ({ ...x, [e.klucz]: id }))}
          >
            <div key={wybory[e.klucz]}>{scena(e.klucz, wybory[e.klucz])}</div>
          </Sekcja>
        ))}
      </div>
    </div>
  );

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 3 <span>· główne elementy</span>
          </div>
          <div className="p-wybor">
            <span>motyw</span>
            <div className="p-segmenty" role="group">
              {(["ciemny", "jasny"] as const).map((m) => (
                <button key={m} type="button" aria-pressed={motyw === m} onClick={() => setMotyw(m)}>
                  {m === "ciemny" ? "Ciemny" : "Jasny"}
                </button>
              ))}
            </div>
          </div>
          <div className="p-wybor">
            <span>ekran</span>
            <div className="p-segmenty" role="group">
              {(["pelna", "telefon"] as const).map((x) => (
                <button key={x} type="button" aria-pressed={szer === x} onClick={() => setSzer(x)}>
                  {x === "pelna" ? "Komputer" : "Telefon"}
                </button>
              ))}
            </div>
          </div>
          <div className="p-wybor" style={{ flexWrap: "wrap" }}>
            <span>skocz do</span>
            {ELEMENTY.map((e) => (
              <a key={e.klucz} href={`#atom-${e.nr}`} style={{ color: "#aeb4b6", fontSize: 12 }}>
                {e.nr}
              </a>
            ))}
          </div>
        </div>
        <div className="p-pulpit-opis">Wybór w każdej sekcji zapisuje się w adresie strony – wystarczy przesłać link.</div>
      </div>
      {telefon ? <div className="p-rama-telefon">{ekran}</div> : ekran}
    </MotionConfig>
  );
}
