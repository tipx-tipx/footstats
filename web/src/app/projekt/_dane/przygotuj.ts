/**
 * Migawka danych dla warsztatu /projekt (zamrożona 30.09 z Supabase i statshub).
 *
 * Czemu migawka, a nie żywe gettery z lib/data: warianty porównujemy na TYCH
 * SAMYCH danych przez cały etap (inaczej zmiana wyglądu miesza się ze zmianą
 * treści), a każdy podgląd na żywo ciągnąłby paczkę z Supabase – limit
 * transferu już raz zablokował projekt.
 */


type DruzynaSurowa = {
  id: number;
  code: string;
  c1: string;
  c2: string | null;
  kraj: string;
  short: string;
  narodowa: boolean;
  kraj_slug?: string;
};

type LigaSurowa = {
  id: number;
  kraj: string;
  kategoria: string;
  flaga: string;
  c1: string | null;
  c2: string | null;
};

export type DruzynaV = {
  nazwa: string;
  kod: string;
  c1: string;
  c2: string;
  id: number | null;
  /** kod flagi circle-flags (np. "rs", "gb-eng") – tylko reprezentacje */
  flaga: string | null;
};

export type MeczV = {
  id: number;
  ts: number;
  dzien: string;
  godzina: string;
  gosp: DruzynaV;
  gosc: DruzynaV;
  okazje: number;
};

export type LigaV = {
  nazwa: string;
  kategoria: string;
  id: number | null;
  flaga: string | null;
  c1: string;
  c2: string;
  mecze: MeczV[];
};

export type DzienV = { klucz: string; etykieta: string; ile: number };

export type TypV = {
  id: number;
  kto: string;
  pozycja: string;
  druzyna: DruzynaV;
  rywal: DruzynaV;
  dzien: string;
  godzina: string;
  rynek: string;
  strona: string;
  linia: number;
  kurs: number;
  szansa: number;
  bukmacher: string;
  /** ostatnie mecze, od najstarszego do najnowszego */
  historia: number[];
  rywale: string[];
  /** minuty w tych meczach (0 = nie wszedł) */
  minuty: number[];
  /** data meczu „12.09” */
  daty: string[];
  /** mecz reprezentacji */
  kadra: boolean[];
  /** kurs, od którego typ ma sens (gdy bukmacher jeszcze nie wystawił) */
  kursUczciwy: number | null;
  /** bieżąca najlepsza cena tej linii, gdy różni się od ceny z publikacji (pipeline od 05.10) */
  kursTeraz?: number | null;
  kursTerazBukmacher?: string;
  uzasadnienie: string | null;
};
import { dzisZrodla, zrodlo } from "./zrodlo";

/** lekka lista WSZYSTKICH typów migawki – do filtrów i liczników */
export type TypLekki = {
  id: number;
  kto: string;
  /** „strzały powyżej 0,5” */
  opis: string;
  bukmacher: string;
  /** „Serbia – Walia” */
  mecz: string;
  rynek: string;
  p: number;
  kurs: number;
  ts: number;
  liga: string;
  polka: string;
  sklady: boolean;
  /** typ na całą drużynę (a nie zawodnika) */
  druzynowy: boolean;
};

const DRUZYNY = () => zrodlo().druzyny as Record<string, DruzynaSurowa>;
const LIGI = () => zrodlo().ligi as Record<string, LigaSurowa>;

/* ---- półki ----------------------------------------------------------- */

/**
 * Półka, na której typ widać na stronie (decyzja 01.10): są tylko „Wysokie
 * szanse” i „Wyższe kursy” (+ Drabinki z radaru). Typ bez półki albo
 * z półką spoza tych dwóch (np. „mocna_linia”) trafia na najbliższą po
 * szansie – od 70% do Wysokich szans, niżej do Wyższych kursów – żeby żaden
 * opublikowany typ nie znikał ze strony.
 */
export function polkaNaStronie(polka: string | null | undefined, p: number): "wysoka_szansa" | "wyzsze_kursy" {
  if (polka === "wysoka_szansa" || polka === "wyzsze_kursy") return polka;
  return p >= 0.7 ? "wysoka_szansa" : "wyzsze_kursy";
}

/* ---- flagi ---------------------------------------------------------- */

const FLAGI_SPECJALNE: Record<string, string> = {
  england: "gb-eng",
  scotland: "gb-sct",
  wales: "gb-wls",
  "northern-ireland": "gb-nir",
  europe: "european_union",
  usa: "us",
  EN: "gb-eng",
};

const slugKraju = (s: string) =>
  s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");

/** slug angielskiej nazwy kraju -> alpha2, z Intl (bez ręcznej tabeli) */
const ALPHA2_ZE_SLUGU: Record<string, string> = (() => {
  const nazwy = new Intl.DisplayNames(["en"], { type: "region" });
  const out: Record<string, string> = {};
  for (let a = 65; a <= 90; a++) {
    for (let b = 65; b <= 90; b++) {
      const kod = String.fromCharCode(a, b);
      try {
        const n = nazwy.of(kod);
        if (n && n !== kod) out[slugKraju(n)] = kod.toLowerCase();
      } catch {
        /* kod spoza ISO */
      }
    }
  }
  out.czechia = "cz";
  out["bosnia-herzegovina"] = "ba";
  out["republic-of-ireland"] = "ie";
  out.turkiye = "tr";
  return out;
})();

