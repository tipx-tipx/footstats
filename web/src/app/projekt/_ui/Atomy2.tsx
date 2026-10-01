"use client";

import { MotionConfig } from "framer-motion";
import { useEffect, useState, type ReactNode } from "react";

import "../atomy.css";
import "../atomy2.css";

import type { DaneFundamentow } from "../_dane/przygotuj";
import { PasekDni, ScenaHistorii, Zakladki } from "./atomy/historia-nawigacja";
import { ScenaKursu, ScenaSzansy } from "./atomy/kurs-szansa";
import { ScenaLadowania, ScenaPrzyciskow, ScenaRozliczenia, ScenaZmiany } from "./atomy/wyniki-ruch";
import { DniD, KafelekD, KratkiD, LegendaKratek, SzansaD } from "./atomy2/podstawowe";
import { PrzyciskiD, SzkieletD } from "./atomy2/reszta";
import { FiltryWKontekscie } from "./atomy2/filtry2";
import { FiltryV3 } from "./atomy2/filtry3";
import { BlyskD, KartyD, RozliczenieD } from "./atomy2/zlozone";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

type Pozycja = {
  nr: string;
  tytul: string;
  wybor: string;
  /** podpisy przełącznika porównania (domyślnie Dopracowane / Pierwsza wersja) */
  etykiety?: [string, string];
  poprawki: ReactNode[];
  uwaga?: ReactNode;
};

