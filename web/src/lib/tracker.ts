"use client";

/** Prosty magazyn "Moich zakładów" w localStorage (narzędzie osobiste).
 *  Po podpięciu Supabase można podmienić na tabelę bet_log. */

import type { MojZaklad, ValueBet } from "./types";

const KEY = "footstats.zaklady.v1";
const EVENT = "footstats:zaklady";

export function listZaklady(): MojZaklad[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function save(zaklady: MojZaklad[]) {
  window.localStorage.setItem(KEY, JSON.stringify(zaklady));
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function addZakladFromBet(bet: ValueBet, stawka: number | null): MojZaklad {
  const z: MojZaklad = {
    id: `${Date.now()}-${bet.id}`,
    value_bet_id: bet.id,
    mecz: bet.mecz,
    podmiot: bet.podmiot,
    rynek: bet.rynek,
    linia: bet.linia,
    strona: bet.strona,
    kurs: bet.kurs ?? 0, // sugestie (kurs null) nie są dodawane — przycisk ukryty
    bukmacher: bet.bukmacher,
    stawka,
    dodano_ts: Math.floor(Date.now() / 1000),
    kurs_zamkniecia: null,
    wynik: "oczekuje",
    p_model: bet.p_model,
  };
  save([z, ...listZaklady()]);
  return z;
}

export function updateZaklad(id: string, patch: Partial<MojZaklad>) {
  save(listZaklady().map((z) => (z.id === id ? { ...z, ...patch } : z)));
}

export function removeZaklad(id: string) {
  save(listZaklady().filter((z) => z.id !== id));
}

export function isTracked(valueBetId: number): boolean {
  return listZaklady().some((z) => z.value_bet_id === valueBetId);
}

export function onZakladyChange(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** CLV — o ile lepszy kurs wzięliśmy niż kurs zamknięcia. */
export function clvPct(z: MojZaklad): number | null {
  if (!z.kurs_zamkniecia) return null;
  return (z.kurs / z.kurs_zamkniecia - 1) * 100;
}
