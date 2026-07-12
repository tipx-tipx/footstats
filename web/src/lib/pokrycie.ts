/**
 * TOP POKRYCIA — zawodnicy z najlepszym pokryciem linii w ostatnich meczach.
 *
 * Zasady (wypracowane z użytkownikiem):
 *  • Próbka = ostatnie 5 meczów, w których zawodnik ZACZYNAŁ (minuty ≥ 60).
 *  • Na mecz REPREZENTACJI (MŚ) PREFERUJEMY starty w kadrze: jeśli zawodnik ma
 *    ≥ 5 startów w kadrze w dostępnej historii, liczymy pokrycie z nich (prawdziwa
 *    forma reprezentacyjna). Jeśli nie (rezerwa kadry / klubowiec) — fallback na
 *    5 ostatnich startów jakichkolwiek, z flagą „forma klubowa".
 *  • Jeden wiersz na (zawodnik, rynek) — linie 1+/2+/3+ zwinięte obok siebie.
 *  • Zostają pokrycia ≥ 2/5. Kurs Superbet z siatki odds.
 */

import type { OddsSuperbet, Zawodnik } from "./types";

/** Etykiety rynków (kod → nazwa PL) — zgodne z pipeline MARKET_NAMES_PL. */
export const RYNEK_LABEL: Record<string, string> = {
  shots: "Strzały",
  sot: "Strzały celne",
  shots_outside_box: "Strzały zza pola",
  shots_off_target: "Strzały niecelne",
  shots_blocked: "Strzały zablokowane",
  sot_outside_box: "Celne zza pola",
  headed_shots: "Strzały głową",
  headed_sot: "Celne głową",
  fouls_committed: "Faule popełnione",
  fouls_won: "Faule wywalczone",
  tackles: "Odbiory",
  interceptions: "Przechwyty",
  offsides: "Spalone",
};

/** Rynki brane pod uwagę (kolejność = domyślny priorytet). */
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
const PROG_STARTU = 60; // minuty ≥ 60 = zaczynał w składzie (jak pipeline)
const MIN_POKRYTE = 2; // ≥ 2/5 = 40%

/** Jedna gra w próbce. */
export interface GraForma {
  v: number;
  rywal: string | null;
  minuty: number;
  kadra: boolean;
  ts: number;
}

/** Pokrycie jednej linii (1+/2+/3+) w obrębie rynku. */
export interface LiniaPokrycie {
  linia: number;
  prog: number;
  pokryte: number;
  kurs: number | null;
  /**
   * Zgrubny sygnał WARTOŚCI: ile dałby ten zakład, gdyby surowe pokrycie było
   * prawdziwym prawdopodobieństwem — (pokryte/próba × kurs − 1) × 100%.
   * NIE jest to EV silnika (brak kalibracji, minut, kontekstu, próba tylko 5) —
   * to szybki filtr „czy kurs w ogóle opłaca to pokrycie" (odsiewa „5/5 @1,01”).
   * null, gdy brak kursu Superbet.
   */
  evPct: number | null;
}

export interface WierszPokrycia {
  player_id: number;
  zawodnik: string;
  druzyna: string;
  rynek_kod: string;
  rynek: string;
  /** 5 startów użytych do liczenia (najnowszy pierwszy) */
  ostatnie: GraForma[];
  probka: number;
  /** true = pokrycie z meczów reprezentacji; false = fallback klubowy (ten rynek) */
  kadraBasis: boolean;
  /** true = zawodnik jest regularny w kadrze (≥5 startów kadry w najbogatszym
   *  rynku) — sygnał na poziomie GRACZA, spójny między rynkami (kolejność + flaga) */
  kadraRegularny: boolean;
  /** timestamp (s) najnowszego meczu w próbce — świeżość */
  ostatniMeczTs: number;
  /** pokrycie per linia (tylko te ≥ MIN_POKRYTE) */
  linie: LiniaPokrycie[];
  /** najlepsze pokrycie w wierszu (do sortowania) */
  maxPokryte: number;
  /** true = któraś linia ma kurs Superbet */
  maKurs: boolean;
  /**
   * Najlepszy sygnał wartości w wierszu do RANKINGU = max( evPct × pokryte/próba )
   * po liniach z kursem. Ważenie pokryciem premiuje pewne trafienia nad loterią
   * (2/5 @wysoki kurs nie przebija stabilnego 5/5). null, gdy żadna linia nie ma kursu.
   */
  maxRankEv: number | null;
  /** najlepszy surowy evPct w wierszu (do wyświetlenia nagłówka), null bez kursu */
  bestEv: number | null;
}

/**
 * Ranga trafności na mecz REPREZENTACJI: 0 = regularny w kadrze (realnie zagra),
 * 1 = rezerwa kadry (forma klubowa, niżej). Sygnał na poziomie GRACZA — spójny
 * między jego rynkami. Świadomie NIE używamy statshub `in_predicted_lineup` —
 * jest rzadki i migocze między cyklami (raz XI, raz nie); baza kadry jest stabilna.
 */
