/**
 * Generator kuponów NA ŻĄDANIE (klient) — wierny port beam searchu z
 * pipeline/footstats/model/kupony.py. Składa kupon z PRZEANALIZOWANEJ puli
 * legów (legi_pool z Supabase) natychmiast, bez czekania na cykl.
 *
 * Ta sama funkcja celu co backend: maksymalna szansa kuponu przy kursie w
 * przedziale, z premią za WARTOŚĆ (ev_uk/miękka/matchup wg profilu), karami
 * korelacji legów z jednego meczu i dywersyfikacją rodzin rynków.
 */

import type { LegPool, Strona } from "./types";

export type Profil = "bezpieczny" | "zbalansowany" | "agresywny";
export interface Kary {
  ta_sama: number;
  przeciwne: number;
  nieznane: number;
}
export const KARY_DEFAULT: Kary = { ta_sama: 0.92, przeciwne: 0.97, nieznane: 0.95 };

const WAGA_VALUE_Q: Record<Profil, number> = {
  bezpieczny: 0, zbalansowany: 0.006, agresywny: 0.011,
};
const BONUS_MIEKKA: Record<Profil, number> = {
  bezpieczny: 1, zbalansowany: 0.95, agresywny: 0.92,
};
const BONUS_MATCHUP: Record<Profil, number> = {
  bezpieczny: 1, zbalansowany: 0.93, agresywny: 0.88,
};
const BONUS_SWIEZE: Record<Profil, number> = {
  bezpieczny: 1, zbalansowany: 0.96, agresywny: 0.93,
};
const WAGA_VALUE_SELEKCJA: Record<Profil, number> = {
  bezpieczny: 0, zbalansowany: 0.15, agresywny: 0.30,
};
const RODZINY: Record<string, string> = {
  shots: "strzelanie", sot: "strzelanie", shots_outside_box: "strzelanie",
  sot_outside_box: "strzelanie", headed_shots: "strzelanie", headed_sot: "strzelanie",
  shots_blocked: "strzelanie", shots_off_target: "strzelanie",
  fouls_committed: "faule", fouls_won: "faule", yellow_card: "faule",
  tackles: "defensywa", interceptions: "defensywa",
};
const DYWERSYFIKACJA = 0.985;
const MAX_LEGI = 12;
const BEAM_W = 90;
const MAX_KANDYDATOW = 120;

function legValue(l: LegPool): number {
  const ev = l.ev_uk ?? l.ev_pct ?? 0;
  return Math.max(0, Math.min(ev ?? 0, 30));
}

function karaKoszyka(legi: LegPool[], kary: Kary): number {
  let kara = 1;
  const seen = new Map<number, string[]>();
  for (const l of legi) {
    const m = l.mecz_id;
    const d = String(l.druzyna ?? "");
    const prev = seen.get(m);
    if (prev) {
      if (d && prev.includes(d)) kara *= kary.ta_sama;
      else if (d && prev.every((x) => x && x !== d)) kara *= kary.przeciwne;
      else kara *= kary.nieznane;
    }
    if (prev) prev.push(d);
    else seen.set(m, [d]);
  }
  return kara;
}

function scoreSelekcji(pRaw: number, legi: LegPool[], wagaValue: number, kary: Kary): number {
  let s = pRaw * karaKoszyka(legi, kary);
  const rodz = new Map<string, number>();
  for (const l of legi) {
    const f = RODZINY[l.rynek_kod];
    if (f) rodz.set(f, (rodz.get(f) ?? 0) + 1);
  }
  let nadmiar = 0;
  for (const c of rodz.values()) nadmiar += Math.max(0, c - 2);
  s *= DYWERSYFIKACJA ** nadmiar;
  if (wagaValue > 0 && legi.length) {
    const srEv = legi.reduce((a, l) => a + legValue(l), 0) / legi.length;
    s *= 1 + (wagaValue * srEv) / 100;
  }
  return s;
}

function qLega(b: LegPool, profil: Profil): number {
  let q = Math.log(b.p_model) / Math.log(b.kurs);
  if (profil === "bezpieczny") return q;
  const v = legValue(b);
  if (v > 0) q *= 1 - v * WAGA_VALUE_Q[profil];
  if (b.miekka_linia) q *= BONUS_MIEKKA[profil];
  if (b.matchup) q *= BONUS_MATCHUP[profil];
  if (b.swieze_sklady) q *= BONUS_SWIEZE[profil];
  if (profil === "agresywny" && (b.linia ?? 0) >= 1.5) q *= 0.97;
  return q;
}

