"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { fmtKurs, fmtProc } from "@/lib/format";
import {
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
  RadarSzczebel,
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
  analiza: {
    label: "tylko nasza analiza",
    pasek: "bg-hairline-strong",
    badge: "border border-hairline bg-paper text-muted",
    opis: "Ta karta stoi wyłącznie na naszej analizie: jak często przebijał tę linię, forma, minuty, rywal i przewidywany przebieg meczu. Drugiego cennika na tę linię nie mamy – albo Betclic nie prowadzi tego meczu, albo nie wystawił tego rynku.",
  },
  rynek_zgodny: {
    label: "obaj bukmacherzy zgodni",
    pasek: "bg-brand-bright",
    badge: "bg-brand-wash text-brand-deep",
    opis: "Drugi bukmacher wycenia to niemal identycznie. Okazji cenowej tu nie ma, ale jest potwierdzenie: obie firmy widzą to tak samo, więc nasza linia nie jest wzięta z sufitu.",
  },
  rozjazd: {
    label: "jeden płaci więcej",
    pasek: "bg-data-amber",
    badge: "bg-data-amber-wash text-data-amber-ink",
    opis: "Za to samo zdarzenie jeden bukmacher płaci zauważalnie więcej niż drugi. Stawia się tam, gdzie płacą więcej – przy tej samej analizie dostajesz lepszą cenę. Sama różnica kursów nie jest powodem, dla którego ta karta tu jest: najpierw musiała przejść całą analizę.",
  },
  pewniak_taniej: {
    label: "drugi bukmacher: to niemal pewne",
    pasek: "bg-data-amber",
    badge: "bg-data-amber text-white",
    opis: "Jeden bukmacher wycenia to jako niemal pewne (kurs poniżej 1,45), a drugi płaci za to samo 1,75 lub więcej. To opinia rynku o pewności, nie nasza gwarancja – i nie ona zdecydowała o tej karcie. Karta i tak musiała przejść wszystkie nasze progi; różnica cen jest dodatkowym dowodem, nie przepustką.",
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

const liczba = (v: number) => String(v).replace(".", ",");

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
/**
 * CHARAKTER SZCZEBLA, nie reklama (2026-08-01, decyzja usera).
 *
 * Etykieta „nasz typ" nad wybraną kolumną nic nie tłumaczyła, tylko się
 * chwaliła – a user i tak wie, że wszystko na tej stronie jest nasze.
 * Każdy szczebel dostaje więc opis SWOJEGO charakteru, wyliczony z naszej
 * szansy. Dzięki temu widać istotę drabinki: idąc w prawo kupujesz wyższy
 * kurs za niższą pewność. Żaden szczebel nie jest przy tym reklamowany.
 */
function charakterSzczebla(p: number | null | undefined): string | null {
  if (p == null) return null;
  if (p >= 0.8) return "wysoka szansa";
  if (p >= 0.5) return "realne";
  return "ryzykowne";
}

/** Czy karta pokaże pasek drabinki (a więc zajawka byłaby jego powtórzeniem). */
function maDrabinke(w: RadarWpis): boolean {
  const r = w.rynki?.find((x) => x.rynek_kod === w.hero?.rynek_kod) ?? w.rynki?.[0];
  return Boolean(w.hero) && (r?.drabinka?.length ?? 0) > 0;
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
      <span className="block rounded-lg border border-hairline bg-card-soft/70 p-2.5">
        <span className="mb-1.5 flex items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold text-ink-soft">
            {hero.rynek ?? rynek?.rynek ?? rynek?.rynek_kod}
          </span>
          <span className="text-[10px] uppercase tracking-wide text-faint">
            kurs / nasza szansa
          </span>
        </span>

        {/* KOMÓRKI STAŁEJ SZEROKOŚCI, nie rozciągane na całą kartę: przy
            dwóch szczeblach `1fr` robił dwa ogromne pudła i pół karty pustki.
            Drabinka ma się czytać jak cennik – wąskie kolumny obok siebie. */}
        <span className="flex flex-wrap items-start gap-x-6 gap-y-2 sm:flex-nowrap">
        <span className="flex flex-wrap gap-1">
          {widoczne.map((s) => {
            const wybrany = s.linia === hero.linia;
            const p = s.p_final ?? s.p_model;
            return (
              <span
                key={s.linia}
                className={[
                  "flex w-[84px] flex-col items-center rounded-md px-1 py-1.5 text-center",
                  wybrany
                    ? "bg-brand-wash ring-1 ring-brand/40"
                    : "bg-card",
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
                  className={`font-data text-[13px] font-bold tabular-nums ${
                    wybrany ? "text-ink" : "text-ink-soft"
                  }`}
                >
                  {fmtKurs(s.kurs)}
                </span>
                <span className="font-data text-[11px] tabular-nums text-faint">
                  {p != null ? fmtProc(p) : "–"}
                </span>
                <span className="mt-0.5 text-[9px] uppercase leading-tight tracking-tight text-faint">
                  {charakterSzczebla(p) ?? ""}
                </span>
              </span>
            );
          })}
        </span>

        {ostatnie.length > 0 && (
          <span className="flex min-w-0 flex-col gap-0.5">
            {/* SKALA CZASU (2026-08-01): dziesięć kresek bez podpisu nie
                mówiło, czy pierwszy słupek to mecz sprzed tygodnia, czy sprzed
                trzech miesięcy. Dane mają najnowszy mecz pierwszy, więc
                odwracamy: czas płynie od lewej do prawej, jak na wykresie. */}
            <span className="flex gap-[3px]" aria-hidden>
              {[...ostatnie].reverse().map((x, i) => (
                <span
                  key={i}
                  className={`h-3.5 w-1.5 rounded-[2px] ${
                    x > hero.linia ? "bg-brand" : "bg-faint/30"
                  }`}
                />
              ))}
            </span>
            {/* JEDNA LINIJKA ZAMIAST DWÓCH PODPISÓW: pasek ma ~90 px, więc
                „10 meczów temu" i „ostatni" na obu końcach sklejały się
                w jedno słowo. Kierunek czasu mówimy słowem, nie układem. */}
            <span className="mt-0.5 text-[11px] leading-tight text-faint">
              {przebite} z {ostatnie.length} przebiło {linLabel(hero.linia)}
              <span className="block text-[9px] uppercase tracking-wide">
                najnowszy mecz z prawej
              </span>
            </span>
          </span>
        )}
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

/** Opis rywala per rynek: co dokładnie dopuszcza i jak to wypada w lidze. */
function opisRywala(r: RadarCzynnik, rynek: string): string | null {
  if (!r || r.zrodlo === "brak") return null;
  const skala =
    r.srednia != null && r.norma != null
      ? `${liczba(r.srednia)} przy średniej ${liczba(r.norma)}`
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
  return `${rynek.toLowerCase()}: rywal dopuszcza ${skala}${miejsce}${zrodlo}`;
}

/**
 * „Dlaczego" – wodospad od surowego pokrycia do szansy po kontekście.
 * To jest odpowiedź na pytanie „gra z najlepszą obroną, czemu miałby oddać
 * 2 strzały?": widać, czy i o ile ścięliśmy historię tym meczem.
 */
function Wodospad({
  kontekst,
  rynek,
  pBazowe,
  pFinal,
  kurs,
  traf,
  z,
}: {
  kontekst: RadarKontekst;
  rynek: string;
  pBazowe?: number | null;
  pFinal?: number | null;
  kurs: number;
  traf: number;
  z: number;
}) {
  const rywal = kontekst.rywal;
  const sedzia = kontekst.sedzia;
  const scen = kontekst.scenariusz;
  const dom = kontekst.dom;
  const sezony = kontekst.sezony;
  const opisR = rywal ? opisRywala(rywal, rynek) : null;
  const cenaRynku = kurs > 0 ? 1 / kurs : null;
  const przewaga =
    pFinal != null && cenaRynku != null
      ? Math.round((pFinal - cenaRynku) * 100)
      : null;

  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-3">
      <p className="text-[10px] uppercase tracking-wide text-faint">
        skąd ta liczba
      </p>
      {/* WYJAŚNIENIA NA STRONIE, NIE W DYMKACH (2026-08-01). Sześć wierszy
          niżej miało sześć dymków z pełnymi zdaniami – czyli na telefonie
          była to lista skrótów bez znaczenia. Zdania, które naprawdę coś
          wnosiły, wsiąkły w opis wiersza; reszta zniknęła. */}
      <div className="mt-1.5 divide-y divide-hairline">
        <CzynnikWiersz
          etykieta="punkt wyjścia"
          opis={`${trafioneZ(traf, z)} – od tego zaczynamy`}
        />
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
          <CzynnikWiersz
            etykieta="cały sezon"
            opis={`przez cały sezon ${naMecz(sezony.sezon90 ?? 0, "")}, w ostatnich meczach ${naMecz(sezony.okno90 ?? 0, "")} – dłuższa historia waży więcej`}
            mnoznik={sezony.mnoznik}
          />
        )}
      </div>
      {/* „+13 pkt proc." zastąpione dwiema liczbami obok siebie i zdaniem,
          co z nich wynika – punkt procentowy to jednostka, której prawie
          nikt nie odróżnia od procenta, a tu akurat na niej wszystko stoi. */}
      {pFinal != null && (
        <p className="mt-2 border-t border-hairline pt-2 text-[11px] leading-relaxed text-ink-soft">
          Po tych poprawkach dajemy temu{" "}
          <span className="font-data font-semibold text-ink">
            {fmtProc(pFinal)}
          </span>
          {cenaRynku != null && (
            <>
              , a kurs {fmtKurs(kurs)} jest wyceniony jak na{" "}
              <span className="font-data text-faint">{fmtProc(cenaRynku)}</span>
              {przewaga != null && przewaga > 0 && (
                <span className="font-semibold text-data-green-ink">
                  {" "}
                  – czyli naszym zdaniem bukmacher płaci tu za dużo
                </span>
              )}
              {przewaga != null && przewaga <= 0 && (
                <span className="font-semibold text-data-amber-ink">
                  {" "}
                  – czyli cena jest uczciwa albo lekko za niska
                </span>
              )}
            </>
          )}
          .
          {pBazowe != null && (
            <span className="mt-0.5 block text-faint">
              Z samej historii wychodziło {fmtProc(pBazowe)}. Resztę zmieniło to,
              co czeka go akurat w tym meczu.
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Wiersz szczebla drabinki: linia · kurs · szansa modelu · pokrycie. */
function SzczebelWiersz({ s }: { s: RadarSzczebel }) {
  const p = s.pokrycie;
  const udzial = p && p.z > 0 ? p.traf / p.z : null;
  return (
    /* BEZ DYMKA (2026-08-01): powtarzał liczby, które i tak są w wierszu.
       Jedyna rzecz, której w wierszu nie było – „szansa ścięta, bo model
       widzi tę linię ciemniej niż historia" – dostała widoczny znacznik. */
    <div className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] items-center gap-x-3 py-1">
      <span className="font-data text-xs font-semibold text-ink">
        {linLabel(s.linia)}
      </span>
      <span className="font-data text-xs font-semibold text-brand-deep">
        {fmtKurs(s.kurs)}
        {/* druga cena POD pierwszą, a nie w nowej kolumnie – na telefonie
            piąta kolumna rozpychała wiersz w bok */}
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
          s.p_final != null ? "font-semibold text-ink-soft" : "text-muted"
        }`}
      >
        {s.p_final != null
          ? fmtProc(s.p_final)
          : s.p_model != null
            ? fmtProc(s.p_model)
            : "–"}
        {s.strzyzenie_modelu && (
          <span className="block text-[9px] font-normal text-data-amber-ink">
            ścięta
          </span>
        )}
      </span>
      {udzial != null ? (
        <span className="flex items-center gap-2">
          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-paper">
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
          <span className="font-data w-8 shrink-0 text-right text-[11px] text-ink-soft">
            {p!.traf}/{p!.z}
          </span>
        </span>
      ) : (
        <span className="text-[11px] text-faint">brak historii</span>
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
  const n = r.ostatnie?.length ?? 0;
  if (!n || !r.rywale?.length) return null;
  return (
    <ul className="mt-2 space-y-0.5">
      {r.ostatnie!.slice(0, n).map((c, i) => {
        const rywal = r.rywale?.[i];
        const min = r.minuty?.[i];
        const krotki = min != null && min < KROTKI_WYSTEP_MIN;
        return (
          <li
            key={i}
            className="flex items-baseline gap-1.5 text-[11px] leading-relaxed"
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
            {min != null && (
              <span
                className={`font-data ml-auto shrink-0 ${
                  krotki ? "text-data-amber-ink" : "text-faint"
                }`}
              >
                {min} min{krotki && " – krótko, więc mało z tego wynika"}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Blok jednego rynku: nagłówek, drabinka-tabela, ostatnie mecze, kontekst. */
function RynekBlok({ r }: { r: RadarRynek }) {
  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-xs font-semibold text-ink">{r.rynek}</span>
        <span className="flex items-baseline gap-3">
          {/* „forma ↑ 2,1/90 (baza 1,7)" -> zdanie. Zapis „/90" znaczy
              „na 90 minut gry", czyli po prostu na mecz – ale tego trzeba
              było się domyślić albo najechać myszą. */}
          {r.forma && (
            <span className="text-[11px]">
              <span
                className={
                  r.forma.okno90 > r.forma.baza90
                    ? "font-semibold text-data-green-ink"
                    : r.forma.okno90 < r.forma.baza90
                      ? "font-semibold text-data-amber-ink"
                      : "text-muted"
                }
              >
                ostatnio {naMecz(r.forma.okno90, "")}
              </span>{" "}
              <span className="text-faint">
                , wcześniej {naMecz(r.forma.baza90, "")}
              </span>
            </span>
          )}
          {r.srednia90 != null && (
            <span className="text-[11px] text-muted">
              {naMecz(r.srednia90)} przez całą historię
            </span>
          )}
        </span>
      </div>

      {/* drabinka: linia · kurs · model · pokrycie ostatnich */}
      <div className="mt-2">
        <div className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] gap-x-3 border-b border-hairline pb-1 text-[9px] uppercase tracking-wide text-faint">
          <span>linia</span>
          <span>kurs</span>
          <span>szansa</span>
          <span>trafienia w ost. meczach</span>
        </div>
        {/* NAGŁÓWKI TŁUMACZĄ SIĘ POD TABELĄ, NIE W DYMKU. Dwa z czterech
            miały wcześniej `title` z pełnym zdaniem – na telefonie nie do
            odczytania, a bez nich kolumna „szansa" nie mówi, czyja to szansa
            i skąd się bierze. */}
        <p className="mt-1 text-[10px] leading-relaxed text-faint">
          „Szansa” to nasza ocena, że przebije tę linię akurat w tym meczu:
          zaczynamy od tego, jak często robił to ostatnio, a potem poprawiamy
          o rywala, sędziego i przewidywany przebieg meczu.
        </p>
        {r.drabinka.map((s) => (
          <SzczebelWiersz key={s.linia} s={s} />
        ))}
        {/* LEGENDA DRUGIEJ CENY na stronie zamiast w dymku przy „BC 1,85" */}
        {r.drabinka.some((s) => s.rozjazd) && (
          <p className="mt-1.5 text-[10px] leading-relaxed text-faint">
            „BC” to cena Betclica za to samo zdarzenie. Stawia się tam, gdzie
            płacą więcej.
          </p>
        )}
        {r.drabinka.some((s) => s.strzyzenie_modelu) && (
          <p className="mt-1 text-[10px] leading-relaxed text-faint">
            „ścięta” znaczy, że model widzi tę linię ciemniej niż sama historia
            – i zostawiamy tę niższą liczbę, nie wyższą.
          </p>
        )}
      </div>

      {r.ostatnie && r.ostatnie.length > 0 && (
        <div className="mt-2.5">
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-[9px] uppercase tracking-wide text-faint">
              ostatnie
            </span>
            {/* bez dymka: rywal i minuty są wypisane niżej, mecz po meczu */}
            {r.ostatnie.map((c, i) => (
              <span
                key={i}
                className={`font-data inline-flex h-5 min-w-5 items-center justify-center rounded px-1 text-[11px] font-semibold ${
                  c > 0 ? "bg-brand-wash text-brand-deep" : "bg-paper text-faint"
                }`}
              >
                {c}
              </span>
            ))}
          </div>
          {/* MECZ PO MECZU, NIE SAM CIĄG LICZB (wzorzec typera, którego user
              przysłał jako docelowy: „3 strzały vs Radomiak", „1 strzał vs
              Miedź (40 min gry)"). Kafelki wyżej zostają na szybki rzut oka,
              ale nazwa rywala i minuty nie mogą siedzieć w dymku – to jest
              treść, po którą czyta się rozwinięcie. Krótkie występy
              wyróżniamy, bo „0 strzałów" po 20 minutach znaczy co innego niż
              po pełnym meczu. */}
          <RywaleMeczPoMeczu r={r} />
        </div>
      )}

      {r.rywal?.srednia != null && (
        <p className="mt-2 text-[11px] leading-relaxed text-muted">
          Najbliższy rywal pozwala na tym rynku{" "}
          <span className="font-data font-semibold text-ink-soft">
            {liczba(r.rywal.srednia)}
          </span>{" "}
          na mecz
          {r.rywal.liga != null && (
            <span className="text-faint">
              {" "}
              przy średniej ligi {liczba(r.rywal.liga)}
            </span>
          )}
          {r.rywal.rank != null && r.rywal.z != null && (
            <span className="text-faint">
              {" – "}
              {miejsceWLidze(r.rywal.rank, r.rywal.z)}
            </span>
          )}
          .
        </p>
      )}
    </div>
  );
}

/** Wiersz sezonu: liga, rok, mecze i średnia – TYLKO dla wybranego rynku. */
function SezonWiersz({ s, rynekKod }: { s: RadarSezon; rynekKod?: string }) {
  const wpisy = Object.entries(s.na_mecz).filter(
    ([mk]) => SEZON_RYNKI_PL[mk] && (!rynekKod || mk === rynekKod),
  );
  if (!wpisy.length) return null;
  return (
    <div className="rounded-(--radius-control) border border-hairline bg-card px-3.5 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className="text-xs font-semibold text-ink">
          {s.turniej} {s.rok}
        </span>
        <span className="font-data text-[11px] text-muted">
          {s.mecze} meczów · {s.minuty} min
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
        {wpisy.map(([mk, v]) => (
          <span key={mk} className="font-data text-[11px] text-ink-soft">
            <span className="text-faint">{SEZON_RYNKI_PL[mk]}</span>{" "}
            <span className="font-semibold">{liczba(v)}</span>
            <span className="text-faint">/mecz</span>
          </span>
        ))}
      </div>
    </div>
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
              <span className="truncate font-semibold">{w.podmiot}</span>
              <span className="text-sm text-muted">
                {w.druzyna}
                {w.pozycja && w.pozycja !== "?" ? ` · ${w.pozycja}` : ""}
              </span>
            </span>
            <span className="mt-0.5 block truncate text-xs text-faint">
              vs {w.przeciwnik}
              {w.minuty_sr6 != null && ` · gra śr. ${w.minuty_sr6} min`}
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
              {/* CO TA KARTA MA NA SOBIE – zdania, które do 2026-08-01 były
                  dymkami przy plakietkach. Dymek nie działa na telefonie,
                  a bez tych zdań etykiety typu „lepsza cena" albo „debiutant"
                  są dla postronnej osoby zgadywanką. */}
              {(klasa || kat || sygnal || w.ocena?.powod_wejscia === "seria") && (
                <ul className="mb-4 max-w-prose space-y-2 text-sm leading-relaxed text-ink-soft">
                  {klasa && (
                    <li>
                      <span className="font-medium text-ink">
                        {klasa.label}:
                      </span>{" "}
                      {klasa.opis}
                    </li>
                  )}
                  {kat && (
                    <li>
                      <span className="font-medium text-ink">{kat.label}:</span>{" "}
                      {kat.opis}
                    </li>
                  )}
                  {w.ocena?.powod_wejscia === "seria" && (
                    <li>
                      <span className="font-medium text-ink">mocna seria:</span>{" "}
                      ta karta stoi na serii, nie na przewadze. Zawodnik
                      regularnie przebija tę linię, a cena jest grywalna – ale
                      nasza szansa NIE bije tu kursu bukmachera.
                    </li>
                  )}
                  {sygnal && (
                    <li>
                      <span className="font-medium text-ink">
                        {sygnal.label}:
                      </span>{" "}
                      {sygnal.tytul}
                    </li>
                  )}
                  {w.xi === false && (
                    <li className="text-data-red-ink">
                      <span className="font-medium">raczej poza składem:</span>{" "}
                      według składu (ogłoszonego albo przewidywanego) nie
                      zaczyna meczu. Ta karta powstała wcześniej – lepiej jej
                      nie grać.
                    </li>
                  )}
                  {w.xi === true && (
                    <li className="text-faint">
                      <span className="font-medium">raczej w pierwszym składzie:</span>{" "}
                      tak wynika ze składu – ale bywa on przewidywany przez
                      serwis nawet 36 godzin przed meczem, a nie ogłoszony
                      przez trenera.
                    </li>
                  )}
                </ul>
              )}
              {opis && (
                <p className="mb-4 max-w-prose text-sm leading-relaxed text-ink-soft">
                  {opis}
                </p>
              )}

              {/* TYLKO wybrany typ – karta argumentuje jedną rekomendację,
                  nie wysypuje wszystkich 9 rynków (decyzja produktowa) */}
              <div className="space-y-2.5">
                {(() => {
                  const r =
                    w.rynki.find((x) => x.rynek_kod === w.hero?.rynek_kod) ??
                    w.rynki[0];
                  if (!r) return null;
                  const kontekst = w.ocena?.kontekst ?? r.kontekst;
                  return (
                    <>
                      {kontekst && w.hero && (
                        <Wodospad
                          kontekst={kontekst}
                          rynek={r.rynek}
                          pBazowe={w.hero.p_bazowe}
                          pFinal={w.hero.p_final}
                          kurs={w.hero.kurs}
                          traf={w.hero.traf}
                          z={w.hero.z}
                        />
                      )}
                      <RynekBlok key={r.rynek_kod} r={r} />
                    </>
                  );
                })()}
              </div>

              {w.sezony && w.sezony.length > 0 && (
                <div className="mt-4">
                  <p className="mb-0.5 text-[10px] uppercase tracking-wide text-faint">
                    średnie sezonowe
                  </p>
                  <p className="mb-2 text-[10px] leading-relaxed text-faint">
                    Średnie z całych sezonów – także z poprzedniego klubu
                    i ligi, jeśli zmienił barwy.
                  </p>
                  <div className="space-y-2">
                    {w.sezony.map((s, i) => (
                      <SezonWiersz
                        key={`${s.turniej}-${s.rok}-${i}`}
                        s={s}
                        rynekKod={w.hero?.rynek_kod}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
});
