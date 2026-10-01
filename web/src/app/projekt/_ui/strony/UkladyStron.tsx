"use client";

import { AnimatePresence, MotionConfig } from "framer-motion";
import { useEffect, useState } from "react";

import "../../atomy.css";
import "../../atomy2.css";
import "../../elementy.css";
import "../../szkielet.css";
import "../../strony.css";
import "../../kontrola.css";
import "../../zawodnik.css";
import "../../jak.css";

import type { DaneStron } from "../../_dane/strony";
import { Sekcja, type WariantAtomu } from "../atomy/wspolne";
import type { KluczNav } from "../szkielet/ikonyNav";
import { MenuKomputerPlus, MenuTelefon, Paleta, PrawaStrona, StopkaPlus } from "../szkielet/Szkielet";
import { StronaDruzyny, StronaGlowna } from "./StronaGlowna";
import { StronaMecze } from "./StronaMecze";
import { StronaMeczu } from "./StronaMeczu";
import { StronaSkutecznosci } from "./StronaSkutecznosci";
import { StronaWynikowAdmin } from "./StronaKontroli";
import type { DaneKontroli } from "../../_dane/kontrola";
import type { ZawodnikStrony } from "../../_dane/zawodnik";
import { StronaZawodnika } from "./StronaZawodnika";
import { PodpowiedziPokaz, StronaJakCzytac } from "./StronaJakCzytac";
import type { DaneSkutecznosci } from "../../_dane/skutecznosc";
import type { MeczStrony } from "../../_dane/mecz";

type Motyw = "ciemny" | "jasny";
const PALETA: Record<Motyw, string> = { ciemny: "b1", jasny: "p3" };