export interface KuponWynik {
  kurs_laczny: number;
  p_model: number;
  fair_kurs: number;
  ev_pct: number;
  cel_label: string;
  strona: Strona;
  legi: LegPool[];
}

export interface OpcjeKuponu {
  profil?: Profil;
  minLegi?: number;
  maxNaMecz?: number;
  kary?: Kary;
}

type St = { kurs: number; p: number; legi: LegPool[] };

/**
 * Złóż kupon: maksymalna szansa przy kursie łącznym w [cmin, cmax].
 * `pool` = już przefiltrowana pula (np. wybrane mecze). Zwraca null, gdy z
 * dostępnych legów nie da się domknąć przedziału.
 */
export function zlozKupon(
  pool: LegPool[],
  cmin: number,
  cmax: number,
  opts: OpcjeKuponu = {},
): KuponWynik | null {
  const profil = opts.profil ?? "zbalansowany";
  const minLegi = opts.minLegi ?? 3;
  const maxNaMecz = opts.maxNaMecz ?? 4;
  const kary = opts.kary ?? KARY_DEFAULT;
  const wagaSel = WAGA_VALUE_SELEKCJA[profil];

  let p = pool.filter((b) => b.kurs > 1 && b.p_model > 0 && b.p_model < 1);
  if (profil === "bezpieczny") p = p.filter((b) => b.p_model >= 0.58);
  const cands = p
    .slice()
    .sort((a, b) => qLega(b, profil) - qLega(a, profil))
    .slice(0, MAX_KANDYDATOW);

  let beam: St[] = [{ kurs: 1, p: 1, legi: [] }];
  const komplety: St[] = [];
  for (const b of cands) {
    const nowe: St[] = [];
    for (const st of beam) {
      if (st.legi.length >= MAX_LEGI) continue;
      if (st.legi.some((l) => l.podmiot_id === b.podmiot_id)) continue;
      if (st.legi.filter((l) => l.mecz_id === b.mecz_id).length >= maxNaMecz) continue;
      const kurs2 = st.kurs * b.kurs;
      if (kurs2 > cmax) continue;
      const legi2 = [...st.legi, b];
      const p2 = st.p * b.p_model;
      nowe.push({ kurs: kurs2, p: p2, legi: legi2 });
      if (kurs2 >= cmin && legi2.length >= minLegi) {
        komplety.push({ kurs: kurs2, p: p2, legi: legi2 });
      }
    }
    beam = beam.concat(nowe);
    // prune: (score × bliskość dolnej granicy) malejąco; dedup równoważnych stanów
    const seen = new Set<string>();
    beam = beam
      .map((st) => {
        const sc = scoreSelekcji(st.p, st.legi, wagaSel, kary);
        return {
          st,
          sc,
          key: `${st.legi.length}|${st.kurs.toFixed(4)}|${sc.toFixed(8)}`,
        };
      })
      .filter((o) => (seen.has(o.key) ? false : (seen.add(o.key), true)))
      .map((o) => ({ st: o.st, rank: o.sc * Math.min(o.st.kurs / cmin, 1) }))
      .sort((a, b) => b.rank - a.rank)
      .slice(0, BEAM_W)
      .map((o) => o.st);
  }
  if (!komplety.length) return null;

  komplety.sort((a, b) => {
    const sb = scoreSelekcji(b.p, b.legi, wagaSel, kary);
    const sa = scoreSelekcji(a.p, a.legi, wagaSel, kary);
    if (sb !== sa) return sb - sa;
    // deterministyczny tie-break po zestawie podmiotów
    const ka = a.legi.map((l) => l.podmiot_id).sort((x, y) => x - y).join(",");
    const kb = b.legi.map((l) => l.podmiot_id).sort((x, y) => x - y).join(",");
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  });

  const best = komplety[0];
  const pFinal = best.p * karaKoszyka(best.legi, kary);
  const legi = best.legi
    .slice()
    .sort(
      (a, b) =>
        a.kickoff_ts - b.kickoff_ts ||
        a.mecz_id - b.mecz_id ||
        b.p_model - a.p_model,
    );
  return {
    kurs_laczny: Math.round(best.kurs * 100) / 100,
    p_model: pFinal,
    fair_kurs: Math.round((1 / Math.max(pFinal, 1e-9)) * 100) / 100,
    ev_pct: Math.round((pFinal * best.kurs - 1) * 1000) / 10,
    cel_label: `${Math.round(cmin)}–${Math.round(cmax)}`,
    strona: "powyzej",
    legi,
  };
}
