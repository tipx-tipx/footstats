/**
 * Etap 5 – dane do układów stron: WSZYSTKIE typy jako karty (z historią
 * i powodami), kupon dnia z tego samego budowniczego co strona Kupony
 * i krótkie podsumowanie wyników z ostatnich dni.
 */

import { zlozKupon } from "@/lib/kuponBuilder";
import type { LegPool } from "@/lib/types";

import { powodPoLudzku, przygotujElementy, type KartaV } from "./elementy";
import { druzyna, dzienTs, etykietaDnia, GODZ_FMT, polkaNaStronie, POZYCJE, type DruzynaV } from "./przygotuj";
import { dzisZrodla, zrodlo } from "./zrodlo";


export type KartaStrony = KartaV & {
  polka: string;
  ts: number;
  meczId: number;
  gosp: string;
  gosc: string;
  gospD: DruzynaV;
  goscD: DruzynaV;
  liga: string;
};

/** Drużyny: średnie obu drużyn w rynkach, na które mamy typy w tym meczu */
export type Pojedynek = { kod: string; nazwa: string; gosp: number | null; gosc: number | null; n: number };

const NAZWY_RYNKOW: Record<string, string> = {
  team_corners: "Rzuty rożne",
  team_goals: "Gole",
  team_shots: "Strzały",
  team_sot: "Strzały celne",
  team_cards: "Kartki",
  team_fouls: "Faule",
};

type Czynnik = { nazwa: string; opis: string; mnoznik: number | null };
type TypS = {
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
  uzasadnienie?: { czynniki?: Czynnik[] };
};
type Forma = { ostatnie: number[]; rywale?: string[]; minuty?: number[]; ts?: number[]; kadra?: boolean[] };

