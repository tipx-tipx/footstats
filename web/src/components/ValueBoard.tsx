"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

import { BetCard } from "./BetCard";
import { FilterDropdown } from "./FilterDropdown";
import { RadarCard } from "./RadarCard";
import { StsBetCard } from "./StsBetCard";
import { Wyrozniona } from "./Wyrozniona";
import { fmtDataCzas } from "@/lib/format";
import { grupujWarianty } from "@/lib/warianty";
import { useTeraz } from "@/lib/useTeraz";
import type {
  Meta,
  Pewnosc,
  RadarWpis,
  StsAlert,
  ValueBet,
  Zawodnik,
} from "@/lib/types";

const RYNKI_FILTRY: { kod: string; label: string }[] = [
  { kod: "wszystkie", label: "Wszystkie rynki" },
  { kod: "shots", label: "Strzały" },
  { kod: "sot", label: "Strzały celne" },
  { kod: "fouls_committed", label: "Faule" },
  { kod: "fouls_won", label: "Faule wywalczone" },
  { kod: "interceptions", label: "Przechwyty" },
  { kod: "shots_outside_box", label: "Zza pola karnego" },
  { kod: "fh_shots", label: "Strzały 1. połowa" },
  { kod: "yellow_card", label: "Żółte kartki" },
  { kod: "shots_off_target", label: "Strzały niecelne" },
  { kod: "shots_blocked", label: "Strzały zablokowane" },
  { kod: "druzyny", label: "Rynki drużynowe" },
  { kod: "inne", label: "Pozostałe" },
];
const GLOWNE_KODY = new Set(RYNKI_FILTRY.map((r) => r.kod));

const PEWNOSC_FILTRY: { kod: Pewnosc | "kazda"; label: string }[] = [
  { kod: "kazda", label: "Każda" },
  { kod: "srednia", label: "Średnia i wyższa" },
  { kod: "wysoka", label: "Tylko wysoka" },
];

type SortKey = "ranking" | "pewnosc" | "kickoff" | "kurs";

/**
 * Sortowanie zakładki Drabinki – inne pytania niż przy typach modelu.
 * "najlepsze" = ranking z backendu (ocena.miejsce): przewaga nad kursem po
 * korekcie na rywala, sędziego i scenariusz meczu.
 */
type SortDrabinki = "najlepsze" | "szansa" | "kurs" | "kickoff";

/** Ile kart drabinek pokazujemy dziennie (decyzja usera 2026-08-01). */
const DRABINKI_MAX = 10;

const SORTOWANIA_DRABINKI: { kod: SortDrabinki; label: string }[] = [
  { kod: "najlepsze", label: "Najlepsze typy" },
  { kod: "szansa", label: "Największa szansa" },
  { kod: "kurs", label: "Najwyższy kurs" },
  { kod: "kickoff", label: "Najbliższy mecz" },
];

// Kolejność wejściowa bets = ranking silnika (szansa × kurs + kontekst:
// matchup, świeże składy, miękka linia) – to jest "Polecane".
//
// NIE MA SORTOWANIA PO WARTOŚCI (2026-08-13). Stało tu „Największa przewaga
// nad kursem". Dwa powody, oba zmierzone: (1) odkąd szansa na karcie jest
// ściągana do uczciwej ceny, wartość netto to praktycznie marża plus podatek,
// więc sortowanie ustawiało typy po cenie, a nie po jakości; (2) sortowanie po
// DEKLAROWANEJ przewadze działa odwrotnie, niż wygląda – górna jedna trzecia
// dawała −41,2%, dolna +32,5% (pomiar na 114 rozliczeniach). Wynoszenie na
// górę największego rozjazdu z kursem to przepis na wybranie najgorszych.
const SORTOWANIA: { kod: SortKey; label: string }[] = [
  { kod: "ranking", label: "Polecane przez model" },
  { kod: "pewnosc", label: "Największa szansa trafienia" },
  { kod: "kurs", label: "Najwyższy kurs" },
  { kod: "kickoff", label: "Najbliższy mecz" },
];
/** Ile czasu temu był skan STS (liczone po stronie klienta – patrz useEffect). */
function odswiezTemu(ts?: number): { label: string; minuty: number } | null {
  if (!ts) return null;
  const minuty = Math.max(0, Math.floor((Date.now() / 1000 - ts) / 60));
  const label =
    minuty < 1
      ? "przed chwilą"
      : minuty < 60
        ? `${minuty} min temu`
        : minuty < 1440
          ? `${Math.round(minuty / 60)} h temu`
          : `${Math.round(minuty / 1440)} dni temu`;
  return { label, minuty };
}

/** Powyżej tylu minut skan uznajemy za nieświeży (kurs STS mógł się ruszyć). */
const STS_STALE_MIN = 45;

/** Poprawna polska odmiana: "1 pozycja", "3 pozycje", "8 pozycji". */
function odmienPozycje(n: number): string {
  if (n === 1) return "1 pozycja";
  const r10 = n % 10;
  const r100 = n % 100;
  const kilka = r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14);
  return `${n} ${kilka ? "pozycje" : "pozycji"}`;
}


