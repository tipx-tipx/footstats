"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { FormBars } from "./FormBars";
import { Krok, Kroki } from "./KrokiRozwiniecia";
import { fmtKurs, fmtProc } from "@/lib/format";
import {
  charakterSzczebla,
  kierunekMnoznika,
  klasaKierunku,
  miejsceWLidze,
  naMecz,
  trafioneZ,
} from "@/lib/slownik";
import type {
  RadarCzynnik,
  RadarKontekst,
  RadarRynek,
  RadarSezon,
  RadarWpis,
} from "@/lib/types";

/** Linia 0,5 to po ludzku „1 lub więcej" – tak mówi też Superbet. */
const linLabel = (linia: number) => `${Math.ceil(linia)}+`;

/**
 * Klasa karty (backend: radar._klasa_karty). NAZWY ZMIENIONE 2026-08-01:
 * „TOP / mocny / solidny" brzmiało jak ocena szkolna i zderzało się z drugą
 * skalą produktu (siła typu wg szansy, `lib/slownik.ts`). Klasa mierzy coś
 * innego – o ile nasza szansa bije cenę bukmachera – więc mówi to wprost.
 * `opis` jedzie NA STRONĘ, do rozwinięcia, a nie do dymka.
 */
const KLASY: Record<
  string,
  { label: string; badge: string; opis: string }
> = {
  top: {
    label: "największa przewaga dziś",
    badge: "bg-data-green text-white",
    opis: "Ze wszystkich dzisiejszych kart ta ma najwyższą przewagę nad kursem – po uwzględnieniu rywala, sędziego i przewidywanego przebiegu meczu. To nie jest gwarancja, tylko najlepsze, co dziś mamy.",
  },
  mocny: {
    label: "wyraźna przewaga",
    badge: "bg-data-green-wash text-data-green-ink",
    opis: "Nasza szansa wyraźnie bije cenę bukmachera, choć to nie jest czubek dzisiejszej stawki.",
  },
  solidny: {
    label: "niewielka przewaga",
    badge: "border border-hairline bg-paper text-muted",
    opis: "Przewaga nad kursem jest dodatnia, ale skromna. Karta przeszła nasze progi jakości i na tym koniec – nie obiecujemy tu nic więcej.",
  },
};

/**
 * NA CZYM STOI KARTA (backend: radar._kategoria_karty). Osobna oś od klasy
 * jakości: klasa mówi „jak dobry jest typ", kategoria – „na jakim dowodzie
 * stoi". Dlatego kategoria dostaje PASEK przy krawędzi karty, a nie kolejną
 * plakietkę obok klasy – inaczej nagłówek robi się jarmarkiem.
 */
const KATEGORIE: Record<
  string,
  { label: string; pasek: string; badge: string; opis: string }
> = {
  // OPISY W JEDNYM ZDANIU (2026-08-06, druga runda uwag usera): sekcja ceny
  // ma być najmniejszym priorytetem karty, więc każde wyjaśnienie mówi jedno
  // zdanie — kto chce więcej, ma „Pełny rachunek".
  analiza: {
    label: "tylko nasza analiza",
    pasek: "bg-hairline-strong",
    badge: "border border-hairline bg-paper text-muted",
    // NAZWA DRUGIEGO BUKMACHERA NIC TU NIE WNOSI (06.08). Czytelnik nie wie,
    // czym jest Betclic ani dlaczego ma go obchodzić — a zdanie i tak mówi
    // wszystko, co potrzebne: nie mamy z czym porównać naszej wyceny.
    opis: "Żaden inny bukmacher nie wystawił na to kursu, więc nie mamy z czym porównać naszej wyceny.",
  },
  rynek_zgodny: {
    label: "obaj bukmacherzy zgodni",
    pasek: "bg-brand-bright",
    badge: "bg-brand-wash text-brand-deep",
    opis: "Drugi bukmacher wycenia to niemal identycznie – to potwierdzenie naszej linii, nie okazja cenowa.",
  },
  rozjazd: {
    label: "jeden płaci więcej",
    pasek: "bg-data-amber",
    badge: "bg-data-amber-wash text-data-amber-ink",
    opis: "Za to samo zdarzenie jeden bukmacher płaci zauważalnie więcej – stawia się tam, gdzie płacą więcej.",
  },
  pewniak_taniej: {
    label: "drugi bukmacher: to niemal pewne",
    pasek: "bg-data-amber",
    badge: "bg-data-amber text-white",
    opis: "Jeden bukmacher wycenia to jako niemal pewne, a drugi płaci wyraźnie więcej – to opinia rynku, nie nasza gwarancja.",
  },
};

/** Mnożnik kontekstu jako zmiana procentowa: 0.8 -> „−20%". */
function pctZmiana(m?: number | null): string | null {
  if (m == null || Math.abs(m - 1) < 0.005) return null;
  const p = Math.round((m - 1) * 100);
  return `${p > 0 ? "+" : "−"}${Math.abs(p)}%`;
}

/** Krótkie polskie etykiety rynków w wierszach sezonowych. */
const SEZON_RYNKI_PL: Record<string, string> = {
  shots: "strzały",
  sot: "celne",
  shots_outside_box: "zza pola",
  fouls_committed: "faule",
  fouls_won: "faule wyw.",
  offsides: "spalone",
  tackles: "odbiory",
  interceptions: "przechwyty",
  shots_blocked: "zablokowane",
};

/** Liczba po polsku, bez ogona z zaokrągleń: 13.02 -> „13,0", 2 -> „2". */
const liczba = (v: number) =>
  (Number.isInteger(v) ? String(v) : v.toFixed(1)).replace(".", ",");

/** Plakietka sygnału – tylko dla wpisów Z SYGNAŁEM (zwykła drabinka bez). */
function sygnalInfo(
  w: RadarWpis,
): { label: string; dioda: string; badge: string; tytul: string } | null {
  if (w.rodzaj === "transfer") {
    return {
      label: "nowy w drużynie",
      dioda: "bg-brand",
      badge: "bg-brand-wash text-brand-deep",
      tytul:
        "Historia zawodnika pochodzi z innej ligi lub innego klubu. Kursy na takich graczy bywają niedograne, bo bukmacher ma mało danych z nowego miejsca.",
    };
  }
  if (w.rodzaj === "debiutant") {
    return {
      label: "debiutant",
      dioda: "bg-data-amber",
      badge: "bg-data-amber-wash text-data-amber-ink",
      tytul:
        "Superbet daje mu pełne kursy, ale w danych nie ma ani jednego jego meczu – rynek wycenia go w ciemno. Sprawdź sam, skąd przyszedł, zanim postawisz.",
    };
  }
  if (w.rodzaj === "forma") {
    return {
      label: "seria formy",
      dioda: "bg-data-green",
      badge: "bg-data-green-wash text-data-green-ink",
      tytul:
        "Zawodnik regularnie przebija linię w ostatnich meczach, wyraźnie ponad swój wcześniejszy poziom. Model celowo nie dolicza formy do szansy – to sygnał dodatkowy.",
    };
  }
  if (w.rodzaj === "bez_feedu") {
    return {
      label: "same kursy",
      dioda: "bg-ink/25",
      badge: "border border-hairline bg-paper text-muted",
      tytul:
        "Ta liga nie jest objęta feedem statystyk meczowych, więc nie mamy historii ostatnich występów. Pokazujemy kursy Superbetu, a tam gdzie się udało – średnie z całych sezonów.",
    };
  }
  return null;
}

/**
 * DRABINKA JAKO TREŚĆ KARTY, NIE UKRYTY DODATEK (przebudowa 2026-08-01).
 *
 * Zgłoszenie usera: karta drabinki wyglądała dokładnie jak każdy inny wiersz
 * typu – nazwisko, jedna linijka tekstu, strzałka „skąd ta liczba". To, co ją
 * wyróżnia, czyli KILKA POZIOMÓW TEJ SAMEJ RZECZY po różnych cenach, było
 * widoczne dopiero po rozwinięciu. Czyli sedno produktu chowało się za
 * kliknięciem.
 *
 * Teraz zwinięta karta pokazuje wprost to, po co się na nią patrzy:
 *   1+     2+     3+      <- szczeble drabinki
 *  1,18   1,56   2,90     <- ile płaci bukmacher za każdy
 *   92%    73%    38%     <- ile dajemy my
 * a pod spodem pasek ostatnich meczów: które przebiły wybraną linię.
 *
 * Wybrany szczebel (ten, który zdecydował o karcie) jest podświetlony – reszta
 * jest tłem, żeby dało się porównać cenę, a nie tylko przeczytać jedną liczbę.
 */
