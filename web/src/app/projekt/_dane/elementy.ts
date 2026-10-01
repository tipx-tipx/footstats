/**
 * Etap 3 – dane do głównych elementów (wiersz meczu, karta typu, drabinka,
 * kupon) z tej samej zamrożonej migawki co etapy 1–2.
 */

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

export type SzczebelV = { linia: number; kurs: number; p: number | null; traf: number; z: number; polecany: boolean };

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
    hero: { linia: number; rynek?: string; rynek_kod?: string };
    rynki: {
      rynek: string;
      rynek_kod?: string;
      ostatnie: number[];
      minuty: number[];
      rywale: string[];
      drabinka: { linia: number; kurs: number; p_final: number }[];
      linie_pelne: Record<string, number>;
    }[];
  };
  // każdy wpis radaru to jedna karta: rynek POLECANY (`hero`), nie pierwszy
  // z listy – u zawodnika z kilkoma rynkami pierwszy bywał innym niż polecany
  const zbudujDrabinke = (wpis: Radar): DrabinkaV | null => {
    const r = wpis.rynki.find((x) => (wpis.hero.rynek_kod ? x.rynek_kod === wpis.hero.rynek_kod : x.rynek === wpis.hero.rynek)) ?? wpis.rynki[0];
    if (!r) return null;
    const hist = (r.ostatnie ?? []).slice(0, 10); // od najnowszego
    const szczeble: SzczebelV[] = Object.entries(r.linie_pelne ?? {})
      .map(([l, kurs]) => {
        const linia = Number(l);
        const d = r.drabinka.find((x) => x.linia === linia);
        return {
          linia,
          kurs,
          p: d ? d.p_final : null,
          traf: hist.filter((v) => v > linia).length,
          z: hist.length,
          polecany: linia === wpis.hero.linia,
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
