/**
 * Kupony od modelu – jak wyszły (właściciel 01.10: „przywróć każdemu, z głową”).
 *
 * Pipeline co dzień sam składa kilka kuponów z typów z listy (`typy_wyniki.kupony`,
 * ostatnie 3 tygodnie, z wynikiem każdej nogi). To NIE jest „Kupon dnia” z kreatora –
 * stąd własna nazwa sekcji. Zasada ze starej strony (2026-08-04): trafione
 * i nietrafione po równo, bilans z CAŁEJ historii (`kupony_roi`), nie z kilku
 * widocznych – „6 z 6” czyta się jak reklama, „4 z 6” jak wynik.
 *
 * Do przeglądarki idzie tylko to, co widać: bez szans modelu, wartości i kalibracji.
 */

import { fmtLinia, nazwaPodmiotu, opisZakladu } from "@/lib/format";

import { etykietaDnia } from "./formatCzasu";
import { dzisZrodla, zrodlo } from "./zrodlo";

type NogaS = { podmiot: string; druzyna?: string | null; mecz: string; rynek: string; rynek_kod: string; linia: number; strona: string; kurs: number; wynik: string | null };
type KuponS = {
  klucz?: string;
  dzien: string;
  opublikowano_ts: number;
  horyzont?: string;
  wynik: string | null;
  kurs_laczny: number;
  kurs_rozliczony?: number;
  pominiety?: boolean;
  legi: NogaS[];
};
type Roi = Record<string, { n: number; wygrane: number }>;

export type WynikKuponu = "wygrany" | "przegrany" | "anulowany" | "zwrot" | "w_grze";
export type WynikNogi = "wygrany" | "przegrany" | "zwrot" | "czeka";

/** „zawodnicy” i „hybryda” od 05.10 (własne sloty w pipeline, `horyzont` = rodzaj) */
export type RodzajKuponu = "dzienny" | "dlugoterminowy" | "zawodnicy" | "hybryda";

export type KuponHistorii = {
  klucz: string;
  rodzaj: RodzajKuponu;
  /** kolejność od najnowszego (sortowanie „Najnowsze”) */
  nr: number;
  /** „Dziś”, „Wt 30.09” */
  dzien: string;
  horyzont: string;
  wynik: WynikKuponu;
  kurs: number;
  nogi: { kto: string; rynek: string; strona: string; linia: string; kurs: number; wynik: WynikNogi }[];
};

export type HistoriaKuponow = {
  bilans: { klucz: RodzajKuponu | "wszystkie"; nazwa: string; n: number; wygrane: number }[];
  kupony: KuponHistorii[];
};

const HORYZONTY: [RodzajKuponu, string][] = [
  ["dzienny", "Na dziś"],
  ["dlugoterminowy", "Na kilka dni"],
  ["zawodnicy", "Zawodnicy"],
  ["hybryda", "Hybryda"],
];
const RODZAJE = new Set<string>(HORYZONTY.map(([k]) => k));
/* podpis przy dniu: dzienny – sam dzień („Dziś · na dziś” powtarzało to samo) */
const PODPIS: Record<RodzajKuponu, string> = {
  dzienny: "",
  dlugoterminowy: "na kilka dni",
  zawodnicy: "zawodnicy",
  hybryda: "hybryda",
};

export function przygotujHistorieKuponow(): HistoriaKuponow | null {
  const w = zrodlo().wyniki as { kupony?: KuponS[]; kupony_roi?: Roi };
  const surowe = (w.kupony ?? []).filter((k) => !k.pominiety && k.legi?.length);
  if (!surowe.length) return null;
  const dzis = dzisZrodla();
  const roi = w.kupony_roi ?? {};
  const poHoryzoncie = HORYZONTY.filter(([k]) => roi[k]?.n).map(([k, nazwa]) => ({ klucz: k, nazwa, n: roi[k].n, wygrane: roi[k].wygrane }));
  const bilans = poHoryzoncie.length
    ? [{ klucz: "wszystkie" as const, nazwa: "Wszystkie", n: poHoryzoncie.reduce((a, b) => a + b.n, 0), wygrane: poHoryzoncie.reduce((a, b) => a + b.wygrane, 0) }, ...poHoryzoncie]
    : [];

  const kupony = surowe
    .map((k): [number, KuponHistorii] => [k.opublikowano_ts, {
      klucz: k.klucz ?? `${k.dzien}-${k.opublikowano_ts}`,
      rodzaj: RODZAJE.has(k.horyzont ?? "") ? (k.horyzont as RodzajKuponu) : "dlugoterminowy",
      nr: 0,
      dzien: etykietaDnia(k.dzien, dzis),
      horyzont: PODPIS[RODZAJE.has(k.horyzont ?? "") ? (k.horyzont as RodzajKuponu) : "dlugoterminowy"],
      wynik: (k.wynik ?? "w_grze") as WynikKuponu,
      kurs: k.kurs_rozliczony ?? k.kurs_laczny,
      nogi: k.legi.map((n) => {
        // „kto więcej”: typowana drużyna (podmiot to zawsze gospodarz), bez linii 0,0
        const wiecej = n.rynek_kod.startsWith("wiecej_");
        return {
          kto: /^match_/.test(n.rynek_kod) ? n.mecz : nazwaPodmiotu(n),
          rynek: wiecej ? opisZakladu(n) : n.rynek.replace(/\s*drużyny\s*/, " ").trim(),
          strona: wiecej ? "" : n.strona === "ponizej" ? "poniżej" : "powyżej",
          linia: wiecej ? "" : fmtLinia(n.linia),
          kurs: n.kurs,
          wynik: (n.wynik ?? "czeka") as WynikNogi,
        };
      }),
    }])
    // w grze na górze, potem od najnowszego
    .sort(([ta, a], [tb, b]) => Number(b.wynik === "w_grze") - Number(a.wynik === "w_grze") || tb - ta)
    .map(([, k], i) => ({ ...k, nr: i }));

  return { bilans, kupony };
}
