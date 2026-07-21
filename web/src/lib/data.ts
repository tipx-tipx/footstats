/**
 * Warstwa danych.
 *
 * Dwa źródła, jeden interfejs:
 *  1. Supabase (produkcja na Vercel) — gdy ustawione SUPABASE_URL + SUPABASE_ANON_KEY.
 *     Pipeline (GitHub Actions / lokalnie) wypycha snapshoty do tabeli app_data,
 *     aplikacja czyta je tutaj. Odświeżane co godzinę (revalidate).
 *  2. Pliki lokalne (dev / brak Supabase) — bundlowane JSON-y z data/demo.
 */

import valueBetsLocal from "@/data/demo/value_bets.json";
import matchesLocal from "@/data/demo/matches.json";
import playersLocal from "@/data/demo/players.json";
import calibrationLocal from "@/data/demo/calibration.json";
import metaLocal from "@/data/demo/meta.json";
import kuponyLocal from "@/data/demo/kupony.json";
import typyWynikiLocal from "@/data/demo/typy_wyniki.json";
import oddsSuperbetLocal from "@/data/demo/odds_superbet.json";
import legiPoolLocal from "@/data/demo/legi_pool.json";
import odrzuceniaLocal from "@/data/demo/odrzucenia.json";
import stsValueLocal from "@/data/demo/sts_value.json";
import druzynyFormaLocal from "@/data/demo/druzyny_forma.json";

import type {
  DruzynaForma,
  Kalibracja,
  Kupon,
  LegPool,
  Mecz,
  Meta,
  OddsSuperbet,
  Odrzucenie,
  StsValue,
  TypyWyniki,
  ValueBet,
  Zawodnik,
} from "./types";

type Bundle = {
  value_bets: ValueBet[];
  matches: Mecz[];
  players: Zawodnik[];
  calibration: Kalibracja;
  meta: Meta;
  kupony: Kupon[];
  typy_wyniki: TypyWyniki;
  odds_superbet: OddsSuperbet;
  legi_pool: LegPool[];
  odrzucenia: Odrzucenie[];
  sts_value: StsValue;
  druzyny_forma: DruzynaForma[];
};

const LOCAL: Bundle = {
  value_bets: valueBetsLocal as unknown as ValueBet[],
  matches: matchesLocal as unknown as Mecz[],
  players: playersLocal as unknown as Zawodnik[],
  calibration: calibrationLocal as unknown as Kalibracja,
  meta: metaLocal as unknown as Meta,
  kupony: kuponyLocal as unknown as Kupon[],
  typy_wyniki: typyWynikiLocal as unknown as TypyWyniki,
  odds_superbet: oddsSuperbetLocal as unknown as OddsSuperbet,
  legi_pool: legiPoolLocal as unknown as LegPool[],
  odrzucenia: odrzuceniaLocal as unknown as Odrzucenie[],
  sts_value: stsValueLocal as unknown as StsValue,
  druzyny_forma: druzynyFormaLocal as unknown as DruzynaForma[],
};

const SUPABASE_URL = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON =
  process.env.SUPABASE_ANON_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/**
 * Odetnij mecze, które już się zaczęły: typ nie do obstawienia nie może
 * wisieć na tablicy (pewniaki/STS/okazje), nawet gdy pipeline chwilowo
 * nie podmienił snapshotu. Kupony zostają — ich status pokazuje historia.
 */
// zapas na obstawienie — jak pipeline (kupony.MARGINES_STARTU_S): kupon na
// mecz startujący za 3 minuty jest praktycznie nieobstawialny
const MARGINES_STARTU_S = 15 * 60;

function tylkoNadchodzace(bundle: Bundle): Bundle {
  const now = Math.floor(Date.now() / 1000);
  return {
    ...bundle,
    value_bets: bundle.value_bets.filter((b) => b.kickoff_ts > now),
    matches: bundle.matches.filter((m) => m.kickoff_ts > now),
    // pula do generatora na żądanie: tylko mecze z zapasem na obstawienie
    legi_pool: bundle.legi_pool.filter(
      (l) => l.kickoff_ts > now + MARGINES_STARTU_S,
    ),
    // value bety STS: kurs bywa ulotny, ale mecz po starcie i tak nie do zagrania
    sts_value: {
      ...bundle.sts_value,
      alerty: bundle.sts_value.alerty.filter((a) => (a.mecz_ts ?? 0) > now),
    },
  };
}

