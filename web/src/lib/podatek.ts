/**
 * Podatek od stawki – lustro `pipeline/footstats/model/betting.py`.
 *
 * W Polsce bukmacher pobiera 12% od STAWKI przy zawieraniu zakładu: z 10 zł
 * do gry idzie 8,80 zł, więc z wygranej wraca `stawka × 0,88 × kurs`.
 *
 * Konsekwencja, która zaskakuje: przy kursie poniżej 1/0,88 = 1,136 zakład
 * jest stratny NAWET przy stuprocentowej pewności.
 *
 * ROZDZIAŁ DWÓCH LICZB (decyzja usera 2026-07-31). W całym systemie:
 *   * `ev_pct`   – BRUTTO, tym decydują bramy publikacji po stronie Pythona,
 *   * `ev_netto` – PO PODATKU, i TO jest liczba dla użytkownika.
 * Front pokazuje wyłącznie netto. Bramy zostały na brutto celowo, żeby
 * wprowadzenie podatku nie zmieniło przy okazji selekcji typów – inaczej
 * w rozliczeniach nie dałoby się rozdzielić skutku jednego od drugiego.
 */

export const WSPOLCZYNNIK_PODATKU: Record<string, number> = {
  standard: 0.88,
  bez_podatku: 1,
  zwrot: 1,
};

export const TRYB_DOMYSLNY = "standard";

/** Kurs, poniżej którego nie da się wyjść na zero nawet przy pewności 100%. */
export const KURS_GRANICZNY = 1 / WSPOLCZYNNIK_PODATKU.standard;

export function wspolczynnik(tryb?: string | null): number {
  return WSPOLCZYNNIK_PODATKU[tryb ?? TRYB_DOMYSLNY] ?? WSPOLCZYNNIK_PODATKU.standard;
}

/** Ile realnie wraca z 1 zł stawki przy wygranej. */
export function kursNetto(kurs: number, tryb?: string | null): number {
  return kurs * wspolczynnik(tryb);
}

/** Ile realnie wraca ze stawki `stawka` – kwota do pokazania userowi. */
export function wyplata(kurs: number, stawka: number, tryb?: string | null): number {
  return kursNetto(kurs, tryb) * stawka;
}

/** Jaką trzeba mieć szansę, żeby przy tym kursie wyjść na zero. */
export function progOplacalnosciKursu(kurs: number, tryb?: string | null): number {
  const netto = kursNetto(kurs, tryb);
  return netto > 0 ? 1 / netto : 1;
}

/**
 * Wartość zakładu w %, po podatku.
 *
 * Rekordy sprzed 2026-07-31 nie mają `ev_netto` – dla nich liczymy je tutaj
 * z szansy i kursu, zamiast pokazywać brutto (byłoby o kilkanaście punktów
 * procentowych za dobre).
 */
export function wartoscNetto(bet: {
  ev_netto?: number | null;
  ev_pct?: number | null;
  p_model?: number | null;
  kurs?: number | null;
  tryb_podatku?: string | null;
}): number | null {
  if (bet.ev_netto != null) return bet.ev_netto;
  if (bet.p_model != null && bet.kurs != null) {
    return (bet.p_model * kursNetto(bet.kurs, bet.tryb_podatku) - 1) * 100;
  }
  return null;
}
