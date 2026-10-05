/**
 * Etap 5.4 – strona meczu: pokrycia zawodników (jak Statshub) z wycinka
 * pobranego 01.10 (`pokrycia.json`: pełne kadry 2 meczów + kursy na linie).
 *
 * Kursy: w danych strony jest JEDEN kurs na linię (wyższy z Superbetu
 * i Betclica, bez źródła). Prototyp pokazuje go w kolumnie Superbet;
 * po zmianie w pipeline dojdzie osobny Betclic (decyzja 01.10).
 */

import { druzyna, GODZ_FMT, POZYCJE, dzienTs, etykietaDnia, type DruzynaV } from "./przygotuj";
import { dzisZrodla, zrodlo } from "./zrodlo";

const OKNO_MAX = 10;

export const RYNKI_ZAWODNIKA: [string, string][] = [
  ["shots", "Strzały"],
  ["sot", "Strzały celne"],
  ["shots_outside_box", "Strzały zza pola"],
  ["sot_outside_box", "Celne zza pola"],
  ["headed_shots", "Strzały głową"],
  ["headed_sot", "Celne głową"],
  ["fouls_committed", "Faule popełnione"],
  ["fouls_won", "Faule wywalczone"],
  ["tackles", "Odbiory"],
  ["offsides", "Spalone"],
  ["yellow_card", "Żółta kartka"],
];

type FormaS = { ts: number[]; kadra: boolean[]; minuty: number[]; rywale: string[]; ostatnie: number[]; srednia90: number | null };
type ZawS = { id: number; nazwa: string; pozycja: string; druzyna: string; xi: boolean; minuty_lacznie: number; forma: Record<string, FormaS> };
/** kurs linii: [Superbet, Betclic] z `kursy_mNN` (7B) albo sama liczba ze starej siatki (wyższa z dwóch, bez nazwy);
 *  trzeci element 1 = Betclic liczy tę statystykę inaczej, cena Betclica ukryta (05.10) */
type KursS = number | [number | null, number | null] | [number | null, number | null, number];
type MeczS = { id: number; gosp: string; gosc: string; zawodnicy: ZawS[]; kursy: Record<string, Record<string, Record<string, KursS>>> };

export type HistoriaRynku = {
  /** od najnowszego */
  v: number[];
  min: number[];
  rywale: string[];
  daty: string[];
};

export type ZawodnikMeczu = {
  id: number;
  nazwa: string;
  pozycja: string;
  strona: "gosp" | "gosc";
  xi: boolean;
  /** rynek → historia (tylko rynki z kursem dla tego zawodnika) */
  rynki: Record<string, HistoriaRynku>;
  /** rynek → linia → kurs Superbet / Betclic (w prototypie Betclic pusty) */
  kursy: Record<string, Record<string, { sb: number | null; bc: number | null; bcInaczej?: boolean }>>;
  /** rynek → id typu na liście dnia (znacznik „na liście”) */
  naLiscie: Record<string, { id: number; linia: number }>;
};

export type MeczStrony = {
  id: number;
  gosp: DruzynaV;
  gosc: DruzynaV;
  liga: string;
  dzien: string;
  godzina: string;
  sedzia: string | null;
  sklady: boolean;
  zawodnicy: ZawodnikMeczu[];
  /** rynki z kursem w tym meczu, w kolejności wyświetlania, z liczbą zawodników */
  rynki: { kod: string; nazwa: string; ile: number; linie: number[] }[];
};

const data = (ts: number) => {
  const d = new Date(ts * 1000);
  return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export function przygotujMecze(): MeczStrony[] {
  const mecze = new Map((zrodlo().mecze as { id: number; liga: string; kickoff_ts: number; sedzia: string | null; sklady_ogloszone: unknown }[]).map((m) => [m.id, m]));
  const typy = zrodlo().typy as { id: number; mecz_id: number; podmiot_id: number; podmiot_typ: string; rynek_kod: string; linia: number }[];

  return (zrodlo().pokrycia as { mecze: MeczS[] }).mecze
    // mecz bez kursów na zawodników też ma stronę (typy drużynowe, pusty stan pokryć)
    .map((m): MeczStrony => {
      const meta = mecze.get(m.id);
      const zawodnicy: ZawodnikMeczu[] = m.zawodnicy
        .map((z): ZawodnikMeczu => {
          const kz = m.kursy[String(z.id)] ?? {};
          const rynki: Record<string, HistoriaRynku> = {};
          const kursy: ZawodnikMeczu["kursy"] = {};
          for (const [kod] of RYNKI_ZAWODNIKA) {
            const f = z.forma[kod];
            if (!kz[kod] || !f) continue;
            const n = Math.min(OKNO_MAX, f.ostatnie.length);
            rynki[kod] = {
              v: f.ostatnie.slice(0, n),
              min: (f.minuty ?? []).slice(0, n),
              rywale: (f.rywale ?? []).slice(0, n),
              daty: (f.ts ?? []).slice(0, n).map(data),
            };
            kursy[kod] = Object.fromEntries(Object.entries(kz[kod]).map(([l, k]) => [l, Array.isArray(k) ? { sb: k[0], bc: k[1], bcInaczej: k[2] === 1 } : { sb: k, bc: null }]));
          }
          const naLiscie: ZawodnikMeczu["naLiscie"] = {};
          for (const t of typy) {
            if (t.mecz_id === m.id && t.podmiot_typ !== "druzyna" && t.podmiot_id === z.id) naLiscie[t.rynek_kod] = { id: t.id, linia: t.linia };
          }
          return {
            id: z.id,
            nazwa: z.nazwa,
            pozycja: POZYCJE[z.pozycja] ?? "",
            strona: z.druzyna === m.gosp ? "gosp" : "gosc",
            xi: z.xi,
            rynki,
            kursy,
            naLiscie,
          };
        })
        .filter((z) => Object.keys(z.rynki).length);

      const rynki = RYNKI_ZAWODNIKA.map(([kod, nazwa]) => {
        const zk = zawodnicy.filter((z) => z.rynki[kod]);
        // linia z kursem u 1–2 zawodników to szum (np. strzały 8,5) – zostają te
        // kwotowane szerzej, najwyżej 6
        const ile = new Map<number, number>();
        for (const z of zk) for (const l of Object.keys(z.kursy[kod]).map(Number)) ile.set(l, (ile.get(l) ?? 0) + 1);
        const prog = Math.max(3, Math.ceil(zk.length * 0.15));
        let linie = [...ile.entries()].filter(([, n]) => n >= prog).map(([l]) => l);
        if (!linie.length) linie = [...ile.keys()];
        linie = linie.sort((a, b) => a - b).slice(0, 6);
        return { kod, nazwa, ile: zk.length, linie };
      }).filter((r) => r.ile > 0);

      return {
        id: m.id,
        gosp: druzyna(m.gosp),
        gosc: druzyna(m.gosc),
        liga: meta?.liga ?? "",
        dzien: meta ? etykietaDnia(dzienTs(meta.kickoff_ts), dzisZrodla()) : "",
        godzina: meta ? GODZ_FMT.format(new Date(meta.kickoff_ts * 1000)) : "",
        sedzia: meta?.sedzia ?? null,
        sklady: Boolean(meta?.sklady_ogloszone),
        zawodnicy,
        rynki,
      };
    });
}
