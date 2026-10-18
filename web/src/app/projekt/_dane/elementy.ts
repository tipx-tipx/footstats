/**
 * Etap 3 – dane do głównych elementów (wiersz meczu, karta typu, drabinka,
 * kupon) z tej samej zamrożonej migawki co etapy 1–2.
 */

import { fmtKurs } from "@/lib/format";
import type { OznaczenieTypu } from "@/lib/oznaczenia";

import { dzisZrodla, zrodlo } from "./zrodlo";
import {
  druzyna,
  dzienTs,
  etykietaDnia,
  GODZ_FMT,
  POZYCJE,
  przygotujFundamenty,
  type DruzynaV,
  type TypV,
} from "./przygotuj";


export type Powod = { tekst: string; kier: "za" | "przeciw" | "baza" };

export type KartaV = TypV & {
  /** numer zawodnika (strona zawodnika); typ drużynowy – brak */
  podmiotId?: number;
  podmiotTyp: "zawodnik" | "druzyna";
  mecz: string;
  powody: Powod[];
  /** oznaczenia z pipeline (`OZNACZENIA_TYPU`, 18.10) – tylko te z przewagą nad kursem w księdze */
  oznaczenia?: OznaczenieTypu[];
};

export type MeczE = {
  id: number;
  ts: number;
  godzina: string;
  dzien: string;
  gosp: DruzynaV;
  gosc: DruzynaV;
  liga: string;
  ligaFlaga: string | null;
  ligaId: number | null;
  ligaC1: string;
  ligaC2: string;
  kategoria: string;
  okazje: number;
  sedzia: string | null;
  sklady: boolean;
  najlepszy: { kto: string; opis: string; p: number; kurs: number; bukmacher: string } | null;
  szanse: number[];
};

/** `bukmacher` – u kogo ta cena (05.10: karta pisała „Superbet” na sztywno, także przy cenach Betclica) */
export type SzczebelV = {
  linia: number;
  kurs: number;
  p: number | null;
  traf: number;
  z: number;
  polecany: boolean;
  bukmacher: "Superbet" | "Betclic";
  /** polecany szczebel: bieżąca cena, gdy różni się od ceny z publikacji (pipeline od 05.10) */
  teraz?: number | null;
  terazBukmacher?: string;
  /** ta sama linia u Betclica – tylko pewna cena (siatka strony meczu, bez „Betclic liczy inaczej”) */
  betclic?: number | null;
};

/**
 * RODZAJ DRABINKI = powód, na którym karta stoi (logika właściciela 17.09:
 * pokrycie, forma, pewny start, hojny rywal, cena; perełka 18.09). Jedna karta
 * może mieć kilka, każdy tylko wtedy, gdy dane go potwierdzają – karta bez
 * powodu ponad sito nie dostaje żadnego (zwykła drabinka).
 */
export type RodzajD = {
  kod:
    | "perla" | "cena_pewne" | "cena_lepsza" | "przewaga" | "ceny_zgodne"
    | "seria" | "forma" | "transfer"
    | "rywal";
  /**
   * KOLOR = ZNACZENIE GRUPY, nie rodzaju (11.10): „cena” bursztyn (argument
   * z kursu), „forma” zieleń (ta sama co trafienia w historii), „mecz”
   * zwykły tekst z herbem rywala. Trzy barwy zamiast tęczy po jednej na rodzaj.
   */
  grupa: "cena" | "forma" | "mecz";
  /** 1–3 słowa do nagłówka karty, rzeczownik, bez ozdobników */
  krotko: string;
  /** pełne zdanie z liczbą, która je potwierdza */
  zdanie: string;
  /** „ceny zgodne” to potwierdzenie, nie powód – nie idzie do nagłówka */
  wNaglowku: boolean;
};

/** Cena polecanego szczebla u obu bukmacherów – gdy obie są pewne. */
export type CenyD = {
  superbet: number;
  betclic: number;
  /** kto płaci więcej */
  lepszy: "Superbet" | "Betclic";
  typ: "lepsza" | "pewne" | "zgodne";
};

