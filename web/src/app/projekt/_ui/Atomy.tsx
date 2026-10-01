"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";

import "../atomy.css";

import type { DaneFundamentow } from "../_dane/przygotuj";
import { Filtry, PasekDni, ScenaHistorii, Zakladki } from "./atomy/historia-nawigacja";
import { ScenaKursu, ScenaSzansy } from "./atomy/kurs-szansa";
import { Sekcja, type WariantAtomu } from "./atomy/wspolne";
import { ScenaLadowania, ScenaPrzyciskow, ScenaRozliczenia, ScenaZmiany } from "./atomy/wyniki-ruch";

type Motyw = "ciemny" | "jasny";

/* Fundamenty zamknięte 30.09: ciemny = B1 „Noc”, jasny = P3 „Gazeta”, Barlow pełny. */
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };
const FONT = "2c";

const ATOMY: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "kurs",
    nr: "2.1",
    tytul: "Kafelek kursu",
    opis: "Najczęściej klikany element. Musi mówić: ile płaci, u kogo, czy jest w kuponie i czy kurs się ruszył.",
    warianty: [
      { id: "a", nazwa: "A · Tablica", opis: "logo bukmachera nad dużą liczbą, stała szerokość – kursy w kolumnie zawsze równe; najczytelniejszy na karcie." },
      { id: "b", nazwa: "B · Poziomy", opis: "logo z lewej, liczba z prawej, jak kafelek u bukmachera; niski, dobrze siedzi w wierszu." },
      { id: "c", nazwa: "C · Pigułka", opis: "znak bukmachera (litera na jego kolorze) + liczba; najmniejszy – do gęstych list i kuponu." },
    ],
  },
  {
    klucz: "szansa",
    nr: "2.2",
    tytul: "Szansa",
    opis: "Nasza główna liczba (jak w Polymarket). Pytanie: sama liczba czy liczba z kontekstem.",
    warianty: [
      { id: "a", nazwa: "A · Liczba i słowo", opis: "duża liczba i poziom słownie („wysoka szansa”); najprostsze, zero nauki." },
      { id: "b", nazwa: "B · Tor ceny", opis: "pasek naszej szansy i znacznik tego, co zakłada kurs bukmachera; od razu widać różnicę zdań. Uwaga: pokazuje też typy, gdzie bukmacher ocenia wyżej niż my." },
      { id: "c", nazwa: "C · Kreski", opis: "10 kresek jak „7 na 10” – ten sam język co historia meczów; intuicyjne dla laika." },
    ],
  },
  {
    klucz: "historia",
    nr: "2.3",
    tytul: "Historia vs linia",
    opis: "Ostatnie mecze zawodnika na tle linii bukmachera – nasz znak rozpoznawczy.",
    warianty: [
      { id: "a", nazwa: "A · Kropki", opis: "kropki połączone linią – dokładnie znak z logo; pełna kropka = ponad linią." },
      { id: "b", nazwa: "B · Słupki", opis: "słupek na mecz, zielony gdy ponad linią; najłatwiej porównać wysokości." },
      { id: "c", nazwa: "C · Kratki", opis: "liczba w kratce, zielona gdy weszło; najmniej miejsca – mieści się w wierszu listy." },
    ],
  },
  {
    klucz: "dni",
    nr: "2.4",
    tytul: "Pasek dni",
    opis: "Wybór dnia nad każdą listą. Na telefonie przewijany palcem.",
    warianty: [
      { id: "a", nazwa: "A · Chipy", opis: "„Jutro 19”, „Pt 2.10 17” – zwarte, dużo dni w jednym rzędzie." },
      { id: "b", nazwa: "B · Kalendarz", opis: "dzień tygodnia, duży numer dnia, liczba meczów – jak kalendarz w aplikacji bukmachera." },
      { id: "c", nazwa: "C · Zakładki", opis: "sam tekst z przesuwającym się podkreśleniem; najlżejsze wizualnie." },
    ],
  },
  {
    klucz: "filtry",
    nr: "2.5",
    tytul: "Filtry i sortowanie",
    opis: "Dziś filtry zajmują pół ekranu. Cel: zawsze pod ręką, nigdy w drodze.",
    warianty: [
      { id: "a", nazwa: "A · Chipy rynków", opis: "rynki z licznikami w jednym przewijanym rzędzie; jedno dotknięcie = filtr." },
      { id: "b", nazwa: "B · Przycisk i panel", opis: "jeden przycisk „Filtry”, reszta w panelu (na telefonie z dołu ekranu); najczystsza lista." },
      { id: "c", nazwa: "C · Sortowanie + chipy", opis: "przełącznik sortowania na górze, rynki pod nim; wszystko widoczne od razu." },
    ],
  },
  {
    klucz: "zakladki",
    nr: "2.6",
    tytul: "Zakładki sekcji",
    opis: "Przełączanie między Wysokimi szansami, Wyższymi kursami i Drabinkami.",
    warianty: [
      { id: "a", nazwa: "A · Podkreślenie", opis: "tekst z przesuwającą się kreską; klasyka, nie zabiera miejsca." },
      { id: "b", nazwa: "B · Segment", opis: "przesuwające się tło pod wybraną opcją; wyraźnie „przełącznik”." },
      { id: "c", nazwa: "C · Karty", opis: "każda zakładka z liczbą i jednym zdaniem, czym się różni; najlepsze dla nowego klienta." },
    ],
  },
  {
    klucz: "wynik",
    nr: "2.7",
    tytul: "Stany rozliczenia",
    opis: "Weszło / nie weszło / zwrot / czeka – w Skuteczności, kuponach i na kartach po meczu.",
    warianty: [
      { id: "a", nazwa: "A · Etykieta", opis: "kolorowa etykieta z ikoną i słowem; wszędzie ta sama." },
      { id: "b", nazwa: "B · Pasek i przygaszenie", opis: "kolorowy pasek z boku, przegrany typ przygasa jak przegrana drużyna w Sofascore." },
      { id: "c", nazwa: "C · Wynik liczbowo", opis: "ile faktycznie było (3 / linia 0,5) i kółko z ikoną; od razu widać, o ile weszło lub zabrakło." },
    ],
  },
  {
    klucz: "zmiana",
    nr: "2.8",
    tytul: "Zmiana liczby",
    opis: "Co się dzieje, gdy kurs lub szansa zmienia się po przeliczeniu. Kliknij „Symuluj przeliczenie”.",
    warianty: [
      { id: "a", nazwa: "A · Licznik", opis: "cyfry przewijają się jak w liczniku; efekt „wow”, ale spokojny." },
      { id: "b", nazwa: "B · Błysk", opis: "nowa liczba wjeżdża, tło błyska na zielono/czerwono, strzałka kierunku – jak w Sofascore." },
      { id: "c", nazwa: "C · Odliczanie", opis: "liczba płynnie dolicza do nowej wartości; najdelikatniejsze." },
    ],
  },
  {
    klucz: "ladowanie",
    nr: "2.9",
    tytul: "Ładowanie",
    opis: "Co widać, zanim dane dojdą – i gdy się odświeżają.",
    warianty: [
      { id: "a", nazwa: "A · Szkielet z połyskiem", opis: "zarys karty z przesuwającym się połyskiem." },
      { id: "b", nazwa: "B · Szkielet pulsujący", opis: "zarys karty, który spokojnie pulsuje." },
      { id: "c", nazwa: "C · Stare dane + kreska", opis: "zostają poprzednie dane, lekko przygaszone, a u góry biegnie cienka kreska; nic nie skacze." },
    ],
  },
  {
    klucz: "przyciski",
    nr: "2.10",
    tytul: "Przyciski i pusty stan",
    opis: "Jeden zestaw (bez wariantów) – do akceptacji lub uwag.",
    warianty: [{ id: "a", nazwa: "Zestaw", opis: "główny (jedna najważniejsza akcja na ekranie), drugi, cichy i ikonowy; 48 px na telefon." }],
  },
];

