/**
 * Etap 7 – surowe dane z Supabase w kształcie migawki warsztatu (`_dane/zrodlo.ts`).
 * Te same klucze, te same pola – adaptery z warsztatu liczą na nich bez zmian.
 *
 * Wszystkie gettery idą przez cache z `lib/data.ts` (revalidate) – żadnych
 * dodatkowych pobrań poza tym, co stara aplikacja i tak ciągnęła.
 */

import { MIGAWKA, zDanymi, type Surowe } from "@/app/projekt/_dane/zrodlo";
import {
  getDruzynyForma,
  getKalibracja,
  getKupony,
  getKursyMeczu,
  getLegiPool,
  getMecze,
  getMeta,
  getRadar,
  getTypyWyniki,
  getValueBets,
  getZawodnicyDruzyn,
  getZawodnicyTypow,
  terazTs,
} from "@/lib/data";
import { bezZjechanych, pulaPoKursieTeraz } from "@/lib/kursTeraz";
import type { Mecz } from "@/lib/types";

type MeczZNumerami = Mecz & {
  gospodarz_id?: number;
  gosc_id?: number;
  turniej_id?: number;
  oferta?: { zawodnicy: number; rynki: number; linie: number };
};

/** Mapa drużyn uzupełniona o numery Sofascore z meczów (pipeline 7B). Mapa wygrywa – ma barwy i kody. */
function zNumerowDruzyn(mecze: Mecz[]): Surowe["druzyny"] {
  const mapa = MIGAWKA.druzyny as Record<string, { id?: number | null }>;
  const out: Record<string, unknown> = { ...mapa };
  for (const m of mecze as MeczZNumerami[]) {
    for (const [nazwa, id] of [[m.gospodarz, m.gospodarz_id], [m.gosc, m.gosc_id]] as const) {
      if (!id || !nazwa) continue;
      const znana = mapa[nazwa];
      if (!znana) out[nazwa] = { id, code: "", c1: "", c2: "", kraj: "", short: nazwa, narodowa: false, kraj_slug: "" };
      else if (!znana.id) out[nazwa] = { ...znana, id };
    }
  }
  return out;
}

/** Mapa lig uzupełniona o numery rozgrywek z meczów (logo ligi z Sofascore). */
function zNumerowLig(mecze: Mecz[]): Surowe["ligi"] {
  const mapa = MIGAWKA.ligi as Record<string, { id?: number | null }>;
  const out: Record<string, unknown> = { ...mapa };
  for (const m of mecze as MeczZNumerami[]) {
    if (m.turniej_id && m.liga && !mapa[m.liga]) out[m.liga] = { id: m.turniej_id, kraj: "", kategoria: "", flaga: "", c1: "", c2: "" };
  }
  return out;
}

/** Tylko herby z numerami z meczów – dla miejsc, które nie potrzebują reszty danych (indeks szukania w układzie). */
export function zHerbamiMeczow<T>(mecze: Mecz[], f: () => T): T {
  return zDanymi({ ...MIGAWKA, druzyny: zNumerowDruzyn(mecze), ligi: zNumerowLig(mecze) }, f);
}

export async function pobierzSurowe(): Promise<Surowe> {
  const [typy, mecze, zawodnicy, druzynyForma, radar, kupony, legiPool, wyniki] = await Promise.all([
    getValueBets(),
    getMecze(),
    getZawodnicyTypow(),
    getDruzynyForma(),
    getRadar(),
    getKupony(),
    getLegiPool(),
    getTypyWyniki(),
  ]);
  // podsumowanie oferty: gotowe w `matches` (7B); mecz bez niego = brak liczb, nie zgadujemy
  const oferta = Object.fromEntries(
    (mecze as MeczZNumerami[]).filter((m) => m.oferta).map((m) => [String(m.id), m.oferta!]),
  );
  // „sugestie” (brak kursu, tylko podpowiedź modelu) nie są typami z listy
  const naLiscie = typy.filter((t) => !t.sugestia);
  return {
    // typ, którego kursu już nie ma (poniżej podłogi), schodzi z list; Wyniki
    // czytają `typy_wyniki`, więc tam zostaje z ceną z publikacji – patrz lib/kursTeraz.ts
    typy: bezZjechanych(naLiscie),
    mecze,
    zawodnicy,
    druzynyForma,
    radar,
    kupony,
    // pula po cenie teraz – z PEŁNEJ listy, także typów zdjętych wyżej
    legiPool: pulaPoKursieTeraz(legiPool, naLiscie),
    wyniki,
    oferta,
    // kadry tylko dla oglądanego meczu – dokłada je `zKadramiMeczu`
    pokrycia: { mecze: [] },
    // kuchnia (Kontrola) tylko dla admina – dokłada ją `zKuchnia`, nigdy dla klienta
    admin: null,
    // herby i barwy: mapa z warsztatu (Sofascore) + numery z meczów (7B) –
    // drużyna spoza mapy dostaje prawdziwy herb, barwy zostają neutralne
    druzyny: zNumerowDruzyn(mecze),
    ligi: zNumerowLig(mecze),
    teraz: terazTs(),
  };
}

/**
 * Strona meczu: pełne kadry obu drużyn (koszyki `players_dNN`, jak na starej
 * stronie meczu – ten sam transfer) i kursy na zawodników tego meczu.
 */
export async function zKadramiMeczu(surowe: Surowe, mecz: Mecz): Promise<Surowe> {
  const [zawodnicy, dwa] = await Promise.all([getZawodnicyDruzyn([mecz.gospodarz, mecz.gosc]), getKursyMeczu(mecz.id)]);
  // kursy obu bukmacherów osobno (7B); brak paczki = brak kursów (głośno w logu), nie stara siatka
  if (dwa === null) console.error(`[data] brak paczki kursów dla meczu ${mecz.id}`);
  const kursy = dwa ?? {};
  return {
    ...surowe,
    pokrycia: { mecze: [{ id: mecz.id, gosp: mecz.gospodarz, gosc: mecz.gosc, zawodnicy, kursy }] },
  };
}

/**
 * Wyniki › Kontrola (tylko admin): ta sama paczka co migawka `admin.json` –
 * pełne typy_wyniki (bez dni), meta.uczenie_stan i egzamin modelu. Wołać
 * WYŁĄCZNIE po sprawdzeniu roli na serwerze (web/AGENTS.md: klient nie może
 * dostać kuchni nawet w propsach).
 */
export async function zKuchnia(surowe: Surowe): Promise<Surowe> {
  const [tw, meta, kal] = await Promise.all([getTypyWyniki(), getMeta(), getKalibracja()]);
  const t = tw as unknown as Record<string, unknown> & { kupony?: unknown[]; kupony_wygrane?: unknown[] };
  return {
    ...surowe,
    admin: {
      typy: { ...t, strumienie_skrot: t.skutecznosc_strumienie },
      kupony: (t.kupony ?? []).slice(0, 12),
      kupony_wygrane_n: (t.kupony_wygrane ?? []).length,
      meta: {
        uczenie_stan: (meta as unknown as Record<string, unknown>).uczenie_stan,
        wygenerowano_ts: meta.wygenerowano_ts,
        meczow_kalibracja: (meta as unknown as Record<string, unknown>).meczow_kalibracja,
      },
      kalibracja: kal,
    },
  };
}
