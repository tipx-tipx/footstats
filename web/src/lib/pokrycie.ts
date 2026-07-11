/**
 * TOP POKRYCIA — zawodnicy z najlepszym pokryciem historycznym danej linii.
 *
 * Liczone z players.json → forma[rynek].ostatnie (surowe wartości statystyki
 * mecz po meczu, NAJNOWSZY PIERWSZY). Bierzemy ostatnie 5 ROZEGRANYCH meczów
 * (filtr DNP po minutach), sprawdzamy pokrycie linii +0.5/+1.5/+2.5 i zostawiamy
 * te z pokryciem ≥ 3/5 (60%). Kurs Superbet dołączamy z siatki odds_superbet.
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
const PROBKA = 5; // ostatnie 5 rozegranych
const MIN_POKRYTE = 3; // ≥ 3/5 = 60%

export interface WierszPokrycia {
  player_id: number;
  zawodnik: string;
  druzyna: string;
  rynek_kod: string;
  rynek: string;
  linia: number;
  /** próg pokrycia dla tej linii (0.5→1, 1.5→2, 2.5→3) */
  prog: number;
  /** ostatnie N rozegranych (najnowszy pierwszy) — surowe wartości */
  ostatnie: number[];
  /** ile z próbki pokryło linię */
  pokryte: number;
  probka: number;
  /** kurs Superbet dla tej linii (strona „powyżej"), jeśli jest */
  kurs: number | null;
}

/**
 * Zwraca wiersze TOP POKRYCIA dla zawodników danego meczu (już odfiltrowanych
 * po drużynie), posortowane: najlepsze pokrycie → wyższa linia → lepszy kurs.
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
      // ostatnie 5 ROZEGRANYCH (minuty > 0), najnowszy pierwszy
      const grane: number[] = [];
      for (let i = 0; i < f.ostatnie.length && grane.length < PROBKA; i++) {
        if ((f.minuty?.[i] ?? 0) > 0) grane.push(f.ostatnie[i]);
      }
      if (grane.length < PROBKA) continue; // za mało rozegranych meczów
      for (const linia of LINIE) {
        const prog = Math.ceil(linia); // 0.5→1, 1.5→2, 2.5→3
        const pokryte = grane.filter((v) => v >= prog).length;
        if (pokryte < MIN_POKRYTE) continue;
        rows.push({
          player_id: z.id,
          zawodnik: z.nazwa,
          druzyna: z.druzyna,
          rynek_kod: kod,
          rynek: RYNEK_LABEL[kod] ?? kod,
          linia,
          prog,
          ostatnie: grane,
          pokryte,
          probka: PROBKA,
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