function flagaZeSlugu(slug: string | undefined): string | null {
  if (!slug) return null;
  return FLAGI_SPECJALNE[slug] ?? ALPHA2_ZE_SLUGU[slug] ?? null;
}

/* ---- drużyny ---------------------------------------------------------- */

const SLOWA_POMIJANE = /^(fc|cf|sc|cd|ac|afc|ca|cs|se|ec|sv|fk|club|de|u21|u23|the)$/i;

function kodDruzyny(nazwa: string, s?: DruzynaSurowa): string {
  if (s?.code) return s.code;
  const slowa = (s?.short || nazwa)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[\s.\-']+/)
    .filter((w) => w && !SLOWA_POMIJANE.test(w));
  if (slowa.length === 0) return nazwa.slice(0, 3).toUpperCase();
  if (slowa.length >= 2 && slowa[0].length <= 3) {
    return (slowa[0] + slowa[1][0]).slice(0, 3).toUpperCase();
  }
  return slowa[0].slice(0, 3).toUpperCase();
}

export function druzyna(nazwa: string): DruzynaV {
  const s = DRUZYNY()[nazwa];
  return {
    nazwa,
    kod: kodDruzyny(nazwa, s),
    c1: s?.c1 || "#6b7478",
    c2: s?.c2 || s?.c1 || "#6b7478",
    id: s?.id ?? null,
    flaga: s?.narodowa ? flagaZeSlugu(s.kraj_slug) : null,
  };
}

/* ---- czas ------------------------------------------------------------- */

export { DZIEN_FMT, GODZ_FMT, dzienTs, etykietaDnia } from "./formatCzasu";
import { GODZ_FMT, dzienTs, etykietaDnia } from "./formatCzasu";


/* ---- składanie -------------------------------------------------------- */

export const POZYCJE: Record<string, string> = {
  G: "bramkarz",
  D: "obrońca",
  M: "pomocnik",
  F: "napastnik",
};

type MeczSurowy = {
  id: number;
  liga: string;
  kickoff_ts: number;
  gospodarz: string;
  gosc: string;
  okazje: number[];
};

type TypSurowy = {
  id: number;
  podmiot: string;
  podmiot_id: number;
  podmiot_typ: string;
  druzyna: string;
  przeciwnik: string;
  rynek: string;
  rynek_kod: string;
  strona: string;
  linia: number;
  kurs: number;
  p_model: number;
  bukmacher: string;
  kickoff_ts: number;
  mecz_id: number;
  polka?: string;
  fair_kurs?: number | null;
  kurs_teraz?: number | null;
  kurs_teraz_bukmacher?: string;
  uzasadnienie?: { czynniki?: { nazwa: string; opis: string }[] };
};

type ZawodnikSurowy = {
  id: number;
  pozycja: string;
  forma: Record<string, { ostatnie: number[]; rywale?: string[]; minuty?: number[]; ts?: number[]; kadra?: boolean[] }>;
};

export function przygotujFundamenty() {
  const mecze = (zrodlo().mecze as MeczSurowy[]).slice().sort((a, b) => a.kickoff_ts - b.kickoff_ts);
  // „dziś” migawki = dzień jej zrobienia, nie dzień oglądania – inaczej za
  // tydzień pasek dni pokazywałby same „Czw 8.10” zamiast Dziś/Jutro
  const dzis = dzisZrodla();

  const liczDni = new Map<string, number>();
  for (const m of mecze) {
    const k = dzienTs(m.kickoff_ts);
    liczDni.set(k, (liczDni.get(k) ?? 0) + 1);
  }
  const dni: DzienV[] = [...liczDni.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([klucz, ile]) => ({ klucz, etykieta: etykietaDnia(klucz, dzis), ile }));

  const ligi = new Map<string, LigaV>();
  for (const m of mecze) {
    let l = ligi.get(m.liga);
    if (!l) {
      const s = LIGI()[m.liga];
      l = {
        nazwa: m.liga,
        kategoria: s?.kategoria ?? "",
        id: s?.id ?? null,
        flaga: s ? (FLAGI_SPECJALNE[s.kraj] ?? (s.kraj ? s.kraj.toLowerCase() : flagaZeSlugu(s.flaga))) : null,
        c1: s?.c1 || s?.c2 || "#6b7478",
        c2: s?.c2 || s?.c1 || "#6b7478",
        mecze: [],
      };
      ligi.set(m.liga, l);
    }
    l.mecze.push({
      id: m.id,
      ts: m.kickoff_ts,
      dzien: dzienTs(m.kickoff_ts),
      godzina: GODZ_FMT.format(new Date(m.kickoff_ts * 1000)),
      gosp: druzyna(m.gospodarz),
      gosc: druzyna(m.gosc),
      okazje: m.okazje?.length ?? 0,
    });
  }

  const zawodnicy = new Map((zrodlo().zawodnicy as ZawodnikSurowy[]).map((z) => [z.id, z]));
  const kandydaci = (zrodlo().typy as TypSurowy[])
    .filter((t) => t.podmiot_typ === "zawodnik" && zawodnicy.get(t.podmiot_id)?.forma?.[t.rynek_kod])
    .sort((a, b) => b.p_model - a.p_model);
  const zbuduj = (t: TypSurowy): TypV => {
    const z = zawodnicy.get(t.podmiot_id)!;
    const f = z.forma[t.rynek_kod];
    return {
      id: t.id,
      kto: t.podmiot,
      pozycja: POZYCJE[z.pozycja] ?? z.pozycja,
      druzyna: druzyna(t.druzyna),
      rywal: druzyna(t.przeciwnik),
      dzien: etykietaDnia(dzienTs(t.kickoff_ts), dzis),
      godzina: GODZ_FMT.format(new Date(t.kickoff_ts * 1000)),
      rynek: t.rynek,
      strona: t.strona,
      linia: t.linia,
      kurs: t.kurs,
      szansa: t.p_model,
      bukmacher: t.bukmacher,
      historia: f.ostatnie.slice(0, 10).reverse(),
      rywale: (f.rywale ?? []).slice(0, 10).reverse(),
      minuty: (f.minuty ?? []).slice(0, 10).reverse(),
      daty: (f.ts ?? []).slice(0, 10).reverse().map((x) => {
        const d = new Date(x * 1000);
        return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
      }),
      kadra: (f.kadra ?? []).slice(0, 10).reverse(),
      kursUczciwy: t.fair_kurs ?? null,
      kursTeraz: t.kurs_teraz ?? null,
      kursTerazBukmacher: t.kurs_teraz_bukmacher,
      uzasadnienie: t.uzasadnienie?.czynniki?.[0]?.opis ?? null,
    };
  };

  const rynki = new Set<string>();
  const typy: TypV[] = [];
  for (const t of kandydaci) {
    if (rynki.has(t.rynek_kod) || typy.length >= 3) continue;
    rynki.add(t.rynek_kod);
    typy.push(zbuduj(t));
  }
  // przykład z meczem „nie zagrał” (0 minut) – do pokazania znaku NZ
  const zNz = kandydaci.find((t) => (zawodnicy.get(t.podmiot_id)!.forma[t.rynek_kod].minuty ?? []).slice(0, 10).includes(0));
  const przykladNZ = zNz ? zbuduj(zNz) : null;

  const licznikRynkow = new Map<string, number>();
  for (const t of zrodlo().typy as TypSurowy[]) {
    const n = t.rynek.replace(/\s*drużyny\s*/g, " ").trim();
    licznikRynkow.set(n, (licznikRynkow.get(n) ?? 0) + 1);
  }
  const rynkiTypow = [...licznikRynkow.entries()]
    .map(([nazwa, ile]) => ({ nazwa, ile }))
    .sort((a, b) => b.ile - a.ile);

  const meczPoId = new Map(mecze.map((m) => [m.id, m]));
  const wszystkie: TypLekki[] = (zrodlo().typy as TypSurowy[]).map((t) => {
    const m = meczPoId.get(t.mecz_id);
    return {
      id: t.id,
      kto: t.podmiot,
      opis: `${t.rynek.toLowerCase()} ${t.strona === "ponizej" ? "poniżej" : "powyżej"} ${String(t.linia).replace(".", ",")}`,
      bukmacher: t.bukmacher,
      mecz: m ? `${m.gospodarz} – ${m.gosc}` : "",
      rynek: t.rynek.replace(/\s*drużyny\s*/g, " ").trim(),
      p: t.p_model,
      kurs: t.kurs,
      ts: t.kickoff_ts,
      liga: m?.liga ?? "",
      polka: polkaNaStronie(t.polka, t.p_model),
      sklady: Boolean((m as { sklady_ogloszone?: boolean } | undefined)?.sklady_ogloszone),
      druzynowy: t.podmiot_typ === "druzyna",
    };
  });
  const drabinki = ((zrodlo().radar as { wpisy?: unknown[] }).wpisy ?? []).length;

  const ligiTypow = [...new Set(wszystkie.map((t) => t.liga))].map((nazwa) => {
    const l = ligi.get(nazwa);
    return {
      nazwa,
      kategoria: l?.kategoria ?? "",
      flaga: l?.flaga ?? null,
      id: l?.id ?? null,
      c1: l?.c1 ?? "#6b7478",
      c2: l?.c2 ?? "#6b7478",
    };
  });

  return {
    dni,
    ligiTypow,
    ligi: [...ligi.values()],
    typy,
    przykladNZ,
    rynki: rynkiTypow,
    wszystkichTypow: wszystkie.length,
    wszystkie,
    drabinki,
  };
}

export type DaneFundamentow = ReturnType<typeof przygotujFundamenty>;