const SEKCJE: { klucz: string; nr: string; tytul: string; opis: string; warianty: WariantAtomu[] }[] = [
  {
    klucz: "glowna",
    nr: "5.1",
    tytul: "Strona główna – Zawodnicy",
    opis: "Zatwierdzona 01.10: układ C po dopracowaniu. Pozostałe warianty zostają do porównania.",
    warianty: [
      {
        id: "a",
        nazwa: "A · Tablica na górze",
        opis: "najpierw trzy rzeczy na dziś (typ dnia duży, kupon dnia, 7 dni), potem cała lista. Na telefonie typ dnia, a kupon i wyniki jeden pod drugim.",
      },
      {
        id: "b",
        nazwa: "B · Dwie kolumny",
        opis: "lista od razu na górze, tablica w prawej kolumnie, która jedzie razem z przewijaniem (jak kupon u Superbetu). Na telefonie tablica zamienia się w karty do przesuwania palcem.",
      },
      {
        id: "c",
        nazwa: "C · Najpierw najlepsze",
        opis: "trzy najmocniejsze typy (każdy z innego meczu), pod nimi dwa wąskie paski: kupon dnia i 7 dni. Lista pogrupowana mecz po meczu z herbami, jak w Sofascore.",
      },
    ],
  },
  {
    klucz: "druzyny",
    nr: "5.2",
    tytul: "Drużyny",
    opis: "Gole, rożne, strzały i kartki całych drużyn. Szkielet jak na zatwierdzonej stronie Zawodnicy; różnice są w tym, jak pokazać mecz. W migawce 15 typów drużynowych, rozłożonych na 5 dni – stąd „najbliższe dni”.",
    warianty: [
      {
        id: "ab",
        nazwa: "A+B · Wybrany",
        opis: "szkielet jak Zawodnicy (najmocniejsze, kupon, 7 dni), a każdy mecz w liście to pojedynek: herby i średnie obu drużyn w rynkach typów. Objaśnienie pasków raz nad listą.",
      },
      {
        id: "a",
        nazwa: "A · Jak Zawodnicy",
        opis: "dokładnie ten sam układ co strona główna: najmocniejsze, kupon i 7 dni, lista mecz po meczu. Zero nauki – kto zna jedną stronę, zna obie.",
      },
      {
        id: "b",
        nazwa: "B · Mecz jak pojedynek",
        opis: "każdy mecz to karta z dużymi herbami i paskami średnich obu drużyn w rynkach typów (np. rożne 5,6 vs 4,1) – od razu widać, skąd typ. Pod spodem typy.",
      },
      {
        id: "c",
        nazwa: "C · Po rynkach",
        opis: "najmocniejsze na górze, lista w grupach rynków (Rożne, Gole, Strzały) – dla gracza, który gra jeden rodzaj zakładu.",
      },
    ],
  },
  {
    klucz: "mecze",
    nr: "5.3",
    tytul: "Mecze – lista",
    opis: "Wejście do narzędzia pokryć (5.4). W wierszu to, co jest w środku meczu: ilu zawodników ma kurs i ile naszych typów jest już na liście – bez „najmocniejszy %”. Na liście mecze z kursami na zawodników albo z naszymi typami. Kliknij Ireland – Austria albo Wales – Norway: otworzy się 5.4.",
    warianty: [
      {
        id: "a",
        nazwa: "Lista – wejście do pokryć",
        opis: "dni, rozgrywki, mecze po rozgrywkach; prawa kolumna: „43 zawodników z kursem” i „2 typy na liście”.",
      },
    ],
  },
  {
    klucz: "mecz",
    nr: "5.4",
    tytul: "Strona meczu – pokrycia",
    opis: "Narzędzie jak Statshub: wszyscy zawodnicy z kursem w danym rynku, ile razy przebili linię w ostatnich 10 (albo 5) meczach, kursy Superbet i Betclic. Bez propozycji – tylko znacznik „na liście”, gdy mamy typ. Dane: pełne kadry 2 meczów pobrane 01.10. UWAGA: dziś na stronę idzie jeden kurs na linię (wyższy z dwóch) – w prototypie stoi w kolumnie Superbet; osobny Betclic po zmianie w pipeline.",
    warianty: [
      {
        id: "a",
        nazwa: "A · Tabela z wyborem linii",
        opis: "wybierasz rynek i linię (powyżej 0,5 / 1,5 / …), każdy zawodnik ma kratki z ostatnich meczów, wynik „9/10”, średnią i dwa kursy. Sortowanie po pokryciu albo kursie.",
      },
      {
        id: "b",
        nazwa: "B · Siatka wszystkich linii (odrzucony 01.10)",
        opis: "wszystkie linie naraz jako kolumny (0,5+ / 1,5+ / 2,5+): w każdej komórce „9/10” i kursy, tło mocniejsze przy wyższym pokryciu. Klik w nagłówek linii sortuje. Najbliżej Statshub.",
      },
    ],
  },
  {
    klucz: "skut",
    nr: "5.5",
    tytul: "Skuteczność – klient",
    opis: "Każdy typ zostaje w historii. U góry jedna liczba i zdanie (58% · 274 z 472 typów weszło od 14.09), obok ostatnie 7 dni i produkty; filtr Wszystko / Zawodnicy / Drużyny / Drabinki. Liczymy jak w produkcji: tylko to, co było na stronie, drabinki 1. szczebel, zwrot ani nie trafia, ani nie przegrywa. Warianty różnią się wyborem dnia.",
    warianty: [
      { id: "a", nazwa: "A · Kalendarz – wybrany", opis: "wybrany 01.10 i dopracowany: miesiące ‹ ›, kolumna tygodnia (komputer), dzień z mniej niż 5 typami bez procentu („2 z 2”), przyszłe dni widoczne, kropka przy dziś, legenda kolorów, strzałki dnia w panelu i klawisze strzałek na kalendarzu." },
      { id: "b", nazwa: "B · Dzień po dniu", opis: "lista dni od najnowszego: wynik i pasek, klik rozwija typy tego dnia. Jak wyniki w Sofascore." },
      { id: "c", nazwa: "C · Wykres", opis: "słupek na każdy dzień (wysokość = trafność) z linią średniej; klik w słupek – lista typów dnia pod wykresem." },
    ],
  },
  {
    klucz: "kontrola",
    nr: "5.6",
    tytul: "Wyniki – admin: Kontrola",
    opis: "Admin ma nad Wynikami przełącznik Wyniki | Kontrola (zastępuje „pokaż jak widzi klient”: Wyniki = dokładnie widok klienta). Kontrola = dziewięć pytań, każde z werdyktem policzonym z liczb i kropką stanu (zielona / żółta / czerwona). Wspólny obraz: poprzeczka – pasek to, ile weszło, pionowa kreska to, ile obiecywał model albo zakładał kurs. Dane z migawki admina 01.10 (widok klienta z 30.09 – liczby mogą się różnić o jeden cykl).",
    warianty: [
      { id: "a", nazwa: "A · Raport – wybrany", opis: "wybrany 01.10 i dopracowany: pytania jedno pod drugim z werdyktem i obrazem; z boku spis z kropkami, który podąża za czytaniem. Na telefonie przyklejony pasek pytań (przewija się sam do bieżącego). Puste stany mówią, czego brakuje. Widok pamięta się w adresie (?widok=kontrola)." },
    ],
  },
  {
    klucz: "zawodnik",
    nr: "5.7",
    tytul: "Strona zawodnika",
    opis: "Wejście z wyszukiwarki, strony meczu i karty typu – bez pozycji w menu. Strona meczu to jeden rynek i wszyscy zawodnicy; tu odwrotnie: jeden zawodnik i wszystkie jego rynki naraz, jego typy na liście i historia naszych typów na niego. Dane: pełne kadry 2 meczów z 01.10. Przełącz zawodnika nad podglądem: Schmid ma typ na liście i jeszcze żadnego rozliczenia, Haaland ma rozliczony typ.",
    warianty: [
      { id: "a", nazwa: "A · Tabela rynków – wybrany", opis: "wybrany 01.10 („klasa”) i dopracowany: klik w rynek rozwija wszystkie linie naraz (z „9/10” i kursem, klik ustawia linię) i dziennik meczów (data, rywal, minuty, wartość). Rynek z naszym typem zawsze na górze, przy zmianie linii kratki płynnie zmieniają kolor, a „X/10” miga." },
    ],
  },
  {
    klucz: "jak",
    nr: "5.8",
    tytul: "Jak czytać typy",
    opis: "Zamiast „Jak to działa” (decyzja 01.10): bez opisu modelu, za to co znaczy każda liczba na karcie – na prawdziwym typie z listy. Lejek z liczbami zamiast trzech kafli z ikonkami (zakaz z listy AI slopu), słowniczek z małymi przykładami z naszych elementów, najczęstsze pytania. Każda odpowiedź to prawda o produkcie: kursy co godzinę, nowe typy do 1,5 h przed meczem, zwrot ani nie trafia, ani nie przegrywa, brak gwarancji.",
    warianty: [
      { id: "b", nazwa: "B · Krok po kroku – wybrany", opis: "wybrany 01.10 („klasa”) i dopracowany: kropki postępu klikalne (skok do części), strzałki ← → na klawiaturze, na telefonie przesunięcie palcem; ostatni krok prowadzi dalej (typy na dziś, słowniczek). W słowniczku prawdziwa drabinka z listy zamiast poglądowych kursów." },
    ],
  },
  {
    klucz: "podpowiedz",
    nr: "5.9",
    tytul: "Podpowiedź „?” przy elementach",
    opis: "Wyjaśnienie tam, gdzie pada pytanie: mały „?” przy półkach, passie „10 z 10”, zwrocie, drabince. Dymek z jednym zdaniem ze słowniczka i linkiem do „Jak czytać typy”. Zamyka się kliknięciem obok albo klawiszem Esc. Kliknij „?” w podglądzie.",
    warianty: [{ id: "a", nazwa: "Dymek ze słowniczka", opis: "ta sama treść co w słowniczku – jedno źródło, zero rozjazdów." }],
  },
];

