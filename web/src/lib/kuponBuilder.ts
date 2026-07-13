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
// backendowy styl "value" (kupony.py:_kandydaci) filtruje ev_pct >= MIN_LEG_EV
// i max 1 leg/mecz — ten sam próg tutaj, żeby GeneratorKuponu mógł go odtworzyć
export const MIN_LEG_EV = 2.0;

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
// ilu RÓŻNYCH zestawów legów o przypadkowo identycznym (długość, kurs, score)
// przetrwa dedup wiązki — jak kupony.py:MAX_TIE_REPR (ten sam fix, przeniesiony
// tutaj z opóźnieniem: przy pierwszej naprawie dedupu portowano tylko Python)
const MAX_TIE_REPR = 3;

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

/** Propozycja wymiany najsłabszego lega (rentgen kuponu — doradcza, jak
 * kupony.py:_rentgen). Kupon zostaje bez zmian, to tylko podpowiedź. */
export interface KuponAlternatywaLeg extends LegPool {
  zamiast_idx: number;
  kurs_po: number;
  p_po: number;
}

/** Propozycja DOŁOŻENIA pewnego lega, gdy kurs wisi w dolnej połowie
 * przedziału (jak kupony.py:_dolozenie). Doradcza. */
export interface KuponDolozenieLeg extends LegPool {
  kurs_po: number;
  p_po: number;
}

export interface KuponWynik {
  kurs_laczny: number;
  p_model: number;
  fair_kurs: number;
  ev_pct: number;
  cel_label: string;
  strona: Strona;
  legi: LegPool[];
  /** indeks (w `legi`, po sortowaniu do wyświetlenia) lega o najniższej szansie */
  najslabszy_idx?: number;
  alternatywa?: KuponAlternatywaLeg;
  dolozenie?: KuponDolozenieLeg;
  /** alternatywny, wyraźnie inny zestaw z tej samej puli (podglądowy) */
  wariant_b?: KuponWynik;
}

