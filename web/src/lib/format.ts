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

export function fmtDataCzas(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString("pl-PL", {
    day: "numeric",
    month: "short",
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