const POZYCJE: Pozycja[] = [
  {
    nr: "2.1",
    tytul: "Kafelek kursu",
    wybor: "B · Poziomy",
    poprawki: [
      <><b>Logo jednokolorowe</b> (w kolorze tekstu) – 20 czerwonych logotypów na liście to był szum; kolor zostaje dla znaczenia. Oryginał w kolorze do porównania przełącznikiem.</>,
      <><b>Wybrany = pełne wypełnienie</b> zieleną akcji z ptaszkiem w środku, jak kurs w kuponie u bukmachera – bez plakietki wystającej poza kafelek.</>,
      <><b>Liczby w kolumnie</b>: cyfry równej szerokości, wyrównanie do prawej, stała szerokość – kursy pod sobą się nie „tańczą”.</>,
      <><b>Brak kursu</b> to nie martwy „–”, tylko informacja „od 1,31” – od jakiego kursu typ ma sens (ramka przerywana, nieklikalny).</>,
      <><b>Dotyk</b>: 40 px na komputerze, 44 px na telefonie; wciśnięcie lekko zmniejsza kafelek; obwódka fokusu z klawiatury.</>,
      <><b>Zmiana kursu</b> od razu z błyskiem z 2.8 (zielony wzrost, czerwony spadek) i strzałką przy liczbie.</>,
    ],
  },
  {
    nr: "2.2",
    tytul: "Szansa",
    wybor: "A · Liczba i słowo",
    poprawki: [
      <><b>Znak % mniejszy i jaśniejszy</b> – liczba czyta się pierwsza, jak w statystykach sportowych.</>,
      <><b>Słowo w kolorze znaczenia</b>: bardzo wysoka = zieleń marki, wysoka = tekst, umiarkowana = przygaszony, niska = bursztyn.</>,
      <><b>Znak zapytania z wyjaśnieniem</b> („na 100 takich typów wchodzi około 73” + progi poziomów) – laik rozumie liczbę bez szukania.</>,
      <><b>Wersja mała do wierszy</b> bez słowa – sama liczba, wyrównana do prawej.</>,
    ],
  },
  {
    nr: "2.3",
    tytul: "Historia (kratki)",
    wybor: "C · Kratki",
    poprawki: [
      <><b>Minuty z danych</b>: mecz, w którym grał mniej niż 45 min, ma kratkę kreskowaną – „0” po 12 minutach to co innego niż „0” po 90.</>,
      <><b>Nie zagrał = osobny znak „NZ”</b> (kratka przekreślona po skosie) – decyzja 30.09; na karcie poza wynikiem („8/9 · 1× nie zagrał”), model bez zmian. Przykład: ostatni zawodnik w tej sekcji.</>,
      <><b>Wynik na górze dużo</b> („8/10 ponad 0,5”) + <b>ostatnie 5</b> osobno – forma teraz vs dłużej.</>,
      <><b>Od najnowszego do najstarszego</b> (decyzja 30.09): pierwsza kratka z lewej to ostatni mecz, z kreską pod spodem; „ostatnie 5” liczone od lewej.</>,
      <><b>Dymek na najechanie i dotknięcie</b>: rywal, data, minuty, czy mecz reprezentacji.</>,
    ],
  },
  {
    nr: "2.4",
    tytul: "Pasek dni",
    wybor: "A · Chipy",
    poprawki: [
      <><b>Tło wybranego dnia przesuwa się</b> płynnie między chipami (ten sam ruch co w zakładkach i sortowaniu).</>,
      <><b>Wygaszona prawa krawędź</b> mówi „przewiń, jest więcej” – bez strzałek; przyciąganie do chipa przy przewijaniu palcem.</>,
      <><b>Strzałki na klawiaturze</b> zmieniają dzień, wybrany dzień sam wjeżdża w pole widzenia.</>,
      <><b>Dzień bez meczów</b> wyszarzony i nieklikalny; obszar dotyku 44 px przy wyglądzie 36 px.</>,
    ],
  },
  {
    nr: "2.5",
    tytul: "Filtry",
    wybor: "B · Przycisk i panel – wersja 3 (po pytaniu „czy czegoś nie brakuje”)",
    etykiety: ["Wersja 3", "Wersja 2"],
    poprawki: [
      <><b>Punkt wyjścia: cztery pytania gracza.</b> „Mam konkretny mecz / zawodnika” → szukaj. „Lubię ten rynek” → rząd rynków. „Co mogę zagrać teraz / czy składy pewne” → przełączniki. „Tylko wysoka szansa, kurs, moje ligi” → panel. Każde pytanie ma jedno miejsce.</>,
      <><b>Szukaj (brakowało):</b> zawodnik, drużyna, mecz, rozgrywki – bez polskich znaków też znajdzie („zivkovic”). Podpowiedzi w grupach z liczbą typów, strzałki + Enter, na komputerze klawisz „/”. Na telefonie lupa, która rozwija pole na cały rząd.</>,
      <><b>Rynki na widoku</b>, jak u Superbetu: jeden rząd tekstowych zakładek z licznikami, pojedynczy wybór (prościej niż zaznaczanie kilku). Rynek zniknął z panelu – jedno miejsce.</>,
      <><b>Panel tylko na rzadsze rzeczy:</b> szansa, kurs, rozgrywki z flagami. Licznik na przycisku liczy tylko to, co jest w panelu.</>,
      <><b>Mądry pusty wynik:</b> zamiast „brak wyników” – „Bez „Wkrótce” byłoby 12 typów” i przycisk, który zdejmuje dokładnie ten jeden filtr.</>,
      <><b>Cztery rodziny kontrolek, każda wygląda inaczej:</b> pole szukania, okrągłe przełączniki, kwadratowe menu, tekstowe zakładki rynków – nic się ze sobą nie myli.</>,
      <>Przy składaniu strony: filtry zapamiętają się po powrocie i trafią do adresu (można wysłać komuś link do tego samego widoku).</>,
    ],
  },
  {
    nr: "2.6",
    tytul: "Zakładki sekcji",
    wybor: "C · Karty – pierwsza wersja (decyzja 30.09)",
    etykiety: ["Wybrana", "Odrzucona wersja z liczbami"],
    poprawki: [
      <>Zostaje pierwsza wersja kart. Jedyna zmiana: <b>prawdziwe liczby z danych</b> zamiast przykładowych – widać ją w sekcji 2.5 nad filtrami.</>,
    ],
  },
  {
    nr: "2.7",
    tytul: "Rozliczenie",
    wybor: "B · Pasek i przygaszenie",
    poprawki: [
      <><b>„Było 3” pod etykietą</b> – faktyczny wynik z wariantu C bez zabierania miejsca.</>,
      <><b>Czeka = pasek przerywany</b> i godzina startu; zwrot = szary z powodem („nie zagrał”).</>,
      <><b>Podsumowanie dnia</b> nad listą: „2 z 3 weszło” i mini-pasek z kolorami wszystkich typów.</>,
      <><b>Animacja rozliczenia</b>: pasek wyrasta, etykieta zmienia się sprężyście, podsumowanie przelicza się samo – kliknij „Rozlicz ostatni mecz”.</>,
    ],
  },
  {
    nr: "2.8",
    tytul: "Zmiana liczby",
    wybor: "B · Błysk",
    poprawki: [
      <><b>Błysk na całym kafelku kursu</b> (obwódka i tło gasną w 1,6 s) + strzałka, która zostaje przy liczbie.</>,
      <><b>Szansa zmienia się tym samym ruchem</b> – jeden język animacji dla wszystkich liczb.</>,
      <>Przy ograniczeniu ruchu w systemie zostaje sama zmiana koloru, bez przesuwania.</>,
    ],
    uwaga: (
      <>
        Ważne: dane przeliczają się co godzinę, więc „na żywo” błysk zobaczy tylko ktoś z otwartą stroną. Żeby strzałka mówiła „kurs
        wzrósł od Twojej ostatniej wizyty / od publikacji”, pipeline musi zapisywać poprzedni kurs – dziś go nie ma w danych strony.
      </>
    ),
  },
  {
    nr: "2.9",
    tytul: "Ładowanie",
    wybor: "A · Szkielet z połyskiem",
    poprawki: [
      <><b>Szkielet ma dokładnie kształt wiersza</b> (nazwisko, rynek, kafelek, kratki) – po doczytaniu nic nie przeskakuje.</>,
      <><b>Jedna fala połysku</b> dla wszystkich szkieletów naraz, zamiast każdy migający osobno.</>,
      <><b>300 ms opóźnienia</b> – szybkie wczytanie nie mignie szarymi paskami.</>,
      <>Odświeżanie w tle (dane już są) nie pokazuje szkieletu – zostają stare dane, bez skakania.</>,
    ],
  },
  {
    nr: "2.10",
    tytul: "Przyciski i pusty stan",
    wybor: "Zestaw",
    poprawki: [
      <><b>Obwódka fokusu</b> z klawiatury, <b>stan wyłączony</b>, <b>stan „zapisuję”</b> z kręciołkiem bez zmiany szerokości przycisku.</>,
      <><b>Przycisk z treścią</b>: „Dodaj do kuponu · 3 typy · ×2,11” – dopisek lżejszy.</>,
      <><b>Cichy przycisk</b>: strzałka lekko przesuwa się przy najechaniu; ikonowy 44 px na telefonie.</>,
      <><b>Pusty stan bez przerywanej ramki</b> (to częsty szablon): zdanie, powód, jedna konkretna akcja.</>,
    ],
  },
];