export type StartAtomow = Record<string, string | undefined>;

export function Atomy({ dane, start }: { dane: DaneFundamentow; start: StartAtomow }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [szer, setSzer] = useState<"pelna" | "telefon">(start.s === "telefon" ? "telefon" : "pelna");
  const [wybory, setWybory] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      ATOMY.map((a) => [a.klucz, a.warianty.some((w) => w.id === start[a.klucz]) ? start[a.klucz]! : a.warianty[0].id]),
    ),
  );

  useEffect(() => {
    const q = new URLSearchParams({ m: motyw, s: szer, ...wybory });
    window.history.replaceState(null, "", `?${q}`);
  }, [motyw, szer, wybory]);

  const typy = dane.typy;
  const scena = (klucz: string, w: string) => {
    switch (klucz) {
      case "kurs":
        return <ScenaKursu wariant={w} typy={typy} />;
      case "szansa":
        return <ScenaSzansy wariant={w} typy={typy} />;
      case "historia":
        return <ScenaHistorii wariant={w} typy={typy} />;
      case "dni":
        return (
          <div className="a-scena">
            <PasekDni wariant={w} dni={dane.dni} />
          </div>
        );
      case "filtry":
        return (
          <div className="a-scena">
            <Filtry wariant={w} rynki={dane.rynki} wszystkich={dane.wszystkichTypow} />
          </div>
        );
      case "zakladki":
        return (
          <div className="a-scena">
            <Zakladki wariant={w} />
          </div>
        );
      case "wynik":
        return <ScenaRozliczenia wariant={w} typy={typy} />;
      case "zmiana":
        return <ScenaZmiany wariant={w} />;
      case "ladowanie":
        return <ScenaLadowania wariant={w} typ={typy[0]} />;
      default:
        return <ScenaPrzyciskow />;
    }
  };

  const ekran = (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font={FONT}>
      <div className="p-tresc" style={{ maxWidth: 880 }}>
        {ATOMY.map((a) => (
          <Sekcja
            key={a.klucz}
            nr={a.nr}
            tytul={a.tytul}
            opis={a.opis}
            warianty={a.warianty}
            wybrany={wybory[a.klucz]}
            zmien={(id) => setWybory((w) => ({ ...w, [a.klucz]: id }))}
          >
            {/* klucz z wariantem: zmiana wariantu montuje scenę od nowa,
                więc animacje wejścia widać przy każdym przełączeniu */}
            <div key={wybory[a.klucz]}>{scena(a.klucz, wybory[a.klucz])}</div>
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
            Etap 2 <span>· atomy – ciemny „Noc”, jasny „Gazeta”, Barlow</span>
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
            {ATOMY.map((a) => (
              <a key={a.klucz} href={`#atom-${a.nr}`} style={{ color: "#aeb4b6", fontSize: 12 }}>
                {a.nr}
              </a>
            ))}
          </div>
        </div>
        <div className="p-pulpit-opis">
          Wybór w każdej sekcji zapisuje się w adresie strony – wystarczy przesłać link.
        </div>
      </div>
      {szer === "telefon" ? <div className="p-rama-telefon">{ekran}</div> : ekran}
    </MotionConfig>
  );
}
