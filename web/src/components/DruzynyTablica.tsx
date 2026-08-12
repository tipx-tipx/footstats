"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { BetCard } from "./BetCard";
import { BetRow, BetRowNaglowek } from "./BetRow";
import { grupujWarianty } from "@/lib/warianty";
import { FilterDropdown } from "./FilterDropdown";
import { Reveal } from "./Reveal";
import { Wyrozniona } from "./Wyrozniona";
import type { DruzynaForma, ValueBet, Zawodnik } from "@/lib/types";
import { useTeraz } from "@/lib/useTeraz";
import { KROPKA_STYL, PRZEWAGA_KROPKI } from "@/lib/slownik";

/**
 * Ceduła typów drużynowych pod SKALĘ sezonu (setki typów dziennie).
 * Układ: DZIŚ jest głównym elementem strony – top 3 jako karty, pod nimi
 * sortowalna ceduła dnia przycięta do LIMIT_DZIS wierszy. Kolejne dni to
 * jedna linia nagłówka ze spisem rozgrywek, rozwijana na klik (animowane).
 * Dzięki temu strona przy wejściu ma stałą, krótką wysokość niezależnie
 * od tego, czy w bazie jest 10 czy 300 typów.
 */

function kluczDnia(ts: number): string {
  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "short",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

function etykietaDnia(ts: number, teraz: number): { glowna: string; data: string } {
  const pelna = new Intl.DateTimeFormat("pl-PL", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
  if (kluczDnia(ts) === kluczDnia(teraz)) return { glowna: "dziś", data: pelna };
  if (kluczDnia(ts) === kluczDnia(teraz + 86400))
    return { glowna: "jutro", data: pelna };
  const [dow, ...reszta] = pelna.split(" ");
  // pl-PL daje "czwartek, 23 lipca" – przecinek zostaje przy dniu tygodnia
  return { glowna: dow.replace(/,$/, ""), data: reszta.join(" ") };
}

function odmienTypy(n: number): string {
  if (n === 1) return "1 typ";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "typy" : "typów"}`;
}

function odmienMecze(n: number): string {
  if (n === 1) return "1 mecz";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "mecze" : "meczów"}`;
}

/**
 * Zdanie „czemu dziś tyle" — pokazywane tylko wtedy, gdy naprawdę jest co
 * tłumaczyć: jutro musi mieć wyraźnie więcej meczów niż dziś. Przy zwykłym
 * dniu nic nie piszemy, bo komentarz do normalnego stanu to szum.
 */
function CzemuTyleDzis({
  meczeDzis,
  meczeJutro,
}: {
  meczeDzis: number;
  meczeJutro: number;
}) {
  if (!meczeDzis && !meczeJutro) return null;
  if (meczeJutro < meczeDzis * 2 || meczeJutro < 5) return null;
  return (
    <p className="mt-2 text-sm leading-relaxed text-muted">
      Dziś w naszych rozgrywkach jest {odmienMecze(meczeDzis)}, jutro{" "}
      {odmienMecze(meczeJutro)} – stąd ta różnica. Typów nie dokładamy na siłę:
      liczba zależy od terminarza, nie od tego, ile chcielibyśmy pokazać.
    </p>
  );
}

/**
 * RODZINA RYNKU — kartki drużyny i kartki w meczu to dla czytelnika JEDNO
 * („znowu kartki"), choć w danych mają osobne kody. Ta sama definicja, co
 * w limicie `LISTA_PER_RODZINA` po stronie pipeline'u.
 */
function rodzinaRynku(kod: string): string {
  return kod.replace(/^(team_|match_|wiecej_)/, "");
}

const NAZWA_RODZINY: Record<string, string> = {
  goals: "gole",
  corners: "rzuty rożne",
  cards: "kartki",
  shots: "strzały",
  sot: "celne strzały",
  fouls: "faule",
};

/**
 * DZIEŃ ZŁOŻONY Z JEDNEGO ZAKŁADU MA SIĘ DO TEGO PRZYZNAĆ (2026-08-06).
 *
 * Zgłoszenie usera brzmiało „bez przesytu". Zmierzone 05.08: limity listy
 * dywersyfikują MOCNIEJ niż źródło (16 opublikowanych typów było
 * różnorodniejsze niż pula 45 legów, w której 71% to jeden rynek), więc
 * zaostrzanie ich tylko skróciłoby listę — nie ma czym zastąpić. Ale limit
 * pilnuje CAŁEJ listy, a czytelnik patrzy na JEDEN DZIEŃ i widzi w sobotę
 * cztery razy „gole poniżej 0,5" pod rząd.
 *
 * Skoro nie wolno tego wyciąć bez wyrzucania dobrych typów, strona to mówi.
 * Powtórzenie z wyjaśnieniem czyta się jak decyzja; bez wyjaśnienia — jak
 * brak pomysłu.
 */
function JedenZaklad({ lista }: { lista: ValueBet[] }) {
  if (lista.length < 3) return null;
  const licznik = new Map<string, number>();
  for (const b of lista) {
    const klucz = `${rodzinaRynku(b.rynek_kod)}|${b.strona}`;
    licznik.set(klucz, (licznik.get(klucz) ?? 0) + 1);
  }
  const [klucz, n] = [...licznik.entries()].sort((a, b) => b[1] - a[1])[0];
  if (n < 3 || n / lista.length < 0.6) return null;
  const [rodzina, strona] = klucz.split("|");
  const nazwa = NAZWA_RODZINY[rodzina];
  if (!nazwa) return null;
  const kierunek = strona === "ponizej" ? "poniżej" : strona === "powyzej" ? "powyżej" : null;
  return (
    <p className="mt-2 text-sm leading-relaxed text-muted">
      {n} z {lista.length} typów na ten dzień to ten sam zakład –{" "}
      <strong className="font-medium text-ink-soft">
        {nazwa}
        {kierunek ? ` ${kierunek}` : ""}
      </strong>{" "}
      w różnych meczach. Tak wyszedł rachunek: w pozostałych rynkach kursy
      stały bliżej naszych liczb. Nie dokładamy typów dla odmiany.
    </p>
  );
}

function odmienPozostale(n: number): string {
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "pozostałe" : "pozostałych"}`;
}

const PROG_SEKCJI_TOP = 6; // poniżej tylu typów dnia karty "top" to szum
const LIMIT_DZIS = 12; // tyle wierszy ceduły dnia widać przed "pokaż wszystkie"
const LIMIT_LIGI_DNIA = 3; // tyle wierszy pokazuje otwarta liga dnia przyszłego

function dataKrotka(ts: number): string {
  return new Intl.DateTimeFormat("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Europe/Warsaw",
  }).format(new Date(ts * 1000));
}

type Sort = "rank" | "szansa" | "kurs" | "godzina";
const SORTY: { kod: Sort; label: string }[] = [
  // „NAJMOCNIEJSZE" -> „POLECANE" (2026-08-02). Tamto słowo obiecywało
  // obiektywną moc, której nikt nie zdefiniował — a kolejność brała się
  // z `rank_score`, które w każdym kanale znaczy co innego (wartość w %
  // przy sumach meczowych, szansa × pierwiastek kursu przy drużynowych,
  // ZERO przy typach wznowionych, czyli przy większości listy). Efekt:
  // stronę otwierały typy 43% i 38% podpisane jako najmocniejsze.
  // „Polecane" nie obiecuje obiektywności, tylko mówi „to nasza kolejność".
  { kod: "rank", label: "polecane" },
  { kod: "szansa", label: "szansa" },
  { kod: "kurs", label: "kurs" },
  { kod: "godzina", label: "godzina" },
];

/**
 * JEDNA MIARA DLA WSZYSTKICH RYNKÓW, liczona tu — nie z backendu.
 *
 * Szansa × pierwiastek z kursu: sama szansa wynosiłaby na górę wyłącznie
 * linie 0,5, a sama wartość — najdłuższe strzały. Pierwiastek tłumi kurs
 * na tyle, żeby typ 87% po 1,21 wygrał z typem 43% po 3,55, ale nie na tyle,
 * żeby wysoki kurs przestał się liczyć. Ta sama formuła, której backend
 * używa do pewniaków (`_atrakcyjnosc`) — tyle że tutaj dostaje ją KAŻDY typ,
 * niezależnie od kanału, którym powstał.
 */
const moc = (b: ValueBet) => b.p_model * Math.sqrt(b.kurs ?? b.fair_kurs ?? 1);

/**
 * Typ z rynku CHWILOWO WSTRZYMANEGO schodzi na koniec kolejności „polecane".
 *
 * Zostaje na liście, bo cena jest zamrożona i user mógł go zagrać — ale skoro
 * sami przestaliśmy ten rynek polecać i nie wpuszczamy go do kuponów, to nie
 * ma prawa otwierać listy podpisanej „polecane". Kolejność wewnątrz obu grup
 * bez zmian.
 */
const wgPolecanych = (xs: ValueBet[]) =>
  [...xs].sort(
    (a, z) =>
      Number(!!a.rynek_wstrzymany) - Number(!!z.rynek_wstrzymany) ||
      moc(z) - moc(a),
  );

/** Od tylu typów dnia rozdzielanie na półki przestaje być szumem. */
const PROG_POLEK = 4;
/**
 * Granica półek: „częściej wchodzą" kontra „więcej płacą" — po KURSIE.
 *
 * ⚑ Do 12.08 dzieliliśmy po naszej szansie (`p_model >= 0,7`). Od 12.08 szansa
 * na karcie jest ściągana do ceny (backend: `rozliczanie.waga_sciagania`), bo
 * tak liczba jest uczciwa — luka deklaracji spadła z −12,9 pp do +0,3 pp. Ale
 * ściągnięta szansa to w 90% cena, więc próg 0,70 odpowiadał odtąd kursowi
 * ~1,35 i pierwsza półka robiła się pusta: zmierzone na żywej liście, 5 typów
 * przed zmianą, 0 po niej.
 *
 * Dzielimy więc po kursie, bo to FAKT RYNKU, a nie nasza deklaracja — nie
 * przesunie się przy następnej zmianie modelu ani wagi ściągania. Inaczej ten
 * próg trzeba by przestawiać po każdej takiej zmianie, a pustą półkę
 * odkrywalibyśmy dopiero wtedy, gdy ktoś ją zobaczy.
 *
 * 1,90 nie jest liczbą z sufitu: przy niej mierzyliśmy różnicę segmentów
 * (drużynowe „poniżej" przy kursie 1,9+ to jedyny wycinek z dodatnim zwrotem).
 */
const PROG_KURSU_POLEK = 1.9;
const czesciejWchodzi = (b: ValueBet) =>
  (b.kurs ?? b.fair_kurs ?? 0) < PROG_KURSU_POLEK;

/** Animowane rozwijanie bloku – wspólny ruch dla dni, sekcji i ceduły dnia. */
function Rozwin({
  open,
  children,
}: {
  open: boolean;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={reduced ? false : { height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={reduced ? undefined : { height: 0, opacity: 0 }}
          transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          className="overflow-hidden"
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Linia "pokaż pozostałe / zwiń" – jedno domknięcie listy w całej tablicy. */
function PokazButton({
  open,
  ukryte,
  zwinLabel,
  onClick,
}: {
  open: boolean;
  ukryte: number;
  zwinLabel: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full border-b border-hairline px-2 py-1.5 text-left text-[11px] font-medium text-brand-deep transition-colors hover:bg-card-soft sm:px-3"
    >
      {open ? zwinLabel : `pokaż ${odmienPozostale(ukryte)}`}
    </button>
  );
}

export function DruzynyTablica({
  bets: wszystkie,
  forma,
  ligaByMecz,
  teraz: terazSerwera,
  meczeTs = [],
}: {
  /** typy drużynowe w kolejności rankingu silnika (najlepsze pierwsze) */
  bets: ValueBet[];
  forma: DruzynaForma[];
  /** mecz_id -> nazwa rozgrywek (z matches.json) */
  ligaByMecz: Record<number, string>;
  /** timestamp serwera (s) – spójne "dziś/jutro" bez zegara klienta */
  teraz: number;
  /**
   * Gwizdki WSZYSTKICH nadchodzących meczów w bazie — do wytłumaczenia, czemu
   * dziś typów jest mało. Surowe znaczniki, nie gotowe liczby: dzień tnie
   * `kluczDnia` w tym pliku i musi to robić JEDNA definicja, inaczej strona
   * policzyłaby mecze według innej granicy doby niż typy.
   */
  meczeTs?: number[];
}) {
  // ZEGAR PRZEGLĄDARKI, nie chwila zbudowania strony. Strona bywa oddana
  // z cache sprzed godzin (patrz useTeraz), a wtedy serwerowe odcięcie
  // „mecz się zaczął" jest równie stare co ona — i rozegrane mecze wiszą
  // na liście do ręcznego odświeżenia. Zgłoszenie usera 2026-08-02.
  const teraz = useTeraz(terazSerwera);
  const bets = useMemo(
    () => wszystkie.filter((b) => b.kickoff_ts > teraz),
    [wszystkie, teraz],
  );
  const [rynek, setRynek] = useState("wszystkie");
  const [liga, setLiga] = useState("wszystkie");
  const [sort, setSort] = useState<Sort>("rank");
  // kafelek dnia wybrany w slocie "dalsze dni" (null = pierwszy z brzegu)
  const [wybranyDzien, setWybranyDzien] = useState<string | null>(null);
  // akordeon lig w dniach przyszłych: zwinięta / top 3 / wszystkie
  // (klucz: "dzień|liga"; bez wpisu najmocniejsza liga dnia startuje na "top")
  const [stanLig, setStanLig] = useState<
    Record<string, "zwin" | "top" | "all">
  >({});
  const [calyDzis, setCalyDzis] = useState(false);

  const formaById = useMemo(
    () => new Map(forma.map((f) => [f.id, f])),
    [forma],
  );

  const rynki = useMemo(
    () => [...new Set(bets.map((b) => b.rynek))].sort(),
    [bets],
  );
  const ligi = useMemo(
    () =>
      [...new Set(bets.map((b) => ligaByMecz[b.mecz_id]).filter(Boolean))].sort(),
    [bets, ligaByMecz],
  );

  // liczniki do chipów rozgrywek: po filtrze rynku, przed filtrem ligi –
  // chip mówi, ile typów kryje się za kliknięciem
  const licznikLig = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of bets) {
      if (rynek !== "wszystkie" && b.rynek !== rynek) continue;
      const l = ligaByMecz[b.mecz_id];
      if (l) m.set(l, (m.get(l) ?? 0) + 1);
    }
    return m;
  }, [bets, rynek, ligaByMecz]);

  // JEDEN WIERSZ NA TYP, NIE NA LINIĘ (2026-08-01, zgłoszenie usera): ta sama
  // drużyna z rożnymi poniżej 4,5 · 5,5 · 6,5 zajmowała trzy wiersze ceduły,
  // choć to jeden pomysł na trzech poprzeczkach. Pozostałe linie jadą
  // z wierszem jako drabinka wyboru w rozwinięciu. Patrz lib/warianty.ts.
  const grupy = useMemo(
    () =>
      grupujWarianty(
        bets.filter(
          (b) =>
            (rynek === "wszystkie" || b.rynek === rynek) &&
            (liga === "wszystkie" || ligaByMecz[b.mecz_id] === liga),
        ),
      ),
    [bets, rynek, liga, ligaByMecz],
  );
  const widoczne = useMemo(() => grupy.map((g) => g.glowny), [grupy]);
  const wariantyById = useMemo(
    () => new Map(grupy.map((g) => [g.glowny.id, g.warianty])),
    [grupy],
  );

  const sortuj = useMemo(
    () =>
      (xs: ValueBet[]): ValueBet[] => {
        switch (sort) {
          case "szansa":
            return [...xs].sort((a, z) => z.p_model - a.p_model);
          case "kurs":
            return [...xs].sort(
              (a, z) => (z.kurs ?? z.fair_kurs) - (a.kurs ?? a.fair_kurs),
            );
          case "godzina":
            return [...xs].sort((a, z) => a.kickoff_ts - z.kickoff_ts);
          default:
            // NIE kolejność wejścia. Payload nie jest posortowany: backend
            // sortuje PRZED doklejeniem typów wznowionych, a te wchodzą na
            // koniec w kolejności rejestru. Sprawdzone na żywej liście:
            // rank_score szedł 0, 0, 0, 0, 7.3, 0, 0.94, 0.
            return wgPolecanych(xs);
        }
      },
    [sort],
  );

  const dzisKlucz = kluczDnia(teraz);
  const dzisiejsze = useMemo(
    () => widoczne.filter((b) => kluczDnia(b.kickoff_ts) === dzisKlucz),
    [widoczne, dzisKlucz],
  );

  // karty top: 3 najlepsze dnia wg rankingu silnika – stała kotwica,
  // niezależna od wybranego sortowania ceduły
  const topIds = useMemo(() => {
    if (dzisiejsze.length < PROG_SEKCJI_TOP) return new Set<number>();
    return new Set(dzisiejsze.slice(0, 3).map((b) => b.id));
  }, [dzisiejsze]);
  const top = dzisiejsze.filter((b) => topIds.has(b.id));
  const cedulaDzis = sortuj(dzisiejsze.filter((b) => !topIds.has(b.id)));

  const przyszle = useMemo(
    () => widoczne.filter((b) => kluczDnia(b.kickoff_ts) !== dzisKlucz),
    [widoczne, dzisKlucz],
  );

  /**
   * ILE MECZÓW JEST DANEGO DNIA — czyli czemu typów jest tyle, ile jest.
   *
   * Zgłoszenie z przeglądu: „najwięcej typów jest pojutrze, nie dziś (3/4/10)".
   * Zmierzone 05.08 na żywych danych: dziś 6 meczów i 2 typy, jutro 49 meczów
   * i 14 typów. Czyli to NIE jest usterka selekcji ani modelu, tylko kształt
   * terminarza — a strona milczała i wyglądała, jakby dziś nic nie znalazła.
   *
   * Mówimy to wprost, zamiast naciągać listę: naciąganie oznaczałoby
   * wpuszczanie typów, które nie przeszły progów, czyli dokładnie odwrotność
   * tego, po co te progi są.
   */
  const meczeDnia = useMemo(() => {
    const licz = new Map<string, number>();
    for (const ts of meczeTs) {
      if (ts <= teraz) continue;
      const k = kluczDnia(ts);
      licz.set(k, (licz.get(k) ?? 0) + 1);
    }
    return licz;
  }, [meczeTs, teraz]);
  const meczeDzis = meczeDnia.get(dzisKlucz) ?? 0;
  const meczeJutro = useMemo(() => {
    const jutroKlucz = kluczDnia(teraz + 86400);
    return meczeDnia.get(jutroKlucz) ?? 0;
  }, [meczeDnia, teraz]);

  /**
   * Kolejne dni chronologicznie, w dniu sekcje rozgrywek (dla sortu
   * "najmocniejsze") – rozgrywki i typy wg rankingu silnika.
   */
  const dni = useMemo(() => {
    const wgDnia = new Map<string, ValueBet[]>();
    for (const b of [...przyszle].sort((a, z) => a.kickoff_ts - z.kickoff_ts)) {
      const k = kluczDnia(b.kickoff_ts);
      (wgDnia.get(k) ?? wgDnia.set(k, []).get(k)!).push(b);
    }
    return [...wgDnia.entries()].map(([klucz, lista]) => {
      const wgLigi = new Map<string, ValueBet[]>();
      for (const b of lista) {
        const l = ligaByMecz[b.mecz_id] ?? "Inne rozgrywki";
        (wgLigi.get(l) ?? wgLigi.set(l, []).get(l)!).push(b);
      }
      // DWIE PÓŁKI ZAMIAST LIST LIG (2026-08-02, decyzja usera).
      //
      // Dzień był dzielony na rozgrywki, czyli po tym, KTO GRA — a to jest
      // informacja, którą i tak niesie każdy wiersz i którą można wyfiltrować
      // chipem. Podział, który naprawdę pomaga wybrać, idzie po tym, JAKI TO
      // ZAKŁAD. Zmierzone na żywej liście: typy 70%+ mają średni kurs 1,31,
      // reszta 3,01. To są dwa różne produkty, a leżały w jednym worku.
      // (Od 12.08 kryterium to sam kurs — patrz `PROG_KURSU_POLEK`. Pomiar
      // wyżej zostaje, bo to on uzasadnił podział; zmieniła się tylko liczba,
      // po której go robimy.)
      //
      // Przy małym dniu nie dzielimy — dwie półki po dwa typy to nie porządek,
      // tylko dwa nagłówki.
      const wgMocy = wgPolecanych;
      const pewne = wgMocy(lista.filter(czesciejWchodzi));
      const odwazne = wgMocy(lista.filter((b) => !czesciejWchodzi(b)));
      const sekcje =
        lista.length >= PROG_POLEK && pewne.length > 0 && odwazne.length > 0
          ? [
              // BEZ ŻARGONU (2026-08-04). Było: „materiał na kupon" i „kurs to
              // wynagradza" — jedno i drugie zakłada, że czytelnik zna świat
              // zakładów. Te dwa zdania są jedynym miejscem, które tłumaczy
              // podział całej listy, więc muszą być zrozumiałe bez wstępu.
              //
              // ⚑ OPIS MUSI PASOWAĆ DO KRYTERIUM (poprawione 12.08). Zdania
              // mówiły „Szansa 70% i więcej", a podział idzie od 12.08 po
              // KURSIE — na zrzucie w pierwszej półce stały typy z szansą 69%,
              // 66% i 61% pod nagłówkiem obiecującym 70%+. Nagłówek, który
              // opisuje inne kryterium niż to użyte, jest po prostu
              // nieprawdziwy; tego pilnujemy w całym produkcie.
              {
                nazwa: "częściej wchodzą",
                opis: "Kurs poniżej 1,90. Wygrana jest mniejsza, ale takie typy wchodzą regularnie – z nich składamy kupony.",
                typy: pewne,
              },
              {
                nazwa: "więcej płacą",
                opis: "Kurs 1,90 i wyżej. Wchodzą rzadziej, ale gdy wejdą, wygrana jest wyraźnie większa.",
                typy: odwazne,
              },
            ]
          : [{ nazwa: "", opis: "", typy: wgMocy(lista) }];
      return { klucz, lista, sekcje };
    });
  }, [przyszle, ligaByMecz]);

  // stała struktura sekcji: jutro zawsze osobno, dalsze dni w jednym
  // slocie z kafelkami wyboru – liczba sekcji nie rośnie z terminarzem
  const jutroKlucz = kluczDnia(teraz + 86400);
  const jutro = dni.find((d) => d.klucz === jutroKlucz);
  const dalsze = dni.filter((d) => d.klucz !== jutroKlucz);
  const dalszyKlucz =
    wybranyDzien && dalsze.some((d) => d.klucz === wybranyDzien)
      ? wybranyDzien
      : dalsze[0]?.klucz;
  const dalszy = dalsze.find((d) => d.klucz === dalszyKlucz);

  const meczeN = new Set(widoczne.map((b) => b.mecz_id)).size;

  const formaRynku = (bet: ValueBet) =>
    formaById.get(bet.podmiot_id)?.forma[bet.rynek_kod];

  const wiersz = (bet: ValueBet, zLiga: boolean) => (
    <BetRow
      key={bet.id}
      bet={bet}
      forma={formaRynku(bet)}
      pokazGodzine={sort === "godzina"}
      liga={zLiga ? ligaByMecz[bet.mecz_id] : undefined}
      warianty={wariantyById.get(bet.id)}
    />
  );

  /**
   * Blok dnia przyszłego: gazetowy nagłówek + AKORDEON LIG. Najmocniejsza
   * liga dnia startuje otwarta (top 3), reszta to zwinięte nagłówki
   * z licznikami. Zwinięta liga = niezamontowane wiersze, więc duży dzień
   * kosztuje przy hydracji tylko tyle, ile realnie widać. Sortowanie działa
   * wewnątrz lig – struktura ligowa zostaje przy każdym sorcie.
   */
  const blokDnia = ({ klucz, lista, sekcje }: (typeof dni)[number]) => {
    const et = etykietaDnia(lista[0].kickoff_ts, teraz);
    return (
      <div key={klucz} className="mt-5">
        {/* nagłówek dnia jak w gazecie: gruba kreska + wersaliki; sticky,
            żeby przy długim dniu nie gubić orientacji */}
        <div className="sticky top-[4.4rem] z-10 -mx-4 bg-paper/85 px-4 backdrop-blur-md sm:-mx-6 sm:px-6">
          <div className="flex items-baseline gap-x-3 border-t-2 border-ink pb-1.5 pt-2">
            <span className="font-display text-lg font-bold uppercase leading-none tracking-tight">
              {et.glowna}
            </span>
            <span className="hidden text-xs text-faint sm:inline">{et.data}</span>
            <span className="ml-auto shrink-0 font-data text-xs text-muted">
              {odmienTypy(lista.length)}
            </span>
          </div>
        </div>

        <JedenZaklad lista={lista} />

        {sekcje.map(({ nazwa, opis, typy }) => {
          const kluczSekcji = `${klucz}|${nazwa}`;
          // OBIE PÓŁKI OTWARTE (2026-08-02). Przy ligach zwijanie miało sens:
          // dzień potrafił mieć osiem rozgrywek i tylko pierwsza była ważna.
          // Półki są DWIE i obie są treścią — chowanie drugiej znaczyłoby,
          // że jeden z dwóch rodzajów typów jest mniej wart pokazania.
          const stan = stanLig[kluczSekcji] ?? "top";
          const otwarta = true;
          // zwijanie ogona dopiero gdy schowa ≥2 wiersze – "pokaż 1
          // pozostały" to więcej UI niż treści
          const zwijalna = typy.length > LIMIT_LIGI_DNIA + 1;
          const posortowane = sortuj(typy);
          return (
            <section
              key={nazwa}
              aria-label={`${nazwa}: ${odmienTypy(typy.length)}`}
              className="mt-2 first:mt-1"
            >
              <div className="flex w-full items-baseline gap-2.5 py-1.5 text-left">
                <h3 className="font-display shrink-0 text-[11px] font-semibold uppercase tracking-widest text-ink">
                  {nazwa}
                </h3>
                <span
                  aria-hidden
                  className="flex-1 self-center border-t border-dotted border-hairline-strong/70"
                />
                {/* LICZNIK SEKCJI TYLKO GDY SEKCJI JEST WIĘCEJ (2026-08-04).
                    Przy jednej półce w dniu ta liczba jest identyczna
                    z licznikiem dnia dwa wiersze wyżej — wyglądało to jak
                    „4 typy / 4 typy" pod sobą i czytało się jak usterka. */}
                {sekcje.length > 1 && (
                  <span className="font-data shrink-0 text-[11px] text-faint">
                    {odmienTypy(typy.length)}
                  </span>
                )}
              </div>
              {/* JEDNO ZDANIE, CO TA PÓŁKA ZNACZY. Sama nazwa („więcej płacą")
                  domyśla się reszty; zdanie mówi, dla kogo ten rodzaj typu
                  jest i czego się po nim spodziewać. */}
              {opis && (
                <p className="mb-1 text-[11px] leading-relaxed text-faint">
                  {opis}
                </p>
              )}
              <Rozwin open={otwarta}>
                <div>
                  <BetRowNaglowek />
                  {posortowane
                    .slice(0, zwijalna ? LIMIT_LIGI_DNIA : typy.length)
                    .map((b) => wiersz(b, true))}
                  {zwijalna && (
                    <>
                      <Rozwin open={stan === "all"}>
                        <div>
                          {posortowane
                            .slice(LIMIT_LIGI_DNIA)
                            .map((b) => wiersz(b, true))}
                        </div>
                      </Rozwin>
                      <PokazButton
                        open={stan === "all"}
                        ukryte={typy.length - LIMIT_LIGI_DNIA}
                        zwinLabel="pokaż tylko najmocniejsze"
                        onClick={() =>
                          setStanLig((s) => ({
                            ...s,
                            [kluczSekcji]: stan === "all" ? "top" : "all",
                          }))
                        }
                      />
                    </>
                  )}
                </div>
              </Rozwin>
            </section>
          );
        })}
      </div>
    );
  };

  return (
    <div>
      {/* odczyty + sortowanie + filtry w jednej bandzie: żywy stan tablicy */}
      <div className="mt-6 border-y border-hairline py-3">
        <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2.5">
          {/* LICZNIK MÓWI, CO JEST W OFERCIE — nie ile rekordów mamy w bazie.
              „17 typów · 12 meczów · 3 rozgrywek" to opis tabeli; człowiek,
              który tu trafia, pyta „co dla mnie macie", a odpowiedzią są dwa
              rodzaje zakładu, nie trzy liczby o zasobach. */}
          <p className="font-data text-xs text-muted">
            <span className="font-semibold text-ink">
              {widoczne.filter(czesciejWchodzi).length} częściej wchodzą
            </span>
            {" · "}
            {widoczne.filter((b) => !czesciejWchodzi(b)).length} więcej płacą
            {" · "}
            {meczeN} {meczeN === 1 ? "mecz" : meczeN < 5 ? "mecze" : "meczów"}
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <div
              role="group"
              aria-label="Sortowanie typów"
              className="flex items-center gap-3"
            >
              {SORTY.map((s) => (
                <button
                  key={s.kod}
                  onClick={() => setSort(s.kod)}
                  aria-pressed={sort === s.kod}
                  className={`border-b-2 pb-0.5 text-[11px] font-semibold uppercase tracking-wide transition-colors ${
                    sort === s.kod
                      ? "border-brand text-brand-deep"
                      : "border-transparent text-muted hover:text-ink"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            {rynki.length > 1 && (
              <FilterDropdown
                label="Rynek"
                value={rynek}
                options={[
                  { value: "wszystkie", label: "Wszystkie rynki" },
                  ...rynki.map((r) => ({ value: r, label: r })),
                ]}
                onChange={setRynek}
              />
            )}
          </div>
        </div>
        {/* chipy rozgrywek: filtr jednym klikiem + od razu widać, gdzie jest
            mięso; na mobile pas przewijany poziomo */}
        {ligi.length > 1 && (
          <div
            role="group"
            aria-label="Filtr rozgrywek"
            className="-mx-1 mt-2.5 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none] sm:flex-wrap"
          >
            <button
              onClick={() => setLiga("wszystkie")}
              aria-pressed={liga === "wszystkie"}
              className={`shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                liga === "wszystkie"
                  ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                  : "border-hairline text-muted hover:border-hairline-strong hover:text-ink"
              }`}
            >
              Wszystkie
            </button>
            {/* „czemu Argentyna w sierpniu?" — pytanie, które zadaje sobie
                każdy, kto pierwszy raz patrzy na te chipy. Jedna cicha linijka
                zamienia dziwny zestaw lig w przemyślany zakres. */}
            {ligi.map((l) => (
              <button
                key={l}
                onClick={() => setLiga(liga === l ? "wszystkie" : l)}
                aria-pressed={liga === l}
                className={`shrink-0 rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  liga === l
                    ? "border-brand bg-brand-wash font-semibold text-brand-deep"
                    : "border-hairline text-muted hover:border-hairline-strong hover:text-ink"
                }`}
              >
                {l}
                <span className="font-data ml-1.5 text-[10px] opacity-70">
                  {licznikLig.get(l) ?? 0}
                </span>
              </button>
            ))}
          </div>
        )}
        {ligi.length > 1 && (
          <p className="mt-1.5 px-1 text-[11px] leading-relaxed text-faint">
            Europa w sezonie, Ameryka Południowa i Skandynawia przez resztę roku.
          </p>
        )}
        {/* LEGENDA KROPKI NA EKRANIE, NIE W DYMKU (2026-08-02). Kolor, którego
            znaczenie siedzi w `title`, na telefonie nie znaczy nic — a to
            pierwsza rzecz, którą oko widzi w każdym wierszu. */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-[11px] text-faint">
          {/* „PRZEWAGA W KURSIE" TŁUMACZYŁO ŻARGON ŻARGONEM (2026-08-04).
              To jedyne miejsce, które ma wyjaśnić symbol widoczny w KAŻDYM
              wierszu — a samo wymagało wyjaśnienia. Nowe zdanie mówi, co ta
              kropka znaczy dla pieniędzy, bez ani jednego słowa z branży. */}
          {/* SŁOWO „PRZEWAGA" DEFINIUJEMY TAM, GDZIE PADA PIERWSZY RAZ
              (2026-08-05). Legenda tłumaczyła kropkę, nie używając tego słowa,
              a etykiety tuż obok mówią „duża przewaga / przewaga / cienka
              przewaga" — czyli czytelnik dostawał termin bez definicji dwa
              centymetry od jego wyjaśnienia. W całym produkcie „przewaga"
              znaczy odtąd DOKŁADNIE jedno: bukmacher płaci więcej, niż wynika
              z naszej szansy. Na liście meczów to samo słowo znaczyło „brak
              typu" — poprawione osobno (TerminarzMeczy). */}
          <span className="uppercase tracking-widest">
            kropka = przewaga, czyli ile bukmacher przepłaca
          </span>
          {/* CO ZNACZĄ DWIE LICZBY PO PRAWEJ (2026-08-04). Wiersz kończy się
              „91%  1,34" i nigdzie nie było napisane, że pierwsza to nasza
              szansa, a druga kurs bukmachera. Dla kogoś, kto nie zna zakładów,
              to dwie liczby bez etykiet — a to one decydują o wyborze typu. */}
          <span className="flex items-center gap-1.5">
            <span className="font-data font-semibold text-brand-deep">91%</span>
            <span>nasza szansa</span>
            <span className="font-data font-semibold text-ink-soft">1,34</span>
            <span>kurs</span>
          </span>
          {PRZEWAGA_KROPKI.map((k) => (
            <span key={k.kod} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className={`h-2 w-2 shrink-0 rounded-full ${KROPKA_STYL[k.kod]}`}
              />
              {k.label}
            </span>
          ))}
        </div>
      </div>

      {widoczne.length === 0 ? (
        // ROZRÓŻNIAMY DWA POWODY PUSTKI. „Zdejmij filtr" przy nieustawionym
        // filtrze wyglądałoby na awarię — a to zwykle znaczy, że wszystkie
        // mecze zdążyły się zacząć, odkąd strona została zbudowana.
        <p className="mt-8 text-sm text-muted">
          {bets.length === 0 && wszystkie.length > 0
            ? "Wszystkie mecze z tej listy już się zaczęły. Nowe typy pojawią się po najbliższym przeliczeniu."
            : "Brak typów dla tych filtrów. Zdejmij filtr, żeby zobaczyć całą listę."}
        </p>
      ) : (
        <>
          {/* GŁÓWNY ELEMENT: dzisiejsza tablica – karty top 3 + sortowalna
              ceduła dnia przycięta do LIMIT_DZIS wierszy */}
          {/* dziś bez typów: jedna cicha linia zamiast znikającej sekcji –
              strona nie wygląda na zepsutą, gdy terminarz ma dziurę */}
          {dzisiejsze.length === 0 && (jutro || dalszy) && (
            <div className="mt-7">
              <div className="flex items-baseline gap-x-3 border-t-2 border-ink pt-2.5">
                <h2 className="font-display text-xl font-bold uppercase leading-none tracking-tight">
                  dziś
                </h2>
                <span className="hidden text-xs text-faint sm:inline">
                  {etykietaDnia(teraz, teraz).data}
                </span>
              </div>
              {/* PUSTY DZIEŃ TO CECHA, NIE AWARIA (2026-08-02). Poprzednia
                  wersja brzmiała jak przeprosiny za brak towaru. Ta mówi, że
                  mamy próg i że go trzymamy — a to jest argument sprzedażowy,
                  nie usprawiedliwienie. */}
              <p className="mt-2 text-sm text-muted">
                Dziś żaden typ nie przeszedł naszych progów. Kolejne mecze
                znajdziesz niżej{jutro ? ", pierwsze już jutro" : ""}.
              </p>
              <CzemuTyleDzis meczeDzis={meczeDzis} meczeJutro={meczeJutro} />
            </div>
          )}

          {dzisiejsze.length > 0 && (
            <section aria-label="Typy na dziś" className="mt-7">
              <div className="flex items-baseline gap-x-3 border-t-2 border-ink pt-2.5">
                <h2 className="font-display text-xl font-bold uppercase leading-none tracking-tight">
                  dziś
                </h2>
                <span className="hidden text-xs text-faint sm:inline">
                  {etykietaDnia(teraz, teraz).data}
                </span>
                <span className="ml-auto shrink-0 font-data text-xs text-muted">
                  {odmienTypy(dzisiejsze.length)}
                </span>
              </div>
              {/* dzień z małą liczbą typów tłumaczy się terminarzem, zamiast
                  zostawiać wrażenie, że model dziś nic nie znalazł */}
              {dzisiejsze.length < PROG_SEKCJI_TOP && (
                <CzemuTyleDzis meczeDzis={meczeDzis} meczeJutro={meczeJutro} />
              )}
              <JedenZaklad lista={dzisiejsze} />

              {top.length > 0 && (
                <div className="mt-4 space-y-4">
                  {top.map((bet, i) => {
                    const karta = (
                      <BetCard
                        bet={bet}
                        rank={i + 1}
                        zawodnik={
                          // BetCard czyta z tego obiektu wyłącznie `forma` –
                          // kształt DruzynaForma celowo pokrywa potrzebne pola
                          formaById.get(bet.podmiot_id) as unknown as
                            | Zawodnik
                            | undefined
                        }
                        warianty={wariantyById.get(bet.id)}
                      />
                    );
                    return (
                      <Reveal key={bet.id} delay={Math.min(i * 0.05, 0.2)}>
                        {/* pierwsza karta dnia wygląda jak pierwsza — ale
                            tylko przy naszej kolejności („polecane"), bo przy
                            sortowaniu po kursie numer 1 nic nie znaczy */}
                        {i === 0 && sort === "rank" ? (
                          <Wyrozniona etykieta="nasz typ numer 1 na dziś">
                            {karta}
                          </Wyrozniona>
                        ) : (
                          karta
                        )}
                      </Reveal>
                    );
                  })}
                </div>
              )}

              {cedulaDzis.length > 0 && (
                <div className="mt-5">
                  <BetRowNaglowek />
                  {cedulaDzis.slice(0, LIMIT_DZIS).map((b) => wiersz(b, true))}
                  {cedulaDzis.length > LIMIT_DZIS && (
                    <>
                      <Rozwin open={calyDzis}>
                        <div>
                          {cedulaDzis.slice(LIMIT_DZIS).map((b) => wiersz(b, true))}
                        </div>
                      </Rozwin>
                      <PokazButton
                        open={calyDzis}
                        ukryte={cedulaDzis.length - LIMIT_DZIS}
                        zwinLabel="zwiń listę dnia"
                        onClick={() => setCalyDzis((v) => !v)}
                      />
                    </>
                  )}
                </div>
              )}
            </section>
          )}

          {(jutro || dalszy) && (
            <section aria-label="Typy na kolejne dni" className="mt-10">
              <h2 className="flex items-center gap-2.5 font-body text-xs font-semibold uppercase tracking-widest text-muted">
                <span aria-hidden className="h-px w-6 bg-hairline" />
                Kolejne dni
              </h2>

              {jutro && blokDnia(jutro)}

              {/* slot dalszych dni: kafelki wyboru + jeden widoczny dzień –
                  liczba sekcji strony stała niezależnie od terminarza */}
              {dalsze.length > 1 && (
                <div
                  role="group"
                  aria-label="Wybierz dzień"
                  className="-mx-1 mt-7 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none] sm:flex-wrap"
                >
                  {dalsze.map((d) => {
                    const et = etykietaDnia(d.lista[0].kickoff_ts, teraz);
                    const aktywny = d.klucz === dalszyKlucz;
                    return (
                      <button
                        key={d.klucz}
                        onClick={() => setWybranyDzien(d.klucz)}
                        aria-pressed={aktywny}
                        className={`shrink-0 rounded-(--radius-control) border px-3 py-1.5 text-left transition-colors ${
                          aktywny
                            ? "border-brand bg-brand-wash"
                            : "border-hairline hover:border-hairline-strong"
                        }`}
                      >
                        <span
                          className={`block text-[11px] font-semibold uppercase tracking-wide ${
                            aktywny ? "text-brand-deep" : "text-ink"
                          }`}
                        >
                          {et.glowna}
                        </span>
                        <span
                          className={`font-data block text-[10px] ${
                            aktywny ? "text-brand-deep/80" : "text-faint"
                          }`}
                        >
                          {dataKrotka(d.lista[0].kickoff_ts)} · {d.lista.length}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              {dalszy && blokDnia(dalszy)}
            </section>
          )}
        </>
      )}
    </div>
  );
}
