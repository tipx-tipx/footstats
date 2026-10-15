/**
 * Mecze › „Najlepsze linie” (15.10): klucz `linie_dnia` z pipeline w kształcie
 * dla przeglądarki. Dane zostają zwięzłe (tablice jak w kluczu) – rachunek
 * pokrycia i filtry robi strona (`_ui/liniePomiar.ts`), żeby przełączanie
 * było natychmiastowe. Mecze, herby i godziny strona bierze z listy meczów,
 * którą i tak ma.
 */

import { bezDubli, DOMYSLNE_LINIE, wybierzLinie, type FormaLinii, type LiniaS } from "../_ui/liniePomiar";
import { POZYCJE } from "./przygotuj";
import { zrodlo } from "./zrodlo";

type KluczLinii = {
  zaw: Record<string, [string, string, string, boolean]>;
  forma: FormaLinii;
  linie: LiniaS[];
};

export type DaneLinii = {
  /** id zawodnika → nazwa, pozycja (po polsku), drużyna, w ogłoszonym składzie */
  zaw: Record<string, { nazwa: string; pozycja: string; druzyna: string; xi: boolean }>;
  forma: FormaLinii;
  linie: LiniaS[];
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
  return {
    zaw: Object.fromEntries(
      Object.entries(k.zaw).map(([id, [nazwa, poz, druzyna, xi]]) => [id, { nazwa, pozycja: POZYCJE[poz] ?? "", druzyna, xi }]),
    ),
    forma: k.forma,
    linie: k.linie,
    naLiscie: typy.filter((t) => t.podmiot_typ !== "druzyna").map((t) => `${t.mecz_id}|${t.podmiot_id}|${t.rynek_kod}`),
  };
}
