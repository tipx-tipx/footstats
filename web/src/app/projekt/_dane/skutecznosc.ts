/**
 * Etap 5.5 – Skuteczność (widok klienta) z migawki `wyniki.json`.
 *
 * Liczy się to, co klient widział: bez typów spoza publikacji i bez dalszych
 * szczebli drabinek (tylko 1. szczebel – decyzja 17.09). Zwrot (nie zagrał,
 * mecz przełożony) nie jest ani trafieniem, ani pudłem.
 *
 * Dalsze szczeble nie liczą się do bilansu, ale są POKAZANE przy drabince
 * (właściciel 01.10: „nie ma innych szczebli z kursami”) – `szczeble`.
 */

import { nazwaPodmiotu, opisZakladu } from "@/lib/format";

import { etykietaDnia } from "./przygotuj";
import { dzisZrodla, zrodlo } from "./zrodlo";


export type Produkt = "zawodnicy" | "druzyny" | "drabinki";
export type Wynik = "wygrany" | "przegrany" | "zwrot";

export type TypWyniku = {
  kto: string;
  mecz: string;
  rynek: string;
  strona: string;
  linia: number;
  kurs: number;
  wynik: Wynik;
  faktyczna: number | null;
  produkt: Produkt;
  /** drabinka: wszystkie szczeble od najniższej linii (polecany = ten liczony) */
  szczeble?: { linia: number; kurs: number; wynik: Wynik; polecany: boolean }[];
};

export type DzienWynikow = {
  klucz: string;
  etykieta: string;
  typy: TypWyniku[];
};

type TypS = {
  podmiot: string;
  mecz: string;
  rynek: string;
  rynek_kod: string;
  strona: string;
  linia: number;
  kurs: number;
  wynik: string;
  faktyczna: number | null;
  ekran: string | null;
  szczebel: number | null;
  poza_publikacja: unknown;
  kickoff_ts: number;
};

const produkt = (t: TypS): Produkt =>
  t.ekran === "drabinki" ? "drabinki" : /^(team_|match_)/.test(t.rynek_kod) ? "druzyny" : "zawodnicy";

export function przygotujSkutecznosc() {
  const dni = (zrodlo().wyniki as { skutecznosc_dzienna: { dzien: string; typy: TypS[] }[] }).skutecznosc_dzienna ?? [];
  const kluczDrabinki = (t: TypS) => `${t.mecz}|${t.podmiot}|${t.rynek_kod}`;
  const wynik: DzienWynikow[] = dni
    .map((d) => {
      // wszystkie rozliczone szczeble każdej drabinki dnia (do pokazania, nie do liczenia)
      const szczebleDnia = new Map<string, NonNullable<TypWyniku["szczeble"]>>();
      for (const t of d.typy) {
        if (t.ekran !== "drabinki" || t.poza_publikacja || !["wygrany", "przegrany", "zwrot"].includes(t.wynik)) continue;
        const k = kluczDrabinki(t);
        szczebleDnia.set(k, [...(szczebleDnia.get(k) ?? []), { linia: t.linia, kurs: t.kurs, wynik: t.wynik as Wynik, polecany: (t.szczebel ?? 1) <= 1 }]);
      }
      for (const lista of szczebleDnia.values()) lista.sort((x, y) => x.linia - y.linia);
      return {
      klucz: d.dzien,
      etykieta: etykietaDnia(d.dzien, dzisZrodla()),
      typy: d.typy
        .filter((t) => !t.poza_publikacja && (t.szczebel ?? 1) <= 1 && ["wygrany", "przegrany", "zwrot"].includes(t.wynik))
        .sort((a, b) => a.kickoff_ts - b.kickoff_ts)
        .map(
          (t): TypWyniku => ({
            // „kto więcej”: typowana drużyna i „więcej … niż rywal” zamiast „powyżej 0,0”
            kto: /^match_/.test(t.rynek_kod) ? t.mecz : nazwaPodmiotu(t),
            mecz: t.mecz,
            rynek: t.rynek_kod.startsWith("wiecej_") ? opisZakladu(t) : t.rynek,
            strona: t.rynek_kod.startsWith("wiecej_") ? "" : t.strona,
            linia: t.linia,
            kurs: t.kurs,
            wynik: t.wynik as Wynik,
            faktyczna: t.faktyczna ?? null,
            produkt: produkt(t),
            szczeble: produkt(t) === "drabinki" ? szczebleDnia.get(kluczDrabinki(t)) : undefined,
          }),
        ),
    };
    })
    .filter((d) => d.typy.length);
  return { dni: wynik, start: "14.09" };
}

export type DaneSkutecznosci = ReturnType<typeof przygotujSkutecznosc>;