export function ValueBoard({
  bets: wszystkieBets,
  stsAlerty = [],
  stsGeneratedTs,
  radarWpisy: wszystkieRadar = [],
  zawodnicy,
  initialMatchId,
  initialRodzaj,
  teraz: terazSerwera,
}: {
  bets: ValueBet[];
  stsAlerty?: StsAlert[];
  stsGeneratedTs?: number;
  radarWpisy?: RadarWpis[];
  zawodnicy: Zawodnik[];
  initialMatchId?: number;
  initialRodzaj?:
    | "pewniaki"
    | "wyzsze_kursy"
    | "value"
    | "radar"
    | "wszystko";
  /** znacznik serwera (s) – wartość startowa dla zegara przeglądarki */
  teraz: number;
}) {
  // ZEGAR PRZEGLĄDARKI, nie chwila zbudowania strony. Strona bywa oddana
  // z cache sprzed godzin, a wtedy serwerowe odcięcie „mecz się zaczął"
  // (lib/data.tylkoNadchodzace) jest równie stare co ona i rozegrane mecze
  // wiszą na liście do ręcznego odświeżenia (zgłoszenie usera 2026-08-02).
  const teraz = useTeraz(terazSerwera);
  const bets = useMemo(
    () => wszystkieBets.filter((b) => b.kickoff_ts > teraz),
    [wszystkieBets, teraz],
  );
  const radarWpisy = useMemo(
    () => wszystkieRadar.filter((w) => w.kickoff_ts > teraz),
    [wszystkieRadar, teraz],
  );
  const [rynek, setRynek] = useState("wszystkie");
  const [pewnosc, setPewnosc] = useState<Pewnosc | "kazda">("kazda");
  const [meczId, setMeczId] = useState<number | undefined>(initialMatchId);
  // Pewniaki pierwsze i domyślne (user wybiera z nich legi na kupony);
  // domyślny sort = ranking silnika ("Polecane") – samo p_model wynosiłoby
  // na górę zawsze linie 0,5 gwiazd i chowało typy kontekstowe (matchup)
  const [rodzaj, setRodzaj] = useState<
    "pewniaki" | "wyzsze_kursy" | "value" | "radar" | "wszystko"
  >(
    // Zakładka „Wszystko" USUNIĘTA (decyzja usera 2026-08-01): dublowała
    // pozostałe, a przy zawodnikach w kwarantannie pokazywała to samo co
    // Drabinki. Domyślnie wchodzimy na pierwszą, która ma zawartość.
    () =>
      initialRodzaj ??
      (bets.some((b) => b.pewniak)
        ? "pewniaki"
        : radarWpisy.length > 0
          ? "radar"
          : "pewniaki"),
  );
  const [sortuj, setSortuj] = useState<SortKey>("ranking");
  const [limit, setLimit] = useState(25);
  // KONSOLA FILTRÓW PRZY LIŚCIE NA JEDNĄ POZYCJĘ (2026-08-06). Cztery
  // rozwijane pola zajmowały na telefonie pół pierwszego ekranu po to, żeby
  // przefiltrować JEDEN typ — a strumień zawodniczy bywa jednoelementowy
  // tygodniami. Filtry nie znikają, tylko czekają za jednym kliknięciem.
  const [filtryOtwarte, setFiltryOtwarte] = useState(false);
  // Drabinki: sortowanie osobne od typów modelu (inne pola, inne pytania).
  // Domyślnie „najlepsze" – kolejność z backendu (ocena.miejsce), bo to
  // JEDYNA definicja jakości karty w całym systemie. Przy sortowaniu po
  // jakości lista jest PŁASKA: grupowanie po meczach chowałoby ranking,
  // bo najlepsza karta dnia lądowałaby w środku listy pod nazwą meczu.
  const [sortDrabinki, setSortDrabinki] = useState<SortDrabinki>("najlepsze");
  // MAX 10 KART DZIENNIE (decyzja usera 2026-08-01). Wybieramy je ZAWSZE po
  // `ocena.miejsce` – to backendowy ranking przewagi nad kursem po korekcie na
  // rywala, sędziego i scenariusz meczu, czyli jedyna definicja „najbardziej
  // value" w systemie. Sortowanie z rozwijanej listy działa DOPIERO na tej
  // dziesiątce: user zmienia kolejność patrzenia, a nie to, które karty
  // w ogóle wchodzą. Inaczej „najwyższy kurs" wciągałby karty z gorszą
  // analizą tylko dlatego, że mają grubszą cenę.
  const radarNajlepsze = useMemo(
    () =>
      [...radarWpisy]
        .sort((a, b) => (a.ocena?.miejsce ?? 9999) - (b.ocena?.miejsce ?? 9999))
        .slice(0, DRABINKI_MAX),
    [radarWpisy],
  );
  const radarPosortowane = useMemo(() => {
    const w = [...radarNajlepsze];
    switch (sortDrabinki) {
      case "najlepsze":
        w.sort(
          (a, b) => (a.ocena?.miejsce ?? 9999) - (b.ocena?.miejsce ?? 9999),
        );
        break;
      case "szansa":
        w.sort((a, b) => (b.ocena?.p_final ?? 0) - (a.ocena?.p_final ?? 0));
        break;
      case "kurs":
        w.sort((a, b) => (b.hero?.kurs ?? 0) - (a.hero?.kurs ?? 0));
        break;
      case "kickoff":
        w.sort(
          (a, b) =>
            a.kickoff_ts - b.kickoff_ts ||
            (a.ocena?.miejsce ?? 9999) - (b.ocena?.miejsce ?? 9999),
        );
        break;
    }
    return w;
  }, [radarNajlepsze, sortDrabinki]);

  /**
   * ILE DRABINEK POKAZUJEMY OD RAZU (2026-08-05).
   *
   * Zmierzone zrzutem tego dnia: zakładka miała **4605 px na laptopie
   * i 6979 px na telefonie** — dziesięć kart po ~260 px jedna pod drugą.
   * Karta jest gęsta i user ją chwali, więc NIE skracamy karty (drabinka jest
   * jej treścią, patrz RadarCard); skracamy LISTĘ. Pięć kart to jeden ekran
   * laptopa i dwa telefonu, a reszta jest o jedno kliknięcie.
   *
   * Świadomie tylko w widoku rankingowym: przy sortowaniu chronologicznym
   * karty są pogrupowane po meczach i ucięcie w połowie grupy myliłoby
   * bardziej, niż pomaga.
   */
  const LIMIT_DRABINEK = 5;
  const [wszystkieDrabinki, setWszystkieDrabinki] = useState(false);
  const radarPokazane = wszystkieDrabinki
    ? radarPosortowane
    : radarPosortowane.slice(0, LIMIT_DRABINEK);
  // Grupowanie po meczach ma sens WYŁĄCZNIE przy sortowaniu chronologicznym
  // (backend sortuje wtedy chronologicznie, w meczu po jakości). Filtr „tylko
  // sygnały" USUNIĘTY 2026-07-25: odkąd każda karta musi przejść te same
  // twarde bramy, etykieta transfer/forma mówi tylko, dlaczego zwróciliśmy
  // uwagę na gracza – nie ile karta jest warta.
  const radarGrupy = useMemo(() => {
    const grupy = new Map<
      number,
      { mecz: string; kickoff_ts: number; wpisy: RadarWpis[] }
    >();
    for (const w of radarPosortowane) {
      const g = grupy.get(w.mecz_id);
      if (g) g.wpisy.push(w);
      else
        grupy.set(w.mecz_id, {
          mecz: w.mecz,
          kickoff_ts: w.kickoff_ts,
          wpisy: [w],
        });
    }
    return [...grupy.values()];
  }, [radarPosortowane]);
  // świeżość skanu STS liczona PO stronie klienta (po mount), żeby Date.now()
  // nie rozjechał SSR/hydracji – do mount pole zostaje puste
  const [swiezosc, setSwiezosc] = useState<ReturnType<typeof odswiezTemu>>(null);
  useEffect(() => {
    setSwiezosc(odswiezTemu(stsGeneratedTs));
  }, [stsGeneratedTs]);

  const liczbaValueSts = stsAlerty.length;
  // PÓŁKI LISTY DNIA (backend `uczony.POLKI`, wpięte 2026-08-20). Doba dzieli
  // się na dwa budżety: 15 typów o kursach 1,20–1,80 i 6 o kursach 1,80–2,20.
  //
  // ⚑ ODPORNIE NA BRAK POLA. Typy sprzed wdrożenia nie mają `polka`, a lista
  // niesie też wznowione sprzed tygodnia — dla nich zostaje stara flaga
  // `pewniak`, żeby zakładka nie zgubiła typu, który user już widział.
  //
  // ⚑ ...ALE FLAGA NIE MOŻE AWANSOWAĆ TYPU SPOZA WIDEŁEK (naprawa 2026-08-21).
  // `pewniak` powstała, zanim doba dzieliła się na półki, i nie zna sufitu
  // kursu (2,00 dla drużyn, 2,20 dla zawodników). Zmierzone na produkcji
  // z 21.08: osiem wznowionych typów o kursach 2,12–2,60 stało w zakładce
  // „Wysokie szanse" — czyli dokładnie odwrotnie, niż ta zakładka obiecuje.
  // Po naprawie backendu (`wybierz_liste_publikowana` nadaje półkę także
  // w dobie domkniętej) brak `polka` znaczy już tylko jedno: typ jest POZA
  // produktem półkowym. Wtedy zostaje w zakładce ze wszystkimi typami.
  const KURS_MAX_PEWNIAKA = 1.8;
  const wWysokiejSzansie = (b: ValueBet) =>
    b.polka
      ? b.polka === "wysoka_szansa"
      : !!b.pewniak && (b.kurs ?? 0) < KURS_MAX_PEWNIAKA;
  const liczbaPewniakow = useMemo(
    () => bets.filter(wWysokiejSzansie).length,
    [bets],
  );
  const liczbaWyzszychKursow = useMemo(
    () => bets.filter((b) => b.polka === "wyzsze_kursy").length,
    [bets],
  );

  const zawodnikById = useMemo(
    () => new Map(zawodnicy.map((z) => [z.id, z])),
    [zawodnicy],
  );

  const mecze = useMemo(() => {
    const seen = new Map<number, string>();
    for (const b of bets) if (!seen.has(b.mecz_id)) seen.set(b.mecz_id, b.mecz);
    return [...seen.entries()];
  }, [bets]);

  // liczba pozycji per rynek (przy aktywnym rodzaju) – do etykiet filtra
  const liczbaPerRynek = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of bets) {
      if (rodzaj === "pewniaki" && !wWysokiejSzansie(b)) continue;
      if (rodzaj === "wyzsze_kursy" && b.polka !== "wyzsze_kursy") continue;
      let kod = b.rynek_kod;
      if (b.rynek_kod.startsWith("team_")) kod = "druzyny";
      else if (!GLOWNE_KODY.has(b.rynek_kod)) kod = "inne";
      m.set(kod, (m.get(kod) ?? 0) + 1);
      m.set("wszystkie", (m.get("wszystkie") ?? 0) + 1);
    }
    return m;
  }, [bets, rodzaj]);

  const wyczyscFiltry = () => {
    setRynek("wszystkie");
    setPewnosc("kazda");
    setMeczId(undefined);
    setSortuj("ranking"); // spójnie ze stanem początkowym
  };

  const dostepneSorty = SORTOWANIA;

  const filtered = useMemo(() => {
    const wynik = bets.filter((b) => {
      if (rynek === "druzyny" && !b.rynek_kod.startsWith("team_")) return false;
      if (
        rynek === "inne" &&
        (GLOWNE_KODY.has(b.rynek_kod) || b.rynek_kod.startsWith("team_"))
      )
        return false;
      if (
        rynek !== "wszystkie" &&
        rynek !== "inne" &&
        rynek !== "druzyny" &&
        b.rynek_kod !== rynek
      )
        return false;
      if (rodzaj === "pewniaki" && !wWysokiejSzansie(b)) return false;
      if (rodzaj === "wyzsze_kursy" && b.polka !== "wyzsze_kursy")
        return false;
      if (pewnosc === "wysoka" && b.pewnosc !== "wysoka") return false;
      if (pewnosc === "srednia" && b.pewnosc === "niska") return false;
      if (meczId !== undefined && b.mecz_id !== meczId) return false;
      return true;
    });
    // kolejność wejściowa = ranking silnika ("Polecane"); sort jest stabilny,
    // więc remisy każdego kryterium zachowują tę kolejność – m.in. przy
    // "najbliższym meczu" typy w obrębie meczu idą od najlepiej ocenianych
    switch (sortuj) {
      case "pewnosc":
        // "największa szansa" = liczba, którą user widzi na karcie
        wynik.sort((a, b) => b.p_model - a.p_model);
        break;
      case "kickoff":
        wynik.sort((a, b) => a.kickoff_ts - b.kickoff_ts);
        break;
      case "kurs":
        wynik.sort((a, b) => (b.kurs ?? 0) - (a.kurs ?? 0));
        break;
    }
    return wynik;
  }, [bets, rynek, pewnosc, meczId, rodzaj, sortuj]);

  // JEDNA KARTA NA TYP, NIE NA LINIĘ (2026-08-01, zgłoszenie usera). Trzy
  // karty „rożne poniżej 4,5 / 5,5 / 6,5" tej samej drużyny wyglądały jak trzy
  // pomysły; to jeden pomysł na trzech poprzeczkach. Grupujemy PO filtrach
  // i PRZED limitem, żeby „pokaż więcej" liczyło karty, a nie linie.
  const grupy = useMemo(() => grupujWarianty(filtered), [filtered]);
  const shown = grupy.slice(0, limit);

  // Filtry chowamy TYLKO wtedy, gdy naprawdę nie mają czego filtrować:
  // lista jest krótka i żaden filtr nie jest ustawiony. Gdyby warunek nie
  // patrzył na stan filtrów, panel znikałby użytkownikowi spod palca
  // w chwili, gdy jego własny wybór zawęzi listę do jednej pozycji.
  const malaLista =
    grupy.length <= 2 &&
    rynek === "wszystkie" &&
    pewnosc === "kazda" &&
    meczId === undefined &&
    sortuj === "ranking";

  // Kotwica ze spotlightu Hero (link „…#bet-<id>”): po wejściu na stronę
  // przewiń do wskazanej karty. Zakładkę ustawia initialRodzaj z ?rodzaj=,
  // a key na ValueBoard (page.tsx) wymusza remont, więc karta jest już w DOM.
  useEffect(() => {
    const scrollToHash = () => {
      const h = window.location.hash;
      if (!/^#bet-\d+$/.test(h)) return;
      const el = document.querySelector(h);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    };
    scrollToHash();
    window.addEventListener("hashchange", scrollToHash);
    return () => window.removeEventListener("hashchange", scrollToHash);
  }, []);

  // zakładki "rodzaj": role=tab wymaga obsługi strzałek (WAI-ARIA Tabs) –
  // roving tabindex, Left/Right/Home/End przenoszą FOKUS I WYBÓR
  // Value Bety STS to skan ODPALANY RĘCZNIE (dwuklik odswiez-sts.bat), więc
  // bywa pusty tygodniami – pusta zakładka tylko myliła. Chowamy ją, gdy nie
  // ma czego pokazać (chyba że user właśnie na niej stoi, żeby nie zniknęła
  // mu pod palcami po odświeżeniu danych).
  const TABY_RODZAJ = (
    [
      // „Pewniaki" -> „Wysokie szanse" (decyzja usera 2026-08-01): stare
      // słowo obiecywało pewność, której nie mamy, i kłóciło się z całą
      // resztą produktu, która mówi o szansach. Kod zakładki zostaje
      // („pewniaki" jedzie w adresie i w backendzie), zmienia się etykieta.
      ["pewniaki", "Wysokie szanse", liczbaPewniakow],
      // ⚑ DRUGA PÓŁKA (2026-08-20, zadanie 5 planu). Do dziś „Wysokie szanse"
      // i „value" pokazywały tę samą listę inaczej posortowaną — dwie
      // zakładki, jedna obietnica. Teraz każda ma własny budżet doby i własne
      // widełki kursu, więc różnią się SKŁADEM, nie kolejnością.
      ["wyzsze_kursy", "Wyższe kursy", liczbaWyzszychKursow],
      ["value", "Lepszy kurs w STS", liczbaValueSts],
      ["radar", "Drabinki", radarNajlepsze.length],
    ] as const
  ).filter(
    // Pusta zakładka tylko myli – chowamy ją, dopóki nie ma czego pokazać.
    // Dotyczy „Lepszy kurs w STS" (skan odpalany ręcznie, bywa pusty
    // tygodniami) ORAZ „Wysokie szanse" (decyzja usera 2026-08-01: rynki
    // zawodnicze potrafią stać puste, a pusta zakładka wygląda jak awaria).
    // Wyjątek: gdy user właśnie na niej stoi – inaczej zniknęłaby mu spod
    // palców przy odświeżeniu danych.
    // ...oraz „Wyższe kursy": do pierwszego cyklu po wdrożeniu półek żaden
    // typ nie ma jeszcze pola `polka`, więc zakładka byłaby pusta.
    ([kod, , liczba]) =>
      (kod !== "value" && kod !== "pewniaki" && kod !== "wyzsze_kursy") ||
      (liczba ?? 0) > 0 ||
      rodzaj === kod,
  );
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const wybierzRodzaj = (kod: (typeof TABY_RODZAJ)[number][0]) => {
    setRodzaj(kod);
  };
  const onTabKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    idx: number,
  ) => {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % TABY_RODZAJ.length;
    else if (e.key === "ArrowLeft") {
      next = (idx - 1 + TABY_RODZAJ.length) % TABY_RODZAJ.length;
    } else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABY_RODZAJ.length - 1;
    else return;
    e.preventDefault();
    wybierzRodzaj(TABY_RODZAJ[next][0]);
    tabRefs.current[next]?.focus();
  };

  return (
    <section aria-label="Lista okazji">
      {/* PASEK ZAKŁADEK POKAZUJEMY DOPIERO OD DWÓCH (2026-08-06).
          Typy zawodnicze potrafią stać puste tygodniami — wtedy zostawała
          jedna zakładka „Drabinki 8", a pasek z jedną pozycją wygląda jak
          interfejs, któremu coś się nie doładowało. Przy jednej zakładce
          zamiast paska idzie zwykły nagłówek sekcji (niżej). */}
      {TABY_RODZAJ.length > 1 && (
        <div
          className="flex flex-wrap items-end gap-x-6 gap-y-1 border-b border-hairline"
          role="tablist"
          aria-label="Rodzaj pozycji"
        >
          {TABY_RODZAJ.map(([kod, label, liczba], i) => (
            <button
              key={kod}
              ref={(el) => { tabRefs.current[i] = el; }}
              role="tab"
              tabIndex={rodzaj === kod ? 0 : -1}
              aria-selected={rodzaj === kod}
              onClick={() => wybierzRodzaj(kod)}
              onKeyDown={(e) => onTabKeyDown(e, i)}
              className={`font-display -mb-px inline-flex items-baseline gap-1.5 border-b-2 px-0.5 pb-2.5 pt-1 text-xs font-semibold uppercase tracking-wide transition-colors ${
                rodzaj === kod
                  ? "border-brand text-brand-deep"
                  : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {label}
              {liczba != null && (
                <span
                  className={`font-data text-[11px] ${
                    rodzaj === kod ? "" : "text-faint"
                  }`}
                >
                  {liczba}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* jedna zakładka = nagłówek sekcji zamiast paska (patrz wyżej) */}
      {TABY_RODZAJ.length === 1 && (
        <div className="flex items-baseline gap-x-3 border-b border-hairline pb-2.5">
          <h2 className="font-display text-xs font-semibold uppercase tracking-wide text-brand-deep">
            {TABY_RODZAJ[0][1]}
          </h2>
          {TABY_RODZAJ[0][2] != null && (
            <span className="font-data text-[11px] text-faint">
              {TABY_RODZAJ[0][2]} na dziś
            </span>
          )}
        </div>
      )}

      {rodzaj === "radar" ? (
        <div className="pt-4">
          {radarWpisy.length === 0 ? (
            <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-12 text-center shadow-(--shadow-card)">
              <p className="text-sm font-medium text-ink">
                Brak drabinek w tej chwili
              </p>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                Drabinka to jeden zawodnik na kilku poprzeczkach tej samej
                statystyki – na przykład „1 strzał”, „2 strzały” i „3 strzały”
                w tym samym meczu. Pokazujemy przy nich kursy, ostatnie mecze
                i to, ile podobnych statystyk dopuszcza rywal. Karty pojawiają
                się, gdy bukmacher wystawi kursy na zawodników – zwykle 1–2 dni
                przed meczem.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                {/* KRÓTKO I BEZ ŁAMAŃCÓW (2026-08-01, zgłoszenie usera).
                    Poprzedni wstęp miał pięć linijek, tłumaczył zapis „8/10"
                    i wyliczał składniki korekty – czyli mówił o kuchni, zanim
                    ktokolwiek zobaczył kartę. Do tego wąska kolumna obok
                    licznika łamała go w przypadkowych miejscach. */}
                {/* SŁOWO „DRABINKA" MUSI BYĆ WYJAŚNIONE PRZY PIERWSZYM UŻYCIU
                    (2026-08-05). Dotąd było wyłącznie etykietą zakładki i
                    nagłówkiem – ktoś, kto nie zna zakładów, nie miał skąd
                    wiedzieć, co kupuje. Definicja idzie z KONKRETNYM
                    przykładem, bo „kilka poprzeczek tej samej statystyki"
                    samo w sobie jest opisem dla kogoś, kto już wie. */}
                {/* JEDNO ZDANIE, RESZTA POD DYMKIEM (06.08). Wyjaśnienie
                    miało trzy linijki i stało między nagłówkiem a pierwszą
                    kartą — czyli dokładnie tam, gdzie czytelnik chce zobaczyć
                    typ, a nie czytać definicję. Definicja zostaje (słowo
                    „drabinka" musi być wyjaśnione przy pierwszym użyciu),
                    ale w jednym zdaniu; szczegóły czekają w dymku i tak samo
                    tłumaczy je każda karta niżej. */}
                <p
                  className="min-w-0 flex-1 text-xs leading-relaxed text-muted"
                  title="Im wyżej postawiona poprzeczka, tym wyższy kurs i mniejsza szansa. Przy każdej piszemy, ile razy zawodnik ją przebił w ostatnich meczach i jaką szansę dajemy na ten mecz."
                >
                  <span className="font-medium text-ink">
                    Drabinka to jeden zawodnik na kilku poprzeczkach tej samej
                    statystyki
                  </span>{" "}
                  – „1 strzał”, „2 strzały”, „3 strzały” w tym samym meczu.
                </p>
                <span className="font-data shrink-0 text-sm font-semibold text-brand-deep">
                  {odmienPozycje(radarNajlepsze.length)}
                </span>
              </div>

              {/* rozwijane pole rozciągało się na CAŁĄ szerokość listy —
                  wyglądało jak pasek narzędzi, a nie jak jeden wybór (06.08) */}
              <div className="mb-4 max-w-56">
                <FilterDropdown
                  label="Sortuj"
                  value={sortDrabinki}
                  options={SORTOWANIA_DRABINKI.map((s) => ({
                    value: s.kod,
                    label: s.label,
                  }))}
                  onChange={(v) => setSortDrabinki(v as SortDrabinki)}
                />
              </div>

              {sortDrabinki === "kickoff" ? (
                /* chronologicznie – karty pogrupowane po meczach */
                <div className="space-y-6">
                  {radarGrupy.map((g) => (
                    <section key={`${g.mecz}-${g.kickoff_ts}`}>
                      <div className="mb-2 flex items-baseline justify-between gap-3 border-b border-hairline pb-1.5">
                        <h3 className="min-w-0 truncate text-sm font-semibold text-ink">
                          {g.mecz}
                        </h3>
                        <span className="font-data shrink-0 text-xs text-muted">
                          {fmtDataCzas(g.kickoff_ts)}
                        </span>
                      </div>
                      <div className="space-y-3">
                        {g.wpisy.map((w, i) => (
                          <motion.div
                            key={w.id}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{
                              delay: Math.min(i * 0.03, 0.3),
                              duration: 0.3,
                            }}
                          >
                            <RadarCard w={w} />
                          </motion.div>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              ) : (
                /* ranking – lista płaska, bo to kolejność niesie informację */
                <div className="space-y-3">
                  {radarPokazane.map((w, i) => (
                    <motion.div
                      key={w.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        delay: Math.min(i * 0.03, 0.3),
                        duration: 0.3,
                      }}
                    >
                      {/* było 11 px w kolorze `faint` — nazwa meczu i godzina
                          to podstawowy kontekst typu, nie przypis (06.08) */}
                      <p className="mb-1.5 flex flex-wrap items-baseline gap-x-2 text-xs">
                        <span className="truncate font-medium text-ink-soft">
                          {w.mecz}
                        </span>
                        <span className="font-data text-faint">
                          {fmtDataCzas(w.kickoff_ts)}
                        </span>
                      </p>
                      {/* pierwsza karta wygląda jak pierwsza — ale tylko przy
                          sortowaniu po jakości (patrz `Wyrozniona`) */}
                      {i === 0 && sortDrabinki === "najlepsze" ? (
                        <Wyrozniona>
                          <RadarCard w={w} />
                        </Wyrozniona>
                      ) : (
                        <RadarCard w={w} />
                      )}
                    </motion.div>
                  ))}
                  {radarPosortowane.length > LIMIT_DRABINEK && (
                    <button
                      onClick={() => setWszystkieDrabinki((v) => !v)}
                      /* był drobnym szarym napisem pod listą i ginął —
                         to jedyne wyjście do POŁOWY kart dnia (06.08) */
                      className="font-display mt-3 inline-flex w-full items-center justify-center gap-2 rounded-(--radius-control) border border-hairline-strong bg-card px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-ink transition-colors hover:border-brand hover:text-brand sm:w-auto"
                    >
                      {wszystkieDrabinki
                        ? "Pokaż mniej"
                        : `Pokaż pozostałe drabinki (${radarPosortowane.length - LIMIT_DRABINEK})`}
                      <span
                        aria-hidden
                        className={wszystkieDrabinki ? "rotate-180" : ""}
                      >
                        ↓
                      </span>
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      ) : rodzaj === "value" ? (
        <div className="pt-4">
          {stsAlerty.length === 0 ? (
            <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-12 text-center shadow-(--shadow-card)">
              <p className="text-sm font-medium text-ink">
                W tej chwili nic tu nie ma
              </p>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                Szukamy tu typów, za które STS płaci wyraźnie więcej niż
                Superbet – a my dodatkowo uważamy, że mają szansę wejść. Takie
                różnice w kursach zdarzają się nieregularnie i znikają, gdy STS
                je zauważy.
              </p>
            </div>
          ) : (
            <>
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <p className="max-w-prose text-xs leading-relaxed text-muted">
                  Za te typy STS płaci więcej niż Superbet, a my uważamy, że
                  mają szansę wejść. Takie kursy szybko się zmieniają – jeśli
                  chcesz je zagrać, lepiej nie zwlekać.
                </p>
                <span className="font-data shrink-0 text-sm font-semibold text-brand-deep">
                  {odmienPozycje(stsAlerty.length)}
                </span>
              </div>
              {swiezosc && (
                <p className="mb-3 flex items-center gap-1.5 text-[11px] text-faint">
                  <span
                    aria-hidden
                    className={`h-1.5 w-1.5 rounded-full ${
                      swiezosc.minuty >= STS_STALE_MIN ? "bg-data-amber" : "bg-data-green"
                    }`}
                  />
                  kursy STS sprawdzone:{" "}
                  <span className="font-data text-muted">{swiezosc.label}</span>
                </p>
              )}
              {swiezosc && swiezosc.minuty >= STS_STALE_MIN && (
                <div className="mb-4 rounded-(--radius-control) border border-data-amber/30 bg-data-amber-wash px-3 py-2 text-xs leading-relaxed text-data-amber-ink">
                  Te kursy sprawdzaliśmy {swiezosc.label} – mogły się już
                  zmienić. Odśwież je na komputerze, żeby zobaczyć aktualne.
                </div>
              )}
              <div className="space-y-3">
                {stsAlerty.map((a, i) => (
                  <motion.div
                    key={`${a.zawodnik}-${a.rynek_kod}-${a.linia}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      delay: Math.min(i * 0.03, 0.4),
                      duration: 0.3,
                    }}
                  >
                    <StsBetCard a={a} rank={i + 1} />
                  </motion.div>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <>
      {/* konsola filtrów: dopracowane dropdowny + żywy odczyt wyniku */}
      {malaLista && !filtryOtwarte ? (
        <div className="mb-6 flex items-baseline justify-between gap-3 pt-4">
          <span className="text-sm text-muted">
            {grupy.length === 1
              ? "Dziś jedna pozycja w tym zestawieniu."
              : `Dziś ${odmienPozycje(grupy.length)} w tym zestawieniu.`}
          </span>
          {/* przy pustej liście filtrowanie nie ma czego filtrować — sam
              komunikat niżej tłumaczy, dlaczego jest pusto (06.08) */}
          {grupy.length > 0 && (
            <button
              onClick={() => setFiltryOtwarte(true)}
              className="shrink-0 whitespace-nowrap text-sm text-muted underline decoration-hairline-strong underline-offset-4 transition-colors hover:text-brand hover:decoration-brand"
            >
              pokaż filtry
            </button>
          )}
        </div>
      ) : (
      <div className="mb-6 grid grid-cols-2 items-end gap-x-6 gap-y-4 pt-4 lg:flex lg:gap-x-9">
        <FilterDropdown
          label="Rynek"
          value={rynek}
          onChange={setRynek}
          className="lg:w-48"
          options={RYNKI_FILTRY.map((r) => ({
            value: r.kod,
            label: r.label,
            n: liczbaPerRynek.get(r.kod) ?? 0,
          }))}
        />

        <FilterDropdown
          label="Pewność"
          value={pewnosc}
          onChange={(v) => setPewnosc(v as Pewnosc | "kazda")}
          className="lg:w-40"
          options={PEWNOSC_FILTRY.map((p) => ({ value: p.kod, label: p.label }))}
        />

        <FilterDropdown
          label="Mecz"
          value={meczId != null ? String(meczId) : ""}
          onChange={(v) => setMeczId(v ? Number(v) : undefined)}
          className="lg:w-56"
          options={[
            { value: "", label: "Wszystkie mecze" },
            ...mecze.map(([id, nazwa]) => ({
              value: String(id),
              label: nazwa,
            })),
          ]}
        />

        <FilterDropdown
          label="Sortuj"
          value={sortuj}
          onChange={(v) => setSortuj(v as SortKey)}
          className="lg:w-56"
          options={dostepneSorty.map((s) => ({ value: s.kod, label: s.label }))}
        />

        {/* żywy odczyt: liczba wjeżdża przy każdej zmianie filtrów */}
        <div
          aria-live="polite"
          className="col-span-2 flex items-baseline justify-between gap-2 lg:ml-auto lg:flex-col lg:items-end lg:justify-start lg:gap-1"
          title="Pozycje spełniające obecne filtry, najlepiej oceniane przez model najpierw"
        >
          <span className="text-[10px] font-semibold uppercase tracking-wide text-faint">
            wynik skanu
          </span>
          <motion.span
            key={grupy.length}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="font-data text-sm font-semibold text-brand-deep"
          >
            {odmienPozycje(grupy.length)}
          </motion.span>
        </div>
      </div>
      )}

      {filtered.length === 0 && (
        <div className="rounded-(--radius-card) border border-hairline bg-card px-6 py-12 text-center shadow-(--shadow-card)">
          {bets.length === 0 ? (
            // cała pula pusta (nie kwestia filtrów): dziś model nie wypuścił
            // ani jednego typu ZAWODNICZEGO – rynki drużynowe mają własną
            // stronę, a drabinki własną zakładkę. Bez tego użytkownik widzi
            // gołą pustkę i nie wie, że okazje w ogóle są.
            <>
              <p className="text-sm font-medium text-ink">
                Brak typów zawodniczych na te mecze
              </p>
              {/* ⚑ KOMUNIKAT O WSTRZYMANYCH RYNKACH ZDJĘTY (2026-08-14).
                  Stał tu tekst „do czasu poprawy ich nie typujemy" — prawdziwy
                  dopóty, dopóki kwarantanna zdejmowała typy z listy. Od 14.08
                  nie zdejmuje (backend: KWARANTANNA_ZDEJMUJE_Z_LISTY; pomiar
                  pokazał, że wstrzymane segmenty wypadały LEPIEJ niż to, co
                  zostawało na stronie), więc kwarantanna przestała być powodem
                  pustej listy — a tekst tłumaczyłby pustkę czymś, co się nie
                  wydarzyło.

                  Sam mechanizm nie zniknął i dalej o nim mówimy, tylko na
                  właściwej karcie („ostrożnie z tym zakładem" w `BetCard`) —
                  czyli przy konkretnym zakładzie, którego dotyczy, zamiast
                  w miejscu, gdzie ktoś szuka typów. */}
              <p className="mx-auto mt-1 max-w-lg text-xs leading-relaxed text-muted">
                Dziś nic nie przeszło naszych progów. Najczęstsze powody:
                Superbet nie wystawił jeszcze kursów na zawodników (robi to
                zwykle 1–2 dni przed meczem), zawodników nie ma w ogłoszonych
                składach, albo nasza szansa za mocno rozjeżdżała się z kursem
                – a wtedy z rozliczeń wychodzi, że to zwykle my się mylimy.
                Pusta lista to działające zabezpieczenie, nie awaria.
              </p>
              {/* Przycisk używa słowa „drabinki" w miejscu, w którym user
                  jeszcze go nie widział wyjaśnionego (pusta lista typów) —
                  więc wyjaśnienie idzie tuż nad nim, a nie dopiero po
                  kliknięciu (2026-08-05). */}
              {radarWpisy.length > 0 && (
                <p className="mx-auto mt-4 max-w-lg text-xs leading-relaxed text-muted">
                  Mamy za to <span className="font-medium text-ink">drabinki</span>:
                  jeden zawodnik na kilku poprzeczkach tej samej statystyki
                  („1 strzał”, „2 strzały”, „3 strzały”), z kursem i szansą przy
                  każdej.
                </p>
              )}
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {radarWpisy.length > 0 && (
                  <button
                    onClick={() => wybierzRodzaj("radar")}
                    className="rounded-(--radius-control) bg-brand px-4 py-2 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
                  >
                    Zobacz drabinki ({radarNajlepsze.length})
                  </button>
                )}
                <a
                  href="/druzyny"
                  className="rounded-(--radius-control) border border-hairline bg-paper px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-brand/40"
                >
                  Rynki drużynowe
                </a>
              </div>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-ink">
                Brak pozycji spełniających obecne filtry
              </p>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">
                Ustaw pewność na „Każda”, wybierz inny rynek albo mecz, albo
                zacznij od czysta.
              </p>
              <button
                onClick={wyczyscFiltry}
                className="mt-4 rounded-(--radius-control) bg-brand px-4 py-2 text-sm font-semibold text-on-brand shadow-(--shadow-card) transition-colors hover:bg-brand-strong"
              >
                Wyczyść filtry
              </button>
            </>
          )}
        </div>
      )}

      {/* lista kart typów */}
      {shown.length > 0 && (
      <div className="space-y-3">
        {shown.map(({ glowny, warianty }, i) => (
          <motion.div
            key={glowny.id}
            id={`bet-${glowny.id}`}
            className="scroll-mt-24"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.4), duration: 0.3 }}
          >
            {/* kotwice pozostałych linii grupy: link „…#bet-<id>" z Hero albo
                z czyjegoś zakładu musi trafić w kartę, choćby ta linia była
                dziś tylko szczeblem, a nie osobną kartą */}
            {warianty
              .filter((b) => b.id !== glowny.id)
              .map((b) => (
                <span key={b.id} id={`bet-${b.id}`} aria-hidden />
              ))}
            <BetCard
              bet={glowny}
              rank={i + 1}
              zawodnik={zawodnikById.get(glowny.podmiot_id)}
              warianty={warianty}
            />
          </motion.div>
        ))}
      </div>
      )}

      {grupy.length > limit && (
        <div className="mt-5 text-center">
          <button
            onClick={() => setLimit((l) => l + 25)}
            className="font-display inline-flex items-center gap-2 px-2 py-1 text-xs font-semibold uppercase tracking-widest text-muted transition-colors hover:text-brand"
          >
            Pokaż więcej
            <span className="font-data tracking-normal">
              ({grupy.length - limit} pozostało)
            </span>
            <span aria-hidden>↓</span>
          </button>
        </div>
      )}
        </>
      )}
    </section>
  );
}