export type StartUkladow = Record<string, string | undefined>;

export function UkladyStron({
  dane,
  mecze,
  skutecznosc,
  kontrola,
  zawodnicy,
  start,
}: {
  dane: DaneStron;
  mecze: MeczStrony[];
  skutecznosc: DaneSkutecznosci;
  kontrola: DaneKontroli;
  zawodnicy: ZawodnikStrony[];
  start: StartUkladow;
}) {
  const [nrMeczu, setNrMeczu] = useState(0);
  const [nrZaw, setNrZaw] = useState(0);
  // klik w mecz na liście (5.3) otwiera jego stronę w 5.4 – gdy mamy dla niego pokrycia
  const otworzMecz = (id: number) => {
    const i = mecze.findIndex((x) => x.id === id);
    if (i < 0) return;
    setNrMeczu(i);
    document.getElementById("atom-5.4")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const [motyw, setMotyw] = useState<Motyw>(start.m === "jasny" ? "jasny" : "ciemny");
  const [wybory, setWybory] = useState<Record<string, string>>(() =>
    Object.fromEntries(SEKCJE.map((x) => [x.klucz, x.warianty.some((w) => w.id === start[x.klucz]) ? start[x.klucz]! : x.klucz === "glowna" ? "c" : x.klucz === "druzyny" ? "ab" : x.warianty[0].id])),
  );
  // menu w każdej sekcji żyje osobno – w sekcji Drużyny zaczyna od „Drużyny”
  const [aktywne, setAktywne] = useState<Record<string, string>>({ glowna: "zawodnicy", druzyny: "druzyny", mecze: "mecze", mecz: "mecze", skut: "skutecznosc", kontrola: "skutecznosc", zawodnik: "zawodnicy", jak: "jak", podpowiedz: "zawodnicy" });
  const [paleta, setPaleta] = useState<string | null>(null);

  useEffect(() => {
    window.history.replaceState(null, "", `?${new URLSearchParams({ m: motyw, ...wybory })}`);
  }, [motyw, wybory]);

  useEffect(() => {
    const klaw = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaleta("komputer-glowna");
      }
    };
    window.addEventListener("keydown", klaw);
    return () => window.removeEventListener("keydown", klaw);
  }, []);

  const zmienMotyw = () => setMotyw((m) => (m === "ciemny" ? "jasny" : "ciemny"));
  const liczby: Partial<Record<KluczNav, number>> = {
    zawodnicy: dane.wszystkie.filter((t) => !t.druzynowy).length,
    druzyny: dane.wszystkie.filter((t) => t.druzynowy).length,
    mecze: new Set(dane.wszystkie.map((t) => t.mecz)).size,
  };
  const jasneLogo = motyw === "ciemny";

  const scena = (klucz: string, w: string) => {
    const m = mecze[nrMeczu];
    const Strona = klucz === "druzyny" ? StronaDruzyny : klucz === "mecze" ? StronaMecze : StronaGlowna;
    // strona meczu dostaje mecz z przełącznika nad podglądem
    const tresc = (telefon: boolean) =>
      klucz === "mecz" ? (
        <StronaMeczu key={`${w}-${nrMeczu}`} wariant={w} m={m} dane={dane} telefon={telefon} />
      ) : klucz === "jak" ? (
        <StronaJakCzytac key={w} dane={dane} telefon={telefon} />
      ) : klucz === "podpowiedz" ? (
        <PodpowiedziPokaz />
      ) : klucz === "zawodnik" ? (
        <StronaZawodnika key={`${w}-${nrZaw}`} z={zawodnicy[nrZaw]} telefon={telefon} />
      ) : klucz === "kontrola" ? (
        <StronaWynikowAdmin key={w} kontrola={kontrola} skutecznosc={skutecznosc} telefon={telefon} />
      ) : klucz === "skut" ? (
        <StronaSkutecznosci key={w} wariant={w} dane={skutecznosc} telefon={telefon} />
      ) : (
        <Strona key={w} wariant={w} dane={dane} telefon={telefon} otworz={klucz === "mecze" ? otworzMecz : undefined} />
      );
    const aktywna = aktywne[klucz];
    const ustaw = (k: string) => setAktywne((a) => ({ ...a, [klucz]: k }));
    return (
    <div className="st-sceny">
      {klucz === "zawodnik" && (
        <div className="mz-wybor-meczu" role="group" aria-label="Zawodnik w podglądzie">
          <span>zawodnik w podglądzie:</span>
          {zawodnicy.map((x, i) => (
            <button key={x.id} type="button" aria-pressed={i === nrZaw} onClick={() => setNrZaw(i)}>
              {x.nazwa}
            </button>
          ))}
        </div>
      )}
      {klucz === "mecz" && (
        <div className="mz-wybor-meczu" role="group" aria-label="Mecz w podglądzie">
          <span>mecz w podglądzie:</span>
          {mecze.map((x, i) => (
            <button key={x.id} type="button" aria-pressed={i === nrMeczu} onClick={() => setNrMeczu(i)}>
              {x.gosp.nazwa} – {x.gosc.nazwa}
            </button>
          ))}
        </div>
      )}
      <div style={{ position: "relative" }}>
        <div className="s-okno st-okno">
          <MenuKomputerPlus
            jasneLogo={jasneLogo}
            aktywna={aktywna}
            ustaw={ustaw}
            liczby={liczby}
            prawa={<PrawaStrona motyw={motyw} zmienMotyw={zmienMotyw} stan="swieze" szukaj={() => setPaleta(`komputer-${klucz}`)} />}
          >
            {tresc(false)}
            <StopkaPlus jasneLogo={jasneLogo} />
          </MenuKomputerPlus>
        </div>
        <AnimatePresence>{paleta === `komputer-${klucz}` && <Paleta dane={dane} zamknij={() => setPaleta(null)} />}</AnimatePresence>
      </div>
      <div className="s-telefon-rama">
        <div style={{ position: "relative", height: 780 }}>
          <MenuTelefon
            wariant="a"
            aktywna={aktywna}
            ustaw={ustaw}
            motyw={motyw}
            zmienMotyw={zmienMotyw}
            stan="swieze"
            szukaj={() => setPaleta(`telefon-${klucz}`)}
          >
            {tresc(true)}
            <StopkaPlus jasneLogo={jasneLogo} />
          </MenuTelefon>
          <AnimatePresence>{paleta === `telefon-${klucz}` && <Paleta dane={dane} zamknij={() => setPaleta(null)} />}</AnimatePresence>
        </div>
      </div>
    </div>
    );
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="p-pulpit">
        <div className="p-pulpit-wnetrze">
          <div className="p-pulpit-tytul">
            Etap 5 <span>· układy stron</span>
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
        </div>
        <div className="p-pulpit-opis">Menu i stopka – zatwierdzone w etapie 4. Dane z migawki 30.09, 22:40. Wybory zapisują się w adresie strony.</div>
      </div>
      <div className="p-ekran" data-p-motyw={motyw} data-p-paleta={PALETA[motyw]} data-p-font="2c">
        <div className="p-tresc" style={{ maxWidth: 1320 }}>
          {SEKCJE.map((x) => (
            <Sekcja
              key={x.klucz}
              nr={x.nr}
              tytul={x.tytul}
              opis={x.opis}
              warianty={x.warianty}
              wybrany={wybory[x.klucz]}
              zmien={(id) => setWybory((v) => ({ ...v, [x.klucz]: id }))}
            >
              {scena(x.klucz, wybory[x.klucz])}
            </Sekcja>
          ))}
        </div>
      </div>
    </MotionConfig>
  );
}