export type StartAtomow2 = Record<string, string | undefined>;

export function Atomy2({ dane, start }: { dane: DaneFundamentow; start: StartAtomow2 }) {
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [szer, setSzer] = useState<"pelna" | "telefon">(start.s === "telefon" ? "telefon" : "pelna");
  const [przed, setPrzed] = useState<Record<string, boolean>>({});
  const [logoKolor, setLogoKolor] = useState(false);
  const [wybrane, setWybrane] = useState<Set<number>>(new Set([dane.typy[0]?.id]));

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, s: szer })}`);
  }, [motyw, szer]);

  const typy = dane.typy;
  const telefon = szer === "telefon";

  const dopracowane = (nr: string): ReactNode => {
    switch (nr) {
      case "2.1":
        return (
          <>
            <div className="d-porownanie" role="group" aria-label="Logo">
              <button type="button" aria-pressed={!logoKolor} onClick={() => setLogoKolor(false)}>
                logo jednokolorowe
              </button>
              <button type="button" aria-pressed={logoKolor} onClick={() => setLogoKolor(true)}>
                logo w kolorze
              </button>
            </div>
            <div className="a-scena">
              <div className="a-podpis">w wierszu – kliknij kurs</div>
              {typy.map((t) => (
                <div key={t.id} className="a-typ">
                  <div style={{ minWidth: 0 }}>
                    <div className="a-typ-kto">{t.kto}</div>
                    <div className="a-typ-co">
                      {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {String(t.linia).replace(".", ",")}
                    </div>
                  </div>
                  <KafelekD
                    k={{ kurs: t.kurs, bukmacher: t.bukmacher }}
                    wybrany={wybrane.has(t.id)}
                    logoKolor={logoKolor}
                    onClick={() =>
                      setWybrane((w) => {
                        const n = new Set(w);
                        if (n.has(t.id)) n.delete(t.id);
                        else n.add(t.id);
                        return n;
                      })
                    }
                  />
                </div>
              ))}
            </div>
            <div className="a-scena">
              <div className="a-podpis">wszystkie stany</div>
              <div className="a-rzad" style={{ alignItems: "flex-start" }}>
                {(
                  [
                    ["zwykły", { kurs: typy[0].kurs, bukmacher: "Superbet" }, false],
                    ["w kuponie", { kurs: typy[0].kurs, bukmacher: "Superbet" }, true],
                    ["Betclic płaci więcej", { kurs: typy[0].kurs + 0.06, bukmacher: "Betclic" }, false],
                    ["kurs wzrósł", { kurs: typy[0].kurs + 0.04, bukmacher: "Superbet", zmiana: "gora" }, false],
                    ["kurs spadł", { kurs: typy[0].kurs - 0.05, bukmacher: "Superbet", zmiana: "dol" }, false],
                    ["brak kursu", { kurs: null, bukmacher: "Superbet", uczciwy: typy[0].kursUczciwy }, false],
                  ] as const
                ).map(([opis, k, w]) => (
                  <div key={opis} style={{ display: "grid", gap: 8, justifyItems: "start" }}>
                    <KafelekD k={k} wybrany={w} logoKolor={logoKolor} />
                    <span className="p-t3" style={{ fontSize: 11 }}>
                      {opis}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        );
      case "2.2":
        return (
          <>
            <div className="a-scena">
              <div className="a-podpis">duża – na karcie (najedź lub kliknij „?”)</div>
              <div className="a-rzad" style={{ gap: 44, alignItems: "flex-start" }}>
                {[...typy.map((t) => t.szansa), 0.78, 0.55].map((p, i) => (
                  <SzansaD key={i} p={p} />
                ))}
              </div>
            </div>
            <div className="a-scena">
              <div className="a-podpis">mała – w wierszu</div>
              {typy.map((t) => (
                <div key={t.id} className="a-typ">
                  <div>
                    <div className="a-typ-kto">{t.kto}</div>
                    <div className="a-typ-co">{t.rynek.toLowerCase()}</div>
                  </div>
                  <SzansaD p={t.szansa} mala />
                </div>
              ))}
            </div>
          </>
        );
      case "2.3":
        return (
          <div className="a-scena" style={{ display: "grid", gap: 26 }}>
            {[...typy, ...(dane.przykladNZ ? [dane.przykladNZ] : [])].map((t) => (
              <div key={t.id} style={{ maxWidth: 440 }}>
                <div className="a-typ-kto">{t.kto}</div>
                <div className="a-typ-co" style={{ marginBottom: 10 }}>
                  {t.rynek.toLowerCase()} {t.strona === "ponizej" ? "poniżej" : "powyżej"} {String(t.linia).replace(".", ",")}
                </div>
                <KratkiD t={t} />
              </div>
            ))}
            <LegendaKratek />
          </div>
        );
      case "2.4":
        return (
          <div className="a-scena">
            <DniD dni={dane.dni} />
          </div>
        );
      case "2.5":
        return (
          <div className="a-scena">
            <FiltryV3 wszystkie={dane.wszystkie} ligi={dane.ligiTypow} drabinki={dane.drabinki} telefon={telefon} />
          </div>
        );
      case "2.6":
        return (
          <div className="a-scena">
            <Zakladki wariant="c" />
          </div>
        );
      case "2.7":
        return <RozliczenieD typy={typy} />;
      case "2.8":
        return <BlyskD typy={typy} />;
      case "2.9":
        return <SzkieletD typy={typy} />;
      default:
        return <PrzyciskiD />;
    }
  };

  const pierwsza = (nr: string): ReactNode => {
    switch (nr) {
      case "2.1":
        return <ScenaKursu wariant="b" typy={typy} />;
      case "2.2":
        return <ScenaSzansy wariant="a" typy={typy} />;
      case "2.3":
        return <ScenaHistorii wariant="c" typy={typy} />;
      case "2.4":
        return (
          <div className="a-scena">
            <PasekDni wariant="a" dni={dane.dni} />
          </div>
        );
      case "2.5":
        return (
          <div className="a-scena">
            <FiltryWKontekscie wszystkie={dane.wszystkie} ligi={dane.ligiTypow} drabinki={dane.drabinki} telefon={telefon} />
          </div>
        );
      case "2.6":
        return (
          <div className="a-scena">
            <KartyD wszystkie={dane.wszystkie} drabinki={dane.drabinki} />
          </div>
        );
      case "2.7":
        return <ScenaRozliczenia wariant="b" typy={typy} />;
      case "2.8":
        return <ScenaZmiany wariant="b" />;
      case "2.9":
        return <ScenaLadowania wariant="a" typ={typy[0]} />;
      default:
        return <ScenaPrzyciskow />;
    }
  };

  const ekran = (
    <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
      <div className="p-tresc" style={{ maxWidth: 880 }}>
        {POZYCJE.map((poz) => {
          const pokazPrzed = !!przed[poz.nr];
          return (
            <section key={poz.nr} className="a-sekcja" id={`atom-${poz.nr}`}>
              <div className="a-sekcja-glowa">
                <div>
                  <h2 className="p-n">
                    <span>{poz.nr}</span>
                    {poz.tytul}
                  </h2>
                  <p className="a-opis">wybrane: {poz.wybor}</p>
                </div>
                <div className="a-warianty" role="group" aria-label="Porównanie">
                  <button type="button" aria-pressed={!pokazPrzed} onClick={() => setPrzed((p) => ({ ...p, [poz.nr]: false }))}>
                    {poz.etykiety?.[0] ?? "Dopracowane"}
                  </button>
                  <button type="button" aria-pressed={pokazPrzed} onClick={() => setPrzed((p) => ({ ...p, [poz.nr]: true }))}>
                    {poz.etykiety?.[1] ?? "Pierwsza wersja"}
                  </button>
                </div>
              </div>
              <div key={`${poz.nr}-${pokazPrzed}`}>{pokazPrzed ? pierwsza(poz.nr) : dopracowane(poz.nr)}</div>
              <ul className="d-lista-poprawek">
                {poz.poprawki.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
              {poz.uwaga && <div className="d-uwaga">{poz.uwaga}</div>}
            </section>
          );
        })}
      </div>
    </div>
  );

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 2b <span>· dopracowanie wybranych atomów</span>
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
            {POZYCJE.map((p) => (
              <a key={p.nr} href={`#atom-${p.nr}`} style={{ color: "#aeb4b6", fontSize: 12 }}>
                {p.nr}
              </a>
            ))}
          </div>
        </div>
        <div className="p-pulpit-opis">
          Każda sekcja: wersja dopracowana, przełącznik do pierwszej wersji, lista zmian i – gdzie trzeba – sprawa do decyzji.
        </div>
      </div>
      {telefon ? <div className="p-rama-telefon">{ekran}</div> : ekran}
    </MotionConfig>
  );
}
