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

/**
 * [mecz, zawodnik, rynek, linia, Superbet, Betclic, (flaga)] – jak w kluczu `linie_dnia`.
 * Flaga 1 = Betclic liczy inaczej (cena ukryta), 2 = ceny mocno się różnią przy tej
 * samej statystyce – cena Betclica prawdziwa i liczy się jak każda (05.11).
 */
export type LiniaS = [number, number, string, number, number | null, number | null, (1 | 2)?];
/**
 * "zawodnik|rynek" → [ostatnie 10, minuty 10, (pozycje meczów)] od najnowszego.
 * Trzecie pole (klucz w2, 05.11): brak = kratki to początek listy meczów
 * zawodnika, tablica = ich pozycje w tej liście, null = bez dymka.
 */
export type FormaLinii = Record<string, [number[], number[], (number[] | null)?]>;

/**
 * Progi pokrycia do wyboru (05.11, właściciel: „w przypadku 10 meczów nawet
 * może być 50%”). Próg to „co najmniej k z okna” – w oknie 5 nie ma 50%
 * (2,5 meczu), najniżej 3/5. `od` – najniższy próg, z jakim pipeline zbudował
 * klucz (bezpiecznik rozmiaru, `lekkie_klucze.PROGI_POKRYCIA_LINII`).
 */
export function progiPokrycia(okno: Okno, od = 0.5): number[] {
  const out: number[] = [];
  for (let k = Math.ceil(okno / 2); k <= okno; k++) if (k / okno >= od - 1e-9) out.push(k / okno);
  return out;
}

/** próg dla innego okna: najbliższy możliwy, nie niższy (50% w oknie 5 → 3/5) */
export function progDlaOkna(pokrycie: number, okno: Okno, od = 0.5): number {
  const progi = progiPokrycia(okno, od);
  return progi.find((p) => p >= pokrycie - 1e-9) ?? progi[progi.length - 1];
}

/** „7/10” – próg tak, jak go liczy gracz */
export const progTxt = (pokrycie: number, okno: Okno) => `${Math.round(pokrycie * okno)}/${okno}`;

/**
 * ⚑ OKNO = OSTATNIE N WYSTĘPÓW (05.11, właściciel: „6 na 8, a nie 6 na 10 …
 * żeby to było przemyślane pod każdy przypadek”). Dotąd okno było N ostatnich
 * MECZÓW razem z „nie zagrał”, więc mianownik spadał (6/8), a pipeline (model,
 * sito drabinek – `pokrycie_historii`) liczył już z N ostatnich WYSTĘPÓW.
 * Teraz tak samo: „nie zagrał” (minuty 0) nie zajmuje miejsca w oknie – okno
 * sięga dalej wstecz (historia ma do 20 meczów), a ile razy nie zagrał w tym
 * czasie, mówi osobna liczba. Mecz BEZ DANYCH dla rynku (minuty −1, np. brak
 * mapy strzałów w FotMob) zajmuje miejsce i jest widoczny jako „?” – świeżość
 * okna się nie cofa – ale do wyniku się nie liczy. Mianownik < N zostaje więc
 * tylko przy krótkiej historii albo braku danych, a próg pokrycia działa wtedy
 * jako odsetek znanych występów (7/10 = 70%: przy 8 znanych trzeba 6).
 */
export const MIN_BRAK_DANYCH = -1;

export function oknoWystepow<T extends { min: number }>(mecze: T[], okno: number): { mecze: T[]; nz: number; bd: number } {
  const out: T[] = [];
  let nz = 0;
  for (const m of mecze) {
    if (out.length >= okno) break;
    if (m.min === 0) {
      nz += 1;
      continue;
    }
    out.push(m);
  }
  return { mecze: out, nz, bd: out.filter((m) => m.min < 0).length };
}

/** podpis pod wynikiem: odsetek, a gdy okno sięgnęło dalej albo czegoś brak – dlaczego (05.11) */
export function podpisWyniku(p: { nz: number; bd?: number; udzial: number }) {
  const czesci = [p.nz ? `${p.nz}× nie grał` : "", p.bd ? `${p.bd}× brak danych` : ""].filter(Boolean);
  return czesci.length ? czesci.join(" · ") : `${Math.round(p.udzial * 100)}%`;
}

