/**
 * Warstwa danych.
 *
 * Dwa źródła, jeden interfejs:
 *  1. Supabase (produkcja na Vercel) — gdy ustawione SUPABASE_URL + SUPABASE_ANON_KEY.
 *     Pipeline (GitHub Actions / lokalnie) wypycha snapshoty do tabeli app_data,
 *     aplikacja czyta je tutaj. Odświeżane co godzinę (revalidate).
 *  2. Pliki lokalne (dev / brak Supabase) — bundlowane JSON-y z data/demo.
 */

import valueBetsLocal from "@/data/demo/value_bets.json";
import matchesLocal from "@/data/demo/matches.json";
import playersLocal from "@/data/demo/players.json";
import calibrationLocal from "@/data/demo/calibration.json";
import metaLocal from "@/data/demo/meta.json";
import kuponyLocal from "@/data/demo/kupony.json";
import typyWynikiLocal from "@/data/demo/typy_wyniki.json";

import type {
  Kalibracja,
  Kupon,
  Mecz,
  Meta,
  TypyWyniki,
  ValueBet,
  Zawodnik,
} from "./types";

type Bundle = {
  value_bets: ValueBet[];
  matches: Mecz[];
  players: Zawodnik[];
  calibration: Kalibracja;
  meta: Meta;
  kupony: Kupon[];
  typy_wyniki: TypyWyniki;
};

const LOCAL: Bundle = {
  value_bets: valueBetsLocal as unknown as ValueBet[],
  matches: matchesLocal as unknown as Mecz[],
  players: playersLocal as unknown as Zawodnik[],
  calibration: calibrationLocal as unknown as Kalibracja,
  meta: metaLocal as unknown as Meta,
  kupony: kuponyLocal as unknown as Kupon[],
  typy_wyniki: typyWynikiLocal as unknown as TypyWyniki,
};

const SUPABASE_URL = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON =
  process.env.SUPABASE_ANON_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

async function loadBundle(): Promise<Bundle> {
  if (!SUPABASE_URL || !SUPABASE_ANON) return LOCAL;
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/app_data?select=key,payload`,
      {
        headers: {
          apikey: SUPABASE_ANON,
          Authorization: `Bearer ${SUPABASE_ANON}`,
        },
        next: { revalidate: 900 }, // odśwież co 15 min
      },
    );
    if (!res.ok) return LOCAL;
    const rows: { key: keyof Bundle; payload: unknown }[] = await res.json();
    const map = Object.fromEntries(rows.map((r) => [r.key, r.payload]));
    return {
      value_bets: (map.value_bets ?? LOCAL.value_bets) as ValueBet[],
      matches: (map.matches ?? LOCAL.matches) as Mecz[],
      players: (map.players ?? LOCAL.players) as Zawodnik[],
      calibration: (map.calibration ?? LOCAL.calibration) as Kalibracja,
      meta: (map.meta ?? LOCAL.meta) as Meta,
      kupony: (map.kupony ?? LOCAL.kupony) as Kupon[],
      typy_wyniki: (map.typy_wyniki ?? LOCAL.typy_wyniki) as TypyWyniki,
    };
  } catch {
    return LOCAL;
  }
}

export async function getValueBets(): Promise<ValueBet[]> {
  return (await loadBundle()).value_bets;
}

export async function getMecze(): Promise<Mecz[]> {
  return (await loadBundle()).matches;
}

export async function getZawodnicy(): Promise<Zawodnik[]> {
  return (await loadBundle()).players;
}

export async function getZawodnik(id: number): Promise<Zawodnik | undefined> {
  return (await getZawodnicy()).find((z) => z.id === id);
}

export async function getKalibracja(): Promise<Kalibracja> {
  return (await loadBundle()).calibration;
}

export async function getMeta(): Promise<Meta> {
  return (await loadBundle()).meta;
}

export async function getBetsForMatch(matchId: number): Promise<ValueBet[]> {
  return (await getValueBets()).filter((b) => b.mecz_id === matchId);
}

export async function getKupony(): Promise<Kupon[]> {
  return (await loadBundle()).kupony;
}

export async function getTypyWyniki(): Promise<TypyWyniki> {
  return (await loadBundle()).typy_wyniki;
}