/** Czy karta pokaże pasek drabinki (a więc zajawka byłaby jego powtórzeniem). */
function maDrabinke(w: RadarWpis): boolean {
  const r = w.rynki?.find((x) => x.rynek_kod === w.hero?.rynek_kod) ?? w.rynki?.[0];
  return Boolean(w.hero) && (r?.drabinka?.length ?? 0) > 0;
}

/**
 * FAKTY KARTY — trzy liczby zamiast trzech przymiotników (2026-08-03).
 *
 * Zgłoszenie usera: „chodzi o proste oznaczenia typów — różnica kursów między
 * bukami, szansa na drugi szczebel — żeby to było ładne i intuicyjne".
 *
 * Karta mówiła dotąd przymiotnikami: „wyraźna przewaga", „jeden płaci więcej".
 * Przymiotnik wymaga zaufania — trzeba wiedzieć, co u nas znaczy „wyraźna".
 * Liczba nie wymaga niczego: „+41% u Betclica" rozumie każdy od razu. Dlatego
 * to NIE są kolejne plakietki oceny (zasada „najwyżej dwie" zostaje nietknięta
 * w nagłówku) — to jest wiersz faktów tuż nad drabinką, którą opisują.
 *
 * Trzy, w kolejności rzadkości: różnica kursów jest najrzadsza i najcenniejsza,
 * drugi szczebel decyduje, czy drabinkę da się rozegrać dalej niż o jeden
 * szczebel, pokrycie to baza całej analizy. Czego nie ma — tego nie pokazujemy,
 * zamiast wypisywać „brak".
 */
function Fakty({ w }: { w: RadarWpis }) {
  const r =
    w.rynki?.find((x) => x.rynek_kod === w.hero?.rynek_kod) ?? w.rynki?.[0];
  const drabinka = r?.drabinka ?? [];
  const i = drabinka.findIndex((s) => s.linia === w.hero?.linia);
  const drugi = i >= 0 ? drabinka[i + 1] : undefined;

  // różnica kursów: bierzemy tę przy linii, która wygrała kartę; gdy jej nie
  // ma — najlepszą z całej drabinki, bo i tak dotyczy tego samego zawodnika
  const roz =
    w.rozjazd_hero ??
    drabinka
      .map((s) => s.rozjazd)
      .filter(Boolean)
      .sort((a, b) => (b!.przewaga_pct ?? 0) - (a!.przewaga_pct ?? 0))[0];

  const fakty: { tekst: string; klasa: string }[] = [];
  // CHIP TYLKO PRZY RÓŻNICY, PO KTÓRĄ SIĘ SIĘGA — 12 PUNKTÓW SZANSY
  // (backend: radar.PROG_OKAZJI_PP). Mierzymy w punktach, nie w procentach
  // kursu, bo ten sam procent znaczy co innego przy różnych cenach: 25% to
  // 16,7 punktu przy 1,20/1,50 i tylko 5,0 punktu przy 4,00/5,00.
  // POKAZUJEMY za to procent, bo user myśli w kursach – miara decyzji i liczba
  // na ekranie to dwie różne rzeczy. Cena Betclica nie znika przy niższej
  // różnicy: dalej stoi przy szczeblu jako „BC 1,82".
  if (roz && (roz.roznica_pp ?? 0) >= 12) {
    fakty.push({
      // „gdzie" mówi, u KOGO jest lepsza cena — bez tego liczba wisi w próżni
      tekst: `+${Math.round(roz.przewaga_pct)}% u ${
        roz.gdzie === "betclic" ? "Betclica" : "Superbetu"
      }`,
      klasa: "bg-data-amber-wash text-data-amber-ink",
    });
  }
  if (drugi?.p_final != null) {
    fakty.push({
      // „szczebel" to nasze słowo na poprzeczkę drabinki (06.08)
      tekst: `druga poprzeczka ${fmtProc(drugi.p_final)}`,
      // ZIELEŃ NIESIE TU INFORMACJĘ, nie ozdabia: mówi, że drabinkę da się
      // rozegrać DALEJ NIŻ O JEDEN SZCZEBEL. Próg 0,40 jest ten sam, którym
      // backend przyznaje kształt „dwa_szczeble" (radar.PEWNA_MIN_P_DRUGI) —
      // dwie liczby w dwóch miejscach nie mogą mówić czego innego.
      // Poniżej progu szczebel zostaje na karcie (drabinka urywa się dopiero
      // pod 0,33 – radar.MIN_P_DRUGIEGO_SZCZEBLA, podniesione z 0,25 w dniu
      // 2026-08-08), ale ma być widać, że to już nie jest pewny dalszy ciąg.
      // PORÓWNUJEMY LICZBĘ, KTÓRĄ USER WIDZI, nie surową. p_final = 0,398
      // wyświetla się jako „40%", więc porównanie na surowej wartości dawało
      // chip z napisem „40%" pomalowany jak poniżej progu — etykieta mówiłaby
      // co innego niż kolor, a to najszybszy sposób na utratę zaufania do
      // obu naraz.
      klasa:
        Math.round(drugi.p_final * 100) >= 40
          ? "bg-data-green-wash text-data-green-ink"
          : "bg-paper text-ink-soft border border-hairline",
    });
  }
  if (w.hero?.z) {
    fakty.push({
      // „7/10 ostatnich" nie mówi, czego siedem z dziesięciu (06.08)
      tekst: `przebił w ${w.hero.traf} z ${w.hero.z} meczów`,
      klasa: "bg-paper text-ink-soft border border-hairline",
    });
  }
  if (!fakty.length) return null;

  return (
    <span className="mx-4 mb-1.5 flex flex-wrap items-center gap-1.5 sm:mx-5">
      {fakty.map((f) => (
        <span
          key={f.tekst}
          className={`font-data inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${f.klasa}`}
        >
          {f.tekst}
        </span>
      ))}
    </span>
  );
}

/**
 * HISTORIA JAKO WYKRES, NIE DZIESIĘĆ RÓWNYCH KRESEK (2026-08-01, część 2).
 *
 * Zgłoszenie usera: „wykres ten x z 10 weszło jest słaby, nierówny". I był:
 * dziesięć identycznych kresek 6 × 14 px, pomalowanych na dwa kolory. Taki
 * pasek mówi wyłącznie „tak / nie", więc mecz z pięcioma strzałami wyglądał
 * dokładnie tak samo jak mecz z jednym. Do tego przy krótszej historii kresek
 * bywało siedem zamiast dziesięciu i pasek kończył się w przypadkowym miejscu.
 *
 * Teraz to prawdziwy wykres: wysokość słupka niesie LICZBĘ zdarzeń, przerywana
 * linia pokazuje poprzeczkę zakładu, a słupki dzielą szerokość równo, więc
 * pasek zawsze dochodzi do prawej krawędzi. Wszystko na `span`-ach, bo ten
 * blok siedzi w środku przycisku rozwijającego kartę.
 */
function HistoriaSparkline({
  ostatnie,
  linia,
}: {
  ostatnie: number[];
  linia: number;
}) {
  // dane mają najnowszy mecz pierwszy – odwracamy, żeby czas płynął w prawo
  const wartosci = [...ostatnie].reverse();
  const max = Math.max(...wartosci, Math.ceil(linia + 0.5), 2);
  const liniaOdGory = (1 - linia / max) * 100;
  return (
    <span aria-hidden className="relative block h-11 w-full">
      <span
        className="absolute inset-x-0 border-t border-dashed border-ink/40"
        style={{ top: `${liniaOdGory}%` }}
      />
      <span className="absolute inset-0 flex items-end gap-[3px]">
        {wartosci.map((v, i) => (
          <span
            key={i}
            className={`min-w-[3px] flex-1 rounded-t-[3px] ${
              v > linia ? "bg-brand" : "bg-hairline-strong"
            }`}
            style={{ height: `${v > 0 ? Math.max((v / max) * 100, 7) : 3}%` }}
          />
        ))}
      </span>
      <span className="absolute inset-x-0 bottom-0 h-px bg-hairline" />
    </span>
  );
}