function ranga(w: WierszPokrycia): number {
  return w.kadraRegularny ? 0 : 1;
}

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
 * suma rynków (rynek z większą próbką wygrywa), xi = OR, wszystkie ID zebrane.
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
    // kursy zbierane ze WSZYSTKICH ID duplikatu (rynek→linia→kurs)
    const oddsGracz: Record<string, Record<string, number>> = {};
    for (const id of z.ids) {
      const o = oddsMecz[String(id)];
      if (!o) continue;
      for (const [mk, linie] of Object.entries(o)) {
        oddsGracz[mk] = { ...(oddsGracz[mk] ?? {}), ...linie };
      }
    }

    // regularny w kadrze na poziomie GRACZA: czy w NAJBOGATSZYM rynku ma ≥5
    // startów w reprezentacji. Steruje kolejnością i flagą spójnie dla wszystkich
    // jego rynków (statshub daje różną głębię historii per statystyka).
    let maxKadraStarty = 0;
    for (const f of Object.values(z.forma ?? {})) {
      let n = 0;
      for (let i = 0; i < f.ostatnie.length; i++) {
        if ((f.minuty?.[i] ?? 0) >= PROG_STARTU && f.kadra?.[i] === true) n++;
      }
      if (n > maxKadraStarty) maxKadraStarty = n;
    }
    const kadraRegularny = maxKadraStarty >= PROBKA;

    for (const kod of RYNKI_POKRYCIA) {
      const f = z.forma?.[kod];
      if (!f) continue;

      // wszystkie gry (najnowszy pierwszy) z kontekstem
      const gry: GraForma[] = f.ostatnie.map((v, i) => ({
        v,
        rywal: f.rywale?.[i] ?? null,
        minuty: f.minuty?.[i] ?? 0,
        kadra: f.kadra?.[i] === true,
        ts: f.ts?.[i] ?? 0,
      }));
      const starty = gry.filter((g) => g.minuty >= PROG_STARTU);
      const kadraStarty = starty.filter((g) => g.kadra);

      // PREFERUJ kadrę: ≥5 startów w reprezentacji → licz z nich; inaczej
      // fallback na 5 ostatnich startów jakichkolwiek (forma klubowa)
      let probka: GraForma[];
      let kadraBasis: boolean;
      if (kadraStarty.length >= PROBKA) {
        probka = kadraStarty.slice(0, PROBKA);
        kadraBasis = true;
      } else if (starty.length >= PROBKA) {
        probka = starty.slice(0, PROBKA);
        kadraBasis = false;
      } else {
        continue; // za mało startów
      }

      const n = probka.length;
      const linie: LiniaPokrycie[] = LINIE.map((linia) => {
        const prog = Math.ceil(linia);
        const pokryte = probka.filter((g) => g.v >= prog).length;
        const kurs = oddsGracz[kod]?.[String(linia)] ?? null;
        const evPct =
          kurs != null && n > 0
            ? Math.round(((pokryte / n) * kurs - 1) * 100)
            : null;
        return { linia, prog, pokryte, kurs, evPct };
      }).filter((l) => l.pokryte >= MIN_POKRYTE);
      if (linie.length === 0) continue;

      // wartość ważona pokryciem (do rankingu) i surowa najlepsza (do wyświetlenia)
      const zKursem = linie.filter((l) => l.kurs != null && l.evPct != null);
      const maxRankEv = zKursem.length
        ? Math.max(...zKursem.map((l) => (l.evPct as number) * (l.pokryte / n)))
        : null;
      const bestEv = zKursem.length
        ? Math.max(...zKursem.map((l) => l.evPct as number))
        : null;

      rows.push({
        player_id: z.id,
        zawodnik: z.nazwa,
        druzyna: z.druzyna,
        rynek_kod: kod,
        rynek: RYNEK_LABEL[kod] ?? kod,
        ostatnie: probka,
        probka: probka.length,
        kadraBasis,
        kadraRegularny,
        ostatniMeczTs: probka[0]?.ts ?? 0,
        linie,
        maxPokryte: Math.max(...linie.map((l) => l.pokryte)),
        maKurs: linie.some((l) => l.kurs != null),
        maxRankEv,
        bestEv,
      });
    }
  }

  rows.sort(
    (a, b) =>
      // 1) regularni w kadrze (realnie zagrają) zawsze na górze
      ranga(a) - ranga(b) ||
      // 2) wiersze z kursem (dają się ocenić wartościowo) przed bez kursu
      (b.maxRankEv != null ? 1 : 0) - (a.maxRankEv != null ? 1 : 0) ||
      // 3) WARTOŚĆ ważona pokryciem — realna przewaga, nie samo pokrycie
      (b.maxRankEv ?? -Infinity) - (a.maxRankEv ?? -Infinity) ||
      // 4) dalej jak dotąd: pokrycie → linia → kurs
      b.maxPokryte - a.maxPokryte ||
      b.linie[0].linia - a.linie[0].linia ||
      (b.linie[0].kurs ?? 0) - (a.linie[0].kurs ?? 0),
  );
  // deduplikacja bezpieczeństwa: jeden zawodnik/rynek tylko raz
  const seen = new Set<string>();
  return rows.filter((w) => {
    const key = `${w.zawodnik}|${w.rynek_kod}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
