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
  "shots_outside_box",
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
  /** true = w przewidywanym pierwszym składzie (sortowany na górę) */
  xi: boolean;
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
  /** ile z 5 startów to mecze reprezentacji (0–1 = rzadko w kadrze) */
  kadraLiczba: number;
  /** kurs Superbet dla tej linii (strona „powyżej"), jeśli jest */
  kurs: number | null;
}

/**
 * Ranga trafności zawodnika na mecz REPREZENTACJI:
 *  0 = potwierdzony/przewidywany skład (xi),
 *  1 = regularny w kadrze (≥2 z ostatnich startów w reprezentacji),
 *  2 = rzadko w kadrze / forma klubowa (0–1 startu w reprezentacji).
 * Sortujemy najpierw po randze (regularni na górę), potem po pokryciu.
 */
function ranga(w: WierszPokrycia): number {
  if (w.xi) return 0;
  if (w.kadraLiczba >= 2) return 1;
  return 2;
}

/**
 * Wiersze TOP POKRYCIA dla zawodników meczu (już odfiltrowanych po drużynie),
 * posortowane: najlepsze pokrycie → wyższa linia → lepszy kurs.
 */
/** Zawodnik po scaleniu duplikatów — trzyma wszystkie źródłowe ID (do kursów). */
type ZawodnikScalony = Zawodnik & { ids: number[] };

const _norm = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z ]/g, "")
    .trim();

/**
 * Statshub bywa zwraca tego samego zawodnika pod kilkoma ID, z ROZBITĄ formą
 * (jeden rekord ma strzały, inny faule) i różną flagą składu — przez co ten
 * sam gracz pojawiał się raz z „XI", raz bez. Scalamy po nazwisku+drużynie:
 * suma rynków (rynek z większą próbką wygrywa), xi = OR, wszystkie ID zebrane
 * (kursy szukamy po każdym z nich).
 */
function scalDuplikaty(zawodnicy: Zawodnik[]): ZawodnikScalony[] {
  const map = new Map<string, ZawodnikScalony>();
  for (const z of zawodnicy) {
    const key = `${_norm(z.nazwa)}|${z.druzyna}`;
    const cur = map.get(key);
    if (!cur) {
      map.set(key, {
        ...z,
        forma: { ...z.forma },
        xi: z.xi === true,
        ids: [z.id],
      });
      continue;
    }
    cur.ids.push(z.id);
    if (z.xi === true) cur.xi = true;
    for (const [mk, f] of Object.entries(z.forma ?? {})) {
      const ist = cur.forma[mk];
      if (!ist || (f.ostatnie?.length ?? 0) > (ist.ostatnie?.length ?? 0)) {
        cur.forma[mk] = f;
      }
    }
  }
  return [...map.values()];
}

export function topPokrycia(
  zawodnicy: Zawodnik[],
  meczId: number,
  odds: OddsSuperbet,
): WierszPokrycia[] {
  const oddsMecz = odds?.[String(meczId)] ?? {};
  const rows: WierszPokrycia[] = [];

  for (const z of scalDuplikaty(zawodnicy)) {
    // kursy zbierane ze WSZYSTKICH ID duplikatu (rynek->linia->kurs)
    const oddsGracz: Record<string, Record<string, number>> = {};
    for (const id of z.ids) {
      const o = oddsMecz[String(id)];
      if (!o) continue;
      for (const [mk, linie] of Object.entries(o)) {
        oddsGracz[mk] = { ...(oddsGracz[mk] ?? {}), ...linie };
      }
    }
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
          xi: z.xi === true,
          rynek_kod: kod,
          rynek: RYNEK_LABEL[kod] ?? kod,
          linia,
          prog,
          ostatnie: starty,
          pokryte,
          probka: starty.length,
          kadraLiczba: starty.filter((g) => g.kadra).length,
          kurs: oddsGracz[kod]?.[String(linia)] ?? null,
        });
      }
    }
  }

  rows.sort(
    (a, b) =>
      // regularni w kadrze / przewidywany skład na górę, potem pokrycie
      ranga(a) - ranga(b) ||
      b.pokryte - a.pokryte ||
      b.linia - a.linia ||
      (b.kurs ?? 0) - (a.kurs ?? 0),
  );
  // deduplikacja: statshub bywa duplikuje zawodnika (ten sam gracz, inny rekord)
  // — jeden zawodnik/rynek/linia tylko raz (zostaje najlepszy po sortowaniu)
  const seen = new Set<string>();
  return rows.filter((w) => {
    const key = `${w.zawodnik}|${w.rynek_kod}|${w.linia}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
