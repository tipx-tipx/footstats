/**
 * Etap 7 – jedno źródło danych dla adapterów `_dane/*`.
 *
 * Warsztat (/projekt) liczy wszystko z zamrożonej migawki 30.09 – domyślnie.
 * Prawdziwa aplikacja podstawia dane z Supabase (te same klucze, ten sam
 * kształt) i czas renderu na serwerze:
 *
 *   const dane = zDanymi({ ...MIGAWKA, typy: await getValueBets(), … , teraz }, () => przygotujStrony());
 *
 * Adaptery są synchroniczne, więc podmiana na czas jednego wywołania jest
 * bezpieczna (nic nie przeplata się między żądaniami).
 */

import druzynyRaw from "./druzyny.json";
import druzynyFormaRaw from "./druzyny_forma.json";
import kuponyRaw from "./kupony.json";
import pulaRaw from "./legi_pool.json";
import ligiRaw from "./ligi.json";
import meczeRaw from "./mecze.json";
import adminRaw from "./admin.json";
import ofertaRaw from "./oferta_meczow.json";
import pokryciaRaw from "./pokrycia.json";
import radarRaw from "./radar.json";
import typyRaw from "./typy.json";
import wynikiRaw from "./wyniki.json";
import zawodnicyRaw from "./zawodnicy.json";

export type Surowe = {
  /** value_bets */
  typy: unknown[];
  /** matches */
  mecze: unknown[];
  /** players (typy) */
  zawodnicy: unknown[];
  /** druzyny_forma */
  druzynyForma: unknown[];
  /** radar */
  radar: unknown;
  /** kupony */
  kupony: unknown[];
  /** legi_pool */
  legiPool: unknown[];
  /** typy_wyniki */
  wyniki: unknown;
  /** mecz_id → ilu zawodników ma kurs, ile rynków (do pipeline: lekkie podsumowanie oferty) */
  oferta: Record<string, { zawodnicy: number; rynki: number; linie: number }>;
  /** pełne kadry + kursy na zawodników dla stron meczów (w aplikacji: tylko oglądany mecz) */
  pokrycia: { mecze: unknown[] };
  /** kuchnia dla admina (Wyniki › Kontrola): typy_wyniki + meta.uczenie_stan + calibration – NIGDY do klienta */
  admin: unknown;
  /** herby i barwy drużyn (Sofascore) – do pipeline: id/kolory/kody */
  druzyny: Record<string, unknown>;
  ligi: Record<string, unknown>;
  /** „teraz” w sekundach */
  teraz: number;
};

import { TERAZ_MIGAWKI } from "./czasMigawki";

export { TERAZ_MIGAWKI };

export const MIGAWKA: Surowe = {
  typy: typyRaw as unknown[],
  mecze: meczeRaw as unknown[],
  zawodnicy: zawodnicyRaw as unknown[],
  druzynyForma: druzynyFormaRaw as unknown[],
  radar: radarRaw,
  kupony: kuponyRaw as unknown[],
  legiPool: pulaRaw as unknown[],
  wyniki: wynikiRaw,
  oferta: ofertaRaw as Surowe["oferta"],
  pokrycia: pokryciaRaw as unknown as Surowe["pokrycia"],
  admin: adminRaw,
  druzyny: druzynyRaw as Record<string, unknown>,
  ligi: ligiRaw as Record<string, unknown>,
  teraz: TERAZ_MIGAWKI,
};

let biezace: Surowe = MIGAWKA;

/** dane, na których liczą teraz adaptery */
export const zrodlo = () => biezace;

/** „dziś” po polsku (YYYY-MM-DD) dla bieżącego „teraz” */
const DZIEN_PL = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" });
export const dzisZrodla = () => DZIEN_PL.format(new Date(biezace.teraz * 1000));

/** policz `f` na podanych danych (aplikacja), potem wróć do migawki */
export function zDanymi<T>(s: Surowe, f: () => T): T {
  const poprzednie = biezace;
  biezace = s;
  try {
    return f();
  } finally {
    biezace = poprzednie;
  }
}
