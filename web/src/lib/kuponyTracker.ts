"use client";

/** Magazyn zagranych kuponów w localStorage (narzędzie osobiste, jak
 *  lib/tracker.ts dla pojedynczych typów). Kupony modelu mają `klucz`,
 *  a pipeline i tak rozlicza każdy z nich — więc wynik zagranego kuponu
 *  bierzemy ZA DARMO z historii (typy_wyniki.kupony), po kluczu.
 */

import type { Kupon, KuponHistoria } from "./types";

export interface MojKupon {
  id: string;
  /** klucz kuponu modelu — po nim dojeżdża wynik z historii */
  klucz: string | null;
  cel_label: string | null;
  horyzont: string | null;
  kurs_laczny: number;
  p_model: number;
  stawka: number;
  dodano_ts: number;
  legi: {
    podmiot: string;
    rynek: string;
    linia: number;
    kurs: number;
    mecz: string;
  }[];
}

const KEY = "footstats.kupony.v1";
const EVENT = "footstats:kupony";

export function listKuponyZagrane(): MojKupon[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function save(kupony: MojKupon[]) {
  window.localStorage.setItem(KEY, JSON.stringify(kupony));
  window.dispatchEvent(new CustomEvent(EVENT));
}

export function addKuponZagrany(k: Kupon, stawka: number): MojKupon {
  const wpis: MojKupon = {
    id: `${Date.now()}-${k.klucz ?? k.kurs_laczny}`,
    klucz: k.klucz ?? null,
    cel_label: k.cel_label ?? String(k.cel),
    horyzont: k.horyzont ?? null,
    kurs_laczny: k.kurs_laczny,
    p_model: k.p_model,
    stawka,
    dodano_ts: Math.floor(Date.now() / 1000),
    legi: k.legi.map((l) => ({
      podmiot: l.podmiot,
      rynek: l.rynek,
      linia: l.linia,
      kurs: l.kurs,
      mecz: l.mecz,
    })),
  };
  save([wpis, ...listKuponyZagrane()]);
  return wpis;
}

export function updateKuponZagrany(id: string, patch: Partial<MojKupon>) {
  save(listKuponyZagrane().map((k) => (k.id === id ? { ...k, ...patch } : k)));
}

export function removeKuponZagrany(id: string) {
  save(listKuponyZagrane().filter((k) => k.id !== id));
}

export function removeKuponZagranyPoKluczu(klucz: string) {
  save(listKuponyZagrane().filter((k) => k.klucz !== klucz));
}

export function isKuponZagrany(klucz?: string): boolean {
  if (!klucz) return false;
  return listKuponyZagrane().some((k) => k.klucz === klucz);
}

export function onKuponyZagraneChange(cb: () => void): () => void {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

/** Wynik zagranego kuponu z historii rozliczeń (null = jeszcze w grze). */
export function wynikZHistorii(
  wpis: MojKupon,
  historia: KuponHistoria[],
): { wynik: KuponHistoria["wynik"]; kurs_rozliczony: number | null } {
  const h = wpis.klucz
    ? historia.find((x) => x.klucz === wpis.klucz)
    : undefined;
  return {
    wynik: h?.wynik ?? null,
    kurs_rozliczony: h?.kurs_rozliczony ?? null,
  };
}

/** Zysk wpisu przy znanym wyniku (zwrot/anulowany = stawka wraca, zysk 0). */
export function zyskKuponu(
  wpis: MojKupon,
  wynik: KuponHistoria["wynik"],
  kursRozliczony: number | null,
): number | null {
  if (wynik === "wygrany") {
    return wpis.stawka * ((kursRozliczony ?? wpis.kurs_laczny) - 1);
  }
  if (wynik === "przegrany") return -wpis.stawka;
  if (wynik === "zwrot" || wynik === "anulowany") return 0;
  return null;
}