/** stan kratki: „?” brak danych, „NZ” nie zagrał, trafione / nie */
export const stanKratki = (min: number, trafil: boolean) => (min < 0 ? "brak" : min === 0 ? "nz" : trafil ? "ok" : "nie");

export type PokrycieLinii = { weszlo: number; zagrane: number; nz: number; bd: number; udzial: number; srednia: number | null };

/** `nzPoza` – „nie zagrał” wycięte już w pipeline (klucz `linie_dnia` niesie okno bez nich) */
export function pokrycieLinii(v: number[], min: number[], linia: number, okno: Okno, nzPoza = 0): PokrycieLinii {
  const w = oknoWystepow(
    v.map((x, i) => ({ x, min: min[i] ?? 90 })),
    okno,
  );
  const zagrane = w.mecze.filter((m) => m.min > 0);
  const weszlo = zagrane.filter((m) => m.x > linia).length;
  return {
    weszlo,
    zagrane: zagrane.length,
    nz: w.nz + nzPoza,
    bd: w.bd,
    udzial: zagrane.length ? weszlo / zagrane.length : 0,
    srednia: zagrane.length ? zagrane.reduce((a, m) => a + m.x, 0) / zagrane.length : null,
  };
}

/** [dzień UTC, numer rywala w `druzyny`] – mecze zawodnika od najnowszego (klucz w2) */
export type MeczZawodnika = [number, number];

/**
 * Rywal i data każdej kratki (dymek, 05.11). `null` = klucz bez tych danych
 * (stary kształt albo pipeline nie miał dat) – kratki bez dymka.
 */
export function meczeKratek(f: FormaLinii[string], mecze: MeczZawodnika[] | undefined, druzyny: string[], okno: number): { rywal: string; data: string }[] | null {
  if (!mecze?.length || f[2] === null) return null;
  const n = Math.min(okno, f[0].length);
  const poz = f[2] ?? Array.from({ length: n }, (_, i) => i);
  const out: { rywal: string; data: string }[] = [];
  for (let i = 0; i < n; i++) {
    const m = mecze[poz[i]];
    if (!m) return null;
    const d = new Date(m[0] * 86400000);
    out.push({ rywal: druzyny[m[1]] ?? "", data: `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}` });
  }
  return out;
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

/**
 * suwak „kurs od”: 1,30 (dolna granica pipeline'u) … 4,00, co 0,10.
 * Pomiar 05.11 (50%, 3996 linii): powyżej 4,00 – 3%, powyżej 3,00 – 9%;
 * dłuższa skala ściskała 1,30–2,50, gdzie jest 85% linii.
 */
export const KURS_MIN = 1.3;
export const KURS_MAX = 4;
export const KURS_KROK = 0.1;

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
  for (const x of liniePokrycia(linie, forma, w, dodatkowo)) {
    const k = `${x.s[0]}|${x.s[1]}|${x.s[2]}`;
    const stara = naj.get(k);
    if (!stara || x.s[3] > stara.s[3]) naj.set(k, x);
  }
  return [...naj.values()];
}

/** cena od progu (z zapasem na liczby zmiennoprzecinkowe – 1,40 z suwaka to 1.4000000001) */
const wCenie = (kurs: number, w: WarunkiLinii) => kurs >= w.kurs - 1e-9;

/** wszystkie linie spełniające progi (przed wyborem jednej na zawodnika i rynek) */
export function liniePokrycia(linie: LiniaS[], forma: FormaLinii, w: WarunkiLinii, dodatkowo?: (s: LiniaS) => boolean): WybranaLinia[] {
  const out: WybranaLinia[] = [];
  for (const s of linie) {
    if (dodatkowo && !dodatkowo(s)) continue;
    const cena = najlepszaCena(s[4], s[5], s[6] === 1);
    if (!cena || !wCenie(cena.kurs, w)) continue;
    const f = forma[`${s[1]}|${s[2]}`];
    if (!f) continue;
    const p = pokrycieLinii(f[0], f[1], s[3], w.okno);
    // 1e-9: 7/10 i 0,7 to ta sama liczba, ale 6/10 liczone inną drogą już nie zawsze
    if (p.zagrane < MIN_ZAGRANYCH[w.okno] || p.udzial < w.pokrycie - 1e-9) continue;
    out.push({ s, p, cena });
  }
  return out;
}