async function fetchBundle(): Promise<Bundle> {
  if (!SUPABASE_URL || !SUPABASE_ANON) return tylkoNadchodzace(LOCAL);
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/app_data?select=key,payload`,
      {
        headers: {
          apikey: SUPABASE_ANON,
          Authorization: `Bearer ${SUPABASE_ANON}`,
        },
        // cache'ujemy SAMI (loadBundle niżej): payload ~14 MB przekracza
        // limit 2 MB data cache Next, więc `revalidate` i tak nie działał
        // ("Failed to set fetch cache … over 2MB" przy każdym żądaniu),
        // a próba zapisu tylko spamowała logi
        cache: "no-store",
      },
    );
    if (!res.ok) return tylkoNadchodzace(LOCAL);
    const rows: { key: keyof Bundle; payload: unknown }[] = await res.json();
    const map = Object.fromEntries(rows.map((r) => [r.key, r.payload]));
    return tylkoNadchodzace({
      value_bets: (map.value_bets ?? LOCAL.value_bets) as ValueBet[],
      matches: (map.matches ?? LOCAL.matches) as Mecz[],
      players: (map.players ?? LOCAL.players) as Zawodnik[],
      calibration: (map.calibration ?? LOCAL.calibration) as Kalibracja,
      meta: (map.meta ?? LOCAL.meta) as Meta,
      kupony: (map.kupony ?? LOCAL.kupony) as Kupon[],
      typy_wyniki: (map.typy_wyniki ?? LOCAL.typy_wyniki) as TypyWyniki,
      odds_superbet: (map.odds_superbet ?? LOCAL.odds_superbet) as OddsSuperbet,
      legi_pool: (map.legi_pool ?? LOCAL.legi_pool) as LegPool[],
      odrzucenia: (map.odrzucenia ?? LOCAL.odrzucenia) as Odrzucenie[],
      sts_value: (map.sts_value ?? LOCAL.sts_value) as StsValue,
      druzyny_forma: (map.druzyny_forma ?? LOCAL.druzyny_forma) as DruzynaForma[],
    });
  } catch {
    return tylkoNadchodzace(LOCAL);
  }
}

/**
 * Cache bundla w pamięci instancji. Bez niego KAŻDY getter KAŻDEGO żądania
 * pobierał całe ~14 MB app_data od nowa (strona zawodników woła 6 getterów
 * w Promise.all = ~87 MB i sześć JSON.parse na jedno wejście — stąd
 * kilkusekundowe ładowanie). Jedna współdzielona obietnica deduplikuje
 * gettery w ramach renderu i równoległe żądania, a TTL 60 s (intencja
 * dawnego revalidate) niesie dane między żądaniami — instancja Fluid
 * Compute żyje dłużej niż pojedynczy request, więc kolejne wejścia mają
 * bundle od ręki. Świeży kupon po pominięciu nadal pojawia się w ~2-3 min
 * (pipeline odpalany od razu, patrz /api/kupon-pomin).
 */
const BUNDLE_TTL_MS = 60_000;
let bundleCache: { ts: number; bundle: Promise<Bundle> } | null = null;

function loadBundle(): Promise<Bundle> {
  if (bundleCache && Date.now() - bundleCache.ts < BUNDLE_TTL_MS) {
    return bundleCache.bundle;
  }
  bundleCache = { ts: Date.now(), bundle: fetchBundle() };
  return bundleCache.bundle;
}

export async function getValueBets(): Promise<ValueBet[]> {
  return (await loadBundle()).value_bets;
}

export async function getMecze(): Promise<Mecz[]> {
  return (await loadBundle()).matches;
}

/** Rejestr odrzuceń: czemu para (zawodnik, rynek) nie dostała typu. */
export async function getOdrzucenia(meczId?: number): Promise<Odrzucenie[]> {
  const wszystkie = (await loadBundle()).odrzucenia;
  return meczId == null
    ? wszystkie
    : wszystkie.filter((o) => o.mecz_id === meczId);
}

export async function getZawodnicy(): Promise<Zawodnik[]> {
  return (await loadBundle()).players;
}

/** Forma drużyn z typami drużynowymi (karta typu na /druzyny). */
export async function getDruzynyForma(): Promise<DruzynaForma[]> {
  return (await loadBundle()).druzyny_forma;
}

export async function getKalibracja(): Promise<Kalibracja> {
  return (await loadBundle()).calibration;
}

/** Znacznik czasu serwera (sekundy) — pomocnik poza komponentem, bo reguła
 *  czystości renderu nie pozwala wołać Date.now() w komponencie. */
export function terazTs(): number {
  return Math.floor(Date.now() / 1000);
}

export async function getMeta(): Promise<Meta> {
  return (await loadBundle()).meta;
}

export async function getKupony(): Promise<Kupon[]> {
  return (await loadBundle()).kupony;
}

/**
 * Kupon dnia do zajawki na stronie głównej: najbliższy grywalny zestaw
 * (wszystkie mecze przed startem), najpierw horyzont dzienny, potem
 * najniższy cel = największa szansa trafienia.
 */
export async function getKuponDnia(): Promise<Kupon | undefined> {
  const kupony = (await loadBundle()).kupony;
  const now = Math.floor(Date.now() / 1000);
  return kupony
    .filter((k) => k.legi.length > 0 && k.legi.every((l) => l.kickoff_ts > now))
    .sort(
      (a, b) =>
        Number(a.horyzont !== "dzienny") - Number(b.horyzont !== "dzienny") ||
        a.cel - b.cel,
    )[0];
}

export async function getTypyWyniki(): Promise<TypyWyniki> {
  return (await loadBundle()).typy_wyniki;
}

export async function getOddsSuperbet(): Promise<OddsSuperbet> {
  return (await loadBundle()).odds_superbet;
}

export async function getLegiPool(): Promise<LegPool[]> {
  return (await loadBundle()).legi_pool;
}

/** Value bety STS (klik użytkownika → Supabase). Alerty już po filtrze startu. */
export async function getStsValue(): Promise<StsValue> {
  return (await loadBundle()).sts_value;
}
