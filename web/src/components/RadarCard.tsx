"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { memo, useState } from "react";

import { fmtKurs, fmtProc } from "@/lib/format";
import type {
  RadarCzynnik,
  RadarKontekst,
  RadarRynek,
  RadarSezon,
  RadarSzczebel,
  RadarWpis,
} from "@/lib/types";

/** Linia 0,5 to po ludzku „1 lub więcej" — tak mówi też Superbet. */
const linLabel = (linia: number) => `${Math.ceil(linia)}+`;

/** Klasa jakości karty (backend: radar._klasa_karty) — jedyne źródło oceny. */
const KLASY: Record<
  string,
  { label: string; badge: string; tytul: string }
> = {
  top: {
    label: "TOP",
    badge: "bg-data-green text-white",
    tytul:
      "Najwyższa przewaga nad kursem w dzisiejszej stawce, po uwzględnieniu rywala, sędziego i scenariusza meczu. Nie gwarancja — po prostu najlepsze, co dziś mamy.",
  },
  mocny: {
    label: "mocny",
    badge: "bg-data-green-wash text-data-green-ink",
    tytul:
      "Wyraźna przewaga nad kursem po korekcie na kontekst meczu, ale poza czubem dzisiejszej stawki.",
  },
  solidny: {
    label: "solidny",
    badge: "border border-hairline bg-paper text-muted",
    tytul:
      "Przewaga nad kursem jest dodatnia, ale skromna — karta przeszła bramy jakości i tyle.",
  },
};

/**
 * NA CZYM STOI KARTA (backend: radar._kategoria_karty). Osobna oś od klasy
 * jakości: klasa mówi „jak dobry jest typ", kategoria — „na jakim dowodzie
 * stoi". Dlatego kategoria dostaje PASEK przy krawędzi karty, a nie kolejną
 * plakietkę obok klasy — inaczej nagłówek robi się jarmarkiem.
 */
const KATEGORIE: Record<
  string,
  { label: string; pasek: string; badge: string; tytul: string }
> = {
  analiza: {
    label: "analiza",
    pasek: "bg-hairline-strong",
    badge: "border border-hairline bg-paper text-muted",
    tytul:
      "Karta stoi wyłącznie na naszej analizie: pokrycie linii, forma, minuty, rywal i scenariusz meczu. Drugiego cennika na tę linię nie mamy — albo Betclic nie prowadzi tego meczu, albo nie wystawił tego rynku.",
  },
  rynek_zgodny: {
    label: "rynek zgodny",
    pasek: "bg-brand-bright",
    badge: "bg-brand-wash text-brand-deep",
    tytul:
      "Drugi bukmacher wycenia to niemal identycznie. Nie ma tu okazji cenowej, ale jest potwierdzenie: obie księgi widzą to tak samo, więc nasza linia nie jest wzięta z sufitu.",
  },
  rozjazd: {
    label: "lepsza cena",
    pasek: "bg-data-amber",
    badge: "bg-data-amber-wash text-data-amber-ink",
    tytul:
      "Za to samo zdarzenie jeden bukmacher płaci zauważalnie więcej niż drugi. Gra się tam, gdzie płacą więcej — przy tej samej analizie dostajesz lepszą cenę. Sama różnica kursów NIE jest powodem, dla którego ta karta tu jest: najpierw musiała przejść całą analizę.",
  },
  pewniak_taniej: {
    label: "cena mówi: pewne",
    pasek: "bg-data-amber",
    badge: "bg-data-amber text-white",
    tytul:
      "Jeden bukmacher wycenia to jako niemal pewne (kurs poniżej 1,45), a drugi płaci za to samo 1,75 lub więcej. UWAGA: to opinia RYNKU o pewności, nie nasza gwarancja — i nie ona zdecydowała o tej karcie. Karta i tak musiała przejść pokrycie linii, formę, minuty, rywala i scenariusz meczu; różnica cen jest dodatkowym dowodem, nie przepustką.",
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

/** Plakietka sygnału — tylko dla wpisów Z SYGNAŁEM (zwykła drabinka bez). */
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
        "Superbet daje mu pełne kursy, ale w danych nie ma ani jednego jego meczu — rynek wycenia go w ciemno. Sprawdź sam, skąd przyszedł, zanim postawisz.",
    };
  }
  if (w.rodzaj === "forma") {
    return {
      label: "seria formy",
      dioda: "bg-data-green",
      badge: "bg-data-green-wash text-data-green-ink",
      tytul:
        "Zawodnik regularnie przebija linię w ostatnich meczach, wyraźnie ponad swój wcześniejszy poziom. Model celowo nie dolicza formy do szansy — to sygnał dodatkowy.",
    };
  }
  if (w.rodzaj === "bez_feedu") {
    return {
      label: "same kursy",
      dioda: "bg-ink/25",
      badge: "border border-hairline bg-paper text-muted",
      tytul:
        "Ta liga nie jest objęta feedem statystyk meczowych, więc nie mamy historii ostatnich występów. Pokazujemy kursy Superbetu, a tam gdzie się udało — średnie z całych sezonów.",
    };
  }
  return null;
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
    return "Superbet wystawił mu komplet kursów, choć my nie mamy o nim żadnych statystyk — bukmacher też strzela.";
  }
  if (w.rodzaj === "bez_feedu") {
    return w.sezony?.length
      ? `Kursy Superbetu i średnie z ${w.sezony.length} ${w.sezony.length === 1 ? "sezonu" : "sezonów"}. Meczu po meczu tu nie pokażemy — z tej ligi nie mamy takich danych.`
      : "Same kursy Superbetu. Z tej ligi nie mamy statystyk mecz po meczu.";
  }
  if (w.rodzaj === "transfer") {
    return w.stara_liga
      ? `Historia z poprzedniej ligi: ${w.stara_liga}. Kurs może tego nie uwzględniać.`
      : "Świeży transfer — historia z poprzedniego klubu.";
  }
  return "Drabinka kursów z pełną historią jego występów.";
}

