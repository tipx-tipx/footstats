/** Formatowanie liczb i dat po polsku. */

export function fmtProc(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits).replace(".", ",")}%`;
}

export function fmtKurs(k: number): string {
  return k.toFixed(2).replace(".", ",");
}

export function fmtLinia(l: number): string {
  return l.toFixed(1).replace(".", ",");
}

export function fmtEV(ev: number): string {
  const sign = ev > 0 ? "+" : "";
  return `${sign}${ev.toFixed(1).replace(".", ",")}%`;
}

export function fmtMnoznik(m: number): string {
  return `×${m.toFixed(2).replace(".", ",")}`;
}

/** Bilans w jednostkach (stawka 1 j. na typ): "+8,2u", "−3u", "0u". */
export function fmtU(v: number): string {
  const s = v.toFixed(2).replace(".", ",").replace(/,?0+$/, "");
  return `${v > 0 ? "+" : ""}${s === "" || s === "-" ? "0" : s}u`;
}

/**
 * Odmiana rzeczownika przez liczbę – po polsku formy są TRZY, nie dwie:
 * 1 zakład, 2–4 zakłady, 5+ zakładów. Warunek „nie 12–14" jest konieczny,
 * bo 22 idzie jak 2, ale 12 jak 5.
 *
 *     odmien(26, "zakład", "zakłady", "zakładów")  ->  "zakładów"
 */
export function odmien(
  n: number,
  jeden: string,
  dwaCztery: string,
  wiele: string,
): string {
  const a = Math.abs(Math.round(n));
  if (a === 1) return jeden;
  const r10 = a % 10;
  const r100 = a % 100;
  if (r10 >= 2 && r10 <= 4 && !(r100 >= 12 && r100 <= 14)) return dwaCztery;
  return wiele;
}

/**
 * Teksty z pipeline miewają kropkę dziesiętną ("Średnio 2.80") – na widoku
 * zamieniamy ją na przecinek. Tylko między cyframi, reszta tekstu nietknięta.
 */
export function fmtOpisLiczby(s: string): string {
  return s.replace(/(\d)\.(\d)/g, "$1,$2");
}

export function fmtDataCzas(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  });
}

/** "2026-07-10" -> "czw, 10 lip" (dłużej: "czwartek, 10 lipca").
 *  Doba brana z południa lokalnego – inaczej strefa przesuwa etykietę o dzień. */
export function fmtDzien(dzien: string, dlugo = false): string {
  return new Intl.DateTimeFormat("pl-PL", {
    weekday: dlugo ? "long" : "short",
    day: "numeric",
    month: dlugo ? "long" : "short",
  }).format(new Date(`${dzien}T12:00:00`));
}

/** Sama godzina kickoffu ("20:15") w czasie polskim. */
export function fmtGodzina(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Warsaw",
  });
}

export const STRONA_LABEL: Record<string, string> = {
  powyzej: "powyżej",
  ponizej: "poniżej",
};

export const PEWNOSC_LABEL: Record<string, string> = {
  wysoka: "wysoka",
  srednia: "średnia",
  niska: "niska",
};

export const RYZYKO_LABEL: Record<string, string> = {
  niskie: "niskie",
  srednie: "średnie",
  wysokie: "wysokie",
};