export interface OpcjeKuponu {
  profil?: Profil;
  minLegi?: number;
  /** górny limit liczby nóg (domyślnie MAX_LEGI=12). Ustaw równe minLegi, żeby
   * wymusić DOKŁADNIE tyle nóg zamiast "co najmniej". */
  maxLegi?: number;
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
  const maxLegi = opts.maxLegi ?? MAX_LEGI;
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
      if (st.legi.length >= maxLegi) continue;
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
    // prune: (score × bliskość dolnej granicy) malejąco. Dedup w DWÓCH
    // warstwach (jak kupony.py:_zloz_pewniaki): prawdziwe duplikaty (ten sam
    // ZBIÓR zawodników, różna kolejność wstawienia) zawsze zwijamy do
    // jednego; RÓŻNE zestawy o przypadkowo identycznym (długość, kurs, score)
    // dostają do MAX_TIE_REPR reprezentantów zamiast zwijać się do jednego —
    // inaczej pula z wieloma podobnymi legami zapycha całą wiązkę stanami tej
    // samej długości i blokuje dojście do dłuższych kompletów.
    const tieRepr = new Map<string, Set<string>>();
    beam = beam
      .map((st) => {
        const sc = scoreSelekcji(st.p, st.legi, wagaSel, kary);
        const tier = `${st.legi.length}|${st.kurs.toFixed(4)}|${sc.toFixed(8)}`;
        const ident = st.legi.map((l) => l.podmiot_id).sort((x, y) => x - y).join(",");
        return { st, sc, tier, ident };
      })
      .filter((o) => {
        const reprSeen = tieRepr.get(o.tier) ?? new Set<string>();
        tieRepr.set(o.tier, reprSeen);
        if (reprSeen.has(o.ident)) return false;
        if (reprSeen.size >= MAX_TIE_REPR) return false;
        reprSeen.add(o.ident);
        return true;
      })
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
    // deterministyczny tie-break po zestawie podmiotów — porównanie LICZBOWE
    // element po elemencie (jak Python tuple(sorted(...))), NIE stringowe:
    // "10,11" < "9,20" leksykograficznie, ale (9,20) < (10,11) liczbowo —
    // przy remisie score backend i frontend potrafiły wybrać inny komplet
    const ka = a.legi.map((l) => l.podmiot_id).sort((x, y) => x - y);
    const kb = b.legi.map((l) => l.podmiot_id).sort((x, y) => x - y);
    const n = Math.min(ka.length, kb.length);
    for (let i = 0; i < n; i++) {
      if (ka[i] !== kb[i]) return ka[i] - kb[i];
    }
    return ka.length - kb.length;
  });

  const buildBase = (st: St): KuponWynik => {
    const pF = st.p * karaKoszyka(st.legi, kary);
    const legiSort = st.legi
      .slice()
      .sort(
        (a, b) =>
          a.kickoff_ts - b.kickoff_ts ||
          a.mecz_id - b.mecz_id ||
          b.p_model - a.p_model,
      );
    return {
      kurs_laczny: Math.round(st.kurs * 100) / 100,
      // zaokrąglone tak samo jak kupony.py:_kupon_z (round(p, 4)) — fair_kurs/
      // ev_pct dalej liczone z NIEzaokrąglonego pF, jak w Pythonie
      p_model: Math.round(pF * 10000) / 10000,
      fair_kurs: Math.round((1 / Math.max(pF, 1e-9)) * 100) / 100,
      ev_pct: Math.round((pF * st.kurs - 1) * 1000) / 10,
      cel_label: `${Math.round(cmin)}–${Math.round(cmax)}`,
      strona: "powyzej",
      legi: legiSort,
    };
  };

  const best = komplety[0];
  const wynik = buildBase(best);
  const legi = wynik.legi;

  // rentgen (jak kupony.py:_rentgen): najsłabsze ogniwo + czy pula ma lepszą
  // zamianę, która realnie podnosi szansę kuponu. Czysto doradcze — kupon
  // (legi) zostaje bez zmian.
  const weakIdx = legi.reduce(
    (mi, l, i, arr) => (l.p_model < arr[mi].p_model ? i : mi), 0,
  );
  wynik.najslabszy_idx = weakIdx;
  const weak = legi[weakIdx];
  const kursBez = wynik.kurs_laczny / weak.kurs;
  const pBez = wynik.p_model / Math.max(weak.p_model, 1e-9);
  const uzyciRentgen = new Set(
    legi.filter((_, i) => i !== weakIdx).map((l) => l.podmiot_id),
  );
  const naMeczRentgen = new Map<number, number>();
  legi.forEach((l, i) => {
    if (i !== weakIdx) naMeczRentgen.set(l.mecz_id, (naMeczRentgen.get(l.mecz_id) ?? 0) + 1);
  });
  let bestSwap: LegPool | null = null;
  for (const b of p) {
    if (uzyciRentgen.has(b.podmiot_id) || b.p_model <= weak.p_model) continue;
    if ((naMeczRentgen.get(b.mecz_id) ?? 0) >= maxNaMecz) continue;
    const kursPo = kursBez * b.kurs;
    if (!(cmin * 0.8 <= kursPo && kursPo <= cmax)) continue;
    if (!bestSwap || b.p_model > bestSwap.p_model) bestSwap = b;
  }
  if (bestSwap) {
    const legiPo = [...legi.filter((_, i) => i !== weakIdx), bestSwap];
    const pPo = pBez * bestSwap.p_model
      * karaKoszyka(legiPo, kary) / Math.max(karaKoszyka(legi, kary), 1e-9);
    if (pPo > wynik.p_model + 1e-9) {
      wynik.alternatywa = {
        ...bestSwap,
        zamiast_idx: weakIdx,
        kurs_po: Math.round(kursBez * bestSwap.kurs * 100) / 100,
        p_po: Math.round(pPo * 10000) / 10000,
      };
    }
  }

  // dołożenie (jak kupony.py:_dolozenie): kupon wisi w dolnej połowie
  // przedziału — zaproponuj dobicie kursu bardzo pewnym legiem (p>=0.70)
  if (wynik.kurs_laczny < (cmin + cmax) / 2) {
    const uzyciDolozenie = new Set(legi.map((l) => l.podmiot_id));
    let bestAdd: LegPool | null = null;
    for (const b of p) {
      if (uzyciDolozenie.has(b.podmiot_id) || b.p_model < 0.70) continue;
      if (legi.filter((l) => l.mecz_id === b.mecz_id).length >= maxNaMecz) continue;
      if (wynik.kurs_laczny * b.kurs > cmax) continue;
      if (!bestAdd || b.p_model > bestAdd.p_model) bestAdd = b;
    }
    if (bestAdd) {
      const legiPo = [...legi, bestAdd];
      const pRaw = wynik.p_model / Math.max(karaKoszyka(legi, kary), 1e-9);
      const pPo = pRaw * bestAdd.p_model * karaKoszyka(legiPo, kary);
      wynik.dolozenie = {
        ...bestAdd,
        kurs_po: Math.round(wynik.kurs_laczny * bestAdd.kurs * 100) / 100,
        p_po: Math.round(pPo * 10000) / 10000,
      };
    }
  }

  // wariant B: najlepszy WYRAŹNIE INNY komplet (Jaccard < 0.5) z tej samej
  // wiązki — czysto podglądowy, nie zajmuje slotu i nie dostaje własnego rentgenu
  const sygnA = new Set(
    legi.map((l) => `${l.mecz_id}:${l.podmiot_id}:${l.rynek_kod}:${l.linia}`),
  );
  for (const alt of komplety.slice(1)) {
    const sygnB = new Set(
      alt.legi.map((l) => `${l.mecz_id}:${l.podmiot_id}:${l.rynek_kod}:${l.linia}`),
    );
    const inter = [...sygnA].filter((x) => sygnB.has(x)).length;
    const union = new Set([...sygnA, ...sygnB]).size;
    if (inter / Math.max(union, 1) < 0.5) {
      wynik.wariant_b = buildBase(alt);
      break;
    }
  }

  return wynik;
}