function DrabinkaPasek({ w }: { w: RadarWpis }) {
  const hero = w.hero;
  const rynek =
    w.rynki?.find((r) => r.rynek_kod === hero?.rynek_kod) ?? w.rynki?.[0];
  const szczeble = rynek?.drabinka ?? [];
  if (!hero || szczeble.length === 0) return null;

  // maksymalnie pięć szczebli wokół wybranego – pełna drabinka bywa długa,
  // a karta ma dać się ogarnąć jednym spojrzeniem
  const idxHero = Math.max(
    0,
    szczeble.findIndex((s) => s.linia === hero.linia),
  );
  const od = Math.max(0, Math.min(idxHero - 2, szczeble.length - 5));
  const widoczne = szczeble.slice(od, od + 5);

  const ostatnie = (rynek?.ostatnie ?? []).slice(0, 10);
  const przebite = ostatnie.filter((x) => x > hero.linia).length;

  return (
    <span className="block px-4 pb-3 sm:px-5">
      {/* bez własnej ramki — patrz DrabinkaLinii: karta ma już obramowanie,
          a trzeci poziom (wybrana poprzeczka) i tak jest wyróżniony (06.08) */}
      <span className="block rounded-(--radius-control) bg-card-soft/70 p-3">
        {/* legenda PRZY drabince, nie przy prawej krawędzi karty – opisuje
            szczeble, a nie zdanie, które od 2026-08-01 stoi po prawej */}
        <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
          {hero.rynek ?? rynek?.rynek ?? rynek?.rynek_kod}
          <span className="ml-2 font-normal text-faint">
            kurs / nasza szansa
          </span>
        </span>

        {/* TRZY STREFY ZAMIAST DWÓCH I PUSTKI (2026-08-01, zgłoszenie usera).
            Przy `1fr` na szczeblach dwa poziomy robiły dwa ogromne pudła;
            przy samej stałej szerokości zostawała martwa pustka po prawej.
            Rozciąganie wykresu na całą resztę też było złe – dziesięć
            słupków na 700 px wygląda jak płot, nie jak wykres.
            Teraz: drabinka (cennik) · wykres (stała, sensowna szerokość) ·
            TEZA KARTY zdaniem – to ona wypełnia resztę wiersza i mówi
            wprost, po co ta karta w ogóle jest. */}
        <span className="flex flex-col gap-3 sm:flex-row sm:items-stretch sm:gap-5">
          <span className="flex flex-wrap gap-1.5">
            {widoczne.map((s) => {
              const wybrany = s.linia === hero.linia;
              const p = s.p_final ?? s.p_model;
              return (
                <span
                  key={s.linia}
                  className={[
                    "flex w-[84px] flex-col items-center rounded-md px-1 py-2 text-center transition-colors sm:w-[92px]",
                    wybrany
                      ? "bg-card shadow-(--shadow-card) ring-1 ring-brand"
                      : "bg-card/60",
                  ].join(" ")}
                >
                  <span
                    className={`font-data text-[12px] font-semibold ${
                      wybrany ? "text-brand" : "text-ink-soft"
                    }`}
                  >
                    {linLabel(s.linia)}
                  </span>
                  <span
                    className={`font-data tabular-nums ${
                      wybrany
                        ? "text-[17px] font-bold leading-tight text-ink"
                        : "text-[13px] font-semibold text-ink-soft"
                    }`}
                  >
                    {fmtKurs(s.kurs)}
                  </span>
                  <span
                    className={`font-data text-[11px] tabular-nums ${
                      wybrany ? "text-brand-deep" : "text-faint"
                    }`}
                  >
                    {p != null ? fmtProc(p) : "–"}
                  </span>
                  <span className="mt-0.5 text-[9px] uppercase leading-tight tracking-tight text-faint">
                    {charakterSzczebla(s.kurs) ?? ""}
                  </span>
                </span>
              );
            })}
          </span>

          {ostatnie.length > 0 && (
            <span className="flex w-full min-w-0 flex-col justify-end sm:w-[13rem] sm:shrink-0">
              <HistoriaSparkline ostatnie={ostatnie} linia={hero.linia} />
              {/* KIERUNEK CZASU SŁOWEM, NIE UKŁADEM: podpisy na obu końcach
                  paska sklejały się w jedno, bo pasek bywa wąski. */}
              <span className="mt-1.5 flex items-baseline justify-between gap-2 text-[10px] uppercase tracking-wide text-faint">
                <span>ostatnie {ostatnie.length} meczów</span>
                <span className="shrink-0">najnowszy z prawej</span>
              </span>
            </span>
          )}

          {/* TEZA KARTY: historia i cena w jednym zdaniu. Wcześniej w tym
              miejscu była pustka, a karta – mimo drabinki – wyglądała jak
              każdy inny wiersz typu. */}
          <span className="flex min-w-0 flex-1 items-center">
            <span className="text-[13px] leading-relaxed text-muted">
              {ostatnie.length > 0 && (
                <>
                  <span className="font-data font-semibold text-ink">
                    {przebite}
                  </span>{" "}
                  z {ostatnie.length} ostatnich meczów przebiło{" "}
                  {linLabel(hero.linia)}.{" "}
                </>
              )}
              {/* BEZ „KURS WYCENIA TO NA X%, MY NA Y%" (2026-08-01, decyzja
                  usera). Na zwiniętej karcie ma stać JEDNA liczba – nasza
                  szansa na ten mecz. Porównanie z wyceną kursu zostaje
                  w rozwinięciu, w kroku „gdzie jest przewaga", gdzie jest
                  miejsce, żeby je wytłumaczyć. */}
              {hero.p_final != null ? (
                <>
                  Na ten mecz dajemy temu{" "}
                  <span className="font-data font-semibold text-ink">
                    {fmtProc(hero.p_final)}
                  </span>{" "}
                  szans przy kursie{" "}
                  <span className="font-data">{fmtKurs(hero.kurs)}</span>.
                </>
              ) : (
                <>Kurs {fmtKurs(hero.kurs)} u Superbetu.</>
              )}
            </span>
          </span>
        </span>
      </span>
    </span>
  );
}

/** Zwinięta zajawka: konkret z danych, nie szablon. */
function zajawka(w: RadarWpis): string {
  // hero wylicza backend (ten sam szczebel, który zdecydował o wyborze karty)
  if (w.hero) {
    const h = w.hero;
    const szansa =
      h.p_final != null ? ` · szansa ${fmtProc(h.p_final)}` : "";
    return `${h.rynek ?? h.rynek_kod} ${linLabel(h.linia)} · trafione ${h.traf}/${h.z} ost. · kurs ${fmtKurs(h.kurs)}${szansa}`;
  }
  if (w.rodzaj === "debiutant") {
    return "Superbet wystawił mu komplet kursów, choć my nie mamy o nim żadnych statystyk – bukmacher też strzela.";
  }
  if (w.rodzaj === "bez_feedu") {
    return w.sezony?.length
      ? `Kursy Superbetu i średnie z ${w.sezony.length} ${w.sezony.length === 1 ? "sezonu" : "sezonów"}. Meczu po meczu tu nie pokażemy – z tej ligi nie mamy takich danych.`
      : "Same kursy Superbetu. Z tej ligi nie mamy statystyk mecz po meczu.";
  }
  if (w.rodzaj === "transfer") {
    return w.stara_liga
      ? `Historia z poprzedniej ligi: ${w.stara_liga}. Kurs może tego nie uwzględniać.`
      : "Świeży transfer – historia z poprzedniego klubu.";
  }
  return "Drabinka kursów z pełną historią jego występów.";
}