export type DrabinkaV = {
  kto: string;
  pozycja: string;
  druzyna: DruzynaV;
  rywal: DruzynaV;
  mecz: string;
  dzien: string;
  godzina: string;
  rynek: string;
  szczeble: SzczebelV[];
  /** od najstarszego do najnowszego – jak w TypV */
  historia: number[];
  minuty: number[];
  rywale: string[];
  /** początek meczu – do wyboru dnia na liście (nie ma go w przykładach z warsztatu) */
  ts?: number;
  /** numer zawodnika – link do jego strony */
  podmiotId?: number;
  klucz?: string;
  /** od najważniejszego; pusta = zwykła drabinka */
  rodzaje?: RodzajD[];
  /**
   * SKŁAD – warunek, nie atut (właściciel 11.10: „każdy w drabince ma mieć
   * w miarę pewny start, to nie jest korzyść drabinki”). Znak przy nazwisku,
   * nie rodzaj: ogłoszony XI albo pewny start z historii.
   */
  sklad?: { stan: "ogloszony" | "pewny_start"; opis: string } | null;
  ceny?: CenyD | null;
};

export type NogaV = {
  kto: string;
  opis: string;
  kurs: number;
  p: number;
  mecz: string;
  gosp: DruzynaV;
  gosc: DruzynaV;
  godzina: string;
  dzien: string;
  ts: number;
  bukmacher: string;
};

export type KuponV = {
  cel: number;
  kurs: number;
  p: number;
  horyzont: string;
  sklady: number;
  mecze: number;
  najslabszy: number;
  nogi: NogaV[];
};

type Czynnik = { nazwa: string; opis: string; mnoznik: number | null };

type TypS = {
  id: number;
  podmiot: string;
  podmiot_typ: string;
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
  fair_kurs?: number | null;
  kurs_teraz?: number | null;
  kurs_teraz_bukmacher?: string;
  uzasadnienie?: { czynniki?: Czynnik[] };
};

type MeczS = {
  id: number;
  liga: string;
  kickoff_ts: number;
  gospodarz: string;
  gosc: string;
  okazje: number[];
  sedzia: string | null;
  sklady_ogloszone?: boolean;
};

/**
 * Powody PO LUDZKU – próbka kierunku z wątku „teksty”. Pipeline pisze językiem
 * modelu („efektywna próba”, „norma ligi”, „skorelowane statystyki”); tu widać,
 * jak ma to brzmieć dla gracza. Czynnik bez wpływu nie trafia na kartę.
 */
