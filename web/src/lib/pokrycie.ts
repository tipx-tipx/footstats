/**
 * TOP POKRYCIA — zawodnicy z najlepszym pokryciem linii w ostatnich meczach.
 *
 * Reguła (wg ustaleń z użytkownikiem): bierzemy ostatnie 5 meczów, w których
 * zawodnik ZACZYNAŁ w pierwszym składzie (dowolne rozgrywki — klub lub kadra),
 * i liczymy, ile z nich pokryło linię +0.5/+1.5/+2.5. Zostają pokrycia ≥ 2/5
 * (40%). „Start" przybliżamy przez minuty ≥ 60 — tak samo jak pipeline
 * (statshub.py: started = minutesPlayed >= 60). Kurs Superbet z siatki odds.
 */

import type { OddsSuperbet, Zawodnik } from "./types";

/** Etykiety rynków (kod → nazwa PL) — zgodne z pipeline MARKET_NAMES_PL. */
export const RYNEK_LABEL: Record<string, string> = {
  shots: "Strzały",
  sot: "Strzały celne",
  shots_off_target: "Strzały niecelne",
  shots_blocked: "Strzały zablokowane",
  shots_outside_box: "Strzały zza pola",
  sot_outside_box: "Celne zza pola",
  headed_shots: "Strzały głową",
  headed_sot: "Celne głową",
  fouls_committed: "Faule popełnione",
  fouls_won: "Faule wywalczone",
  tackles: "Odbiory",
  interceptions: "Przechwyty",
  offsides: "Spalone",
};

/** Rynki brane pod uwagę w TOP POKRYCIA (kolejność = domyślny priorytet). */
const RYNKI_POKRYCIA = [
  "shots",
  "sot",
  "shots_off_target",
  "shots_blocked",
  "fouls_committed",
  "fouls_won",
  "tackles",
  "interceptions",
];

const LINIE = [0.5, 1.5, 2.5];
const PROBKA = 5; // ostatnie 5 startów
const PROG_STARTU = 60; // minuty ≥ 60 = zaczynał w składzie (jak w pipeline)
const MIN_POKRYTE = 2; // ≥ 2/5 = 40%

/** Jedna gra w próbce: wartość statystyki + kontekst (z kim, ile minut). */
export interface GraForma {
  v: number;
  /** rywal w tym meczu (może brakować) */
  rywal: string | null;
  /** minuty w tym meczu (≥ 60 = start) */
  minuty: number;
  /** true = mecz reprezentacji; false = klub */
  kadra: boolean;
}

export interface WierszPokrycia {
  player_id: number;
  zawodnik: string;
  druzyna: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  /** próg pokrycia dla tej linii (0.5→1, 1.5→2, 2.5→3) */
  prog: number;
  /** ostatnie 5 startów (najnowszy pierwszy) z kontekstem */
  ostatnie: GraForma[];
  /** ile z próbki pokryło linię */
  pokryte: number;
  probka: number;
  /** kurs Superbet dla tej linii (strona „powyżej"), jeśli jest */
  kurs: number | null;
}

/**
 * Wiersze TOP POKRYCIA dla zawodników meczu (już odfiltrowanych po drużynie),
 * posortowane: najlepsze pokrycie → wyższa linia → lepszy kurs.
 */
export function topPokrycia(
  zawodnicy: Zawodnik[],
  meczId: number,
  odds: OddsSuperbet,
): WierszPokrycia[] {
  const oddsMecz = odds?.[String(meczId)] ?? {};
  const rows: WierszPokrycia[] = [];

  for (const z of zawodnicy) {
    const oddsGracz = oddsMecz[String(z.id)] ?? {};
    for (const kod of RYNKI_POKRYCIA) {
      const f = z.forma?.[kod];
      if (!f) continue;
      // ostatnie 5 STARTÓW (minuty ≥ 60), najnowszy pierwszy, z kontekstem
      const starty: GraForma[] = [];
      for (let i = 0; i < f.ostatnie.length && starty.length < PROBKA; i++) {
        const min = f.minuty?.[i] ?? 0;
        if (min >= PROG_STARTU) {
          starty.push({
            v: f.ostatnie[i],
            rywal: f.rywale?.[i] ?? null,
            minuty: min,
            kadra: f.kadra?.[i] === true,
          });
        }
      }
      if (starty.length < PROBKA) continue; // za mało meczów w składzie
      for (const linia of LINIE) {
        const prog = Math.ceil(linia); // 0.5→1, 1.5→2, 2.5→3
        const pokryte = starty.filter((g) => g.v >= prog).length;
        if (pokryte < MIN_POKRYTE) continue;
        rows.push({
          player_id: z.id,
          zawodnik: z.nazwa,
          druzyna: z.druzyna,
          rynek_kod: kod,
          rynek: RYNEK_LABEL[kod] ?? kod,
          linia,
          prog,
          ostatnie: starty,
          pokryte,
          probka: starty.length,
          kurs: oddsGracz[kod]?.[String(linia)] ?? null,
        });
      }
    }
  }

  rows.sort(
    (a, b) =>
      b.pokryte - a.pokryte ||
      b.linia - a.linia ||
      (b.kurs ?? 0) - (a.kurs ?? 0),
  );
  return rows;
}
