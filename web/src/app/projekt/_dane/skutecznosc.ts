/**
 * Etap 5.5 – Skuteczność (widok klienta) z migawki `wyniki.json`.
 *
 * Liczy się to, co klient widział: bez typów spoza publikacji i bez dalszych
 * szczebli drabinek (tylko 1. szczebel) – ta sama reguła co
 * `okrojDlaKlienta` + `strumienieZDni` w produkcji. Zwrot (nie zagrał,
 * mecz przełożony) nie jest ani trafieniem, ani pudłem.
 */

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
  const wynik: DzienWynikow[] = dni
    .map((d) => ({
      klucz: d.dzien,
      etykieta: etykietaDnia(d.dzien, dzisZrodla()),
      typy: d.typy
        .filter((t) => !t.poza_publikacja && (t.szczebel ?? 1) <= 1 && ["wygrany", "przegrany", "zwrot"].includes(t.wynik))
        .sort((a, b) => a.kickoff_ts - b.kickoff_ts)
        .map(
          (t): TypWyniku => ({
            kto: /^match_/.test(t.rynek_kod) ? t.mecz : t.podmiot,
            mecz: t.mecz,
            rynek: t.rynek,
            strona: t.strona,
            linia: t.linia,
            kurs: t.kurs,
            wynik: t.wynik as Wynik,
            faktyczna: t.faktyczna ?? null,
            produkt: produkt(t),
          }),
        ),
    }))
    .filter((d) => d.typy.length);
  return { dni: wynik, start: "14.09" };
}

export type DaneSkutecznosci = ReturnType<typeof przygotujSkutecznosc>;