const data = (ts: number) => {
  const d = new Date(ts * 1000);
  return `${d.getUTCDate()}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
};

export function przygotujStrony() {
  const DZIS = dzisZrodla();
  const TERAZ = zrodlo().teraz;
  const baza = przygotujElementy();
  const typy = zrodlo().typy as TypS[];
  const mecze = new Map((zrodlo().mecze as { id: number; gospodarz: string; gosc: string; liga: string }[]).map((m) => [m.id, m]));
  const zaw = new Map((zrodlo().zawodnicy as { id: number; pozycja: string; forma: Record<string, Forma> }[]).map((z) => [z.id, z]));
  const dr = new Map((zrodlo().druzynyForma as { nazwa: string; forma: Record<string, Forma> }[]).map((d) => [d.nazwa, d]));

  const karty: KartaStrony[] = [];
  for (const t of typy) {
    const druzynowy = t.podmiot_typ === "druzyna";
    const f = druzynowy ? dr.get(t.podmiot)?.forma?.[t.rynek_kod] : zaw.get(t.podmiot_id)?.forma?.[t.rynek_kod];
    const m = mecze.get(t.mecz_id);
    // typ drużynowy na cały mecz (np. rożne w meczu) nie ma własnej historii – karta bez kratek
    if (!m || (!f && !druzynowy)) continue;
    const n = f ? Math.min(10, f.ostatnie.length) : 0;
    karty.push({
      id: t.id,
      // rynek „w meczu” dotyczy obu drużyn razem, nie drużyny z pola podmiot
      kto: t.rynek_kod.startsWith("match_") ? "Cały mecz" : t.podmiot,
      pozycja: druzynowy ? "drużyna" : (POZYCJE[zaw.get(t.podmiot_id)?.pozycja ?? ""] ?? ""),
      druzyna: druzyna(t.druzyna),
      rywal: druzyna(t.przeciwnik),
      dzien: etykietaDnia(dzienTs(t.kickoff_ts), DZIS),
      godzina: GODZ_FMT.format(new Date(t.kickoff_ts * 1000)),
      rynek: t.rynek,
      strona: t.strona,
      linia: t.linia,
      kurs: t.kurs,
      szansa: t.p_model,
      bukmacher: t.bukmacher,
      historia: (f?.ostatnie ?? []).slice(0, n).reverse(),
      rywale: (f?.rywale ?? []).slice(0, n).reverse(),
      minuty: (f?.minuty ?? Array(n).fill(90)).slice(0, n).reverse(),
      daty: (f?.ts ?? []).slice(0, n).reverse().map(data),
      kadra: (f?.kadra ?? Array(n).fill(false)).slice(0, n).reverse(),
      kursUczciwy: t.fair_kurs ?? null,
      kursTeraz: t.kurs_teraz ?? null,
      kursTerazBukmacher: t.kurs_teraz_bukmacher,
      uzasadnienie: null,
      podmiotTyp: druzynowy ? "druzyna" : "zawodnik",
      podmiotId: druzynowy ? undefined : t.podmiot_id,
      mecz: `${m.gospodarz} – ${m.gosc}`,
      powody: (t.uzasadnienie?.czynniki ?? []).map((c) => powodPoLudzku(c, t.rynek)).filter((x): x is NonNullable<typeof x> => x !== null),
      polka: polkaNaStronie(t.polka, t.p_model),
      ts: t.kickoff_ts,
      meczId: t.mecz_id,
      gosp: m.gospodarz,
      gosc: m.gosc,
      gospD: druzyna(m.gospodarz),
      goscD: druzyna(m.gosc),
      liga: m.liga,
    });
  }

  /* pojedynki: dla każdego meczu z typem drużynowym – średnie z 10 ostatnich
     meczów obu drużyn w tych rynkach (rynek „w meczu” = ten sam rynek drużyn) */
  const pojedynki: Record<number, Pojedynek[]> = {};
  const sr = (nazwa: string, kod: string) => {
    const w = dr.get(nazwa)?.forma?.[kod]?.ostatnie?.slice(0, 10) ?? [];
    return { v: w.length ? w.reduce((a, b) => a + b, 0) / w.length : null, n: w.length };
  };
  for (const t of typy) {
    if (t.podmiot_typ !== "druzyna") continue;
    const m = mecze.get(t.mecz_id);
    if (!m) continue;
    const kod = t.rynek_kod.replace(/^match_/, "team_");
    if (!NAZWY_RYNKOW[kod]) continue;
    const lista = (pojedynki[t.mecz_id] ??= []);
    if (lista.some((p) => p.kod === kod)) continue;
    const g = sr(m.gospodarz, kod);
    const h = sr(m.gosc, kod);
    lista.push({ kod, nazwa: NAZWY_RYNKOW[kod], gosp: g.v, gosc: h.v, n: Math.min(g.n, h.n) });
  }

  /* kupon dnia – DOKŁADNIE kupon, od którego startuje kreator na stronie Kupony
     (KreatorV2, ustawienia domyślne): cel ×5 (4,4–5,6), styl zbalansowany,
     1 typ z meczu, wszystkie dni, i ta sama podmiana najsłabszej nogi na
     pewniejszy zamiennik, gdy kurs dalej mieści się w celu. 01.10: wcześniej
     strona główna liczyła własny kupon (3,2–5,5 z doby) – pod tą samą nazwą
     klient widział dwa różne kupony. */
  const pula = (zrodlo().legiPool as LegPool[]).filter((l) => l.kickoff_ts > TERAZ);
  const CEL = 5;
  const k0 = zlozKupon(pula, CEL * 0.88, CEL * 1.12, { profil: "zbalansowany", minLegi: 2, maxNaMecz: 1, przypiete: [], wykluczone: new Set(), teraz: TERAZ });
  const pNogi = (l: LegPool) => l.p_pokaz ?? l.p_model;
  const kd = (() => {
    if (!k0) return null;
    const a = k0.alternatywa;
    const stara = a ? k0.legi[a.zamiast_idx] : null;
    if (a && stara && a.kurs_po >= CEL * 0.88 && a.kurs_po <= CEL * 1.12 && pNogi(a) > pNogi(stara)) {
      return { legi: k0.legi.map((l, i) => (i === a.zamiast_idx ? (a as LegPool) : l)), kurs_laczny: a.kurs_po };
    }
    return { legi: k0.legi, kurs_laczny: k0.kurs_laczny };
  })();
  const kuponDnia = kd
    ? {
        kurs: kd.kurs_laczny,
        szansa: kd.legi.reduce((a, l) => a * (l.p_pokaz ?? l.p_model), 1),
        nogi: kd.legi
          .slice()
          .sort((a, b) => a.kickoff_ts - b.kickoff_ts)
          .map((l) => ({
            kto: l.podmiot,
            opis: `${l.rynek.replace(/\s*drużyny\s*/, " ").trim().toLowerCase()} ${l.strona === "ponizej" ? "poniżej" : "powyżej"} ${String(l.linia).replace(".", ",")}`,
            kurs: l.kurs,
            godzina: GODZ_FMT.format(new Date(l.kickoff_ts * 1000)),
            dzien: etykietaDnia(dzienTs(l.kickoff_ts), DZIS),
          })),
      }
    : null;

  /* wyniki: ostatnie 7 dni (weszło / rozstrzygnięte). `rozliczone` w danych
     dnia NIE zawiera zwrotów – wcześniej odejmowaliśmy je drugi raz
     i 7 dni wychodziło 62 z 99 zamiast 62 z 113 (poprawione 01.10) */
  type Dzien = { dzien: string; trafione: number; rozliczone: number };
  const dni = ((zrodlo().wyniki as { skutecznosc_dzienna: Dzien[] }).skutecznosc_dzienna ?? []).slice(0, 7);
  const wyniki = dni.map((d) => ({ dzien: d.dzien, ok: d.trafione, n: d.rozliczone })).reverse();
  const suma = wyniki.reduce((a, d) => ({ ok: a.ok + d.ok, n: a.n + d.n }), { ok: 0, n: 0 });

  /* lista meczów (narzędzie pokryć): oferta zawodnicza i nasze typy na mecz */
  const oferta = zrodlo().oferta;
  const infoMeczow: Record<number, { zawodnicy: number; rynki: number; typy: number }> = {};
  for (const m of baza.meczeWszystkie) {
    infoMeczow[m.id] = {
      zawodnicy: oferta[String(m.id)]?.zawodnicy ?? 0,
      rynki: oferta[String(m.id)]?.rynki ?? 0,
      typy: typy.filter((t) => t.mecz_id === m.id).length,
    };
  }

  return { ...baza, kartyStrony: karty, kuponDnia, wyniki, sumaWynikow: suma, pojedynki, infoMeczow };
}

export type DaneStron = ReturnType<typeof przygotujStrony>;