/** Akapit „dlaczego ta karta" w rozwinięciu – tylko wpisy z sygnałem. */
function opisSygnalu(w: RadarWpis): string {
  if (w.rodzaj === "transfer") {
    if (w.powod === "zmiana_ligi") {
      const liga = w.stara_liga ? ` (${w.stara_liga})` : "";
      const nowa =
        !w.mecze_nowa || w.mecze_nowa === 0
          ? "W nowej lidze jeszcze nie debiutował"
          : `W nowej lidze zagrał dopiero ${w.mecze_nowa} ${w.mecze_nowa === 1 ? "mecz" : w.mecze_nowa < 5 ? "mecze" : "meczów"}`;
      return (
        `Ostatnie ${w.mecze_stara ?? ""} występów zaliczył w poprzedniej lidze${liga}. ` +
        `${nowa}. Liczby niżej pochodzą głównie ze starego adresu – kurs może tego nie uwzględniać.`
      );
    }
    return (
      "W ostatnich tygodniach grał przeciw swojej obecnej drużynie, czyli zmienił klub w ramach ligi. " +
      "Nowa rola może zmienić jego liczby w obie strony."
    );
  }
  if (w.rodzaj === "debiutant") {
    const p = w.profil;
    const czesci = [
      p?.wiek != null ? `${p.wiek} lat` : null,
      p?.wzrost != null ? `${p.wzrost} cm` : null,
      p?.kraj ? `kraj: ${p.kraj[0].toUpperCase()}${p.kraj.slice(1)}` : null,
    ].filter(Boolean);
    return (
      "Superbet daje mu pełne linie, ale nie mamy ani jednego jego meczu w danych (świeży nabytek). " +
      (czesci.length ? `Profil: ${czesci.join(", ")}. ` : "") +
      "Sprawdź sam, skąd przyszedł i ile może zagrać, zanim postawisz."
    );
  }
  if (w.rodzaj === "bez_feedu") {
    return (
      "Rozgrywki tego meczu nie są objęte feedem statystyk meczowych, więc nie pokazujemy ostatnich występów ani formy – to nie znaczy, że zawodnik jest nieznany. " +
      (w.sezony?.length
        ? "Poniżej kursy Superbetu i średnie z całych sezonów."
        : "Poniżej same kursy Superbetu; średnie sezonowe dojdą przy najbliższym odświeżeniu danych.")
    );
  }
  if (w.rodzaj === "forma") {
    const f = w.forma;
    if (!f) return "";
    return (
      `Przebił ${linLabel(f.linia)} w ${f.trafienia} z ${f.okno} ostatnich meczów. ` +
      `W tej serii średnio ${liczba(f.srednia90_okno)} na 90 minut, wcześniej ${liczba(f.srednia90_baza)}.`
    );
  }
  return "";
}

/**
 * Jeden wiersz wodospadu: co zmieniło szansę i w którą stronę.
 *
 * KIERUNEK SŁOWEM, PROCENT JAKO PRZYPIS (2026-08-01). Wcześniej kolumna
 * pokazywała samo „−20%" i nie było wiadomo, czy to o tyle spadła szansa,
 * czy oczekiwana liczba zdarzeń – a wyjaśnienie siedziało w dymku, którego
 * na telefonie nie ma. Teraz wiersz mówi „obniża", a liczba jest obok,
 * mniejsza, dla tych, którzy jej szukają.
 */
