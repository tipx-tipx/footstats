import przyklady from "../_dane/drabinki_przyklady.json";
import { przygotujElementy } from "../_dane/elementy";
import { zDanymi } from "../_dane/zrodlo";
import { DrabinkiRodzaje, type StartRodzajow } from "../_ui/DrabinkiRodzaje";
import { pobierzSurowe } from "@/lib/nowe/surowe";

/*
 * Warsztat 11.10 – oznaczenia rodzajów drabinek (właściciel: „brakuje
 * oznaczeń tych typów drabinek, przemyślanego designu”). Karty z produkcji
 * (Supabase, jak strona główna) + jedna perełka odtworzona z księgi, bo
 * w bieżącym radarze perełki akurat nie ma.
 */

/**
 * Mulligan, Dundee United – Hibernian 10.10: hero strzały 1,5 @2,20 (perła,
 * 7/10, forma 4/5), 2,5 @4,50 (5/10), 3,5 @5,30 (3/10) – szczeble i kursy
 * z publikacji (typy_log), 0,5 z archiwum ofert, historia 10 rozegranych
 * meczów sprzed gwizdka z banku `trend_lib` (zgodna z księgą: 7/5/3 z 10).
 */
const PERLA_Z_KSIEGI = {
  podmiot: "Josh Mulligan",
  podmiot_id: 988691,
  pozycja: "M",
  druzyna: "Hibernian",
  przeciwnik: "Dundee United",
  mecz: "Dundee United – Hibernian",
  kickoff_ts: 1791640800,
  hero: {
    linia: 1.5, rynek: "Strzały", rynek_kod: "shots", kurs: 2.2, kurs_publikacji: 2.2,
    traf: 7, z: 10, traf5: 4, z5: 5, powod_szczebla: "perla",
  },
  rynki: [{
    rynek: "Strzały", rynek_kod: "shots",
    ostatnie: [2, 4, 1, 4, 4, 3, 2, 3, 0, 0],
    minuty: [90, 90, 75, 90, 90, 90, 90, 90, 45, 21],
    rywale: ["Aberdeen", "Kilmarnock", "St. Johnstone", "Heart of Midlothian", "Dundee FC", "KAA Gent", "Rangers", "Motherwell", "Motherwell", "Rangers"],
    drabinka: [
      { linia: 1.5, kurs: 2.2, p_final: 0.718 },
      { linia: 2.5, kurs: 4.5, p_final: 0.41 },
      { linia: 3.5, kurs: 5.3, p_final: 0.3 },
    ],
    linie_pelne: { "0.5": 1.12, "1.5": 2.2, "2.5": 4.5, "3.5": 5.3 },
  }],
};

export default async function DrabinkiRodzajePage({ searchParams }: { searchParams: Promise<StartRodzajow> }) {
  const surowe = await pobierzSurowe();
  const radar = (surowe.radar ?? {}) as { wpisy?: unknown[] };
  // przykłady z 06–10.10 (Rivera, Benedyczak, Mafouta, Terrats): obie ceny z tej
  // samej chwili – ostatni zrzut archiwum ofert przed gwizdkiem (skrypt
  // przyklady_drabinek.py, sesja 11.10); dziś Betclic tych linii jeszcze nie ma
  const zPerla = { ...surowe, radar: { ...radar, wpisy: [PERLA_Z_KSIEGI, ...przyklady, ...(radar.wpisy ?? [])] } };
  const dane = zDanymi(zPerla as typeof surowe, () => przygotujElementy());
  return <DrabinkiRodzaje karty={dane.drabinkiLista} start={await searchParams} />;
}