export function powodPoLudzku(c: Czynnik, rynek: string): Powod | null {
  const kier: Powod["kier"] = c.mnoznik === null ? "baza" : c.mnoznik > 1.02 ? "za" : c.mnoznik < 0.98 ? "przeciw" : "baza";
  if (c.mnoznik !== null && kier === "baza") return null;
  const r = rynek.toLowerCase().replace(/\s*drużyny\s*/, " ").trim();
  if (c.nazwa === "Poziom bazowy") {
    const m = c.opis.match(/Średnio ([\d,]+) (na 90 minut|na mecz)/);
    const l5 = c.opis.match(/ostatnie 5 meczów: ([\d,]+)/);
    return m ? { kier, tekst: `Średnio ${m[1]} ${m[2]}${l5 ? `, w ostatnich 5 meczach ${l5[1]}` : ""}` } : null;
  }
  if (c.nazwa === "Minuty") {
    const m = c.opis.match(/Przewidywane (\d+) min gry, (\d+)% szans na pierwszy skład/);
    return m ? { kier, tekst: `Powinien zagrać ok. ${m[1]} minut (${m[2]}% szans na wyjściowy skład)` } : null;
  }
  if (c.nazwa === "Profil rywala") {
    const a = c.opis.match(/przeciw (.+?) średnio ([\d,]+) przy normie ligi ([\d,]+)/);
    if (a) return { kier, tekst: `Przeciw ${a[1]} rywale mają średnio ${a[2]} (${r}), w lidze ${a[3]}` };
    const b = c.opis.match(/^(.+?) dopuszcza więcej/);
    if (b) return { kier, tekst: `${b[1]} pozwala na więcej takich akcji niż przeciętny rywal` };
    return { kier, tekst: kier === "za" ? "Rywal pozwala na więcej niż przeciętny" : "Rywal pozwala na mniej niż przeciętny" };
  }
  if (c.nazwa.startsWith("Dom")) {
    // kierunek bierzemy z liczby, nie z założenia – faule na wyjeździe ROSNĄ
    const gdzie = /siebie/.test(c.opis) ? "Gra u siebie" : "Gra na wyjeździe";
    return { kier, tekst: `${gdzie}, a w tym zakładzie to ${kier === "za" ? "pomaga" : "przeszkadza"}` };
  }
  if (c.nazwa === "Styl rywala") return { kier, tekst: kier === "za" ? "Styl gry rywala sprzyja temu zakładowi" : "Styl gry rywala nie sprzyja" };
  if (c.nazwa === "Scenariusz meczu") {
    return {
      kier,
      tekst: kier === "za" ? "Kursy na sam mecz zapowiadają korzystny przebieg" : "Kursy na sam mecz zapowiadają trudniejszy mecz",
    };
  }
  return { kier, tekst: c.opis.split(/[;(]/)[0].trim() };
}

const data = (ts: number) => {
  const d = new Date(ts * 1000);
  return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export function przygotujElementy() {
  const baza = przygotujFundamenty();
  const typySur = zrodlo().typy as TypS[];
  const mecze = zrodlo().mecze as MeczS[];
  const meczPoId = new Map(mecze.map((m) => [m.id, m]));
  const nazwaMeczu = (id: number) => {
    const m = meczPoId.get(id);
    return m ? `${m.gospodarz} – ${m.gosc}` : "";
  };
  const powody = (t: TypS) =>
    (t.uzasadnienie?.czynniki ?? []).map((c) => powodPoLudzku(c, t.rynek)).filter((x): x is Powod => x !== null);

  /* karty: 2 zawodników z historią + 1 drużyna (forma drużyn) */
  const karty: KartaV[] = baza.typy.slice(0, 2).map((t) => {
    const s = typySur.find((x) => x.id === t.id)!;
    return { ...t, podmiotTyp: "zawodnik", mecz: nazwaMeczu(s.mecz_id), powody: powody(s) };
  });
  type Forma = { nazwa: string; forma: Record<string, { ostatnie: number[]; rywale?: string[]; ts?: number[] }> };
  const formy = zrodlo().druzynyForma as Forma[];
  const dr = typySur.find((t) => t.podmiot_typ === "druzyna" && formy.find((f) => f.nazwa === t.podmiot)?.forma?.[t.rynek_kod]);
  if (dr) {
    const f = formy.find((x) => x.nazwa === dr.podmiot)!.forma[dr.rynek_kod];
    const n = Math.min(10, f.ostatnie.length);
    karty.push({
      id: dr.id,
      kto: dr.podmiot,
      pozycja: "drużyna",
      druzyna: druzyna(dr.podmiot),
      rywal: druzyna(dr.przeciwnik),
      dzien: etykietaDnia(dzienTs(dr.kickoff_ts), dzisZrodla()),
      godzina: GODZ_FMT.format(new Date(dr.kickoff_ts * 1000)),
      rynek: dr.rynek,
      strona: dr.strona,
      linia: dr.linia,
      kurs: dr.kurs,
      szansa: dr.p_model,
      bukmacher: dr.bukmacher,
      historia: f.ostatnie.slice(0, n).reverse(),
      rywale: (f.rywale ?? []).slice(0, n).reverse(),
      minuty: Array(n).fill(90),
      daty: (f.ts ?? []).slice(0, n).reverse().map(data),
      kadra: Array(n).fill(false),
      kursUczciwy: dr.fair_kurs ?? null,
      kursTeraz: dr.kurs_teraz ?? null,
      kursTerazBukmacher: dr.kurs_teraz_bukmacher,
      uzasadnienie: null,
      podmiotTyp: "druzyna",
      mecz: nazwaMeczu(dr.mecz_id),
      powody: powody(dr),
    });
  }

  /* mecze z typami, z najmocniejszym typem */
  const meczeWszystkie: MeczE[] = mecze
    .filter((m) => m.okazje?.length || zrodlo().oferta[String(m.id)])
    .sort((a, b) => a.kickoff_ts - b.kickoff_ts)
    .map((m): MeczE => {
      const typyMeczu = typySur.filter((t) => t.mecz_id === m.id).sort((a, b) => b.p_model - a.p_model);
      const n = typyMeczu[0];
      const l = baza.ligi.find((x) => x.nazwa === m.liga);
      return {
        id: m.id,
        ts: m.kickoff_ts,
        godzina: GODZ_FMT.format(new Date(m.kickoff_ts * 1000)),
        dzien: etykietaDnia(dzienTs(m.kickoff_ts), dzisZrodla()),
        gosp: druzyna(m.gospodarz),
        gosc: druzyna(m.gosc),
        liga: m.liga,
        ligaFlaga: l?.flaga ?? null,
        ligaId: l?.id ?? null,
        ligaC1: l?.c1 ?? "#6b7478",
        ligaC2: l?.c2 ?? "#6b7478",
        kategoria: l?.kategoria ?? "",
        okazje: Math.max(typyMeczu.length, m.okazje?.length ?? 0),
        sedzia: m.sedzia,
        sklady: Boolean(m.sklady_ogloszone),
        najlepszy: n
          ? {
              kto: n.podmiot,
              opis: `${n.rynek.toLowerCase()} ${n.strona === "ponizej" ? "poniżej" : "powyżej"} ${String(n.linia).replace(".", ",")}`,
              p: n.p_model,
              kurs: n.kurs,
              bukmacher: n.bukmacher,
            }
          : null,
        szanse: typyMeczu.map((t) => t.p_model),
      };
    });
  const meczeE = meczeWszystkie.filter((m) => m.najlepszy).slice(0, 8);

  /* drabinka z radaru */
  type Radar = {
    podmiot: string;
    podmiot_id?: number;
    pozycja: string;
    druzyna: string;
    przeciwnik: string;
    mecz: string;
    kickoff_ts: number;
    hero: {
      linia: number;
      rynek?: string;
      rynek_kod?: string;
      bukmacher?: string;
      /** cena z pierwszej publikacji – po niej rozlicza się 1. szczebel */
      kurs_publikacji?: number;
      kurs_teraz?: number;
      kurs_teraz_bukmacher?: string;
      kurs?: number;
      traf?: number;
      z?: number;
      traf5?: number;
      z5?: number;
      powod_szczebla?: string | null;
      wartosc_rozjazdu?: number;
      powod_wejscia?: string;
    };
    kategoria?: string;
    rozjazd_pewniak?: boolean;
    rodzaj?: string;
    udzial_startow?: number | null;
    ostatni_wystep_min?: number | null;
    /** skład OGŁOSZONY (pipeline od 11.10); `xi` miesza ogłoszony z przewidywanym */
    xi_ogloszony?: boolean;
    rynki: {
      rynek: string;
      rynek_kod?: string;
      ostatnie: number[];
      minuty: number[];
      rywale: string[];
      drabinka: {
        linia: number; kurs: number; p_final: number; bukmacher?: string;
        rozjazd?: { superbet?: number; betclic?: number; gdzie?: string; roznica_pp?: number; typ?: string } | null;
      }[];
      linie_pelne: Record<string, number>;
      /** u kogo każda linia – tylko wyjątki od Superbetu (pipeline od 05.10) */
      linie_bukmacher?: Record<string, string>;
      /** ta sama linia u Betclica, pewna cena (pipeline / warsztat) */
      linie_betclic?: Record<string, number>;
      kontekst?: { rywal?: { mnoznik?: number; srednia?: number; norma?: number } };
    }[];
  };
  const liczba = (x: number) => x.toFixed(1).replace(".", ",");
  const proc = (x: number) => `${Math.round(x * 100)}%`;
  /** cena polecanego szczebla u obu bukmacherów (radar `rozjazd`), kategoria karty */
  /**
   * Te same progi co radar (`PROG_OKAZJI_PP`, „pewniak taniej”): różnica
   * w punktach szansy ≥ 12 = lepsza cena; jeden ≤ 1,45 i drugi ≥ 1,75 =
   * cena mówi: pewne; inaczej ceny zgodne.
   */
  const cenyDrabinki = (wpis: Radar, r: Radar["rynki"][number]): CenyD | null => {
    const l = wpis.hero.linia;
    const roz = r.drabinka.find((x) => x.linia === l)?.rozjazd;
    const sb = roz?.superbet ?? (r.linie_bukmacher?.[String(l)] === "Betclic" ? null : r.linie_pelne?.[String(l)]) ?? null;
    const bc = roz?.betclic ?? r.linie_betclic?.[String(l)] ?? null;
    if (!sb || !bc || sb <= 1 || bc <= 1) return null;
    const lepszy = Math.max(sb, bc);
    const gorszy = Math.min(sb, bc);
    const typ = gorszy <= 1.45 && lepszy >= 1.75 ? "pewne" : (1 / gorszy - 1 / lepszy) * 100 >= 12 ? "lepsza" : "zgodne";
    return { superbet: sb, betclic: bc, lepszy: sb >= bc ? "Superbet" : "Betclic", typ };
  };
  const skladDrabinki = (wpis: Radar): DrabinkaV["sklad"] =>
    wpis.xi_ogloszony
      ? { stan: "ogloszony", opis: "W ogłoszonym składzie od pierwszej minuty" }
      : (wpis.udzial_startow ?? 0) >= 0.9 && (wpis.ostatni_wystep_min ?? 0) >= 60
        ? { stan: "pewny_start", opis: `Pewny start – zaczynał w ${Math.round((wpis.udzial_startow ?? 0) * 10)} z 10 ostatnich meczów drużyny` }
        : null;
  /**
   * RODZAJE KARTY – kolejność = ważność (pierwszy idzie do nagłówka w C i D).
   * Teksty: krótko = rzeczownik, który da się zobaczyć na karcie; zdanie =
   * fakt + liczba, która go potwierdza. Bez „pewniak”, „gwarancja” (właściciel 28.07).
   */
  const rodzajeDrabinki = (wpis: Radar, r: Radar["rynki"][number], ceny: CenyD | null): RodzajD[] => {
    const h = wpis.hero;
    const out: RodzajD[] = [];
    const traf = h.traf ?? 0;
    const z = h.z ?? 0;
    const kurs = h.kurs_publikacji ?? h.kurs ?? 0;
    const p = r.drabinka.find((x) => x.linia === h.linia)?.p_final ?? null;
    const gorszy = ceny ? (ceny.lepszy === "Superbet" ? "Betclic" : "Superbet") : null;
    const cenaU = (b: string | null) => (ceny && b ? fmtKurs(b === "Superbet" ? ceny.superbet : ceny.betclic) : "");
    if (h.powod_szczebla === "perla" && kurs)
      out.push({ kod: "perla", grupa: "cena", wNaglowku: true, krotko: "Perełka", zdanie: `Kurs ${fmtKurs(kurs)}, a ta linia weszła w ${traf} z ${z} ostatnich meczów` });
    if (ceny?.typ === "pewne")
      out.push({ kod: "cena_pewne", grupa: "cena", wNaglowku: true, krotko: "Cena mówi: pewne", zdanie: `${gorszy} daje tylko ${cenaU(gorszy)} – wycenia to jak niemal pewne; ${ceny.lepszy} płaci ${cenaU(ceny.lepszy)}` });
    if (ceny?.typ === "lepsza")
      out.push({ kod: "cena_lepsza", grupa: "cena", wNaglowku: true, krotko: "Lepsza cena", zdanie: `${ceny.lepszy} płaci ${cenaU(ceny.lepszy)}, ${gorszy} ${cenaU(gorszy)} za tę samą linię` });
    if (z >= 8 && traf / z >= 0.8)
      out.push({ kod: "seria", grupa: "forma", wNaglowku: true, krotko: `Seria ${traf}/${z}`, zdanie: `Ta linia weszła w ${traf} z ${z} ostatnich meczów` });
    if ((h.z5 ?? 0) >= 5 && h.traf5 === h.z5)
      out.push({ kod: "forma", grupa: "forma", wNaglowku: true, krotko: "Forma 5/5", zdanie: "Weszła w każdym z 5 ostatnich meczów" });
    const ryw = r.kontekst?.rywal;
    if (ryw && (ryw.mnoznik ?? 1) >= 1.1 && ryw.srednia != null && ryw.norma != null)
      out.push({
        kod: "rywal", grupa: "mecz", wNaglowku: true, krotko: "Hojny rywal",
        zdanie: `Przeciw ${druzyna(wpis.przeciwnik).nazwa} średnio ${liczba(ryw.srednia)} na zawodnika, w lidze ${liczba(ryw.norma)}`,
      });
    if (h.powod_wejscia === "przewaga" && p !== null && kurs)
      out.push({ kod: "przewaga", grupa: "cena", wNaglowku: true, krotko: "Kurs ponad szansę", zdanie: `Z analizy wychodzi ${proc(p)}, a kurs ${fmtKurs(kurs)} płaci jak za ${proc(1 / kurs)}` });
    if (wpis.rodzaj === "transfer")
      out.push({ kod: "transfer", grupa: "forma", wNaglowku: true, krotko: "Nowy w klubie", zdanie: "Mało meczów w nowym klubie – liczymy też z poprzedniego sezonu" });
    if (ceny?.typ === "zgodne")
      out.push({ kod: "ceny_zgodne", grupa: "cena", wNaglowku: false, krotko: "Ceny zgodne", zdanie: `Superbet ${fmtKurs(ceny.superbet)}, Betclic ${fmtKurs(ceny.betclic)} – obaj wyceniają to tak samo` });
    return out;
  };
  // każdy wpis radaru to jedna karta: rynek POLECANY (`hero`), nie pierwszy
  // z listy – u zawodnika z kilkoma rynkami pierwszy bywał innym niż polecany
  const zbudujDrabinke = (wpis: Radar): DrabinkaV | null => {
    const r = wpis.rynki.find((x) => (wpis.hero.rynek_kod ? x.rynek_kod === wpis.hero.rynek_kod : x.rynek === wpis.hero.rynek)) ?? wpis.rynki[0];
    if (!r) return null;
    const hist = (r.ostatnie ?? []).slice(0, 10); // od najnowszego
    // U kogo cena: szczebel ze swoim bukmacherem > mapa linii z pipeline'u >
    // (karty sprzed 05.10, bez mapy) Betclic, gdy WSZYSTKIE szczeble są od
    // Betclica – wtedy Superbet tego zawodnika nie wystawia (Güler).
    const tylkoBetclic = r.drabinka.length > 0 && r.drabinka.every((x) => x.bukmacher === "Betclic");
    const uKogo = (linia: number, l: string, d?: { bukmacher?: string }): "Superbet" | "Betclic" => {
      // radar zapisuje bukmachera szczebla TYLKO, gdy to nie Superbet
      const kto = d ? (d.bukmacher ?? "Superbet") : (r.linie_bukmacher?.[String(linia)] ?? r.linie_bukmacher?.[l] ?? (!r.linie_bukmacher && tylkoBetclic ? "Betclic" : "Superbet"));
      return kto === "Betclic" ? "Betclic" : "Superbet";
    };
    const szczeble: SzczebelV[] = Object.entries(r.linie_pelne ?? {})
      .map(([l, kurs]) => {
        const linia = Number(l);
        const d = r.drabinka.find((x) => x.linia === linia);
        const polecany = linia === wpis.hero.linia;
        // polecany szczebel niesie cenę z publikacji (po niej się rozliczy)
        // i bieżącą – kafelek pokazuje grubo bieżącą, publikacji małym „z …”
        return {
          linia,
          kurs: polecany && wpis.hero.kurs_publikacji ? wpis.hero.kurs_publikacji : kurs,
          p: d ? d.p_final : null,
          traf: hist.filter((v) => v > linia).length,
          z: hist.length,
          polecany,
          bukmacher: uKogo(linia, l, d),
          // druga cena tylko obok Superbetu (gdy szczebel jest od Betclica, to on jest ceną główną)
          betclic: uKogo(linia, l, d) === "Superbet" ? (d?.rozjazd?.betclic ?? r.linie_betclic?.[l] ?? null) : null,
          ...(polecany && wpis.hero.kurs_teraz ? { teraz: wpis.hero.kurs_teraz, terazBukmacher: wpis.hero.kurs_teraz_bukmacher ?? "Superbet" } : {}),
        };
      })
      .sort((a, b) => a.linia - b.linia);
    return {
      kto: wpis.podmiot,
      pozycja: POZYCJE[wpis.pozycja] ?? wpis.pozycja,
      druzyna: druzyna(wpis.druzyna),
      rywal: druzyna(wpis.przeciwnik),
      mecz: wpis.mecz,
      dzien: etykietaDnia(dzienTs(wpis.kickoff_ts), dzisZrodla()),
      godzina: GODZ_FMT.format(new Date(wpis.kickoff_ts * 1000)),
      rynek: r.rynek,
      szczeble,
      historia: hist.slice().reverse(),
      minuty: (r.minuty ?? []).slice(0, 10).reverse(),
      rywale: (r.rywale ?? []).slice(0, 10).reverse(),
      ts: wpis.kickoff_ts,
      podmiotId: wpis.podmiot_id,
      klucz: `${wpis.podmiot_id ?? wpis.podmiot}-${r.rynek_kod ?? r.rynek}`,
      ceny: cenyDrabinki(wpis, r),
      sklad: skladDrabinki(wpis),
      rodzaje: rodzajeDrabinki(wpis, r, cenyDrabinki(wpis, r)),
    };
  };
  const drabinkiLista = ((zrodlo().radar as { wpisy?: Radar[] }).wpisy ?? [])
    .map(zbudujDrabinke)
    .filter((d): d is DrabinkaV => d !== null)
    .sort((a, b) => (a.ts ?? 0) - (b.ts ?? 0));
  // warsztat i słowniczek pokazują jedną przykładową
  const drabinka = drabinkiLista[0] ?? null;

  /* kupony */
  type KuponS = {
    cel: number;
    kurs_laczny: number;
    p_model: number;
    horyzont: string;
    mecze_ze_skladami?: number;
    mecze_lacznie?: number;
    najslabszy_idx?: number;
    legi: {
      podmiot: string;
      druzyna: string;
      rynek: string;
      strona: string;
      linia: number;
      kurs: number;
      p_pokaz: number;
      mecz: string;
      kickoff_ts: number;
      bukmacher: string;
    }[];
  };
  const kupony: KuponV[] = (zrodlo().kupony as KuponS[]).slice(0, 3).map((k) => ({
    cel: k.cel,
    kurs: k.kurs_laczny,
    p: k.p_model,
    horyzont: k.horyzont,
    sklady: k.mecze_ze_skladami ?? 0,
    mecze: k.mecze_lacznie ?? k.legi.length,
    najslabszy: k.najslabszy_idx ?? -1,
    nogi: k.legi
      .map((l): NogaV => {
        const [g, h] = l.mecz.split(" – ");
        const wiecej = l.rynek.startsWith("Więcej");
        return {
          kto: wiecej ? l.druzyna : l.podmiot,
          opis: wiecej
            ? `więcej ${l.rynek.replace(/^Więcej:\s*/i, "").toLowerCase()} niż rywal`
            : `${l.rynek.toLowerCase()} ${l.strona === "ponizej" ? "poniżej" : "powyżej"} ${String(l.linia).replace(".", ",")}`,
          kurs: l.kurs,
          p: l.p_pokaz,
          mecz: l.mecz,
          gosp: druzyna(g ?? ""),
          gosc: druzyna(h ?? ""),
          godzina: GODZ_FMT.format(new Date(l.kickoff_ts * 1000)),
          dzien: etykietaDnia(dzienTs(l.kickoff_ts), dzisZrodla()),
          ts: l.kickoff_ts,
          bukmacher: l.bukmacher,
        };
      })
      .sort((a, b) => a.ts - b.ts),
  }));

  return { ...baza, karty, meczeE, meczeWszystkie, drabinka, drabinkiLista, kupony };
}

export type DaneElementow = ReturnType<typeof przygotujElementy>;