/** Akapit „dlaczego ta karta" w rozwinięciu — tylko wpisy z sygnałem. */
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
        `${nowa}. Liczby niżej pochodzą głównie ze starego adresu — kurs może tego nie uwzględniać.`
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
      "Rozgrywki tego meczu nie są objęte feedem statystyk meczowych, więc nie pokazujemy ostatnich występów ani formy — to nie znaczy, że zawodnik jest nieznany. " +
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

/** Jeden wiersz wodospadu: co zmieniło szansę i o ile. */
function CzynnikWiersz({
  etykieta,
  opis,
  mnoznik,
  tytul,
}: {
  etykieta: string;
  opis: string;
  mnoznik?: number | null;
  tytul?: string;
}) {
  const zmiana = pctZmiana(mnoznik);
  return (
    <div
      className="flex items-baseline justify-between gap-3 py-1"
      title={tytul}
    >
      <span className="min-w-0 text-[11px] text-muted">
        <span className="text-faint">{etykieta}</span> {opis}
      </span>
      <span
        className={`font-data shrink-0 text-[11px] font-semibold ${
          zmiana == null
            ? "text-faint"
            : mnoznik! > 1
              ? "text-data-green-ink"
              : "text-data-amber-ink"
        }`}
      >
        {zmiana ?? "bez zmian"}
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
  const miejsce =
    r.rank != null && r.z != null ? ` (#${r.rank} z ${r.z} w lidze)` : "";
  const zrodlo =
    r.zrodlo === "historia_pokrewny"
      ? " — z rynku pokrewnego, więc z połową siły"
      : r.zrodlo === "historia"
        ? ` — z ${r.mecze ?? 0} meczów w naszych danych`
        : "";
  return `${rynek.toLowerCase()}: rywal dopuszcza ${skala}${miejsce}${zrodlo}`;
}

/**
 * „Dlaczego" — wodospad od surowego pokrycia do szansy po kontekście.
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
        dlaczego ta linia
      </p>
      <div className="mt-1.5 divide-y divide-hairline">
        <CzynnikWiersz
          etykieta="historia"
          opis={`trafione ${traf} z ${z} ostatnich meczów`}
          tytul="Punkt wyjścia: surowe pokrycie linii, ściągnięte w dół karą za krótką próbę."
        />
        {opisR && (
          <CzynnikWiersz
            etykieta="rywal"
            opis={opisR}
            mnoznik={rywal?.mnoznik}
            tytul="Ile najbliższy przeciwnik przeciętnie dopuszcza NA TYM rynku w porównaniu ze średnią ligi. Szczelna defensywa ścina szansę, hojna podbija."
          />
        )}
        {sedzia?.zrodlo === "brak_obsady" ? (
          <CzynnikWiersz
            etykieta="sędzia"
            opis="nie wiadomo jeszcze, kto sędziuje — nic z tego tytułu nie zmieniamy"
            tytul="Arbitrzy różnią się liczbą odgwizdanych fauli. Obsada jest znana zwykle 1–2 dni przed meczem; dopóki jej nie ma, nie zgadujemy."
          />
        ) : sedzia?.sedzia ? (
          <CzynnikWiersz
            etykieta="sędzia"
            opis={`${sedzia.sedzia}: ${
              (sedzia.mnoznik ?? 1) > 1 ? "gwiżdże dużo" : "pobłażliwy"
            }${sedzia.mecze ? ` (${sedzia.mecze} meczów)` : ""}`}
            mnoznik={sedzia.mnoznik}
            tytul="Profil arbitra: faule w jego meczach vs faule oczekiwane po tych drużynach. Liczy się tylko przy rynkach faulowych i kartkowych."
          />
        ) : null}
        {scen?.mnoznik != null && (
          <CzynnikWiersz
            etykieta="mecz"
            opis={`${scen.faworyt ? "faworyt" : "underdog"}${
              scen.total != null ? `, oczekiwane ${liczba(scen.total)} gola` : ""
            }`}
            mnoznik={scen.mnoznik}
            tytul="Scenariusz meczu odczytany z kursów 1X2 i liczby goli: otwarty mecz to więcej strzałów, wyraźny faworyt spycha rywala do głębokiej obrony."
          />
        )}
        {dom?.mnoznik != null && (
          <CzynnikWiersz
            etykieta="boisko"
            opis={dom.dom ? "u siebie" : "na wyjeździe"}
            mnoznik={dom.mnoznik}
            tytul="Gospodarze średnio częściej strzelają i rzadziej faulują niż goście."
          />
        )}
        {sezony?.mnoznik != null && (
          <CzynnikWiersz
            etykieta="sezony"
            opis={`średnia z całych sezonów ${liczba(
              sezony.sezon90 ?? 0,
            )}/90 wobec ${liczba(sezony.okno90 ?? 0)}/90 z ostatnich meczów`}
            mnoznik={sezony.mnoznik}
            tytul="Kilkadziesiąt meczów sezonu waży więcej niż dziesięć ostatnich: jeśli sezon mówi mniej niż bieżące okno, to okno jest najpewniej szczytem formy."
          />
        )}
      </div>
      {pFinal != null && (
        <p className="mt-2 border-t border-hairline pt-2 text-[11px] text-ink-soft">
          szansa po kontekście{" "}
          <span className="font-data font-semibold text-ink">
            {fmtProc(pFinal)}
          </span>
          {cenaRynku != null && (
            <>
              {" "}
              wobec kursu {fmtKurs(kurs)} ={" "}
              <span className="font-data text-faint">
                {fmtProc(cenaRynku)}
              </span>
              {przewaga != null && (
                <span
                  className={`font-data font-semibold ${
                    przewaga > 0 ? "text-data-green-ink" : "text-data-amber-ink"
                  }`}
                  title="O ile nasza szansa jest wyższa od tej, którą wycenia kurs. Na plusie znaczy, że naszym zdaniem bukmacher płaci za dużo."
                >
                  {" "}
                  ({przewaga > 0 ? "+" : "−"}
                  {Math.abs(przewaga)} pkt proc.)
                </span>
              )}
            </>
          )}
          {pBazowe != null && (
            <span className="block text-faint">
              z samej historii wychodziło {fmtProc(pBazowe)} — resztę zmieniło to,
              co czeka go w tym meczu
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Wiersz szczebla drabinki: linia · kurs · szansa modelu · pokrycie. */
function SzczebelWiersz({ r, s }: { r: RadarRynek; s: RadarSzczebel }) {
  const p = s.pokrycie;
  const udzial = p && p.z > 0 ? p.traf / p.z : null;
  return (
    <div
      className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] items-center gap-x-3 py-1"
      title={
        `${r.rynek}: ${linLabel(s.linia)} po kursie ${fmtKurs(s.kurs)}` +
        (p ? `. Linia trafiona w ${p.traf} z ${p.z} ostatnich meczów` : "") +
        (s.p_final != null
          ? `. Po korekcie na ten mecz dajemy jej ${fmtProc(s.p_final)} szans` +
            (s.p_bazowe != null
              ? ` (samo pokrycie: ${fmtProc(s.p_bazowe)})`
              : "") +
            (s.strzyzenie_modelu
              ? ". Szansa ścięta, bo model widzi tę linię ciemniej niż historia"
              : "")
          : s.p_model != null
            ? `. Model daje tej linii ${fmtProc(s.p_model)} szans`
            : ". Za mało danych, żeby policzyć szansę")
      }
    >
      <span className="font-data text-xs font-semibold text-ink">
        {linLabel(s.linia)}
      </span>
      <span className="font-data text-xs font-semibold text-brand-deep">
        {fmtKurs(s.kurs)}
        {/* druga cena POD pierwszą, a nie w nowej kolumnie — na telefonie
            piąta kolumna rozpychała wiersz w bok */}
        {s.rozjazd && (
          <span
            title={
              `Betclic płaci za to samo ${fmtKurs(s.rozjazd.betclic)}, ` +
              `Superbet ${fmtKurs(s.rozjazd.superbet)} — różnica ` +
              `${Math.round(s.rozjazd.przewaga_pct)}%. Gra się tam, gdzie ` +
              `płacą więcej` +
              (s.rozjazd.typ === "pewniak_taniej"
                ? ". Tańsza cena mówi: to niemal pewne — najcenniejszy układ."
                : ".")
            }
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
            : "—"}
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
 * Mecz po meczu, zdaniami — nie samym ciągiem liczb.
 *
 * Wzorzec, który user przysłał jako docelowy dla Drabinek, opisuje KAŻDY mecz
 * osobno („3 strzały zza pola vs Radomiak", „1 strzał vs Miedź, 40 minut gry").
 * Dopiero taki zapis pozwala odróżnić zero po pełnym meczu od zera po wejściu
 * z ławki — a to zupełnie inna informacja o zawodniku.
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
                title={
                  krotki
                    ? "Krótki występ — z tej liczby niewiele wynika"
                    : undefined
                }
              >
                {min} min
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
          {r.forma && (
            <span
              className="font-data text-[11px]"
              title="Ile notował na 90 minut w 6 ostatnich meczach w porównaniu z wcześniejszym okresem"
            >
              <span
                className={
                  r.forma.okno90 > r.forma.baza90
                    ? "font-semibold text-data-green-ink"
                    : r.forma.okno90 < r.forma.baza90
                      ? "font-semibold text-data-amber-ink"
                      : "text-muted"
                }
              >
                {r.forma.okno90 > r.forma.baza90
                  ? "forma ↑"
                  : r.forma.okno90 < r.forma.baza90
                    ? "forma ↓"
                    : "forma ="}{" "}
                {liczba(r.forma.okno90)}/90
              </span>{" "}
              <span className="text-faint">
                (baza {liczba(r.forma.baza90)})
              </span>
            </span>
          )}
          {r.srednia90 != null && (
            <span
              className="font-data text-[11px] text-muted"
              title="Ile notował średnio na 90 minut przez całą historię, jaką mamy"
            >
              śr. {liczba(r.srednia90)}/90
            </span>
          )}
        </span>
      </div>

      {/* drabinka: linia · kurs · model · pokrycie ostatnich */}
      <div className="mt-2">
        <div className="grid grid-cols-[2.4rem_3.2rem_3rem_1fr] gap-x-3 border-b border-hairline pb-1 text-[9px] uppercase tracking-wide text-faint">
          <span>linia</span>
          <span>kurs</span>
          <span title="Nasza szansa, że przebije tę linię akurat w tym meczu. Zaczynamy od tego, jak często robił to ostatnio, a potem poprawiamy o rywala, sędziego, przewidywany przebieg meczu i formę.">
            szansa
          </span>
          <span title="W ilu z ostatnich meczów przebił tę linię">
            trafienia w ost. meczach
          </span>
        </div>
        {r.drabinka.map((s) => (
          <SzczebelWiersz key={s.linia} r={r} s={s} />
        ))}
      </div>

      {r.ostatnie && r.ostatnie.length > 0 && (
        <div className="mt-2.5">
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-[9px] uppercase tracking-wide text-faint">
              ostatnie
            </span>
            {r.ostatnie.map((c, i) => (
              <span
                key={i}
                title={`${c} vs ${r.rywale?.[i] ?? "?"}${
                  r.minuty?.[i] != null ? ` (${r.minuty[i]} min)` : ""
                }`}
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
              ale nazwa rywala i minuty nie mogą siedzieć w dymku — to jest
              treść, po którą czyta się rozwinięcie. Krótkie występy
              wyróżniamy, bo „0 strzałów" po 20 minutach znaczy co innego niż
              po pełnym meczu. */}
          <RywaleMeczPoMeczu r={r} />
        </div>
      )}

      {r.rywal?.srednia != null && (
        <p
          className="mt-2 text-[11px] text-muted"
          title="Ile najbliższy rywal średnio pozwala rywalom na tym rynku i które to miejsce w lidze. Uwaga: miejsce 1 ma drużyna, która pozwala NAJMNIEJ, a nie najwięcej."
        >
          rywal puszcza śr.{" "}
          <span className="font-data font-semibold text-ink-soft">
            {liczba(r.rywal.srednia)}
          </span>
          {r.rywal.rank != null && r.rywal.z != null && (
            <span className="text-faint">
              {" "}
              (#{r.rywal.rank} z {r.rywal.z} w lidze)
            </span>
          )}
          {r.rywal.liga != null && (
            <span className="text-faint">
              {" "}
              · śr. ligi {liczba(r.rywal.liga)}
            </span>
          )}
        </p>
      )}
    </div>
  );
}

/** Wiersz sezonu: liga, rok, mecze i średnia — TYLKO dla wybranego rynku. */
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
          <span
            key={mk}
            className="font-data text-[11px] text-ink-soft"
            title={
              s.na90[mk] != null
                ? `${SEZON_RYNKI_PL[mk]}: ${liczba(v)} na mecz, ${liczba(s.na90[mk])} na 90 minut`
                : `${SEZON_RYNKI_PL[mk]}: ${liczba(v)} na mecz`
            }
          >
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
  // „analiza" bez paska i plakietki — to stan domyślny, a etykieta na każdej
  // karcie przestaje cokolwiek znaczyć (ta sama zasada co przy „solidny")
  const kat =
    w.kategoria && w.kategoria !== "analiza" ? KATEGORIE[w.kategoria] : null;

  return (
    <motion.article
      layout={!reduced}
      className="relative overflow-hidden rounded-(--radius-card) border border-hairline bg-card shadow-(--shadow-card) transition-[border-color,box-shadow] duration-200 hover:border-brand/30 hover:shadow-(--shadow-card-hover)"
    >
      {/* pasek kategorii przy krawędzi — skanuje się wzrokiem, bez czytania */}
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
                <span
                  title={sygnal.tytul}
                  className="relative inline-flex h-2 w-2 shrink-0 translate-y-px items-center justify-center"
                >
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

          <span className="flex flex-col items-end justify-center gap-1">
            {kat && (
              <span
                title={kat.tytul}
                className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${kat.badge}`}
              >
                {kat.label}
                {w.rozjazd_pewniak || w.rozjazd_hero ? (
                  <span className="ml-1 opacity-80">
                    +
                    {Math.round(
                      (w.rozjazd_pewniak ?? w.rozjazd_hero)!.przewaga_pct,
                    )}
                    %
                  </span>
                ) : null}
              </span>
            )}
            {klasa && (
              <span
                title={klasa.tytul}
                className={`font-data inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ${klasa.badge}`}
              >
                {klasa.label}
                {w.ocena?.miejsce != null && w.ocena.klasa === "top" && (
                  <span className="opacity-70">#{w.ocena.miejsce}</span>
                )}
              </span>
            )}
            {/* NA CZYM STOI KARTA. Od 2026-07-30 karta może wejść z dwóch
                powodów: przewagi nad kursem albo mocnej serii przy grywalnej
                cenie. Druga ścieżka nie ma prawa udawać pierwszej, więc
                mówimy o niej wprost — to jest ta sama zasada, co przy
                „różnica kursów to dowód, nie przepustka". */}
            {w.ocena?.powod_wejscia === "seria" && (
              <span
                title="Karta stoi na serii, nie na przewadze: zawodnik regularnie przebija tę linię, a cena jest grywalna. Nasza szansa NIE bije tu kursu bukmachera — to wzorzec z ostatnich meczów, nie wycena."
                className="font-data inline-flex items-center rounded-full bg-paper px-2.5 py-0.5 text-xs font-semibold text-ink-soft"
              >
                mocna seria
              </span>
            )}
            {sygnal && (
              <span
                title={sygnal.tytul}
                className={`font-data inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${sygnal.badge}`}
              >
                {sygnal.label}
              </span>
            )}
            {/* SKŁAD TO PRZEWIDYWANIE, NIE PEWNIK (zgłoszenie usera 2026-07-27).
                Sygnał bierze się ze składu OGŁOSZONEGO albo PRZEWIDYWANEGO
                (algorytm serwisu, nawet 36 h przed meczem) i karta nie umie ich
                dziś rozróżnić. Skoro część z tego to prognoza, napis mówi
                „raczej", a nie stawia tezy o decyzji trenera. */}
            {w.xi === true && (
              <span
                className="text-[9px] uppercase tracking-wide text-faint"
                title="Według składu (ogłoszonego albo przewidywanego) zaczyna mecz"
              >
                raczej 1. skład
              </span>
            )}
            {w.xi === false && (
              <span
                className="rounded-full bg-data-red-wash px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-data-red-ink"
                title="Według składu (ogłoszonego albo przewidywanego) nie zaczyna meczu. Ta karta powstała wcześniej — lepiej jej nie grać."
              >
                raczej poza 1. składem
              </span>
            )}
          </span>
        </span>

        {/* UKŁAD „PEWNIAK TANIEJ" — najcenniejszy rodzaj rozjazdu, więc mówimy
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
            — o {Math.round(w.rozjazd_pewniak.przewaga_pct)}% więcej za to samo.
            <span className="mt-0.5 block text-[10px] opacity-80">
              To ocena rynku, nie gwarancja — karta stoi na analizie, a różnica
              cen jest do niej dodatkiem.
            </span>
          </span>
        )}

        {/* zajawka z konkretem + rozwinięcie */}
        <span className="flex items-center gap-x-2.5 px-4 pb-3.5 sm:px-5">
          <span className="min-w-0 truncate text-[11px] font-medium text-ink-soft">
            {zajawka(w)}
          </span>
          <span className="ml-auto flex shrink-0 items-center gap-1 text-[10px] uppercase tracking-wide text-faint">
            {open ? "zwiń" : "analiza"}
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
              {opis && (
                <p className="mb-4 max-w-prose text-sm leading-relaxed text-ink-soft">
                  {opis}
                </p>
              )}

              {/* TYLKO wybrany typ — karta argumentuje jedną rekomendację,
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
                  <p
                    className="mb-2 text-[10px] uppercase tracking-wide text-faint"
                    title="Średnie z całych sezonów, także z poprzedniego klubu i ligi, jeśli zmienił barwy"
                  >
                    średnie sezonowe
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
