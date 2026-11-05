/**
 * Mecze › „Najlepsze linie” (15.10): klucz `linie_dnia` z pipeline w kształcie
 * dla przeglądarki. Dane zostają zwięzłe (tablice jak w kluczu) – rachunek
 * pokrycia i filtry robi strona (`_ui/liniePomiar.ts`), żeby przełączanie
 * było natychmiastowe. Mecze, herby i godziny strona bierze z listy meczów,
 * którą i tak ma.
 *
 * 05.11 – klucz w2: próg pokrycia, od którego pipeline zbudował klucz (50%,
 * przy za dużym kluczu 60/70%), i mecze zawodnika do dymka kratek (dzień +
 * numer rywala w `druzyny`). Stary kształt (przed pierwszym cyklem na nowym
 * kodzie) działa dalej: próg 70%, kratki bez dymka.
 */

import { bezDubli, DOMYSLNE_LINIE, wybierzLinie, type FormaLinii, type LiniaS, type MeczZawodnika } from "../_ui/liniePomiar";
import { POZYCJE } from "./przygotuj";
import { zrodlo } from "./zrodlo";

type KluczLinii = {
  w?: number;
  prog?: number;
  zaw: Record<string, [string, string, string, boolean, MeczZawodnika[]?]>;
  forma: FormaLinii;
  druzyny?: string[];
  linie: LiniaS[];
};

export type DaneLinii = {
  /** id zawodnika → nazwa, pozycja (po polsku), drużyna, w ogłoszonym składzie, mecze (dymek kratek) */
  zaw: Record<string, { nazwa: string; pozycja: string; druzyna: string; xi: boolean; mecze?: MeczZawodnika[] }>;
  forma: FormaLinii;
  linie: LiniaS[];
  /** rywale z `mecze` zawodników */
  druzyny: string[];
  /** najniższy próg pokrycia w danych (0,5; stary klucz 0,7) */
  prog: number;
  /** "mecz|zawodnik|rynek" – mamy na to typ (znacznik „na liście”) */
  naLiscie: string[];
};

/** Zapowiedź na liście meczów: ile mocnych linii ma mecz (progi domyślnego widoku linii). */
export function mocneLinieMeczow(): Record<number, number> {
  const k = zrodlo().linie as KluczLinii | null;
  if (!k?.linie) return {};
  const out: Record<number, number> = {};
  const nazwa = (id: number) => k.zaw[String(id)]?.[0] ?? "";
  for (const w of bezDubli(wybierzLinie(k.linie, k.forma, DOMYSLNE_LINIE), nazwa)) out[w.s[0]] = (out[w.s[0]] ?? 0) + 1;
  return out;
}

export function przygotujLinie(): DaneLinii | null {
  const k = zrodlo().linie as KluczLinii | null;
  if (!k?.linie) return null;
  const typy = zrodlo().typy as { mecz_id: number; podmiot_id: number; podmiot_typ: string; rynek_kod: string }[];
  const w2 = k.w === 2;
  return {
    zaw: Object.fromEntries(
      Object.entries(k.zaw).map(([id, [nazwa, poz, druzyna, xi, mecze]]) => [
        id,
        { nazwa, pozycja: POZYCJE[poz] ?? "", druzyna, xi, ...(w2 && mecze?.length ? { mecze } : {}) },
      ]),
    ),
    forma: k.forma,
    linie: k.linie,
    druzyny: w2 ? (k.druzyny ?? []) : [],
    prog: w2 && typeof k.prog === "number" ? k.prog : 0.7,
    naLiscie: typy.filter((t) => t.podmiot_typ !== "druzyna").map((t) => `${t.mecz_id}|${t.podmiot_id}|${t.rynek_kod}`),
  };
}