function CzynnikWiersz({
  etykieta,
  opis,
  mnoznik,
}: {
  etykieta: string;
  opis: string;
  mnoznik?: number | null;
}) {
  const zmiana = pctZmiana(mnoznik);
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="min-w-0 text-[11px] text-muted">
        <span className="text-faint">{etykieta}</span> {opis}
      </span>
      <span className="shrink-0 text-right">
        <span
          className={`text-[11px] font-semibold ${klasaKierunku(mnoznik)}`}
        >
          {kierunekMnoznika(mnoznik)}
        </span>
        {zmiana && (
          <span className="font-data ml-1.5 text-[10px] text-faint">
            {zmiana}
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * Opis rywala: co dokładnie dopuszcza i jak to wypada w lidze.
 *
 * BEZ POWTÓRZENIA NAZWY (2026-08-01): wiersz ma już etykietę „rywal", a cała
 * karta jest o jednym rynku – więc „rywal | strzały: rywal dopuszcza 13,5"
 * mówiło to samo trzy razy w jednej linijce.
 */
function opisRywala(r: RadarCzynnik): string | null {
  if (!r || r.zrodlo === "brak") return null;
  const skala =
    r.srednia != null && r.norma != null
      ? `dopuszcza ${liczba(r.srednia)} przy średniej ${liczba(r.norma)}`
      : "";
  // „#3 z 18 w lidze" było pułapką: miejsce 1 ma drużyna, która pozwala
  // NAJMNIEJ, więc sama liczba porządkowa czytała się odwrotnie, niż znaczy.
  // Sprostowanie siedziało w dymku, czyli na telefonie nie istniało.
  const miejsce =
    r.rank != null && r.z != null ? `, ${miejsceWLidze(r.rank, r.z)}` : "";
  const zrodlo =
    r.zrodlo === "historia_pokrewny"
      ? " – z rynku pokrewnego, więc z połową siły"
      : r.zrodlo === "historia"
        ? ` – z ${r.mecze ?? 0} meczów w naszych danych`
        : "";
  return `${skala}${miejsce}${zrodlo}`;
}

/**
 * KROK „SKĄD TA LICZBA" – punkt wyjścia, zanim mecz cokolwiek zmieni.
 *
 * Do 2026-08-01 była to pierwsza linijka wodospadu („punkt wyjścia: przebił
 * tę linię w 7 z 10 – od tego zaczynamy"), zgubiona w tabeli sześciu wierszy
 * z mnożnikami. A to jest fundament całej karty, więc dostaje własny krok
 * i pełne zdanie – tak samo jak na karcie drużynowej.
 */
function PunktWyjscia({
  traf,
  z,
  pBazowe,
  srednia90,
}: {
  traf: number;
  z: number;
  pBazowe?: number | null;
  srednia90?: number | null;
}) {
  return (
    <p className="text-sm leading-relaxed text-ink-soft">
      Liczymy od jego własnej historii:{" "}
      <span className="text-ink">{trafioneZ(traf, z)}</span>
      {srednia90 != null && <>, {naMecz(srednia90)}</>}.
      {pBazowe != null && (
        <>
          {" "}
          Z samej historii wychodzi{" "}
          <span className="font-data font-semibold text-ink">
            {fmtProc(pBazowe)}
          </span>{" "}
          szans – i to jest liczba, którą dopiero ten mecz koryguje.
        </>
      )}
    </p>
  );
}

/**
 * KROK „CO ZMIENIA TEN MECZ" – wodospad korekt: rywal, sędzia, przebieg,
 * miejsce gry, dłuższa historia. To odpowiedź na „gra z najlepszą obroną,
 * czemu miałby oddać 2 strzały?": widać, czy i o ile ścięliśmy historię.
 *
 * Zwraca null, gdy ten mecz nie zmienia nic – pusty nagłówek „brak korekt"
 * byłby gorszy niż brak kroku.
 */
function CzynnikiMeczu({ kontekst }: { kontekst: RadarKontekst }) {
  const rywal = kontekst.rywal;
  const sedzia = kontekst.sedzia;
  const scen = kontekst.scenariusz;
  const dom = kontekst.dom;
  const sezony = kontekst.sezony;
  const opisR = rywal ? opisRywala(rywal) : null;
  const cokolwiek =
    opisR != null ||
    sedzia?.sedzia != null ||
    sedzia?.zrodlo === "brak_obsady" ||
    scen?.mnoznik != null ||
    dom?.mnoznik != null ||
    sezony?.mnoznik != null;
  if (!cokolwiek) return null;

  return (
    <div>
      {/* WYJAŚNIENIA NA STRONIE, NIE W DYMKACH (2026-08-01). Sześć wierszy
          niżej miało sześć dymków z pełnymi zdaniami – czyli na telefonie
          była to lista skrótów bez znaczenia. Zdania, które naprawdę coś
          wnosiły, wsiąkły w opis wiersza; reszta zniknęła. */}
      <div className="divide-y divide-hairline">
        {opisR && (
          <CzynnikWiersz
            etykieta="rywal"
            opis={opisR}
            mnoznik={rywal?.mnoznik}
          />
        )}
        {sedzia?.zrodlo === "brak_obsady" ? (
          <CzynnikWiersz
            etykieta="sędzia"
            opis="jeszcze nie wiadomo, kto sędziuje – nie zgadujemy, więc nic tu nie zmieniamy"
          />
        ) : /* ZA MAŁO MECZÓW TO NIE JEST „ARBITER PRZECIĘTNY". Do 05.08 ten
               wiersz pisał „X gwiżdże mniej niż przeciętny arbiter (1 jego
               meczów w danych)" – zdanie o stylu sędziego postawione na jednym
               meczu. 210 z 444 arbitrów w bazie ma dokładnie jeden mecz. */
        sedzia?.zrodlo === "za_chuda_proba" ? (
          <CzynnikWiersz
            etykieta="sędzia"
            opis={`${sedzia.sedzia ?? "arbiter"} – mamy za mało jego meczów${
              sedzia.mecze ? ` (${sedzia.mecze})` : ""
            }, żeby cokolwiek o nim twierdzić, więc nic tu nie zmieniamy`}
          />
        ) : sedzia?.sedzia ? (
          <CzynnikWiersz
            etykieta="sędzia"
            opis={`${sedzia.sedzia} ${
              (sedzia.mnoznik ?? 1) > 1
                ? "gwiżdże więcej niż przeciętny arbiter"
                : "gwiżdże mniej niż przeciętny arbiter"
            }${sedzia.mecze ? ` (${sedzia.mecze} jego meczów w danych)` : ""}`}
            mnoznik={sedzia.mnoznik}
          />
        ) : null}
        {scen?.mnoznik != null && (
          <CzynnikWiersz
            etykieta="przebieg meczu"
            opis={`jego drużyna jest ${scen.faworyt ? "faworytem" : "słabszą stroną"}${
              scen.total != null
                ? `, kursy zapowiadają ${liczba(scen.total)} gola w meczu`
                : ""
            }`}
            mnoznik={scen.mnoznik}
          />
        )}
        {dom?.mnoznik != null && (
          <CzynnikWiersz
            etykieta="gdzie gra"
            opis={dom.dom ? "u siebie" : "na wyjeździe"}
            mnoznik={dom.mnoznik}
          />
        )}
        {sezony?.mnoznik != null && (
          /* bez „przez cały sezon" w opisie – etykieta już to mówi, a razem
             czytało się „cały sezon przez cały sezon 2,0 na mecz" (06.08) */
          <CzynnikWiersz
            etykieta="cały sezon"
            opis={`${naMecz(sezony.sezon90 ?? 0, "")}, w ostatnich meczach ${naMecz(sezony.okno90 ?? 0, "")} – dłuższa historia waży więcej`}
            mnoznik={sezony.mnoznik}
          />
        )}
      </div>
    </div>
  );
}

/**
 * KROK „GDZIE JEST PRZEWAGA" – nasza szansa kontra cena bukmachera.
 *
 * „+13 pkt proc." zastąpione dwiema liczbami obok siebie i zdaniem, co z nich
 * wynika – punkt procentowy to jednostka, której prawie nikt nie odróżnia od
 * procenta, a tu akurat na niej wszystko stoi.
 */
function PrzewagaZdanie({
  pFinal,
  kurs,
  linia,
}: {
  pFinal?: number | null;
  kurs: number;
  linia: number;
}) {
  if (pFinal == null) return null;
  // JĘZYK KURSÓW, NIE DWÓCH PROCENTÓW (2026-08-01, decyzja usera). „Kurs jest
  // wyceniony jak na 64%, my dajemy 73%" kazało czytelnikowi porównywać dwie
  // liczby tego samego rodzaju i samemu zgadywać, co z tego wynika. Nasza
  // szansa mówi swoje, a cenę porównujemy z ceną: ile ten typ jest wart
  // i ile za niego płacą.
  const uczciwy = pFinal > 0 ? 1 / pFinal : null;
  const przewaga = uczciwy != null ? kurs / uczciwy - 1 : null;
  // PRZYPIS, NIE WERDYKT (2026-08-06, decyzja usera). Cena przestała być
  // najgłośniejszym elementem rozwinięcia: to dodatek do historii, więc mówi
  // tym samym drobnym drukiem co inne dopiski, bez wytłuszczeń na całą linię.
  return (
    <p className="text-[12px] leading-relaxed text-muted">
      Po tych poprawkach dajemy {linLabel(linia)}{" "}
      <span className="font-data font-semibold text-ink-soft">
        {fmtProc(pFinal)}
      </span>{" "}
      szans
      {uczciwy != null && (
        <>
          , czyli uczciwy kurs to{" "}
          <span className="font-data">{fmtKurs(uczciwy)}</span>. Superbet płaci{" "}
          <span className="font-data font-semibold text-ink-soft">
            {fmtKurs(kurs)}
          </span>
          {przewaga != null && przewaga > 0.01 && (
            <span className="text-data-green-ink">
              {" "}
              – więcej, niż ten typ jest wart
            </span>
          )}
          {przewaga != null && przewaga <= 0.01 && (
            <span className="text-data-amber-ink">
              {" "}
              – tyle, ile trzeba, albo odrobinę mniej
            </span>
          )}
        </>
      )}
      .
    </p>
  );
}

/**
 * KROK „POKRYCIE POPRZECZEK" (2026-08-06, przebudowa na życzenie usera):
 * fakty z historii — w ilu z ostatnich meczów każda poprzeczka by weszła —
 * stały schowane w „Pełnym rachunku", a mają stać NAD naszymi korektami
 * i ceną.
 *
 * OD TRZECIEJ RUNDY UWAG to JEDYNA tabela linii na karcie: doszła kolumna
 * naszej szansy, druga cena i znacznik „ścięta", a bliźniacza tabela
 * w „Pełnym rachunku" zniknęła razem z całym przyciskiem — dwie tabele
 * o tych samych liniach to było czyste duplikowanie.
 */
function PokryciePoprzeczek({
  r,
  heroLinia,
}: {
  r: RadarRynek;
  heroLinia: number;
}) {
  const zPokryciem = r.drabinka.filter((s) => s.pokrycie && s.pokrycie.z > 0);
  if (zPokryciem.length < 2) return null;
  return (
    <div>
      <div className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr_auto] items-center gap-x-3 border-b border-hairline pb-1 text-[9px] uppercase tracking-wide text-faint">
        <span>linia</span>
        <span>kurs</span>
        <span>szansa</span>
        <span className="col-span-2">weszło w ost. meczach</span>
      </div>
      <div className="mt-1.5 space-y-1.5">
        {zPokryciem.map((s) => {
          const p = s.pokrycie!;
          const udzial = p.traf / p.z;
          const ten = s.linia === heroLinia;
          const szansa = s.p_final ?? s.p_model;
          return (
            <div
              key={s.linia}
              className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr_auto] items-center gap-x-3"
            >
              <span
                className={`font-data text-xs font-semibold ${
                  ten ? "text-brand-deep" : "text-ink"
                }`}
              >
                {linLabel(s.linia)}
              </span>
              <span className="font-data text-xs font-semibold text-ink-soft">
                {fmtKurs(s.kurs)}
                {/* druga cena POD pierwszą – piąta kolumna rozpychałaby
                    wiersz na telefonie (ta sama zasada co w starej tabeli) */}
                {s.rozjazd && (
                  <span
                    className={`block text-[10px] font-medium ${
                      s.rozjazd.gdzie === "betclic"
                        ? "text-data-amber-ink"
                        : "text-faint"
                    }`}
                  >
                    BC {fmtKurs(s.rozjazd.betclic)}
                  </span>
                )}
              </span>
              <span
                className={`font-data text-[11px] ${
                  ten ? "font-semibold text-brand-deep" : "text-ink-soft"
                }`}
              >
                {szansa != null ? fmtProc(szansa) : "–"}
                {s.strzyzenie_modelu && (
                  <span className="block text-[9px] font-normal text-data-amber-ink">
                    ścięta
                  </span>
                )}
              </span>
              <span className="h-1.5 overflow-hidden rounded-full bg-paper">
                <span
                  className={`block h-full rounded-full ${
                    udzial >= 0.7
                      ? "bg-data-green"
                      : udzial >= 0.4
                        ? "bg-data-amber"
                        : "bg-ink/25"
                  }`}
                  style={{ width: `${Math.round(udzial * 100)}%` }}
                />
              </span>
              <span className="font-data text-right text-[11px] text-ink-soft">
                {p.traf}/{p.z}
                {ten && (
                  <span className="ml-1.5 text-[9px] font-semibold uppercase tracking-wide text-brand-deep">
                    ten typ
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      <p className="mt-1.5 text-[10px] leading-relaxed text-faint">
        „Szansa” to nasza ocena na ten mecz – zaczyna od tego, jak często
        przebijał linię, i poprawia o rywala, sędziego i przebieg meczu.
        Wyższa poprzeczka = rzadsze trafienia i wyższy kurs.
      </p>
      {zPokryciem.some((s) => s.rozjazd) && (
        <p className="mt-1 text-[10px] leading-relaxed text-faint">
          „BC” to cena Betclica za to samo zdarzenie. Stawia się tam, gdzie
          płacą więcej.
        </p>
      )}
      {zPokryciem.some((s) => s.strzyzenie_modelu) && (
        <p className="mt-1 text-[10px] leading-relaxed text-faint">
          „ścięta” znaczy, że model widzi tę linię ciemniej niż sama historia
          – i zostawiamy tę niższą liczbę, nie wyższą.
        </p>
      )}
    </div>
  );
}

/** Odmiana rzeczownika rynku po liczbie: 1 strzał / 2 strzały / 5 strzałów. */
const ODMIANY: Record<string, [string, string, string]> = {
  shots: ["strzał", "strzały", "strzałów"],
  sot: ["celny strzał", "celne strzały", "celnych strzałów"],
  shots_outside_box: [
    "strzał zza pola", "strzały zza pola", "strzałów zza pola",
  ],
  headed_sot: [
    "celny strzał głową", "celne strzały głową", "celnych strzałów głową",
  ],
  fouls_committed: ["faul", "faule", "fauli"],
  fouls_won: [
    "faul na nim", "faule na nim", "fauli na nim",
  ],
  tackles: ["odbiór", "odbiory", "odbiorów"],
  offsides: ["spalony", "spalone", "spalonych"],
  interceptions: ["przechwyt", "przechwyty", "przechwytów"],
};

function odmien(n: number, kod: string): string {
  const f = ODMIANY[kod];
  if (!f) return "";
  if (n === 1) return f[0];
  const d = n % 10;
  const s = n % 100;
  return d >= 2 && d <= 4 && !(s >= 12 && s <= 14) ? f[1] : f[2];
}

/** Poniżej tylu minut występ jest zbyt krótki, żeby liczba coś znaczyła. */
const KROTKI_WYSTEP_MIN = 60;

/**
 * Mecz po meczu, zdaniami – nie samym ciągiem liczb.
 *
 * Wzorzec, który user przysłał jako docelowy dla Drabinek, opisuje KAŻDY mecz
 * osobno („3 strzały zza pola vs Radomiak", „1 strzał vs Miedź, 40 minut gry").
 * Dopiero taki zapis pozwala odróżnić zero po pełnym meczu od zera po wejściu
 * z ławki – a to zupełnie inna informacja o zawodniku.
 */
function RywaleMeczPoMeczu({ r }: { r: RadarRynek }) {
  // TELEFON WIDZI 5 NAJNOWSZYCH, RESZTA NA KLIK (2026-08-06, przebudowa
  // rozwinięcia). Krok „jak było ostatnio" jest od dziś otwarty z domysłu,
  // więc pełna lista dziesięciu meczów jedną kolumną robiłaby z karty tę samą
  // ścianę, przez którą krok wcześniej zwinęliśmy. Laptop ma miejsce: tam
  // lista idzie w dwie kolumny i pokazuje wszystko od razu.
  const [wszystkie, setWszystkie] = useState(false);
  const n = r.ostatnie?.length ?? 0;
  if (!n || !r.rywale?.length) return null;
  const LIMIT_TELEFON = 5;
  return (
    <div className="mt-2.5">
      <ul className="space-y-0.5 sm:columns-2 sm:gap-x-8 sm:space-y-0">
        {r.ostatnie!.slice(0, n).map((c, i) => {
          const rywal = r.rywale?.[i];
          const min = r.minuty?.[i];
          const krotki = min != null && min < KROTKI_WYSTEP_MIN;
          const tylkoLaptop = !wszystkie && i >= LIMIT_TELEFON;
          return (
            <li
              key={i}
              className={`${
                tylkoLaptop ? "hidden sm:flex" : "flex"
              } items-baseline gap-1.5 text-[11px] leading-relaxed sm:break-inside-avoid sm:py-px`}
            >
              <span
                className={`font-data font-semibold ${
                  c > 0 ? "text-ink-soft" : "text-faint"
                }`}
              >
                {c}
              </span>
              <span className={c > 0 ? "text-muted" : "text-faint"}>
                {odmien(c, r.rynek_kod)}
              </span>
              {rywal && (
                <span className="truncate text-muted">vs {rywal}</span>
              )}
              {/* MINUTY PRZY RYWALU, NIE PRZY PRAWEJ KRAWĘDZI (2026-08-01):
                  odkąd rozwinięcie idzie na pełną szerokość, `ml-auto` odrzucał
                  „90 min" o pół ekranu od meczu, którego dotyczy. */}
              {min != null && (
                <span
                  className={`font-data shrink-0 ${
                    krotki ? "text-data-amber-ink" : "text-faint"
                  }`}
                >
                  · {min} min{krotki && " – krótko, więc mało z tego wynika"}
                </span>
              )}
            </li>
          );
        })}
      </ul>
      {n > LIMIT_TELEFON && !wszystkie && (
        <button
          type="button"
          onClick={() => setWszystkie(true)}
          className="mt-1.5 text-[11px] font-medium text-brand transition-colors hover:text-brand-bright sm:hidden"
        >
          pokaż wszystkie {n} meczów ↓
        </button>
      )}
    </div>
  );
}

/**
 * KROK „JAK BYŁO OSTATNIO" – ten sam wykres, co na karcie drużynowej, plus
 * rozpiska mecz po meczu. Wykres niesie liczbę i poprzeczkę zakładu, lista
 * pod nim – rywala i minuty, czyli to, czego z samego słupka nie widać.
 */
function HistoriaRynku({ r, linia }: { r: RadarRynek; linia: number }) {
  const ostatnie = r.ostatnie ?? [];
  if (ostatnie.length === 0) return null;
  const przebite = ostatnie.filter((x) => x > linia).length;
  return (
    <div>
      <FormBars
        counts={ostatnie}
        minutes={r.minuty}
        opponents={r.rywale}
        line={linia}
        side="powyzej"
        height={64}
        rynek={r.rynek.toLowerCase()}
      />
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">
        W {ostatnie.length} ostatnich meczach przebił {linLabel(linia)}{" "}
        <span className="font-data font-semibold text-ink">{przebite}</span>{" "}
        {przebite === 1 ? "raz" : "razy"}
        {r.srednia90 != null && <>, {naMecz(r.srednia90)}</>}.
        {/* „forma ↑ 2,1/90 (baza 1,7)" -> zdanie. Zapis „/90" znaczy „na 90
            minut gry", czyli po prostu na mecz – ale tego trzeba było się
            domyślić albo najechać myszą. */}
        {r.forma && (
          <>
            {" "}
            Ostatnio{" "}
            <span
              className={
                r.forma.okno90 > r.forma.baza90
                  ? "font-semibold text-data-green-ink"
                  : r.forma.okno90 < r.forma.baza90
                    ? "font-semibold text-data-amber-ink"
                    : "text-muted"
              }
            >
              {naMecz(r.forma.okno90, "")}
            </span>
            , wcześniej {naMecz(r.forma.baza90, "")}.
          </>
        )}
      </p>
      {/* MECZ PO MECZU, NIE SAM CIĄG LICZB (wzorzec typera, którego user
          przysłał jako docelowy). Krótkie występy wyróżniamy, bo „0 strzałów"
          po 20 minutach znaczy co innego niż po pełnym meczu. */}
      <RywaleMeczPoMeczu r={r} />
    </div>
  );
}

/**
 * ŚREDNIE SEZONOWE JAKO LINIJKA HISTORII (2026-08-06, trzecia runda uwag
 * usera: „średnią sezonową dałbym wyżej, ale nie wiem, czy aż tak"). Zamiast
 * kart-sezonów schowanych w „Pełnym rachunku" – jedna zbita linijka na końcu
 * kroku „jak było ostatnio": szersze tło dla dziesięciu meczów nad nią.
 * Przy kartach bez historii meczowej (liga poza feedem) to jedyna historia,
 * jaką mamy – wtedy niesie cały krok.
 */
function SezonyLinijka({
  sezony,
  rynekKod,
}: {
  sezony?: RadarSezon[] | null;
  rynekKod?: string;
}) {
  const wpisy = (sezony ?? [])
    .map((s) => {
      const pary = Object.entries(s.na_mecz).filter(
        ([mk]) => SEZON_RYNKI_PL[mk] && (!rynekKod || mk === rynekKod),
      );
      if (!pary.length) return null;
      const liczby = pary
        .map(
          ([mk, v]) =>
            `${rynekKod ? "" : `${SEZON_RYNKI_PL[mk]} `}${liczba(v)}/mecz`,
        )
        .join(", ");
      return `${s.turniej} ${s.rok}: ${liczby} (${s.mecze} ${
        s.mecze === 1 ? "mecz" : s.mecze < 5 ? "mecze" : "meczów"
      })`;
    })
    .filter(Boolean);
  if (!wpisy.length) return null;
  return (
    <p className="mt-2 border-t border-hairline pt-2 text-[11px] leading-relaxed text-muted">
      <span className="mr-1.5 text-[9px] font-semibold uppercase tracking-wide text-faint">
        całe sezony
      </span>
      {wpisy.join(" · ")}
      <span className="text-faint">
        {" "}
        – także z poprzedniego klubu i ligi, jeśli zmienił barwy.
      </span>
    </p>
  );
}

/** memo: przy zmianie filtrów listy karty się nie przerenderowują wszystkie. */
export const RadarCard = memo(function RadarCard({
  w,
}: {
  w: RadarWpis;
  rank?: number;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const sygnal = sygnalInfo(w);
  const opis = opisSygnalu(w);
  // „solidny" bez plakietki: etykieta na każdej karcie przestaje cokolwiek
  // znaczyć, a lista i tak jest posortowana po jakości
  const klasa =
    w.ocena?.klasa && w.ocena.klasa !== "solidny"
      ? KLASY[w.ocena.klasa]
      : null;
  // „analiza" bez paska i plakietki – to stan domyślny, a etykieta na każdej
  // karcie przestaje cokolwiek znaczyć (ta sama zasada co przy „solidny")
  const kat =
    // od 2026-08-01 kategoria nie jest plakietką, tylko zdaniem w rozwinięciu
    // – więc „tylko nasza analiza" też warto powiedzieć, zamiast przemilczeć
    w.kategoria ? KATEGORIE[w.kategoria] : null;

  // NAJWYŻEJ DWIE PLAKIETKI (2026-08-01). Wcześniej mogło ich być pięć naraz
  // – kategoria, klasa, „mocna seria", sygnał i skład – i nagłówek robił się
  // jarmarkiem, w którym nic nie było ważne. Kolejność niżej to kolejność
  // WAŻNOŚCI DLA DECYZJI: ostrzeżenie o składzie bije wszystko, potem ocena
  // przewagi, potem uczciwe zastrzeżenie „to stoi na serii, nie na przewadze",
  // na końcu sygnał. Wszystko, co się nie zmieści, ma swoje zdanie
  // w rozwinięciu – nie znika, tylko przestaje krzyczeć.
  const plakietki = [
    w.xi === false
      ? {
          label: "raczej poza 1. składem",
          badge: "bg-data-red-wash text-data-red-ink",
        }
      : null,
    klasa ? { label: klasa.label, badge: klasa.badge } : null,
    w.ocena?.powod_wejscia === "seria"
      ? { label: "mocna seria", badge: "bg-paper text-ink-soft" }
      : null,
    sygnal ? { label: sygnal.label, badge: sygnal.badge } : null,
  ]
    .filter((p): p is { label: string; badge: string } => p !== null)
    .slice(0, 2);

  return (
    <motion.article
      layout={!reduced}
      className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-[border-color,box-shadow] duration-200 hover:border-brand/30 hover:shadow-(--shadow-card-hover)"
    >
      {/* pasek kategorii przy krawędzi – skanuje się wzrokiem, bez czytania */}
      {kat && (
        <span
          aria-hidden
          className={`absolute inset-y-0 left-0 w-1 ${kat.pasek}`}
        />
      )}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="group w-full text-left"
      >
        {/* wiersz główny: kto · info · plakietki */}
        <span className="grid grid-cols-[1fr_auto] items-center gap-x-4 px-4 pb-1.5 pt-3.5 sm:px-5">
          <span className="min-w-0">
            <span className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
              {sygnal && (
                <span className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center">
                  <span
                    aria-hidden
                    className={`absolute -inset-1 rounded-full opacity-20 ${sygnal.dioda}`}
                  />
                  <span
                    aria-hidden
                    className={`h-2 w-2 rounded-full ${sygnal.dioda}`}
                  />
                </span>
              )}
              <span role="heading" aria-level={3} className="truncate font-semibold">
                {w.podmiot}
              </span>
              <span className="text-sm text-muted">
                {w.druzyna}
                {w.pozycja && w.pozycja !== "?" ? ` · ${w.pozycja}` : ""}
              </span>
            </span>
            <span className="mt-0.5 block truncate text-xs text-faint">
              vs {w.przeciwnik}
              {w.minuty_sr6 != null && ` · gra średnio ${w.minuty_sr6} min`}
            </span>
          </span>

          {/* NAJWYŻEJ DWIE PLAKIETKI (2026-08-01). Wcześniej mogło ich być
              pięć naraz – kategoria, klasa, „mocna seria", sygnał i skład –
              a nagłówek robił się jarmarkiem, w którym nic nie było ważne.
              Zostają: OCENA (jak duża przewaga) i OSTRZEŻENIE (poza składem),
              bo tylko te dwie zmieniają decyzję. Cała reszta ma teraz swoje
              zdanie w rozwinięciu, gdzie jest miejsce, żeby ją wytłumaczyć. */}
          <span className="flex flex-col items-end justify-center gap-1">
            {plakietki.map((p) => (
              <span
                key={p.label}
                className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${p.badge}`}
              >
                {p.label}
              </span>
            ))}
          </span>
        </span>

        {/* UKŁAD „PEWNIAK TANIEJ" – najcenniejszy rodzaj rozjazdu, więc mówimy
            go zdaniem, a nie samym procentem. Cena tańsza jest DOWODEM, że
            zdarzenie jest pewne; stawia się tam, gdzie płacą więcej. */}
        {w.rozjazd_pewniak && (
          <span className="mx-4 mb-2 block rounded-(--radius-control) bg-data-amber-wash px-3 py-1.5 text-[11px] text-data-amber-ink sm:mx-5">
            {w.rozjazd_pewniak.gdzie === "betclic" ? "Superbet" : "Betclic"}{" "}
            wycenia {linLabel(w.rozjazd_pewniak.linia)} na zaledwie{" "}
            <span className="font-data font-semibold">
              {fmtKurs(
                w.rozjazd_pewniak.gdzie === "betclic"
                  ? w.rozjazd_pewniak.superbet
                  : w.rozjazd_pewniak.betclic,
              )}
            </span>
            , a{" "}
            {w.rozjazd_pewniak.gdzie === "betclic" ? "Betclic" : "Superbet"}{" "}
            płaci{" "}
            <span className="font-data font-semibold">
              {fmtKurs(w.rozjazd_pewniak.lepszy)}
            </span>{" "}
            – o {Math.round(w.rozjazd_pewniak.przewaga_pct)}% więcej za to samo.
            <span className="mt-0.5 block text-[10px] opacity-80">
              To ocena rynku, nie gwarancja – karta stoi na analizie, a różnica
              cen jest do niej dodatkiem.
            </span>
          </span>
        )}

        {/* FAKTY tuż nad drabinką, którą opisują – patrz komentarz przy Fakty */}
        <Fakty w={w} />

        {/* DRABINKA – to jest treść karty, patrz DrabinkaPasek */}
        <DrabinkaPasek w={w} />

        {/* zajawka z konkretem + rozwinięcie */}
        <span className="flex items-center gap-x-2.5 px-4 pb-3.5 sm:px-5">
          {/* Gdy pasek drabinki jest na karcie, zajawka mówiłaby DOKŁADNIE to
              samo („Strzały 2+ · kurs 1,56 · szansa 73%") tylko prozą – dwa
              razy ta sama rzecz, jedna pod drugą. Zostaje wtedy sam przycisk
              rozwinięcia; opisowe zajawki (debiutant, transfer, brak feedu)
              niosą treść, której w pasku nie ma, więc te zostają. */}
          {!maDrabinke(w) && (
            <span className="min-w-0 truncate text-[11px] font-medium text-ink-soft">
              {zajawka(w)}
            </span>
          )}
          <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
            {open ? "zwiń" : "skąd ta liczba"}
            <svg
              aria-hidden
              width="12"
              height="12"
              viewBox="0 0 14 14"
              className={`transition-transform ${open ? "rotate-180" : ""}`}
            >
              <path
                d="M3 5.5 L7 9.5 L11 5.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </span>
      </button>

      {/* rozwinięcie: opis sygnału + rynki + sezony */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.25, 0.9, 0.3, 1] }}
          >
            <div className="border-t border-hairline bg-paper/50 px-4 py-4 sm:px-6">
              {/* TEN SAM UKŁAD, CO NA KARCIE DRUŻYNOWEJ (2026-08-01, część 2):
                  skąd ta liczba → co zmienia ten mecz → jak było ostatnio →
                  gdzie jest przewaga. Wcześniej drabinka tłumaczyła się
                  wodospadem i tabelą, drużyna werdyktem i osią – nauka jednej
                  karty nie pomagała przy drugiej.

                  OSTRZEŻENIE O SKŁADZIE STOI PRZED HISTORIĄ: jeśli zawodnik
                  raczej nie zagra, reszta rachunku jest bez znaczenia. */}
              {w.xi === false && (
                <p className="mb-4 rounded-(--radius-control) bg-data-red-wash px-3.5 py-2.5 text-sm leading-relaxed text-data-red-ink">
                  <span className="font-medium">Raczej poza pierwszym składem:</span>{" "}
                  według składu (ogłoszonego albo przewidywanego) nie zaczyna
                  meczu. Ta karta powstała wcześniej – lepiej jej nie grać.
                </p>
              )}

              {(() => {
                // TYLKO wybrany typ – karta argumentuje jedną rekomendację,
                // nie wysypuje wszystkich 9 rynków (decyzja produktowa)
                const r =
                  w.rynki.find((x) => x.rynek_kod === w.hero?.rynek_kod) ??
                  w.rynki[0];
                const kontekst = w.ocena?.kontekst ?? r?.kontekst;
                const hero = w.hero;
                // bez tego warunku krok „pokrycie poprzeczek" potrafiłby
                // stanąć jako sam nagłówek nad niczym (komponent zwraca null
                // przy mniej niż dwóch liniach z historią)
                const liniePokrycia =
                  r?.drabinka.filter((s) => (s.pokrycie?.z ?? 0) > 0).length ?? 0;
                return (
                  <Kroki>
                    {(hero || opis) && (
                      <Krok kod="skad">
                        {hero && (
                          <PunktWyjscia
                            traf={hero.traf}
                            z={hero.z}
                            pBazowe={hero.p_bazowe}
                            srednia90={r?.srednia90}
                          />
                        )}
                        {/* skąd BIORĄ SIĘ te dane: transfer z innej ligi,
                            debiutant bez historii, liga poza feedem.
                            BEZ WPISU „forma" (06.08): odkąd krok „jak było
                            ostatnio" jest otwarty, te same liczby serii stały
                            trzy razy na jednej karcie – zdanie o serii niesie
                            teraz historia i notka „seria formy" pod nią. */}
                        {opis && w.rodzaj !== "forma" && (
                          <p className="mt-1.5 text-sm leading-relaxed text-muted">
                            {opis}
                          </p>
                        )}
                        {sygnal && w.rodzaj !== "forma" && (
                          <p className="mt-1.5 text-[13px] leading-relaxed text-faint">
                            <span className="font-medium text-ink-soft">
                              {sygnal.label}:
                            </span>{" "}
                            {sygnal.tytul}
                          </p>
                        )}
                        {/* karta wznowiona z rejestru publikacji: hero jest
                            ZAMROŻONY z chwili, gdy karta powstała – kurs
                            u bukmachera mógł się od tego czasu skrócić */}
                        {w.wznowiony && (
                          <p className="mt-1.5 text-[13px] leading-relaxed text-faint">
                            Ta karta powstała we wcześniejszym przeliczeniu,
                            więc kurs i szansa są zamrożone z tamtej chwili.
                            Cenę sprawdź u bukmachera przed postawieniem.
                          </p>
                        )}
                      </Krok>
                    )}

                    {/* FAKTY PRZED KOREKTAMI (2026-08-06, druga runda uwag
                        usera): najpierw cała historia — mecz po meczu i
                        pokrycie poprzeczek — a dopiero potem to, co my z nią
                        robimy („co zmienia ten mecz") i na końcu cena.
                        Krok „ostatnio" jest OTWARTY Z DOMYSŁU: zwinięty
                        wyglądał jak pusta etykieta z myślnikiem. Wysokość
                        trzyma w ryzach lista mecz po meczu: dwie kolumny na
                        laptopie, 5 najnowszych na telefonie. */}
                    {((r && hero && (r.ostatnie?.length ?? 0) > 0) ||
                      (w.sezony?.length ?? 0) > 0) && (
                      <Krok kod="ostatnio">
                        {r && hero && (r.ostatnie?.length ?? 0) > 0 && (
                          <HistoriaRynku r={r} linia={hero.linia} />
                        )}
                        {sygnal && w.rodzaj === "forma" && (
                          <p className="mt-2 text-[13px] leading-relaxed text-faint">
                            <span className="font-medium text-ink-soft">
                              {sygnal.label}:
                            </span>{" "}
                            {sygnal.tytul}
                          </p>
                        )}
                        {/* szersze tło pod dziesięcioma meczami; przy lidze
                            poza feedem to JEDYNA historia i niesie cały krok */}
                        <SezonyLinijka
                          sezony={w.sezony}
                          rynekKod={w.hero?.rynek_kod}
                        />
                      </Krok>
                    )}

                    {r && hero && liniePokrycia >= 2 && (
                      <Krok kod="pokrycie">
                        <PokryciePoprzeczek r={r} heroLinia={hero.linia} />
                      </Krok>
                    )}

                    {kontekst && r && (
                      <Krok kod="zmiana">
                        <CzynnikiMeczu kontekst={kontekst} />
                      </Krok>
                    )}

                    {/* „CENA", NIE „GDZIE JEST PRZEWAGA" (2026-08-06, decyzja
                        usera): to dodatek do historii, nie punkt kulminacyjny.
                        Stoi OSTATNIA i mówi najdrobniejszym drukiem na karcie
                        — patrz PrzewagaZdanie. */}
                    <Krok kod="przewaga" tytul="cena">
                      {hero && (
                        <PrzewagaZdanie
                          pFinal={hero.p_final}
                          kurs={hero.kurs}
                          linia={hero.linia}
                        />
                      )}
                      {/* CO TA KARTA MA NA SOBIE – zdania, które do 2026-08-01
                          były dymkami przy plakietkach. Dymek nie działa na
                          telefonie, a bez tych zdań etykiety typu „lepsza
                          cena" są dla postronnej osoby zgadywanką. */}
                      {(klasa ||
                        kat ||
                        w.ocena?.powod_wejscia === "seria" ||
                        w.xi === true) && (
                        <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-muted">
                          {klasa && (
                            <li>
                              <span className="font-medium text-ink-soft">
                                {klasa.label}:
                              </span>{" "}
                              {klasa.opis}
                            </li>
                          )}
                          {kat && (
                            <li>
                              <span className="font-medium text-ink-soft">
                                {kat.label}:
                              </span>{" "}
                              {kat.opis}
                            </li>
                          )}
                          {w.ocena?.powod_wejscia === "seria" && (
                            <li>
                              <span className="font-medium text-ink-soft">
                                mocna seria:
                              </span>{" "}
                              ta karta stoi na serii, nie na przewadze.
                              Zawodnik regularnie przebija tę linię, a cena
                              jest grywalna – ale nasza szansa NIE bije tu
                              kursu bukmachera.
                            </li>
                          )}
                          {w.xi === true && (
                            <li className="text-faint">
                              <span className="font-medium">
                                raczej w pierwszym składzie:
                              </span>{" "}
                              tak wynika ze składu – ale bywa on przewidywany
                              przez serwis nawet 36 godzin przed meczem, a nie
                              ogłoszony przez trenera.
                            </li>
                          )}
                        </ul>
                      )}
                    </Krok>
                  </Kroki>
                );
              })()}

              {/* PRZYCISK „PEŁNY RACHUNEK" ZNIKŁ (2026-08-06, trzecia runda
                  uwag usera). Po wciągnięciu pokryć (z szansą i drugą ceną)
                  oraz sezonów do kroków nie zostało w nim NIC, czego nie ma
                  na wierzchu — karta drabinki nie ma już żadnej schowanej
                  sekcji. */}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
