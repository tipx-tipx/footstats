/*
 * Mecze › „Najlepsze linie” (15.10) – rachunek wspólny dla listy linii
 * (przeglądarka) i zapowiedzi „N mocnych linii” na liście meczów (serwer).
 * Bez danych i bez Reacta – wolno go importować z obu stron.
 *
 * Zasady jak na stronie meczu: mecz bez minut to „nie zagrał” i nie liczy się
 * do wyniku; cena Betclica liczonego inaczej (inna statystyka) nie jest
 * porównywana. Do tego minimum rozegranych meczów w oknie (jak w pipeline,
 * `lekkie_klucze.MIN_ZAGRANYCH`) – inaczej „3/3” udaje pewniaka.
 */

export type Okno = 5 | 10;
export const MIN_ZAGRANYCH: Record<Okno, number> = { 10: 7, 5: 4 };

/** [mecz, zawodnik, rynek, linia, Superbet, Betclic, (1 = Betclic liczy inaczej)] – jak w kluczu `linie_dnia` */
export type LiniaS = [number, number, string, number, number | null, number | null, 1?];
export type FormaLinii = Record<string, [number[], number[]]>;

export type PokrycieLinii = { weszlo: number; zagrane: number; nz: number; udzial: number; srednia: number | null };

export function pokrycieLinii(v: number[], min: number[], linia: number, okno: Okno): PokrycieLinii {
  const mecze = v.slice(0, okno).map((x, i) => ({ x, m: min[i] ?? 90 }));
  const zagrane = mecze.filter((m) => m.m > 0);
  const weszlo = zagrane.filter((m) => m.x > linia).length;
  return {
    weszlo,
    zagrane: zagrane.length,
    nz: mecze.length - zagrane.length,
    udzial: zagrane.length ? weszlo / zagrane.length : 0,
    srednia: zagrane.length ? zagrane.reduce((a, m) => a + m.x, 0) / zagrane.length : null,
  };
}

export type Cena = { kurs: number; bukmacher: "Superbet" | "Betclic"; drugi: number | null };

/** wyższa z dwóch cen; przy remisie Superbet (jak na stronie meczu) */
export function najlepszaCena(sb: number | null, bc: number | null, inaczej: boolean): Cena | null {
  const b = inaczej ? null : bc;
  if (sb === null && b === null) return null;
  if (b === null || (sb !== null && sb >= b)) return { kurs: sb!, bukmacher: "Superbet", drugi: b };
  return { kurs: b, bukmacher: "Betclic", drugi: sb };
}

export type WarunkiLinii = {
  okno: Okno;
  /** udział trafień od (0–1) */
  pokrycie: number;
  /** najlepsza cena od */
  kurs: number;
};

/** domyślne filtry listy i próg „mocnej linii” w zapowiedzi na liście meczów */
export const DOMYSLNE_LINIE: WarunkiLinii = { okno: 10, pokrycie: 0.8, kurs: 1.4 };

export type WybranaLinia = { s: LiniaS; p: PokrycieLinii; cena: Cena };

/**
 * Siła dowodu pokrycia: dolna granica przedziału Wilsona (95%). Sam udział
 * stawiał 5/5 (pięć meczów bez gry) nad 9/10; tu 10/10 > 7/7 > 6/6 > 9/10 > 5/5
 * – mniej meczów to mniej pewności, nie remis.
 */
export function silaPokrycia(p: PokrycieLinii): number {
  const n = p.zagrane;
  if (!n) return 0;
  const z = 1.96;
  const f = p.weszlo / n;
  return (f + (z * z) / (2 * n) - z * Math.sqrt((f * (1 - f) + (z * z) / (4 * n)) / n)) / (1 + (z * z) / n);
}

const czlony = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^a-z]+/)
    .filter((x) => x.length >= 4);

/**
 * Ten sam zawodnik pod dwoma numerami (różna pisownia w źródłach, np.
 * „Saidou Alioum” i „Saidou Alioum Moubarak”) – ta sama linia w tym samym
 * meczu z identycznymi cenami i wspólnym członem nazwiska. Zostaje ten
 * z dłuższą historią.
 */
export function bezDubli(lista: WybranaLinia[], nazwa: (id: number) => string): WybranaLinia[] {
  const grupy = new Map<string, WybranaLinia[]>();
  for (const w of lista) {
    const k = `${w.s[0]}|${w.s[2]}|${w.s[3]}|${w.s[4]}|${w.s[5]}`;
    grupy.set(k, [...(grupy.get(k) ?? []), w]);
  }
  const out: WybranaLinia[] = [];
  for (const g of grupy.values()) {
    const zostaja: WybranaLinia[] = [];
    for (const w of [...g].sort((a, b) => b.p.zagrane - a.p.zagrane)) {
      const c = new Set(czlony(nazwa(w.s[1])));
      if (zostaja.some((x) => czlony(nazwa(x.s[1])).some((t) => c.has(t)))) continue;
      zostaja.push(w);
    }
    out.push(...zostaja);
  }
  return out;
}

const nazwaDruzyny = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

/** ta sama drużyna mimo różnej wielkości liter i znaków („Fk Jablonec” = „FK Jablonec”) */
export const taSamaDruzyna = (a: string, b: string) => {
  const x = nazwaDruzyny(a);
  return x !== "" && x === nazwaDruzyny(b);
};

/**
 * Jedna linia na zawodnika i rynek w meczu: NAJWYŻSZA, która spełnia
 * warunki (wyższa linia = wyższa cena przy tym samym progu pokrycia –
 * zasada 1. szczebla drabinki). `dodatkowo` – filtry gracza poza progami.
 */
export function wybierzLinie(linie: LiniaS[], forma: FormaLinii, w: WarunkiLinii, dodatkowo?: (s: LiniaS) => boolean): WybranaLinia[] {
  const naj = new Map<string, WybranaLinia>();
  for (const s of linie) {
    if (dodatkowo && !dodatkowo(s)) continue;
    const cena = najlepszaCena(s[4], s[5], s[6] === 1);
    if (!cena || cena.kurs < w.kurs) continue;
    const f = forma[`${s[1]}|${s[2]}`];
    if (!f) continue;
    const p = pokrycieLinii(f[0], f[1], s[3], w.okno);
    if (p.zagrane < MIN_ZAGRANYCH[w.okno] || p.udzial < w.pokrycie) continue;
    const k = `${s[0]}|${s[1]}|${s[2]}`;
    const stara = naj.get(k);
    if (!stara || s[3] > stara.s[3]) naj.set(k, { s, p, cena });
  }
  return [...naj.values()];
}
